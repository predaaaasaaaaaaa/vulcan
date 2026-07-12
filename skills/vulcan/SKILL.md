---
name: vulcan
description: "Forge a voice note into a publish-ready vertical video (1080×1920, kinetic captions, cutouts, SFX, frame-synced to the voice) and deliver it back on Telegram with a post kit. Use when the user sends a voice note asking for a video/reel/short, says 'forge this', 'make this a video', 'vulcan', or asks to clean up after taking a video."
version: 1.1.0
metadata:
  hermes:
    tags: [video, content, telegram, voice, reels, shorts]
    category: media
    requires_toolsets: [terminal]
---

# VULCAN — voice note → vertical video

You (the agent) are the RELAY, not the director. ALL creative and technical
logic lives in one CLI at `/home/preda/vulcan/bin/vulcan`. Your entire job:
**confirm intent → invoke → stream status → deliver files → clean up on
approval.** Never edit VULCAN's files, never craft manifests yourself, never
retry more than once.

---

## 1. Command reference (everything you may run)

```bash
/home/preda/vulcan/bin/vulcan run --latest          # forge the newest UNCONSUMED cached voice note (the normal trigger path)
/home/preda/vulcan/bin/vulcan run /path/to/voice.ogg # forge a specific file (testing; also mp3/m4a/wav)
/home/preda/vulcan/bin/vulcan status <RUN_ID>        # which stage artifacts exist for a run
/home/preda/vulcan/bin/vulcan cleanup <RUN_ID>       # after user APPROVES the video: reclaim ~70% of the run's disk (keeps final.mp4 + receipts)
/home/preda/vulcan/bin/vulcan cleanup <RUN_ID> --purge  # user took the file & wants it gone: delete the entire run dir
/home/preda/vulcan/bin/vulcan cleanup --all          # housekeeping: clean every past run (never touches runs/golden)
/home/preda/vulcan/bin/vulcan doctor                 # environment self-check (run if anything smells broken)
```

There are no other entry points. Working dir does not matter (absolute paths
inside). One run takes **2–10 minutes** depending on note length.

## 2. When to trigger a run

- A voice note arrives AND (its transcript/caption asks for a video/reel/
  short/TikTok, OR the user previously said to forge the next note).
- The user explicitly writes "vulcan", "forge this", "fais-en une vidéo", etc.
  about a voice note they just sent.
- DEFAULT (auto_mode=false): ask exactly once — "🔥 Forge this into a video?
  (y/n)" — and proceed only on yes.
- ONE run at a time. If a run is in progress, say so instead of starting another.

You never need the voice file's path. The gateway caches incoming notes to
`~/.hermes/cache/audio/*.ogg`; `run --latest` finds the newest one **that has
not been forged before** (VULCAN keeps a consumed-notes ledger at
`runs/.consumed.json`, so re-running can never accidentally re-forge an old
message — if the user wants the SAME note redone, they must re-send it, or
you pass the explicit file path from `runs/<old_id>/audio/input.ogg`... which
only exists until cleanup).

## 3. How to invoke (exact mechanics)

The run outlives your terminal tool's timeout (180s). ALWAYS run it in the
background and poll:

```bash
# start (backgrounded, output captured):
nohup /home/preda/vulcan/bin/vulcan run --latest > /tmp/vulcan_run.log 2>&1 &

# poll every ~30s (cheap, non-blocking):
tail -5 /tmp/vulcan_run.log

# finished when the log contains a line starting with "DONE" or "ERROR".
```

If your harness has a dedicated background-process tool, prefer it over
`nohup` — same contract: start, poll the output file, react to DONE/ERROR.

## 4. Output protocol (what the CLI prints and what you do with it)

| line | example | your action |
|---|---|---|
| `RUN_ID <id>` | `RUN_ID v_20260712_105540` | remember it — needed for status/cleanup |
| `STATUS n/7 <text>` | `STATUS 5/7 render — Remotion is forging the video` | relay a SHORT progress message at stages 1, 3, 5, 7 only. Suggested voice: 1→"🎙️ Got it, mastering your audio…" · 3→"🎬 Cutting it into beats…" · 5→"🔨 Rendering — ~2 min" · 7→"📦 Packaging…" |
| `STATUS asset fallback: …` | `…b14 → kinetic_type (failed: ['a04'])` | ignore (internal resilience, not an error) |
| `DELIVER MEDIA:<path>` | `DELIVER MEDIA:/home/preda/vulcan/runs/v_…/out/final.mp4` | send a message whose text contains exactly `MEDIA:<that path>` → platform delivers the native video |
| `DELIVER_SHEET MEDIA:<path>` | contact sheet png | only send if the user asks for details/frames |
| `POST_KIT_START … POST_KIT_END` | hook line, caption, hashtags | send the text between the markers as a normal message, right after the video |
| `DONE <id> <path>` | `DONE v_… /home/…/final.mp4` | run finished clean — deliver if you haven't already |
| `ERROR <reason>` | `ERROR DirectorError: pass B failed…` | failure playbook below; at most ONE retry |

