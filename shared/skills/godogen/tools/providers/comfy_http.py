from __future__ import annotations

import json
import os
import urllib.request


BASE_URL = "https://cloud.comfy.org"


def api_key() -> str:
    key = os.environ.get("COMFY_CLOUD_API_KEY")
    if not key:
        raise ValueError("COMFY_CLOUD_API_KEY is required for Comfy Cloud submission")
    return key


def submit_prompt(payload: dict) -> str:
    fake = os.environ.get("GODOGEN_COMFY_FAKE_PROMPT_ID")
    if fake:
        return fake

    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{BASE_URL}/api/prompt",
        data=data,
        headers={
            "X-API-Key": api_key(),
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        parsed = json.loads(response.read().decode("utf-8"))
    return parsed["prompt_id"]
