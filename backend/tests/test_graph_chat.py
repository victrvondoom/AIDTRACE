"""Graph fallback must be grounded, bounded and read-only without a model."""
from api.services.aidtrace_agent.graph_chat import answer


class Memory:
    def snapshot(self):
        return {"decisions": [{"id": "D1", "summary": "Review supplier"}], "actions": [],
                "memories": [], "sources": [{"id": "S1", "title": "Audit"}]}

    def impact_preview(self, source_id):
        assert source_id == "S1"
        return {"source_id": source_id, "would_mark_stale": [{"id": "D1"}]}

    def handoffs(self):
        return [{"memory_id": "M1", "usable": False}]


def test_counts_and_citations_come_from_current_records():
    result = answer("Show current decisions", Memory())
    assert result["answered_by"] == "graph"
    assert "1 decisions" in result["answer"]["finding"]
    assert result["answer"]["citations"] == ["D1", "S1"]


def test_impact_only_uses_an_identifier_from_the_graph():
    result = answer("What is the impact of revising S1?", Memory())
    assert "1 dependent records" in result["answer"]["finding"]
    assert result["tool_calls"][-1]["tool"] == "get_graph_impact"
    unknown = answer("What is the impact of revising MISSING?", Memory())
    assert "Choose a source ID" in unknown["answer"]["finding"]
    assert len(unknown["tool_calls"]) == 1


def test_unavailable_graph_does_not_invent_an_answer():
    class Offline:
        def snapshot(self):
            raise ConnectionError("offline")
    result = answer("Show decisions", Offline())
    assert result["status"] == "graph_unavailable"
    assert result["answer"] is None


def test_unsupported_question_does_not_pretend_to_be_a_model():
    result = answer("Write me a poem", None)
    assert result["status"] == "unsupported"
    assert result["tool_calls"] == []
    assert result["answer"] is None
