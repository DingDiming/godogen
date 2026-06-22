#!/usr/bin/env python3
"""Asset Generator CLI - creates images/videos via keyless providers and GLBs via Tripo3D.

Subcommands:
  image     Generate a PNG from a prompt
  texture   Generate a texture PNG via procedural or image providers
  video     Generate MP4 video from prompt + reference image
  glb       Convert a PNG to a static GLB (30¢ default, 60¢ hd)
  rig       Convert a PNG to a rigged biped GLB (preset + 25¢)
  retarget  Apply a biped preset animation to a rigged GLB (10¢)
  resume    Resume a timed-out Tripo3D job (glb/rig/retarget) from its sidecar — no extra cost

Output: JSON to stdout. Progress to stderr.
"""

import argparse
import json
import os
import sys
from pathlib import Path

from providers import codex_task, comfy_cloud, dreamina_cli, procedural
from providers.common import ProviderResult

TOOLS_DIR = Path(__file__).parent
BUDGET_FILE = Path("assets/budget.json")


def _load_budget():
    if not BUDGET_FILE.exists():
        return None
    return json.loads(BUDGET_FILE.read_text())


def _spent_total(budget):
    return sum(v for entry in budget.get("log", []) for v in entry.values())


def check_budget(cost_cents: int):
    """Check remaining budget. Exit with error JSON if insufficient."""
    budget = _load_budget()
    if budget is None:
        return
    spent = _spent_total(budget)
    remaining = budget.get("budget_cents", 0) - spent
    if cost_cents > remaining:
        result_json(False, error=f"Budget exceeded: need {cost_cents}¢ but only {remaining}¢ remaining ({spent}¢ of {budget['budget_cents']}¢ spent)")
        sys.exit(1)


def record_spend(cost_cents: int, service: str):
    """Append a generation record to the budget log."""
    budget = _load_budget()
    if budget is None:
        return
    budget.setdefault("log", []).append({service: cost_cents})
    BUDGET_FILE.write_text(json.dumps(budget, indent=2) + "\n")

QUALITY_PRESETS = {
    "default": {
        "face_limit": 30000,
        "geometry_quality": "standard",
        "texture_quality": "standard",
        "cost_cents": 30,
    },
    "hd": {
        "face_limit": None,
        "geometry_quality": "detailed",
        "texture_quality": "detailed",
        "cost_cents": 60,
    },
}

RIG_COST_CENTS = 25
RETARGET_COST_CENTS = 10


def _tripo3d_api():
    import tripo3d

    return tripo3d


def result_json(
    ok: bool,
    path: str | None = None,
    cost_cents: int = 0,
    error: str | None = None,
    **extra,
):
    d = {"ok": ok, "cost_cents": cost_cents}
    if path:
        d["path"] = path
    if error:
        d["error"] = error
    d.update({k: v for k, v in extra.items() if v is not None})
    print(json.dumps(d))


def emit_provider_result(result: ProviderResult) -> None:
    payload = dict(result.extra)
    if result.provider:
        payload.setdefault("provider", result.provider)
    result_json(
        result.ok,
        path=result.path,
        cost_cents=result.cost_cents,
        error=result.error,
        **payload,
    )


# --- Image/video provider routing ---

IMAGE_PROVIDERS = ["dreamina", "procedural", "codex", "comfy-cloud"]
VIDEO_PROVIDERS = ["dreamina", "codex", "comfy-cloud"]
ALL_SIZES = ["512", "1K", "2K", "4K"]
ALL_ASPECT_RATIOS = [
    "1:1",
    "16:9",
    "9:16",
    "4:3",
    "3:4",
    "3:2",
    "2:3",
    "4:5",
    "5:4",
    "21:9",
    "auto",
]


def _selected_provider(cli_provider: str | None, env_var: str, fallback: str) -> str:
    return cli_provider or os.environ.get(env_var) or fallback


def _fail_provider_error(message: str) -> None:
    result_json(False, error=message)
    sys.exit(1)


def _emit_or_exit(result: ProviderResult, spend_service: str | None = None) -> None:
    if result.ok and result.cost_cents and spend_service:
        record_spend(result.cost_cents, spend_service)
    emit_provider_result(result)
    if not result.ok:
        sys.exit(1)


