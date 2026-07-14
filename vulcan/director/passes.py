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
from .client import DirectorError, QuotaExhausted, chat, extract_json

log = logging.getLogger("vulcan.director")

PROMPTS = Path(__file__).parent / "prompts"

TREATMENTS = {"kinetic_type", "cutout_pop", "stat_slam", "list_stack", "tweet_card",
              "screenshot_zoom", "logo_versus", "emoji_burst", "quote_card", "chart_pop", "network_grow"}
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


def _music_index() -> dict:
    from ..paths import SFX_DIR
    try:
        return json.loads((SFX_DIR / "music" / "index.json").read_text())["beds"]
    except (OSError, KeyError, json.JSONDecodeError):
        return {}


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
        except QuotaExhausted:
            raise
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
    # no apostrophes in the normal form — ’ vs ' must not break matching
    return re.sub(r"[^\w-]", "", w, flags=re.UNICODE).lower()


_STOPWORDS = {
    "the", "a", "an", "of", "to", "and", "or", "in", "on", "for", "with", "at",
    "photo", "image", "picture", "png", "cutout", "portrait", "shot", "close",
    "up", "closeup", "view", "background", "transparent", "isolated", "hd",
    "le", "la", "les", "un", "une", "des", "de", "du", "et", "ou", "en", "sur",
}


def _literal_types_overlap(asset_label: str, queries: list[str], beat_words: list[dict]) -> bool:
    """True when the asset request references something actually SPOKEN in the
    beat. Guards rule 12 deterministically: 'large black bull portrait' on a
    beat about bankruptcy shares no token with the words → rejected. Loose
    stem match (5-char prefix) tolerates inflections (grape/grapes,
    croissance/croissante)."""
    spoken = {_norm(w["w"]) for w in beat_words}
    spoken.discard("")
    asked = set()
    for text in [asset_label, *queries]:
        for tok in re.split(r"\s+", str(text)):
            t = _norm(tok)
            if len(t) >= 3 and t not in _STOPWORDS:
                asked.add(t)
    for a in asked:
        for s in spoken:
            if a == s or (len(a) >= 5 and len(s) >= 5 and a[:5] == s[:5]):
                return True
    return False


