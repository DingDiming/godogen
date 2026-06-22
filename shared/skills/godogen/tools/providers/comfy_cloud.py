from __future__ import annotations

from pathlib import Path

from .common import ProviderResult
from .comfy_profiles import load_profile


BASE_URL = "https://cloud.comfy.org"


def build_dry_run_request(profile_id: str, args) -> dict:
    profile = load_profile(profile_id)
    return {
        "method": "POST",
        "url": f"{BASE_URL}/api/prompt",
        "json": {
            "prompt": {
                "_profile": profile["id"],
                "_workflow": profile["workflow"],
                "_inputs": {
                    "prompt": args.prompt,
                    "image": getattr(args, "image", None),
                    "duration": getattr(args, "duration", None),
                    "resolution": getattr(args, "resolution", None),
                },
            }
        },
    }


def generate_image(args, output: Path, task_type: str = "image") -> ProviderResult:
    profile_id = args.workflow
    if not profile_id:
        return ProviderResult(False, error="--workflow is required for --provider comfy-cloud", provider="comfy-cloud")
    if getattr(args, "dry_run", False):
        return ProviderResult(
            True,
            path=str(output),
            cost_cents=0,
            provider="comfy-cloud",
            extra={
                "dry_run": True,
                "profile": profile_id,
                "task_type": task_type,
                "request": build_dry_run_request(profile_id, args),
            },
        )
    return ProviderResult(False, error="Comfy Cloud real submission is not implemented yet", provider="comfy-cloud")


def generate_video(args, output: Path) -> ProviderResult:
    return generate_image(args, output, task_type="video")
