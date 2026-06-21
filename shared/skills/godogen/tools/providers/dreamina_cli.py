from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path

from .common import ProviderResult


DREAMINA_IMAGE_COST_CENTS = 0
DREAMINA_VIDEO_COST_CENTS = 0
DREAMINA_RATIOS = ["21:9", "16:9", "3:2", "4:3", "1:1", "3:4", "2:3", "9:16"]


def _dreamina_bin() -> str:
    override = os.environ.get("GODOGEN_DREAMINA_BIN")
    if override:
        return override
    local = Path("/Users/ddm/.local/bin/dreamina")
    if local.exists():
        return str(local)
    return "dreamina"


def _display_command(command: list[str]) -> list[str]:
    if Path(command[0]).name == "dreamina":
        return ["dreamina", *command[1:]]
    return command


def build_image2video_command(args) -> list[str]:
    return [
        _dreamina_bin(),
        "image2video",
        f"--image={args.image}",
        f"--prompt={args.prompt}",
        f"--duration={args.duration}",
        f"--video_resolution={args.resolution}",
        f"--poll={args.poll}",
    ]


def _resolution_type(size: str, image_to_image: bool) -> str:
    if image_to_image and size in {"512", "1K"}:
        return "2k"
    return {
        "512": "1k",
        "1K": "1k",
        "2K": "2k",
        "4K": "4k",
    }[size]


def build_text2image_command(args) -> list[str]:
    return [
        _dreamina_bin(),
        "text2image",
        f"--prompt={args.prompt}",
        f"--ratio={args.aspect_ratio}",
        f"--resolution_type={_resolution_type(args.size, image_to_image=False)}",
        f"--poll={args.poll}",
    ]


def build_image2image_command(args) -> list[str]:
    return [
        _dreamina_bin(),
        "image2image",
        f"--images={args.image}",
        f"--prompt={args.prompt}",
        f"--ratio={args.aspect_ratio}",
        f"--resolution_type={_resolution_type(args.size, image_to_image=True)}",
        f"--poll={args.poll}",
    ]


def _extract_json_objects(text: str) -> list[dict]:
    objects = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("{") or not line.endswith("}"):
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            objects.append(parsed)
    return objects


def _find_submit_id(text: str) -> str | None:
    for parsed in _extract_json_objects(text):
        for key in ("submit_id", "submitId", "id"):
            value = parsed.get(key)
            if isinstance(value, str) and value:
                return value
    match = re.search(r"submit[_-]?id[\"'=:\s]+([A-Za-z0-9_.:-]+)", text, re.IGNORECASE)
    return match.group(1) if match else None


def _find_media_candidates(text: str, suffix: str) -> list[str]:
    candidates = []
    for parsed in _extract_json_objects(text):
        stack = [parsed]
        while stack:
            item = stack.pop()
            if isinstance(item, dict):
                stack.extend(item.values())
            elif isinstance(item, list):
                stack.extend(item)
            elif isinstance(item, str) and suffix in item.lower():
                candidates.append(item)
    candidates.extend(re.findall(r"(https?://\S+?%s)(?:[\s\"']|$)" % re.escape(suffix), text, re.IGNORECASE))
    candidates.extend(re.findall(r"((?:/|\.{1,2}/|[A-Za-z]:\\)[^\s\"']+?%s)(?:[\s\"']|$)" % re.escape(suffix), text, re.IGNORECASE))
    return candidates


def _find_image_candidates(text: str) -> list[str]:
    candidates = []
    for suffix in (".png", ".jpg", ".jpeg", ".webp"):
        candidates.extend(_find_media_candidates(text, suffix))
    return candidates


def _copy_or_download(candidate: str, output: Path) -> bool:
    output.parent.mkdir(parents=True, exist_ok=True)
    if candidate.startswith(("http://", "https://")):
        with urllib.request.urlopen(candidate, timeout=120) as response:
            output.write_bytes(response.read())
        return True

    source = Path(candidate).expanduser()
    if source.exists():
        shutil.copyfile(source, output)
        return True
    return False


def _pending_result(media_label: str, submit_id: str, output: Path, cost_cents: int) -> ProviderResult:
    return ProviderResult(
        False,
        cost_cents=cost_cents,
        error=(
            f"Dreamina task is pending; no {media_label} was available before --poll expired. "
            f"Query later with: dreamina query_result --submit_id={submit_id} --download_dir={output.parent}"
        ),
        provider="dreamina",
        extra={"pending": True, "submit_id": submit_id},
    )


