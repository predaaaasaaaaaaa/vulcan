# VULCAN BUILDLOG
Chronological decisions, phase verdicts, evidence. Newest entries appended at the bottom of each phase block.

---

## PHASE 0 — RECON
**Status: ✅ PASS** — 2026-07-12

- Mapped Hermes end-to-end (install, gateway pid 2117, MiniMax config, voice-note flow, send path, skill registration). Full detail: [RECON.md](RECON.md).
- Decision: `vulcan run --latest` resolves the voice file itself — traced `gateway/run.py:13495`: when STT is on, the agent sees the transcript but **never the file path**, so MiniMax must not be asked to supply one.
- Decision: delivery via Hermes `send_message` tool with `MEDIA:<path>` convention (traced `tools/send_message_tool.py:165`).
- Decision: register skill via `skills.external_dirs` (additive config.yaml entry) — no Hermes files modified.
- HyperFrames autopsy (5 bullets in RECON.md §2). Evidence: contact sheet extracted from `~/hermes-demo/hermes-final-v5.mp4` — landscape slide-deck, no word sync, no assets. Confirms every VULCAN prime directive.
- Hardware: 12 cores / 7.1GB RAM (constraint — sequential stages, tuned Remotion concurrency) / RTX 2050 4GB (unused for now, CPU-first) / 255GB disk / node 22 / python 3.12 / ffmpeg 6.1 / torch cu128 pre-installed in user site.
- Network: all asset sources reachable except lottiefiles.com HTML (403 bot-guard) — swapped per dead-source rule: lottie via direct CDN URLs or curated local pack, decided in Phase 3/4.
- MiniMax key: present in `~/.hermes/.env` as `MINIMAX_API_KEY` (no blocker).
- Disk: 255GB ≥ 10GB (no blocker).

**Evidence:** [RECON.md](RECON.md), scratchpad `hf_autopsy/hf_v5_sheet.png`.

---

## PHASE 1 — SKELETON
**Status: ✅ PASS** — 2026-07-12

- Layout per CLAUDE.md created; git repo initialized; venv `~/vulcan/.venv` with `--system-site-packages` (inherits torch 2.8.0+cu128; `torch.cuda.is_available()==True`, GPU held in reserve).
- Deps installed & frozen: [requirements.txt](requirements.txt) (floors) + [requirements.lock.txt](requirements.lock.txt) (155 pinned resolved packages). Note: `duckduckgo_search` is deprecated upstream → installed its successor `ddgs` (import verified). transformers 5.13.1.
- [config.yaml](config.yaml): all tunables centralized; CALIBRATE markers for values set in later phases (siglip_threshold, render.concurrency, crf).
- [schemas/manifest.schema.json](schemas/manifest.schema.json): draft 2020-12, `additionalProperties:false` everywhere, all enums locked (9 treatments, 7 asset types, 5 roles, 3 cameras, 3 transitions). Decision: `enter_ms/exit_ms/at_ms` are **beat-relative** (0 ≤ enter < exit ≤ beat length) — beats are self-contained, renderer computes absolute times.
- [vulcan/validate.py](vulcan/validate.py): deterministic validator with stable error codes (`E_TILE_GAP`, `E_ASSET_ORPHAN`, `E_SFX_UNKNOWN`, …) designed for retry-with-error-injection. Rules: exact tiling 0→duration, beat 1.2–5.0s, words in-beat ascending, asset refs exist + no orphans, windows in bounds, role/payload requirements per treatment, hero type constraints, sfx cues from [sfx/index.json](sfx/index.json), emphasis ⊆ spoken words (case/punct-insensitive), headline ≤6 words, render gate (validated + file exists).
- [sfx/index.json](sfx/index.json): 43-cue contract (ids stable now so Director prompts & validator agree; wav files land Phase 4).
- **Gate: `pytest` → 39 passed** (happy paths + adversarial: overlaps, gaps, wrong start/end, orphan assets, hallucinated asset ids, fake sfx cues, out-of-bounds windows/sfx/list-items, unspoken emphasis words, 7-word headline, bad enums, extra keys, 6 hashtags, render-gate violations).

**Evidence:** `tests/test_validator.py` (39 tests), `pytest -q` output in session log.

---

## PHASE 2 — AUDIO
**Status: ✅ PASS** — 2026-07-12

- [vulcan/ingest.py](vulcan/ingest.py): decode → afftdn (nr=12, gentle — heavy NR smears consonants and hurts ASR) → acompressor 3:1 → **two-pass linear loudnorm** → residual-gain correction with limiter. First attempt undershot (−15.79 LUFS: TP ceiling capped linear gain on dynamic source) → fixed with pre-compression + correction pass. Final fixture: **−14.59 LUFS** (inside qc ±1), mono 48k wav. The mastered track is the single timeline for ASR+render+QC.
- Fixture: `fixtures/fixture_60s.ogg` — 62s LibriVox public-domain English speech, re-encoded **opus-in-ogg** to mimic a Telegram voice note exactly. Source: archive.org `babys_own_aesop_librivox` (PD).
- **ASR benchmark on the 62s fixture (CPU, 12 threads):**
  | engine | total | words | mean confidence |
  |---|---|---|---|
  | faster-whisper base int8 | 6.4s | 86 | 0.885 |
  | faster-whisper **small int8** | **9.7s** | **86** | **0.937** |
  | whisperx small + wav2vec2 align | **259.6s** (align alone 244.9s) | 85 | 0.840 |
- **Decision: faster-whisper / small / int8 / CPU.** WhisperX's aligner is 25× slower on CPU (a 3-min note would spend ~13 min in ASR alone) for a boundary difference of ~±200ms — irrelevant at 3–5-word caption groups and 30fps. GPU could fix it but GPU is optional-only per doctrine (and llama-server holds 734MB VRAM). `small` beats `base` on confidence for +3s; it also carries French far better (auto language detect verified: en @ 0.995).
- ASR hardening: `_normalize_words` fixes whisper's known zero-duration-word quirk (20ms floor, monotonic clamp) — mechanical normalization, not timing invention. `sanity_check_words` gate: monotonicity, in-bounds, ≤3s words, ≥75% words above 0.30 confidence — failures abort loudly.
- [vulcan/beats.py](vulcan/beats.py) (pre-work for Pass A): Director returns **cut indices, never milliseconds** — `cuts_to_beats` computes boundaries at silence midpoints, so tiling is perfect **by construction**, validator double-checks anyway. +10 tests.
- **Gate: `runs/phase2_test/words.json`** — 86 words with per-word ms timestamps + probabilities, sanity checks green. pytest: 49 passed.

**Evidence:** `runs/phase2_test/words.json`, `runs/phase2_test/words_fw_base.json`, `runs/phase2_test/words_whisperx.json`, benchmark output in session log.
