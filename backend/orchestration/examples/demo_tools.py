"""Example tools for demo_workflow.json.

    python -m orchestration validate orchestration/examples/demo_workflow.json --tools orchestration.examples.demo_tools:REGISTRY
"""

from orchestration.tools import ToolRegistry

REGISTRY = ToolRegistry()


def word_count(text: str) -> dict[str, int]:
    """Count words so an agent can check a summary against a length limit."""
    return {"words": len(text.split())}


REGISTRY.register(
    "word_count",
    word_count,
    description="Count the words in a piece of text. Use it to check length limits.",
    parameters={
        "type": "object",
        "properties": {"text": {"type": "string", "description": "The text to measure"}},
        "required": ["text"],
    },
)
