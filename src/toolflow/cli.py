"""toolflow command-line interface."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .parse import parse_events
from .render import render_mermaid, render_summary


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="toolflow",
        description="Turn agent tool-call JSONL into Mermaid flow diagrams and summaries.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("path", type=Path, help="Path to a JSONL agent/tool-call log")

    r = sub.add_parser("render", help="Render Mermaid and/or summary from JSONL")
    add_common(r)
    r.add_argument(
        "--format",
        choices=("mermaid", "summary", "both"),
        default="both",
        help="Output format (default: both)",
    )
    r.add_argument("--out", type=Path, default=None, help="Directory to write flow.mmd / summary.md")
    r.add_argument("--max-steps", type=int, default=80, help="Max tool calls in Mermaid (default 80)")

    s = sub.add_parser("summarize", help="Print the markdown summary table only")
    add_common(s)
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    path: Path = args.path
    if not path.is_file():
        print(f"toolflow: file not found: {path}", file=sys.stderr)
        return 2

    events = parse_events(path)

    if args.cmd == "summarize":
        sys.stdout.write(render_summary(events))
        return 0

    fmt = args.format
    out_dir: Path | None = args.out
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)

    chunks: list[tuple[str, str, str]] = []  # title, filename, body
    if fmt in {"mermaid", "both"}:
        chunks.append(("Mermaid", "flow.mmd", render_mermaid(events, max_steps=args.max_steps)))
    if fmt in {"summary", "both"}:
        chunks.append(("Summary", "summary.md", render_summary(events)))

    if out_dir is not None:
        for _, filename, body in chunks:
            (out_dir / filename).write_text(body, encoding="utf-8")
            print(f"wrote {out_dir / filename}")
        return 0

    for i, (title, _, body) in enumerate(chunks):
        if i:
            sys.stdout.write("\n")
        sys.stdout.write(f"## {title}\n\n")
        sys.stdout.write(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
