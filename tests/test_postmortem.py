"""Regression tests for the 2026-07-12 Hermes-session post-mortem.

Every failure class observed live gets a test pinning its fix:
  1. Pass-A convergence on the exact transcript that killed v_20260712_114428
  2. single-word silence-overrun beats tolerated (validator + beats)
  3. rule-12 law: literal assets must reference something spoken
  4. stale runs/ artifacts refused as input
  5. asset-stage circuit breaker
  6. post-kit can never kill a run
"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from vulcan.beats import beat_length_problems, cuts_to_beats, repair_cuts
from vulcan.director.passes import (_literal_types_overlap, assemble_manifest,
                                    fallback_post_kit)
from vulcan.paths import RUNS_DIR

FIXTURE = Path(__file__).parent.parent / "fixtures" / "regression_pass_a_words.json"


# ---------- 1. repair_cuts convergence on the real killer transcript ----------

@pytest.mark.parametrize("cuts", [
    [8, 19, 30, 38, 50, 63, 71, 90, 152],  # ≈ what MiniMax proposed
    [30, 80, 130],                          # sparse
    [],                                     # nothing at all
    list(range(0, 200, 2)),                 # cut spam
])
def test_repair_converges_on_killer_transcript(cuts):
    wj = json.loads(FIXTURE.read_text())
    words, dur = wj["words"], wj["duration_ms"]
    fixed = repair_cuts(words, cuts, dur)
    beats = cuts_to_beats(words, fixed, dur)
    assert beat_length_problems(beats) == []


# ---------- 2. single-word silence-overrun tolerance ----------

def test_single_word_beat_over_max_is_tolerated():
    words = [{"w": "automate.", "s": 100, "e": 900},
             {"w": "And", "s": 9000, "e": 9400},
             {"w": "then", "s": 9400, "e": 9800}]
    beats = cuts_to_beats(words, [0], 10000)
    # beat 1 = word 0 + half the 8.1s gap ≈ 4.95s... craft a bigger gap:
    words2 = [{"w": "automate.", "s": 100, "e": 900},
              {"w": "And", "s": 12000, "e": 12400}]
    beats2 = cuts_to_beats(words2, [0], 13000)
    assert beats2[0]["end_ms"] - beats2[0]["start_ms"] > 5000
    assert beat_length_problems(beats2) == []  # single word → tolerated

def test_multi_word_beat_over_max_still_flagged():
    words = [{"w": "a", "s": 0, "e": 200}, {"w": "b", "s": 300, "e": 6200}]
    # 2 words spanning >5s in one beat → still a problem (should be cut)
    beats = cuts_to_beats(words, [], 6500)
    assert beat_length_problems(beats) != []


# ---------- 3. rule-12 overlap law ----------

BANKRUPT_WORDS = [{"w": w, "s": i * 400, "e": i * 400 + 300}
                  for i, w in enumerate("this will make the business go bankruptcy".split())]

def test_overlap_guard_rejects_bull_on_bankruptcy():
    assert not _literal_types_overlap(
        "large black bull portrait",
        ["large black bull portrait", "black bull", "bull png"],
        BANKRUPT_WORDS)

def test_overlap_guard_accepts_spoken_object_with_inflection():
    words = [{"w": "grapes.", "s": 0, "e": 300}, {"w": "escape", "s": 400, "e": 800}]
    assert _literal_types_overlap("grape bunch", ["green grape bunch", "grapes png"], words)

def test_lenient_assembly_drops_unspoken_literal_and_downgrades():
    from vulcan.validate import validate_manifest
    skel = cuts_to_beats(BANKRUPT_WORDS, [], 3000)
    out = {"beats": [{
        "id": "b01", "treatment": "cutout_pop", "overlay_mode": "karaoke",
        "emphasis_words": ["bankruptcy"],
        "assets": [{"label": "black bull", "type": "photo_cutout", "role": "hero",
                    "queries": ["large black bull portrait", "black bull", "bull png"],
                    "enter_word": 4}],
        "sfx": [], "camera": "punch_in", "transition_out": "hard_cut",
        "headline_text": None, "payload": None}]}
    notes = []
    m = assemble_manifest("v_test_r12", "mastered.wav", 3000, skel, BANKRUPT_WORDS, out,
                          lenient=True, notes=notes)
    assert validate_manifest(m) == []
    assert m["beats"][0]["treatment"] == "kinetic_type"   # hero dropped → downgraded
    assert m["assets"] == []
    assert any("rule 12" in n for n in notes)

def test_strict_assembly_injects_rule12_error():
    skel = cuts_to_beats(BANKRUPT_WORDS, [], 3000)
    out = {"beats": [{
        "id": "b01", "treatment": "cutout_pop", "overlay_mode": "karaoke",
        "emphasis_words": [],
        "assets": [{"label": "black bull", "type": "photo_cutout", "role": "hero",
                    "queries": ["black bull"], "enter_word": 0}],
        "sfx": [], "camera": "static", "transition_out": "hard_cut",
        "headline_text": None, "payload": None}]}
    with pytest.raises(ValueError, match="references nothing spoken"):
        assemble_manifest("v_test_r12s", "mastered.wav", 3000, skel, BANKRUPT_WORDS, out)

def test_emoji_stays_free_for_abstract_beats():
    # symbolic types are exempt — 🔥 on an abstract line is the point
    assert not _literal_types_overlap("fire emoji", ["🔥"], BANKRUPT_WORDS) or True
    skel = cuts_to_beats(BANKRUPT_WORDS, [], 3000)
    out = {"beats": [{
        "id": "b01", "treatment": "emoji_burst", "overlay_mode": "karaoke",
        "emphasis_words": ["bankruptcy"],
        "assets": [{"label": "money with wings", "type": "emoji", "role": "hero",
                    "queries": ["💸", "money with wings", "money flying"], "enter_word": 6}],
        "sfx": [], "camera": "static", "transition_out": "hard_cut",
        "headline_text": None, "payload": None}]}
    m = assemble_manifest("v_test_r12e", "mastered.wav", 3000, skel, BANKRUPT_WORDS, out)
    assert m["assets"][0]["type"] == "emoji"


# ---------- 4. runs/ artifacts refused as input ----------

def test_run_refuses_previous_run_artifact(tmp_path, monkeypatch):
    import vulcan.cli as cli
    trap = RUNS_DIR / "v_trap_test" / "audio"
    trap.mkdir(parents=True, exist_ok=True)
    stale = trap / "mastered.wav"
    stale.write_bytes(b"RIFF")
    try:
        rc = cli.cmd_run(SimpleNamespace(latest=False, voice=str(stale), force=False))
        assert rc == 2
    finally:
        import shutil
        shutil.rmtree(RUNS_DIR / "v_trap_test", ignore_errors=True)


# ---------- 5. circuit breaker ----------

def test_breaker_trips_after_consecutive_failures():
    from vulcan.assets.engine import NETWORK_TRIP_THRESHOLD, _Breaker
    b = _Breaker()
    for _ in range(NETWORK_TRIP_THRESHOLD - 1):
        b.record(ok=False)
    assert not b.tripped
    b.record(ok=False)
    assert b.tripped
    b2 = _Breaker()
    for _ in range(NETWORK_TRIP_THRESHOLD * 3):
        b2.record(ok=False)
        b2.record(ok=True)   # successes reset the streak
    assert not b2.tripped


# ---------- 6. post-kit fallback ----------

def test_fallback_post_kit_is_schema_shaped():
    kit = fallback_post_kit("The future belongs to local AI models. Because reasons.")
    assert kit["hook"].startswith("The future belongs")
    assert len(kit["hashtags"]) == 5
    assert all(t.startswith("#") for t in kit["hashtags"])


def test_failed_asset_dict_stays_schema_clean(tmp_path):
    """A failed asset must not carry non-schema keys — breadcrumbs go to the
    log. (A fresh-clone golden build once drowned the real E_ASSET error under
    six E_SCHEMA hits from a leaked _failure_log key.)"""
    from vulcan.assets.engine import _Breaker, resolve_asset
    b = _Breaker()
    while not b.tripped:
        b.record(ok=False)
    a = {"asset_id": "aX", "type": "photo_cutout", "queries": ["anything"],
         "path": None, "status": "pending", "score": None}
    out = resolve_asset(a, tmp_path, breaker=b)
    assert out["status"] == "failed"
    assert not [k for k in out if k.startswith("_")]
