"""assemble_manifest + apply_patches: the deterministic wall between MiniMax
output and the manifest. MiniMax mistakes must become injectable errors, never
bad manifests."""

import pytest

from vulcan.beats import cuts_to_beats
from vulcan.director.passes import apply_patches, assemble_manifest

WORDS = [
    {"w": "Apple", "s": 100, "e": 500}, {"w": "just", "s": 500, "e": 800},
    {"w": "killed", "s": 800, "e": 1200}, {"w": "the", "s": 1200, "e": 1300},
    {"w": "iPhone", "s": 1300, "e": 1900},
    {"w": "and", "s": 2600, "e": 2750}, {"w": "87", "s": 2750, "e": 3200},
    {"w": "percent", "s": 3200, "e": 3700}, {"w": "missed", "s": 3700, "e": 4100},
    {"w": "it", "s": 4100, "e": 4300},
]
DUR = 5200
SKEL = cuts_to_beats(WORDS, [4], DUR)


def b_out(**overrides):
    beats = [
        {"id": "b01", "treatment": "cutout_pop", "overlay_mode": "karaoke",
         "emphasis_words": ["Apple", "iPhone"],
         "assets": [{"label": "iphone", "type": "photo_cutout", "role": "hero",
                     "queries": ["iphone 15", "iphone", "apple phone"], "enter_word": 4}],
         "sfx": [{"cue": "whoosh_02", "at_word": 4}],
         "camera": "punch_in", "transition_out": "hard_cut",
         "headline_text": None, "payload": None},
        {"id": "b02", "treatment": "stat_slam", "overlay_mode": "headline",
         "emphasis_words": ["87", "percent"],
         "assets": [], "sfx": [{"cue": "tick_01", "at_word": 6}],
         "camera": "punch_in", "transition_out": "hard_cut",
         "headline_text": "87% missed it", "payload": {"stat_text": "87%"}},
    ]
    out = {"beats": beats}
    out.update(overrides)
    return out


def assemble(out=None):
    return assemble_manifest("v_test_asm1", "mastered.wav", DUR, SKEL, WORDS, out or b_out())


def test_happy_assembly():
    m = assemble()
    assert len(m["beats"]) == 2
    assert m["assets"][0]["asset_id"] == "a01"
    assert m["beats"][0]["assets"][0]["asset_id"] == "a01"
    # word 4 starts at 1300 → enter clamped to ≤55% of beat length
    blen = m["beats"][0]["end_ms"] - m["beats"][0]["start_ms"]
    assert m["beats"][0]["assets"][0]["enter_ms"] <= blen * 0.55 + 1

def test_missing_beat_rejected():
    out = b_out()
    out["beats"] = out["beats"][:1]
    with pytest.raises(ValueError, match="missing beats"):
        assemble(out)

def test_bad_enter_word_rejected():
    out = b_out()
    out["beats"][0]["assets"][0]["enter_word"] = 9  # word of beat 2
    with pytest.raises(ValueError, match="not a word index of this beat"):
        assemble(out)

def test_unknown_treatment_rejected():
    out = b_out()
    out["beats"][0]["treatment"] = "explode"
    with pytest.raises(ValueError, match="unknown treatment"):
        assemble(out)

def test_unknown_sfx_cue_passes_assembly_fails_validation():
    # assembly doesn't own the cue list — validate_manifest catches it
    from vulcan.validate import validate_manifest
    out = b_out()
    out["beats"][0]["sfx"][0]["cue"] = "epic_boom_99"
    m = assemble(out)
    errs = validate_manifest(m)
    assert any("E_SFX_UNKNOWN" in e for e in errs)

def test_asset_dedup_by_label():
    out = b_out()
    out["beats"][1]["assets"] = [{"label": "iphone", "type": "photo_cutout", "role": "hero",
                                  "queries": ["iphone 15"], "enter_word": 6}]
    m = assemble(out)
    assert len(m["assets"]) == 1  # same (type,label) → one asset id

def test_full_manifest_validates():
    from vulcan.validate import validate_manifest
    m = assemble()
    assert validate_manifest(m) == []


# ---------- patches ----------

def test_patch_set_treatment_and_camera():
    m = assemble()
    notes = apply_patches(m, [
        {"op": "set_treatment", "beat": "b02", "treatment": "kinetic_type"},
        {"op": "set_camera", "beat": "b02", "camera": "drift"},
    ], WORDS)
    assert notes == []
    assert m["beats"][1]["treatment"] == "kinetic_type"
    assert m["beats"][1]["camera"] == "drift"

def test_patch_unknown_beat_rejected_not_fatal():
    m = assemble()
    notes = apply_patches(m, [{"op": "set_camera", "beat": "b99", "camera": "drift"}], WORDS)
    assert len(notes) == 1

def test_patch_drop_asset_removes_orphan():
    m = assemble()
    notes = apply_patches(m, [{"op": "drop_asset", "beat": "b01", "label": "iphone"}], WORDS)
    assert notes == []
    assert m["beats"][0]["assets"] == []
    assert m["assets"] == []

# ---------- lenient (final-attempt) assembly ----------

def test_lenient_coerces_all_taste_mistakes():
    from vulcan.validate import validate_manifest
    out = b_out()
    out["beats"][0]["sfx"][0]["cue"] = "epic_boom_99"          # unknown cue → dropped
    out["beats"][0]["emphasis_words"] = ["Apple", "Bitcoin"]   # unspoken word → dropped
    out["beats"][1]["payload"] = None                          # stat_slam w/o payload → downgrade
    out["beats"][1]["camera"] = "dolly_zoom"                   # bad camera → static
    notes = []
    m = assemble_manifest("v_test_len1", "mastered.wav", DUR, SKEL, WORDS, out,
                          lenient=True, notes=notes)
    assert validate_manifest(m) == []
    assert m["beats"][0]["sfx"] == []
    assert m["beats"][0]["text_overlay"]["emphasis_words"] == ["Apple"]
    assert m["beats"][1]["treatment"] == "kinetic_type"
    assert m["beats"][1]["camera"] == "static"
    assert len(notes) >= 4

def test_strict_still_rejects_same_mistakes():
    out = b_out()
    out["beats"][1]["camera"] = "dolly_zoom"
    with pytest.raises(ValueError, match="unknown camera"):
        assemble(out)

def test_lenient_drops_quote_with_empty_attribution_and_downgrades():
    # the exact failure that killed the 150s run
    from vulcan.validate import validate_manifest
    out = b_out()
    out["beats"][1]["treatment"] = "quote_card"
    out["beats"][1]["overlay_mode"] = "karaoke"
    out["beats"][1]["payload"] = {"quote": {"text": "some quote", "attribution": ""}}
    notes = []
    m = assemble_manifest("v_test_len2", "mastered.wav", DUR, SKEL, WORDS, out,
                          lenient=True, notes=notes)
    assert validate_manifest(m) == []
    assert m["beats"][1]["treatment"] == "kinetic_type"

def test_apostrophe_variants_match():
    # ASR emits U+2019, models type ASCII — both must normalize identically
    from vulcan.validate import _norm_word
    assert _norm_word("Don’t") == _norm_word("Don't") == "dont"


def test_patch_set_asset_queries_resets_status():
    m = assemble()
    m["assets"][0]["status"] = "validated"
    notes = apply_patches(m, [{"op": "set_asset_queries", "beat": "b01", "label": "iphone",
                               "queries": ["iphone 16 pro", "iphone 16", "apple iphone"]}], WORDS)
    assert notes == []
    assert m["assets"][0]["status"] == "pending"
    assert m["assets"][0]["queries"][0] == "iphone 16 pro"
