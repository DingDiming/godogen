# ComfyUI Cloud / Local Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Comfy provider paths so Godogen can use local ComfyUI plus Comfy account credits/Partner Nodes, and optionally hosted Comfy Cloud API, as the unified model router for image, texture, video, 3D, and workflow-local LLM tasks.

**Architecture:** Codex remains the orchestrator and acceptance owner. ComfyUI becomes the model execution layer through versioned workflow profiles, async job monitoring, output download/text write, and sidecar tracking.

**Tech Stack:** Python 3 standard library, existing `asset_gen.py` provider pattern, local ComfyUI `/prompt` API, optional Comfy Cloud API, exported Comfy API-format workflow JSON, unittest, Bash wrapper checks.

---

## Task 5: Local ComfyUI Partner Node Provider

**Status:** implemented in this phase.

**Files:**
- Create: `shared/skills/godogen/tools/providers/comfy_local.py`
- Modify: `shared/skills/godogen/tools/providers/comfy_outputs.py`
- Modify: `shared/skills/godogen/tools/asset_gen.py`
- Modify: `bin/godogen-ddm`
- Create: `comfyui-cloud/profiles/llm-smoke.json`
- Create: `comfyui-cloud/workflows/llm-smoke.workflow_api.json`
- Test: `tests/test_asset_gen_providers.py`
- Test: `tests/test_godogen_ddm_cli.py`

- [x] Add `comfy-local` provider for local ComfyUI `POST /prompt`, `GET /history/{prompt_id}`, and `GET /view`.
- [x] Add `asset_gen.py analyze --provider comfy-local --workflow llm-smoke`.
- [x] Add a low-cost OpenRouter `llm-smoke` workflow profile for credit/auth smoke testing.
- [x] Require `COMFY_API_KEY` for paid Partner/API node CLI submission; do not assume browser login can be reused by Codex.
- [x] Preserve no-secret sidecars; never write Comfy API keys, account email, signed URLs, or credit balances.
- [x] Extend non-paid `external-smoke` with `comfy-local` dry-run only.
- [x] Verify current local state: logged-in UI visible, Partner/API nodes loaded, direct CLI submission without `COMFY_API_KEY` refuses before paid work.

## File Structure

- Create `shared/skills/godogen/tools/providers/comfy_profiles.py`
  - Load workflow profile JSON from `comfyui-cloud/profiles/`.
  - Validate required fields before cloud submission.

- Create `shared/skills/godogen/tools/providers/comfy_http.py`
  - Submit `POST /api/prompt`.
  - Poll `GET /api/job/{prompt_id}/status`.
  - Fetch job details and output metadata.
  - Download files through `/api/view`.
  - Redact keys and signed URLs from errors.

- Create `shared/skills/godogen/tools/providers/comfy_cloud.py`
  - Provider entrypoint for `image`, `texture`, `video`, later `model3d` and `analyze`.
  - Writes sidecars.
  - Returns Godogen-compatible JSON.

- Modify `shared/skills/godogen/tools/asset_gen.py`
  - Add `comfy-cloud` to image/video providers.
  - Add `--workflow`.
  - Later add `model3d` and `analyze` subcommands after first provider slice is stable.

- Modify `bin/godogen-ddm`
  - `check-env` reports `COMFY_CLOUD_API_KEY=set|unset`.
  - `external-smoke` includes Comfy Cloud dry-run only, no paid submission unless explicit flag is added later.

- Create `comfyui-cloud/profiles/schema.json`
  - Describes profile metadata, inputs, outputs, timeout, paid flag.

- Create placeholder profile docs under `comfyui-cloud/profiles/`
  - First implementation can use profile JSON without real workflow files, then add real exported workflow JSON after Comfy Cloud UI setup.

- Modify `tests/test_asset_gen_providers.py`
  - Unit tests for profile loading, dry-run request building, pending sidecar, completed download mapping, error redaction.

- Modify `tests/test_godogen_ddm_cli.py`
  - `check-env` test for `COMFY_CLOUD_API_KEY`.
  - `external-smoke` dry-run test mentions Comfy Cloud.

## Task 1: Profile Loader

**Files:**
- Create: `shared/skills/godogen/tools/providers/comfy_profiles.py`
- Create: `comfyui-cloud/profiles/schema.json`
- Create: `comfyui-cloud/profiles/ref-image.json`
- Test: `tests/test_asset_gen_providers.py`