def _run_image_provider(args, output: Path, provider: str, kind: str = "image") -> None:
    if provider not in IMAGE_PROVIDERS:
        _fail_provider_error(f"Unknown image provider: {provider}. Use: {', '.join(IMAGE_PROVIDERS)}")

    label = f"{provider} {args.size} {args.aspect_ratio}"
    if args.image:
        label += " (image-to-image)"
    print(f"Generating {kind} ({label})...", file=sys.stderr)

    try:
        if provider == "procedural":
            check_budget(0)
            _emit_or_exit(procedural.generate_image(args, output))

        elif provider == "dreamina":
            check_budget(dreamina_cli.DREAMINA_IMAGE_COST_CENTS)
            _emit_or_exit(dreamina_cli.generate_image(args, output))

        elif provider == "codex":
            check_budget(codex_task.CODEX_TASK_COST_CENTS)
            _emit_or_exit(codex_task.generate_image(args, output, kind))

        elif provider == "comfy-cloud":
            check_budget(0)
            _emit_or_exit(comfy_cloud.generate_image(args, output, kind))

    except Exception as e:
        result_json(False, error=str(e), provider=provider)
        sys.exit(1)


def cmd_image(args):
    provider = _selected_provider(args.provider, "GODOGEN_IMAGE_PROVIDER", "codex")
    _run_image_provider(args, Path(args.output), provider, kind="image")


def cmd_texture(args):
    provider = _selected_provider(args.provider, "GODOGEN_IMAGE_PROVIDER", "procedural")
    _run_image_provider(args, Path(args.output), provider, kind="texture")


def cmd_video(args):
    provider = _selected_provider(args.provider, "GODOGEN_VIDEO_PROVIDER", "dreamina")
    if provider not in VIDEO_PROVIDERS:
        _fail_provider_error(f"Unknown video provider: {provider}. Use: {', '.join(VIDEO_PROVIDERS)}")

    output = Path(args.output)
    image_path = Path(args.image)
    if not image_path.exists():
        result_json(False, error=f"Reference image not found: {image_path}", provider=provider)
        sys.exit(1)

    print(f"Generating {args.duration}s video ({provider} {args.resolution})...", file=sys.stderr)

    try:
        if provider == "dreamina":
            check_budget(dreamina_cli.DREAMINA_VIDEO_COST_CENTS)
            _emit_or_exit(dreamina_cli.generate_video(args, output))

        elif provider == "codex":
            check_budget(codex_task.CODEX_TASK_COST_CENTS)
            _emit_or_exit(codex_task.generate_video(args, output))

        elif provider == "comfy-cloud":
            check_budget(0)
            _emit_or_exit(comfy_cloud.generate_video(args, output))

    except Exception as e:
        result_json(False, error=str(e), provider=provider)
        sys.exit(1)


def _sidecar_path(output: Path) -> Path:
    return output.with_suffix(output.suffix + ".tripo.json")


def _write_sidecar(output: Path, data: dict) -> None:
    _sidecar_path(output).write_text(json.dumps(data, indent=2) + "\n")


def _read_sidecar(path: Path) -> dict:
    sc = _sidecar_path(path)
    if not sc.exists():
        raise FileNotFoundError(f"Sidecar not found: {sc} (run `rig` first)")
    return json.loads(sc.read_text())


def _resolve_preset(name: str) -> dict:
    if name not in QUALITY_PRESETS:
        result_json(False, error=f"Unknown quality: {name}. Use: {', '.join(QUALITY_PRESETS)}")
        sys.exit(1)
    return QUALITY_PRESETS[name]


def _resume_hint(output: Path) -> str:
    return f"Task is still processing on the server. Resume (no extra cost) with: asset_gen.py resume -o {output}"