def assemble_manifest(video_id: str, audio_path: str, duration_ms: int,
                      skeleton: list[dict], words: list[dict], b_out: dict,
                      lenient: bool = False, notes: list[str] | None = None) -> dict:
    """Deterministic Pass-B-output → manifest conversion. Raises ValueError with
    injectable messages on any reference the model got wrong.

    ``lenient=True`` (the FINAL retry) coerces taste-level mistakes to the
    nearest legal manifest instead of raising — unknown cue → cue dropped,
    unspoken emphasis word → word dropped, missing payload/role → treatment
    downgraded to kinetic_type, bad camera/transition → defaults. Structural
    problems (missing beats, unusable JSON) still raise. Doctrine: two strict
    attempts keep quality pressure on MiniMax; the lenient pass makes a legal
    render inevitable.
    """
    if notes is None:
        notes = []

    def slip(msg: str, fallback=None):
        """Raise when strict; log-and-coerce when lenient."""
        if not lenient:
            raise ValueError(msg)
        notes.append(msg)
        return fallback

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
            if isinstance(wi, int) and wi not in wrange:
                # off-by-one forgiveness: models habitually anchor "the end"
                # at last_word+1 (burned 3 strict retries on one run) — an
                # off-by-one is mechanical, not creative; clamp silently
                if wi == sk["last_word"] + 1:
                    wi = sk["last_word"]
                elif wi == sk["first_word"] - 1:
                    wi = sk["first_word"]
            if not isinstance(wi, int) or wi not in wrange:
                if lenient:
                    notes.append(f"{bid}: {what} anchor {wi!r} out of beat — snapped to beat start")
                    return 0
                raise ValueError(
                    f"{bid}: {what} at_word/enter_word {wi} is not a word index of this beat "
                    f"(valid: {sk['first_word']}-{sk['last_word']})")
            return words[wi]["s"] - sk["start_ms"]

        treatment = bo.get("treatment")
        if treatment not in TREATMENTS:
            treatment = slip(f"{bid}: unknown treatment {bo.get('treatment')!r}", "kinetic_type")
        camera = bo.get("camera")
        if camera not in CAMERAS:
            camera = slip(f"{bid}: unknown camera {bo.get('camera')!r}", "static")
        transition = bo.get("transition_out")
        if transition not in TRANSITIONS:
            transition = slip(f"{bid}: unknown transition_out {bo.get('transition_out')!r}", "hard_cut")

        beat_word_set = {_norm(w["w"]) for w in beat_words}
        mode = bo.get("overlay_mode", "karaoke")
        overlay = {"mode": mode if mode in ("karaoke", "headline") else "karaoke"}
        if bo.get("emphasis_words"):
            emph = [str(w) for w in bo["emphasis_words"]][:4]
            if lenient:
                kept = [w for w in emph if _norm(w) in beat_word_set]
                if len(kept) != len(emph):
                    notes.append(f"{bid}: dropped unspoken emphasis words "
                                 f"{[w for w in emph if _norm(w) not in beat_word_set]}")
                emph = kept
            if emph:
                overlay["emphasis_words"] = emph
        if overlay["mode"] == "headline":
            text = str(bo.get("headline_text") or "")
            if lenient and len(text.split()) > 6:
                notes.append(f"{bid}: headline truncated to 6 words")
                text = " ".join(text.split()[:6])
            overlay["headline_text"] = text[:60]

        refs = []
        for a in bo.get("assets") or []:
            atype, role = a.get("type"), a.get("role")
            if atype not in ASSET_TYPES:
                slip(f"{bid}: unknown asset type {atype!r}")
                continue
            if role not in ROLES:
                role = slip(f"{bid}: unknown asset role {a.get('role')!r}", "hero")
            queries = [str(q)[:80] for q in (a.get("queries") or []) if str(q).strip()][:3]
            if not queries:
                slip(f"{bid}: asset '{a.get('label')}' has no queries")
                continue
            # rule-12 law: literal imagery must reference something SPOKEN.
            # Symbolic types (emoji/icons) stay free — that's their job.
            if atype in ("photo_cutout", "screenshot", "logo") and not _literal_types_overlap(
                    str(a.get("label") or ""), queries, beat_words):
                slip(f"{bid}: asset '{a.get('label')}' ({atype}) references nothing spoken in this beat "
                     f"— for abstract lines use kinetic_type or emoji_burst instead (rule 12)")
                continue
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
        known_cues = load_sfx_cues()
        for s in (bo.get("sfx") or [])[:2]:
            cue = str(s.get("cue"))
            if lenient and cue not in known_cues:
                notes.append(f"{bid}: dropped unknown sfx cue {cue!r}")
                continue
            at = word_anchor(s.get("at_word"), "sfx")
            sfx.append({"cue": cue, "at_ms": clamp_asset_enter(at, blen, 0.92)})

        payload = bo.get("payload") or None
        if payload:
            payload = {k: v for k, v in payload.items()
                       if k in ("stat_text", "items", "tweet", "quote", "chart", "network") and v}
            if "items" in payload:
                items = []
                for it in payload["items"][:4]:
                    text = str(it.get("text", "")).strip()[:28]
                    if not text:
                        slip(f"{bid}: empty list item dropped")
                        continue
                    at = word_anchor(it.get("at_word"), "list item") if "at_word" in it else int(it.get("at_ms", 0))
                    items.append({"text": text, "at_ms": max(min(at, blen), 0)})
                items.sort(key=lambda x: x["at_ms"])
                if len(items) < 2:
                    slip(f"{bid}: list_stack needs ≥2 items — payload dropped")
                    payload.pop("items", None)
                else:
                    payload["items"] = items
            if lenient:
                # malformed sub-payloads sneak past assembly into schema
                # rejection (empty attribution killed the 150s run) — sanitize
                # here so the treatment-downgrade below can absorb the loss
                if "stat_text" in payload:
                    st = str(payload["stat_text"]).strip()[:12]
                    if st:
                        payload["stat_text"] = st
                    else:
                        notes.append(f"{bid}: empty stat_text dropped")
                        payload.pop("stat_text")
                if "tweet" in payload:
                    t = payload["tweet"] or {}
                    author = str(t.get("author", "")).strip()[:40]
                    text = str(t.get("text", "")).strip()[:220]
                    handle = re.sub(r"[^A-Za-z0-9_]", "", str(t.get("handle", "")))[:20]
                    if author and text:
                        payload["tweet"] = {"author": author, "handle": f"@{handle or 'anonymous'}", "text": text}
                    else:
                        notes.append(f"{bid}: malformed tweet payload dropped")
                        payload.pop("tweet")
                if "chart" in payload:
                    c = payload["chart"] or {}
                    kind = str(c.get("kind", "")).strip()
                    label = str(c.get("label", "")).strip()[:18]
                    if kind in ("bar_up", "bar_down", "line_up", "line_down") and label:
                        payload["chart"] = {"kind": kind, "label": label}
                    else:
                        notes.append(f"{bid}: malformed chart payload dropped")
                        payload.pop("chart")
                if "network" in payload:
                    nw = payload["network"] or {}
                    nlabel = str(nw.get("label", "")).strip()[:18]
                    if nlabel:
                        payload["network"] = {"label": nlabel}
                    else:
                        notes.append(f"{bid}: empty network label dropped")
                        payload.pop("network")
                if "quote" in payload:
                    q = payload["quote"] or {}
                    text = str(q.get("text", "")).strip()[:160]
                    attribution = str(q.get("attribution", "")).strip()[:40]
                    if text and attribution:
                        payload["quote"] = {"text": text, "attribution": attribution}
                    else:
                        notes.append(f"{bid}: quote payload incomplete (missing "
                                     f"{'text' if not text else 'attribution'}) — dropped")
                        payload.pop("quote")
            payload = payload or None

        if lenient:
            # downgrade treatments whose hard requirements aren't met — a plain
            # kinetic beat is always legal and still carries the captions
            from ..validate import _PAYLOAD_REQUIREMENTS, _ROLE_REQUIREMENTS
            need_payload = _PAYLOAD_REQUIREMENTS.get(treatment)
            roles_here = {r["role"] for r in refs}
            missing_role = any(r not in roles_here for r in _ROLE_REQUIREMENTS.get(treatment, ()))
            if (need_payload and need_payload not in (payload or {})) or missing_role:
                notes.append(f"{bid}: treatment {treatment} downgraded to kinetic_type "
                             f"(missing {'payload.' + need_payload if need_payload else 'role'})")
                treatment = "kinetic_type"
                payload = None
                refs = [r for r in refs if r["role"] in ("hero", "secondary")]
            if overlay["mode"] == "headline" and not overlay.get("headline_text"):
                notes.append(f"{bid}: empty headline — switched to karaoke")
                overlay = {"mode": "karaoke", **({"emphasis_words": overlay["emphasis_words"]} if overlay.get("emphasis_words") else {})}

        beat = {
            "id": bid, "start_ms": sk["start_ms"], "end_ms": sk["end_ms"],
            "words": beat_words, "treatment": treatment, "text_overlay": overlay,
            "assets": refs, "sfx": sfx, "camera": camera, "transition_out": transition,
        }
        if payload:
            beat["payload"] = payload
        manifest_beats.append(beat)

    # prune assets whose every reference was dropped (lenient guard drops /
    # treatment downgrades strip refs) — an orphan here failed a whole run
    still_referenced = {r["asset_id"] for b in manifest_beats for r in b["assets"]}
    assets_final = [a for a in assets_registry.values() if a["asset_id"] in still_referenced]
    if len(assets_final) != len(assets_registry):
        dropped_ids = [a["asset_id"] for a in assets_registry.values()
                       if a["asset_id"] not in still_referenced]
        notes.append(f"pruned orphaned assets after ref drops: {dropped_ids}")

    # music mood: MiniMax picks from the menu; invalid/missing coerces to a
    # safe default (music must never block a video)
    mood = str(b_out.get("music_mood") or "").strip().lower()
    music_index = _music_index()
    if mood == "none":
        music = {"mood": "none", "file": None}
    elif mood in music_index:
        music = {"mood": mood, "file": music_index[mood]["file"]}
    else:
        if mood:
            notes.append(f"unknown music_mood {mood!r} — defaulting to chill")
        music = {"mood": "chill", "file": music_index.get("chill", {}).get("file")}

    return {
        "video_id": video_id, "fps": 30, "aspect": "9:16",
        "audio": {"path": audio_path, "duration_ms": duration_ms},
        "beats": manifest_beats,
        "assets": assets_final,
        "music": music,
    }


