from __future__ import annotations

import sys
from typing import Optional
import os
import json
import random

import typer

from .config import AppConfig
from .generator import ContentGenerator
from .twitter_client import TwitterClient
from filelock import FileLock


def _author_slug(raw: str) -> str:
    s = (raw or "").strip().lower()
    if not s:
        return "unknown"
    # normalize separators
    s = s.replace("—", "-").replace("–", "-")
    import re
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "unknown"


def _classify_author(author: str) -> tuple[str, Optional[str]]:
    """Return (category, subfolder) for an author.

    Categories:
    - celebrities: flat (no subfolder)
    - stoic: subfolder per key figure (marcus-aurelius, seneca, epictetus, socrates, plato, aristotle)
    - philosophy: subfolder per key figure (carl-jung, nietzsche, confucius, lao-tzu, etc.)
    - religion: subfolder per tradition (buddha, christianity, zen, japanese, chinese)
    """
    a = (author or "").strip().lower()
    s = _author_slug(a)
    # Religion first
    if "buddha" in a or s in {"gautama-buddha"}:
        return ("religion", "buddha")
    if any(k in a for k in ["christ", "bible", "new testament", "old testament"]):
        return ("religion", "christianity")
    if "zen" in a:
        return ("religion", "zen")
    if "japanese proverb" in a or "japanese" in a:
        return ("religion", "japanese")
    if "chinese proverb" in a or "chinese" in a:
        return ("religion", "chinese")

    # Stoic and classical philosophers (as requested under stoic)
    stoics = {
        "marcus-aurelius",
        "seneca",
        "lucius-annaeus-seneca",
        "epictetus",
        "socrates",
        "plato",
        "aristotle",
    }
    if s in stoics:
        return ("stoic", s)

    # Philosophy bucket
    philosophers = {
        "carl-jung",
        "friedrich-nietzsche",
        "nietzsche",
        "confucius",
        "lao-tzu",
        "laozi",
        "heraclitus",
        "protagoras",
        "descartes",
        "ren-descartes",
    }
    if s in philosophers:
        return ("philosophy", s)

    # Default to celebrities (flat)
    return ("celebrities", None)


_AUTHOR_IMAGE_CACHE: dict[str, list[str]] = {}


def _pick_author_image(author: str) -> Optional[bytes]:
    # Prefer new category structure
    try:
        category, sub = _classify_author(author)
        if category == "celebrities":
            base = os.path.join("assets", "celebrities", "images")
        elif category in {"stoic", "philosophy"}:
            base = os.path.join("assets", category, (sub or "misc"), "images")
        elif category == "religion":
            base = os.path.join("assets", "religion", (sub or "misc"), "images")
        else:
            base = os.path.join("assets", "celebrities", "images")
        if not os.path.isdir(base):
            # Backward-compat to old per-author layout
            slug = _author_slug(author)
            legacy = os.path.join("assets", "authors", slug, "images")
            base = legacy if os.path.isdir(legacy) else os.path.join("assets", "celebrities", "images")
        files = _AUTHOR_IMAGE_CACHE.get(base)
        if files is None:
            files = []
            for name in os.listdir(base):
                p = os.path.join(base, name)
                if os.path.isfile(p) and name.lower().endswith((".jpg", ".jpeg", ".png")):
                    files.append(p)
            _AUTHOR_IMAGE_CACHE[base] = files
        if not files:
            return None
        path = random.choice(files)
        with open(path, "rb") as f:
            return f.read()
    except Exception:
        return None

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


# Legacy state (kept for compatibility of recent cache only)
def _cycle_state_path() -> str:
    return os.getenv("CYCLE_STATE_PATH", "post_cycle_state.json")


def _read_cycle_index() -> int:
    path = _cycle_state_path()
    try:
        lock = FileLock(path + ".lock")
        with lock, open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            idx = int(data.get("index", 0))
            return max(0, idx)
    except Exception:
        return 0


