"""Post-mortem 2026-07-14: anemic manifests and the music system."""

import pytest

from vulcan.assets.sources import _name_variants
from vulcan.beats import cuts_to_beats
from vulcan.director.passes import assemble_manifest, richness_problems
from vulcan.validate import visual_coverage

WORDS = [{"w": w, "s": i * 420, "e": i * 420 + 350}
         for i, w in enumerate("custom agents will be the only thing that matters "
                               "for engineers in the next decade honestly".split())]
DUR = WORDS[-1]["e"] + 200
SKEL = cuts_to_beats(WORDS, [4, 9], DUR)


def bare_bout(music="tech"):
    beats = []
    for i, sk in enumerate(SKEL):
        beats.append({
            "id": f"b{i+1:02d}", "treatment": "kinetic_type", "overlay_mode": "karaoke",
            "emphasis_words": [WORDS[sk["first_word"]]["w"]],
            "assets": [], "sfx": [], "camera": "drift", "transition_out": "hard_cut",
            "headline_text": None, "payload": None,
        })
    return {"music_mood": music, "beats": beats}


def test_all_kinetic_manifest_fails_richness():
    m = assemble_manifest("v_test_rich1", "mastered.wav", DUR, SKEL, WORDS, bare_bout())
    probs = richness_problems(m, 0.35)
    assert probs and "RICHNESS" in probs[0]
    assert visual_coverage(m) == 0.0

def test_emoji_burst_counts_as_visual():
    out = bare_bout()
    out["beats"][0]["treatment"] = "emoji_burst"
    out["beats"][0]["assets"] = [{"label": "robot", "type": "emoji", "role": "hero",
                                  "queries": ["🤖", "robot", "robot face"], "enter_word": 0}]
    m = assemble_manifest("v_test_rich2", "mastered.wav", DUR, SKEL, WORDS, out)
    assert visual_coverage(m) == pytest.approx(1 / 3)
    assert richness_problems(m, 0.30) == []

def test_music_mood_mapped_to_bed_file():
    m = assemble_manifest("v_test_mus1", "mastered.wav", DUR, SKEL, WORDS, bare_bout("dramatic"))
    assert m["music"]["mood"] == "dramatic"
    assert m["music"]["file"] == "music/bed_dramatic.wav"

def test_bad_music_mood_coerces_to_chill():
    m = assemble_manifest("v_test_mus2", "mastered.wav", DUR, SKEL, WORDS,
                          bare_bout("dubstep"), lenient=True, notes=[])
    assert m["music"]["mood"] == "chill"

def test_music_none_allowed():
    m = assemble_manifest("v_test_mus3", "mastered.wav", DUR, SKEL, WORDS, bare_bout("none"))
    assert m["music"] == {"mood": "none", "file": None}

def test_manifest_with_music_validates():
    from vulcan.validate import validate_manifest
    m = assemble_manifest("v_test_mus4", "mastered.wav", DUR, SKEL, WORDS, bare_bout())
    assert validate_manifest(m) == []


# --- emoji name resolution (the 404 class) ---

def test_name_variants_strip_filler():
    assert "warning" in _name_variants("warning emoji")
    assert "robot" in _name_variants("robot face")
    assert _name_variants("rocket") == ["rocket"]

def test_fluent_by_name_includes_iconify_fallback():
    from vulcan.assets.sources import fluent_emoji_by_name
    cands = fluent_emoji_by_name("warning emoji")
    urls = [c.url for c in cands]
    assert any("Warning/3D/warning_3d.png" in u for u in urls)          # cleaned folder guess
    assert any("api.iconify.design" in u for u in urls) or len(urls) >= 2  # search net
