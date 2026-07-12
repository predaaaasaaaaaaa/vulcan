"""Adversarial tests for the manifest validator — the contract MiniMax cannot break."""

import copy
import json

import pytest

from vulcan.validate import load_sfx_cues, schema_errors, validate_manifest

SFX = load_sfx_cues()


def make_manifest() -> dict:
    """A fully valid 3-beat manifest exercising payloads, roles and karaoke."""
    return {
        "video_id": "v_test_0001",
        "fps": 30,
        "aspect": "9:16",
        "audio": {"path": "mastered.wav", "duration_ms": 9000},
        "beats": [
            {
                "id": "b01",
                "start_ms": 0,
                "end_ms": 3200,
                "words": [
                    {"w": "Nobody", "s": 120, "e": 480},
                    {"w": "talks", "s": 480, "e": 820},
                    {"w": "about", "s": 820, "e": 1100},
                    {"w": "Elon", "s": 1150, "e": 1520},
                ],
                "treatment": "cutout_pop",
                "text_overlay": {"mode": "karaoke", "emphasis_words": ["Nobody", "Elon"]},
                "assets": [
                    {"asset_id": "a01", "role": "hero", "enter_ms": 150, "exit_ms": 3200}
                ],
                "sfx": [{"cue": "whoosh_02", "at_ms": 150}],
                "camera": "punch_in",
                "transition_out": "hard_cut",
            },
            {
                "id": "b02",
                "start_ms": 3200,
                "end_ms": 6000,
                "words": [
                    {"w": "eighty", "s": 3300, "e": 3700},
                    {"w": "seven", "s": 3700, "e": 4000},
                    {"w": "percent", "s": 4000, "e": 4500},
                ],
                "treatment": "stat_slam",
                "text_overlay": {"mode": "headline", "headline_text": "87% of founders"},
                "assets": [],
                "sfx": [{"cue": "tick_01", "at_ms": 100}],
                "camera": "static",
                "transition_out": "whip",
                "payload": {"stat_text": "87%"},
            },
            {
                "id": "b03",
                "start_ms": 6000,
                "end_ms": 9000,
                "words": [
                    {"w": "so", "s": 6100, "e": 6300},
                    {"w": "remember", "s": 6300, "e": 6900},
                    {"w": "this", "s": 6900, "e": 7200},
                ],
                "treatment": "kinetic_type",
                "text_overlay": {"mode": "karaoke", "emphasis_words": ["remember"]},
                "assets": [],
                "sfx": [],
                "camera": "drift",
                "transition_out": "flash",
            },
        ],
        "assets": [
            {
                "asset_id": "a01",
                "type": "photo_cutout",
                "queries": ["elon musk pointing", "elon musk portrait", "elon musk png"],
                "path": None,
                "status": "pending",
                "score": None,
            }
        ],
    }


def errs_with(manifest, **kw):
    return validate_manifest(manifest, sfx_cues=SFX, **kw)


def assert_code(errors, code):
    assert any(e.startswith(code) for e in errors), f"expected {code} in {errors}"


# ---------- happy paths ----------

def test_valid_manifest_passes():
    assert errs_with(make_manifest()) == []

def test_valid_manifest_with_post_kit_passes():
    m = make_manifest()
    m["post_kit"] = {
        "hook": "Nobody talks about this",
        "caption": "The 87% stat that changes everything.",
        "hashtags": ["#founders", "#startup", "#tech", "#motivation", "#business"],
    }
    assert errs_with(m) == []

def test_single_beat_manifest_passes():
    m = make_manifest()
    m["beats"] = [m["beats"][2]]
    m["beats"][0].update({"id": "b01", "start_ms": 0, "end_ms": 3000})
    m["beats"][0]["words"] = [{"w": "so", "s": 100, "e": 300}, {"w": "remember", "s": 300, "e": 900}, {"w": "this", "s": 900, "e": 1200}]
    m["audio"]["duration_ms"] = 3000
    m["assets"] = []
    assert errs_with(m) == []


# ---------- tiling ----------

def test_gap_between_beats_fails():
    m = make_manifest()
    m["beats"][1]["start_ms"] = 3300  # 100ms gap
    assert_code(errs_with(m), "E_TILE_GAP")

def test_overlap_between_beats_fails():
    m = make_manifest()
    m["beats"][1]["start_ms"] = 3100  # 100ms overlap
    # words of b02 start at 3300 > 3100 so only the tiling rule must fire
    assert_code(errs_with(m), "E_TILE_OVERLAP")

