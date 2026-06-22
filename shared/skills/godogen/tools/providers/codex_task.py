"""Codex task queue provider.

This provider does not call an external API. It writes a deterministic task
manifest next to the requested output so Codex automation can pick up,
monitor, and complete the asset generation work.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from .common import ProviderResult

CODEX_TASK_COST_CENTS = 0


def _task_path(output: Path) -> Path:
    return output.with_suffix(output.suffix + ".codex-task.json")


def _base_payload(args, output: Path, task_type: str) -> dict:
    payload = {
        "provider": "codex",
        "task_type": task_type,
        "status": "pending",
        "prompt": args.prompt,
        "target_path": str(output),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "automation": {
            "owner": "codex",
            "instruction": "Generate the requested asset, write it to target_path, then update this manifest status to complete.",
        },
    }
    if getattr(args, "size", None):
        payload["size"] = args.size
    if getattr(args, "aspect_ratio", None):
        payload["aspect_ratio"] = args.aspect_ratio
    if getattr(args, "procedural_kind", None):
        payload["procedural_kind"] = args.procedural_kind
    if getattr(args, "image", None):
        payload["source_image"] = str(args.image)
    if getattr(args, "duration", None) is not None:
        payload["duration"] = args.duration
    if getattr(args, "resolution", None):
        payload["resolution"] = args.resolution
    return payload


def _queue_or_dry_run(args, output: Path, task_type: str) -> ProviderResult:
    task = _base_payload(args, output, task_type)
    task_path = _task_path(output)

    if getattr(args, "dry_run", False):
        return ProviderResult(
            True,
            path=str(output),
            cost_cents=CODEX_TASK_COST_CENTS,
            provider="codex",
            extra={"dry_run": True, "task": task},
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    task_path.write_text(json.dumps(task, indent=2) + "\n")
    return ProviderResult(
        False,
        error=f"Codex task queued; no asset exists yet. Complete task and place output at {output}",
        cost_cents=CODEX_TASK_COST_CENTS,
        provider="codex",
        extra={
            "pending": True,
            "task_path": str(task_path),
            "target_path": str(output),
            "task_type": task_type,
        },
    )


def generate_image(args, output: Path, task_type: str = "image") -> ProviderResult:
    if getattr(args, "image", None) and not Path(args.image).exists():
        return ProviderResult(False, error=f"Reference image not found: {args.image}", provider="codex")
    return _queue_or_dry_run(args, output, task_type)


def generate_video(args, output: Path) -> ProviderResult:
    return _queue_or_dry_run(args, output, "video")
