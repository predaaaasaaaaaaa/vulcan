# FEEDBACK — Golden Run (Phase 7)

Samy's notes on the first real voice-note video land here, verbatim, with the
fix/iteration log underneath each item.

## Golden run
- **Announced:** 2026-07-12 11:05 — "VULCAN is live" delivered to telegram home channel (chat_id <redacted>) via `hermes send`, exit 0.
- **Voice note received:** _pending — Hermes triggers `bin/vulcan run --latest` automatically per skills/vulcan/SKILL.md (one-tap confirm, auto_mode=false)_
- **Run id:** _pending_
- **Delivered:** _pending_

## Samy's notes — session 1 (2026-07-12, via VULCAN_FORGE_REPORT.md)
1. Literal object scraped onto an abstract line ("black bull" on the bankruptcy beat) — visuals must BE the words for opinion/commentary content.
2. Too many operator-side failures: stale audio re-forged 3×, wrong python, 16-min asset hang, Pass-A death on his real 106s note.
3. "Didn't expect that many errors — stop and report."

## Samy's notes — session 2 (2026-07-14, run v_20260714_033227)
1. "Captions and SFX are there but NO visual animations at all — no PNGs, no motion graphics, pure black screen."
2. "No background music that corresponds to the type of video."

**Iteration (same day):** richness law (pass-B quota + 35%/20% floors + stage-4 abort + QC gate), emoji query resolution fixed (the 404 class), music system built (5 mood beds, Director-picked, word-ducked), never-bare kinetic beats, screenshot cache-pollution fix. Re-run of the same note: 10 visual beats (8 emoji + cutout + ChatGPT screenshot), tech bed, QC green — frames eye-checked. Video: `runs/v_20260714_041639/out/final.mp4`.

## Samy's notes — session 3 (2026-07-14, run v_20260714_041639)
1. "Only emojis are rendering — we need something pro: screenshots, PNGs, charts, animations, MOTION-GRAPHICS."
2. "All of that should be animated as the talking goes."
3. "A lot of black void spaces — not something people will watch."

**Iteration (same day, pro-bar sprint):** KineticType v2 (power-word stacks slamming in at word timestamps — void class eliminated), Background v2 (dot grid + accent blobs), idle motion on every element, NEW chart_pop treatment (animated bar/line charts), variety law (emoji ≤50% of visual beats), logo-ambiguity law (no logos for name-colliding niche tools — a Hermès Paris logo appeared on an AI-agents beat and was surgically replaced), off-by-one anchor forgiveness + orphan pruning (fixed a pass-B failure chain). Result: `runs/v_20260714_053419/out/final.mp4` — 7 treatment types, 50% coverage, OpenAI-vs-cloud versus beat, tech bed. Frames eye-checked.

## Iterations
**2026-07-12 (post-mortem package, commit-tracked):**
- Abstract-topic rule (Samy's prompt rule 12) now backed by a deterministic law: photo/screenshot/logo asset requests must reference a spoken word or they're rejected/dropped. Reverted the 0.30 SigLIP floor (would have disabled the asset engine); kept 0.05.
- Ingest silence cap (pauses ≤0.9s) + provably-convergent `repair_cuts`: his exact failed transcript now cuts cleanly from any input (regression fixture pinned).
- Asset stage bounded (attempt/time caps + network circuit breaker) — no more 16-min hangs; beats degrade and the render ships.
- CLI refuses `runs/` inputs; wrong-python fails fast with the fix; post kit always exists (fallback) and is written to `runs/<id>/post_kit.json`.
- SKILL v1.2: input law, safe-kill recipe, "relay not mechanic" rule, quota playbook.
- **Golden run re-attempt blocked externally:** MiniMax Token Plan exhausted (429 error 2056) mid-re-run of `inbox/custom_agents.ogg`. Everything up to the Director is proven on that note (silence cap: 105.6s→92.2s, max gap 9150ms→1080ms, 27 legal beats). **Next step: top up / wait for MiniMax quota reset, then `bin/vulcan run inbox/custom_agents.ogg --force`** (staged copy; or send a fresh note → `run --latest`).
