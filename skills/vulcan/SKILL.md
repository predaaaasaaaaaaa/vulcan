---
name: vulcan
description: "Forge a voice note into a publish-ready vertical video (1080×1920, kinetic captions, cutouts, SFX, frame-synced to the voice) and deliver it back on Telegram with a post kit. Use when the user sends a voice note asking for a video/reel/short, or says 'forge this', 'make this a video', 'vulcan'."
version: 1.0.0
metadata:
  hermes:
    tags: [video, content, telegram, voice, reels, shorts]
    category: media
    requires_toolsets: [terminal]
---

# VULCAN — voice note → vertical video

You (Hermes) are the RELAY, not the director. ALL creative and technical logic
lives in one CLI. You: confirm intent → invoke → stream status → deliver files.
Never edit VULCAN's files, never craft manifests yourself, never retry more
than once.

## When to trigger
- A voice note arrives AND (its transcript or caption asks for a video/reel/short/TikTok, OR the user has said to forge the next note).
- The user explicitly writes "vulcan", "forge this", "fais-en une vidéo", etc. about a voice note they just sent.
- DEFAULT (auto_mode=false): ask exactly once — "🔥 Forge this into a video? (y/n)" — and proceed only on yes.

## How to run it
The voice note is already cached on disk by the gateway. You do NOT know its
path — the CLI resolves the newest one itself:

```bash
cd /home/preda/vulcan && .venv/bin/python -m vulcan.cli run --latest
```

- Use your terminal/process tool in BACKGROUND mode (a run takes 2–8 minutes —
  longer than the terminal timeout; poll the process output).
- Testing with an explicit file: `.venv/bin/python -m vulcan.cli run /path/to/voice.ogg`
- Environment check: `.venv/bin/python -m vulcan.cli doctor`

## While it runs — status relay
The CLI prints lines like `STATUS 3/7 director — 86 words → beats + treatments`.
Relay a SHORT progress message to the user at stages 1, 3, 5 and 7 only
(e.g. "🎬 Cutting your audio into beats…", "🔨 Rendering now — ~2 min").
Do not spam every line.

## On success — delivery
The CLI ends with:
```
DELIVER MEDIA:/home/preda/vulcan/runs/<id>/out/final.mp4
DELIVER_SHEET MEDIA:/home/preda/vulcan/runs/<id>/qc/contact_sheet.png
POST_KIT_START
🪝 <hook>
<caption>
#tags…
POST_KIT_END
DONE <id> <path>
```
Then you send, in this order, via send_message:
1. The video: a message containing `MEDIA:/home/preda/vulcan/runs/<id>/out/final.mp4`
2. The post kit text (between POST_KIT_START/END) as a normal message.
3. Only if the user asks for details: the contact sheet image.

## On failure — playbook (exact user-facing messages)
The CLI prints `ERROR …` and exits non-zero. Report the matching message,
attach nothing, and do NOT retry more than ONCE (a second identical failure =
stop and surface):

| failing stage (from last STATUS line) | tell the user |
|---|---|
| 1/7 ingest | "⚠️ I couldn't read that voice note — could you send it again?" |
| 2/7 asr | "⚠️ I couldn't transcribe the audio clearly (too noisy or too short). A cleaner take fixes it." |
| 3/7 director | "⚠️ The director brain hiccuped while planning your video. I'll retry once — if it fails again, try re-sending in a few minutes." (this one IS worth one retry) |
| 4/7 assets | "⚠️ I couldn't find good-enough visuals for what you mentioned. It'll still work — re-run, or name things slightly differently." |
| 5/7 render | "⚠️ The render crashed on my side. Retrying once…" (retry once) |
| 6/7 qc | "⚠️ The video came out below quality bar and auto-repair didn't save it. I kept the artifacts for debugging." |
| 7/7 deliver | Send the file path in a plain message: "The video is ready at `runs/<id>/out/final.mp4` but Telegram delivery failed — it may be over 50MB." |
| `ERROR no voice note newer than` | "⚠️ I couldn't find a recent voice note — send it again and say 'forge this'." |

## Hard rules
- ONE run at a time. If a run is in progress, tell the user instead of starting another.
- Never modify anything under /home/preda/vulcan except by running the CLI.
- Never send intermediate artifacts unless asked.
- The run directory `runs/<id>/` is the audit trail — reference it when reporting failures.