**Delivery order:** 1) video (`MEDIA:` line) → 2) post-kit text → 3) nothing
else unless asked.

## 5. Worked example (happy path)

> **User:** *(voice note, 90s)* + "make this a reel"
> **You:** "🔥 Forge this into a video? (y/n)"
> **User:** "y"
> **You:** start `run --latest` in background → "🎙️ On it — mastering your audio…"
> *(poll; on STATUS 3)* "🎬 Cutting your words into beats…"
> *(poll; on STATUS 5)* "🔨 Rendering now, ~2 minutes…"
> *(log shows DONE v_20260712_1234)*
> **You:** message 1: `MEDIA:/home/preda/vulcan/runs/v_20260712_1234/out/final.mp4`
> **You:** message 2: the post-kit text (hook / caption / hashtags)
> **User:** "perfect, taking it 🔥"
> **You:** run `cleanup v_20260712_1234` → "🧹 Cleaned up — 18MB freed, ready for the next one."

## 6. Cleanup doctrine (IMPORTANT — keeps every new run fresh)

Each run leaves ~25MB+ of intermediates (mastered wav, raw renders, QC frames,
asset candidates). Stale artifacts are noise for debugging and disk, and old
cached inputs are how old/new-message mixups happen. The ledger already
guarantees `--latest` never re-forges an old note; cleanup keeps the rest tidy:

- **When the user approves / takes the video** (says it's good, reposts it,
  says "done", reacts 👍…): run `cleanup <RUN_ID>` immediately. This keeps
  `final.mp4` + the receipts (manifest, words, QC report, log) and frees the
  rest. Validated assets are migrated to the shared cache first — cleanup
  never loses reusable cutouts.
- **When the user rejects the video and wants a retry**: do NOT clean yet —
  the artifacts are the debugging trail. Clean only after the accepted take.
- **If the user says get rid of it entirely**: `cleanup <RUN_ID> --purge`.
- **Weekly housekeeping** (or when disk complains): `cleanup --all`.
- Never delete anything under `/home/preda/vulcan` by hand — cleanup is the
  only sanctioned mutation, and `runs/golden/` is never cleaned (reference).

## 7. Failure playbook (exact user-facing messages)

The CLI prints `ERROR …` and exits non-zero. Match on the LAST `STATUS n/7`
line before the error; report the message; attach nothing; retry at most ONCE
(a second identical failure = stop and surface):

| failing stage | tell the user |
|---|---|
| 1/7 ingest | "⚠️ I couldn't read that voice note — could you send it again?" |
| 2/7 asr | "⚠️ I couldn't transcribe the audio clearly (too noisy or too short). A cleaner take fixes it." |
| 3/7 director | "⚠️ The director brain hiccuped while planning your video. Retrying once…" (this one IS worth one retry) |
| 4/7 assets | "⚠️ I couldn't find good-enough visuals for what you mentioned. Re-run, or name things slightly differently." |
| 5/7 render | "⚠️ The render crashed on my side. Retrying once…" (retry once) |
| 6/7 qc | "⚠️ The video came out below the quality bar and auto-repair didn't save it. Artifacts kept for debugging." |
| 7/7 deliver | send the path in plain text: "Video ready at `runs/<id>/out/final.mp4` but Telegram delivery failed — possibly over 50MB." |
| `ERROR no unconsumed voice note…` | "⚠️ I couldn't find a NEW voice note — the last one was already forged. Send a fresh one and say 'forge this'." |

For any failure: `runs/<RUN_ID>/pipeline.log` holds the full forensic story —
quote its last lines if the user asks what happened.

## 8. For non-Hermes agents adopting this skill

Everything above holds with two substitutions: (a) your platform's voice-note
cache dirs go in `/home/preda/vulcan/config.yaml → trigger.voice_cache_dirs`
(or skip `--latest` and pass explicit paths); (b) replace the `MEDIA:` sending
convention with however your platform sends a local video file. The
CLI protocol (§4), the cleanup doctrine (§6), and the playbook (§7) are
platform-agnostic. Full integration guide: `/home/preda/vulcan/README.md` §6.

## 9. Hard rules

- ONE run at a time; never edit files under `/home/preda/vulcan` (invoke the CLI only).
- Never send intermediate artifacts unless asked.
- Never retry more than once per failure.
- Cleanup only after approval; purge only on explicit request.
- `runs/<id>/` is the audit trail — reference it when reporting failures.