- [ ] **Step 1: Write failing profile-load test**

Add this test to `tests/test_asset_gen_providers.py`:

```python
def test_comfy_profile_loader_reads_ref_image_profile(self):
    sys.path.insert(0, str(REPO_ROOT / "shared" / "skills" / "godogen" / "tools"))
    from providers.comfy_profiles import load_profile

    profile = load_profile("ref-image")

    self.assertEqual(profile["id"], "ref-image")
    self.assertEqual(profile["asset_kind"], "image")
    self.assertEqual(profile["workflow"], "workflows/ref-image.workflow_api.json")
    self.assertEqual(profile["inputs"]["prompt"]["node"], "6")
    self.assertEqual(profile["outputs"][0]["kind"], "image")
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
python3 -m unittest tests.test_asset_gen_providers.AssetGenProviderTests.test_comfy_profile_loader_reads_ref_image_profile
```

Expected: fails because `providers.comfy_profiles` does not exist.

- [ ] **Step 3: Add minimal profile files**

Create `comfyui-cloud/profiles/ref-image.json`:

```json
{
  "id": "ref-image",
  "asset_kind": "image",
  "workflow": "workflows/ref-image.workflow_api.json",
  "inputs": {
    "prompt": {"node": "6", "field": "inputs.text"},
    "seed": {"node": "3", "field": "inputs.seed"}
  },
  "outputs": [
    {"node": "9", "kind": "image", "extensions": [".png"]}
  ],
  "timeout_seconds": 600,
  "paid": true
}
```

Create `comfyui-cloud/profiles/schema.json` with the fields above required.

- [ ] **Step 4: Implement profile loader**

Create `shared/skills/godogen/tools/providers/comfy_profiles.py`:

```python
import json
from pathlib import Path


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
    for key in ("id", "asset_kind", "workflow", "inputs", "outputs", "timeout_seconds", "paid"):
        if key not in profile:
            raise ValueError(f"{path}: missing required field {key}")
    if not isinstance(profile["outputs"], list) or not profile["outputs"]:
        raise ValueError(f"{path}: outputs must be a non-empty list")
```

- [ ] **Step 5: Verify test passes**

Run:

```bash
python3 -m unittest tests.test_asset_gen_providers.AssetGenProviderTests.test_comfy_profile_loader_reads_ref_image_profile
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add comfyui-cloud/profiles shared/skills/godogen/tools/providers/comfy_profiles.py tests/test_asset_gen_providers.py
git commit -m "feat(comfy): add workflow profile loader"
```

## Task 2: Cloud Request Dry Run

**Files:**
- Create: `shared/skills/godogen/tools/providers/comfy_cloud.py`
- Modify: `shared/skills/godogen/tools/asset_gen.py`
- Test: `tests/test_asset_gen_providers.py`

- [ ] **Step 1: Write failing dry-run test**

```python
def test_comfy_image_dry_run_builds_cloud_prompt_request(self):
    with tempfile.TemporaryDirectory(prefix="godogen-comfy-dry.") as tmp:
        output = Path(tmp) / "assets" / "img" / "ref.png"
        proc = run_asset_gen([
            "image",
            "--provider",
            "comfy-cloud",
            "--workflow",
            "ref-image",
            "--dry-run",
            "--prompt",
            "top down racing car reference",
            "-o",
            str(output),
        ])

        self.assertEqual(proc.returncode, 0, proc.stderr)
        result = parse_json_stdout(proc)
        self.assertTrue(result["ok"])
        self.assertEqual(result["provider"], "comfy-cloud")
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["path"], str(output))
        self.assertEqual(result["profile"], "ref-image")
        self.assertEqual(result["request"]["method"], "POST")
        self.assertEqual(result["request"]["url"], "https://cloud.comfy.org/api/prompt")
        self.assertIn("prompt", result["request"]["json"])
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
python3 -m unittest tests.test_asset_gen_providers.AssetGenProviderTests.test_comfy_image_dry_run_builds_cloud_prompt_request
```

Expected: FAIL because `comfy-cloud` is not a provider choice.

- [ ] **Step 3: Add CLI provider choice and `--workflow`**

