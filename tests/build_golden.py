"""Golden manifest — hand-authored to exercise EVERY treatment on the real
fixture audio. This is the render gate's input and the quality reference the
Director few-shots echo. 20 beats, all 9 treatments, both overlay modes.

Run: .venv/bin/python tests/build_golden.py  → runs/golden/manifest.json
"""

import json
import logging
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

from vulcan.assets.engine import resolve_asset
from vulcan.beats import clamp_asset_enter, cuts_to_beats
from vulcan.validate import validate_manifest

GOLDEN = Path("runs/golden")
CUTS = [6, 8, 13, 18, 25, 28, 32, 33, 37, 40, 44, 49, 51, 55, 58, 63, 68, 73, 80]

K = "kinetic_type"


def beat_plan(W, sk):
    """20 beat directions. Every anchor is a word timestamp; rel() converts to beat-relative."""
    def rel(bi, wi):
        return max(W[wi]["s"] - sk[bi]["start_ms"], 0)

    def L(bi):
        return sk[bi]["end_ms"] - sk[bi]["start_ms"]

    return [
        # b01 "This fox has a longing for grapes."
        dict(treatment="cutout_pop",
             text_overlay={"mode": "karaoke", "emphasis_words": ["fox", "grapes"]},
             assets=[{"asset_id": "a01", "role": "hero", "enter_ms": rel(0, 1), "exit_ms": L(0)}],
             sfx=[{"cue": "whoosh_02", "at_ms": max(rel(0, 1) - 80, 0)}],
             camera="punch_in", transition_out="hard_cut"),
        # b02 "He jumps,"
        dict(treatment=K,
             text_overlay={"mode": "karaoke", "emphasis_words": ["jumps"]},
             assets=[], sfx=[{"cue": "swish_01", "at_ms": rel(1, 8)}],
             camera="static", transition_out="hard_cut"),
        # b03 "but the bunch still escapes." — exercises network_grow
        dict(treatment="network_grow",
             text_overlay={"mode": "karaoke", "emphasis_words": ["escapes"]},
             assets=[], sfx=[{"cue": "riser_02", "at_ms": 100}],
             camera="static", transition_out="whip",
             payload={"network": {"label": "THE BUNCH"}}),
        # b04 "So he goes away sour,"
        dict(treatment="emoji_burst",
             text_overlay={"mode": "karaoke", "emphasis_words": ["sour"]},
             assets=[{"asset_id": "a02", "role": "hero", "enter_ms": rel(3, 18), "exit_ms": L(3)}],
             sfx=[{"cue": "pop_03", "at_ms": rel(3, 18)}],
             camera="static", transition_out="hard_cut"),
        # b05 "and, to his said, to this hour,"
        dict(treatment=K,
             text_overlay={"mode": "karaoke", "emphasis_words": ["hour"]},
             assets=[], sfx=[], camera="drift", transition_out="hard_cut"),
        # b06 "declares that he's"
        dict(treatment="tweet_card",
             text_overlay={"mode": "karaoke", "emphasis_words": ["declares"]},
             assets=[], sfx=[{"cue": "pop_02", "at_ms": 120}],
             camera="static", transition_out="hard_cut",
             payload={"tweet": {"author": "Sour Fox", "handle": "@sourfox",
                                "text": "I never liked those grapes anyway. Total waste of a jump."}}),
        # b07 "no taste for grapes."
        dict(treatment=K,
             text_overlay={"mode": "karaoke", "emphasis_words": ["taste", "grapes"]},
             assets=[], sfx=[], camera="drift", transition_out="flash"),
        # b08 "Moral."
        dict(treatment=K,
             text_overlay={"mode": "headline", "headline_text": "The moral"},
             assets=[], sfx=[{"cue": "boom_01", "at_ms": 60}],
             camera="punch_in", transition_out="hard_cut"),
        # b09 "The grapes of disappointment"
        dict(treatment="quote_card",
             text_overlay={"mode": "karaoke", "emphasis_words": ["disappointment"]},
             assets=[], sfx=[{"cue": "ding_01", "at_ms": 100}],
             camera="drift", transition_out="hard_cut",
             payload={"quote": {"text": "The grapes of disappointment are always sour.",
                                "attribution": "Aesop"}}),
        # b10 "are always sour."
        dict(treatment=K,
             text_overlay={"mode": "karaoke", "emphasis_words": ["sour"]},
             assets=[], sfx=[], camera="drift", transition_out="hard_cut"),
        # b11 "Turn to page ten."
        dict(treatment="stat_slam",
             text_overlay={"mode": "headline", "headline_text": "Turn to page ten"},
             assets=[], sfx=[{"cue": "tick_01", "at_ms": 80}, {"cue": "boom_03", "at_ms": 720}],
             camera="punch_in", transition_out="whip",
             payload={"stat_text": "10"}),
        # b12 "The cock and the pearl."
        dict(treatment="logo_versus",
             text_overlay={"mode": "karaoke", "emphasis_words": ["cock", "pearl"]},
             assets=[{"asset_id": "a03", "role": "left", "enter_ms": rel(11, 46), "exit_ms": L(11)},
                     {"asset_id": "a04", "role": "right", "enter_ms": rel(11, 49), "exit_ms": L(11)}],
             sfx=[{"cue": "whoosh_04", "at_ms": max(rel(11, 46) - 60, 0)},
                  {"cue": "boom_01", "at_ms": rel(11, 49)}],
             camera="static", transition_out="hard_cut"),
        # b13 "A rooster,"
        dict(treatment="cutout_pop",
             text_overlay={"mode": "karaoke", "emphasis_words": ["rooster"]},
             assets=[{"asset_id": "a03", "role": "hero", "enter_ms": rel(12, 51), "exit_ms": L(12)}],
             sfx=[{"cue": "whoosh_01", "at_ms": max(rel(12, 51) - 80, 0)}],
             camera="punch_in", transition_out="hard_cut"),
        # b14 "while scratching for grain," — exercises chart_pop
        dict(treatment="chart_pop",
             text_overlay={"mode": "karaoke", "emphasis_words": ["scratching"]},
             assets=[], sfx=[{"cue": "tick_02", "at_ms": 200}],
             camera="static", transition_out="hard_cut",
             payload={"chart": {"kind": "bar_up", "label": "GRAIN"}}),
        # b15 "found a pearl."
        dict(treatment="cutout_pop",
             text_overlay={"mode": "karaoke", "emphasis_words": ["pearl"]},
             assets=[{"asset_id": "a04", "role": "hero", "enter_ms": rel(14, 58), "exit_ms": L(14)}],
             sfx=[{"cue": "sparkle_01", "at_ms": rel(14, 58)}],
             camera="punch_in", transition_out="hard_cut"),
        # b16 "He just paused to explain"
        dict(treatment="screenshot_zoom",
             text_overlay={"mode": "karaoke", "emphasis_words": ["explain"]},
             assets=[{"asset_id": "a05", "role": "hero", "enter_ms": 100, "exit_ms": L(15)}],
             sfx=[{"cue": "click_03", "at_ms": 100}],
             camera="static", transition_out="flash"),
        # b17 "that a jewel's no good"
        dict(treatment="list_stack",
             text_overlay={"mode": "karaoke", "emphasis_words": ["jewel's"]},
             assets=[], sfx=[{"cue": "pop_04", "at_ms": rel(16, 66)}],
             camera="drift", transition_out="hard_cut",
             payload={"items": [{"text": "A jewel", "at_ms": rel(16, 66)},
                                {"text": "No good", "at_ms": rel(16, 68)}]}),
        # b18 "to a fowl wanting food,"
        dict(treatment=K,
             text_overlay={"mode": "karaoke", "emphasis_words": ["fowl", "food"]},
             assets=[], sfx=[], camera="drift", transition_out="hard_cut"),
        # b19 "and then kicked it aside with disdain."
        dict(treatment=K,
             text_overlay={"mode": "karaoke", "emphasis_words": ["kicked", "disdain"]},
             assets=[], sfx=[{"cue": "thud_01", "at_ms": rel(18, 76)}],
             camera="punch_in", transition_out="whip"),
        # b20 "Moral. If he asked bread,"
        dict(treatment="emoji_burst",
             text_overlay={"mode": "karaoke", "emphasis_words": ["bread"]},
             assets=[{"asset_id": "a06", "role": "hero", "enter_ms": rel(19, 85), "exit_ms": L(19)}],
             sfx=[{"cue": "cash_01", "at_ms": rel(19, 85)}],
             camera="drift", transition_out="hard_cut"),
    ]


