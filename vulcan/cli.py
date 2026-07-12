"""VULCAN CLI — the one guarded actuator Hermes invokes.

    vulcan run <voice.ogg>     full pipeline on a file
    vulcan run --latest        resolve newest cached Telegram voice note
    vulcan status <video_id>   print stage status for a run
    vulcan doctor              environment self-check

Deterministic orchestrator: every stage writes its artifact under
runs/<video_id>/ and prints a STATUS line Hermes can relay. Exit 0 = delivered
(or rendered, if delivery is agent-relayed). Non-zero = failed stage, with the
artifact trail intact.
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
import time
from pathlib import Path

from . import config
from .paths import RUNS_DIR

log = logging.getLogger("vulcan")

STAGES = ["ingest", "asr", "director", "assets", "render", "qc", "deliver"]


def status(msg: str) -> None:
    print(f"STATUS {msg}", flush=True)


def find_latest_voice() -> Path:
    """Newest .ogg in the Hermes audio caches within the freshness window."""
    window_min = config.get("trigger.voice_latest_window_min", 15)
    dirs = [Path(d) for d in config.get("trigger.voice_cache_dirs", [])]
    candidates: list[tuple[float, Path]] = []
    now = time.time()
    for d in dirs:
        if not d.is_dir():
            continue
        for f in d.glob("*.ogg"):
            age_min = (now - f.stat().st_mtime) / 60
            if age_min <= window_min:
                candidates.append((f.stat().st_mtime, f))
    if not candidates:
        raise SystemExit(
            f"ERROR no voice note newer than {window_min} min found in "
            f"{', '.join(str(d) for d in dirs)} — ask the user to resend it."
        )
    return sorted(candidates)[-1][1]


def cmd_run(args: argparse.Namespace) -> int:
    from .asr import run_asr
    from .assets.engine import resolve_all
    from .deliver import deliver_direct_bot, emit_delivery_lines, post_kit_text
    from .director.passes import direct
    from .ingest import master, probe_duration_ms, verify_lufs
    from .qc import QCFailure, run_qc
    from .render import render
    from .validate import validate_manifest

    voice = find_latest_voice() if args.latest else Path(args.voice)
    if not voice.exists():
        print(f"ERROR voice file not found: {voice}")
        return 2

    video_id = f"v_{time.strftime('%Y%m%d_%H%M%S')}"
    run_dir = RUNS_DIR / video_id
    (run_dir / "audio").mkdir(parents=True, exist_ok=True)
    shutil.copy(voice, run_dir / "audio" / f"input{voice.suffix}")
    # forensic log: every stage's INFO/WARNING lands in the run dir, so a
    # failed run explains itself without rerunning
    fh = logging.FileHandler(run_dir / "pipeline.log")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.getLogger().addHandler(fh)
    print(f"RUN_ID {video_id}")
    status(f"1/7 ingest — mastering {voice.name}")

    try:
        mastered = master(voice, run_dir / "audio", config.get("audio.target_lufs", -14.0))
        duration_ms = probe_duration_ms(mastered)
        verify_lufs(mastered, config.get("audio.target_lufs", -14.0),
                    config.get("qc.lufs_tolerance", 1.0))
        if duration_ms < 5000:
            print("ERROR voice note under 5s — nothing to forge")
            return 2
        status(f"2/7 asr — transcribing {duration_ms/1000:.0f}s of audio")
        words = run_asr(
            mastered, run_dir / "words.json", duration_ms,
            model_size=config.get("asr.model", "small"),
            compute_type=config.get("asr.compute_type", "int8"),
            language=config.get("asr.language"),
        )
        status(f"3/7 director — {len(words['words'])} words → beats + treatments (MiniMax)")
        manifest = direct(video_id, words)
        (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False))

        status(f"4/7 assets — resolving {len(manifest['assets'])} assets")
        manifest, failed = resolve_all(manifest, run_dir / "assets")
        if failed:
            # drop failed assets' beats to kinetic_type rather than dying
            for b in manifest["beats"]:
                keep = [r for r in b["assets"] if r["asset_id"] not in failed]
                if len(keep) != len(b["assets"]):
                    b["assets"] = keep
                    if b["treatment"] in ("cutout_pop", "screenshot_zoom", "emoji_burst", "logo_versus"):
                        b["treatment"] = "kinetic_type"
                        status(f"asset fallback: {b['id']} → kinetic_type (failed: {failed})")
            manifest["assets"] = [a for a in manifest["assets"] if a["asset_id"] not in failed]
        (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False))
        errs = validate_manifest(manifest, for_render=True)
        if errs:
            print(f"ERROR manifest failed render gate: {errs[:5]}")
            return 3

        status("5/7 render — Remotion is forging the video")
        mp4 = render(manifest, run_dir)

        status("6/7 qc — checking the output")
        try:
            metrics = run_qc(mp4, manifest, run_dir / "qc")
        except QCFailure as qf:
            status(f"qc failed ({qf.problems[:2]}) — one auto-repair re-render")
            mp4 = render(manifest, run_dir, out_name="raw_repair.mp4")
            metrics = run_qc(mp4, manifest, run_dir / "qc")  # second failure raises out

        final = run_dir / "out" / "final.mp4"
        shutil.copy(mp4, final)
        status(f"7/7 deliver — {metrics['size_mb']}MB, {metrics['duration_ms']/1000:.0f}s")

        post_kit = manifest.get("post_kit")
        if config.get("delivery.mode") == "direct_bot":
            ok = deliver_direct_bot(final, post_kit)
            if not ok:
                print("ERROR direct delivery failed — file is at " + str(final))
                return 4
            print("DELIVERED direct_bot")
        else:
            emit_delivery_lines(final, post_kit, run_dir / "qc" / "contact_sheet.png")
        print(f"DONE {video_id} {final}")
        return 0

    except Exception as e:
        log.exception("pipeline failed")
        print(f"ERROR {type(e).__name__}: {e}")
        return 1


def cmd_status(args: argparse.Namespace) -> int:
    run_dir = RUNS_DIR / args.video_id
    if not run_dir.exists():
        print(f"no such run: {args.video_id}")
        return 1
    marks = {
        "ingest": run_dir / "audio" / "mastered.wav",
        "asr": run_dir / "words.json",
        "director": run_dir / "manifest.json",
        "assets": run_dir / "assets",
        "render": run_dir / "out" / "raw.mp4",
        "qc": run_dir / "qc" / "qc_report.json",
        "final": run_dir / "out" / "final.mp4",
    }
    for stage, p in marks.items():
        print(f"{stage:9s} {'✅' if p.exists() else '—'}  {p}")
    return 0


def cmd_doctor(_: argparse.Namespace) -> int:
    import subprocess
    ok = True
    for cmd in (["ffmpeg", "-version"], ["ffprobe", "-version"], ["node", "--version"], ["npx", "--version"]):
        try:
            subprocess.run(cmd, capture_output=True, check=True)
            print(f"✅ {cmd[0]}")
        except Exception as e:
            print(f"❌ {cmd[0]}: {e}")
            ok = False
    try:
        config.minimax_api_key()
        print("✅ MINIMAX_API_KEY reachable")
    except Exception as e:
        print(f"❌ {e}")
        ok = False
    from .render import _local_browser
    print(f"{'✅' if _local_browser() else '❌'} chrome-headless-shell: {_local_browser()}")
    for mod in ("faster_whisper", "rembg", "transformers", "jsonschema"):
        try:
            __import__(mod)
            print(f"✅ python: {mod}")
        except ImportError:
            print(f"❌ python: {mod} missing")
            ok = False
    sfx = list((Path(__file__).parent.parent / "sfx").glob("*.wav"))
    print(f"{'✅' if len(sfx) >= 40 else '❌'} sfx cues on disk: {len(sfx)}")
    return 0 if ok else 1


def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        datefmt="%H:%M:%S")
    ap = argparse.ArgumentParser(prog="vulcan", description="voice note → vertical video")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="run the full pipeline")
    p_run.add_argument("voice", nargs="?", help="path to voice file (ogg/mp3/m4a/wav)")
    p_run.add_argument("--latest", action="store_true",
                       help="use the newest Telegram voice note from the Hermes cache")
    p_run.set_defaults(fn=cmd_run)

    p_st = sub.add_parser("status", help="show stage artifacts for a run")
    p_st.add_argument("video_id")
    p_st.set_defaults(fn=cmd_status)

    sub.add_parser("doctor", help="environment self-check").set_defaults(fn=cmd_doctor)

    args = ap.parse_args()
    if args.cmd == "run" and not args.latest and not args.voice:
        ap.error("run needs a voice file or --latest")
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
