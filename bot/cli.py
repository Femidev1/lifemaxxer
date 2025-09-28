from __future__ import annotations

import sys
from typing import Optional

import typer

from .config import AppConfig
from .generator import ContentGenerator
from .twitter_client import TwitterClient
from .stoic_client import StoicClient
from .image_maker import ImageMaker
from .ai_image_client import AIImageClient
from .sources import fetch_quote_rotating
from .image_prompt import build_sdxl_prompt
from .quote_store import QuoteStore

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


def _sanitize_no_emdash(text: str) -> str:
    # Replace em dash and en dash with a simple hyphen or space
    sanitized = text.replace("—", "-").replace("–", "-")
    # Avoid fancy quotes; normalize basic quotes
    sanitized = sanitized.replace("“", '"').replace("”", '"').replace("’", "'")
    return sanitized


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
    engine: str = typer.Option("auto", help="Choose generation engine for rephrasing", case_sensitive=False),
    rephrase: bool = typer.Option(True, "--rephrase/--no-rephrase", help="Use AI to paraphrase/reword the quote"),
):
    """Fetch a Stoic quote, optionally rephrase into bot style, and post it."""
    if engine.lower() not in ENGINE_CHOICES:
        raise typer.BadParameter(f"engine must be one of: {', '.join(ENGINE_CHOICES)}")
    config, generator, twitter = _load_components()
    use_dry_run = config.dry_run_default if dry_run is None else dry_run
    stoic = StoicClient()
    result = stoic.fetch_quote()
    if not result:
        print("[error] Failed to fetch stoic quote.")
        return
    text, _author = result
    # Always ignore attribution per requirements
    text = _sanitize_no_emdash(text)
    candidate = text
    if rephrase:
        # Ask the generator to paraphrase into one short blunt tweet with constraints
        prompt = (
            "Paraphrase the following Stoic idea into ONE short tweet. "
            "No hashtags, no emojis, no quotes or attribution, no em dashes. "
            "Tone: raw, direct, confident, no fluff. Under 200 characters.\n\n"
            f"Idea: {text}"
        )
        ai_text = generator.generate(prompt, preferred_engine=engine)
        candidate = ai_text.strip() or text
    tweet = _truncate_to_limit(_sanitize_no_emdash(candidate).strip(), config.max_length)
    print(tweet)
    if use_dry_run:
        print("[dry-run] Skipping post.")
        return
    tweet_id = twitter.post_tweet(tweet)
    if tweet_id:
        print(f"Posted tweet id: {tweet_id}")
    else:
        print("[skip] No post (rate-limited or error).")


