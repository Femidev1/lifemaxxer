from __future__ import annotations

from typing import Optional, Tuple

import requests


class StoicClient:
	"""Simple client to fetch Stoic quotes from a public API."""

	def __init__(self, timeout_seconds: int = 10):
		self.timeout_seconds = max(1, int(timeout_seconds))

	def fetch_quote(self) -> Optional[Tuple[str, Optional[str]]]:
		"""Fetch a Stoic quote.

		Returns (text, author) where author may be None if unavailable.
		"""
		url = "https://stoic-api.vercel.app/api/quote"
		try:
			resp = requests.get(url, timeout=self.timeout_seconds)
			resp.raise_for_status()
			data = resp.json() if resp.content else None
			if not isinstance(data, dict):
				return None
			text = data.get("text") or data.get("quote") or data.get("message")
			author = data.get("author")
			if not text or not str(text).strip():
				return None
			return str(text).strip(), (str(author).strip() if author else None)
		except Exception:
			return None


