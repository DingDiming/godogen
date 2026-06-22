from __future__ import annotations

import copy
import json
import os
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .common import ProviderResult
from .common import mime_for_image
from .comfy_outputs import first_output_file, first_text_output
from .comfy_profiles import load_profile, repo_root


DEFAULT_BASE_URL = "http://127.0.0.1:8000"
PENDING_STATES = {"pending", "queued", "running", "in_progress"}
FAILED_STATES = {"failed", "error", "cancelled"}


def base_url() -> str:
    return os.environ.get("COMFY_SERVER_URL", DEFAULT_BASE_URL).rstrip("/")


def account_api_key() -> str:
    return os.environ.get("COMFY_API_KEY") or os.environ.get("COMFY_CLOUD_API_KEY") or ""


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


def _workflow_path(profile: dict) -> Path:
    path = repo_root() / "comfyui-cloud" / profile["workflow"]
    if not path.exists():
        raise FileNotFoundError(f"Comfy workflow not found: {path}")
    return path


def _set_field(workflow: dict, node_id: str, field: str, value) -> None:
    node = workflow[node_id]
    parts = field.split(".")
    if parts[0] == "inputs":
        node.setdefault("inputs", {})
        node["inputs"][".".join(parts[1:])] = value
        return

    target = node
    for part in parts[:-1]:
        target = target.setdefault(part, {})
    target[parts[-1]] = value


def _arg_value(args, input_name: str, binding: dict):
    value = None
    if hasattr(args, input_name):
        value = getattr(args, input_name)
    if value is None:
        value = binding.get("default")
    mapping = binding.get("map")
    if isinstance(mapping, dict) and value in mapping:
        return mapping[value]
    return value


def _build_workflow(profile: dict, args, uploaded_inputs: dict[str, str] | None = None) -> dict:
    uploaded_inputs = uploaded_inputs or {}
    workflow = json.loads(_workflow_path(profile).read_text())
    for input_name, binding in profile.get("inputs", {}).items():
        value = uploaded_inputs.get(input_name)
        if value is None:
            value = _arg_value(args, input_name, binding)
        if value is None:
            continue
        _set_field(workflow, binding["node"], binding["field"], value)
    return workflow


def _request_payload(profile: dict, args, include_key: bool = True, uploaded_inputs: dict[str, str] | None = None) -> dict:
    payload = {
        "prompt": _build_workflow(profile, args, uploaded_inputs=uploaded_inputs),
        "client_id": f"godogen-{uuid.uuid4()}",
    }
    key = account_api_key()
    if include_key and key:
        payload["extra_data"] = {
            "api_key_comfy_org": key,
            "comfy_usage_source": "godogen",
        }
    return payload


def _sanitized_payload(payload: dict) -> dict:
    sanitized = copy.deepcopy(payload)
    extra = sanitized.get("extra_data")
    if isinstance(extra, dict) and extra.get("api_key_comfy_org"):
        extra["api_key_comfy_org"] = "<set>"
    return sanitized


def build_dry_run_request(profile_id: str, args) -> dict:
    profile = load_profile(profile_id)
    payload = _request_payload(profile, args, uploaded_inputs=_resolve_upload_inputs(profile, args, base_url(), dry_run=True))
    return {
        "method": "POST",
        "url": f"{base_url()}/prompt",
        "json": _sanitized_payload(payload),
    }