from ..validate import VISUAL_TREATMENTS  # noqa: E402  (shared with the QC gate)


def richness_problems(manifest: dict, floor: float) -> list[str]:
    """The anemic-manifest guard (post-mortem 2: 27/28 bare kinetic beats
    shipped a 'black screen with captions'). A beat counts as VISUAL when it
    carries an asset or a payload treatment. Below the floor → injectable
    error naming the barest stretch so MiniMax knows exactly where to enrich."""
    beats = manifest["beats"]
    visual = [b["id"] for b in beats if b["assets"] or b["treatment"] in VISUAL_TREATMENTS]
    ratio = len(visual) / max(len(beats), 1)
    if ratio >= floor:
        return []
    bare = [b["id"] for b in beats if not (b["assets"] or b["treatment"] in VISUAL_TREATMENTS)]
    return [
        f"VISUAL RICHNESS too low: only {len(visual)}/{len(beats)} beats "
        f"({ratio:.0%}) carry a visual element (need ≥{floor:.0%}). This renders as "
        f"text-on-black. Add emoji_burst (always legal, even on abstract beats — "
        f"queries[0] MUST be the literal emoji character), quote_card, stat_slam or "
        f"cutout_pop (only for spoken concrete nouns) to these beats: "
        f"{', '.join(bare[:10])}. The hook (b01) and the closer MUST be visual."
    ]


