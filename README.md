# Godogen

Autonomous game development for Godot, Bevy, and Babylon.js with Claude Code and Codex.

[![Watch the video](https://img.youtube.com/vi/eUz19GROIpY/maxresdefault.jpg)](https://youtu.be/eUz19GROIpY)

[Watch the demos](https://youtu.be/eUz19GROIpY) · [Prompts](docs/demo_prompts.md)

Describe a game. Godogen plans it, writes the code, generates assets, runs the engine, checks screenshots, and fixes what looks wrong.

This repo is not a game. It is the source for a generator that produces games: **godogen -> game repo -> game**. You publish the skills into a fresh game repo, choosing the engine and host-agent flavor, then the agent runs inside that repo to build the actual game.

## Source layout

The source is organized along the engine axis:

- `shared/` — engine-agnostic `godogen` stages, asset-generation tooling, shared stop hook, and common game-repo instructions
- `godot/` — Godot-specific `godogen` stages, Godot capture helpers, and the `godot-api` skill
- `bevy/` — Bevy-specific `godogen` stages, Bevy capture helpers, and the `bevy-help` skill
- `babylon/` — Babylon.js-specific `godogen` stages, Vite scaffold, browser capture helpers, and the `babylon-help` skill

Claude Code vs Codex is a publish-time render choice, not a separate source tree. The root [publish.sh](publish.sh) renders the right runtime layout for the chosen engine and host agent.

## What skills do

- **Godot 4 output** — real C#/.NET projects with proper scene trees, scene builders, scripts, and asset organization.
- **Godot Android export** — debug APK export remains available when the user requests an Android app.
- **Bevy output** — Rust/Bevy projects with code-first scenes, local Bevy docs lookup, deterministic capture guidance, and final proof bundles.
- **Babylon.js output** — TypeScript/Vite browser games with first-class hot reload, Chrome/Chromium WebGL2 capture, and static web builds.
- **Asset generation** — configurable providers generate images and videos: Grok remains the default, Gemini supports precise references, Dreamina CLI can handle local image/video runs, OpenAI can generate images, procedural output covers debug textures/placeholders, and Tripo3D converts images to 3D models.
- **C# / .NET 9 for Godot** — Godot output uses C#. See [why C# over GDScript](docs/gdscript-vs-csharp.md).
- **Frame-grounded self-repair** — the agent is carefully prompted to judge progress from captured screenshots, not from code that compiles, so visible defects (clipping, wrong scale, frozen motion, missing assets) drive the next iteration instead of being rationalized away.
- **Telegram proof push** — opt in with `--video_hook` at publish time to install a stop hook that pushes the latest `screenshots/result/{N}/video.mp4` to Telegram when `tg-push` and the TG_* env vars are configured. No-op otherwise. Off by default.
- **Runs on commodity hardware** — any machine with the relevant engine toolchain, Python, and the required API keys can run the pipeline.

## Getting started

### Prerequisites

- [Godot 4](https://godotengine.org/download/) (.NET build) on `PATH` for Godot projects
- Current stable Rust/Cargo plus local Bevy docs for Bevy projects
- Node.js 22.12+ and npm for Babylon.js projects
- Chrome or Chromium with hardware WebGL2 for Babylon.js browser capture
- Python 3 with pip
- Provider credentials as environment variables or local login state:
  - `GODOGEN_IMAGE_PROVIDER=openai|dreamina|gemini|grok|procedural`
  - `GODOGEN_VIDEO_PROVIDER=dreamina|grok|openai`
  - `GOOGLE_API_KEY` — [Google AI Studio](https://aistudio.google.com/) only when using Gemini image generation
  - `XAI_API_KEY` — [xAI Grok](https://console.x.ai/home) when using Grok image/video generation
  - `OPENAI_API_KEY` — [OpenAI](https://platform.openai.com/) only when using OpenAI image/video generation
  - Dreamina CLI login state — required when using Dreamina providers
  - `TRIPO3D_API_KEY` — [Tripo3D](https://platform.tripo3d.ai/) for 3D generation
- System packages from [setup.md](setup.md): `vulkan-tools`, `xvfb`, `ffmpeg`, `imagemagick`, plus platform-specific extras
- Tested on Ubuntu, Debian, and macOS
- Claude Code or Codex

### Publish a game repo

Pick the engine and host agent:

```bash
./publish.sh --engine godot --agent claude --out ~/my-game  # CLAUDE.md + .claude/skills/
./publish.sh --engine godot --agent codex  --out ~/my-game  # AGENTS.md + .agents/skills/
./publish.sh --engine bevy  --agent claude --out ~/my-game
./publish.sh --engine bevy  --agent codex  --out ~/my-game
./publish.sh --engine babylon --agent claude --out ~/my-game
./publish.sh --engine babylon --agent codex  --out ~/my-game
```

Pass `--force` to wipe existing contents at the target before publishing — use this when re-publishing over a previous run. Pass `--video_hook` to install the optional Telegram stop hook (off by default; see below).

### DDM wrapper

This fork also includes `bin/godogen-ddm` for local CLI use:

```bash
bin/godogen-ddm check-env
bin/godogen-ddm publish --engine godot --agent codex --out /tmp/my-game
bin/godogen-ddm asset texture --prompt "debug grid" -o assets/img/grid.png
bin/godogen-ddm asset texture --provider openai --dry-run --prompt "wet cobblestone" -o assets/img/cobblestone.png
bin/godogen-ddm asset video --provider dreamina --dry-run --image assets/img/first.png --prompt "camera push" --duration 4 -o assets/video/clip.mp4
bin/godogen-ddm smoke
bin/godogen-ddm external-smoke --out /tmp/godogen-external-smoke
bin/godogen-ddm verify
```

Published game repos also get `tools/godogen-ddm`; run it from the game root for asset commands against the published `.agents` or `.claude` runtime skill copy.
`check-env` reports provider env vars as `set` or `unset` only; it does not print key values.
`smoke` verifies Godot/Codex publishing, provider routing, procedural texture output, Dreamina dry-run command construction, and a minimal Godot C# `dotnet build` plus headless project load.
`external-smoke` defaults to non-paid dry-runs for Dreamina/OpenAI image-video command construction and skips Tripo3D because it has no dry-run path. Use `external-smoke --yes-charge` only when you explicitly want to submit real Dreamina/OpenAI/Tripo3D provider tasks and accept provider credits/API billing.
When a charged provider task returns `pending` or `failed`, `external-smoke` prints an `incomplete` summary and exits nonzero instead of treating generation submission as asset acceptance. Raw provider stdout/stderr is not persisted in the output directory, and provider JSON error summaries redact known key/token-shaped values.
`verify` runs the reusable local verification suite: unit tests, syntax checks, Python bytecode checks, publish/runtime wrapper matrix, `smoke`, and non-paid `external-smoke`.
OpenAI video uses the Sora 2 Videos API, which OpenAI marks as deprecated with a scheduled shutdown on September 24, 2026; keep Dreamina/Grok available as video alternatives.
See [DDM provider adapter branch notes](docs/ddm-provider-adapters.md) for the fork branch contract, verification commands, and remaining paid-smoke boundary.

### Bevy docs setup

If you're working on Bevy generation, configure and populate a shared Bevy docs folder once after clone:

```bash
rustup update stable
./setup_bevy_docs.sh /absolute/or/user/path/to/bevy-docs
```

The setup script links `bevy/skills/bevy-help/docs/` to that folder, creates shallow Bevy docs source checkouts for new caches, and builds local rustdoc for the current stable Bevy release. Because the script tracks current stable Bevy, update Rust stable first if your toolchain is older than the Bevy release's minimum supported Rust version. No default path is assumed. See [setup.md](setup.md) for the full workstation setup.

## Running on a server

A full generation run can take hours, so it's convenient to offload it to a server, ideally a GPU instance, since engine rendering and video capture are much faster with hardware acceleration.

- Keep the session alive across SSH drops with `tmux` or `screen`.
- Install [tg-push](https://github.com/htdt/tg-push) and publish with `--video_hook`: the stop hook auto-sends the final proof video to Telegram on completion.
- Enable remote control so you can check in and steer the run from any device — both Claude Code and Codex have official remote-control interfaces.

## Improving the skills

After a full generation session, ask the agent you used to review how the pipeline performed:

> Analyze this session. Were the instructions optimal? Flag anything that was too obvious, missing, or misleading. Did any tools pollute context with noise? Did the capture loop catch the real problems? Any tool failures or workarounds?

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

Follow progress: [@alex_erm](https://x.com/alex_erm)
