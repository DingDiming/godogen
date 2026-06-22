# ComfyUI Cloud / Local Partner Node Integration

This folder records the planning surface for simplifying Godogen into:

- **Codex** as the orchestrator: repo edits, planning, code generation, test/build/run, git, engine capture, and acceptance.
- **ComfyUI** as the model router: local ComfyUI server for workflow execution, Comfy account credits for paid Partner/API nodes, and Comfy Cloud API when a hosted API workflow is explicitly selected.

The goal is to avoid direct runtime bindings to many model vendor APIs. Godogen should submit versioned Comfy workflow profiles, monitor jobs, download or write outputs, copy artifacts into `assets/` or `refs/`, and then verify those artifacts inside the target engine.

## Current Repo Baseline

Current branch: `ddm-provider-adapters`

Current runtime provider surface:

- `image`: `dreamina`, `procedural`, `codex`, `comfy-cloud`, `comfy-local`
- `texture`: defaults to `procedural`, can use image providers
- `video`: `dreamina`, `codex`, `comfy-cloud`, `comfy-local`
- `analyze`: `comfy-local`
- `glb` / `rig` / `retarget` / `resume`: direct Tripo3D path

The branch has already removed direct Grok, Gemini, and OpenAI API-key providers from runtime asset generation. The next architecture step is to replace one-off asset providers with a ComfyUI Cloud provider that can route through workflow profiles.

## Target Provider Direction

Add Comfy providers:

```bash
asset_gen.py image   --provider comfy-cloud --workflow ref-image ...
asset_gen.py image   --provider comfy-local --workflow ref-image ...
asset_gen.py texture --provider comfy-cloud --workflow pbr-texture ...
asset_gen.py video   --provider comfy-cloud --workflow image-to-video ...
asset_gen.py model3d --provider comfy-cloud --workflow hunyuan-image-to-3d ...
asset_gen.py analyze --provider comfy-local --workflow llm-smoke ...
```

The exact command names can still be refined during implementation. The stable contract should be:

```json
{"ok": true, "path": "assets/...", "cost_cents": 0}
```

When the Comfy job is not complete:

```json
{
  "ok": false,
  "pending": true,
  "provider": "comfy-local",
  "prompt_id": "...",
  "status": "pending",
  "sidecar": "assets/...comfy.json"
}
```

## Required Account Material

Only one primary Comfy account key should be needed by Godogen for automated Partner/API node execution:

- `COMFY_API_KEY`

`COMFY_CLOUD_API_KEY` remains supported for the hosted Comfy Cloud API path and as a compatibility fallback. Comfy account credits/subscription are required for Cloud API and paid Partner Nodes. Vendor-specific model access should be handled inside ComfyUI Partner Nodes and workflow profiles, not exposed as separate Godogen provider keys.

Browser login in the local ComfyUI UI is enough for manual UI runs, but it is not enough for CLI automation through `asset_gen.py`. Programmatic paid Partner/API node submissions require `COMFY_API_KEY` in the environment so Codex can submit `/prompt` without reading browser tokens.

Direct `TRIPO3D_API_KEY` may remain temporarily as fallback while the ComfyUI Cloud 3D profiles are validated.

## Non-Goals

- Do not install local Hunyuan3D weights for this architecture.
- Do not dynamically generate arbitrary Comfy graphs at runtime.
- Do not treat Comfy job completion as game-asset acceptance.
- Do not store cloud API keys, partner tokens, account IDs, credit balances, or signed output URLs in repo files.

## Acceptance Shape

A generated cloud asset is accepted only after:

1. The Comfy job completes.
2. The output file is downloaded and copied to the requested `assets/` or explicit `refs/` path.
3. A sidecar records workflow profile, prompt id, output node, output filenames, status, timestamps, and sanitized error information.
4. The game imports/builds/runs with the asset.
5. Capture evidence shows the asset in context.
