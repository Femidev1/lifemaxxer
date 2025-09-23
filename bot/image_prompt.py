from __future__ import annotations

import random
from typing import Tuple

from .generator import ContentGenerator


POSTER_TMPL = (
	"{subject}, minimalist, cinematic poster, strong silhouette, rim light, desaturated, "
	"high contrast, centered subject, wide negative space, clean background, subtle light rays, SDXL quality, sharp focus"
)

GRITTY_TMPL = (
	"{subject}, cinematic photography, moody, natural film grain, shallow depth of field, early morning side light, "
	"high dynamic range, 35mm, f/1.8, SDXL quality, sharp focus"
)

MONO_TMPL = (
	"{subject}, minimalist brutalist black and white, bold geometry, high contrast, clean shapes, SDXL quality, razor sharp"
)


def _choose_style_and_subject(tweet: str) -> Tuple[str, str]:
	lc = tweet.lower()
	gritty_keys = ["discipline", "grind", "gym", "dawn", "workout", "sweat", "soldier", "battle"]
	poster_keys = ["stoic", "silence", "restraint", "patience", "calm", "philosopher", "statue"]
	gritty_subjects = [
		"lone figure atop a ridge at dawn",
		"empty gym lit by a single window",
		"boots on a gravel road at sunrise",
	]
	poster_subjects = [
		"greek marble statue in dramatic shadow",
		"warrior silhouette under moody sky",
		"philosopher bust with rim light",
	]
	mono_subjects = [
		"shadow cutting across a concrete wall",
		"storm clouds over a calm sea cliff",
		"chessboard with looming knight piece",
	]
	if any(k in lc for k in gritty_keys):
		return "gritty", random.choice(gritty_subjects)
	if any(k in lc for k in poster_keys):
		return "poster", random.choice(poster_subjects)
	return "mono", random.choice(mono_subjects)


def build_style_prompt(tweet: str) -> Tuple[str, str]:
	style, subject = _choose_style_and_subject(tweet)
	if style == "gritty":
		return style, GRITTY_TMPL.format(subject=subject)
	if style == "poster":
		return style, POSTER_TMPL.format(subject=subject)
	return style, MONO_TMPL.format(subject=subject)


def build_sdxl_prompt(generator: ContentGenerator, tweet: str, engine: str) -> str:
	style, base = build_style_prompt(tweet)
	# Keep LLM involvement minimal; we already have a strong template
	return base
