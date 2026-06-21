from __future__ import annotations

import json
import os
import time
import urllib.request
from pathlib import Path

from .common import ProviderResult, image_data_uri


OPENAI_VIDEO_COST_CENTS = 0
OPENAI_VIDEO_MODEL_DEFAULT = "sora-2"
OPENAI_VIDEO_SECONDS = {4, 8, 12}
OPENAI_VIDEO_RESOLUTIONS = {"720p": "1280x720"}


def _api_base() -> str:
    return os.environ.get("GODOGEN_OPENAI_API_BASE", "https://api.openai.com/v1").rstrip("/")


def _video_url(video_id: str | None = None, suffix: str = "") -> str:
    base = f"{_api_base()}/videos"
    if video_id:
        base = f"{base}/{video_id}"
    return f"{base}{suffix}"


def build_create_request(args) -> dict:
    if args.duration not in OPENAI_VIDEO_SECONDS:
        raise ValueError("OpenAI video duration must be one of: 4, 8, 12 seconds")
    if args.resolution not in OPENAI_VIDEO_RESOLUTIONS:
        raise ValueError("OpenAI video currently supports 720p through this wrapper")

    payload = {
        "model": os.environ.get("GODOGEN_OPENAI_VIDEO_MODEL", OPENAI_VIDEO_MODEL_DEFAULT),
        "prompt": args.prompt,
        "seconds": str(args.duration),
        "size": OPENAI_VIDEO_RESOLUTIONS[args.resolution],
        "input_reference": {"image_url": image_data_uri(Path(args.image))},
    }
    return {
        "url": _video_url(),
        "poll_url": _video_url("{video_id}"),
        "download_url": _video_url("{video_id}", "/content"),
        "payload": payload,
    }


def _authorized_request(url: str, api_key: str, *, method: str = "GET", body: bytes | None = None):
    headers = {"Authorization": f"Bearer {api_key}"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    return urllib.request.Request(url, data=body, method=method, headers=headers)


def _post_json(url: str, payload: dict, api_key: str) -> dict:
    body = json.dumps(payload).encode("utf-8")
    request = _authorized_request(url, api_key, method="POST", body=body)
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.loads(response.read().decode("utf-8"))


def _get_json(url: str, api_key: str) -> dict:
    request = _authorized_request(url, api_key)
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def _download_video(url: str, api_key: str, output: Path) -> None:
    request = _authorized_request(url, api_key)
    with urllib.request.urlopen(request, timeout=300) as response:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(response.read())


def _error_message(video: dict) -> str:
    error = video.get("error")
    if isinstance(error, dict):
        message = error.get("message")
        code = error.get("code")
        if message and code:
            return f"{code}: {message}"
        if message:
            return str(message)
    return "OpenAI video generation failed"


def generate_video(args, output: Path) -> ProviderResult:
    request_info = build_create_request(args)

    if args.dry_run:
        return ProviderResult(
            True,
            path=str(output),
            cost_cents=OPENAI_VIDEO_COST_CENTS,
            provider="openai",
            extra={"dry_run": True, "request": request_info},
        )

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return ProviderResult(False, error="OPENAI_API_KEY is required for --provider openai", provider="openai")

    video = _post_json(request_info["url"], request_info["payload"], api_key)
    video_id = video.get("id")
    if not isinstance(video_id, str) or not video_id:
        return ProviderResult(False, error="OpenAI video response did not include a video id", provider="openai")

    deadline = time.monotonic() + max(0, args.poll)
    while video.get("status") in {"queued", "in_progress"} and time.monotonic() < deadline:
        time.sleep(1)
        video = _get_json(_video_url(video_id), api_key)

    status = video.get("status")
    if status == "completed":
        _download_video(_video_url(video_id, "/content"), api_key, output)
        return ProviderResult(True, path=str(output), cost_cents=OPENAI_VIDEO_COST_CENTS, provider="openai")

    if status == "failed":
        return ProviderResult(
            False,
            cost_cents=OPENAI_VIDEO_COST_CENTS,
            error=_error_message(video),
            provider="openai",
            extra={"video_id": video_id, "status": status},
        )

    return ProviderResult(
        False,
        cost_cents=OPENAI_VIDEO_COST_CENTS,
        error=(
            "OpenAI video task is pending; no MP4 was available before --poll expired. "
            f"Retrieve later with: GET {_video_url(video_id)} and download {_video_url(video_id, '/content')}"
        ),
        provider="openai",
        extra={"pending": True, "video_id": video_id, "status": status},
    )
