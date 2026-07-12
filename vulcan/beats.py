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
    """Human-readable length violations for retry injection.

    A single-word beat over max_ms is tolerated: its overrun is pure silence
    (tiling must put inter-word silence somewhere), it cannot be cut, and the
    renderer just holds the caption. The ingest silence cap makes this rare;
    when it happens it is structurally unfixable and visually harmless.
    """
    problems = []
    for i, b in enumerate(beats):
        length = b["end_ms"] - b["start_ms"]
        single_word = b["last_word"] <= b["first_word"]
        if length < min_ms:
            problems.append(
                f"beat {i + 1} (words {b['first_word']}-{b['last_word']}) is {length}ms — too short, "
                f"merge it with a neighbor (min {min_ms}ms)"
            )
        elif length > max_ms and not single_word:
            problems.append(
                f"beat {i + 1} (words {b['first_word']}-{b['last_word']}) is {length}ms — too long, "
                f"add a cut between words {b['first_word']} and {b['last_word']} (max {max_ms}ms)"
            )
    return problems


def sanitize_cuts(cut_indices: list[int], n_words: int) -> list[int]:
    """Drop out-of-range/duplicate indices and sort — mechanical forgiveness
    for weak-reasoner slips; the idea boundaries that survive stay theirs."""
    return sorted({c for c in cut_indices if isinstance(c, int) and 0 <= c < n_words - 1})


def repair_cuts(words: list[dict], cut_indices: list[int], duration_ms: int,
                min_ms: int = MIN_BEAT_MS, max_ms: int = MAX_BEAT_MS) -> list[int]:
    """Deterministically fix beat-length violations in a cut set.

    The LLM chooses ideas; math fixes lengths. Rewritten after the 2026-07-12
    post-mortem: the previous greedy multi-cut recomputed split targets from a
    stale beat start each round, so `set.add` kept hitting existing cuts and
    the loop spun without converging. This version is provably terminating:

      Phase 1 (split): while any too-long beat exists, add exactly ONE new cut
      inside it — the candidate is scored (a) both sides ≥ min_ms first,
      (b) largest silence gap, (c) most balanced. Each iteration either adds a
      strictly new cut (bounded by word count) or marks the beat unsplittable
      (single word — bounded by beat count).

      Phase 2 (merge): each too-short beat merges into its shorter neighbor,
      removing exactly one cut per iteration (bounded by cut count). A merge
      that would re-create a too-long beat prefers the other neighbor, else
      tolerates the short beat rather than ping-ponging.

    Up to 3 rounds of (split, merge) — in practice one converges, because the
    ingest silence cap (≤0.9s pauses) + the ASR word-length ceiling (≤3s)
    make every >max beat splittable with legal sides.
    """
    cuts = sanitize_cuts(cut_indices, len(words))
    unsplittable: set[int] = set()
    tolerated_short: set[int] = set()

    for _round in range(3):
        # ---- Phase 1: split all too-long beats, one new cut at a time ----
        for _ in range(len(words) + len(cuts) + 8):
            beats = cuts_to_beats(words, cuts, duration_ms)
            target = next(
                (b for b in beats
                 if b["end_ms"] - b["start_ms"] > max_ms
                 and b["first_word"] not in unsplittable),
                None,
            )
            if target is None:
                break
            lo, hi = target["first_word"], target["last_word"]
            if hi <= lo:
                unsplittable.add(lo)  # single word — cannot cut
                continue
            candidates = []
            for i in range(lo, hi):
                b_ms = boundary_ms(words, i)
                left = b_ms - target["start_ms"]
                right = target["end_ms"] - b_ms
                gap = words[i + 1]["s"] - words[i]["e"]
                candidates.append((left >= min_ms and right >= min_ms, gap, -abs(left - right), i))
            candidates.sort(reverse=True)
            chosen = candidates[0][3]
            if chosen in cuts:  # geometry left nothing new — stop touching this beat
                unsplittable.add(lo)
                continue
            cuts = sorted(set(cuts) | {chosen})

        # ---- Phase 2: merge too-short beats, one cut removed at a time ----
        merged_any = False
        for _ in range(len(cuts) + 4):
            beats = cuts_to_beats(words, cuts, duration_ms)
            short_i = next(
                (i for i, b in enumerate(beats)
                 if b["end_ms"] - b["start_ms"] < min_ms
                 and b["first_word"] not in tolerated_short),
                None,
            )
            if short_i is None or not cuts:
                break
            blen = lambda i: beats[i]["end_ms"] - beats[i]["start_ms"]  # noqa: E731
            options = []  # (resulting_len, cut_to_drop)
            if short_i > 0:
                options.append((blen(short_i - 1) + blen(short_i), cuts[short_i - 1]))
            if short_i < len(beats) - 1:
                options.append((blen(short_i + 1) + blen(short_i), cuts[short_i]))
            legal = [o for o in options if o[0] <= max_ms]
            pick = min(legal or options)  # prefer a legal merge, else smallest overshoot
            if not legal and pick[0] > max_ms:
                # merging would re-create a long beat → tolerate the short one
                tolerated_short.add(beats[short_i]["first_word"])
                continue
            cuts = [c for c in cuts if c != pick[1]]
            merged_any = True

        beats = cuts_to_beats(words, cuts, duration_ms)
        if not beat_length_problems(beats, min_ms, max_ms) or not merged_any:
            break

    return cuts


ASSET_ENTER_MAX_FRAC = 0.55


def clamp_asset_enter(enter_ms: int, beat_len_ms: int, frac: float = ASSET_ENTER_MAX_FRAC) -> int:
    """Anticipate beat-final nouns: a hero that would enter after 55% of the
    beat enters at 55% instead, so it actually reads on screen (Phase 4 eye
    check: lemon/pearl/rooster/bread all invisible without this)."""
    return max(min(enter_ms, int(beat_len_ms * frac)), 0)


def silence_gaps(words: list[dict], min_gap_ms: int = 350) -> list[dict]:
    """Natural pause candidates, precomputed for the Pass A prompt."""
    gaps = []
    for i in range(len(words) - 1):
        gap = words[i + 1]["s"] - words[i]["e"]
        if gap >= min_gap_ms:
            gaps.append({"after_word": i, "gap_ms": gap})
    return gaps