ASSET_SPECS = [
    {"asset_id": "a01", "type": "photo_cutout", "queries": ["red fox side view", "fox animal", "red fox png"]},
    {"asset_id": "a02", "type": "emoji", "queries": ["🍋", "lemon", "sour"]},
    {"asset_id": "a03", "type": "photo_cutout", "queries": ["rooster", "rooster chicken", "rooster png"]},
    {"asset_id": "a04", "type": "photo_cutout", "queries": ["white pearl", "pearl in oyster shell", "pearl png"]},
    {"asset_id": "a05", "type": "screenshot", "queries": ["stripe.com homepage", "stripe website", "stripe dashboard"]},
    {"asset_id": "a06", "type": "emoji", "queries": ["🍞", "bread", "loaf of bread"]},
]


if __name__ == "__main__":
    (GOLDEN / "audio").mkdir(parents=True, exist_ok=True)
    (GOLDEN / "assets").mkdir(parents=True, exist_ok=True)
    shutil.copy("runs/phase2_test/audio/mastered.wav", GOLDEN / "audio" / "mastered.wav")
    shutil.copy("runs/phase2_test/words.json", GOLDEN / "words.json")

    wj = json.load(open(GOLDEN / "words.json"))
    words, dur = wj["words"], wj["duration_ms"]

    sk = cuts_to_beats(words, CUTS, dur)
    plans = beat_plan(words, sk)
    assert len(sk) == len(plans) == 20

    beats = []
    for i, (s, plan) in enumerate(zip(sk, plans)):
        blen = s["end_ms"] - s["start_ms"]
        for ref in plan["assets"]:
            old = ref["enter_ms"]
            ref["enter_ms"] = clamp_asset_enter(ref["enter_ms"], blen)
            # entrance sfx keeps its lead relative to the (possibly clamped) enter
            for sfx in plan["sfx"]:
                if abs(sfx["at_ms"] - old) <= 100:
                    sfx["at_ms"] = max(ref["enter_ms"] - (old - sfx["at_ms"]), 0)
        beats.append({
            "id": f"b{i+1:02d}",
            "start_ms": s["start_ms"], "end_ms": s["end_ms"],
            "words": [{"w": w["w"], "s": w["s"], "e": w["e"]} for w in words[s["first_word"]:s["last_word"] + 1]],
            **plan,
        })

    manifest = {
        "video_id": "v_golden_0001",
        "fps": 30, "aspect": "9:16",
        "audio": {"path": "mastered.wav", "duration_ms": dur},
        "beats": beats,
        "assets": [{**a, "path": None, "status": "pending", "score": None} for a in ASSET_SPECS],
        "music": {"mood": "chill", "file": "music/bed_chill.wav"},
    }

    errs = validate_manifest(manifest)
    if errs:
        print("VALIDATION ERRORS (pre-assets):")
        for e in errs:
            print("  ", e)
        sys.exit(1)
    print("structure valid ✅")

    for a in manifest["assets"]:
        resolve_asset(a, GOLDEN / "assets")
        print(a["asset_id"], a["status"], a.get("score"))

    errs = validate_manifest(manifest, for_render=True)
    if errs:
        print("RENDER-GATE ERRORS:")
        for e in errs:
            print("  ", e)
        sys.exit(1)

    (GOLDEN / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print(f"\ngolden manifest valid ✅ → {GOLDEN / 'manifest.json'}")
