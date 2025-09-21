from __future__ import annotations

import sys
from typing import Optional

import typer

from .config import AppConfig
from .generator import ContentGenerator
from .twitter_client import TwitterClient
from .stoic_client import StoicClient

app = typer.Typer(help="AI-powered Twitter bot CLI")


ENGINE_CHOICES = ["auto", "provider", "ollama", "hf", "fallback"]


def _load_components() -> tuple[AppConfig, ContentGenerator, TwitterClient]:
	config = AppConfig.load()
	generator = ContentGenerator(config)
	twitter = TwitterClient(config)
	return config, generator, twitter


def _truncate_to_limit(text: str, limit: int) -> str:
    limit = min(max(limit, 1), 275)
    return text[:limit]


@app.command()
def generate(
	prompt: str = typer.Argument(..., help="Prompt for content generation"),
	max_length: Optional[int] = typer.Option(None, help="Override max length for this run"),
	engine: str = typer.Option("auto", help="Choose generation engine", case_sensitive=False),
):
	"""Generate tweet content and print to stdout."""
	if engine.lower() not in ENGINE_CHOICES:
		raise typer.BadParameter(f"engine must be one of: {', '.join(ENGINE_CHOICES)}")
	config, generator, _ = _load_components()
	if max_length is not None:
		config.max_length = max_length
	text = generator.generate(prompt, preferred_engine=engine)
	print(text)


@app.command()
def post(
	prompt: str = typer.Argument(..., help="Prompt for content generation"),
	dry_run: Optional[bool] = typer.Option(
		None,
		"--dry-run/--no-dry-run",
		help="If set, overrides config default to skip posting or force posting.",
	),
	engine: str = typer.Option("auto", help="Choose generation engine", case_sensitive=False),
):
	"""Generate and post a tweet. Prints tweet text and the tweet id if posted."""
	if engine.lower() not in ENGINE_CHOICES:
		raise typer.BadParameter(f"engine must be one of: {', '.join(ENGINE_CHOICES)}")
	config, generator, twitter = _load_components()
	use_dry_run = config.dry_run_default if dry_run is None else dry_run
	text = generator.generate(prompt, preferred_engine=engine)
	if not text:
		print("[error] Empty generation result; not posting.")
		return
	print(text)
	if use_dry_run:
		print("[dry-run] Skipping post.")
		return
	tweet_id = twitter.post_tweet(text)
	if tweet_id:
		print(f"Posted tweet id: {tweet_id}")
	else:
		print("[skip] No post (rate-limited or error).")


@app.command("post-text")
def post_text(
	text: str = typer.Argument(..., help="Tweet text to post as-is"),
	dry_run: Optional[bool] = typer.Option(
		None,
		"--dry-run/--no-dry-run",
		help="If set, overrides config default to skip posting or force posting.",
	),
):
	"""Post provided text as a tweet (no generation)."""
	config, _, twitter = _load_components()
	use_dry_run = config.dry_run_default if dry_run is None else dry_run
	print(text)
	if use_dry_run:
		print("[dry-run] Skipping post.")
		return
	tweet_id = twitter.post_tweet(text)
	if tweet_id:
		print(f"Posted tweet id: {tweet_id}")
	else:
		print("[skip] No post (rate-limited or error).")


@app.command()
def health():
	"""Check basic configuration and environment."""
	config, _, _ = _load_components()
	missing = []
	if not config.twitter_api_key:
		missing.append("TWITTER_API_KEY")
	if not config.twitter_api_key_secret:
		missing.append("TWITTER_API_KEY_SECRET")
	if not config.twitter_access_token:
		missing.append("TWITTER_ACCESS_TOKEN")
	if not config.twitter_access_token_secret:
		missing.append("TWITTER_ACCESS_TOKEN_SECRET")
	# bearer is optional for posting with user context, but useful for reads
	status = "ok" if not missing else f"missing: {', '.join(missing)}"
	print(f"config: {status}")


@app.command("post-stoic")
def post_stoic(
    dry_run: Optional[bool] = typer.Option(
        None,
        "--dry-run/--no-dry-run",
        help="If set, overrides config default to skip posting or force posting.",
    ),
):
    """Fetch a Stoic quote from a free API and post it."""
    config, _, twitter = _load_components()
    use_dry_run = config.dry_run_default if dry_run is None else dry_run
    stoic = StoicClient()
    result = stoic.fetch_quote()
    if not result:
        print("[error] Failed to fetch stoic quote.")
        return
    text, author = result
    if author:
        candidate = f"\"{text}\" — {author}"
    else:
        candidate = text
    tweet = _truncate_to_limit(candidate, config.max_length)
    print(tweet)
    if use_dry_run:
        print("[dry-run] Skipping post.")
        return
    tweet_id = twitter.post_tweet(tweet)
    if tweet_id:
        print(f"Posted tweet id: {tweet_id}")
    else:
        print("[skip] No post (rate-limited or error).")


def run():
	app()


if __name__ == "__main__":
	run()
