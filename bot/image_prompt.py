from __future__ import annotations

from .generator import ContentGenerator


def build_sdxl_prompt(generator: ContentGenerator, tweet: str, engine: str) -> str:
	prompt = (
		"Give ONE concise SDXL image prompt (<=50 tokens). "
		"Match this tweet's idea with ONE of: greek philosopher, greek warrior, modern soldier, battle scene, chess match. "
		"Vibe: dark, mysterious, moody lighting. NO TEXT IN IMAGE. "
		"Return ONLY the prompt, no quotes, no commentary.\n\n"
		f"Tweet: {tweet}"
	)
	return (generator.generate(prompt, preferred_engine=engine) or "").strip()