def cmd_glb(args):
    image_path = Path(args.image)
    if not image_path.exists():
        result_json(False, error=f"Image not found: {image_path}")
        sys.exit(1)

    tripo3d = _tripo3d_api()
    preset = _resolve_preset(args.quality)
    check_budget(preset["cost_cents"])

    face_limit = args.face_limit if args.quality == "default" else preset["face_limit"]

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    print(f"Generating GLB (quality={args.quality}, pbr={args.pbr}, face_limit={face_limit})...", file=sys.stderr)

    sidecar = {
        "kind": "mesh",
        "preset": args.quality,
        "pbr": args.pbr,
        "status": "pending",
    }
    try:
        task_id = tripo3d.create_image_to_model_task(
            image_path,
            face_limit=face_limit,
            pbr=args.pbr,
            geometry_quality=preset["geometry_quality"],
            texture_quality=preset["texture_quality"],
        )
        print(f"  image_to_model: {task_id}", file=sys.stderr)
        record_spend(preset["cost_cents"], "tripo3d-glb")
        sidecar["image_to_model_task_id"] = task_id
        _write_sidecar(output, sidecar)

        result = tripo3d.poll_task(task_id)
        tripo3d.download_model(result, output)
    except TimeoutError as e:
        result_json(False, error=f"{e}. {_resume_hint(output)}", cost_cents=preset["cost_cents"])
        sys.exit(1)
    except Exception as e:
        result_json(False, error=str(e))
        sys.exit(1)

    sidecar["status"] = "complete"
    _write_sidecar(output, sidecar)
    print(f"Saved: {output}", file=sys.stderr)
    result_json(True, path=str(output), cost_cents=preset["cost_cents"])


def cmd_rig(args):
    image_path = Path(args.image)
    if not image_path.exists():
        result_json(False, error=f"Image not found: {image_path}")
        sys.exit(1)

    tripo3d = _tripo3d_api()
    preset = _resolve_preset(args.quality)
    total_cost = preset["cost_cents"] + RIG_COST_CENTS
    check_budget(total_cost)

    face_limit = args.face_limit if args.quality == "default" else preset["face_limit"]

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    print(f"Generating rigged GLB (quality={args.quality}, face_limit={face_limit})...", file=sys.stderr)

    sidecar = {
        "kind": "rig",
        "preset": args.quality,
        "pbr": args.pbr,
        "rig_type": "biped",
        "status": "pending",
    }
    try:
        gen_id = tripo3d.create_image_to_model_task(
            image_path,
            face_limit=face_limit,
            pbr=args.pbr,
            geometry_quality=preset["geometry_quality"],
            texture_quality=preset["texture_quality"],
        )
        print(f"  image_to_model: {gen_id}", file=sys.stderr)
        record_spend(preset["cost_cents"], "tripo3d-glb")
        sidecar["image_to_model_task_id"] = gen_id
        sidecar["stage"] = "image_to_model"
        _write_sidecar(output, sidecar)
        tripo3d.poll_task(gen_id)

        check_id = tripo3d.create_prerigcheck_task(gen_id)
        print(f"  animate_prerigcheck: {check_id}", file=sys.stderr)
        sidecar["prerigcheck_task_id"] = check_id
        sidecar["stage"] = "prerigcheck"
        _write_sidecar(output, sidecar)
        check_result = tripo3d.poll_task(check_id)
        check_out = check_result.get("output", {})
        rig_type = check_out.get("rig_type")
        if rig_type != "biped":
            result_json(False, error=(
                f"Rig pipeline is biped-only; prerigcheck reported rig_type={rig_type!r}. "
                f"Use `glb` for non-biped characters."
            ), cost_cents=preset["cost_cents"])
            sys.exit(1)

        rig_id = tripo3d.create_rig_task(gen_id, rig_type="biped")
        print(f"  animate_rig: {rig_id}", file=sys.stderr)
        record_spend(RIG_COST_CENTS, "tripo3d-rig")
        sidecar["animate_rig_task_id"] = rig_id
        sidecar["stage"] = "animate_rig"
        _write_sidecar(output, sidecar)
        rig_result = tripo3d.poll_task(rig_id)
        tripo3d.download_model(rig_result, output)
    except TimeoutError as e:
        result_json(False, error=f"{e}. {_resume_hint(output)}", cost_cents=0)
        sys.exit(1)
    except Exception as e:
        result_json(False, error=str(e))
        sys.exit(1)

    sidecar["status"] = "complete"
    _write_sidecar(output, sidecar)
    print(f"Saved: {output}", file=sys.stderr)
    result_json(True, path=str(output), cost_cents=total_cost)


