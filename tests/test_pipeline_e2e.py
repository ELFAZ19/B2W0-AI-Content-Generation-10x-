"""End-to-end integration test running the full pipeline in deterministic mock mode."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from pipeline.__main__ import run_full_pipeline
from pipeline.assemble import run_assemble_stage
from pipeline.config import PROJECT_ROOT, load_config
from pipeline.ffmpeg_utils import probe_media


def test_full_pipeline_mock_end_to_end(tmp_path: Path) -> None:
    (tmp_path / "schema").mkdir()
    shutil.copy2(PROJECT_ROOT / "schema" / "storyboard.schema.json", tmp_path / "schema" / "storyboard.schema.json")
    shutil.copy2(PROJECT_ROOT / "storyboard.json", tmp_path / "storyboard.json")

    cfg = load_config(root=tmp_path, mode="mock")
    result = run_full_pipeline(cfg, quality="draft", force=False)

    # Check final dual-aspect MP4s exist and have valid video + audio streams
    out_9x16 = Path(result["assemble"]["outputs"][0])
    out_16x9 = Path(result["assemble"]["outputs"][1])
    assert out_9x16.exists() and out_9x16.stat().st_size > 10_000
    assert out_16x9.exists() and out_16x9.stat().st_size > 10_000

    info_v = probe_media(out_9x16)
    v_stream = next(s for s in info_v["streams"] if s["codec_type"] == "video")
    a_stream = next(s for s in info_v["streams"] if s["codec_type"] == "audio")
    assert v_stream["width"] == 540 and v_stream["height"] == 960
    assert a_stream["codec_name"] == "aac"
    assert 60.0 <= float(info_v["format"]["duration"]) <= 90.0

    info_h = probe_media(out_16x9)
    h_stream = next(s for s in info_h["streams"] if s["codec_type"] == "video")
    assert h_stream["width"] == 854 and h_stream["height"] == 480

    # Also verify Phase 1 radio cut builds cleanly
    radio_res = run_assemble_stage(cfg, cut_type="radio")
    radio_mp4 = Path(radio_res["outputs"][0])
    assert radio_mp4.exists() and radio_mp4.stat().st_size > 5_000

    # Verify runs.jsonl contains entries across stages and no raw secret strings
    log_text = cfg.runs_log_path.read_text(encoding="utf-8")
    records = [json.loads(line) for line in log_text.splitlines()]
    stages_logged = {r["stage"] for r in records}
    assert {"script", "keyframes_ref", "keyframes", "narration", "shots", "music"}.issubset(stages_logged)
