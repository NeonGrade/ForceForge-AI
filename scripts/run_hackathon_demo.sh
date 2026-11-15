#!/bin/sh
# Safe demo launcher: no Docker cleanups, new CFD solves, or file deletions.
set -eu
cd "$(dirname "$0")/.."
if [ -f .venv/bin/activate ]; then
  . .venv/bin/activate
fi
python -m streamlit run hackathon_app.py --server.port 8501 --server.fileWatcherType none
