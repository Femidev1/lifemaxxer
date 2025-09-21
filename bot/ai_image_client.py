from __future__ import annotations

from typing import Optional, Dict, Any

import time
import requests

from .config import AppConfig


class AIImageClient:
	"""Free image generation via Stable Horde (AI Horde).

	Docs: https://aihorde.net/api/
	Key is optional; anonymous is allowed but slower.
	"""

	def __init__(self, config: AppConfig):
		self.config = config
		self.base_url = (config.horde_base_url or "https://stablehorde.net/api").rstrip("/")
		self.api_key = config.horde_api_key or "0000000000"  # anonymous

	def generate(self, prompt: str, width: int = 768, height: int = 1024, steps: int = 20) -> Optional[bytes]:
		try:
			job_id = self._submit(prompt, width, height, steps)
			if not job_id:
				return None
			return self._await_and_fetch(job_id)
		except Exception:
			return None

	def _submit(self, prompt: str, width: int, height: int, steps: int) -> Optional[str]:
		url = f"{self.base_url}/v2/generate/async"
		headers = {"apikey": self.api_key, "accept": "application/json", "content-type": "application/json"}
		body: Dict[str, Any] = {
			"params": {
				"sampler_name": "k_euler_a",
				"width": int(width),
				"height": int(height),
				"steps": int(steps),
				"n": 1,
			},
			"prompt": prompt,
			"nsfw": False,
			"censor_nsfw": True,
			"r2": True,
		}
		r = requests.post(url, json=body, headers=headers, timeout=20)
		r.raise_for_status()
		data = r.json()
		return data.get("id") if isinstance(data, dict) else None

	def _await_and_fetch(self, job_id: str) -> Optional[bytes]:
		check_url = f"{self.base_url}/v2/generate/status/{job_id}"
		headers = {"apikey": self.api_key, "accept": "application/json"}
		for _ in range(60):  # up to ~60s
			r = requests.get(check_url, headers=headers, timeout=10)
			if r.status_code == 404:
				return None
			r.raise_for_status()
			data = r.json()
			if isinstance(data, dict) and data.get("done") and data.get("generations"):
				gens = data.get("generations")
				if isinstance(gens, list) and gens:
					item = gens[0]
					img_b64 = item.get("img")
					if img_b64:
						import base64
						return base64.b64decode(img_b64)
			time.sleep(1)
		return None


