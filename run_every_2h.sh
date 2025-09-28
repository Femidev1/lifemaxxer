#!/bin/bash
set -euo pipefail

cd "/Users/femidavid/Lifemaxerbot"
source .venv/bin/activate

# Cycle runner: 9 text tweets then 10th engagement+image
PROMPT="Short blunt tweet about discipline, stoicism, purpose, self-control. No hashtags, no emojis."

python -m bot post-cycle "$PROMPT" --engine ollama --no-dry-run
