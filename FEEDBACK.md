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

## Iterations
**2026-07-12 (post-mortem package, commit-tracked):**
- Abstract-topic rule (Samy's prompt rule 12) now backed by a deterministic law: photo/screenshot/logo asset requests must reference a spoken word or they're rejected/dropped. Reverted the 0.30 SigLIP floor (would have disabled the asset engine); kept 0.05.
- Ingest silence cap (pauses ≤0.9s) + provably-convergent `repair_cuts`: his exact failed transcript now cuts cleanly from any input (regression fixture pinned).
- Asset stage bounded (attempt/time caps + network circuit breaker) — no more 16-min hangs; beats degrade and the render ships.
- CLI refuses `runs/` inputs; wrong-python fails fast with the fix; post kit always exists (fallback) and is written to `runs/<id>/post_kit.json`.
- SKILL v1.2: input law, safe-kill recipe, "relay not mechanic" rule, quota playbook.
- **Golden run re-attempt blocked externally:** MiniMax Token Plan exhausted (429 error 2056) mid-re-run of `inbox/custom_agents.ogg`. Everything up to the Director is proven on that note (silence cap: 105.6s→92.2s, max gap 9150ms→1080ms, 27 legal beats). **Next step: top up / wait for MiniMax quota reset, then `bin/vulcan run inbox/custom_agents.ogg --force`** (staged copy; or send a fresh note → `run --latest`).