def test_first_beat_not_zero_fails():
    m = make_manifest()
    m["beats"][0]["start_ms"] = 100
    assert_code(errs_with(m), "E_TILE_START")

def test_last_beat_short_of_duration_fails():
    m = make_manifest()
    m["audio"]["duration_ms"] = 9500
    assert_code(errs_with(m), "E_TILE_END")


# ---------- beat length ----------

def test_beat_too_short_fails():
    m = make_manifest()
    m["beats"][0]["end_ms"] = 1000
    m["beats"][1]["start_ms"] = 1000
    m["beats"][0]["words"] = [{"w": "Nobody", "s": 120, "e": 480}]
    m["beats"][0]["assets"][0]["exit_ms"] = 900
    assert_code(errs_with(m), "E_BEAT_LEN")

def test_beat_too_long_fails():
    m = make_manifest()
    m["beats"][2]["end_ms"] = 12000
    m["audio"]["duration_ms"] = 12000
    assert_code(errs_with(m), "E_BEAT_LEN")


# ---------- words ----------

def test_word_outside_beat_fails():
    m = make_manifest()
    m["beats"][0]["words"][0]["s"] = 0
    m["beats"][0]["words"][0]["e"] = 0  # also s>=e
    errors = errs_with(m)
    assert_code(errors, "E_WORD_BOUNDS")

def test_word_after_beat_end_fails():
    m = make_manifest()
    m["beats"][0]["words"][-1]["e"] = 3500
    assert_code(errs_with(m), "E_WORD_BOUNDS")

def test_word_order_regression_fails():
    m = make_manifest()
    m["beats"][0]["words"][2]["s"] = 300  # starts before word 1
    assert_code(errs_with(m), "E_WORD_BOUNDS")


# ---------- assets ----------

def test_hallucinated_asset_reference_fails():
    m = make_manifest()
    m["beats"][0]["assets"][0]["asset_id"] = "a99"
    errors = errs_with(m)
    assert_code(errors, "E_ASSET_MISSING")
    assert_code(errors, "E_ASSET_ORPHAN")  # a01 now unreferenced

def test_orphan_asset_fails():
    m = make_manifest()
    m["assets"].append(
        {"asset_id": "a02", "type": "logo", "queries": ["apple logo"], "path": None, "status": "pending", "score": None}
    )
    assert_code(errs_with(m), "E_ASSET_ORPHAN")

def test_asset_exit_beyond_beat_fails():
    m = make_manifest()
    m["beats"][0]["assets"][0]["exit_ms"] = 4000  # beat is 3200 long
    assert_code(errs_with(m), "E_ASSET_WINDOW")

def test_asset_enter_after_exit_fails():
    m = make_manifest()
    m["beats"][0]["assets"][0]["enter_ms"] = 3000
    m["beats"][0]["assets"][0]["exit_ms"] = 200
    assert_code(errs_with(m), "E_ASSET_WINDOW")

def test_duplicate_asset_id_fails():
    m = make_manifest()
    m["assets"].append(copy.deepcopy(m["assets"][0]))
    assert_code(errs_with(m), "E_DUP_ID")

def test_duplicate_beat_id_fails():
    m = make_manifest()
    m["beats"][1]["id"] = "b01"
    assert_code(errs_with(m), "E_DUP_ID")


# ---------- treatment requirements ----------

def test_cutout_pop_without_hero_fails():
    m = make_manifest()
    m["beats"][0]["assets"] = []
    m["assets"] = []
    assert_code(errs_with(m), "E_ROLE_MISSING")

def test_stat_slam_without_payload_fails():
    m = make_manifest()
    del m["beats"][1]["payload"]
    assert_code(errs_with(m), "E_PAYLOAD_MISSING")

def test_logo_versus_needs_left_and_right():
    m = make_manifest()
    m["beats"][0]["treatment"] = "logo_versus"
    m["beats"][0]["assets"] = [{"asset_id": "a01", "role": "left", "enter_ms": 0, "exit_ms": 3000}]
    assert_code(errs_with(m), "E_ROLE_MISSING")  # right missing

def test_emoji_burst_with_photo_hero_fails():
    m = make_manifest()
    m["beats"][0]["treatment"] = "emoji_burst"
    # a01 is photo_cutout — not allowed as emoji_burst hero
    assert_code(errs_with(m), "E_ASSET_TYPE")

