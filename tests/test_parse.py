from toolflow.parse import arg_digest, parse_events_from_lines, sanitize_mermaid_id


def test_arg_digest_stable():
    assert arg_digest({"b": 1, "a": 2}) == arg_digest({"a": 2, "b": 1})
    assert len(arg_digest({"x": 1})) == 8


def test_sanitize_mermaid_id():
    assert sanitize_mermaid_id("web.search") == "web_search"
    assert sanitize_mermaid_id("123go").startswith("t_")


def test_openai_and_anthropic_shapes():
    lines = [
        '{"type":"tool_use","name":"search","input":{"q":"a"},"duration_ms":10}',
        '{"type":"tool_result","name":"search","is_error":false}',
        '{"tool_calls":[{"function":{"name":"read","arguments":"{\\"p\\":\\"x\\"}"}}]}',
        '{"role":"tool","name":"read","ok":true,"latency_ms":5}',
        '{"event":"tool_call","tool":"shell","args":{"cmd":"ls"},"duration_ms":3}',
        '{"type":"tool_result","name":"shell","is_error":true}',
    ]
    events = parse_events_from_lines(lines)
    assert [e.name for e in events] == ["search", "read", "shell"]
    assert events[0].ok is True
    assert events[0].duration_ms == 10
    assert events[2].ok is False
