from __future__ import annotations

import os
from typing import Optional

from pydantic import BaseModel
from dotenv import load_dotenv


class AppConfig(BaseModel):
	# Twitter/X credentials
	twitter_api_key: Optional[str] = None
	twitter_api_key_secret: Optional[str] = None
	twitter_access_token: Optional[str] = None
	twitter_access_token_secret: Optional[str] = None
	twitter_bearer_token: Optional[str] = None

	# Hosted provider (OpenAI-compatible)
	provider_api_key: Optional[str] = None
	provider_base_url: Optional[str] = None
	provider_model: Optional[str] = None  # e.g., ollama/llama3.1:8b-instruct via LiteLLM

	# Content generation
	ollama_model: str = "qwen2.5:3b-instruct"
	hf_model: Optional[str] = None
	max_length: int = 220

	# Behavior
	dry_run_default: bool = True
	twitter_wait_on_rate_limit: bool = False

	# Image generation (Stable Horde)
	horde_api_key: Optional[str] = None
	horde_base_url: Optional[str] = None  # default applied in client if None
	horde_model: Optional[str] = None  # e.g., SDXL 1.0, Deliberate, Realistic Vision
	horde_negative_prompt: Optional[str] = None

	# ComfyUI (self-hosted Stable Diffusion)
	comfy_base_url: Optional[str] = None  # e.g., http://127.0.0.1:8188
	comfy_checkpoint: Optional[str] = None  # e.g., sdxl_checkpoint.safetensors
	comfy_timeout_s: int = 60

	@classmethod
	def load(cls) -> "AppConfig":
		# Load .env if present
		load_dotenv(override=False)

		return cls(
			twitter_api_key=os.getenv("TWITTER_API_KEY"),
			twitter_api_key_secret=os.getenv("TWITTER_API_KEY_SECRET"),
			twitter_access_token=os.getenv("TWITTER_ACCESS_TOKEN"),
			twitter_access_token_secret=os.getenv("TWITTER_ACCESS_TOKEN_SECRET"),
			twitter_bearer_token=os.getenv("TWITTER_BEARER_TOKEN"),
			provider_api_key=os.getenv("PROVIDER_API_KEY"),
			provider_base_url=os.getenv("PROVIDER_BASE_URL"),
			provider_model=os.getenv("PROVIDER_MODEL"),
			ollama_model=os.getenv("OLLAMA_MODEL", "qwen2.5:3b-instruct"),
			hf_model=os.getenv("HF_MODEL"),
			max_length=int(os.getenv("MAX_LENGTH", "220")),
			dry_run_default=os.getenv("DRY_RUN_DEFAULT", "true").lower() == "true",
			twitter_wait_on_rate_limit=os.getenv("TWITTER_WAIT_ON_RATE_LIMIT", "false").lower() == "true",
			horde_api_key=os.getenv("HORDE_API_KEY"),
			horde_base_url=os.getenv("HORDE_BASE_URL"),
			horde_model=os.getenv("HORDE_MODEL"),
			horde_negative_prompt=os.getenv("HORDE_NEGATIVE_PROMPT"),
			comfy_base_url=os.getenv("COMFY_BASE_URL"),
			comfy_checkpoint=os.getenv("COMFY_CHECKPOINT"),
			comfy_timeout_s=int(os.getenv("COMFY_TIMEOUT_S", "60")),
		)
