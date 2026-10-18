"""Investigation agent. Two planners share one tool surface and one event stream:

  * LLM planner (Claude tool use) when ANTHROPIC_API_KEY is set and use_llm=True
  * Deterministic planner otherwise: the same tools in a fixed order, no model call

In both cases a freeze is only ever proposed through GraphTools.propose_freeze, which applies the
policy in code. The model cannot bypass the rule that IP-only links never justify action.
"""
import json
from collections.abc import Callable

from domains.fraud import config
from domains.fraud.tools import GraphTools

Emit = Callable[[dict], None]

SYSTEM_PROMPT = (
    "You investigate flagged transactions in a fraud graph. Gather evidence with the tools before "
    "concluding. Shared device or card links are strong evidence. Shared IP links are weak and never "
    "justify action on their own. Call propose_freeze only for an account whose ring you have examined. "
    "Cite the graph path behind each conclusion. Keep reasoning to a few short sentences per step."
)

TOOL_SPECS = [
    {"name": "flagged_transactions",
     "description": "List flagged transactions and the account each came from.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "account_profile",
     "description": "Devices, cards and IPs linked to one account.",
     "input_schema": {"type": "object", "properties": {"account_id": {"type": "string"}},
                      "required": ["account_id"]}},
    {"name": "ring_members",
     "description": "Accounts linked to this one through shared device or card, with the shortest graph path to each.",
     "input_schema": {"type": "object", "properties": {"account_id": {"type": "string"}},
                      "required": ["account_id"]}},
    {"name": "weak_links",
     "description": "Accounts that share only an IP with this one. Weak evidence; never a basis for action.",
     "input_schema": {"type": "object", "properties": {"account_id": {"type": "string"}},
                      "required": ["account_id"]}},
    {"name": "propose_freeze",
     "description": ("Propose freezing the strong-link ring around this account. The graph policy decides "
                     "the exact account set. A human must approve before anything changes."),
     "input_schema": {"type": "object", "properties": {"account_id": {"type": "string"}},
                      "required": ["account_id"]}},
]


class Investigator:
    def __init__(self, tools: GraphTools, emit: Emit, run_id: str):
        self.tools = tools
        self.emit = emit
        self.run_id = run_id
        self.mode = "deterministic"

    # ---------- entry point ----------

    def run(self, use_llm: bool = True) -> None:
        try:
            if use_llm and config.ANTHROPIC_API_KEY:
                self.mode = "llm"
                self._plan_llm()
            else:
                self._plan_deterministic()
            self.emit({"type": "done", "mode": self.mode})
        except Exception as exc:  # surfaced to the UI, never swallowed silently
            self.emit({"type": "error", "message": f"{type(exc).__name__}: {exc}"})

    # ---------- deterministic planner ----------

    def _plan_deterministic(self) -> None:
        self.emit({"type": "step", "text": "Loading flagged transactions from FalkorDB"})
        flagged = self.tools.flagged_transactions()
        self.emit({"type": "tool", "name": "flagged_transactions", "input": {},
                   "summary": f"{len(flagged)} flagged transaction(s)"})
        covered: set[str] = set()
        for item in flagged:
            acc = item["account_id"]
            self.emit({"type": "step",
                       "text": f"Following {item['transaction_id']} (amount {item['amount']}) to account {acc}"})
            if acc in covered:
                self.emit({"type": "reasoning",
                           "text": f"{acc} is already in an earlier proposal; skipping duplicate ring."})
                continue
            profile = self.tools.account_profile(acc)
            self.emit({"type": "tool", "name": "account_profile", "input": {"account_id": acc},
                       "summary": f"{len(profile.get('devices', []))} device(s), "
                                  f"{len(profile.get('cards', []))} card(s), "
                                  f"{len(profile.get('ips', []))} IP(s)"})
            members = self.tools.ring_members(acc)
            self.emit({"type": "tool", "name": "ring_members", "input": {"account_id": acc},
                       "summary": f"{len(members)} account(s) linked by device or card"})
            weak = self.tools.weak_links(acc)
            self.emit({"type": "tool", "name": "weak_links", "input": {"account_id": acc},
                       "summary": f"{len(weak)} account(s) share only an IP"})
            deepest = max((m["hops"] for m in members), default=0)
            self.emit({"type": "reasoning", "text": (
                f"{acc} is linked to {len(members)} other account(s) through shared devices or cards, "
                f"the furthest {deepest} account-hop(s) away. {len(weak)} account(s) share only an IP; "
                "those are weak evidence and are not used for a freeze.")})
            result = self.tools.propose_freeze(acc, self.run_id)
            self.emit({"type": "tool", "name": "propose_freeze", "input": {"account_id": acc},
                       "summary": "proposed" if "proposed" in result else "rejected by policy"})
            self._report_freeze(result)
            if "proposed" in result:
                covered.update(result["proposed"]["targets"])

    # ---------- LLM planner (Claude tool use) ----------

    def _plan_llm(self) -> None:
        import anthropic  # imported here so the deterministic path works without the SDK

        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        messages = [{"role": "user",
                     "content": "Investigate every flagged transaction. Propose freezes only where the graph supports them."}]
        for _ in range(12):
            resp = client.messages.create(model=config.ANTHROPIC_MODEL, max_tokens=1500,
                                          system=SYSTEM_PROMPT, tools=TOOL_SPECS, messages=messages)
            messages.append({"role": "assistant", "content": resp.content})
            if resp.stop_reason != "tool_use":
                for block in resp.content:
                    if block.type == "text" and block.text.strip():
                        self.emit({"type": "reasoning", "text": block.text.strip()})
                return
            results = []
            for block in resp.content:
                if block.type == "text" and block.text.strip():
                    self.emit({"type": "reasoning", "text": block.text.strip()})
                elif block.type == "tool_use":
                    output = self._dispatch(block.name, block.input or {})
                    results.append({"type": "tool_result", "tool_use_id": block.id,
                                    "content": json.dumps(output, default=str)})
            messages.append({"role": "user", "content": results})
        self.emit({"type": "error", "message": "LLM planner stopped after 12 turns without finishing"})

    def _dispatch(self, name: str, args: dict) -> dict:
        acc = args.get("account_id", "")
        if name == "flagged_transactions":
            out = self.tools.flagged_transactions()
        elif name == "account_profile":
            out = self.tools.account_profile(acc)
        elif name == "ring_members":
            out = self.tools.ring_members(acc)
        elif name == "weak_links":
            out = self.tools.weak_links(acc)
        elif name == "propose_freeze":
            out = self.tools.propose_freeze(acc, self.run_id)
            self._report_freeze(out)
        else:
            out = {"error": f"unknown tool {name}"}
        self.emit({"type": "tool", "name": name, "input": args,
                   "summary": f"returned {len(out) if isinstance(out, (list, dict)) else 1} item(s)"})
        return out

    # ---------- shared ----------

    def _report_freeze(self, result: dict) -> None:
        if "proposed" in result:
            self.emit({"type": "proposal", "action": result["proposed"]})
        else:
            self.emit({"type": "rejected", "reason": result.get("rejected", "policy rejected"),
                       "members": result.get("members", 0)})
