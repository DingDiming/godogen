# ComfyUI Cloud Architecture

## Core Boundary

The target product boundary is:

```text
Codex
  owns repo, code, tests, engine runs, capture, git, acceptance

ComfyUI / Comfy Account
  owns workflow execution for image, video, 3D, texture, and workflow-local LLM nodes
  uses local ComfyUI server plus Comfy credits for paid Partner/API nodes
```

Codex should not become a thin wrapper around Comfy. Comfy should not become the project manager. The split is:

- Codex decides what asset is needed.
- Codex chooses a workflow profile.
- Codex submits the workflow to local ComfyUI or Comfy Cloud.
- Comfy runs the selected models and returns files or structured text.
- Codex copies files into the game repo and verifies them in-engine.

## Provider Layer

Use two explicit Comfy providers under the existing asset generator system:

- `comfy-local`: submits workflow API JSON to a local ComfyUI server, defaulting to `http://127.0.0.1:8000`; paid Partner/API nodes require `COMFY_API_KEY`.
- `comfy-cloud`: submits to hosted Comfy Cloud API; it remains useful when the hosted API tier is intentionally used.

Candidate source files:

- `shared/skills/godogen/tools/providers/comfy_cloud.py`
- `shared/skills/godogen/tools/providers/comfy_profiles.py`
- `shared/skills/godogen/tools/providers/comfy_http.py`
- `shared/skills/godogen/tools/providers/comfy_local.py`
- `shared/skills/godogen/tools/providers/comfy_outputs.py`

Keep responsibilities split:

- `comfy_profiles.py`: load and validate workflow profile manifests.
- `comfy_http.py`: submit workflow, poll job, fetch job detail, download output.
- `comfy_outputs.py`: map Comfy output metadata to requested output paths.
- `comfy_cloud.py`: provider entrypoint called by `asset_gen.py`.
- `comfy_local.py`: local ComfyUI provider entrypoint for local `/prompt`, `/history`, and `/view`.

## Workflow Profiles

Comfy workflows should be versioned in source, not generated ad hoc.

Suggested layout:

```text
comfyui-cloud/
  README.md
  sources.md
  architecture.md
  tasks.md
  profiles/
    schema.json
    ref-image.json
    image-to-video.json
    hunyuan-image-to-3d.json
    hunyuan-multiview-to-3d.json
    tripo-image-to-3d.json
    llm-vision-review.json
  workflows/
    ref-image.workflow_api.json
    image-to-video.workflow_api.json
    hunyuan-image-to-3d.workflow_api.json
```

Profiles describe how Godogen fills a Comfy workflow:

```json
{
  "id": "hunyuan-image-to-3d",
  "asset_kind": "model3d",
  "workflow": "workflows/hunyuan-image-to-3d.workflow_api.json",
  "inputs": {
    "prompt": {"node": "12", "field": "inputs.prompt"},
    "image": {"node": "5", "field": "inputs.image"}
  },
  "outputs": [
    {"node": "42", "kind": "model", "extensions": [".glb", ".obj", ".fbx"]}
  ],
  "timeout_seconds": 1200,
  "paid": true
}
```

The schema should validate before any cloud submission.

## CLI Surface

Keep the existing compatibility shape and add the smallest new command surface:

```bash
asset_gen.py image \
  --provider comfy-local \
  --workflow ref-image \
  --prompt "..." \
  -o assets/img/ref.png

asset_gen.py video \
  --provider comfy-cloud \
  --workflow image-to-video \
  --image assets/img/first.png \
  --prompt "..." \
  --duration 4 \
  -o assets/video/clip.mp4

asset_gen.py model3d \
  --provider comfy-cloud \
  --workflow hunyuan-image-to-3d \
  --image assets/img/model_ref.png \
  -o assets/glb/model.glb

asset_gen.py analyze \
  --provider comfy-local \
  --workflow llm-smoke \
  --prompt "Reply with exactly: ok" \
  -o refs/review/llm_smoke.txt
```

If adding `model3d` is too broad for the first coding slice, start with `analyze --provider comfy-local --dry-run`, `image --provider comfy-cloud --dry-run`, and `texture --provider comfy-cloud --dry-run`, then add other kinds.

## Sidecar Contract

Every Comfy submission writes a sidecar next to the target output:

```json
{
  "provider": "comfy-local",
  "profile": "ref-image",
  "status": "pending",
  "prompt_id": "cloud-job-id",
  "target_path": "assets/img/ref.png",
  "workflow": "comfyui-cloud/workflows/ref-image.workflow_api.json",
  "submitted_at": "2026-06-22T00:00:00Z",
  "outputs": [],
  "error": null
}
```

Never store:

- `COMFY_CLOUD_API_KEY`
- `COMFY_API_KEY`
- signed output URLs
- account email
- credit balance
- raw provider logs that may include tokens

## Completion Semantics

Comfy states map into Godogen JSON as:

- `pending` / `in_progress`: `{"ok": false, "pending": true, ...}`
- `completed` with downloaded file: `{"ok": true, "path": "...", "cost_cents": 0}`
- `failed` / `cancelled`: `{"ok": false, "error": "...", "cost_cents": 0}`

`completed` is still only provider completion. Game-task acceptance still needs build/import/capture verification.

## Why LLM Stays Workflow-Local

Comfy has LLM partner nodes, including OpenRouter, OpenAI Chat, and Anthropic Claude nodes. They are useful inside visual workflows:

- prompt expansion
- image-to-prompt conversion
- visual target critique
- asset metadata generation
- style consistency checks

They should not replace Codex as project orchestrator because Codex has local repo access, can edit files, run engines, inspect git, and close the acceptance loop.
