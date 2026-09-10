"""Render ToolEvent lists to Mermaid and markdown summaries."""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from .parse import ToolEvent, sanitize_mermaid_id


def render_mermaid(events: Iterable[ToolEvent], max_steps: int = 80) -> str:
    events = list(events)
    truncated = len(events) > max_steps
    events = events[:max_steps]

    lines = ["sequenceDiagram", "    participant Agent"]
    seen: set[str] = set()
    order: list[str] = []
    for ev in events:
        sid = sanitize_mermaid_id(ev.name)
        if sid not in seen:
            seen.add(sid)
            order.append(sid)
            # Keep a readable label via note is awkward; use participant id
            lines.append(f"    participant {sid}")

    for ev in events:
        sid = sanitize_mermaid_id(ev.name)
        lines.append(f"    Agent->>{sid}: call#{ev.step} · args:{ev.arg_digest}")
        status = "ok" if ev.ok else "error"
        if ev.duration_ms is not None:
            status = f"{status} · {ev.duration_ms:.0f}ms"
        lines.append(f"    {sid}-->>Agent: {status}")

    if truncated:
        lines.append("    Note over Agent: truncated to max-steps")
    if not events:
        lines.append("    Note over Agent: no tool calls found")
    return "\n".join(lines) + "\n"


def render_summary(events: Iterable[ToolEvent]) -> str:
    events = list(events)
    stats: dict[str, dict[str, float]] = defaultdict(
        lambda: {"calls": 0, "errors": 0, "ms_sum": 0.0, "ms_n": 0}
    )
    for ev in events:
        s = stats[ev.name]
        s["calls"] += 1
        if not ev.ok:
            s["errors"] += 1
        if ev.duration_ms is not None:
            s["ms_sum"] += ev.duration_ms
            s["ms_n"] += 1

    lines = [
        "| tool | calls | errors | avg_ms |",
        "| --- | ---: | ---: | ---: |",
    ]
    for name in sorted(stats.keys()):
        s = stats[name]
        avg = f"{s['ms_sum'] / s['ms_n']:.0f}" if s["ms_n"] else "—"
        lines.append(
            f"| `{name}` | {int(s['calls'])} | {int(s['errors'])} | {avg} |"
        )

    total_calls = sum(int(s["calls"]) for s in stats.values())
    total_errors = sum(int(s["errors"]) for s in stats.values())
    lines.append("")
    lines.append(f"**Totals:** {total_calls} calls, {total_errors} errors, {len(stats)} tools.")
    if not events:
        lines = [
            "| tool | calls | errors | avg_ms |",
            "| --- | ---: | ---: | ---: |",
            "",
            "**Totals:** 0 calls, 0 errors, 0 tools.",
        ]
    return "\n".join(lines) + "\n"
