from __future__ import annotations

from typing import Optional, Dict, Any, List

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
		self.comfy_base_url = (config.comfy_base_url or "").rstrip("/")

	def generate(
		self,
		prompt: str,
		width: int = 768,
		height: int = 1024,
		steps: int = 20,
		negative_prompt: Optional[str] = None,
		models: Optional[List[str]] = None,
	) -> Optional[bytes]:
		# Prefer ComfyUI if configured
		if self.comfy_base_url:
			img = self._generate_comfy(prompt, width, height, steps, negative_prompt)
			if img:
				return img
		try:
			job_id = self._submit(prompt, width, height, steps, negative_prompt=negative_prompt, models=models)
			if not job_id:
				return None
			return self._await_and_fetch(job_id)
		except Exception:
			return None

	def _generate_comfy(
		self,
		prompt: str,
		width: int,
		height: int,
		steps: int,
		negative_prompt: Optional[str],
	) -> Optional[bytes]:
		try:
			if not self.comfy_base_url:
				return None
			# Minimal ComfyUI API (queue prompt) expects a graph; here we send a simple SDXL text2img workflow
			# User must have ComfyUI running with SDXL checkpoint name matching config.comfy_checkpoint
			ckpt = self.config.comfy_checkpoint or "sdxl.safetensors"
			graph: Dict[str, Any] = {
				"prompt": {
					"3": {
						"class_type": "CheckpointLoaderSimple",
						"inputs": {"ckpt_name": ckpt},
					},
					"5": {
						"class_type": "KSampler",
						"inputs": {
							"seed": int(time.time() * 1000) % 2_147_483_647,
							"steps": int(steps),
							"cfg": 7.0,
							"sampler_name": "dpmpp_2m_karras",
							"scheduler": "karras",
							"denoise": 1.0,
						},
					},
					"7": {
						"class_type": "CLIPTextEncode",
						"inputs": {"text": prompt},
					},
					"8": {
						"class_type": "CLIPTextEncode",
						"inputs": {"text": negative_prompt or ""},
					},
					"12": {
						"class_type": "EmptyLatentImage",
						"inputs": {"width": int(width), "height": int(height)},
					},
					"20": {
						"class_type": "VAEDecode",
						"inputs": {},
					},
					"25": {
						"class_type": "SaveImage",
						"inputs": {"filename_prefix": "lifemaxxer"},
					},
				},
			}
			r = requests.post(f"{self.comfy_base_url}/prompt", json=graph, timeout=self.config.comfy_timeout_s)
			r.raise_for_status()
			data = r.json()
			# Poll history/images endpoint for result
			hash_id = data.get("prompt_id") or data.get("prompt_hash")
			if not hash_id:
				return None
			for _ in range(self.config.comfy_timeout_s):
				h = requests.get(f"{self.comfy_base_url}/history/{hash_id}", timeout=5)
				if h.status_code == 200:
					jd = h.json()
					# Extract base64 image
					for _, node in jd.items():
						outs = node.get("outputs") or {}
						imgs = outs.get("images") or []
						if imgs:
							img = imgs[0]
							# Comfy stores files; for a stateless call we would need /view endpoint
							img_name = img.get("filename")
							if img_name:
								view = requests.get(f"{self.comfy_base_url}/view?filename={img_name}", timeout=10)
								if view.status_code == 200:
									return view.content
			time.sleep(1)
			return None
		except Exception:
			return None

	def _submit(
		self,
		prompt: str,
		width: int,
		height: int,
		steps: int,
		*,
		negative_prompt: Optional[str] = None,
		models: Optional[List[str]] = None,
	) -> Optional[str]:
		url = f"{self.base_url}/v2/generate/async"
		headers = {"apikey": self.api_key, "accept": "application/json", "content-type": "application/json"}
		body: Dict[str, Any] = {
			"params": {
				"sampler_name": "DPM++ 2M Karras",
				"width": int(width),
				"height": int(height),
				"steps": int(steps),
				"n": 1,
				"cfg_scale": 7,
				"karras": True,
				"clip_skip": 1,
				"post_processing": [],
				"seed": int(time.time() * 1000) % 2_147_483_647,
			},
			"prompt": self._build_prompt(prompt),
			"nsfw": False,
			"censor_nsfw": True,
			"r2": True,
		}
		if negative_prompt:
			body["params"]["negative_prompt"] = negative_prompt
		if models:
			body["models"] = models
		r = requests.post(url, json=body, headers=headers, timeout=20)
		r.raise_for_status()
		data = r.json()
		return data.get("id") if isinstance(data, dict) else None

	def _build_prompt(self, core: str) -> str:
		# Attach model hints and negative prompts for quality
		neg = self.config.horde_negative_prompt or (
			"text, watermark, signature, blurry, lowres, jpeg artifacts, deformed, extra limbs, bad anatomy"
		)
		model = self.config.horde_model or "SDXL 1.0"
		return (
			f"{core}. Minimalist stoic poster, professional graphic design, SDXL quality, clean composition."
			f" Negative prompt: {neg}. Model hint: {model}."
		)

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