Modify `shared/skills/godogen/tools/asset_gen.py`:

```python
from providers import codex_task, comfy_cloud, dreamina_cli, procedural

IMAGE_PROVIDERS = ["dreamina", "procedural", "codex", "comfy-cloud"]
VIDEO_PROVIDERS = ["dreamina", "codex", "comfy-cloud"]
```

Add `--workflow` to image, texture, and video parsers:

```python
p_img.add_argument("--workflow", default=None, help="Comfy Cloud workflow profile id when --provider comfy-cloud.")
```

- [ ] **Step 4: Implement minimal dry-run provider**

Create `shared/skills/godogen/tools/providers/comfy_cloud.py`:

```python
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
                "request": build_dry_run_request(profile_id, args),
            },
        )
    return ProviderResult(False, error="Comfy Cloud real submission is not implemented yet", provider="comfy-cloud")
```

- [ ] **Step 5: Route image provider**

Modify `_run_image_provider()`:

```python
elif provider == "comfy-cloud":
    _emit_or_exit(comfy_cloud.generate_image(args, output, kind))
```

- [ ] **Step 6: Verify test passes**

Run:

```bash
python3 -m unittest tests.test_asset_gen_providers.AssetGenProviderTests.test_comfy_image_dry_run_builds_cloud_prompt_request
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add shared/skills/godogen/tools/asset_gen.py shared/skills/godogen/tools/providers/comfy_cloud.py tests/test_asset_gen_providers.py
git commit -m "feat(comfy): add cloud provider dry run"
```

## Task 3: Async Sidecar And Pending State

**Files:**
- Create: `shared/skills/godogen/tools/providers/comfy_http.py`
- Modify: `shared/skills/godogen/tools/providers/comfy_cloud.py`
- Test: `tests/test_asset_gen_providers.py`

- [ ] **Step 1: Write failing pending test**

```python
def test_comfy_image_submission_records_pending_sidecar(self):
    with tempfile.TemporaryDirectory(prefix="godogen-comfy-pending.") as tmp:
        fake_http = Path(tmp) / "fake_comfy_http.py"
        output = Path(tmp) / "assets" / "img" / "ref.png"
        proc = run_asset_gen([
            "image",
            "--provider",
            "comfy-cloud",
            "--workflow",
            "ref-image",
            "--prompt",
            "top down racing car reference",
            "-o",
            str(output),
        ], env={
            "COMFY_CLOUD_API_KEY": "comfy-secret-value",
            "GODOGEN_COMFY_FAKE_PROMPT_ID": "prompt-123",
        })

        self.assertEqual(proc.returncode, 1)
        result = parse_json_stdout(proc)
        self.assertFalse(result["ok"])
        self.assertTrue(result["pending"])
        self.assertEqual(result["provider"], "comfy-cloud")
        self.assertEqual(result["prompt_id"], "prompt-123")
        sidecar = Path(result["sidecar"])
        self.assertTrue(sidecar.exists())
        data = json.loads(sidecar.read_text())
        self.assertEqual(data["status"], "pending")
        self.assertEqual(data["prompt_id"], "prompt-123")
        self.assertNotIn("comfy-secret-value", proc.stdout + proc.stderr + sidecar.read_text())
```

- [ ] **Step 2: Run test to verify it fails**

Expected: FAIL because real submission is not implemented.

- [ ] **Step 3: Implement `comfy_http.submit_prompt()`**

Create `shared/skills/godogen/tools/providers/comfy_http.py`:

```python
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
```

- [ ] **Step 4: Implement sidecar write**

In `comfy_cloud.py`, add:

```python
import json
from datetime import datetime, timezone

from . import comfy_http


def sidecar_path(output: Path) -> Path:
    return output.with_suffix(output.suffix + ".comfy.json")


def write_sidecar(output: Path, data: dict) -> Path:
    path = sidecar_path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")
    return path
```

On real submit, write:

```python
prompt_id = comfy_http.submit_prompt(request["json"])
sidecar = write_sidecar(output, {
    "provider": "comfy-cloud",
    "profile": profile_id,
    "status": "pending",
    "prompt_id": prompt_id,
    "target_path": str(output),
    "submitted_at": datetime.now(timezone.utc).isoformat(),
    "outputs": [],
    "error": None,
})
return ProviderResult(False, error="Comfy Cloud job submitted; output is pending.", provider="comfy-cloud", extra={
    "pending": True,
    "prompt_id": prompt_id,
    "status": "pending",
    "sidecar": str(sidecar),
})
```

