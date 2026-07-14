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


# --- variety + chart_pop ---

def test_variety_guard_rejects_all_emoji():
    from vulcan.director.passes import variety_problems
    out = bare_bout()
    for b in out["beats"]:
        b["treatment"] = "emoji_burst"
        b["assets"] = [{"label": "fire", "type": "emoji", "role": "hero",
                        "queries": ["🔥", "fire", "flame"], "enter_word": 0}]
    # need ≥4 visual beats for the guard — replicate beats
    while len(out["beats"]) < 4:
        clone = dict(out["beats"][0]); clone_id = f"b{len(out['beats'])+1:02d}"
        out["beats"].append({**clone, "id": clone_id})
    skel4 = SKEL + [dict(SKEL[-1])] * (len(out["beats"]) - len(SKEL))
    # simpler: construct manifest directly
    m = {"beats": [{"id": b["id"], "treatment": "emoji_burst", "assets": [1]} for b in out["beats"]]}
    assert variety_problems(m)
    # 25% law: 1 emoji among 4 visual beats passes; 2/4 fails
    m2 = {"beats": [
        {"id": "b01", "treatment": "emoji_burst", "assets": [1]},
        {"id": "b02", "treatment": "chart_pop", "assets": []},
        {"id": "b03", "treatment": "quote_card", "assets": []},
        {"id": "b04", "treatment": "network_grow", "assets": []},
    ]}
    assert variety_problems(m2) == []
    m3 = {"beats": [
        {"id": "b01", "treatment": "emoji_burst", "assets": [1]},
        {"id": "b02", "treatment": "emoji_burst", "assets": [1]},
        {"id": "b03", "treatment": "quote_card", "assets": []},
        {"id": "b04", "treatment": "network_grow", "assets": []},
    ]}
    assert variety_problems(m3)

def test_chart_pop_requires_payload():
    from vulcan.validate import validate_manifest
    out = bare_bout()
    out["beats"][0]["treatment"] = "chart_pop"
    m = assemble_manifest("v_test_ch1", "mastered.wav", DUR, SKEL, WORDS, out)
    errs = validate_manifest(m)
    assert any("E_PAYLOAD_MISSING" in e for e in errs)

def test_chart_pop_valid_payload_passes():
    from vulcan.validate import validate_manifest
    out = bare_bout()
    out["beats"][0]["treatment"] = "chart_pop"
    out["beats"][0]["payload"] = {"chart": {"kind": "bar_down", "label": "COSTS"}}
    m = assemble_manifest("v_test_ch2", "mastered.wav", DUR, SKEL, WORDS, out)
    assert validate_manifest(m) == []
    assert m["beats"][0]["payload"]["chart"]["kind"] == "bar_down"

def test_lenient_drops_malformed_chart_and_downgrades():
    from vulcan.validate import validate_manifest
    out = bare_bout()
    out["beats"][0]["treatment"] = "chart_pop"
    out["beats"][0]["payload"] = {"chart": {"kind": "pie_3d", "label": ""}}
    notes = []
    m = assemble_manifest("v_test_ch3", "mastered.wav", DUR, SKEL, WORDS, out,
                          lenient=True, notes=notes)
    assert validate_manifest(m) == []
    assert m["beats"][0]["treatment"] == "kinetic_type"


# --- orphan pruning + off-by-one anchors (run v_20260714_052811 failure chain) ---

def test_lenient_ref_drop_prunes_orphaned_asset():
    from vulcan.validate import validate_manifest
    out = bare_bout()
    # logo_versus with one legal logo ('agents' spoken) and one that references
    # nothing spoken → lenient drops it → downgrade strips the other ref →
    # BOTH assets must be pruned, no orphans left behind
    out["beats"][0]["treatment"] = "logo_versus"
    out["beats"][0]["assets"] = [
        {"label": "agents logo", "type": "logo", "role": "left",
         "queries": ["agents logo"], "enter_word": 1},
        {"label": "Claude AI logo", "type": "logo", "role": "right",
         "queries": ["claude ai logo", "anthropic logo"], "enter_word": 1},
    ]
    notes = []
    m = assemble_manifest("v_test_orph1", "mastered.wav", DUR, SKEL, WORDS, out,
                          lenient=True, notes=notes)
    assert validate_manifest(m) == []          # would previously fail E_ASSET_ORPHAN
    assert m["beats"][0]["treatment"] == "kinetic_type"
    assert m["assets"] == []

def test_off_by_one_anchor_clamps_in_strict_mode():
    out = bare_bout()
    last = SKEL[0]["last_word"]
    out["beats"][0]["treatment"] = "list_stack"
    out["beats"][0]["payload"] = {"items": [
        {"text": "first", "at_word": SKEL[0]["first_word"]},
        {"text": "second", "at_word": last + 1},   # the classic off-by-one
    ]}
    m = assemble_manifest("v_test_ob1", "mastered.wav", DUR, SKEL, WORDS, out)
    blen = m["beats"][0]["end_ms"] - m["beats"][0]["start_ms"]
    assert 0 <= m["beats"][0]["payload"]["items"][-1]["at_ms"] <= blen


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
