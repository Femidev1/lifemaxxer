# Lifemaxerbot - Interesting Facts Bot for X

Minimal Twitter bot that posts a single-line interesting fact: "Did you know ...". Uses Python, Tweepy, and pluggable LLMs (Hosted OpenAI-compatible, Ollama, or Transformers).

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

# Generate a fact (engine auto/provider/ollama/hf/fallback)
python -m bot generate-fact "black holes" --engine provider

# Generate and post a fact (respecting DRY_RUN_DEFAULT)
python -m bot post-fact "the Amazon rainforest" --engine provider

# Force post now
python -m bot post-fact --engine provider --no-dry-run

# Post raw text (no generation)
python -m bot post-text "Did you know octopuses have three hearts?"
```

## Railway deployment
- Push to GitHub and connect the repo on Railway.
- Set env vars in Railway (Twitter keys + provider vars).
- Cron job example:
  - Command: `python -m bot post-fact --engine provider --no-dry-run`
  - Schedule as desired.
- If using provider only, you can remove `transformers` from requirements to keep image light.

## Notes
- Posting requires proper app permissions (Read + Write) and a plan with write access.
- Tweets should be under 280 chars; `MAX_LENGTH` is used to truncate.

## Facts

- Output format: starts with "Did you know " and ends with punctuation.
- Keep under 240 characters; the bot truncates to `MAX_LENGTH`.
