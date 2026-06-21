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

- Image: `grok`, `gemini`, `dreamina`, `openai`, `procedural`
- Video: `grok`, `dreamina`, `openai`
- Texture: defaults to `procedural`, but can use any image provider
- 3D: Tripo3D `glb`, `rig`, `retarget`, and `resume` remain in place

Provider selection:

- `GODOGEN_IMAGE_PROVIDER=openai|dreamina|gemini|grok|procedural`
- `GODOGEN_VIDEO_PROVIDER=dreamina|grok|openai`
- CLI `--provider` overrides environment selection
- Legacy image `--model grok|gemini` remains available when no provider override is set
- Image-to-image providers require an existing `--image` reference file before command construction.

## CLI

Source repo wrapper:

```bash
bin/godogen-ddm check-env
bin/godogen-ddm publish --engine godot --agent codex --out /tmp/my-game
bin/godogen-ddm asset texture --prompt "debug grid" -o assets/img/grid.png
bin/godogen-ddm smoke
bin/godogen-ddm external-smoke --out /tmp/godogen-external-smoke
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
- `external-smoke --yes-charge` is the only path that submits real Dreamina/OpenAI/Tripo3D tasks.
- `external-smoke --yes-charge` summarizes provider `pending` and `failed` states, exits nonzero when any provider is incomplete, and does not persist raw provider logs in the output directory.
- Provider JSON error summaries redact known key/token-shaped values before printing.
- A provider success response is not final asset acceptance. Generated assets still need engine import/build/capture verification in the target game.

## Verification

Current local verification set:

```bash
python3 -m unittest tests/test_asset_gen_providers.py tests/test_godogen_ddm_cli.py
/bin/bash -n bin/godogen-ddm && /bin/bash -n publish.sh
python3 -m py_compile shared/skills/godogen/tools/asset_gen.py shared/skills/godogen/tools/providers/*.py tests/test_asset_gen_providers.py tests/test_godogen_ddm_cli.py
bin/godogen-ddm smoke
bin/godogen-ddm external-smoke --out /tmp/godogen-external-smoke
```

Publish matrix smoke:

```bash
for engine in godot bevy babylon; do
  for agent in codex claude; do
    out="/tmp/godogen-$engine-$agent"
    ./publish.sh --engine "$engine" --agent "$agent" --out "$out" --force
    test -x "$out/tools/godogen-ddm"
    "$out/tools/godogen-ddm" asset texture --prompt "runtime probe" --procedural-kind checker -o "$out/assets/img/probe.png"
  done
done
```

## Remaining Explicit Authorization

Do not run this without explicit user approval because it can consume provider credits/API billing:

```bash
bin/godogen-ddm external-smoke --yes-charge --out /tmp/godogen-external-paid-smoke
```
