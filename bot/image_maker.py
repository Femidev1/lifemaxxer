from __future__ import annotations

from typing import Tuple

import io
import random
import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter


class ImageMaker:
	"""Compose a quote over a random free background (Picsum)."""

	def __init__(self, width: int = 1080, height: int = 1350):
		self.width = width
		self.height = height

	def _fetch_background(self) -> Image.Image:
		seed = random.randint(1, 10_000_000)
		url = f"https://picsum.photos/seed/{seed}/{self.width}/{self.height}"
		r = requests.get(url, timeout=10)
		r.raise_for_status()
		img = Image.open(io.BytesIO(r.content)).convert("RGB")
		return img

	def _wrap_text(self, draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> str:
		words = text.split()
		lines = []
		current = []
		for w in words:
			trial = (" ".join(current + [w])).strip()
			w_px, _ = draw.textsize(trial, font=font)
			if w_px <= max_width or not current:
				current.append(w)
			else:
				lines.append(" ".join(current))
				current = [w]
		if current:
			lines.append(" ".join(current))
		return "\n".join(lines)

	def compose_quote(self, text: str) -> bytes:
		# Fetch and soften background
		img = self._fetch_background()
		img = img.filter(ImageFilter.GaussianBlur(radius=2))

		draw = ImageDraw.Draw(img)
		# Choose font; use a default PIL font if truetype not available
		try:
			font = ImageFont.truetype("DejaVuSans.ttf", size=56)
		except Exception:
			font = ImageFont.load_default()

		margin = 80
		box_width = self.width - margin * 2
		# Wrap text
		wrapped = self._wrap_text(draw, text, font, box_width)
		# Draw translucent overlay for readability
		overlay_h = min(self.height - margin * 2, 800)
		overlay_top = (self.height - overlay_h) // 2
		overlay = Image.new("RGBA", (self.width - margin, overlay_h), (0, 0, 0, 90))
		img.paste(overlay, (margin // 2, overlay_top), overlay)

		# Draw text centered
		lines = wrapped.splitlines()
		line_height = draw.textsize("Ag", font=font)[1] + 8
		total_h = line_height * len(lines)
		y = max(overlay_top + (overlay_h - total_h) // 2, margin)
		for line in lines:
			w_px, _ = draw.textsize(line, font=font)
			x = (self.width - w_px) // 2
			draw.text((x, y), line, fill=(255, 255, 255), font=font)
			y += line_height

		# Export JPEG
		buf = io.BytesIO()
		img.save(buf, format="JPEG", quality=92, optimize=True)
		return buf.getvalue()


