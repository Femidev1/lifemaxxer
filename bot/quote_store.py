from __future__ import annotations

from typing import Optional, List, Dict

import csv
import os
import uuid
import random
import re
from datetime import datetime, timezone, timedelta


CSV_HEADER = [
	"id",
	"text",
	"author",
	"source",
	"added_at",
	"last_posted_at",
	"times_posted",
]


def _utc_now_iso() -> str:
	return datetime.now(timezone.utc).isoformat()


def _normalize_text(text: str) -> str:
	# Lowercase, collapse spaces, normalize dashes/quotes
	s = text.strip().lower()
	s = s.replace("—", "-").replace("–", "-")
	s = re.sub(r"\s+", " ", s)
	return s


class QuoteStore:
	def __init__(self, store_path: Optional[str] = None):
		self.store_path = store_path or os.getenv("QUOTES_STORE_PATH", "quotes_master.csv")
		self.records: List[Dict[str, str]] = []
		self._by_norm: Dict[str, Dict[str, str]] = {}
		self._loaded = False

	def _ensure_loaded(self):
		if self._loaded:
			return
		self._loaded = True
		if not os.path.exists(self.store_path):
			# Initialize empty file with header
			with open(self.store_path, "w", newline="", encoding="utf-8") as f:
				writer = csv.writer(f)
				writer.writerow(CSV_HEADER)
			self.records = []
			self._by_norm = {}
			return
		with open(self.store_path, "r", newline="", encoding="utf-8") as f:
			reader = csv.DictReader(f)
			for row in reader:
				if not row.get("text"):
					continue
				# Backward compatibility: older files may not have 'author'
				row.setdefault("author", "")
				self.records.append(row)
				norm = _normalize_text(row["text"])
				self._by_norm[norm] = row

	def _persist(self):
		# Write to a temp file and replace
		tmp_path = self.store_path + ".tmp"
		with open(tmp_path, "w", newline="", encoding="utf-8") as f:
			writer = csv.DictWriter(f, fieldnames=CSV_HEADER)
			writer.writeheader()
			for r in self.records:
				writer.writerow({k: r.get(k, "") for k in CSV_HEADER})
		os.replace(tmp_path, self.store_path)

	def ingest_quote_records(self, records: List[Dict[str, str]], source: str) -> Dict[str, int]:
		self._ensure_loaded()
		added = 0
		dupes = 0
		for rec_in in records:
			q = rec_in.get("text") if isinstance(rec_in, dict) else str(rec_in)
			if not q or not str(q).strip():
				continue
			norm = _normalize_text(str(q))
			if norm in self._by_norm:
				dupes += 1
				continue
			rec = {
				"id": str(uuid.uuid4()),
				"text": str(q).strip(),
				"author": (rec_in.get("author") if isinstance(rec_in, dict) else "") or "",
				"source": source,
				"added_at": _utc_now_iso(),
				"last_posted_at": "",
				"times_posted": "0",
			}
			self.records.append(rec)
			self._by_norm[norm] = rec
			added += 1
		if added:
			self._persist()
		return {"added": added, "duplicates": dupes}

	def ingest_quotes(self, quotes: List[str], source: str) -> Dict[str, int]:
		# Compatibility wrapper for plain text lists
		recs = [{"text": q, "author": ""} for q in quotes]
		return self.ingest_quote_records(recs, source)

	def ingest_csv_file(self, csv_path: str, source: Optional[str] = None) -> Dict[str, int]:
		self._ensure_loaded()
		records: List[Dict[str, str]] = []
		with open(csv_path, "r", newline="", encoding="utf-8") as f:
			# Try DictReader first to support headers like: id,text,author,source
			pos = f.tell()
			peek = f.readline()
			f.seek(pos)
			if "," in (peek or "") and any(h in peek.lower() for h in ["text", "quote"]):
				reader_d = csv.DictReader(f)
				for row in reader_d:
					if not row:
						continue
					t = row.get("text") or row.get("quote")
					if t:
						records.append({"text": str(t), "author": (row.get("author") or "").strip()})
			else:
				reader = csv.reader(f)
				for row in reader:
					if not row:
						continue
					# One-quote-per-line CSVs: take first column as quote text
					records.append({"text": row[0], "author": ""})
		return self.ingest_quote_records(records, source or os.path.basename(csv_path))

	def pick_for_post(self, cooldown_days: int = 14) -> Optional[Dict[str, str]]:
		self._ensure_loaded()
		cutoff = datetime.now(timezone.utc) - timedelta(days=cooldown_days)
		eligible: List[Dict[str, str]] = []
		for r in self.records:
			lp = r.get("last_posted_at") or ""
			if not lp:
				eligible.append(r)
				continue
			try:
				lp_dt = datetime.fromisoformat(lp)
			except Exception:
				eligible.append(r)
				continue
			if lp_dt <= cutoff:
				eligible.append(r)
		if not eligible:
			# Fallback to least recently posted
			if not self.records:
				return None
			sorted_all = sorted(
				self.records,
				key=lambda r: (r.get("last_posted_at") or "9999-12-31T00:00:00Z"),
			)
			return sorted_all[0]
		return random.choice(eligible)

	def mark_posted(self, rec: Dict[str, str]):
		self._ensure_loaded()
		rec["last_posted_at"] = _utc_now_iso()
		try:
			rec["times_posted"] = str(int(rec.get("times_posted", "0")) + 1)
		except Exception:
			rec["times_posted"] = "1"
		self._persist()

	def count(self) -> int:
		self._ensure_loaded()
		return len(self.records)


