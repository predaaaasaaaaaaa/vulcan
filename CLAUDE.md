# VULCAN — Voice-to-Video Forge
Hermes delivers the message. Vulcan forges the video.

## MISSION
Build a fully automated short-form content system inside Hermes (Samy's agent on this Ubuntu laptop). Input: a voice note sent to Hermes via Telegram. Output: a 1–3 min faceless vertical video (1080×1920, 30fps) with viral-grade motion graphics — kinetic captions, PNG cutouts, 3D icons, SFX — frame-synced to the voice, delivered back on Telegram with a post kit (hook, caption, hashtags), ready to publish.

Claude (Opus) is the architect. You (Claude Code) are the builder. Hermes (MiniMax-M3) is the runtime operator. MiniMax is a weak reasoner — the harness must make quality inevitable regardless of model strength. Your few-shot examples and templates ARE the quality ceiling; write them like Claude would.

## PRIME DIRECTIVES
1. **The LLM never touches the timeline.** All timing comes from word-level ASR timestamps. MiniMax only assigns treatments/assets/text to pre-cut beats by ID. Wrong-image-on-wrong-voice must be structurally impossible.
2. **Renderer is a pure function.** `render(manifest.json, assets/) → mp4`. No LLM in the render path. Same inputs = same video.
3. **Menus, not freedom.** MiniMax picks from enums you define (treatments, SFX cues, asset types, cameras, transitions). It never invents component names, file paths, or timings.
4. **Validate between every stage.** JSON Schema + deterministic validators. On failure: retry with the error injected into the prompt. Max 3 retries, then fail loudly with artifacts.
5. **Guarded Actuator.** Hermes invokes ONE CLI: `vulcan run <voice_file>`. The orchestrator (Python, deterministic) owns the whole pipeline including the MiniMax Director calls. Hermes's skill is thin: receive → invoke → stream status → deliver.
6. **No-Claude Runtime Doctrine.** Zero Anthropic API calls at runtime. MiniMax-M3 only (reuse Hermes's existing key/config — discover in recon, never hardcode secrets).
7. **Lane separation.** Never touch GBrain internals or OpenClaw's lanes (NEXORA/Supabase). Never modify other Hermes agents' files. Additive only. HyperFrames MCP stays installed but UNUSED by VULCAN.
8. **Verify with your eyes.** After every render: extract frames with ffmpeg, VIEW them, judge against the bar. The bar: 5M-view Instagram/TikTok motion-graphics reels. If a frame looks like a template demo, it fails.

## PIPELINE
```
voice.ogg → [1 ingest] → mastered.wav
          → [2 asr] → words.json (word-level timestamps)
          → [3 director] → manifest.json (MiniMax 3-pass, validated)
          → [4 assets] → assets/ (fetched, cut, stamped, scored, cached)
          → [5 render] → raw.mp4 (Remotion)
          → [6 qc] → final.mp4 or auto-repair
          → [7 deliver] → Telegram (mp4 + post kit)
```

## LAYOUT
```
~/vulcan/
├── CLAUDE.md  BUILDLOG.md  RECON.md  config.yaml
├── vulcan/                # python package (orchestrator + stages)
│   ├── cli.py ingest.py asr.py director/ assets/ qc.py deliver.py
├── schemas/manifest.schema.json
├── remotion/              # node project: templates, tokens, captions
├── sfx/                   # ~40 normalized CC0 cues + index.json
├── cache/media.db         # SQLite: query, source, path, embedding, score, uses
├── runs/<video_id>/       # per-run workdir: audio, words, manifest, assets, qc, out
└── skills/vulcan/SKILL.md # Hermes Fat SKILL.md
```

## MANIFEST CONTRACT (the heart)
```json
{
  "video_id": "v_2026...", "fps": 30, "aspect": "9:16",
  "audio": {"path": "mastered.wav", "duration_ms": 83250},
  "beats": [{
    "id": "b01", "start_ms": 0, "end_ms": 3200,
    "words": [{"w":"nobody","s":120,"e":410}, ...],
    "treatment": "cutout_pop",
    "text_overlay": {"mode":"karaoke","emphasis_words":["nobody"]},
    "assets": [{"asset_id":"a01","role":"hero","enter_ms":150,"exit_ms":3200}],
    "sfx": [{"cue":"whoosh_02","at_ms":150}],
    "camera": "punch_in", "transition_out": "hard_cut"
  }],
  "assets": [{
    "asset_id":"a01","type":"photo_cutout",
    "queries":["elon musk pointing","elon musk portrait","elon musk png"],
    "path":null,"status":"pending","score":null
  }]
}
```
**Validator rules (deterministic, non-negotiable):** beats tile the audio exactly (b[i].end == b[i+1].start, 0 → duration_ms); beat length 1.2–5.0s; every asset_id referenced exists and is `validated` before render; enter/exit within beat bounds; all enums valid; karaoke text comes from `words` verbatim (never paraphrased — headline mode may paraphrase, ≤6 words); SFX cues exist in sfx/index.json. Adversarial unit tests required: overlaps, gaps, orphan assets, hallucinated cues.

## TREATMENT LIBRARY (Remotion components — build ONCE, MiniMax only selects)
| treatment | trigger | visual |
|---|---|---|
| kinetic_type | default / abstract statements | karaoke captions center, stressed-word scale-pop (1.08x) + accent color |
| cutout_pop | named person/object/place | stamped PNG cutout springs in beside captions, spring physics |
| stat_slam | numbers, %, money | giant numeral count-up, punch-in, tick SFX |
| list_stack | enumerations ("three things") | items stack in, each on its word timestamp |
| tweet_card | quoting online posts/claims | SYNTHETIC tweet card rendered in Remotion (never scraped — always crisp) |
| screenshot_zoom | referencing product/site | framed screenshot, Ken Burns + highlight box |
| logo_versus | comparisons | two logos/cutouts, VS slam layout |
| emoji_burst | emotional beats | oversized Apple-style emoji, spring + burst |
| quote_card | quotes | serif card + attribution |

Global systems: **caption engine** (always on, 3–5 word groups, center-lower, active word highlighted, punctuation stripped); **background** (near-black #0A0A0C, film grain, slow gradient drift); **camera enum** static|punch_in|drift; **transitions** hard_cut|whip|flash; **audio mix** voice −14 LUFS, SFX ~−22, optional CC0 music bed −26 with ducking (default OFF, config flag).
`tokens.ts` is the single style source: font Outfit ExtraBold (download .ttf once, commit — no runtime font fetch), text #FFFFFF, accent from config.yaml (default #FFCC00), stroke 12px white + soft shadow on all cutouts, shared spring configs. Design tokens configurable, hardcoded nowhere else.

## ASSET ENGINE
asset_type enum + source waterfall (check `cache/media.db` FIRST, always):
- **photo_cutout**: Wikimedia API → DuckDuckGo images (`duckduckgo_search` pip, transparent filter first, else any photo → rembg)
- **3d_icon**: 3dicons.co (CC0) → Icons8 3D
- **flat_icon / logo**: Iconify API → SimpleIcons
- **lottie**: LottieFiles (@remotion/lottie plays natively)
- **emoji**: Apple-style set (iamcal/emoji-data sheets or best hi-res source found) > flat sets
Post-process every raster: rembg `isnet-general-use` if no alpha → autocrop → white stroke + drop shadow stamp → save PNG. Reject source < 500px long edge.
**Validation gate:** alpha sanity + resolution floor + SigLIP relevance score vs beat noun-phrase (CPU inference; calibrate threshold on 10 hand-picked good/bad pairs during build, record in config). Fail → next source → next query variant (Director always supplies 3). All validated assets cached with embeddings — recurring topics compound.

## DIRECTOR (MiniMax 3-pass, owned by orchestrator, temp low, strict JSON, schema-checked, ≤3 retries/pass)
- **Pass A — Beat Cut:** words+timestamps in → beat boundaries out, snapped to word edges, cut on pauses ≥350ms or idea shifts. Validator: perfect tiling.
- **Pass B — Treatment & Copy:** per beat: treatment, emphasis words, asset requests (type + 3 query variants + role), sfx cue, camera, transition. Validator: enums, caps, hero present where required.
- **Pass C — Coherence:** MiniMax reviews full manifest vs checklist (asset matches the spoken noun? no 3 identical treatments in a row? hook lands in first 3s? closing beat?) → returns patch list → orchestrator applies + re-validates.
- **Pass D — Post kit:** hook line, caption, 5 hashtags.
Embed 2 full worked examples per pass in the prompts, authored by you at Claude quality — this is how MiniMax "becomes Claude."

## RENDER + QC + DELIVERY
Remotion: Node 18+, Linux headless-Chromium deps per Remotion docs, one `<Master>` composition consuming manifest via inputProps, concurrency = cores−1, h264 CRF tuned so 3 min ≤ 45MB (Telegram bot cap 50MB; flat graphics compress well).
QC gates: duration delta ≤150ms vs audio; ffprobe res/fps/codec/size; frame sample every 5s → luminance variance (no dead frames) + contact sheet saved to `runs/<id>/qc/`; loudness −14 ±1 LUFS; every beat logged rendered. Fail → one auto-repair (re-render/re-encode) → then surface with artifacts.
Delivery: reuse Hermes's Telegram send path (recon decides; direct bot-token send is acceptable fallback). Status pings at stage transitions. Ship MP4 + post kit.

## HERMES INTEGRATION
Trigger: voice note where caption/intent says video, OR Hermes one-tap confirm ("Forge this? y/n"); `auto_mode: false` default in config. `skills/vulcan/SKILL.md` = Fat SKILL.md doctrine: complete operating manual — trigger rules, CLI invocation, status relay, failure playbook (exact user-facing message per failing stage) — but ALL logic lives in the CLI.

## RUNTIME CONSTRAINTS
Discover in recon: nproc, RAM, nvidia-smi (GPU optional — use if present for ASR/rembg/SigLIP, never require), disk. ASR: benchmark faster-whisper (word_timestamps=True) vs WhisperX on a 60s sample; language auto (English or French possible). Audio master chain: ogg→wav, light denoise (afftdn), loudnorm −14 LUFS — the mastered track IS the video audio. One venv `~/vulcan/.venv`, pinned requirements.txt.

## NEVER
Paid APIs / new accounts / Anthropic runtime calls / refactoring Hermes core / secrets in code / ToS lectures (sources above are owner-approved) / declaring a phase done without its evidence artifact.

## DONE =
`vulcan run` green end-to-end on 2 test notes (~60s and ~150s) → SKILL.md registered → golden run on Samy's real voice note passes his review.
