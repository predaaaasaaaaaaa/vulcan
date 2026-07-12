"""Beat boundary math — deterministic, word-edge snapped.

The Director (Pass A) returns CUT POINTS as word indices ("cut after word i").
This module converts them to millisecond boundaries. MiniMax never emits a
millisecond value, so gaps and overlaps are structurally impossible:

  boundary(cut after word i) = midpoint of the silence between word i and
  word i+1 (or word i's end if they touch). First beat starts at 0, last
  beat ends at duration_ms.
"""

from __future__ import annotations

MIN_BEAT_MS = 1200
MAX_BEAT_MS = 5000


def boundary_ms(words: list[dict], cut_after: int) -> int:
    """Millisecond boundary for a cut after words[cut_after]."""
    w = words[cut_after]
    if cut_after + 1 >= len(words):
        raise ValueError("cut after final word is not a cut")
    nxt = words[cut_after + 1]
    gap = nxt["s"] - w["e"]
    if gap <= 0:
        return w["e"]
    return w["e"] + gap // 2


def cuts_to_beats(words: list[dict], cut_indices: list[int], duration_ms: int) -> list[dict]:
    """cut indices → tiled beat skeletons [{start_ms, end_ms, word_range}] .

    Raises ValueError with a Director-injectable message when the cut set is
    unusable (out of range, duplicates, not ascending).
    """
    n = len(words)
    if any(c < 0 or c >= n - 1 for c in cut_indices):
        raise ValueError(f"cut index out of range: valid range is 0..{n - 2} (cut AFTER that word)")
    if sorted(set(cut_indices)) != cut_indices:
        raise ValueError("cut indices must be strictly ascending with no duplicates")

    bounds = [0] + [boundary_ms(words, c) for c in cut_indices] + [duration_ms]
    word_starts = [0] + [c + 1 for c in cut_indices]
    word_ends = [c for c in cut_indices] + [n - 1]

    beats = []
    for i in range(len(bounds) - 1):
        beats.append({
            "start_ms": bounds[i],
            "end_ms": bounds[i + 1],
            "first_word": word_starts[i],
            "last_word": word_ends[i],
        })
    return beats


def beat_length_problems(beats: list[dict], min_ms: int = MIN_BEAT_MS, max_ms: int = MAX_BEAT_MS) -> list[str]:
    """Human-readable length violations for retry injection."""
    problems = []
    for i, b in enumerate(beats):
        length = b["end_ms"] - b["start_ms"]
        if length < min_ms:
            problems.append(
                f"beat {i + 1} (words {b['first_word']}-{b['last_word']}) is {length}ms — too short, "
                f"merge it with a neighbor (min {min_ms}ms)"
            )
        elif length > max_ms:
            problems.append(
                f"beat {i + 1} (words {b['first_word']}-{b['last_word']}) is {length}ms — too long, "
                f"add a cut between words {b['first_word']} and {b['last_word']} (max {max_ms}ms)"
            )
    return problems


def silence_gaps(words: list[dict], min_gap_ms: int = 350) -> list[dict]:
    """Natural pause candidates, precomputed for the Pass A prompt."""
    gaps = []
    for i in range(len(words) - 1):
        gap = words[i + 1]["s"] - words[i]["e"]
        if gap >= min_gap_ms:
            gaps.append({"after_word": i, "gap_ms": gap})
    return gaps
