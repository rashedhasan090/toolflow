from toolflow.parse import ToolEvent
from toolflow.render import render_mermaid, render_summary


def test_mermaid_and_summary():
    events = [
        ToolEvent(1, "search", "abcd1234", True, 12.0),
        ToolEvent(2, "search", "eeeeeeee", False, 9.0),
        ToolEvent(3, "read_file", "ffffffff", True, None),
    ]
    mmd = render_mermaid(events)
    assert "sequenceDiagram" in mmd
    assert "Agent->>search:" in mmd
    assert "error" in mmd

    summary = render_summary(events)
    assert "`search`" in summary
    assert "2 calls" in summary or "| `search` | 2 |" in summary
    assert "3 calls" in summary
