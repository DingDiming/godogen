from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from . import comfy_http
from .common import ProviderResult
from .comfy_outputs import first_output_file
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


def sidecar_path(output: Path) -> Path:
    return output.with_suffix(output.suffix + ".comfy.json")


def write_sidecar(output: Path, data: dict) -> Path:
    path = sidecar_path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")
    return path


def read_sidecar(output: Path) -> dict:
    path = sidecar_path(output)
    if not path.exists():
        raise FileNotFoundError(f"Comfy sidecar not found: {path}")
    return json.loads(path.read_text())


def _profile_extensions(profile: dict) -> list[str]:
    extensions: list[str] = []
    for output in profile.get("outputs", []):
        extensions.extend(output.get("extensions", []))
    return extensions


def generate_image(args, output: Path, task_type: str = "image") -> ProviderResult:
    profile_id = args.workflow
    if not profile_id:
        return ProviderResult(False, error="--workflow is required for --provider comfy-cloud", provider="comfy-cloud")
    request = build_dry_run_request(profile_id, args)
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
                "request": request,
            },
        )

    prompt_id = comfy_http.submit_prompt(request["json"])
    sidecar = write_sidecar(
        output,
        {
            "provider": "comfy-cloud",
            "profile": profile_id,
            "task_type": task_type,
            "status": "pending",
            "prompt_id": prompt_id,
            "target_path": str(output),
            "submitted_at": datetime.now(timezone.utc).isoformat(),
            "outputs": [],
            "error": None,
        },
    )
    return ProviderResult(
        False,
        error="Comfy Cloud job submitted; output is pending.",
        provider="comfy-cloud",
        extra={
            "pending": True,
            "prompt_id": prompt_id,
            "status": "pending",
            "sidecar": str(sidecar),
        },
    )


def generate_video(args, output: Path) -> ProviderResult:
    return generate_image(args, output, task_type="video")


def resume_output(output: Path) -> ProviderResult:
    sidecar = read_sidecar(output)
    prompt_id = sidecar["prompt_id"]
    status = comfy_http.get_status(prompt_id)
    sidecar["status"] = status

    if status in {"pending", "waiting_to_dispatch", "in_progress"}:
        write_sidecar(output, sidecar)
        return ProviderResult(
            False,
            error="Comfy Cloud job is still pending.",
            provider="comfy-cloud",
            extra={
                "pending": True,
                "prompt_id": prompt_id,
                "status": status,
                "sidecar": str(sidecar_path(output)),
            },
        )

    if status in {"failed", "error", "cancelled"}:
        sidecar["error"] = sidecar.get("error") or f"Comfy Cloud job {status}"
        write_sidecar(output, sidecar)
        return ProviderResult(False, error=sidecar["error"], provider="comfy-cloud", extra={"status": status})

    if status != "completed":
        write_sidecar(output, sidecar)
        return ProviderResult(False, error=f"Unknown Comfy Cloud job status: {status}", provider="comfy-cloud")

    profile = load_profile(sidecar["profile"])
    job = comfy_http.get_job(prompt_id)
    file_info = first_output_file(job, _profile_extensions(profile))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(comfy_http.download_output(file_info))

    sidecar["status"] = "complete"
    sidecar["outputs"] = [
        {
            "path": str(output),
            "file": file_info,
        }
    ]
    sidecar["completed_at"] = datetime.now(timezone.utc).isoformat()
    sidecar["error"] = None
    write_sidecar(output, sidecar)
    return ProviderResult(
        True,
        path=str(output),
        cost_cents=0,
        provider="comfy-cloud",
        extra={
            "prompt_id": prompt_id,
            "status": "complete",
            "sidecar": str(sidecar_path(output)),
        },
    )
