#!/usr/bin/env bash
# One-command start for macOS / Linux:  bash run.sh
set -e
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null 2>&1; then echo "Python 3 not found. Install it from https://www.python.org/downloads/ and run this again."; exit 1; fi
if [ ! -d .venv ]; then echo "Setting up (first run only, takes a minute)..."; python3 -m venv .venv; fi
source .venv/bin/activate
python -m pip install -q --upgrade pip || true
python -m pip install -q -r requirements.txt
python scripts/load_demo.py      # creates the demo accounts if missing; existing accounts are left untouched
PORT="${PORT:-5001}"
echo; echo "Open http://localhost:${PORT}  (login: demo / demo1234).  Press Ctrl+C to stop."
PORT="$PORT" python app.py
