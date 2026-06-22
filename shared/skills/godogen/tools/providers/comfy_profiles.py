from __future__ import annotations

import json
from pathlib import Path


REQUIRED_FIELDS = (
    "id",
    "asset_kind",
    "workflow",
    "inputs",
    "outputs",
    "timeout_seconds",
    "paid",
)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[5]


def profile_dir() -> Path:
    return repo_root() / "comfyui-cloud" / "profiles"


def load_profile(profile_id: str) -> dict:
    path = profile_dir() / f"{profile_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Comfy profile not found: {profile_id}")
    profile = json.loads(path.read_text())
    validate_profile(profile, path)
    return profile


def validate_profile(profile: dict, path: Path) -> None:
    for key in REQUIRED_FIELDS:
        if key not in profile:
            raise ValueError(f"{path}: missing required field {key}")
    if not isinstance(profile["outputs"], list) or not profile["outputs"]:
        raise ValueError(f"{path}: outputs must be a non-empty list")