def _write_cycle_index(idx: int) -> None:
    path = _cycle_state_path()
    try:
        lock = FileLock(path + ".lock")
        with lock, open(path, "w", encoding="utf-8") as f:
            json.dump({"index": max(0, int(idx))}, f)
    except Exception:
        pass


ENGAGEMENT_QUESTIONS = []


# Recent LLM posts cache to avoid duplicate tweets
def _recent_posts_path() -> str:
    return os.getenv("RECENT_POSTS_PATH", "recent_posts.json")


def _thread_state_path() -> str:
    return os.getenv("THREAD_STATE_PATH", "thread_state.json")


def _read_recent_posts() -> list[str]:
    path = _recent_posts_path()
    try:
        lock = FileLock(path + ".lock")
        with lock, open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return [str(x) for x in data][-200:]
    except Exception:
        pass
    return []


def _write_recent_posts(items: list[str]) -> None:
    path = _recent_posts_path()
    try:
        lock = FileLock(path + ".lock")
        with lock, open(path, "w", encoding="utf-8") as f:
            json.dump(items[-200:], f)
    except Exception:
        pass


def _read_post_counter() -> int:
    path = _thread_state_path()
    try:
        lock = FileLock(path + ".lock")
        with lock, open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return int(data.get("since_last_thread", 0))
    except Exception:
        return 0


def _write_post_counter(val: int) -> None:
    path = _thread_state_path()
    try:
        lock = FileLock(path + ".lock")
        with lock, open(path, "w", encoding="utf-8") as f:
            json.dump({"since_last_thread": max(0, int(val))}, f)
    except Exception:
        pass


def _post_with_media_or_text(twitter: TwitterClient, text: str, image_bytes: Optional[bytes], filename: str) -> Optional[str]:
	if image_bytes:
		return twitter.upload_media_and_post(text, image_bytes=image_bytes, filename=filename)
	return twitter.post_tweet(text)


# removed generic generate; use generate-fact instead


# removed generic post; use post-fact instead


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


@app.command("generate-fact")
def generate_fact(
    subject: Optional[str] = typer.Argument(None, help="Optional subject for the fact"),
    max_length: Optional[int] = typer.Option(None, help="Override max length for this run"),
    engine: str = typer.Option("auto", help="Choose generation engine", case_sensitive=False),
):
    """Generate a single 'Did you know ...' fact and print to stdout."""
    if engine.lower() not in ENGINE_CHOICES:
        raise typer.BadParameter(f"engine must be one of: {', '.join(ENGINE_CHOICES)}")
    config, generator, _ = _load_components()
    if max_length is not None:
        config.max_length = max_length
    prompt = subject.strip() if subject else "Make up any interesting fact."
    text = generator.generate(prompt, preferred_engine=engine)
    print(_truncate_to_limit(_sanitize_no_emdash(text), config.max_length))


