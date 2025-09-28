# Lifemaxerbot - Twitter/X AI Bot

Minimal Twitter bot scaffold using Python, Tweepy, and pluggable content generation: Hosted (OpenAI-compatible), Ollama, or Transformers.

## Quickstart

1. Create a virtual env and install deps:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Configure environment variables:

```bash
cp .env.example .env
# Fill values in .env
```

Required for posting:
- `TWITTER_API_KEY`
- `TWITTER_API_KEY_SECRET`
- `TWITTER_ACCESS_TOKEN`
- `TWITTER_ACCESS_TOKEN_SECRET`

Pick ONE generation method:
- Hosted provider (recommended for Railway): set `PROVIDER_BASE_URL`, `PROVIDER_API_KEY`, `PROVIDER_MODEL`.
  - Together example:
    - `PROVIDER_BASE_URL=https://api.together.xyz/v1`
    - `PROVIDER_MODEL=meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo`
  - OpenRouter example:
    - `PROVIDER_BASE_URL=https://openrouter.ai/api/v1`
    - `PROVIDER_MODEL=meta-llama/llama-3.1-70b-instruct:free`
- Ollama (local): install Ollama and set `OLLAMA_MODEL` (e.g., `llama3.2:3b-instruct`).
- Transformers (local): set `HF_MODEL` (e.g., `distilgpt2`) and install `torch`.

Optional:
- `TWITTER_BEARER_TOKEN` (useful for reads)
- `MAX_LENGTH` (default 220)
- `DRY_RUN_DEFAULT` (default `true`)

3. Use the CLI:

```bash
# Health check
python -m bot health

# Generate only (engine auto/provider/ollama/hf/fallback)
python -m bot generate "Prompt" --engine provider

# Generate and post (respecting DRY_RUN_DEFAULT)
python -m bot post "Prompt" --engine provider

# Force post now
python -m bot post "Prompt" --engine provider --no-dry-run

# Post raw text (no generation)
python -m bot post-text "Hello world"
```

## Railway deployment
- Push to GitHub and connect the repo on Railway.
- Set env vars in Railway (Twitter keys + provider vars).
- Cron job example:
  - Command: `python -m bot post "Daily tip about healthy habits" --engine provider --no-dry-run`
  - Schedule as desired.
- If using provider only, you can remove `transformers` from requirements to keep image light.

## Notes
- Posting requires proper app permissions (Read + Write) and a plan with write access.
- Tweets should be under 280 chars; `MAX_LENGTH` is used to truncate.

## Posting cycle (9 text + 1 image)

- New command: `post-cycle` maintains a 10-slot loop.
  - Slots 1–9: text-only tweets generated from your prompt seed.
  - Slot 10: an engagement question (randomly chosen) plus an image rendering of a stored quote in monochrome (black-on-white or white-on-black).

Examples:

```bash
# Seed guides the style for the nine text tweets
python -m bot post-cycle "Short blunt tweet about discipline, stoicism, purpose, self-control. No hashtags, no emojis." --engine provider --no-dry-run

# Ingest quotes first for the image cycle
python -m bot ingest-csv quotes_public_domain_batch2.csv
```

Notes:
- Cycle index persists to `post_cycle_state.json` (override with `CYCLE_STATE_PATH`).
- If no eligible quotes are found for the 10th slot, the command will prompt you to ingest.