def variety_problems(manifest: dict) -> list[str]:
    """Emoji monotony guard. Samy's taste law: emojis read as cheap in
    short-form — among visual beats emoji_burst may carry at most a QUARTER;
    real cutouts and Remotion-native graphics carry the rest."""
    beats = manifest["beats"]
    visual = [b for b in beats if b["assets"] or b["treatment"] in VISUAL_TREATMENTS]
    if len(visual) < 4:
        return []
    emoji = [b["id"] for b in visual if b["treatment"] == "emoji_burst"]
    if len(emoji) / len(visual) <= 0.25:
        return []
    return [
        f"TREATMENT MONOTONY: {len(emoji)}/{len(visual)} visual beats are emoji_burst "
        f"(max 25% — emojis read as cheap). Re-assign most of {', '.join(emoji[:6])} to: "
        f"cutout_pop (REAL photo png of any spoken noun — preferred), network_grow "
        f"(scale/systems), chart_pop (trends/costs), quote_card, stat_slam, list_stack, "
        f"screenshot_zoom."
    ]


def pass_b(video_id: str, audio_path: str, duration_ms: int,
           skeleton: list[dict], words: list[dict], language: str) -> dict:
    sfx_cues = load_sfx_cues()
    feedback = ""
    attempts = 1 + _retries()
    for attempt in range(attempts):
        lenient = attempt == attempts - 1  # final attempt: coerce, don't reject
        text = chat(
            system="You are an art director. Output strict JSON only.",
            user=_prompt("pass_b", language=language,
                         beat_table=_beat_table(skeleton, words), feedback=feedback),
        )
        try:
            notes: list[str] = []
            manifest = assemble_manifest(video_id, audio_path, duration_ms,
                                         skeleton, words, extract_json(text),
                                         lenient=lenient, notes=notes)
            for n in notes:
                # WARNING, not INFO: "attempt 4, lenient" must not read as a
                # clean pass in the forensic log (post-mortem 2, cause #4)
                log.warning("pass B lenient coercion: %s", n)
            errs = validate_manifest(manifest, sfx_cues=sfx_cues)
            if errs:
                raise ValueError("; ".join(errs[:8]))
            floor = config.get("director.richness_floor", 0.35)
            rich = richness_problems(manifest, floor)
            if rich:
                if not lenient:
                    raise ValueError(rich[0])
                # final attempt: a thin video may pass, an EMPTY one may not
                hard = richness_problems(manifest, 0.20)
                if hard:
                    raise ValueError(hard[0] + " — refusing to ship a text-only video")
                log.warning("pass B richness below target on lenient attempt: %s", rich[0][:180])
            monotony = variety_problems(manifest)
            if monotony:
                if not lenient:
                    raise ValueError(monotony[0])
                log.warning("pass B monotony accepted on lenient attempt: %s", monotony[0][:160])
            log.info("pass B ok: %d beats, %d assets (attempt %d%s)",
                     len(manifest["beats"]), len(manifest["assets"]), attempt + 1,
                     ", lenient" if lenient and notes else "")
            return manifest
        except QuotaExhausted:
            raise
        except (ValueError, DirectorError) as e:
            log.warning("pass B attempt %d rejected: %s", attempt + 1, str(e)[:300])
            feedback = (
                f"\nYOUR PREVIOUS ANSWER WAS REJECTED by the validator:\n{e}\n"
                "Fix exactly these problems (keep everything else identical) and output the corrected JSON.\n"
            )
    raise DirectorError(f"pass B failed after {attempts} attempts")


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
        except QuotaExhausted:
            raise
        except (ValueError, DirectorError) as e:
            feedback = f"\nYOUR PREVIOUS ANSWER WAS REJECTED: {e}\nOutput corrected JSON.\n"
    raise DirectorError("pass D failed")


