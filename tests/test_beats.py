"""Beat boundary math: MiniMax picks indices, we compute ms — tiling must be perfect by construction."""

import pytest

from vulcan.beats import beat_length_problems, boundary_ms, cuts_to_beats, silence_gaps

WORDS = [
    {"w": "one", "s": 100, "e": 400},
    {"w": "two", "s": 450, "e": 800},
    {"w": "three", "s": 1400, "e": 1900},   # 600ms gap before
    {"w": "four", "s": 1900, "e": 2300},
    {"w": "five", "s": 2700, "e": 3100},    # 400ms gap before
    {"w": "six", "s": 3100, "e": 3600},
]
DURATION = 4000


def test_boundary_at_midpoint_of_silence():
    assert boundary_ms(WORDS, 1) == 800 + (1400 - 800) // 2  # 1100

def test_boundary_when_words_touch():
    assert boundary_ms(WORDS, 2) == 1900

def test_cut_after_last_word_rejected():
    with pytest.raises(ValueError):
        boundary_ms(WORDS, 5)

def test_cuts_produce_perfect_tiling():
    beats = cuts_to_beats(WORDS, [1, 3], DURATION)
    assert beats[0]["start_ms"] == 0
    assert beats[-1]["end_ms"] == DURATION
    for a, b in zip(beats, beats[1:]):
        assert a["end_ms"] == b["start_ms"]
    assert [(b["first_word"], b["last_word"]) for b in beats] == [(0, 1), (2, 3), (4, 5)]

def test_no_cuts_single_beat():
    beats = cuts_to_beats(WORDS, [], DURATION)
    assert len(beats) == 1
    assert beats[0]["start_ms"] == 0 and beats[0]["end_ms"] == DURATION

def test_out_of_range_cut_raises():
    with pytest.raises(ValueError, match="out of range"):
        cuts_to_beats(WORDS, [7], DURATION)

def test_unsorted_cuts_raise():
    with pytest.raises(ValueError, match="ascending"):
        cuts_to_beats(WORDS, [3, 1], DURATION)

def test_duplicate_cuts_raise():
    with pytest.raises(ValueError, match="ascending"):
        cuts_to_beats(WORDS, [1, 1], DURATION)

def test_length_problems_reported_for_injection():
    beats = cuts_to_beats(WORDS, [0], DURATION)  # beat1 ≈ 425ms → too short
    problems = beat_length_problems(beats)
    assert any("too short" in p for p in problems)

def test_silence_gap_detection():
    gaps = silence_gaps(WORDS, min_gap_ms=350)
    assert {g["after_word"] for g in gaps} == {1, 3}