def cmd_retarget(args):
    rigged = Path(args.rigged)
    if not rigged.exists():
        result_json(False, error=f"Rigged GLB not found: {rigged}")
        sys.exit(1)

    try:
        rigged_sidecar = _read_sidecar(rigged)
    except FileNotFoundError as e:
        result_json(False, error=str(e))
        sys.exit(1)

    rig_task_id = rigged_sidecar.get("animate_rig_task_id")
    if not rig_task_id or rigged_sidecar.get("kind") != "rig":
        result_json(False, error=f"Sidecar for {rigged} is not a rig output")
        sys.exit(1)

    tripo3d = _tripo3d_api()
    check_budget(RETARGET_COST_CENTS)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    print(f"Retargeting ({args.animation})...", file=sys.stderr)

    sidecar = {
        "kind": "anim",
        "animate_rig_task_id": rig_task_id,
        "animation": args.animation,
        "status": "pending",
    }
    try:
        task_id = tripo3d.create_retarget_task(rig_task_id, args.animation)
        print(f"  animate_retarget: {task_id}", file=sys.stderr)
        record_spend(RETARGET_COST_CENTS, "tripo3d-retarget")
        sidecar["animate_retarget_task_id"] = task_id
        _write_sidecar(output, sidecar)
        result = tripo3d.poll_task(task_id)
        tripo3d.download_model(result, output)
    except TimeoutError as e:
        result_json(False, error=f"{e}. {_resume_hint(output)}", cost_cents=RETARGET_COST_CENTS)
        sys.exit(1)
    except Exception as e:
        result_json(False, error=str(e))
        sys.exit(1)

    sidecar["status"] = "complete"
    _write_sidecar(output, sidecar)
    print(f"Saved: {output}", file=sys.stderr)
    result_json(True, path=str(output), cost_cents=RETARGET_COST_CENTS)


def cmd_resume(args):
    output = Path(args.output)
    try:
        sidecar = _read_sidecar(output)
    except FileNotFoundError as e:
        result_json(False, error=str(e))
        sys.exit(1)

    if sidecar.get("status") == "complete":
        print(f"Already complete: {output}", file=sys.stderr)
        result_json(True, path=str(output), cost_cents=0)
        return

    kind = sidecar.get("kind")
    output.parent.mkdir(parents=True, exist_ok=True)
    tripo3d = _tripo3d_api()

    try:
        if kind == "mesh":
            task_id = sidecar["image_to_model_task_id"]
            print(f"  resuming image_to_model: {task_id}", file=sys.stderr)
            result = tripo3d.poll_task(task_id)
            tripo3d.download_model(result, output)

        elif kind == "rig":
            stage = sidecar.get("stage")
            gen_id: str = sidecar["image_to_model_task_id"]

            if stage == "image_to_model":
                print(f"  resuming image_to_model: {gen_id}", file=sys.stderr)
                tripo3d.poll_task(gen_id)
                check_id = tripo3d.create_prerigcheck_task(gen_id)
                print(f"  animate_prerigcheck: {check_id}", file=sys.stderr)
                sidecar["prerigcheck_task_id"] = check_id
                sidecar["stage"] = "prerigcheck"
                _write_sidecar(output, sidecar)
                stage = "prerigcheck"

            if stage == "prerigcheck":
                check_id = sidecar["prerigcheck_task_id"]
                print(f"  resuming animate_prerigcheck: {check_id}", file=sys.stderr)
                check_result = tripo3d.poll_task(check_id)
                rt = check_result.get("output", {}).get("rig_type")
                if rt != "biped":
                    result_json(False, error=f"prerigcheck: rig_type={rt!r}; rig pipeline is biped-only")
                    sys.exit(1)
                rig_id = tripo3d.create_rig_task(gen_id, rig_type="biped")
                print(f"  animate_rig: {rig_id}", file=sys.stderr)
                record_spend(RIG_COST_CENTS, "tripo3d-rig")
                sidecar["animate_rig_task_id"] = rig_id
                sidecar["stage"] = "animate_rig"
                _write_sidecar(output, sidecar)
                stage = "animate_rig"

            if stage == "animate_rig":
                rig_id = sidecar["animate_rig_task_id"]
                print(f"  resuming animate_rig: {rig_id}", file=sys.stderr)
                rig_result = tripo3d.poll_task(rig_id)
                tripo3d.download_model(rig_result, output)
            else:
                result_json(False, error=f"Unknown rig stage: {stage}")
                sys.exit(1)

        elif kind == "anim":
            task_id = sidecar["animate_retarget_task_id"]
            print(f"  resuming animate_retarget: {task_id}", file=sys.stderr)
            result = tripo3d.poll_task(task_id)
            tripo3d.download_model(result, output)

        else:
            result_json(False, error=f"Unknown sidecar kind: {kind!r}")
            sys.exit(1)

    except TimeoutError as e:
        result_json(False, error=f"{e}. Task still processing; retry resume.", cost_cents=0)
        sys.exit(1)
    except Exception as e:
        result_json(False, error=str(e))
        sys.exit(1)

    sidecar["status"] = "complete"
    _write_sidecar(output, sidecar)
    print(f"Saved: {output}", file=sys.stderr)
    result_json(True, path=str(output), cost_cents=0)


