from __future__ import annotations

from typing import Optional, Tuple

import requests
import random


class StoicClient:
	"""Simple client to fetch Stoic quotes from a public API."""

	def __init__(self, timeout_seconds: int = 10):
		self.timeout_seconds = max(1, int(timeout_seconds))

	def fetch_quote(self) -> Optional[Tuple[str, Optional[str]]]:
		"""Fetch a Stoic quote.

		Returns (text, author) where author may be None if unavailable.
		Tries multiple public endpoints; falls back to a small local list if all fail.
		"""
		endpoints = [
			# stoic-api on Vercel: { text, author }
			("https://stoic-api.vercel.app/api/quote", self._parse_vercel),
			# themotivate365: { author, quote }
			("https://api.themotivate365.com/stoic-quote", self._parse_motivate365),
		]
		for url, parser in endpoints:
			try:
				resp = requests.get(url, timeout=self.timeout_seconds)
				resp.raise_for_status()
				data = resp.json() if resp.content else None
				parsed = parser(data)
				if parsed is not None:
					text, author = parsed
					if text and str(text).strip():
						return str(text).strip(), (str(author).strip() if author else None)
			except Exception:
				# try next endpoint
				pass
		# Local fallback list to avoid hard failure
		fallbacks: list[Tuple[str, str]] = [
			("You have power over your mind—not outside events. Realize this, and you will find strength.", "Marcus Aurelius"),
			("We suffer more often in imagination than in reality.", "Seneca"),
			("Man is disturbed not by things, but by the views he takes of them.", "Epictetus"),
			("Waste no more time arguing what a good man should be. Be one.", "Marcus Aurelius"),
			("No man is free who is not master of himself.", "Epictetus"),
		]
		text, author = random.choice(fallbacks)
		return text, author

	def _parse_vercel(self, data: object) -> Optional[Tuple[str, Optional[str]]]:
		if not isinstance(data, dict):
			return None
		text = data.get("text") or data.get("quote") or data.get("message")
		author = data.get("author")
		if not text:
			return None
		return str(text), (str(author) if author else None)

	def _parse_motivate365(self, data: object) -> Optional[Tuple[str, Optional[str]]]:
		if not isinstance(data, dict):
			return None
		text = data.get("quote") or data.get("text")
		author = data.get("author")
		if not text:
			return None
		return str(text), (str(author) if author else None)


