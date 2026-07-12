# RECON — VULCAN Phase 0
Date: 2026-07-12. All findings verified by direct inspection on this machine.

## 1. Hermes map

| Item | Finding |
|---|---|
| Install | `~/.hermes/` (data) + `~/.hermes/hermes-agent/` (framework checkout, Nous Research hermes-agent) |
| Runtime | Gateway live: pid 2117, `venv/bin/python -m hermes_cli.main gateway run`, venv at `~/.hermes/hermes-agent/venv` |
| Model | `config.yaml` → `model.default: MiniMax-M3`, `provider: minimax`, `base_url: https://api.minimax.io/anthropic` (**Anthropic-compatible API**) |
| Key | `MINIMAX_API_KEY` in `~/.hermes/.env` (non-empty, verified). VULCAN reads it from there at runtime — never copied anywhere. |
| Fallback | xai-oauth / grok-4.3 configured as Hermes fallback (VULCAN will NOT use it — MiniMax only per doctrine) |

### Voice note inbound flow (traced through code)
1. Telegram plugin `hermes-agent/plugins/platforms/telegram/adapter.py:6663` — `msg.voice` → `download_as_bytearray()` → `cache_audio_from_bytes(bytes, ext=".ogg")`.
2. `gateway/platforms/base.py:813` — writes to `~/.hermes/cache/audio/audio_<12hex>.ogg` (legacy `~/.hermes/audio_cache/` also exists with older files).
3. `gateway/run.py:9153` — STT is ON (`stt.enabled: true`, provider local, whisper base). The agent message becomes `[The user sent a voice message~ Here's what they said: "<transcript>"]` — **the file path is NOT shown to the agent when STT is on** (path only appears when STT is off). Transcript is echoed to the user as `🎙️ "..."`.
4. Real voice notes present in both cache dirs (usable as fixtures, e.g. `~/.hermes/audio_cache/audio_0dc56714e85e.ogg`, 590KB).

**Consequence for VULCAN:** MiniMax cannot know the voice path. → `vulcan run --latest` resolves the newest `.ogg` in `~/.hermes/cache/audio` (+ legacy dir) within a freshness window itself. MiniMax never types paths. Explicit `vulcan run <file>` kept for testing.

