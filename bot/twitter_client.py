from __future__ import annotations

from typing import Optional

import tweepy

from .config import AppConfig


class TwitterClient:
	def __init__(self, config: AppConfig):
		self.config = config
		self._client: Optional[tweepy.Client] = None

	def _build_client(self) -> tweepy.Client:
		if self._client is not None:
			return self._client
		# Prefer v2 Client with user-context credentials
		self._client = tweepy.Client(
			consumer_key=self.config.twitter_api_key,
			consumer_secret=self.config.twitter_api_key_secret,
			access_token=self.config.twitter_access_token,
			access_token_secret=self.config.twitter_access_token_secret,
			bearer_token=self.config.twitter_bearer_token,
			wait_on_rate_limit=self.config.twitter_wait_on_rate_limit,
		)
		return self._client

	def post_tweet(self, text: str, dry_run: bool = False) -> Optional[str]:
		# Safety: never attempt to post empty/whitespace text
		if text is None or not str(text).strip():
			print("[error] Empty tweet text; skipping post.")
			return None
		if dry_run:
			return None
		client = self._build_client()
		try:
			resp = client.create_tweet(text=text)
		except tweepy.TooManyRequests as e:
			print("[rate-limit] Skipping this post due to Twitter rate limit.")
			return None
		except Exception as e:
			print(f"[twitter-error] {type(e).__name__}: {e}")
			return None
		# resp.data example: { 'id': '...', 'text': '...' }
		if hasattr(resp, "data") and isinstance(resp.data, dict):
			return resp.data.get("id")
		return None
