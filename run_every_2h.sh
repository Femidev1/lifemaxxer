#!/bin/bash
set -euo pipefail

cd "/Users/femidavid/Lifemaxerbot"
source .venv/bin/activate

PROMPT="Drop a random motivational quote, feel free to look up one on the internet or make some shit up. Also be direct a use some vulgar language"

python -m bot post "$PROMPT" --engine ollama --no-dry-run
