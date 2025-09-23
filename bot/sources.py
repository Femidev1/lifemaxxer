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


class GutenbergStoicSource(QuoteSource):
	URLS = [
		"https://www.gutenberg.org/cache/epub/2680/pg2680.txt",  # Marcus Aurelius - Meditations
	]

	def fetch(self) -> Optional[str]:
		try:
			url = random.choice(self.URLS)
			r = requests.get(url, timeout=20)
			r.raise_for_status()
			txt = r.text
			paras = [p.strip() for p in txt.split("\n\n") if len(p.strip().split()) > 8]
			if not paras:
				return None
			p = random.choice(paras)
			p = re.sub(r"\s+", " ", p)
			return textwrap.shorten(p, width=260, placeholder="…")
		except Exception:
			return None


def fetch_quote_rotating() -> Optional[str]:
	sources = [ZenQuotesSource, WikiSummarySource, GutenbergStoicSource]
	random.shuffle(sources)
	for cls in sources:
		q = cls().fetch()
		if q:
			return q
	return None