# ------------------------------------------------------------------ full chain

def fallback_post_kit(transcript: str) -> dict:
    """Deterministic post kit when pass D exhausts retries — a plain kit must
    never cost the user a fully rendered video."""
    first = re.split(r"(?<=[.!?])\s+", transcript.strip())[0][:110] if transcript.strip() else "New video"
    return {
        "hook": first,
        "caption": "Watch till the end 👀\nWhat do you think? Drop it below 👇",
        "hashtags": ["#shorts", "#reels", "#fyp", "#viral", "#learnontiktok"],
    }


def direct(video_id: str, words_data: dict, audio_path: str = "mastered.wav") -> dict:
    """words.json content → validated manifest (assets still pending) + post_kit."""
    words, duration = words_data["words"], words_data["duration_ms"]
    skeleton = pass_a(words, duration)
    manifest = pass_b(video_id, audio_path, duration, skeleton, words,
                      language=words_data.get("language", "en"))
    manifest = pass_c(manifest, words)
    try:
        manifest["post_kit"] = pass_d(words_data.get("text", ""))
    except DirectorError as e:
        log.warning("pass D failed (%s) — using deterministic fallback kit", e)
        manifest["post_kit"] = fallback_post_kit(words_data.get("text", ""))
    errs = validate_manifest(manifest)
    if errs:
        raise DirectorError(f"final manifest invalid after pass C/D: {errs[:5]}")
    return manifest
