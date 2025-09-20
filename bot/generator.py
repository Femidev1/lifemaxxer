from __future__ import annotations

from typing import Optional
import time
import os

from .config import AppConfig


class ContentGenerator:
	def __init__(self, config: AppConfig):
		self.config = config
		self._ollama_client = None
		self._hf_pipeline = None
		self._openai_client = None

	def _ensure_provider(self):
		if self._openai_client is not None:
			return
		if not self.config.provider_api_key or not self.config.provider_base_url or not self.config.provider_model:
			self._openai_client = None
			return
		try:
			from openai import OpenAI  # type: ignore
			kwargs = {
				"api_key": self.config.provider_api_key,
				"base_url": self.config.provider_base_url,
			}
			# OpenRouter prefers referer/title headers for free usage
			if "openrouter.ai" in (self.config.provider_base_url or ""):
				kwargs["default_headers"] = {
					"HTTP-Referer": os.getenv("OPENROUTER_REFERER", "https://github.com/Femidev1/lifemaxxer"),
					"X-Title": os.getenv("OPENROUTER_TITLE", "Lifemaxxer Bot"),
				}
			self._openai_client = OpenAI(**kwargs)
		except Exception:
			self._openai_client = None

	def _ensure_ollama(self):
		if self._ollama_client is not None:
			return
		try:
			import ollama  # type: ignore
			self._ollama_client = ollama
		except Exception:
			self._ollama_client = None

	def _ensure_hf(self):
		if self._hf_pipeline is not None:
			return
		try:
			from transformers import pipeline  # type: ignore
			model_name = self.config.hf_model or "gpt2"
			self._hf_pipeline = pipeline("text-generation", model=model_name)
		except Exception:
			self._hf_pipeline = None

	def generate(self, prompt: str, preferred_engine: str = "auto") -> str:
		engine = (preferred_engine or "auto").strip().lower()
		if engine == "provider":
			text = self._try_provider(prompt)
			return self._truncate(text or "")
		if engine == "ollama":
			text = self._try_ollama(prompt)
			return self._truncate(text or "")
		if engine == "hf":
			text = self._try_hf(prompt)
			return self._truncate(text or "")
		if engine == "fallback":
			return self._truncate(self._fallback(prompt))

		# auto: try hosted provider → ollama → hf → fallback
		text = self._try_provider(prompt)
		if text:
			return self._truncate(text)
		text = self._try_ollama(prompt)
		if text:
			return self._truncate(text)
		text = self._try_hf(prompt)
		if text:
			return self._truncate(text)
		return self._truncate(self._fallback(prompt))

	def _tweet_system_prompt(self) -> str:
		return (
			"You are a social media copywriter for a blunt, red‑pill style account. "
			"Write ONE tweet under 240 characters. Tone: raw, direct, confident, no fluff. "
			"Profanity is allowed (e.g., fuck, shit, damn) but ABSOLUTELY NO hate speech, slurs, threats, or demeaning groups. "
			"Themes: masculinity, women & dating dynamics, purpose, goals, growth, discipline. "
			"Offer a punchy truth or imperative. No hashtags, no emojis, no disclaimers, no quotes from you about being an AI."
		)

	def _try_provider(self, prompt: str) -> Optional[str]:
		self._ensure_provider()
		if not self._openai_client or not self.config.provider_model:
			return None
		for attempt in range(3):
			try:
				resp = self._openai_client.chat.completions.create(
					model=self.config.provider_model,
					messages=[
						{"role": "system", "content": self._tweet_system_prompt()},
						{"role": "user", "content": prompt.strip()},
					],
					temperature=0.7,
					max_tokens=max(60, min(200, self.config.max_length)),
					stream=False,
				)
				# Some providers may still stream; handle both
				text = ""
				if hasattr(resp, "choices") and resp.choices:
					choice = resp.choices[0].message.content
					text = (choice or "").strip()
				elif hasattr(resp, "__iter__") and not isinstance(resp, (str, bytes)):
					chunks = []
					for chunk in resp:
						try:
							delta = chunk.choices[0].delta.content or ""
							chunks.append(delta)
						except Exception:
							pass
					text = ("".join(chunks)).strip()
				if text:
					return text
			except Exception as e:
				print(f"[provider-fail attempt {attempt+1}/3] {type(e).__name__}: {e}")
				# tiny backoff
				time.sleep(1.0 + 0.5 * attempt)
		return None

	def _try_ollama(self, prompt: str) -> Optional[str]:
		self._ensure_ollama()
		if not self._ollama_client:
			return None
		# Prefer chat API
		try:
			chat = self._ollama_client.chat(
				model=self.config.ollama_model,
				messages=[
					{"role": "system", "content": self._tweet_system_prompt()},
					{"role": "user", "content": prompt.strip()},
				],
			)
			# Support object or dict response
			content = None
			if hasattr(chat, "message") and hasattr(chat.message, "content"):
				content = chat.message.content
			elif isinstance(chat, dict):
				msg = chat.get("message")
				if isinstance(msg, dict):
					content = msg.get("content")
			if content:
				return str(content).strip()
		except Exception:
			pass
		# Fallback to generate API
		try:
			res = self._ollama_client.generate(
				model=self.config.ollama_model,
				prompt=(
					self._tweet_system_prompt()
					+ "\n\nUser: "
					+ prompt.strip()
					+ "\nAssistant:"
				),
				stream=False,
			)
			text = None
			if hasattr(res, "response"):
				text = res.response
			elif isinstance(res, dict):
				text = res.get("response")
			return str(text).strip() if text else None
		except Exception:
			return None

	def _try_hf(self, prompt: str) -> Optional[str]:
		self._ensure_hf()
		if not self._hf_pipeline:
			return None
		try:
			outputs = self._hf_pipeline(
				f"{self._tweet_system_prompt()}\nUser: {prompt.strip()}\nAssistant:",
				max_length=max(40, self.config.max_length),
				num_return_sequences=1,
			)
			if not outputs:
				return None
			text = outputs[0].get("generated_text")
			return text.strip() if text else None
		except Exception:
			return None

	def _fallback(self, prompt: str) -> str:
		# Heuristic, never echo raw prompt. Build a short motivational line.
		try:
			import random
			themes = [
				("discipline", [
					"Discipline is choosing what you want most over what you want now.",
					"Small reps, every day. That's how momentum is built.",
					"Consistency beats intensity when the dust settles.",
				]),
				("masculinity", [
					"Lead yourself first: responsibility, courage, restraint.",
					"Strength without respect is weakness wearing armor.",
					"Be the man who chooses character when no one is watching.",
				]),
				("women", [
					"Respect her by respecting yourself: clear standards, steady actions.",
					"Listen, lead with kindness, and keep your word.",
					"Admire, don’t idolize; respect, don’t control.",
				]),
				("purpose", [
					"Build your day around your purpose, not your impulses.",
					"Aim at something worth failing for, then get to work.",
					"Purpose turns pain into fuel; use it.",
				]),
			]
			# bias theme by prompt keywords
			p = prompt.lower()
			weights = []
			for key, lines in themes:
				w = 2 if key in p else 1
				weights.append(w)
			idx = random.choices(range(len(themes)), weights=weights, k=1)[0]
			line = random.choice(themes[idx][1])
			return line[: self.config.max_length]
		except Exception:
			return "Keep going. One honest step today beats perfect tomorrow."

	def _truncate(self, text: str) -> str:
		# X currently supports 280 chars for standard accounts; allow a small buffer.
		limit = min(max(self.config.max_length, 1), 275)
		return text[:limit]