def cmd_set_budget(args):
    BUDGET_FILE.parent.mkdir(parents=True, exist_ok=True)
    budget = {"budget_cents": args.cents, "log": []}
    if BUDGET_FILE.exists():
        old = json.loads(BUDGET_FILE.read_text())
        budget["log"] = old.get("log", [])
    BUDGET_FILE.write_text(json.dumps(budget, indent=2) + "\n")
    spent = _spent_total(budget)
    print(json.dumps({"ok": True, "budget_cents": args.cents, "spent_cents": spent, "remaining_cents": args.cents - spent}))


def main():
    parser = argparse.ArgumentParser(description="Asset Generator — keyless images/videos and GLBs (Tripo3D)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_img = sub.add_parser("image", help="Generate a PNG image")
    p_img.add_argument("--prompt", required=True, help="Full image generation prompt")
    p_img.add_argument("--provider", choices=IMAGE_PROVIDERS, default=None,
                       help="Provider override. Env fallback: GODOGEN_IMAGE_PROVIDER. Default: codex task queue.")
    p_img.add_argument("--size", choices=ALL_SIZES, default="1K",
                       help="Resolution hint. Default: 1K.")
    p_img.add_argument("--aspect-ratio", choices=ALL_ASPECT_RATIOS, default="1:1",
                       help="Aspect ratio. Default: 1:1")
    p_img.add_argument("--image", default=None, help="Reference image for image-to-image edit")
    p_img.add_argument("--workflow", default=None,
                       help="Comfy Cloud workflow profile id when --provider comfy-cloud.")
    p_img.add_argument("--procedural-kind", choices=procedural.PROCEDURAL_KINDS, default="checker",
                       help="Procedural image kind when --provider procedural. Default: checker.")
    p_img.add_argument("--poll", type=int, default=0,
                       help="Dreamina: poll up to N seconds after submit. Default: 0")
    p_img.add_argument("--dry-run", action="store_true",
                       help="Build provider request/command without submitting a paid generation task.")
    p_img.add_argument("-o", "--output", required=True, help="Output PNG path")
    p_img.set_defaults(func=cmd_image)

    p_tex = sub.add_parser("texture", help="Generate a texture PNG via procedural or image providers")
    p_tex.add_argument("--prompt", required=True, help="Texture generation prompt")
    p_tex.add_argument("--provider", choices=IMAGE_PROVIDERS, default=None,
                       help="Provider override. Env fallback: GODOGEN_IMAGE_PROVIDER. Default: procedural.")
    p_tex.add_argument("--size", choices=ALL_SIZES, default="1K",
                       help="Resolution. Default: 1K.")
    p_tex.add_argument("--aspect-ratio", choices=ALL_ASPECT_RATIOS, default="1:1",
                       help="Aspect ratio. Default: 1:1")
    p_tex.add_argument("--image", default=None, help="Reference image for provider image-to-image edit")
    p_tex.add_argument("--workflow", default=None,
                       help="Comfy Cloud workflow profile id when --provider comfy-cloud.")
    p_tex.add_argument("--procedural-kind", choices=procedural.PROCEDURAL_KINDS, default="tile",
                       help="Procedural texture kind when --provider procedural. Default: tile.")
    p_tex.add_argument("--poll", type=int, default=0,
                       help="Dreamina: poll up to N seconds after submit. Default: 0")
    p_tex.add_argument("--dry-run", action="store_true",
                       help="Build provider request/command without submitting a paid generation task.")
    p_tex.add_argument("-o", "--output", required=True, help="Output PNG path")
    p_tex.set_defaults(func=cmd_texture)

    p_vid = sub.add_parser("video", help="Generate MP4 video from prompt + reference image")
    p_vid.add_argument("--provider", choices=VIDEO_PROVIDERS, default=None,
                       help="Provider override. Env fallback: GODOGEN_VIDEO_PROVIDER. Default: dreamina.")
    p_vid.add_argument("--prompt", required=True, help="Video generation prompt")
    p_vid.add_argument("--image", required=True, help="Reference image path (starting frame)")
    p_vid.add_argument("--duration", type=int, required=True, help="Duration in seconds (1-15)")
    p_vid.add_argument("--resolution", choices=["480p", "720p"], default="720p",
                       help="Video resolution. Default: 720p")
    p_vid.add_argument("--workflow", default=None,
                       help="Comfy Cloud workflow profile id when --provider comfy-cloud.")
    p_vid.add_argument("--poll", type=int, default=0,
                       help="Dreamina: poll up to N seconds after submit. Default: 0")
    p_vid.add_argument("--dry-run", action="store_true",
                       help="Build provider command without submitting a paid generation task.")
    p_vid.add_argument("-o", "--output", required=True, help="Output MP4 path")
    p_vid.set_defaults(func=cmd_video)

    p_glb = sub.add_parser("glb", help="Convert PNG to static GLB (30¢ default, 60¢ hd)")
    p_glb.add_argument("--image", required=True, help="Input PNG path")
    p_glb.add_argument("--quality", default="default", choices=list(QUALITY_PRESETS.keys()),
                       help="default=30¢ v3.1 std (30k faces), hd=60¢ v3.1 detailed geom+HD texture")
    p_glb.add_argument("--no-pbr", dest="pbr", action="store_false", default=True,
                       help="Disable PBR (use if PBR output looks wrong)")
    p_glb.add_argument("--face-limit", type=int, default=30000,
                       help="Face cap for default quality, 10000-50000. Ignored when --quality hd. Default: 30000")
    p_glb.add_argument("-o", "--output", required=True, help="Output GLB path")
    p_glb.set_defaults(func=cmd_glb)

    p_rig = sub.add_parser("rig", help="Convert PNG to rigged biped GLB (preset cost + 25¢). Biped only.")
    p_rig.add_argument("--image", required=True, help="Input PNG path (biped character)")
    p_rig.add_argument("--quality", default="default", choices=list(QUALITY_PRESETS.keys()),
                       help="Underlying mesh preset (default or hd)")
    p_rig.add_argument("--no-pbr", dest="pbr", action="store_false", default=True,
                       help="Disable PBR")
    p_rig.add_argument("--face-limit", type=int, default=30000,
                       help="Face cap for default quality. Ignored when --quality hd. Default: 30000")
    p_rig.add_argument("-o", "--output", required=True, help="Output rigged GLB path")
    p_rig.set_defaults(func=cmd_rig)

    p_rt = sub.add_parser("retarget", help="Apply a preset:biped:* animation to a rigged GLB (10¢)")
    p_rt.add_argument("--rigged", required=True, help="Rigged GLB produced by `rig`")
    p_rt.add_argument("--animation", required=True, help="e.g. preset:biped:walk")
    p_rt.add_argument("-o", "--output", required=True, help="Output animated GLB path")
    p_rt.set_defaults(func=cmd_retarget)

    p_res = sub.add_parser("resume", help="Resume a timed-out Tripo3D job from its sidecar (no extra cost)")
    p_res.add_argument("-o", "--output", required=True, help="Output path whose .tripo.json sidecar holds the pending task id(s)")
    p_res.set_defaults(func=cmd_resume)

    p_budget = sub.add_parser("set_budget", help="Set the asset generation budget in cents")
    p_budget.add_argument("cents", type=int, help="Budget in cents")
    p_budget.set_defaults(func=cmd_set_budget)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