### Outbound (messages + files)
- Agent tool: `send_message` (`hermes-agent/tools/send_message_tool.py`). To send a file, the agent includes `MEDIA:<absolute_path>` in the message text; the platform delivers natively. `[[as_document]]` forces document mode.
- Telegram adapter: `.mp4` → native video; `.ogg/.opus` → voice bubble; others → document. Bot API cap 50MB (our target ≤45MB).
- `gateway.trust_recent_files: true` (600s) — recently created files are deliverable without extra allow-listing.
- Direct bot-token fallback possible (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_HOME_CHANNEL` set in `.env`) but **primary plan = Hermes send_message path** (keeps threading/permissions).

### Skills registration
- Skills live at `~/.hermes/skills/<category>/<skill>/SKILL.md` (YAML frontmatter: name, description, metadata.hermes.{tags,category,requires_toolsets}).
- Official external mechanism: `config.yaml → skills.external_dirs` (list of dirs scanned for `*/SKILL.md`), parsed in `agent/skill_utils.py:416`. **Plan: add `/home/preda/vulcan/skills` to `skills.external_dirs`** (one additive config line, no Hermes core touched) → registers `~/vulcan/skills/vulcan/SKILL.md`.
- Agent has `terminal` + `process` tools (toolset `hermes-cli`, toolsets.py:428) → it can invoke `vulcan run ...` as a shell command. Persistent shell, timeout 180s default → SKILL.md must instruct running vulcan **backgrounded/`process` tool** since renders exceed 180s.

## 2. HyperFrames autopsy
Skill at `~/.hermes/skills/creative/hyperframes/` (+ `hyperframes-audio-video`). Outputs found at `~/hermes-demo/` — **14 mp4 iterations** (draft, v2…v5, `-sm` re-encodes). Contact sheet of `hermes-final-v5.mp4` extracted and reviewed (scratchpad `hf_autopsy/hf_v5_sheet.png`).

Why the outputs weren't postable:
1. **Wrong canvas.** 1920×1080 landscape, 12.7s — not 9:16 vertical; instantly dead on Reels/TikTok.
2. **Slide-deck, not motion graphics.** Static centered title cards ("Voice Conversations", "Autonomous Coding") on an empty near-black field with seconds of nothing moving. Reads as a corporate template demo — the exact failure CLAUDE.md bans.
3. **LLM-invented timing.** The skill has the model hand-author GSAP timelines and narration tables; its own docs codify voice/visual desync ("narration naturally extends past the visual scene"). No word-level anchoring exists anywhere in the pipeline.
4. **Zero asset engine.** Only text + two thumbnail-sized icons across 13 seconds. No cutouts, no screenshots, no emoji, no density — nothing to hold the eye.
5. **Blind iteration.** 14 renders with no validators and no frame-level QC; every "fix" was the model re-guessing GSAP by feel. v1→v5 is the visible cost of having no deterministic contract.

Salvage:
- `MEDIA:<path>` delivery convention + send_message wiring (reused for VULCAN delivery).
- Hard lesson "headless Chromium cannot fetch CDNs" → VULCAN commits fonts/assets locally (already doctrine).
- The DESIGN.md hard-gate concept → maps to `tokens.ts` single style source.
- Nothing else — timing model and rendering approach are the disease, not the cure.

## 3. Hardware / runtime

| Resource | Value | Impact |
|---|---|---|
| CPU | 12 threads | Remotion concurrency & ASR fine on CPU |
| RAM | **7.1 GB total, ~3 GB avail** | Real constraint. Remotion concurrency must be tuned (not cores−1=11 blindly); run stages sequentially |
| GPU | RTX 2050 4GB, CUDA 13.2, driver 595.71.05, `llama-server` resident (734MiB) | GPU optional per doctrine → CPU-first for ASR/rembg/SigLIP; revisit only if CPU too slow |
| Disk | 255 GB free | No blocker |
| Node | v22.22.2 (+npm 10.9.7) | Remotion OK (needs ≥18) |
| Python | 3.12.3; **torch 2.8.0+cu128 already in `~/.local`** | venv with `--system-site-packages` inherits torch — saves ~2.5GB install |
| ffmpeg | 6.1.1 (+ffprobe) | OK |
| HF cache | `systran/faster-whisper-base` already downloaded | faster-whisper warm start |

## 4. Network probes (curl, HTTP status)
| Source | Status | Verdict |
|---|---|---|
| commons.wikimedia.org API | 200 | ✅ |
| upload.wikimedia.org | 200 | ✅ |
| duckduckgo.com | 200 | ✅ |
| api.iconify.design | 200 | ✅ |
| 3dicons.co | 200 | ✅ |
| **lottiefiles.com** | **403** | Bot-guard on HTML. Not a blocker: lottie is the lowest-priority asset type; will use direct CDN asset URLs or drop lottie to a curated local pack. Noted per swap rule. |
| raw.githubusercontent (iamcal/emoji-data) | 200 | ✅ emoji sheets available |
| pypi.org | 200 | ✅ |
| registry.npmjs.org (remotion) | 200 | ✅ |
| api.minimax.io | 404 on `/` (host up; real path `/anthropic` is what Hermes actively uses) | ✅ |

## 5. Decisions locked by recon
1. **Delivery:** Hermes `send_message` + `MEDIA:` (primary); direct bot token only as coded fallback path in deliver.py, off by default.
2. **Voice file resolution:** `vulcan run --latest` (newest cached ogg, ≤15 min old) because agent never sees the path.
3. **Skill registration:** `skills.external_dirs += /home/preda/vulcan/skills` (additive config).
4. **ASR:** faster-whisper first candidate (base model pre-cached, CPU int8); WhisperX benchmarked against it in Phase 2 before committing.
5. **Venv:** `~/vulcan/.venv --system-site-packages` to inherit torch cu128.
6. **RAM discipline:** stages run sequentially; Remotion concurrency benchmarked, capped below cores−1 if Chrome tabs push past ~5GB.
