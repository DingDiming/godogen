from __future__ import annotations

import io
from pathlib import Path

from .common import ProviderResult, image_data_uri


GROK_IMAGE_MODEL = "grok-imagine-image"
GROK_IMAGE_COST = 2
GROK_SIZES = ["1K", "2K"]
GROK_ASPECT_RATIOS = [
    "1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3",
    "2:1", "1:2", "19.5:9", "9:19.5", "20:9", "9:20", "auto",
]

GROK_VIDEO_MODEL = "grok-imagine-video"
GROK_VIDEO_COST_PER_SEC = 5


def generate_image(args, output: Path, cost: int) -> ProviderResult:
    from PIL import Image
    import xai_sdk

    image_url = None
    if args.image:
        ref_path = Path(args.image)
        if not ref_path.exists():
            return ProviderResult(False, error=f"Reference image not found: {ref_path}", provider="grok")
        image_url = image_data_uri(ref_path)

    client = xai_sdk.Client()
    resp = client.image.sample(
        prompt=args.prompt,
        model=GROK_IMAGE_MODEL,
        image_url=image_url,
        aspect_ratio=args.aspect_ratio,
        resolution=args.size.lower(),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    image = Image.open(io.BytesIO(resp.image))
    image.save(output, format="PNG")
    return ProviderResult(True, path=str(output), cost_cents=cost, provider="grok")


def generate_video(args, output: Path, cost: int) -> ProviderResult:
    import requests
    import xai_sdk

    image_url = image_data_uri(Path(args.image))

    client = xai_sdk.Client()
    resp = client.video.generate(
        prompt=args.prompt,
        model=GROK_VIDEO_MODEL,
        image_url=image_url,
        duration=args.duration,
        aspect_ratio="1:1",
        resolution=args.resolution,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    download = requests.get(resp.url, timeout=120)
    download.raise_for_status()
    output.write_bytes(download.content)
    return ProviderResult(True, path=str(output), cost_cents=cost, provider="grok")
