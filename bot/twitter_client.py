from __future__ import annotations

from typing import Optional
import time

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

	def _compute_retry_delay_seconds(self, exc: Exception, attempt_index: int) -> int:
		# If Tweepy exposes response headers, try to honor reset
		try:
			resp = getattr(exc, "response", None)
			if resp is not None:
				# x-rate-limit-reset is epoch seconds when limit resets
				reset = resp.headers.get("x-rate-limit-reset") or resp.headers.get("X-Rate-Limit-Reset")
				if reset:
					try:
						reset_epoch = int(float(reset))
						now_epoch = int(time.time())
						wait = max(0, reset_epoch - now_epoch) + 2
						return min(wait, 600)
					except Exception:
						pass
		except Exception:
			pass
		# Exponential backoff fallback (capped)
		return min(30 * (attempt_index + 1), 180)

	def post_tweet(self, text: str, dry_run: bool = False) -> Optional[str]:
		# Safety: never attempt to post empty/whitespace text
		if text is None or not str(text).strip():
			print("[error] Empty tweet text; skipping post.")
			return None
		if dry_run:
			return None
		client = self._build_client()
		last_error: Optional[Exception] = None
		for attempt in range(3):
			try:
				resp = client.create_tweet(text=text)
				# resp.data example: { 'id': '...', 'text': '...' }
				if hasattr(resp, "data") and isinstance(resp.data, dict):
					return resp.data.get("id")
				return None
			except tweepy.TooManyRequests as e:
				# Gather diagnostics
				status = None
				remaining = None
				reset = None
				try:
					if getattr(e, "response", None) is not None:
						status = e.response.status_code
						remaining = e.response.headers.get("x-rate-limit-remaining")
						reset = e.response.headers.get("x-rate-limit-reset")
				except Exception:
					pass
				delay = self._compute_retry_delay_seconds(e, attempt)
				print(f"[rate-limit] HTTP {status or '429'} remaining={remaining} reset={reset} waiting {delay}s (attempt {attempt+1}/3)")
				time.sleep(delay)
				last_error = e
				continue
			except Exception as e:
				# Log details if available (e.g., duplicate content or forbidden)
				code = None
				try:
					if getattr(e, "response", None) is not None:
						code = e.response.status_code
				except Exception:
					pass
				print(f"[twitter-error] {type(e).__name__} status={code}: {e}")
				last_error = e
				break
		if isinstance(last_error, tweepy.TooManyRequests):
			print("[rate-limit] Exhausted retries due to Twitter rate limit; giving up for now.")
		return None
