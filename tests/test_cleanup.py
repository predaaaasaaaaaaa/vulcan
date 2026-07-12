"""cleanup + consumed-ledger: fresh state per generation, no old/new note mismatch."""

import json
import time
from pathlib import Path

import pytest

import vulcan.cli as cli


def make_run(tmp_path: Path) -> Path:
    run = tmp_path / "runs" / "v_test_clean"
    (run / "audio").mkdir(parents=True)
    (run / "assets").mkdir()
    (run / "out").mkdir()
    (run / "qc" / "frames").mkdir(parents=True)
    (run / "audio" / "mastered.wav").write_bytes(b"x" * 5000)
    (run / "audio" / "input.ogg").write_bytes(b"x" * 2000)
    (run / "assets" / "a01_rejected.png").write_bytes(b"x" * 800)
    (run / "out" / "raw.mp4").write_bytes(b"x" * 9000)
    (run / "out" / "final.mp4").write_bytes(b"x" * 9000)
    (run / "qc" / "frames" / "qc_001.png").write_bytes(b"x" * 500)
    (run / "qc" / "qc_report.json").write_text("{}")
    (run / "manifest.json").write_text("{}")
    (run / "pipeline.log").write_text("log")
    (run / "props.json").write_text("{}")
    return run


def test_cleanup_keeps_receipts_removes_noise(tmp_path):
    run = make_run(tmp_path)
    freed, _ = cli.cleanup_run(run)
    assert freed > 0
    assert (run / "out" / "final.mp4").exists()
    assert (run / "manifest.json").exists()
    assert (run / "pipeline.log").exists()
    assert (run / "qc" / "qc_report.json").exists()
    assert not (run / "audio").exists()
    assert not (run / "out" / "raw.mp4").exists()
    assert not (run / "qc" / "frames").exists()
    assert not (run / "props.json").exists()
    assert not (run / "assets").exists()


def test_cleanup_purge_removes_everything(tmp_path):
    run = make_run(tmp_path)
    cli.cleanup_run(run, purge=True)
    assert not run.exists()


def test_consumed_ledger_blocks_reforging(tmp_path, monkeypatch):
    cache_dir = tmp_path / "hermes_audio"
    cache_dir.mkdir()
    note = cache_dir / "audio_abc.ogg"
    note.write_bytes(b"ogg")

    monkeypatch.setattr(cli, "CONSUMED_LEDGER", tmp_path / "runs" / ".consumed.json")
    monkeypatch.setattr(cli.config, "get", lambda k, d=None: {
        "trigger.voice_latest_window_min": 15,
        "trigger.voice_cache_dirs": [str(cache_dir)],
    }.get(k, d))

    assert cli.find_latest_voice() == note          # fresh note found
    cli.mark_voice_consumed(note, "v_test_1")
    with pytest.raises(SystemExit, match="already forged"):
        cli.find_latest_voice()                      # same note never re-picked

    # a NEW note (new mtime) is picked up normally
    note2 = cache_dir / "audio_def.ogg"
    note2.write_bytes(b"ogg2")
    assert cli.find_latest_voice() == note2