@app.command("post-fact")
def post_fact(
    dry_run: Optional[bool] = typer.Option(
        None,
        "--dry-run/--no-dry-run",
        help="If set, overrides config default to skip posting or force posting.",
    ),
    engine: str = typer.Option("auto", help="Choose generation engine", case_sensitive=False),
    subject: Optional[str] = typer.Argument(None, help="Optional subject for the fact"),
):
    """Generate and post a 'Did you know ...' fact."""
    if engine.lower() not in ENGINE_CHOICES:
        raise typer.BadParameter(f"engine must be one of: {', '.join(ENGINE_CHOICES)}")
    config, generator, twitter = _load_components()
    use_dry_run = config.dry_run_default if dry_run is None else dry_run
    base = subject.strip() if subject else "Make up any interesting fact."
    text = generator.generate(base, preferred_engine=engine)
    tweet = _truncate_to_limit(_sanitize_no_emdash((text or '').strip()), config.max_length)
    print(tweet)
    if use_dry_run:
        print("[dry-run] Skipping post.")
        return
    tweet_id = twitter.post_tweet(tweet)
    if tweet_id:
        print(f"Posted tweet id: {tweet_id}")
        # Update recent cache
        cache = _read_recent_posts()
        cache.append(tweet)
        _write_recent_posts(cache)
        # Increment post counter and trigger thread every 15 posts
        count = _read_post_counter() + 1
        if count >= 15:
            facts: list[str] = []
            seen = set(cache[-500:])
            for _ in range(50):  # up to 50 attempts to gather 10 unique facts
                cand = generator.generate("Make up any interesting fact.", preferred_engine=engine)
                cand = _truncate_to_limit(_sanitize_no_emdash((cand or '').strip()), config.max_length)
                if cand and cand not in seen:
                    facts.append(cand)
                    seen.add(cand)
                if len(facts) == 10:
                    break
            if facts:
                head = "10 interesting things you didn’t know until now:"
                thread_texts = [head] + [f"{i+1}. {t}" for i, t in enumerate(facts)]
                ids = twitter.post_thread(thread_texts)
                if ids:
                    print(f"Posted thread with {len(ids)} tweets")
            count_after = 0
        else:
            count_after = count
        _write_post_counter(count_after)
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
    """Deprecated in fact-only mode."""
    print("This command has been removed. Use 'post-fact' instead.")


@app.command("post-auto-image")
def post_auto_image(
    dry_run: Optional[bool] = typer.Option(
        None,
        "--dry-run/--no-dry-run",
        help="If set, overrides config default to skip posting or force posting.",
    ),
    engine: str = typer.Option("auto", help="Choose generation engine for rewriting/prompts", case_sensitive=False),
):
    """Deprecated in fact-only mode."""
    print("This command has been removed. Use 'post-fact' instead.")


@app.command("ingest-csv")
def ingest_csv(
    path: str = typer.Argument(..., help="Path to CSV with one quote per line"),
    source: Optional[str] = typer.Option(None, help="Source label for these quotes"),
):
    print("This command has been removed. Not applicable in fact-only mode.")


@app.command("ingest-apis")
def ingest_apis(
    count: int = typer.Option(10, help="How many quotes to fetch from APIs"),
):
    print("This command has been removed. Not applicable in fact-only mode.")


@app.command("post-quote-image")
def post_quote_image(
    dry_run: Optional[bool] = typer.Option(
        None,
        "--dry-run/--no-dry-run",
        help="If set, overrides config default to skip posting or force posting.",
    ),
):
    """Deprecated in fact-only mode."""
    print("This command has been removed. Use 'post-fact' instead.")


@app.command("post-quote-text")
def post_quote_text(
    dry_run: Optional[bool] = typer.Option(
        None,
        "--dry-run/--no-dry-run",
        help="If set, overrides config default to skip posting or force posting.",
    ),
):
    """Deprecated in fact-only mode."""
    print("This command has been removed. Use 'post-fact' instead.")


@app.command("init-authors-folders")
def init_authors_folders():
    print("This command has been removed. Not applicable in fact-only mode.")


@app.command("post-cycle")
def post_cycle(
    prompt: str = typer.Argument(..., help="Prompt seed for text tweets (guides the generator)"),
    dry_run: Optional[bool] = typer.Option(
        None,
        "--dry-run/--no-dry-run",
        help="If set, overrides config default to skip posting or force posting.",
    ),
    engine: str = typer.Option("auto", help="Choose generation engine", case_sensitive=False),
):
    """Deprecated in fact-only mode."""
    print("This command has been removed. Use 'post-fact' instead.")


@app.command("post-engage-image")
def post_engage_image(
    dry_run: Optional[bool] = typer.Option(
        None,
        "--dry-run/--no-dry-run",
        help="If set, overrides config default to skip posting or force posting.",
    ),
):
    """Deprecated in fact-only mode."""
    print("This command has been removed. Use 'post-fact' instead.")


def run():
	app()


if __name__ == "__main__":
	run()
