from __future__ import annotations

from typing import Optional

import random
import re
import textwrap
import requests


class QuoteSource:
	def fetch(self) -> Optional[str]:
		raise NotImplementedError


class ZenQuotesSource(QuoteSource):
	def fetch(self) -> Optional[str]:
		try:
			r = requests.get("https://zenquotes.io/api/random", timeout=10)
			r.raise_for_status()
			data = r.json()
			if isinstance(data, list) and data:
				q = data[0].get("q")
				return q.strip() if q else None
		except Exception:
			return None


class WikiSummarySource(QuoteSource):
	PAGES = [
		"Marcus_Aurelius",
		"Seneca_the_Younger",
		"Epictetus",
		"Stoicism",
		"Chess",
		"Spartan_army",
		"Battle",
	]

	def fetch(self) -> Optional[str]:
		try:
			page = random.choice(self.PAGES)
			r = requests.get(f"https://en.wikipedia.org/api/rest_v1/page/summary/{page}", timeout=10)
			r.raise_for_status()
			txt = (r.json().get("extract") or "").strip()
			if not txt:
				return None
			sent = re.split(r"(?<=[.!?])\s+", txt)[0]
			return sent[:240] if sent else None
		except Exception:
			return None


def fetch_quote_rotating() -> Optional[str]:
	sources = [ZenQuotesSource, WikiSummarySource]
	random.shuffle(sources)
	for cls in sources:
		q = cls().fetch()
		if q:
			return q
	return None
