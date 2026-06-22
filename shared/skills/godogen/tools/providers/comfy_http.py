from __future__ import annotations

import json
import os
import urllib.parse
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


def _get_json(path: str) -> dict:
    request = urllib.request.Request(
        f"{BASE_URL}{path}",
        headers={"X-API-Key": api_key()},
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def get_status(prompt_id: str) -> str:
    fake = os.environ.get("GODOGEN_COMFY_FAKE_STATUS")
    if fake:
        return fake
    parsed = _get_json(f"/api/job/{prompt_id}/status")
    return parsed["status"]


def get_job(prompt_id: str) -> dict:
    fake_status = os.environ.get("GODOGEN_COMFY_FAKE_STATUS")
    if fake_status:
        return {
            "id": prompt_id,
            "status": fake_status,
            "outputs": {
                "9": {
                    "images": [
                        {
                            "filename": "godogen-fake-output.png",
                            "subfolder": "",
                            "type": "output",
                        }
                    ]
                }
            },
        }
    return _get_json(f"/api/jobs/{prompt_id}")


def download_output(file_info: dict) -> bytes:
    fake_hex = os.environ.get("GODOGEN_COMFY_FAKE_OUTPUT_BYTES_HEX")
    if fake_hex:
        return bytes.fromhex(fake_hex)

    query = urllib.parse.urlencode(
        {
            "filename": file_info["filename"],
            "subfolder": file_info.get("subfolder", ""),
            "type": file_info.get("type", "output"),
        }
    )
    request = urllib.request.Request(
        f"{BASE_URL}/api/view?{query}",
        headers={"X-API-Key": api_key()},
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()
