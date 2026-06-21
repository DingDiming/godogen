from __future__ import annotations

import base64
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ProviderResult:
    ok: bool
    path: str | None = None
    cost_cents: int = 0
    error: str | None = None
    provider: str | None = None
    extra: dict = field(default_factory=dict)


def mime_for_image(path: Path) -> str:
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }.get(path.suffix.lower(), "image/png")


def image_data_uri(image_path: Path) -> str:
    b64 = base64.b64encode(image_path.read_bytes()).decode()
    return f"data:{mime_for_image(image_path)};base64,{b64}"


def size_to_pixels(size: str) -> int:
    return {
        "512": 512,
        "1K": 1024,
        "2K": 2048,
        "4K": 4096,
    }[size]


def dimensions_for(size: str, aspect_ratio: str) -> tuple[int, int]:
    base = size_to_pixels(size)
    if ":" not in aspect_ratio:
        return base, base
    width_ratio, height_ratio = aspect_ratio.split(":", 1)
    width_value = float(width_ratio)
    height_value = float(height_ratio)
    if width_value >= height_value:
        return base, max(1, round(base * height_value / width_value))
    return max(1, round(base * width_value / height_value)), base