def test_list_stack_item_beyond_beat_fails():
    m = make_manifest()
    m["beats"][2]["treatment"] = "list_stack"
    m["beats"][2]["payload"] = {
        "items": [
            {"text": "first thing", "at_ms": 100},
            {"text": "second thing", "at_ms": 9999},
        ]
    }
    assert_code(errs_with(m), "E_PAYLOAD_BOUNDS")

def test_list_stack_items_must_ascend():
    m = make_manifest()
    m["beats"][2]["treatment"] = "list_stack"
    m["beats"][2]["payload"] = {
        "items": [
            {"text": "first", "at_ms": 2000},
            {"text": "second", "at_ms": 100},
        ]
    }
    assert_code(errs_with(m), "E_PAYLOAD_BOUNDS")

def test_tweet_card_without_tweet_fails():
    m = make_manifest()
    m["beats"][2]["treatment"] = "tweet_card"
    assert_code(errs_with(m), "E_PAYLOAD_MISSING")


# ---------- sfx ----------

def test_hallucinated_sfx_cue_fails():
    m = make_manifest()
    m["beats"][0]["sfx"][0]["cue"] = "epic_explosion_99"
    assert_code(errs_with(m), "E_SFX_UNKNOWN")

def test_sfx_beyond_beat_fails():
    m = make_manifest()
    m["beats"][0]["sfx"][0]["at_ms"] = 5000
    assert_code(errs_with(m), "E_SFX_BOUNDS")


# ---------- text overlay ----------

def test_emphasis_word_not_spoken_fails():
    m = make_manifest()
    m["beats"][0]["text_overlay"]["emphasis_words"] = ["Bitcoin"]
    assert_code(errs_with(m), "E_EMPH_NOT_IN_WORDS")

def test_emphasis_word_case_and_punct_insensitive():
    m = make_manifest()
    m["beats"][0]["text_overlay"]["emphasis_words"] = ["nobody", "ELON"]
    assert errs_with(m) == []

def test_headline_over_six_words_fails():
    m = make_manifest()
    m["beats"][1]["text_overlay"]["headline_text"] = "this headline has way too many words in it"
    assert_code(errs_with(m), "E_HEADLINE_LEN")

def test_headline_mode_without_text_fails():
    m = make_manifest()
    del m["beats"][1]["text_overlay"]["headline_text"]
    assert_code(errs_with(m), "E_HEADLINE_MISSING")


# ---------- schema-level ----------

def test_bad_treatment_enum_fails_schema():
    m = make_manifest()
    m["beats"][0]["treatment"] = "explode_everything"
    assert_code(errs_with(m), "E_SCHEMA")

def test_bad_aspect_fails_schema():
    m = make_manifest()
    m["aspect"] = "16:9"
    assert_code(errs_with(m), "E_SCHEMA")

def test_extra_key_fails_schema():
    m = make_manifest()
    m["beats"][0]["surprise_field"] = True
    assert_code(errs_with(m), "E_SCHEMA")

def test_six_hashtags_fails_schema():
    m = make_manifest()
    m["post_kit"] = {
        "hook": "h", "caption": "c",
        "hashtags": ["#a1", "#b2", "#c3", "#d4", "#e5", "#f6"],
    }
    assert_code(errs_with(m), "E_SCHEMA")

def test_camera_enum_fails_schema():
    m = make_manifest()
    m["beats"][0]["camera"] = "dolly_zoom"
    assert_code(errs_with(m), "E_SCHEMA")


# ---------- render gate ----------

def test_render_gate_rejects_pending_asset():
    m = make_manifest()
    assert_code(errs_with(m, for_render=True), "E_RENDER_GATE")

def test_render_gate_rejects_missing_file(tmp_path):
    m = make_manifest()
    m["assets"][0]["status"] = "validated"
    m["assets"][0]["path"] = str(tmp_path / "ghost.png")
    m["assets"][0]["score"] = 0.9
    assert_code(errs_with(m, for_render=True), "E_RENDER_GATE")

def test_render_gate_passes_with_real_file(tmp_path):
    m = make_manifest()
    p = tmp_path / "a01.png"
    p.write_bytes(b"png")
    m["assets"][0]["status"] = "validated"
    m["assets"][0]["path"] = str(p)
    m["assets"][0]["score"] = 0.9
    assert errs_with(m, for_render=True) == []