- [ ] **Step 5: Verify pending test passes**

Run the focused test and confirm PASS.

- [ ] **Step 6: Commit**

```bash
git add shared/skills/godogen/tools/providers/comfy_cloud.py shared/skills/godogen/tools/providers/comfy_http.py tests/test_asset_gen_providers.py
git commit -m "feat(comfy): submit cloud jobs with pending sidecars"
```

## Task 4: Resume/Poll And Download Output

**Files:**
- Modify: `shared/skills/godogen/tools/providers/comfy_http.py`
- Modify: `shared/skills/godogen/tools/providers/comfy_outputs.py`
- Modify: `shared/skills/godogen/tools/providers/comfy_cloud.py`
- Modify: `shared/skills/godogen/tools/asset_gen.py`
- Test: `tests/test_asset_gen_providers.py`

- [ ] **Step 1: Write failing completion test**

Write a test that sets fake environment variables:

```python
env={
    "COMFY_CLOUD_API_KEY": "comfy-secret-value",
    "GODOGEN_COMFY_FAKE_STATUS": "completed",
    "GODOGEN_COMFY_FAKE_OUTPUT_BYTES_HEX": PNG_1X1.hex(),
}
```

Expected JSON:

```json
{"ok": true, "provider": "comfy-cloud", "path": "...", "cost_cents": 0}
```

Expected file header:

```python
self.assertEqual(output.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
```

- [ ] **Step 2: Add polling functions**

Implement:

```python
def get_status(prompt_id: str) -> str:
    ...

def get_job(prompt_id: str) -> dict:
    ...

def download_output(file_info: dict) -> bytes:
    ...
```

Use fake env variables for unit tests so tests never hit Comfy Cloud.

- [ ] **Step 3: Map output metadata to target path**

Create `comfy_outputs.py` with:

```python
def first_output_file(job: dict, expected_extensions: list[str]) -> dict:
    for node_outputs in job.get("outputs", {}).values():
        for key in ("images", "videos", "audio", "models"):
            for item in node_outputs.get(key, []):
                filename = item.get("filename", "")
                if any(filename.endswith(ext) for ext in expected_extensions):
                    return item
    raise ValueError(f"No Comfy output matched extensions: {expected_extensions}")
```

- [ ] **Step 4: Add `--resume` or sidecar-based polling**

Do not overload Tripo `resume`. Add a Comfy-specific path:

```bash
asset_gen.py comfy_resume -o assets/img/ref.png
```

This command reads `assets/img/ref.png.comfy.json`, polls status, downloads output when complete, updates sidecar, and returns success JSON.

- [ ] **Step 5: Verify focused tests pass**

Run:

```bash
python3 -m unittest tests/test_asset_gen_providers.py
```

- [ ] **Step 6: Commit**

```bash
git add shared/skills/godogen/tools/providers/comfy_*.py shared/skills/godogen/tools/asset_gen.py tests/test_asset_gen_providers.py
git commit -m "feat(comfy): resume and download cloud outputs"
```

## Task 5: Wrapper And Smoke Integration

**Files:**
- Modify: `bin/godogen-ddm`
- Modify: `tests/test_godogen_ddm_cli.py`
- Modify: `README.md`
- Modify: `docs/ddm-provider-adapters.md`

- [ ] **Step 1: Write failing check-env test**

Add:

```python
env["COMFY_CLOUD_API_KEY"] = "comfy-secret-value"
...
self.assertIn("COMFY_CLOUD_API_KEY=set", proc.stdout)
self.assertNotIn("comfy-secret-value", proc.stdout)
```

- [ ] **Step 2: Update `check-env`**

Add:

```bash
env_status COMFY_CLOUD_API_KEY
```

- [ ] **Step 3: Update external smoke dry-run**

Add a non-paid dry-run:

```bash
"$SELF" asset image \
  --provider comfy-cloud --workflow ref-image --dry-run \
  --prompt "external smoke cloud image" \
  -o "$comfy_image" >/dev/null
```

Print:

```text
comfy-cloud-image: dry-run <path>
```

