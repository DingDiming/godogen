from __future__ import annotations

import base64
import json
import os
import urllib.request
from pathlib import Path

from .common import ProviderResult, image_data_uri


OPENAI_IMAGES_URL = "https://api.openai.com/v1/images/generations"
OPENAI_EDITS_URL = "https://api.openai.com/v1/images/edits"
OPENAI_IMAGE_COST_CENTS = 0


def _openai_size(aspect_ratio: str) -> str:
    if aspect_ratio == "1:1":
        return "1024x1024"
    if ":" in aspect_ratio:
        width, height = aspect_ratio.split(":", 1)
        if float(width) < float(height):
            return "1024x1536"
    return "1536x1024"


def build_generation_request(args) -> dict:
    return {
        "url": OPENAI_IMAGES_URL,
        "payload": {
            "model": os.environ.get("GODOGEN_OPENAI_IMAGE_MODEL", "gpt-image-1.5"),
            "prompt": args.prompt,
            "n": 1,
            "size": _openai_size(args.aspect_ratio),
            "output_format": "png",
            "quality": os.environ.get("GODOGEN_OPENAI_IMAGE_QUALITY", "medium"),
        },
    }


def build_edit_request(args) -> dict:
    source = Path(args.image)
    return {
        "url": OPENAI_EDITS_URL,
        "payload": {
            "model": os.environ.get("GODOGEN_OPENAI_IMAGE_MODEL", "gpt-image-1.5"),
            "prompt": args.prompt,
            "n": 1,
            "size": _openai_size(args.aspect_ratio),
            "output_format": "png",
            "quality": os.environ.get("GODOGEN_OPENAI_IMAGE_QUALITY", "medium"),
            "images": [{"image_url": image_data_uri(source)}],
        },
    }


def _write_openai_image(response: dict, output: Path) -> None:
    data = response.get("data")
    if not isinstance(data, list) or not data:
        raise ValueError("OpenAI response did not include image data")

    first = data[0]
    output.parent.mkdir(parents=True, exist_ok=True)

    if first.get("b64_json"):
        output.write_bytes(base64.b64decode(first["b64_json"]))
        return

    if first.get("url"):
        with urllib.request.urlopen(first["url"], timeout=120) as image_response:
            output.write_bytes(image_response.read())
        return

    raise ValueError("OpenAI response did not include b64_json or url")


def generate_image(args, output: Path) -> ProviderResult:
    if args.image:
        source = Path(args.image)
        if not source.exists():
            return ProviderResult(False, error=f"Reference image not found: {source}", provider="openai")
        request_info = build_edit_request(args)
    else:
        request_info = build_generation_request(args)

    if args.dry_run:
        return ProviderResult(
            True,
            path=str(output),
            cost_cents=OPENAI_IMAGE_COST_CENTS,
            provider="openai",
            extra={"dry_run": True, "request": request_info},
        )

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return ProviderResult(False, error="OPENAI_API_KEY is required for --provider openai", provider="openai")

    body = json.dumps(request_info["payload"]).encode("utf-8")
    request = urllib.request.Request(
        request_info["url"],
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        parsed = json.loads(response.read().decode("utf-8"))

    _write_openai_image(parsed, output)
    return ProviderResult(True, path=str(output), cost_cents=OPENAI_IMAGE_COST_CENTS, provider="openai")
