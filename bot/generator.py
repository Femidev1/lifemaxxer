from __future__ import annotations

from typing import Optional

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
			self._openai_client = OpenAI(
				api_key=self.config.provider_api_key,
				base_url=self.config.provider_base_url,
			)
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
			return self._truncate(text or self._fallback(prompt))
		if engine == "ollama":
			text = self._try_ollama(prompt)
			return self._truncate(text or self._fallback(prompt))
		if engine == "hf":
			text = self._try_hf(prompt)
			return self._truncate(text or self._fallback(prompt))
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
			"You are a social media copywriter. Write a single high-quality tweet "
			"under 240 characters, clear, actionable, no hashtags, no emojis."
		)

	def _try_provider(self, prompt: str) -> Optional[str]:
		self._ensure_provider()
		if not self._openai_client or not self.config.provider_model:
			return None
		try:
			resp = self._openai_client.chat.completions.create(
				model=self.config.provider_model,
				messages=[
					{"role": "system", "content": self._tweet_system_prompt()},
					{"role": "user", "content": prompt.strip()},
				],
				temperature=0.7,
				max_tokens=max(60, min(200, self.config.max_length)),
			)
			choice = resp.choices[0].message.content if resp and resp.choices else None
			return choice.strip() if choice else None
		except Exception:
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
		return f"{prompt.strip()} — Sharing a quick thought for the day."

	def _truncate(self, text: str) -> str:
		# X currently supports 280 chars for standard accounts; allow a small buffer.
		limit = min(max(self.config.max_length, 1), 275)
		return text[:limit]