def _failure_result(action: str, returncode: int, cost_cents: int) -> ProviderResult:
    return ProviderResult(
        False,
        cost_cents=cost_cents,
        error=f"Dreamina {action} failed with exit {returncode}; raw CLI output was suppressed.",
        provider="dreamina",
    )


def generate_video(args, output: Path) -> ProviderResult:
    command = build_image2video_command(args)
    display_command = _display_command(command)
    if args.dry_run:
        return ProviderResult(
            True,
            path=str(output),
            cost_cents=DREAMINA_VIDEO_COST_CENTS,
            provider="dreamina",
            extra={"dry_run": True, "command": display_command},
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="godogen-dreamina.") as tmp:
        completed = subprocess.run(
            command,
            cwd=tmp,
            text=True,
            capture_output=True,
            check=False,
        )

        combined = f"{completed.stdout}\n{completed.stderr}"
        submit_id = _find_submit_id(combined)
        if completed.returncode != 0:
            if submit_id:
                return _pending_result("MP4", submit_id, output, DREAMINA_VIDEO_COST_CENTS)
            return _failure_result("image2video", completed.returncode, DREAMINA_VIDEO_COST_CENTS)

        if output.exists():
            return ProviderResult(True, path=str(output), cost_cents=DREAMINA_VIDEO_COST_CENTS, provider="dreamina")

        for path in Path(tmp).rglob("*.mp4"):
            shutil.copyfile(path, output)
            return ProviderResult(True, path=str(output), cost_cents=DREAMINA_VIDEO_COST_CENTS, provider="dreamina")

        for candidate in _find_media_candidates(combined, ".mp4"):
            if _copy_or_download(candidate, output):
                return ProviderResult(True, path=str(output), cost_cents=DREAMINA_VIDEO_COST_CENTS, provider="dreamina")

        if submit_id:
            return _pending_result("MP4", submit_id, output, DREAMINA_VIDEO_COST_CENTS)

    return ProviderResult(
        False,
        cost_cents=DREAMINA_VIDEO_COST_CENTS,
        error="Dreamina completed without an MP4 path or submit_id; no output was written.",
        provider="dreamina",
    )


def generate_image(args, output: Path) -> ProviderResult:
    if args.aspect_ratio not in DREAMINA_RATIOS:
        return ProviderResult(
            False,
            error=f"Dreamina does not support aspect ratio {args.aspect_ratio}. Use: {', '.join(DREAMINA_RATIOS)}",
            provider="dreamina",
        )
    if args.image and not Path(args.image).exists():
        return ProviderResult(False, error=f"Reference image not found: {args.image}", provider="dreamina")

    command = build_image2image_command(args) if args.image else build_text2image_command(args)
    display_command = _display_command(command)
    if args.dry_run:
        return ProviderResult(
            True,
            path=str(output),
            cost_cents=DREAMINA_IMAGE_COST_CENTS,
            provider="dreamina",
            extra={"dry_run": True, "command": display_command},
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="godogen-dreamina.") as tmp:
        completed = subprocess.run(
            command,
            cwd=tmp,
            text=True,
            capture_output=True,
            check=False,
        )

        combined = f"{completed.stdout}\n{completed.stderr}"
        submit_id = _find_submit_id(combined)
        if completed.returncode != 0:
            if submit_id:
                return _pending_result("image", submit_id, output, DREAMINA_IMAGE_COST_CENTS)
            return _failure_result("image generation", completed.returncode, DREAMINA_IMAGE_COST_CENTS)

        if output.exists():
            return ProviderResult(True, path=str(output), cost_cents=DREAMINA_IMAGE_COST_CENTS, provider="dreamina")

        for path in Path(tmp).rglob("*"):
            if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
                _copy_or_download(str(path), output)
                return ProviderResult(True, path=str(output), cost_cents=DREAMINA_IMAGE_COST_CENTS, provider="dreamina")

        for candidate in _find_image_candidates(combined):
            if _copy_or_download(candidate, output):
                return ProviderResult(True, path=str(output), cost_cents=DREAMINA_IMAGE_COST_CENTS, provider="dreamina")

        if submit_id:
            return _pending_result("image", submit_id, output, DREAMINA_IMAGE_COST_CENTS)

    return ProviderResult(
        False,
        cost_cents=DREAMINA_IMAGE_COST_CENTS,
        error="Dreamina completed without an image path or submit_id; no output was written.",
        provider="dreamina",
    )