def upload_image(image_path: Path, endpoint: str) -> str:
    if os.environ.get("GODOGEN_COMFY_FAKE_PROMPT_ID"):
        return os.environ.get("GODOGEN_COMFY_FAKE_UPLOAD_NAME") or image_path.name

    filename = f"godogen_{uuid.uuid4().hex}_{image_path.name}"
    boundary = f"----godogen-comfy-{uuid.uuid4().hex}"
    body = bytearray()

    def add_field(name: str, value: str) -> None:
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        body.extend(str(value).encode())
        body.extend(b"\r\n")

    add_field("type", "input")
    add_field("overwrite", "true")
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(
        (
            f'Content-Disposition: form-data; name="image"; filename="{filename}"\r\n'
            f"Content-Type: {mime_for_image(image_path)}\r\n\r\n"
        ).encode()
    )
    body.extend(image_path.read_bytes())
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode())

    request = urllib.request.Request(
        f"{endpoint}/upload/image",
        data=bytes(body),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        parsed = json.loads(response.read().decode("utf-8"))
    subfolder = parsed.get("subfolder") or ""
    name = parsed.get("name") or filename
    if subfolder:
        return f"{subfolder}/{name}"
    return name


def _resolve_upload_inputs(profile: dict, args, endpoint: str, dry_run: bool) -> dict[str, str]:
    uploaded: dict[str, str] = {}
    for input_name, binding in profile.get("inputs", {}).items():
        if not binding.get("upload"):
            continue
        value = _arg_value(args, input_name, binding)
        if value is None:
            continue
        image_path = Path(value)
        if not image_path.exists():
            raise FileNotFoundError(f"Reference image not found: {image_path}")
        uploaded[input_name] = str(image_path) if dry_run else upload_image(image_path, endpoint)
    return uploaded


def _profile_extensions(profile: dict) -> list[str]:
    extensions: list[str] = []
    for output in profile.get("outputs", []):
        extensions.extend(output.get("extensions", []))
    return extensions


def _profile_outputs_text(profile: dict) -> bool:
    return any(output.get("kind") == "text" for output in profile.get("outputs", []))


def submit_prompt(payload: dict, endpoint: str) -> str:
    fake = os.environ.get("GODOGEN_COMFY_FAKE_PROMPT_ID")
    if fake:
        return fake

    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{endpoint}/prompt",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        parsed = json.loads(response.read().decode("utf-8"))
    return parsed["prompt_id"]


def get_history(prompt_id: str, endpoint: str) -> dict:
    fake_status = os.environ.get("GODOGEN_COMFY_FAKE_STATUS")
    if fake_status:
        if fake_status in PENDING_STATES:
            return {}
        output_text = os.environ.get("GODOGEN_COMFY_FAKE_HISTORY_TEXT", "ok")
        return {
            prompt_id: {
                "outputs": {
                    "2": {
                        "ui": {
                            "text": [output_text],
                        },
                    },
                },
                "status": {
                    "status_str": "success" if fake_status == "completed" else fake_status,
                    "completed": fake_status == "completed",
                },
            }
        }

    with urllib.request.urlopen(f"{endpoint}/history/{prompt_id}", timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def history_status(history: dict, prompt_id: str) -> str:
    item = history.get(prompt_id)
    if not item:
        return "pending"
    status = item.get("status", {})
    status_str = status.get("status_str")
    if status_str == "success" or status.get("completed") is True:
        return "completed"
    if status_str in FAILED_STATES:
        return status_str
    return status_str or "pending"


def download_output(file_info: dict, endpoint: str) -> bytes:
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
    with urllib.request.urlopen(f"{endpoint}/view?{query}", timeout=120) as response:
        return response.read()


def generate_output(args, output: Path, task_type: str) -> ProviderResult:
    profile_id = args.workflow
    if not profile_id:
        return ProviderResult(False, error="--workflow is required for --provider comfy-local", provider="comfy-local")

    profile = load_profile(profile_id)
    request = {
        "method": "POST",
        "url": f"{base_url()}/prompt",
        "json": _sanitized_payload(_request_payload(profile, args, uploaded_inputs=_resolve_upload_inputs(profile, args, base_url(), dry_run=True))),
    }
    if getattr(args, "dry_run", False):
        return ProviderResult(
            True,
            path=str(output),
            cost_cents=0,
            provider="comfy-local",
            extra={
                "dry_run": True,
                "profile": profile_id,
                "task_type": task_type,
                "request": request,
            },
        )

    if profile.get("paid") and not account_api_key():
        return ProviderResult(
            False,
            error="COMFY_API_KEY is required for paid Comfy Partner/API node submission",
            provider="comfy-local",
        )

    endpoint = base_url()
    uploaded_inputs = _resolve_upload_inputs(profile, args, endpoint, dry_run=False)
    prompt_id = submit_prompt(_request_payload(profile, args, uploaded_inputs=uploaded_inputs), endpoint)
    sidecar = write_sidecar(
        output,
        {
            "provider": "comfy-local",
            "profile": profile_id,
            "task_type": task_type,
            "status": "pending",
            "prompt_id": prompt_id,
            "target_path": str(output),
            "endpoint": endpoint,
            "submitted_at": datetime.now(timezone.utc).isoformat(),
            "outputs": [],
            "error": None,
        },
    )
    return ProviderResult(
        False,
        error="Comfy local job submitted; output is pending.",
        provider="comfy-local",
        extra={
            "pending": True,
            "prompt_id": prompt_id,
            "status": "pending",
            "sidecar": str(sidecar),
        },
    )


def generate_image(args, output: Path, task_type: str = "image") -> ProviderResult:
    return generate_output(args, output, task_type)


def generate_video(args, output: Path) -> ProviderResult:
    return generate_output(args, output, "video")


def generate_model3d(args, output: Path) -> ProviderResult:
    return generate_output(args, output, "model3d")


def generate_analyze(args, output: Path) -> ProviderResult:
    return generate_output(args, output, "analyze")


def resume_output(output: Path) -> ProviderResult:
    sidecar = read_sidecar(output)
    prompt_id = sidecar["prompt_id"]
    endpoint = sidecar.get("endpoint") or base_url()
    history = get_history(prompt_id, endpoint)
    status = history_status(history, prompt_id)
    sidecar["status"] = status

    if status in PENDING_STATES:
        write_sidecar(output, sidecar)
        return ProviderResult(
            False,
            error="Comfy local job is still pending.",
            provider="comfy-local",
            extra={
                "pending": True,
                "prompt_id": prompt_id,
                "status": status,
                "sidecar": str(sidecar_path(output)),
            },
        )

    if status in FAILED_STATES:
        sidecar["error"] = sidecar.get("error") or f"Comfy local job {status}"
        write_sidecar(output, sidecar)
        return ProviderResult(False, error=sidecar["error"], provider="comfy-local", extra={"status": status})

    if status != "completed":
        write_sidecar(output, sidecar)
        return ProviderResult(False, error=f"Unknown Comfy local job status: {status}", provider="comfy-local")

    profile = load_profile(sidecar["profile"])
    job = history[prompt_id]
    output.parent.mkdir(parents=True, exist_ok=True)
    if _profile_outputs_text(profile):
        text = first_text_output(job)
        output.write_text(text.rstrip("\n") + "\n")
        output_ref = {"path": str(output), "kind": "text"}
    else:
        file_info = first_output_file(job, _profile_extensions(profile))
        output.write_bytes(download_output(file_info, endpoint))
        output_ref = {"path": str(output), "file": file_info}

    sidecar["status"] = "complete"
    sidecar["outputs"] = [output_ref]
    sidecar["completed_at"] = datetime.now(timezone.utc).isoformat()
    sidecar["error"] = None
    write_sidecar(output, sidecar)
    return ProviderResult(
        True,
        path=str(output),
        cost_cents=0,
        provider="comfy-local",
        extra={
            "prompt_id": prompt_id,
            "status": "complete",
            "sidecar": str(sidecar_path(output)),
        },
    )
