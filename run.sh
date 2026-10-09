#!/usr/bin/env bash
# Start the local API and the web app. Ctrl-C stops both.
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
  echo "ffmpeg and ffprobe are required. On a Mac: brew install ffmpeg" >&2
  exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required (3.11+)." >&2
  exit 1
fi
if ! command -v npm >/dev/null 2>&1; then
  echo "Node.js and npm are required." >&2
  exit 1
fi

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install -q -r backend/requirements.txt

if [[ ! -d frontend/node_modules ]]; then
  npm install --prefix frontend
fi
if [[ ! -f .env ]]; then
  cp .env.example .env
fi

cleanup() {
  if [[ -n "${API_PID:-}" ]]; then kill "$API_PID" 2>/dev/null || true; fi
  if [[ -n "${WEB_PID:-}" ]]; then kill "$WEB_PID" 2>/dev/null || true; fi
}
trap cleanup EXIT INT TERM

python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8741 &
API_PID=$!
npm run dev --prefix frontend -- --host 127.0.0.1 --port 8742 --strictPort &
WEB_PID=$!

echo ""
echo "Spool is running at http://127.0.0.1:8742"
echo ""
wait
