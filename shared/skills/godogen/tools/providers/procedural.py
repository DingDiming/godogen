from __future__ import annotations

import random
from pathlib import Path

from .common import ProviderResult, dimensions_for


PROCEDURAL_KINDS = ["checker", "flat", "grid", "noise", "tile", "ui_panel", "placeholder_sprite"]


def _palette(prompt: str) -> tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]]:
    text = prompt.lower()
    if "grass" in text or "terrain" in text:
        return (57, 127, 71), (82, 154, 83), (33, 82, 48)
    if "stone" in text or "wall" in text:
        return (112, 117, 124), (151, 154, 160), (68, 74, 82)
    if "water" in text or "ice" in text:
        return (38, 119, 173), (88, 178, 220), (21, 72, 130)
    if "ui" in text or "panel" in text:
        return (36, 43, 56), (70, 83, 103), (183, 198, 221)
    return (64, 96, 160), (96, 144, 204), (28, 36, 56)


def generate_image(args, output: Path) -> ProviderResult:
    from PIL import Image, ImageDraw

    width, height = dimensions_for(args.size, args.aspect_ratio)
    primary, secondary, accent = _palette(args.prompt)
    kind = args.procedural_kind

    if kind == "flat":
        image = Image.new("RGBA", (width, height), primary + (255,))

    elif kind == "noise":
        rng = random.Random(args.prompt)
        pixels = []
        for _ in range(width * height):
            jitter = rng.randint(-28, 28)
            pixels.append(tuple(max(0, min(255, c + jitter)) for c in primary) + (255,))
        image = Image.new("RGBA", (width, height))
        image.putdata(pixels)

    else:
        image = Image.new("RGBA", (width, height), primary + (255,))
        draw = ImageDraw.Draw(image)

        if kind in {"checker", "tile"}:
            step = max(16, min(width, height) // 8)
            for y in range(0, height, step):
                for x in range(0, width, step):
                    fill = secondary if ((x // step) + (y // step)) % 2 == 0 else primary
                    draw.rectangle((x, y, x + step, y + step), fill=fill + (255,))
                    if kind == "tile":
                        draw.rectangle((x, y, x + step, y + step), outline=accent + (180,), width=max(1, step // 16))

        elif kind == "grid":
            step = max(16, min(width, height) // 12)
            for x in range(0, width, step):
                draw.line((x, 0, x, height), fill=secondary + (220,), width=max(1, step // 20))
            for y in range(0, height, step):
                draw.line((0, y, width, y), fill=secondary + (220,), width=max(1, step // 20))

        elif kind == "ui_panel":
            radius = max(6, min(width, height) // 24)
            margin = max(8, min(width, height) // 12)
            draw.rounded_rectangle(
                (margin, margin, width - margin, height - margin),
                radius=radius,
                fill=primary + (255,),
                outline=accent + (255,),
                width=max(2, min(width, height) // 80),
            )
            draw.rectangle((margin * 2, margin * 2, width - margin * 2, margin * 2 + radius), fill=secondary + (255,))

        elif kind == "placeholder_sprite":
            image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            body = (width * 0.28, height * 0.28, width * 0.72, height * 0.78)
            head = (width * 0.36, height * 0.12, width * 0.64, height * 0.40)
            draw.ellipse(head, fill=secondary + (255,), outline=accent + (255,), width=max(2, width // 80))
            draw.rounded_rectangle(body, radius=max(3, width // 24), fill=primary + (255,), outline=accent + (255,), width=max(2, width // 80))

    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, format="PNG")
    return ProviderResult(True, path=str(output), cost_cents=0, provider="procedural")
