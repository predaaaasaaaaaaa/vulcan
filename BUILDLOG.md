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

---

## PHASE 3 — ASSET ENGINE
**Status: ✅ PASS** — 2026-07-12

- Modules: [sources.py](vulcan/assets/sources.py) (waterfall), [stamp.py](vulcan/assets/stamp.py) (rembg isnet-general-use → largest-component cleanup → autocrop → 12px stroke + shadow), [scorer.py](vulcan/assets/scorer.py) (SigLIP base CPU), [cache.py](vulcan/assets/cache.py) (media.db + embedding similarity lookup), [engine.py](vulcan/assets/engine.py) (orchestration).
- **Source swaps (dead-source rule):**
  - `duckduckgo_search` → `ddgs` (renamed upstream); DDG's own image API 403s but ddgs transparently falls back to Bing images — works.
  - 3dicons.co & LottieFiles are JS-walled → **3d_icon + emoji = Microsoft fluentui-emoji 3D** (MIT, raw.githubusercontent, deterministic URL from unicode name, verified: fire/rocket/brain/money bag/tears-of-joy all 200). Apple emoji sources max at 160px (checked emojipedia CDN + iamcal); fluent 3D ships 256px → Lanczos-upscaled to 512 (smooth-shaded art upscales cleanly). **lottie deferred: not in v1 menus** (emoji_burst + 3d_icon cover the need); plumbing kept.
  - Kenney.nl zips are JS-gated → **SFX synthesized instead** (see Phase 4 entry).
- **Crashes found & fixed:** (1) `cairosvg` import segfaults the process (native lib clash with onnxruntime/torch) → SVG rasterization isolated into a subprocess; (2) PIL `MaxFilter(1)` segfaults C layer when stroke_px=0 → guarded. Both were silent process deaths — found via core dumps.
- **Eye-check iteration (the gate doing its job):** first sheet had 2 failures invisible to scores: Eiffel = lightning-storm photo shredded by rembg (fix: `keep_largest_component` — reject cutouts whose largest connected alpha component < 75% of mass); GitHub = black octocat on near-black canvas (fix: `mean_luma < 0.22` → refetch iconify mono sets with `color=white`, reject dark rasters). Re-run: both post-grade.
- **SigLIP threshold calibrated on 10 good + 10 bad pairs** from the gate assets: good ∈ [0.0781, 0.1646], bad ∈ [−0.0706, 0.0128], gap 0.065. **Threshold = 0.045** → config.yaml. Policy: mandatory for search-sourced candidates (ddg/wikimedia); advisory for name-exact sources (iconify/fluent) whose relevance is guaranteed by lookup.
- **Gate: 8/8 queries validated across all types → contact sheet VIEWED, all post-grade** (`runs/phase3_gate/contact_sheet.png`). Cache verified: re-run hits media.db by embedding similarity, zero network.

**Evidence:** `runs/phase3_gate/contact_sheet.png` (+ per-asset PNGs), calibration table in session log, `cache/media.db`.

---

## PHASE 4 — REMOTION RENDER
**Status: ✅ PASS** — 2026-07-12

