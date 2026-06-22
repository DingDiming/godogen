# DDM Provider Adapter Branch

This document records the current operator contract for the `ddm-provider-adapters` fork branch.

## Branch

- Source repo: `/Users/ddm/Documents/GitHub/godogen`
- Upstream remote: `origin https://github.com/htdt/godogen`
- Fork remote: `fork https://github.com/DingDiming/godogen.git`
- Long-lived branch: `ddm-provider-adapters`

The branch keeps upstream Godogen's render model: source files live under `shared/`, `godot/`, `bevy/`, and `babylon/`; published game repos receive `.agents/skills/` or `.claude/skills/`. Do not maintain generated `.agents/skills/` or `.claude/skills/` inside this source repo.

## Provider Surface

`shared/skills/godogen/tools/asset_gen.py` keeps the original JSON compatibility shape:

```json
{"ok": true, "path": "assets/...", "cost_cents": 0}
```

Supported routes:

- Image: `dreamina`, `procedural`, `codex`
- Video: `dreamina`, `codex`
- Texture: defaults to `procedural`, but can use any image provider
- 3D: Tripo3D `glb`, `rig`, `retarget`, and `resume` remain in place

Provider selection:

- `GODOGEN_IMAGE_PROVIDER=dreamina|procedural|codex`
- `GODOGEN_VIDEO_PROVIDER=dreamina|codex`
- CLI `--provider` overrides environment selection
- Image-to-image providers require an existing `--image` reference file before command construction.
- `codex` queues a local `*.codex-task.json` manifest and returns `pending` until automation writes the target asset.

## CLI

Source repo wrapper:

```bash
bin/godogen-ddm check-env
bin/godogen-ddm publish --engine godot --agent codex --out /tmp/my-game
bin/godogen-ddm asset texture --prompt "debug grid" -o assets/img/grid.png
bin/godogen-ddm smoke
bin/godogen-ddm external-smoke --out /tmp/godogen-external-smoke
bin/godogen-ddm verify
```

Published game repos receive a project-local wrapper:

```bash
tools/godogen-ddm asset texture --prompt "runtime checker" -o assets/img/runtime_checker.png
tools/godogen-ddm asset video --provider dreamina --dry-run --image assets/img/first.png --prompt "camera push" --duration 4 -o assets/video/clip.mp4
```

The wrapper auto-locates `asset_gen.py` in either source layout or published runtime layout.

## Safety Rules

- `check-env` prints provider env status as `set` or `unset`; it does not print key values.
- Dreamina non-pending failures return a short exit-code summary and suppress raw CLI stdout/stderr.
- Direct remote API-key image/video providers are not exposed by this branch.
- `external-smoke --yes-charge` is the only path that submits real Dreamina/Tripo3D tasks.
- `external-smoke --yes-charge` summarizes provider `pending` and `failed` states, exits nonzero when any provider is incomplete, and does not persist raw provider logs in the output directory.
- Provider JSON error summaries redact known key/token-shaped values before printing.
- A provider success response is not final asset acceptance. Generated assets still need engine import/build/capture verification in the target game.

## Verification

Current local verification set:

```bash
bin/godogen-ddm verify
```

`verify` runs unit tests, shell syntax checks, Python bytecode checks, the publish/runtime wrapper matrix, `smoke`, and non-paid `external-smoke`. For focused runtime wrapper checks without recursive unit tests or heavier smoke:

```bash
bin/godogen-ddm verify --skip-tests --skip-smoke --skip-external-smoke --out /tmp/godogen-ddm-verify
```

## Remaining Explicit Authorization

Do not run this without explicit user approval because it can consume provider credits:

```bash
bin/godogen-ddm external-smoke --yes-charge --out /tmp/godogen-external-paid-smoke
```
