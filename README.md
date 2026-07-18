# VULCAN — Voice-to-Video Forge

**A voice note goes in. A publish-ready vertical video comes out.**

VULCAN is a fully automated short-form content pipeline that lives inside a
[Hermes](https://github.com/NousResearch/hermes-agent) agent on a Linux machine.
You send your agent a Telegram voice note; minutes later it sends back a
1080×1920@30fps MP4 with kinetic karaoke captions, stamped PNG cutouts, 3D
emoji, synthetic tweet/quote cards, SFX — every element frame-synced to your
voice — plus a post kit (hook, caption, 5 hashtags), ready for TikTok/Reels/Shorts.

Built end-to-end by Claude (architect: Claude Opus spec, builder: Claude Code)
around one idea:

> **The LLM never touches the timeline.** A weak runtime model (MiniMax-M3)
> picks treatments from menus by word-index. Deterministic code owns every
> millisecond, every validation, every render. The harness makes quality
> inevitable regardless of model strength.

---

## Quickstart

```bash
git clone <this-repo> ~/vulcan && cd ~/vulcan
./setup.sh                                # prereqs → venv → deps → browser → sfx → doctor
bin/vulcan run fixtures/fixture_60s.ogg   # full pipeline on the bundled test note
bin/vulcan setup-agent hermes             # wire your agent (or: openclaw | generic)
```

Point `config.yaml → director:` at any Anthropic-compatible `/v1/messages`
endpoint (every field explained in [config.example.yaml](config.example.yaml)),
list your platform's voice-note cache dirs in `trigger.voice_cache_dirs` — and
your agent forges videos. Adopter's guide: §6 below.

## Showcase

<!-- sample output goes here: 3-4 frames or a GIF (runs/golden/qc/ has full
     contact sheets after `tests/build_golden.py` + a render) -->
*Coming soon — golden-run frames and a real forged reel.*

---

## 1. The pipeline

```
voice.ogg ──▶ [1 ingest]   ffmpeg: denoise → compress → 2-pass loudnorm −14 LUFS   → mastered.wav
          ──▶ [2 asr]      faster-whisper small/int8 word timestamps               → words.json
          ──▶ [3 director] MiniMax-M3, 4 passes, validated + auto-repaired         → manifest.json
          ──▶ [4 assets]   waterfall fetch → rembg cutout → stamp → SigLIP gate    → assets/*.png
          ──▶ [5 render]   Remotion (React) — pure function of manifest + assets   → raw.mp4
          ──▶ [6 qc]       duration/res/loudness/dead-frame gates + auto-repair    → final.mp4
          ──▶ [7 deliver]  Telegram via Hermes (MEDIA: relay) + post kit
```

Every run writes a self-contained audit trail to `runs/<video_id>/`:
`audio/`, `words.json`, `manifest.json`, `assets/`, `out/final.mp4`,
`qc/` (report, sampled frames, contact sheet), `pipeline.log` (forensics).

### Stage 1 — Ingest (`vulcan/ingest.py`)
`ogg/mp3/m4a/wav → mastered.wav` (mono 48k):
`afftdn` light denoise (nr=12 — heavier NR smears consonants and hurts ASR) →
`acompressor` 3:1 (tames peaks so linear loudnorm can reach target) →
**two-pass measured loudnorm** to −14 LUFS → residual-gain correction through a
limiter. The mastered track **is** the final video audio, so ASR, the manifest,
the render, and QC all share one timeline by construction.

### Stage 2 — ASR (`vulcan/asr.py`)
faster-whisper `small`/int8 on CPU (benchmarked 25× faster than WhisperX's
CPU aligner for ±200ms boundary difference that's invisible at 3–5-word caption
groups; see BUILDLOG Phase 2). Language auto-detect (English/French verified).
Output contract `words.json`: `{"words": [{"w","s","e","p"}...]}` in absolute
ms. Deterministic normalization fixes known whisper quirks (zero-duration
words, timestamp regressions); a sanity gate aborts loudly on garbage audio.

### Stage 3 — Director (`vulcan/director/`)
MiniMax-M3 through its **Anthropic-compatible** endpoint
(`https://api.minimax.io/anthropic/v1/messages`) — the same provider and key
Hermes itself runs on. Zero Anthropic-service calls at runtime. Four passes,
temp 0.2, strict JSON, ≤3 retries with **validator errors injected verbatim**
into the retry prompt:

| pass | in → out | the trick |
|---|---|---|
| A — Beat Cut | numbered words + pause markers → `{"cuts":[word indices]}` | model picks *idea boundaries*; `repair_cuts()` fixes beat-length violations mechanically (extra cuts at largest silences, orphan merges). Re-asking a weak reasoner to satisfy `1.2s ≤ beat ≤ 5.0s` numerically is a dead end — math repairs it deterministically. |
| B — Treatment & Copy | beat table → per-beat treatment/emphasis/assets/sfx/camera/transition (+payloads) | every anchor is a **word index**, never a millisecond. `assemble_manifest()` converts deterministically; attempts 1–2 strict (errors injected), final attempt **lenient**: unknown cue → dropped, unspoken emphasis word → dropped, malformed payload → treatment downgraded to `kinetic_type`. Two strict shots keep quality pressure; the lenient pass makes a legal manifest inevitable. |
| C — Coherence | manifest summary → whitelisted patch ops | patches applied transactionally; if the patched manifest fails validation, the whole set reverts. |
| D — Post kit | transcript → hook/caption/5 hashtags | length + hashtag normalization enforced. |

The few-shot examples in `vulcan/director/prompts/*.md` are the quality
ceiling — they're written the way the golden manifest was hand-authored.

### Stage 4 — Assets (`vulcan/assets/`)
Per manifest asset: **cache first** (`cache/media.db`, SigLIP-embedding
similarity — recurring topics compound), then the source waterfall:

| type | sources (in order) |
|---|---|
| photo_cutout | ddg images (transparent first) → Wikimedia Commons → ddg any + rembg |
| emoji / 3d_icon | Microsoft fluentui-emoji 3D (MIT, deterministic URL from unicode name) → iconify |
| flat_icon | iconify (rendered white for the dark canvas) |
| logo | iconify `logos`/`simple-icons` (auto-recolored white if too dark) → ddg |
| screenshot | ddg images |

Every raster is **stamped house-style** (`stamp.py`): rembg
`isnet-general-use` if no alpha → largest-connected-component cleanup (kills
shredded cutouts) → autocrop → 12px white sticker stroke + soft drop shadow →
PNG ≤1000px. Stock-photo preview domains are blocklisted (watermarks).
Search-sourced candidates must clear the **SigLIP relevance gate**
(`google/siglip-base-patch16-224`, CPU): threshold **0.045**, calibrated on 10
good/bad pairs (good ≥ 0.078, bad ≤ 0.013). A failed asset never kills a run —
its beat degrades to `kinetic_type`.

### Stage 5 — Render (`vulcan/render.py` + `remotion/`)
`render(manifest, assets) → mp4` — a pure function. The Remotion project:

- `src/tokens.ts` — **the single style source**: colors, type scale, springs,
  layout fractions. The accent color is injected from `config.yaml`; nothing
  else is overridable, nothing is hardcoded elsewhere.
- `src/Captions.tsx` — the always-on karaoke engine: 3–4-word groups split on
  punctuation/pauses, active-word pop (adaptive scale cap so long words never
  fuse), persistent accent on Director-chosen emphasis words, headline mode
  with accent underline. Caption text comes **verbatim from `beat.words`** —
  paraphrase is structurally impossible.
- `src/treatments/` — the 9-treatment menu: `kinetic_type` (+ giant ghost word),
  `cutout_pop`, `stat_slam` (count-up), `list_stack` (word-anchored rows),
  `tweet_card` (synthetic, always crisp), `screenshot_zoom` (browser frame +
  Ken Burns), `logo_versus` (slam + shake), `emoji_burst`, `quote_card`.
- Background (gradient drift + film grain + vignette), Camera enum
  (static/punch_in/drift), Transitions (hard_cut/whip/flash), SFX layer.
- `calculateMetadata` derives duration from `manifest.audio.duration_ms` — the
  video cannot disagree with the audio.

### Stage 6 — QC (`vulcan/qc.py`)
ffprobe gates (duration ±150ms vs audio, 1080×1920@30 h264, ≤45MB), frame
sampling every 5s → luma-variance dead-frame detection (threshold 4.0,
calibrated: dead 1.8–2.9 vs live ≥4.5) + contact sheet, program loudness −14±1
LUFS. One auto-repair re-render, then loud failure with artifacts.

### Stage 7 — Delivery (`vulcan/deliver.py`)
Default: the CLI prints `DELIVER MEDIA:<abs path>` + post-kit lines; the Hermes
agent relays them with its `send_message` tool (Telegram sends `.mp4` as native
video; 50MB bot cap → CRF 23 keeps 3min ≈ 35MB). Fallback `direct_bot` mode
(Bot API with the token from Hermes's `.env`) exists but is off by default.

### Music beds (`sfx/music/`)
Five synthesized mood loops (energetic / chill / dramatic / uplifting / tech),
CC0-by-construction like the SFX (`sfx/music/build_music.py`), normalized to
sit ≈14 LU under the voice. The Director picks ONE `music_mood` per video
(menu in pass_b rule 15); the renderer loops the bed with **deterministic
word-driven ducking** — the word timestamps are the sidechain: −7dB while
speech is active, breathing back up in real pauses. `audio.music_bed: false`
in config.yaml turns the whole system off.

### Visual-richness law
A structurally-valid manifest can still be creatively empty (learned the hard
way: a green pipeline once shipped 92s of captions on black). Three gates now
make that impossible: pass B rejects manifests where <35% of beats carry a
visual element (retry with the bare beats named); stage 4 aborts if asset
failures collapse coverage below 20%; QC re-checks the final manifest the
same way. Emoji bursts are always a legal visual — even fully abstract
commentary can meet the floor.

### SFX library (`sfx/`)
43 cues, **synthesized from scratch** with seeded numpy/scipy DSP
(`sfx/build_sfx.py`): overlap-crossfaded bandpass-swept whooshes, FM bells,
layered booms, gated glitches… CC0-by-construction (external CC0 zip sources
were JS-walled), deterministic (same bytes every build), RMS-normalized to a
−20dBFS bus so the mix lands at spec. `sfx/index.json` is the contract the
Director picks from and the validator enforces.

---

## 2. The manifest contract

`schemas/manifest.schema.json` (draft 2020-12, `additionalProperties:false`
everywhere) + `vulcan/validate.py` (the deterministic wall — stable error codes
designed for retry injection). Non-negotiables:

- beats **tile the audio exactly**: `b[0].start=0`, `b[i].end == b[i+1].start`,
  `b[-1].end == duration_ms` — structurally guaranteed because beat boundaries
  are *derived from word indices*, never written by the LLM;
- beat length 1.2–5.0s; words in-beat, ascending; asset/sfx windows in-bounds
  (beat-relative); every referenced asset exists, no orphans; role/payload
  requirements per treatment; emphasis words ⊆ spoken words
  (case/punctuation/apostrophe-insensitive); headline ≤6 words; SFX cues must
  exist in `sfx/index.json`;
- **render gate**: every referenced asset `validated` with its file on disk.

102 unit tests (`tests/`) cover the validator, beat math, and the
Director's assembly/patch layers — including adversarial manifests (overlaps,
gaps, orphans, hallucinated cues, out-of-range anchors, malformed payloads).

---

## 3. Layout

```
~/vulcan/
├── README.md            # you are here
├── BUILDLOG.md          # every decision + phase gate + evidence path
├── FEEDBACK.md          # golden-run feedback loop
├── docs/                # BUILD-SPEC.md (original build doctrine) + RECON.md (Hermes internals)
├── setup.sh             # idempotent auto-setup: prereqs → venv → deps → browser → sfx → doctor
├── config.yaml          # ALL tunables (config.example.yaml = fully commented reference)
├── requirements.txt / requirements.lock.txt
├── bin/vulcan           # the one CLI an agent invokes (self-locating wrapper)
├── vulcan/              # python package
│   ├── cli.py           # orchestrator: run/status/doctor, STATUS protocol
│   ├── ingest.py asr.py beats.py validate.py render.py qc.py deliver.py
│   ├── config.py paths.py
│   ├── director/        # client.py, passes.py, prompts/pass_{a,b,c,d}.md
│   └── assets/          # engine.py sources.py stamp.py scorer.py cache.py
├── schemas/manifest.schema.json
├── remotion/            # the render engine (React/Remotion 4)
│   ├── src/ (tokens, Master, Captions, Background, Camera, Transitions, Sfx, treatments/)
│   └── public/ (fonts/Outfit committed; runs/ + sfx/ symlinks)
├── sfx/                 # 43 wavs + index.json + build_sfx.py
├── skills/vulcan/       # SKILL.md.template → SKILL.md generated per-clone by setup-agent
├── tests/               # 102 unit tests + phase3_gate.py + build_golden.py
├── fixtures/            # 62s + 150s public-domain test voice notes
├── cache/media.db       # cross-run asset cache with SigLIP embeddings
└── runs/<video_id>/     # per-run audit trail
```

---

## 4. How Hermes uses it (exact mechanics)

This is how VULCAN wires into a Hermes install at `~/.hermes` —
`bin/vulcan setup-agent hermes` performs the registration automatically
(full recon in [docs/RECON.md](docs/RECON.md)):

1. **Trigger.** A Telegram voice note arrives → Hermes's gateway caches it at
   `~/.hermes/cache/audio/audio_<hex>.ogg` and hands the agent the transcript
   (never the path). The registered skill (`skills/vulcan/SKILL.md`,
   discovered through `skills.external_dirs: [<abs-path-to-your-clone>/skills]` in
   `~/.hermes/config.yaml`) tells the agent: confirm once ("Forge this? y/n"),
   then run in a background terminal:
   ```bash
   ~/vulcan/bin/vulcan run --latest
   ```
   `--latest` resolves the newest cached ogg (≤15 min) itself — the agent
   never types a file path, so it can't hallucinate one.
2. **Status.** The CLI prints `STATUS n/7 …` lines; the skill relays a short
   progress message at stages 1/3/5/7.
3. **Delivery.** On `DONE`, the agent sends a message containing
   `MEDIA:<clone>/runs/<id>/out/final.mp4` (Hermes's media
   convention → native Telegram video), then the post kit text.
4. **Failure.** The skill maps each failing stage to an exact user-facing
   message (see SKILL.md playbook); max one retry; artifacts stay in
   `runs/<id>/` for forensics (`pipeline.log` has the full story).
5. **Secrets.** The MiniMax key is read from `~/.hermes/.env`
   (`MINIMAX_API_KEY`) at call time — never copied, never logged.

Manual use (no Hermes needed):

```bash
bin/vulcan doctor                      # environment self-check
bin/vulcan run path/to/voice.ogg       # full pipeline on a file
bin/vulcan run --latest                # newest UNCONSUMED cached voice note
bin/vulcan status v_20260712_105540    # stage artifacts of a run
bin/vulcan cleanup v_20260712_105540   # after approval: free ~70% of the run (keeps final.mp4 + receipts)
bin/vulcan cleanup --all [--purge]     # housekeeping across runs (golden never touched)
```

Two freshness guarantees keep old and new messages from ever mixing:
`--latest` consults a **consumed-notes ledger** (`runs/.consumed.json`) so a
note that was already forged is never picked again, and `cleanup` migrates
cache-worthy assets to `cache/assets/` before deleting a run's intermediates —
each generation starts from a clean state without losing the cross-run cache.

---

## 5. Ops notes & known constraints

- **Hardware floor:** built/tuned on 12 threads + 7GB RAM + RTX 2050 (GPU
  unused — everything is CPU). Render concurrency 4 ≈ 1.25× realtime;
  stages run sequentially on purpose (RAM).
- **This LAN cannot reach remotion.dev/remotion.media** (Cloudflare) —
  Remotion's browser mirror. The renderer pins `--browser-executable` to the
  puppeteer-cached `chrome-headless-shell`. If you ever wipe
  `~/.cache/puppeteer`, restore it with `npx puppeteer browsers install chrome-headless-shell`.
- **cairosvg segfaults in-process** (native lib clash with onnxruntime) — SVG
  rasterization runs in a subprocess. Don't "simplify" that back.
- ddg image search 403s its own API but falls back to Bing internally (ddgs
  package). Stock-photo domains are blocklisted for watermarks.
- Model caches live in `~/.cache/huggingface` (SigLIP ~780MB, whisper small)
  and `~/.u2net` (rembg isnet ~170MB) — pre-downloaded, no runtime fetches.
- Everything tunable is in `config.yaml`; calibrated values cite their
  BUILDLOG phase. Change `style.accent_color` to re-skin every video.

---

## 6. For future agents — adopting VULCAN for *your* agent

*(This section is for people/agents wiring VULCAN into a different assistant —
Hermes on another box, OpenClaw, a custom agent, anything that can run a CLI.)*

### What you actually need
1. **A Linux box** with: python ≥3.11, node ≥18, ffmpeg/ffprobe, ~10GB free
   disk, ≥6GB RAM. GPU optional (unused by default).
2. **An Anthropic-compatible LLM endpoint** for the Director (any provider
   exposing `/v1/messages`; an OpenAI-style endpoint needs ~30 lines changed in
   `vulcan/director/client.py`). Configure in `config.yaml → director:`
   (`base_url`, `model`, `api_key_env`, `env_file`).
3. **A way to get voice files in and MP4s out** (your agent's platform).

### Install
```bash
git clone <this repo> ~/vulcan && cd ~/vulcan
./setup.sh                              # prereq checks → venv (CPU torch when needed)
                                        # → npm install → headless-browser fallback
                                        # → SFX/music rebuild → bin/vulcan doctor
.venv/bin/python -m pytest tests/ -q    # 102 tests must pass
bin/vulcan setup-agent hermes           # or: openclaw | generic — wires your agent
```
`setup.sh` is idempotent — re-run it after pulling updates. First run downloads
SigLIP (~780MB), whisper-small (~460MB), and rembg-isnet (~170MB) into local
caches; after that it's offline except asset search + LLM calls.

### Wire your agent (the contract)
Your agent needs exactly three behaviors — copy the doctrine from
`skills/vulcan/SKILL.md`:
1. **Invoke:** run `bin/vulcan run <voice_file>` (or implement your own
   `--latest`-style resolver in `config.yaml → trigger.voice_cache_dirs` if
   your platform caches voice notes to disk). Run it in the background — a
   3-min note takes ~6–10 min on modest hardware.
2. **Relay:** stream the `STATUS n/7` lines as short progress messages.
3. **Deliver:** on `DONE`, send the file from the `DELIVER MEDIA:<path>` line
   + the `POST_KIT_START…END` text. On `ERROR`, map the last STATUS stage to
   a human message (table in SKILL.md); retry at most once.
4. **Clean up on approval:** when the user accepts/takes the video, run
   `bin/vulcan cleanup <RUN_ID>` (see SKILL.md §6) — keeps `final.mp4` and the
   receipts, frees the intermediates, and preserves the shared asset cache.

**Do not** let your agent edit manifests, pick timings, or "help" the
pipeline. The whole design is that the agent is a thin relay around one
deterministic CLI. If you want different creative behavior, change the
*menus*: treatment components in `remotion/src/treatments/` + the prompt menus
in `vulcan/director/prompts/pass_b.md` + the enums in
`schemas/manifest.schema.json` and `vulcan/validate.py` — all four must agree
(the tests will tell you if they don't).

### Where quality comes from (don't skip these)
- The **few-shot examples** in the pass prompts are the ceiling for your
  runtime model. If you swap the Director model, rewrite them at the best
  quality you can produce — a stronger example beats a stronger model.
- The **eye-check ritual** is not optional culture, it's the QA method:
  after any visual change, render `tests/build_golden.py`'s manifest and view
  one frame per beat (`runs/golden/qc/`). Frames that read "template demo" fail.
- The **validator is the API** between the LLM and the renderer. New failure
  mode observed? Add a stable error code + a test + (if it's a taste-level
  slip) a lenient coercion. Never widen the schema to "make it work".
- Calibrate on YOUR corpus: SigLIP threshold (10 good/bad pairs),
  `qc.min_luma_variance` (dead vs live frames), render concurrency (RAM).
  Grep BUILDLOG for "calibrated" to see the method for each.

### The three invariants (break these and you've rebuilt HyperFrames)
1. LLM emits **word indices and menu picks only** — code computes all times.
2. `render(manifest, assets) → mp4` stays a **pure function** — no LLM, no
   network, no clock in the render path.
3. **Validate between every stage**, inject errors on retry, repair
   mechanically where the model is structurally weak (beat lengths, payload
   shapes), and fail loudly with artifacts when the gate can't be met.

---

*Built 2026-07-12. Full decision log with evidence: [BUILDLOG.md](BUILDLOG.md).
Integration recon: [docs/RECON.md](docs/RECON.md). License: [MIT](LICENSE)
(assets fetched at runtime keep their own licenses; SFX are CC0-by-construction;
Outfit font is OFL).*