- Remotion 4 project under [remotion/](remotion/): `tokens.ts` (single style source, accent injectable from config.yaml via inputProps), offline font loading (committed Outfit variable TTF), Background (gradient drift + SVG grain + vignette), Captions (karaoke engine: 3–4-word groups split on punctuation/gaps, active-word pop, persistent accent on emphasis words, headline mode with accent underline), Camera (static/punch_in/drift), Transitions (hard_cut/whip/flash), all **9 treatments**, SFX layer, `<Master>` with `calculateMetadata` deriving duration from the manifest — the renderer cannot disagree with the audio.
- **Network quirk:** remotion.dev/remotion.media (Cloudflare) unreachable on this LAN → Remotion crashed on an uncaught fetch at startup. Fixed by pinning `--browser-executable` to the puppeteer-cached chrome-headless-shell 148 (present from the old HyperFrames setup). No Remotion code touched.
- **SFX library:** all external CC0 zip sources are JS-walled (Kenney) → **synthesized all 43 cues** with seeded numpy/scipy DSP ([sfx/build_sfx.py](sfx/build_sfx.py)): swept-bandpass whooshes (overlap-add crossfade after spectrogram showed block striping — verified by eye on spectrograms), FM bells, gated squares, layered booms. RMS-normalized to a −20dBFS bus, 24ms tails. CC0-by-construction, deterministic, 1.8MB total.
- **Golden manifest:** [tests/build_golden.py](tests/build_golden.py) — 20 beats over the 62s fixture, all 9 treatments + both overlay modes + 6 real assets. My own validator rejected my first hand-cut (5 beats >5s) — the retry-injection message format proved itself before MiniMax ever saw it.
- **Render gate (VIEW EVERY FRAME):** round 1 — 20/20 frames extracted & viewed; found: word-gap collapse under scale pops, beat-final heroes invisible (lemon/pearl/rooster/bread/VS), ghost lateness, weak headline mode, **watermarked stock pearl**, VS overlap. Fixes: wordGap token 30px; `clamp_asset_enter` ≤55% of beat (in [vulcan/beats.py](vulcan/beats.py), shared with Director conversion); ghost ≤40%; headline 96px + accent underline; **stock-domain blocklist** in ddg source; duel layout 24/76 @300px. Round 2 — 20/20 frames viewed, all pass the bar.
- **QC caught real dead frames** (beats opening on ASR silence rendered nothing for up to 1.5s). Fix: captions always-on — first group displays dim from beat start, karaoke pop still lands on the word. Calibration data: dead frames var 1.8–2.9, live minimum 4.5 → `min_luma_variance: 4.0` confirmed.
- **Final gate:** `runs/golden/out/golden.mp4` — **QC PASS**: Δduration 59ms, 8.57MB (≈25MB for 3min, well under the 45MB cap → CRF 23 confirmed), −14.62 LUFS, 12/12 sampled frames alive. Render 77s for 62s @ concurrency 4 (RAM watchdog silent) → `render.concurrency: 4` calibrated.

**Evidence:** `runs/golden/out/golden.mp4`, `runs/golden/qc/` (r2_sheet_1..4.png = all 20 beat frames, contact_sheet.png, qc_report.json), `runs/golden/manifest.json`.

---

## PHASE 5 — DIRECTOR (MiniMax 3-pass + post kit)
**Status: ✅ PASS** — 2026-07-12

- [vulcan/director/client.py](vulcan/director/client.py): MiniMax-M3 via its **Anthropic-compatible** `/v1/messages` (Hermes's own endpoint + key, read at call time from `~/.hermes/.env`; zero Anthropic-service calls). Transient-error backoff ×4, strict JSON extraction tolerant of fences.
- Prompts ([pass_a](vulcan/director/prompts/pass_a.md), [pass_b](vulcan/director/prompts/pass_b.md), [pass_c](vulcan/director/prompts/pass_c.md), [pass_d](vulcan/director/prompts/pass_d.md)): full menus (9 treatments with triggers, 43 sfx with feel-tags, cameras, transitions), hard rules, and worked examples authored at target quality (incl. a French Pass-A example for language coverage). **MiniMax only ever emits word indices and menu picks — never a millisecond.**
- [vulcan/director/passes.py](vulcan/director/passes.py): deterministic conversion (`assemble_manifest`) turns Pass-B JSON into the manifest — word-anchor validation, asset dedup by (type,label), enter-clamp, payload normalization; every model mistake becomes a named, injectable error. Pass C = whitelisted patch ops applied transactionally (validation break → full revert). Pass D post kit with hashtag normalization.
- **Live finding → design upgrade:** MiniMax could not satisfy the 1.2–5.0s beat-length law on slow speech even with error injection (4/4 rejects). Fix: `repair_cuts` — MiniMax picks idea boundaries, **math repairs lengths** (extra cuts at largest internal silences, orphan merges, fixed-point iteration). On the exact failing cut set, repair reproduced nearly the same boundaries I hand-picked for the golden manifest. Re-asking a weak reasoner for arithmetic is a dead end; mechanical repair is doctrine now.
- Unit tests: +11 (`tests/test_director_assembly.py`) → **60 passed** total.
- **Gate: 5/5 consecutive full chains valid** on the Phase-2 transcript (19–20 beats, 6–7 assets, 28–55s per chain). Observed self-healing in the wild: hallucinated cue `kick_01` → rejected+fixed on retry; missing stat payloads → fixed; a Pass-C patch that broke validation → auto-reverted. Run-5 sample quality: hook beat = cutout_pop/punch_in/whoosh + fox emphasis; query specificity like "red fox looking up at grapes illustration"; postable post kit.

**Evidence:** gate output in session log, sample manifests in scratchpad `dirgate_1..5.json`.
