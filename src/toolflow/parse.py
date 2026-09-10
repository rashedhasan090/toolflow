"""Liberal JSONL parsers for common agent tool-call event shapes."""

from __future__ import annotations

import hashlib
import json
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Iterator


@dataclass(frozen=True)
class ToolEvent:
    step: int
    name: str
    arg_digest: str
    ok: bool
    duration_ms: float | None = None


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def arg_digest(args: Any) -> str:
    payload = "" if args is None else _canonical_json(args)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:8]


def sanitize_mermaid_id(name: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z_]", "_", name or "tool")
    if not cleaned or cleaned[0].isdigit():
        cleaned = f"t_{cleaned}"
    return cleaned[:48]


def _as_bool_error(obj: dict[str, Any]) -> bool | None:
    if "is_error" in obj:
        return bool(obj["is_error"])
    status = obj.get("status")
    if isinstance(status, str) and status.lower() in {"error", "failed", "failure"}:
        return True
    if obj.get("error"):
        return True
    if obj.get("ok") is False:
        return True
    if obj.get("ok") is True:
        return False
    return None


def _duration_ms(obj: dict[str, Any]) -> float | None:
    for key in ("duration_ms", "latency_ms", "elapsed_ms"):
        if key in obj and obj[key] is not None:
            try:
                return float(obj[key])
            except (TypeError, ValueError):
                pass
    start, end = obj.get("started_at"), obj.get("ended_at")
    if isinstance(start, str) and isinstance(end, str):
        try:
            s = datetime.fromisoformat(start.replace("Z", "+00:00"))
            e = datetime.fromisoformat(end.replace("Z", "+00:00"))
            return max(0.0, (e - s).total_seconds() * 1000.0)
        except ValueError:
            return None
    return None


def _parse_args(raw: Any) -> Any:
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"_raw": raw}
    return raw if raw is not None else {}


def _extract(obj: Any) -> list[dict[str, Any]]:
    """Normalize one JSON object into zero or more call/result dicts.

    Each dict: {kind: call|result, name, args, error: bool|None, duration_ms}
    """
    if not isinstance(obj, dict):
        return []

    duration = _duration_ms(obj)
    err = _as_bool_error(obj)
    typ = str(obj.get("type") or obj.get("event") or "").lower()
    role = str(obj.get("role") or "").lower()
    out: list[dict[str, Any]] = []

    tool_calls = obj.get("tool_calls")
    if isinstance(tool_calls, list):
        for tc in tool_calls:
            if not isinstance(tc, dict):
                continue
            fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
            name = tc.get("name") or fn.get("name") or "tool"
            raw_args = tc.get("arguments")
            if raw_args is None:
                raw_args = tc.get("args")
            if raw_args is None:
                raw_args = fn.get("arguments")
            out.append(
                {
                    "kind": "call",
                    "name": str(name),
                    "args": _parse_args(raw_args),
                    "error": False if err is None else err,
                    "duration_ms": _duration_ms(tc) or duration,
                }
            )
        return out

    if typ in {"tool_use", "tool_call"} or obj.get("event") == "tool_call":
        name = obj.get("name") or obj.get("tool") or obj.get("tool_name") or "tool"
        args = obj.get("input")
        if args is None:
            args = obj.get("arguments")
        if args is None:
            args = obj.get("args")
        out.append(
            {
                "kind": "call",
                "name": str(name),
                "args": _parse_args(args),
                "error": False if err is None else err,
                "duration_ms": duration,
            }
        )
        return out

    if typ in {"tool_result"} or role == "tool":
        name = obj.get("name") or obj.get("tool") or obj.get("tool_name") or "tool"
        out.append(
            {
                "kind": "result",
                "name": str(name),
                "args": {},
                "error": False if err is None else err,
                "duration_ms": duration,
            }
        )
        return out

    # Generic: has tool / tool_name and looks like a call
    if "tool" in obj or "tool_name" in obj:
        name = obj.get("name") or obj.get("tool") or obj.get("tool_name")
        if name and typ not in {"message", "text", "content"}:
            args = obj.get("arguments")
            if args is None:
                args = obj.get("args")
            if args is None:
                args = obj.get("input")
            out.append(
                {
                    "kind": "call",
                    "name": str(name),
                    "args": _parse_args(args),
                    "error": False if err is None else err,
                    "duration_ms": duration,
                }
            )
    return out


def iter_jsonl(path: Path) -> Iterator[Any]:
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def parse_events(path: Path) -> list[ToolEvent]:
    events: list[ToolEvent] = []
    step = 0
    # Map tool name -> index of latest call awaiting a result
    open_idx: dict[str, int] = {}

    for obj in iter_jsonl(path):
        for item in _extract(obj):
            name = item["name"]
            if item["kind"] == "call":
                step += 1
                ev = ToolEvent(
                    step=step,
                    name=name,
                    arg_digest=arg_digest(item["args"]),
                    ok=not bool(item["error"]),
                    duration_ms=item["duration_ms"],
                )
                events.append(ev)
                open_idx[name] = len(events) - 1
            else:
                idx = open_idx.get(name)
                if idx is None and events:
                    # fall back to last event with same name
                    for i in range(len(events) - 1, -1, -1):
                        if events[i].name == name:
                            idx = i
                            break
                if idx is None:
                    continue
                last = events[idx]
                events[idx] = ToolEvent(
                    step=last.step,
                    name=last.name,
                    arg_digest=last.arg_digest,
                    ok=not bool(item["error"]),
                    duration_ms=(
                        item["duration_ms"]
                        if item["duration_ms"] is not None
                        else last.duration_ms
                    ),
                )
    return events


def parse_events_from_lines(lines: Iterable[str]) -> list[ToolEvent]:
    with tempfile.NamedTemporaryFile(
        "w", suffix=".jsonl", delete=False, encoding="utf-8"
    ) as tmp:
        for line in lines:
            tmp.write(line.rstrip("\n") + "\n")
        tmp_path = Path(tmp.name)
    try:
        return parse_events(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)
