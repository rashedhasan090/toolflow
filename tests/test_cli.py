from pathlib import Path

from toolflow.cli import main


def test_cli_render_sample(tmp_path: Path):
    sample = Path(__file__).resolve().parents[1] / "examples" / "sample.jsonl"
    out = tmp_path / "out"
    assert main(["render", str(sample), "--out", str(out)]) == 0
    assert (out / "flow.mmd").is_file()
    assert (out / "summary.md").is_file()
    text = (out / "flow.mmd").read_text()
    assert "sequenceDiagram" in text
    assert "web_search" in text