- [ ] **Step 4: Verify wrapper tests**

Run:

```bash
python3 -m unittest tests/test_godogen_ddm_cli.py
```

- [ ] **Step 5: Commit**

```bash
git add bin/godogen-ddm tests/test_godogen_ddm_cli.py README.md docs/ddm-provider-adapters.md
git commit -m "feat(cli): surface comfy cloud provider"
```

## Task 6: Real Cloud Smoke Boundary

**Files:**
- Modify: `bin/godogen-ddm`
- Modify: `comfyui-cloud/README.md`
- Modify: `comfyui-cloud/sources.md`
- Test: `tests/test_godogen_ddm_cli.py`

- [ ] **Step 1: Add paid smoke guard test**

Test behavior:

```bash
bin/godogen-ddm external-smoke --yes-charge
```

Expected without key:

```text
COMFY_CLOUD_API_KEY=missing
```

Expected with fake key and fake provider:

```text
comfy-cloud-image: pending
```

- [ ] **Step 2: Implement explicit paid cloud smoke**

Only submit real Comfy Cloud jobs under:

```bash
bin/godogen-ddm external-smoke --yes-charge --include-comfy-cloud
```

This avoids accidentally consuming credits during existing paid Dreamina/Tripo checks.

- [ ] **Step 3: Verify no secret leakage**

Add tests that set:

```bash
COMFY_CLOUD_API_KEY=comfy-secret-value
```

Assert the value never appears in stdout, stderr, sidecars, or output files.

- [ ] **Step 4: Commit**

```bash
git add bin/godogen-ddm tests/test_godogen_ddm_cli.py comfyui-cloud
git commit -m "feat(comfy): guard paid cloud smoke"
```

## Task 7: Runtime Publish

**Files:**
- Modify: `publish.sh`
- Modify: `tests/test_godogen_ddm_cli.py`
- Modify: `README.md`

- [ ] **Step 1: Write failing publish test**

Publish Godot/Codex and assert:

```python
self.assertTrue((root / "comfyui-cloud").exists())
self.assertTrue((root / "comfyui-cloud" / "profiles" / "ref-image.json").exists())
```

- [ ] **Step 2: Copy profile/workflow assets at publish time**

Modify `publish.sh` to copy `comfyui-cloud/` into the published game repo, excluding planning-only files if needed.

- [ ] **Step 3: Verify runtime wrapper can dry-run Comfy provider**

Run published:

```bash
tools/godogen-ddm asset image --provider comfy-cloud --workflow ref-image --dry-run --prompt "runtime cloud probe" -o assets/img/cloud_probe.png
```

Expected: `ok: true`, provider `comfy-cloud`, dry_run `true`.

- [ ] **Step 4: Commit**

```bash
git add publish.sh tests/test_godogen_ddm_cli.py README.md
git commit -m "feat(publish): include comfy cloud profiles"
```

## Full Verification Command

After all tasks:

```bash
bin/godogen-ddm verify --out /tmp/godogen-ddm-comfy-cloud-verify
git diff --check
```

Expected:

- Unit tests pass.
- Bash syntax checks pass.
- Python bytecode checks pass.
- Publish/runtime matrix passes.
- Smoke passes.
- Non-paid external-smoke includes Comfy Cloud dry-run and does not consume credits.

## Open Decisions Before Coding Real Cloud Submission

- Which first real workflow profile should be exported from Comfy Cloud UI: `ref-image`, `hunyuan-image-to-3d`, or `llm-vision-review`.
- Whether `model3d` should be a new asset subcommand immediately or whether it should initially reuse existing `glb` only after Comfy profile validation.
- Whether direct Tripo3D remains a long-term fallback or is retired after Comfy Tripo/Hunyuan workflows pass real smoke.
- Where Comfy Cloud workflow JSON should be stored in published game repos if workflows become large.

## Spec Coverage Check

- Single Codex + single ComfyUI Cloud architecture: covered by `README.md` and `architecture.md`.
- Cloud-only Comfy direction: covered by non-goals and provider design.
- Images, models, videos: covered by provider surface and task plan.
- LLM availability: covered by source notes and architecture boundary.
- Separate `comfyui-cloud/` folder: created in this plan.
- Existing info planning phase: covered by `sources.md`, `architecture.md`, and this task plan.
