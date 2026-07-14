"""Deterministic manifest validator — the wall between the Director and the renderer.

Every rule here is non-negotiable and mechanical. Errors are returned as strings
prefixed with a stable code (e.g. ``E_TILE_GAP``) so the Director retry loop can
inject them verbatim into the repair prompt.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator

from .paths import SCHEMA_PATH, SFX_INDEX

# Treatments that carry a visual element even without a fetched asset.
VISUAL_TREATMENTS = {"cutout_pop", "stat_slam", "list_stack", "tweet_card",
                     "screenshot_zoom", "logo_versus", "emoji_burst", "quote_card",
                     "chart_pop"}


def visual_coverage(manifest: dict) -> float:
    """Fraction of beats carrying a visual element (asset or payload card)."""
    beats = manifest["beats"]
    if not beats:
        return 0.0
    visual = sum(1 for b in beats if b["assets"] or b["treatment"] in VISUAL_TREATMENTS)
    return visual / len(beats)


# Treatments that must reference at least one asset with the given role.
_ROLE_REQUIREMENTS = {
    "cutout_pop": ("hero",),
    "screenshot_zoom": ("hero",),
    "logo_versus": ("left", "right"),
    "emoji_burst": ("hero",),
}

# Treatment → required payload key.
_PAYLOAD_REQUIREMENTS = {
    "stat_slam": "stat_text",
    "chart_pop": "chart",
    "list_stack": "items",
    "tweet_card": "tweet",
    "quote_card": "quote",
}

# Treatment → allowed asset types for its hero-ish roles (guards e.g. a photo in emoji_burst).
_HERO_TYPE_CONSTRAINTS = {
    "emoji_burst": {"emoji"},
    "screenshot_zoom": {"screenshot"},
    "logo_versus": {"logo", "photo_cutout", "flat_icon", "3d_icon"},
}

# strips ALL apostrophe variants: ASR emits U+2019 (’), models type ASCII (')
# — "Don’t" and "Don't" must normalize identically (Phase 6 150s-run bug)
_WORD_STRIP_RE = re.compile(r"[^\w-]", re.UNICODE)


def _norm_word(w: str) -> str:
    return _WORD_STRIP_RE.sub("", w).lower()


@lru_cache(maxsize=1)
def _schema_validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text())
    return Draft202012Validator(schema)


def load_sfx_cues(index_path: Path | None = None) -> set[str]:
    path = index_path or SFX_INDEX
    data = json.loads(Path(path).read_text())
    return set(data["cues"].keys())


def schema_errors(manifest: dict) -> list[str]:
    errs = []
    for e in sorted(_schema_validator().iter_errors(manifest), key=lambda e: list(e.absolute_path)):
        loc = "/".join(str(p) for p in e.absolute_path) or "<root>"
        errs.append(f"E_SCHEMA at {loc}: {e.message}")
    return errs


def validate_manifest(
    manifest: dict,
    sfx_cues: set[str] | None = None,
    for_render: bool = False,
    beat_min_ms: int = 1200,
    beat_max_ms: int = 5000,
) -> list[str]:
    """Return a list of error strings; empty list == valid.

    ``for_render=True`` additionally requires every referenced asset to be
    ``validated`` with an existing file path (the pre-render gate).
    """
    errs = schema_errors(manifest)
    if errs:
        # Structural garbage — semantic checks on it would throw, not help.
        return errs

    if sfx_cues is None:
        sfx_cues = load_sfx_cues()

    beats = manifest["beats"]
    assets = manifest["assets"]
    duration = manifest["audio"]["duration_ms"]

    # --- IDs unique ---
    beat_ids = [b["id"] for b in beats]
    for bid in sorted({b for b in beat_ids if beat_ids.count(b) > 1}):
        errs.append(f"E_DUP_ID beat id '{bid}' appears {beat_ids.count(bid)} times")
    asset_ids = [a["asset_id"] for a in assets]
    for aid in sorted({a for a in asset_ids if asset_ids.count(a) > 1}):
        errs.append(f"E_DUP_ID asset id '{aid}' appears {asset_ids.count(aid)} times")
    asset_by_id = {a["asset_id"]: a for a in assets}

    # --- Beats tile the audio exactly ---
    if beats[0]["start_ms"] != 0:
        errs.append(f"E_TILE_START first beat starts at {beats[0]['start_ms']}ms, must be 0")
    for prev, cur in zip(beats, beats[1:]):
        if prev["end_ms"] != cur["start_ms"]:
            kind = "gap" if prev["end_ms"] < cur["start_ms"] else "overlap"
            errs.append(
                f"E_TILE_{'GAP' if kind == 'gap' else 'OVERLAP'} between {prev['id']} (end {prev['end_ms']}) "
                f"and {cur['id']} (start {cur['start_ms']}): {abs(cur['start_ms'] - prev['end_ms'])}ms {kind}"
            )
    if beats[-1]["end_ms"] != duration:
        errs.append(
            f"E_TILE_END last beat ends at {beats[-1]['end_ms']}ms but audio duration is {duration}ms"
        )

    referenced: set[str] = set()

    for b in beats:
        bid = b["id"]
        blen = b["end_ms"] - b["start_ms"]

        # --- Beat length ---
        # Single-word beats may exceed max: the overrun is inter-word silence
        # the tiling had to park somewhere (unsplittable; captions just hold).
        if blen < beat_min_ms or (blen > beat_max_ms and len(b["words"]) > 1):
            errs.append(
                f"E_BEAT_LEN {bid} is {blen}ms; must be {beat_min_ms}-{beat_max_ms}ms"
            )
        if b["end_ms"] <= b["start_ms"]:
            errs.append(f"E_BEAT_LEN {bid} end_ms <= start_ms")

        # --- Words inside beat, ascending ---
        prev_s = -1
        for w in b["words"]:
            if w["s"] >= w["e"]:
                errs.append(f"E_WORD_BOUNDS {bid} word '{w['w']}' has s>=e ({w['s']}>={w['e']})")
            if w["s"] < b["start_ms"] or w["e"] > b["end_ms"]:
                errs.append(
                    f"E_WORD_BOUNDS {bid} word '{w['w']}' ({w['s']}-{w['e']}) outside beat "
                    f"({b['start_ms']}-{b['end_ms']})"
                )
            if w["s"] < prev_s:
                errs.append(f"E_WORD_BOUNDS {bid} word '{w['w']}' starts before previous word")
            prev_s = w["s"]

        # --- Asset references + windows ---
        roles_present: dict[str, list[str]] = {}
        for ref in b["assets"]:
            aid = ref["asset_id"]
            referenced.add(aid)
            if aid not in asset_by_id:
                errs.append(f"E_ASSET_MISSING {bid} references '{aid}' which is not in assets[]")
            else:
                roles_present.setdefault(ref["role"], []).append(aid)
            if ref["enter_ms"] >= ref["exit_ms"]:
                errs.append(f"E_ASSET_WINDOW {bid}/{aid} enter_ms >= exit_ms")
            if ref["exit_ms"] > blen:
                errs.append(
                    f"E_ASSET_WINDOW {bid}/{aid} exit_ms {ref['exit_ms']} exceeds beat length {blen} "
                    f"(enter/exit are relative to beat start)"
                )

        # --- Treatment role requirements ---
        for role in _ROLE_REQUIREMENTS.get(b["treatment"], ()):
            if role not in roles_present:
                errs.append(
                    f"E_ROLE_MISSING {bid} treatment '{b['treatment']}' requires an asset with role '{role}'"
                )
        type_constraint = _HERO_TYPE_CONSTRAINTS.get(b["treatment"])
        if type_constraint:
            for role in _ROLE_REQUIREMENTS.get(b["treatment"], ()):
                for aid in roles_present.get(role, []):
                    a = asset_by_id.get(aid)
                    if a and a["type"] not in type_constraint:
                        errs.append(
                            f"E_ASSET_TYPE {bid}/{aid} type '{a['type']}' not allowed for "
                            f"{b['treatment']} role '{role}' (allowed: {sorted(type_constraint)})"
                        )

        # --- Treatment payload requirements ---
        need = _PAYLOAD_REQUIREMENTS.get(b["treatment"])
        if need and need not in (b.get("payload") or {}):
            errs.append(
                f"E_PAYLOAD_MISSING {bid} treatment '{b['treatment']}' requires payload.{need}"
            )
        if b["treatment"] == "list_stack" and "items" in (b.get("payload") or {}):
            last_at = -1
            for item in b["payload"]["items"]:
                if item["at_ms"] > blen:
                    errs.append(
                        f"E_PAYLOAD_BOUNDS {bid} list item '{item['text']}' at_ms {item['at_ms']} "
                        f"exceeds beat length {blen}"
                    )
                if item["at_ms"] < last_at:
                    errs.append(f"E_PAYLOAD_BOUNDS {bid} list items must be in ascending at_ms order")
                last_at = item["at_ms"]

        # --- SFX cues exist, inside beat ---
        for s in b["sfx"]:
            if s["cue"] not in sfx_cues:
                errs.append(
                    f"E_SFX_UNKNOWN {bid} cue '{s['cue']}' not in sfx/index.json"
                )
            if s["at_ms"] > blen:
                errs.append(
                    f"E_SFX_BOUNDS {bid} cue '{s['cue']}' at_ms {s['at_ms']} exceeds beat length {blen}"
                )

        # --- Text overlay ---
        to = b["text_overlay"]
        if to["mode"] == "headline":
            if not to.get("headline_text"):
                errs.append(f"E_HEADLINE_MISSING {bid} headline mode requires headline_text")
            elif len(to["headline_text"].split()) > 6:
                errs.append(
                    f"E_HEADLINE_LEN {bid} headline_text has {len(to['headline_text'].split())} words, max 6"
                )
        beat_words = {_norm_word(w["w"]) for w in b["words"]}
        for ew in to.get("emphasis_words", []):
            if _norm_word(ew) not in beat_words:
                errs.append(
                    f"E_EMPH_NOT_IN_WORDS {bid} emphasis word '{ew}' is not one of the beat's spoken words"
                )

    # --- Orphan assets ---
    for a in assets:
        if a["asset_id"] not in referenced:
            errs.append(f"E_ASSET_ORPHAN asset '{a['asset_id']}' is not referenced by any beat")

    # --- Render gate ---
    if for_render:
        for aid in sorted(referenced):
            a = asset_by_id.get(aid)
            if a is None:
                continue  # already reported as E_ASSET_MISSING
            if a["status"] != "validated":
                errs.append(f"E_RENDER_GATE asset '{aid}' status is '{a['status']}', must be 'validated'")
            elif not a["path"] or not Path(a["path"]).exists():
                errs.append(f"E_RENDER_GATE asset '{aid}' path missing on disk: {a['path']}")

    return errs
