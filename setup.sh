#!/usr/bin/env bash
# VULCAN auto-setup — idempotent, safe to re-run on an existing install.
# Fresh clone → working `bin/vulcan doctor` in one command:
#   git clone <repo> ~/vulcan && cd ~/vulcan && ./setup.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
cd "$ROOT"

say()  { printf '\n\033[1m== %s\033[0m\n' "$*"; }
fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }

say "prerequisites"
command -v ffmpeg  >/dev/null || fail "ffmpeg not found (e.g. apt install ffmpeg)"
command -v ffprobe >/dev/null || fail "ffprobe not found (ships with ffmpeg)"
command -v node    >/dev/null || fail "node not found (need >= 18)"
command -v npm     >/dev/null || fail "npm not found"
NODE_MAJOR="$(node -e 'console.log(process.versions.node.split(".")[0])')"
[ "$NODE_MAJOR" -ge 18 ] || fail "node >= 18 required (found $(node --version))"
PY="${PYTHON:-python3}"
command -v "$PY" >/dev/null || fail "python3 not found (need >= 3.11)"
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' \
  || fail "python >= 3.11 required (found $("$PY" --version 2>&1))"
echo "ffmpeg + node $(node --version) + $("$PY" --version) OK"

say "python venv"
if [ ! -x .venv/bin/python ]; then
  # inherit a system torch when present (saves ~800MB download); else plain venv
  if "$PY" -c 'import torch' 2>/dev/null; then
    echo "system torch found — creating venv with --system-site-packages"
    "$PY" -m venv --system-site-packages .venv
  else
    "$PY" -m venv .venv
  fi
else
  echo ".venv exists — reusing"
fi
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt
# the SigLIP relevance gate needs torch; pull the CPU wheel only when nothing
# already provides it (CUDA is never required — the pipeline is CPU-first)
if ! .venv/bin/python -c 'import torch' 2>/dev/null; then
  echo "no torch available — installing CPU build"
  .venv/bin/pip install -q torch --index-url https://download.pytorch.org/whl/cpu
fi
echo "python deps OK"

say "remotion (node deps)"
( cd remotion && npm install --no-audit --no-fund --loglevel=error )
echo "remotion deps OK"

say "headless browser for the renderer"
# remotion.dev/remotion.media can be unreachable on some LANs (Cloudflare) —
# the renderer pins a puppeteer-cached chrome-headless-shell instead of letting
# Remotion download one mid-render (BUILDLOG Phase 4). A system Chrome also works.
if compgen -G "$HOME/.cache/puppeteer/chrome-headless-shell/*/chrome-headless-shell-linux64/chrome-headless-shell" >/dev/null 2>&1; then
  echo "chrome-headless-shell present OK"
elif command -v google-chrome >/dev/null || command -v chromium >/dev/null || command -v chromium-browser >/dev/null; then
  echo "system Chrome/Chromium found — Remotion will use it"
else
  ( cd remotion && npx --yes puppeteer browsers install chrome-headless-shell )
fi

say "sfx library (synthesized from scratch, deterministic)"
WAVS=$(find sfx -maxdepth 1 -name '*.wav' 2>/dev/null | wc -l)
if [ "$WAVS" -ge 40 ]; then
  echo "$WAVS sfx cues present OK"
else
  .venv/bin/python sfx/build_sfx.py
fi
MUSIC=$(find sfx/music -maxdepth 1 -name '*.wav' 2>/dev/null | wc -l)
if [ "$MUSIC" -ge 5 ]; then
  echo "$MUSIC music beds present OK"
else
  .venv/bin/python sfx/music/build_music.py
fi

say "workspace dirs + render symlinks"
mkdir -p runs cache/assets inbox
[ -e remotion/public/runs ] || ln -sfn ../../runs remotion/public/runs
[ -e remotion/public/sfx ]  || ln -sfn ../../sfx  remotion/public/sfx
echo "runs/ cache/ inbox/ + symlinks OK"

say "doctor"
bin/vulcan doctor || true

cat <<EOF

Setup done. Next steps:
  bin/vulcan run fixtures/fixture_60s.ogg   # full pipeline on the bundled test note
  bin/vulcan setup-agent hermes             # wire into a Hermes agent install
  bin/vulcan setup-agent generic            # the 3-step contract for any agent

Notes:
- The Director needs an API key: config.yaml -> director (api_key_env/env_file).
  A doctor X on the key just means that part isn't configured yet.
- First run lazily downloads models: SigLIP ~780MB, whisper-small ~460MB,
  rembg-isnet ~170MB (one-time, cached in ~/.cache and ~/.u2net).
EOF
