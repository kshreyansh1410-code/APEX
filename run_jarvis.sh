#!/usr/bin/env bash
set -euo pipefail

# Run from repository root. Exits on error.
if [ ! -d "agent" ]; then
  echo "Error: 'agent' directory not found in $(pwd)"
  exit 1
fi

cd agent

PYTHON_CMD="${PYTHON:-python3}"

if ! command -v "$PYTHON_CMD" >/dev/null 2>&1; then
  echo "Error: $PYTHON_CMD not found. Install Python 3 or set PYTHON env var."
  exit 1
fi

# Create venv if missing
if [ ! -d ".venv" ]; then
  "$PYTHON_CMD" -m venv .venv
fi

# Activate venv for this script
# shellcheck disable=SC1091
. .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

# Run the package
python -m jarvis
