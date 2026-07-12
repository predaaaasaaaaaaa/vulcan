"""Director passes A–D. MiniMax picks from menus and word indices; this module
converts to the manifest deterministically, validates, and retries with the
validator errors injected. The LLM never emits a millisecond.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from .. import config
from ..beats import (beat_length_problems, clamp_asset_enter, cuts_to_beats,
                     repair_cuts, silence_gaps)
from ..validate import load_sfx_cues, validate_manifest
from .client import DirectorError, chat, extract_json

log = logging.getLogger("vulcan.director")

PROMPTS = Path(__file__).parent / "prompts"

TREATMENTS = {"kinetic_type", "cutout_pop", "stat_slam", "list_stack", "tweet_card",
              "screenshot_zoom", "logo_versus", "emoji_burst", "quote_card"}
ASSET_TYPES = {"photo_cutout", "3d_icon", "flat_icon", "logo", "emoji", "screenshot"}
ROLES = {"hero", "secondary", "left", "right"}
CAMERAS = {"static", "punch_in", "drift"}
TRANSITIONS = {"hard_cut", "whip", "flash"}


def _prompt(name: str, **kw) -> str:
    tpl = (PROMPTS / f"{name}.md").read_text()
    for k, v in kw.items():
        tpl = tpl.replace("{" + k + "}", str(v))
    return tpl


def _retries() -> int:
    return config.get("director.max_retries_per_pass", 3)


# ------------------------------------------------------------------ PASS A

def _word_list_for_prompt(words: list[dict]) -> str:
    gaps = {g["after_word"]: g["gap_ms"] for g in silence_gaps(words)}
    parts = []
    for i, w in enumerate(words):
        parts.append(f"{i}:{w['w']}[{w['s']}-{w['e']}]")
        if i in gaps:
            parts.append(f"⏸{gaps[i]}ms")
    return " ".join(parts)


def pass_a(words: list[dict], duration_ms: int) -> list[dict]:
    """→ beat skeletons [{start_ms,end_ms,first_word,last_word}]. Raises DirectorError."""
    feedback = ""
    for attempt in range(1 + _retries()):
        text = chat(
            system="You cut speech into visual beats. Output strict JSON only.",
            user=_prompt("pass_a",
                         n_words=len(words), duration_ms=duration_ms,
                         word_list=_word_list_for_prompt(words), feedback=feedback),
        )
        try:
            cuts = extract_json(text).get("cuts")
            if not isinstance(cuts, list) or not all(isinstance(c, int) for c in cuts):
                raise ValueError("output must be {\"cuts\": [int, ...]}")
            # MiniMax picks idea boundaries; math enforces beat-length law.
            # (A weak reasoner cannot reliably satisfy numeric constraints —
            # deterministic repair beats re-asking, see BUILDLOG Phase 5.)
            repaired = repair_cuts(words, cuts, duration_ms)
            skeleton = cuts_to_beats(words, repaired, duration_ms)
            problems = beat_length_problems(skeleton)
            if problems:
                raise ValueError("; ".join(problems[:6]))
            if repaired != sorted(set(c for c in cuts if isinstance(c, int))):
                log.info("pass A: repaired cuts %s → %s", cuts, repaired)
            log.info("pass A ok: %d beats (attempt %d)", len(skeleton), attempt + 1)
            return skeleton
        except (ValueError, DirectorError) as e:
            log.warning("pass A attempt %d rejected: %s", attempt + 1, e)
            feedback = (
                f"\nYOUR PREVIOUS ANSWER WAS REJECTED: {e}\n"
                "Fix exactly these problems and output the corrected JSON.\n"
            )
    raise DirectorError(f"pass A failed after {1 + _retries()} attempts: {feedback[:400]}")


# ------------------------------------------------------------------ PASS B

def _beat_table(skeleton: list[dict], words: list[dict]) -> str:
    rows = []
    for i, b in enumerate(skeleton):
        ws = " ".join(f"{j}:{words[j]['w']}" for j in range(b["first_word"], b["last_word"] + 1))
        rows.append(f"b{i+1:02d} [words {b['first_word']}-{b['last_word']}, "
                    f"{(b['end_ms']-b['start_ms'])/1000:.1f}s]: {ws}")
    return "\n".join(rows)


def _norm(w: str) -> str:
    return re.sub(r"[^\w'-]", "", w, flags=re.UNICODE).lower()


def assemble_manifest(video_id: str, audio_path: str, duration_ms: int,
                      skeleton: list[dict], words: list[dict], b_out: dict) -> dict:
    """Deterministic Pass-B-output → manifest conversion. Raises ValueError with
    injectable messages on any reference the model got wrong."""
    beats_out = {b.get("id"): b for b in b_out.get("beats", [])}
    expected_ids = [f"b{i+1:02d}" for i in range(len(skeleton))]
    missing = [i for i in expected_ids if i not in beats_out]
    if missing:
        raise ValueError(f"missing beats in output: {missing}")

    assets_registry: dict[tuple, dict] = {}
    manifest_beats = []

    for i, sk in enumerate(skeleton):
        bid = expected_ids[i]
        bo = beats_out[bid]
        blen = sk["end_ms"] - sk["start_ms"]
        wrange = range(sk["first_word"], sk["last_word"] + 1)
        beat_words = [{"w": words[j]["w"], "s": words[j]["s"], "e": words[j]["e"]} for j in wrange]

        def word_anchor(wi, what):
            if not isinstance(wi, int) or wi not in wrange:
                raise ValueError(
                    f"{bid}: {what} at_word/enter_word {wi} is not a word index of this beat "
                    f"(valid: {sk['first_word']}-{sk['last_word']})")
            return words[wi]["s"] - sk["start_ms"]

        treatment = bo.get("treatment")
        if treatment not in TREATMENTS:
            raise ValueError(f"{bid}: unknown treatment {treatment!r}")
        camera = bo.get("camera")
        if camera not in CAMERAS:
            raise ValueError(f"{bid}: unknown camera {camera!r}")
        transition = bo.get("transition_out")
        if transition not in TRANSITIONS:
            raise ValueError(f"{bid}: unknown transition_out {transition!r}")

        mode = bo.get("overlay_mode", "karaoke")
        overlay = {"mode": mode}
        if bo.get("emphasis_words"):
            overlay["emphasis_words"] = [str(w) for w in bo["emphasis_words"]][:4]
        if mode == "headline":
            overlay["headline_text"] = str(bo.get("headline_text") or "")[:60]

        refs = []
        for a in bo.get("assets") or []:
            atype, role = a.get("type"), a.get("role")
            if atype not in ASSET_TYPES:
                raise ValueError(f"{bid}: unknown asset type {atype!r}")
            if role not in ROLES:
                raise ValueError(f"{bid}: unknown asset role {role!r}")
            queries = [str(q)[:80] for q in (a.get("queries") or []) if str(q).strip()][:3]
            if not queries:
                raise ValueError(f"{bid}: asset '{a.get('label')}' has no queries")
            key = (atype, _norm(str(a.get("label") or queries[0])))
            if key not in assets_registry:
                assets_registry[key] = {
                    "asset_id": f"a{len(assets_registry)+1:02d}",
                    "type": atype, "queries": queries,
                    "path": None, "status": "pending", "score": None,
                }
            enter = clamp_asset_enter(word_anchor(a.get("enter_word"), "asset"), blen)
            refs.append({"asset_id": assets_registry[key]["asset_id"], "role": role,
                         "enter_ms": enter, "exit_ms": blen})

        sfx = []
        for s in (bo.get("sfx") or [])[:2]:
            at = word_anchor(s.get("at_word"), "sfx")
            sfx.append({"cue": str(s.get("cue")), "at_ms": clamp_asset_enter(at, blen, 0.92)})

        payload = bo.get("payload") or None
        if payload:
            payload = {k: v for k, v in payload.items()
                       if k in ("stat_text", "items", "tweet", "quote") and v}
            if "items" in payload:
                items = []
                for it in payload["items"][:4]:
                    at = word_anchor(it.get("at_word"), "list item") if "at_word" in it else int(it.get("at_ms", 0))
                    items.append({"text": str(it.get("text", ""))[:28], "at_ms": max(min(at, blen), 0)})
                items.sort(key=lambda x: x["at_ms"])
                payload["items"] = items
            payload = payload or None

        beat = {
            "id": bid, "start_ms": sk["start_ms"], "end_ms": sk["end_ms"],
            "words": beat_words, "treatment": treatment, "text_overlay": overlay,
            "assets": refs, "sfx": sfx, "camera": camera, "transition_out": transition,
        }
        if payload:
            beat["payload"] = payload
        manifest_beats.append(beat)

    return {
        "video_id": video_id, "fps": 30, "aspect": "9:16",
        "audio": {"path": audio_path, "duration_ms": duration_ms},
        "beats": manifest_beats,
        "assets": list(assets_registry.values()),
    }


def pass_b(video_id: str, audio_path: str, duration_ms: int,
           skeleton: list[dict], words: list[dict], language: str) -> dict:
    sfx_cues = load_sfx_cues()
    feedback = ""
    for attempt in range(1 + _retries()):
        text = chat(
            system="You are an art director. Output strict JSON only.",
            user=_prompt("pass_b", language=language,
                         beat_table=_beat_table(skeleton, words), feedback=feedback),
        )
        try:
            manifest = assemble_manifest(video_id, audio_path, duration_ms,
                                         skeleton, words, extract_json(text))
            errs = validate_manifest(manifest, sfx_cues=sfx_cues)
            if errs:
                raise ValueError("; ".join(errs[:8]))
            log.info("pass B ok: %d beats, %d assets (attempt %d)",
                     len(manifest["beats"]), len(manifest["assets"]), attempt + 1)
            return manifest
        except (ValueError, DirectorError) as e:
            log.warning("pass B attempt %d rejected: %s", attempt + 1, str(e)[:300])
            feedback = (
                f"\nYOUR PREVIOUS ANSWER WAS REJECTED by the validator:\n{e}\n"
                "Fix exactly these problems (keep everything else identical) and output the corrected JSON.\n"
            )
    raise DirectorError(f"pass B failed after {1 + _retries()} attempts")


# ------------------------------------------------------------------ PASS C

def _summary(manifest: dict) -> str:
    rows = []
    for b in manifest["beats"]:
        phrase = " ".join(w["w"] for w in b["words"])
        assets = ", ".join(
            f"{r['role']} {next(a['type'] for a in manifest['assets'] if a['asset_id']==r['asset_id'])} "
            f"q={next(a['queries'][0] for a in manifest['assets'] if a['asset_id']==r['asset_id'])!r}"
            for r in b["assets"]) or "none"
        sfx = ", ".join(f"{s['cue']}@{s['at_ms']}ms" for s in b["sfx"]) or "none"
        extra = ""
        if b.get("payload"):
            extra = f" payload={json.dumps(b['payload'], ensure_ascii=False)[:100]}"
        rows.append(f"{b['id']} {b['treatment']}/{b['text_overlay']['mode']} [{phrase}] "
                    f"emph={b['text_overlay'].get('emphasis_words', [])} assets: [{assets}] "
                    f"sfx: [{sfx}] cam={b['camera']} out={b['transition_out']}{extra}")
    return "\n".join(rows)


def apply_patches(manifest: dict, patches: list[dict], words: list[dict]) -> list[str]:
    """Apply whitelisted patch ops in place; returns list of rejected-patch notes."""
    notes = []
    by_id = {b["id"]: b for b in manifest["beats"]}

    def find_asset(label: str):
        """Labels aren't stored in the manifest (schema is closed) — match the
        normalized label against any query, exact first then substring."""
        want = _norm(label)
        if not want:
            return None
        for a in manifest["assets"]:
            if any(_norm(q) == want for q in a["queries"]):
                return a
        for a in manifest["assets"]:
            if any(want in _norm(q) or _norm(q) in want for q in a["queries"]):
                return a
        return None
    for p in patches[:12]:
        try:
            op, bid = p.get("op"), p.get("beat")
            b = by_id.get(bid)
            if b is None:
                raise ValueError(f"unknown beat {bid}")
            if op == "set_treatment":
                if p["treatment"] not in TREATMENTS:
                    raise ValueError("bad treatment")
                b["treatment"] = p["treatment"]
            elif op == "set_overlay":
                mode = p.get("mode", "karaoke")
                b["text_overlay"]["mode"] = mode
                if mode == "headline":
                    b["text_overlay"]["headline_text"] = str(p.get("headline_text") or "")[:60]
                else:
                    b["text_overlay"].pop("headline_text", None)
            elif op == "set_emphasis":
                b["text_overlay"]["emphasis_words"] = [str(w) for w in p["emphasis_words"]][:4]
            elif op == "set_camera":
                if p["camera"] not in CAMERAS:
                    raise ValueError("bad camera")
                b["camera"] = p["camera"]
            elif op == "set_transition":
                if p["transition_out"] not in TRANSITIONS:
                    raise ValueError("bad transition")
                b["transition_out"] = p["transition_out"]
            elif op == "set_sfx":
                blen = b["end_ms"] - b["start_ms"]
                new = []
                for s in (p.get("sfx") or [])[:2]:
                    if "at_word" in s:
                        wi = s["at_word"]
                        w = next((w for w in b["words"] if words[wi]["s"] == w["s"]), None) if 0 <= wi < len(words) else None
                        if w is None:
                            raise ValueError(f"sfx at_word {wi} not in beat")
                        at = w["s"] - b["start_ms"]
                    else:
                        at = int(s.get("at_ms", 0))
                    new.append({"cue": str(s["cue"]), "at_ms": max(min(at, blen), 0)})
                b["sfx"] = new
            elif op == "set_asset_queries":
                a = find_asset(str(p.get("label", "")))
                if a is None:
                    # fall back: single asset on that beat
                    refs = b["assets"]
                    if len(refs) != 1:
                        raise ValueError(f"cannot resolve asset label {p.get('label')!r}")
                    a = next(x for x in manifest["assets"] if x["asset_id"] == refs[0]["asset_id"])
                a["queries"] = [str(q)[:80] for q in p["queries"]][:3]
                a["status"], a["path"], a["score"] = "pending", None, None
            elif op == "drop_asset":
                a = find_asset(str(p.get("label", "")))
                if a is None:
                    raise ValueError(f"unknown asset label {p.get('label')!r}")
                b["assets"] = [r for r in b["assets"] if r["asset_id"] != a["asset_id"]]
                if not any(r["asset_id"] == a["asset_id"] for bb in manifest["beats"] for r in bb["assets"]):
                    manifest["assets"] = [x for x in manifest["assets"] if x["asset_id"] != a["asset_id"]]
            elif op == "set_payload":
                b["payload"] = p.get("payload") or {}
            else:
                raise ValueError(f"unknown op {op!r}")
        except (KeyError, ValueError, StopIteration) as e:
            notes.append(f"patch rejected ({p.get('op')}/{p.get('beat')}): {e}")
    return notes


def pass_c(manifest: dict, words: list[dict]) -> dict:
    sfx_cues = load_sfx_cues()
    text = chat(
        system="You review video manifests. Output strict JSON only.",
        user=_prompt("pass_c", summary=_summary(manifest), feedback=""),
    )
    try:
        patches = extract_json(text).get("patches", [])
    except DirectorError as e:
        log.warning("pass C unparseable — skipping review: %s", e)
        return manifest
    if not patches:
        log.info("pass C: no patches")
        return manifest
    snapshot = json.loads(json.dumps(manifest))
    notes = apply_patches(manifest, patches, words)
    errs = validate_manifest(manifest, sfx_cues=sfx_cues)
    if errs:
        log.warning("pass C patches broke validation (%s) — reverting", errs[:3])
        return snapshot
    log.info("pass C: applied %d patches (%d rejected)", len(patches) - len(notes), len(notes))
    return manifest


# ------------------------------------------------------------------ PASS D

def pass_d(transcript: str) -> dict:
    feedback = ""
    for attempt in range(1 + _retries()):
        text = chat(
            system="You write social post kits. Output strict JSON only.",
            user=_prompt("pass_d", transcript=transcript[:4000], feedback=feedback),
        )
        try:
            kit = extract_json(text)
            hook = str(kit.get("hook", ""))[:120]
            caption = str(kit.get("caption", ""))[:2200]
            tags = [str(t) for t in kit.get("hashtags", [])]
            tags = [t if t.startswith("#") else f"#{t}" for t in tags]
            tags = [re.sub(r"[^#\w]", "", t)[:31] for t in tags if len(t) > 2][:5]
            if not hook or not caption or len(tags) != 5:
                raise ValueError("need hook, caption and exactly 5 hashtags")
            return {"hook": hook, "caption": caption, "hashtags": tags}
        except (ValueError, DirectorError) as e:
            feedback = f"\nYOUR PREVIOUS ANSWER WAS REJECTED: {e}\nOutput corrected JSON.\n"
    raise DirectorError("pass D failed")


# ------------------------------------------------------------------ full chain

def direct(video_id: str, words_data: dict, audio_path: str = "mastered.wav") -> dict:
    """words.json content → validated manifest (assets still pending) + post_kit."""
    words, duration = words_data["words"], words_data["duration_ms"]
    skeleton = pass_a(words, duration)
    manifest = pass_b(video_id, audio_path, duration, skeleton, words,
                      language=words_data.get("language", "en"))
    manifest = pass_c(manifest, words)
    manifest["post_kit"] = pass_d(words_data.get("text", ""))
    errs = validate_manifest(manifest)
    if errs:
        raise DirectorError(f"final manifest invalid after pass C/D: {errs[:5]}")
    return manifest