@app.command("post-stoic-image")
def post_stoic_image(
    dry_run: Optional[bool] = typer.Option(
        None,
        "--dry-run/--no-dry-run",
        help="If set, overrides config default to skip posting or force posting.",
    ),
    engine: str = typer.Option("auto", help="Choose generation engine for rephrasing", case_sensitive=False),
    rephrase: bool = typer.Option(True, "--rephrase/--no-rephrase", help="Use AI to paraphrase/reword the quote"),
    ai_image: bool = typer.Option(True, "--ai-image/--no-ai-image", help="Generate background with AI Horde when possible"),
):
    """Fetch a Stoic quote, rephrase, render to image, and post as an image tweet."""
    if engine.lower() not in ENGINE_CHOICES:
        raise typer.BadParameter(f"engine must be one of: {', '.join(ENGINE_CHOICES)}")
    config, generator, twitter = _load_components()
    use_dry_run = config.dry_run_default if dry_run is None else dry_run
    stoic = StoicClient()
    result = stoic.fetch_quote()
    if not result:
        print("[error] Failed to fetch stoic quote.")
        return
    text, _author = result
    text = _sanitize_no_emdash(text)
    candidate = text
    if rephrase:
        prompt = (
            "Paraphrase the following Stoic idea into ONE short tweet. "
            "No hashtags, no emojis, no quotes or attribution, no em dashes. "
            "Tone: raw, direct, confident, no fluff. Under 200 characters.\n\n"
            f"Idea: {text}"
        )
        ai_text = generator.generate(prompt, preferred_engine=engine)
        candidate = ai_text.strip() or text
    tweet = _truncate_to_limit(_sanitize_no_emdash(candidate).strip(), config.max_length)
    print(tweet)
    # Generate image from the tweet text
    maker = ImageMaker()
    image_bytes = b""
    # Try AI Horde generation for a custom background
    if ai_image:
        try:
            ai = AIImageClient(config)
            # Build an SDXL-style visual prompt from the tweet via the LLM
            prompt_seed = (
                "Craft a concise SDXL visual prompt (max ~50 tokens) matching this Stoic tweet. "
                "Themes: greek philosopher or greek warrior or modern soldier or battle scene or chess match;"
                " vibe: dark, mysterious, moody lighting; NO embedded text. Return only the prompt.\n\n"
                f"Tweet: {tweet}"
            )
            vis_prompt = generator.generate(prompt_seed, preferred_engine=engine)
            neg = config.horde_negative_prompt or (
                "text, watermark, signature, logo, blurry, lowres, artifacts, deformed, extra fingers, bad anatomy"
            )
            models = [config.horde_model] if config.horde_model else ["SDXL 1.0"]
            bg_bytes = ai.generate(prompt=vis_prompt, width=1024, height=1024, steps=28, negative_prompt=neg, models=models)
            if bg_bytes:
                from PIL import Image
                import io
                bg_img = Image.open(io.BytesIO(bg_bytes)).convert("RGB").resize((1080, 1080))
                image_bytes = maker.compose_quote(tweet, background=bg_img)
        except Exception as e:
            print(f"[ai-image-error] {type(e).__name__}: {e}")
            image_bytes = b""
    # Fallback to free background if AI image not available
    if not image_bytes:
        try:
            image_bytes = maker.compose_quote(tweet)
        except Exception as e:
            print(f"[image-error] {type(e).__name__}: {e}")
            image_bytes = b""
    if use_dry_run:
        print("[dry-run] Skipping post.")
        return
    if image_bytes:
        tweet_id = twitter.upload_media_and_post(tweet, image_bytes=image_bytes, filename="stoic.jpg")
    else:
        tweet_id = twitter.post_tweet(tweet)
    if tweet_id:
        print(f"Posted tweet id: {tweet_id}")
    else:
        print("[skip] No post (rate-limited or error).")


@app.command("post-auto-image")
def post_auto_image(
    dry_run: Optional[bool] = typer.Option(
        None,
        "--dry-run/--no-dry-run",
        help="If set, overrides config default to skip posting or force posting.",
    ),
    engine: str = typer.Option("auto", help="Choose generation engine for rewriting/prompts", case_sensitive=False),
):
    """Fetch source material, rewrite to a short tweet, generate SDXL image, and post."""
    if engine.lower() not in ENGINE_CHOICES:
        raise typer.BadParameter(f"engine must be one of: {', '.join(ENGINE_CHOICES)}")
    config, generator, twitter = _load_components()
    use_dry_run = config.dry_run_default if dry_run is None else dry_run

    # 0) Ensure quote store exists and ingest APIs if desired (optional external call elsewhere)
    store = QuoteStore()

    # 1) Fetch source (prefer stored quotes; fallback to APIs)
    pick = store.pick_for_post(cooldown_days=14)
    raw = (pick or {}).get("text") if pick else None
    if not raw:
        raw = fetch_quote_rotating()
    if not raw:
        print("[error] No source quote found.")
        return

    # 2) Rewrite short tweet
    rewrite_prompt = (
        "Rewrite into ONE short tweet under 140 chars. "
        "No emojis, no hashtags, no quotes, no attribution, no AI phrasing. "
        "Tone: raw, direct, confident. Themes: masculinity, stoicism, discipline, purpose, self-control.\n\n"
        f"Source: {raw}"
    )
    candidate = generator.generate(rewrite_prompt, preferred_engine=engine)
    tweet = _truncate_to_limit(_sanitize_no_emdash((candidate or "").strip()), config.max_length)
    if not tweet:
        print("[error] Empty rewrite.")
        return

    # 3) Build SDXL prompt via LLM
    vis_prompt = build_sdxl_prompt(generator, tweet, engine)
    if not vis_prompt:
        vis_prompt = "dark moody minimalist stoic poster, greek marble statue, dramatic shadows, no text"

    # 4) Generate image (Stable Horde SDXL)
    ai = AIImageClient(config)
    neg = config.horde_negative_prompt or "text, watermark, signature, logo, blurry, lowres, artifacts, deformed, extra fingers, bad anatomy"
    models = [config.horde_model] if config.horde_model else ["SDXL 1.0"]
    img_bytes = ai.generate(prompt=vis_prompt, width=1024, height=1024, steps=32, negative_prompt=neg, models=models)

    # 5) Fallback to local composition if needed
    maker = ImageMaker()
    if not img_bytes:
        img_bytes = maker.compose_duotone_text(tweet)
    # Light upscale/sharpen
    img_bytes = maker.upscale_bytes(img_bytes, max_side=1400, sharpen=True)

    print(tweet)
    if use_dry_run:
        print("[dry-run] Skipping post.")
        return

    if img_bytes:
        tweet_id = twitter.upload_media_and_post(tweet, image_bytes=img_bytes, filename="auto.jpg")
    else:
        tweet_id = twitter.post_tweet(tweet)
    # Mark posted if we used a stored quote
    if tweet_id and pick:
        store.mark_posted(pick)
    if tweet_id:
        print(f"Posted tweet id: {tweet_id}")
    else:
        print("[skip] No post (rate-limited or error).")


