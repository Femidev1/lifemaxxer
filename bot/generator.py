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
			return self._truncate(self._format_fact_out(text or ""))
		if engine == "ollama":
			text = self._try_ollama(prompt)
			return self._truncate(self._format_fact_out(text or ""))
		if engine == "hf":
			text = self._try_hf(prompt)
			return self._truncate(self._format_fact_out(text or ""))
		if engine == "fallback":
			return self._truncate(self._fallback(prompt))

		# auto: try hosted provider → ollama → hf → fallback
		text = self._try_provider(prompt)
		if text:
			return self._truncate(self._format_fact_out(text))
		text = self._try_ollama(prompt)
		if text:
			return self._truncate(self._format_fact_out(text))
		text = self._try_hf(prompt)
		if text:
			return self._truncate(self._format_fact_out(text))
		return self._truncate(self._fallback(prompt))

	def _fact_system_prompt(self) -> str:
		return (
			"You generate a single interesting fact in one sentence. "
			"The output MUST begin with 'Did you know ' and end with a period or a question mark. "
			"Keep it under 240 characters. No hashtags. No emojis. No lists. No quotes. "
			"Use plain ASCII punctuation and simple wording suitable for a tweet. "
			"If a subject is provided, make the fact about that subject; otherwise pick any topic."
		)

	def _try_provider(self, prompt: str) -> Optional[str]:
		self._ensure_provider()
		if not self._openai_client or not self.config.provider_model:
			return None
		for attempt in range(5):
			try:
				resp = self._openai_client.chat.completions.create(
					model=self.config.provider_model,
					messages=[
						{"role": "system", "content": self._fact_system_prompt()},
						{"role": "user", "content": prompt.strip()},
					],
					temperature=0.7,
					max_tokens=max(60, min(200, self.config.max_length)),
					stream=False,
				)
				# Non-streaming response path
				text = ""
				if hasattr(resp, "choices") and resp.choices:
					msg = resp.choices[0].message
					parts = []
					try:
						val = getattr(msg, "content", None)
						if val:
							parts.append(val)
					except Exception:
						pass
					try:
						val = getattr(msg, "reasoning", None)
						if val:
							parts.append(val)
					except Exception:
						pass
					text = " ".join(parts).strip()
				elif hasattr(resp, "__iter__") and not isinstance(resp, (str, bytes)):
					# Streaming chunks path
					chunks = []
					for chunk in resp:
						try:
							d = chunk.choices[0].delta
							val = getattr(d, "content", None) or getattr(d, "reasoning", None) or ""
							chunks.append(val)
						except Exception:
							pass
					text = ("".join(chunks)).strip()
				if text:
					return text
				else:
					print("[provider-empty] Received no content/reasoning text")
			except Exception as e:
				print(f"[provider-fail attempt {attempt+1}/5] {type(e).__name__}: {e}")
				# exponential backoff with jitter
				delay = (2 ** attempt) * 0.75
				time.sleep(delay)
		return None

	def _try_ollama(self, prompt: str) -> Optional[str]:
		self._ensure_ollama()
		if not self._ollama_client:
			return None
		# Prefer chat API
		try:
			# Add sampling options for variety and a changing seed
			opts = {
				"temperature": 0.95,
				"top_p": 0.92,
				"repeat_penalty": 1.1,
				"seed": int(time.time() * 1000) % 2_147_483_647,
			}
			chat = self._ollama_client.chat(
				model=self.config.ollama_model,
				messages=[
					{"role": "system", "content": self._fact_system_prompt()},
					{"role": "user", "content": prompt.strip()},
				],
				options=opts,
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
					self._fact_system_prompt()
					+ "\n\nUser: "
					+ prompt.strip()
					+ "\nAssistant:"
				),
				options={
					"temperature": 0.95,
					"top_p": 0.92,
					"repeat_penalty": 1.1,
					"seed": int(time.time() * 1000) % 2_147_483_647,
				},
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
				f"{self._fact_system_prompt()}\nUser: {prompt.strip()}\nAssistant:",
				return_full_text=False,
				truncation=True,
				max_new_tokens=min(160, max(40, self.config.max_length)),
				do_sample=True,
				temperature=0.9,
				top_p=0.92,
				num_return_sequences=1,
			)
			if not outputs:
				return None
			text = outputs[0].get("generated_text") or outputs[0].get("generated_texts")
			return str(text).strip() if text else None
		except Exception:
			return None

	def _fallback(self, prompt: str) -> str:
		# Heuristic fallback: simple did-you-know facts
		try:
			import random
			facts = [
				"Did you know octopuses have three hearts?",
				"Did you know honey never spoils? Archaeologists found edible honey in ancient tombs.",
				"Did you know bananas are berries but strawberries aren’t?",
				"Did you know the Eiffel Tower can be 15 cm taller in summer due to heat expansion?",
				"Did you know a day on Venus is longer than its year?",
			]
			return facts[random.randrange(len(facts))][: self.config.max_length]
		except Exception:
			return "Did you know sharks existed before trees?"

	def _format_fact_out(self, text: str) -> str:
		"""Normalize any raw model output to a single-line 'Did you know ...' fact."""
		if not text:
			return ""
		clean = text.strip()
		# Remove any leading system/prompt echoes
		marker = "Assistant:"
		if marker in clean:
			clean = clean.split(marker, 1)[1].strip()
		# Drop surrounding quotes/backticks
		if (clean.startswith("\"") and clean.endswith("\"")) or (clean.startswith("'") and clean.endswith("'")):
			clean = clean[1:-1].strip()
		if (clean.startswith("`") and clean.endswith("`")):
			clean = clean[1:-1].strip()
		# Ensure prefix
		prefix = "Did you know "
		lc = clean.lower()
		if not lc.startswith("did you know "):
			clean = prefix + clean.lstrip("-•* ")
		# Ensure ending punctuation
		if not clean.endswith((".", "?")):
			clean = clean.rstrip() + "."
		return clean

	def _truncate(self, text: str) -> str:
		# X currently supports 280 chars for standard accounts; allow a small buffer.
		limit = min(max(self.config.max_length, 1), 275)
		return text[:limit]
