from __future__ import annotations

import io
from pathlib import Path

from .common import ProviderResult, mime_for_image


GEMINI_MODEL = "gemini-3.1-flash-image-preview"
GEMINI_SIZES = ["512", "1K", "2K", "4K"]
GEMINI_COSTS = {"512": 5, "1K": 7, "2K": 10, "4K": 15}
GEMINI_ASPECT_RATIOS = [
    "1:1", "1:4", "1:8", "2:3", "3:2", "3:4", "4:1", "4:3",
    "4:5", "5:4", "8:1", "9:16", "16:9", "21:9",
]


def generate_image(args, output: Path, cost: int) -> ProviderResult:
    from google import genai
    from google.genai import types
    from PIL import Image

    config = types.GenerateContentConfig(
        response_modalities=["IMAGE"],
        image_config=types.ImageConfig(
            image_size=args.size,
            aspect_ratio=args.aspect_ratio,
        ),
    )

    contents = []
    if args.image:
        ref_path = Path(args.image)
        if not ref_path.exists():
            return ProviderResult(False, error=f"Reference image not found: {ref_path}", provider="gemini")
        contents.append(types.Part.from_bytes(data=ref_path.read_bytes(), mime_type=mime_for_image(ref_path)))
    contents.append(args.prompt)

    client = genai.Client()
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=contents,
        config=config,
    )

    if response.parts is None:
        reason = "unknown"
        if response.candidates and response.candidates[0].finish_reason:
            reason = response.candidates[0].finish_reason
        return ProviderResult(False, error=f"Generation blocked (reason: {reason})", provider="gemini")

    for part in response.parts:
        if part.inline_data is not None:
            output.parent.mkdir(parents=True, exist_ok=True)
            image = Image.open(io.BytesIO(part.inline_data.data))
            image.save(output, format="PNG")
            return ProviderResult(True, path=str(output), cost_cents=cost, provider="gemini")

    return ProviderResult(False, error="No image returned", provider="gemini")