@app.command("ingest-csv")
def ingest_csv(
    path: str = typer.Argument(..., help="Path to CSV with one quote per line"),
    source: Optional[str] = typer.Option(None, help="Source label for these quotes"),
):
    store = QuoteStore()
    result = store.ingest_csv_file(path, source=source)
    print(f"added={result['added']} duplicates={result['duplicates']}")


@app.command("ingest-apis")
def ingest_apis(
    count: int = typer.Option(10, help="How many quotes to fetch from APIs"),
):
    store = QuoteStore()
    quotes = []
    for _ in range(count):
        q = fetch_quote_rotating()
        if q:
            quotes.append(q)
    result = store.ingest_quotes(quotes, source="apis")
    print(f"added={result['added']} duplicates={result['duplicates']}")


@app.command("post-quote-image")
def post_quote_image(
    dry_run: Optional[bool] = typer.Option(
        None,
        "--dry-run/--no-dry-run",
        help="If set, overrides config default to skip posting or force posting.",
    ),
):
    """Post a quote from the CSV store with image; no AI rewriting."""
    config, _generator, twitter = _load_components()
    use_dry_run = config.dry_run_default if dry_run is None else dry_run
    store = QuoteStore()
    pick = store.pick_for_post(cooldown_days=14)
    if not pick:
        print(f"[error] No eligible quotes in store. Ingest CSV or APIs first. count={store.count()}")
        return
    text = (pick.get("text") or "").strip()
    author = (pick.get("author") or "").strip()
    tweet = f"{text} --- {author}" if author else text
    tweet = _truncate_to_limit(_sanitize_no_emdash(tweet), config.max_length)
    if not tweet:
        print("[error] Empty quote text.")
        return
    print(tweet)
    # Build image prompt purely from content
    vis_prompt = build_sdxl_prompt(None, tweet, "fallback")  # templates only
    ai = AIImageClient(config)
    neg = config.horde_negative_prompt or "text, watermark, signature, logo, blurry, lowres, artifacts, deformed, extra fingers, bad anatomy"
    models = [config.horde_model] if config.horde_model else ["SDXL 1.0"]
    img_bytes = ai.generate(prompt=vis_prompt, width=1024, height=1024, steps=32, negative_prompt=neg, models=models)
    # Fallback duotone
    maker = ImageMaker()
    if not img_bytes:
        img_bytes = maker.compose_duotone_text(tweet)
    img_bytes = maker.upscale_bytes(img_bytes, max_side=1400, sharpen=True)
    if use_dry_run:
        print("[dry-run] Skipping post.")
        return
    tweet_id = twitter.upload_media_and_post(tweet, image_bytes=img_bytes, filename="quote.jpg") if img_bytes else twitter.post_tweet(tweet)
    if tweet_id:
        store.mark_posted(pick)
        print(f"Posted tweet id: {tweet_id}")
    else:
        print("[skip] No post (rate-limited or error).")

def run():
	app()


if __name__ == "__main__":
	run()
