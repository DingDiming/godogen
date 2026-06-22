import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ASSET_GEN = REPO_ROOT / "shared" / "skills" / "godogen" / "tools" / "asset_gen.py"


PNG_1X1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753"
    "de0000000c49444154789c63606060000000040001f61738550000000049454e44ae426082"
)


def write_fake_dreamina(path, submit_key="submit_id", submit_id="submit-123", exit_code=42):
    path.write_text(
        "#!/bin/sh\n"
        f"printf '{{\"{submit_key}\":\"{submit_id}\"}}\\n'\n"
        f"exit {exit_code}\n"
    )
    path.chmod(0o755)


def run_asset_gen(args, env=None):
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    return subprocess.run(
        [sys.executable, str(ASSET_GEN), *args],
        cwd=tempfile.mkdtemp(prefix="godogen-asset-test."),
        env=merged_env,
        text=True,
        capture_output=True,
        check=False,
    )


def parse_json_stdout(proc):
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(f"stdout was not JSON: {proc.stdout!r}\nstderr: {proc.stderr}") from exc


class AssetGenProviderTests(unittest.TestCase):
    def test_comfy_profile_loader_reads_ref_image_profile(self):
        sys.path.insert(0, str(REPO_ROOT / "shared" / "skills" / "godogen" / "tools"))
        from providers.comfy_profiles import load_profile

        profile = load_profile("ref-image")

        self.assertEqual(profile["id"], "ref-image")
        self.assertEqual(profile["asset_kind"], "image")
        self.assertEqual(profile["workflow"], "workflows/ref-image.workflow_api.json")
        self.assertEqual(profile["inputs"]["prompt"]["node"], "6")
        self.assertEqual(profile["outputs"][0]["kind"], "image")

    def test_comfy_image_dry_run_builds_cloud_prompt_request(self):
        with tempfile.TemporaryDirectory(prefix="godogen-comfy-dry.") as tmp:
            output = Path(tmp) / "assets" / "img" / "ref.png"
            proc = run_asset_gen(
                [
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
                ]
            )

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

    def test_procedural_env_provider_generates_png_without_external_sdks(self):
        with tempfile.TemporaryDirectory(prefix="godogen-procedural.") as tmp:
            output = Path(tmp) / "assets" / "img" / "checker.png"
            proc = run_asset_gen(
                [
                    "image",
                    "--prompt",
                    "checker debug tile",
                    "--size",
                    "512",
                    "--aspect-ratio",
                    "1:1",
                    "-o",
                    str(output),
                ],
                env={"GODOGEN_IMAGE_PROVIDER": "procedural"},
            )

            self.assertEqual(proc.returncode, 0, proc.stderr)
            result = parse_json_stdout(proc)
            self.assertTrue(result["ok"])
            self.assertEqual(result["path"], str(output))
            self.assertEqual(result["cost_cents"], 0)
            self.assertEqual(output.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")

    def test_cli_provider_overrides_env_provider(self):
        with tempfile.TemporaryDirectory(prefix="godogen-provider-override.") as tmp:
            output = Path(tmp) / "assets" / "img" / "flat.png"
            proc = run_asset_gen(
                [
                    "image",
                    "--provider",
                    "procedural",
                    "--procedural-kind",
                    "flat",
                    "--prompt",
                    "flat ui panel",
                    "-o",
                    str(output),
                ],
                env={"GODOGEN_IMAGE_PROVIDER": "codex"},
            )

            self.assertEqual(proc.returncode, 0, proc.stderr)
            result = parse_json_stdout(proc)
            self.assertTrue(result["ok"])
            self.assertEqual(result["provider"], "procedural")
            self.assertEqual(output.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")

    def test_dreamina_video_dry_run_builds_image2video_command(self):
        with tempfile.TemporaryDirectory(prefix="godogen-dreamina-video.") as tmp:
            first_frame = Path(tmp) / "assets" / "img" / "first.png"
            output = Path(tmp) / "assets" / "video" / "walk.mp4"
            first_frame.parent.mkdir(parents=True)
            first_frame.write_bytes(PNG_1X1)

            proc = run_asset_gen(
                [
                    "video",
                    "--provider",
                    "dreamina",
                    "--dry-run",
                    "--prompt",
                    "slow camera push in",
                    "--image",
                    str(first_frame),
                    "--duration",
                    "4",
                    "--resolution",
                    "720p",
                    "--poll",
                    "2",
                    "-o",
                    str(output),
                ]
            )

            self.assertEqual(proc.returncode, 0, proc.stderr)
            result = parse_json_stdout(proc)
            self.assertTrue(result["ok"])
            self.assertTrue(result["dry_run"])
            self.assertEqual(result["provider"], "dreamina")
            self.assertEqual(result["path"], str(output))
            self.assertEqual(result["cost_cents"], 0)
            command = result["command"]
            self.assertEqual(command[:2], ["dreamina", "image2video"])
            self.assertIn(f"--image={first_frame}", command)
            self.assertIn("--duration=4", command)
            self.assertIn("--video_resolution=720p", command)
            self.assertIn("--poll=2", command)

    def test_dreamina_video_nonzero_submit_id_returns_pending(self):
        with tempfile.TemporaryDirectory(prefix="godogen-dreamina-pending-video.") as tmp:
            tmp_path = Path(tmp)
            fake_dreamina = tmp_path / "dreamina"
            write_fake_dreamina(fake_dreamina, submit_id="video-submit-123", exit_code=42)
            first_frame = tmp_path / "assets" / "img" / "first.png"
            output = tmp_path / "assets" / "video" / "walk.mp4"
            first_frame.parent.mkdir(parents=True)
            first_frame.write_bytes(PNG_1X1)

            proc = run_asset_gen(
                [
                    "video",
                    "--provider",
                    "dreamina",
                    "--prompt",
                    "slow camera push in",
                    "--image",
                    str(first_frame),
                    "--duration",
                    "4",
                    "--resolution",
                    "720p",
                    "--poll",
                    "2",
                    "-o",
                    str(output),
                ],
                env={"GODOGEN_DREAMINA_BIN": str(fake_dreamina)},
            )

            self.assertEqual(proc.returncode, 1)
            result = parse_json_stdout(proc)
            self.assertFalse(result["ok"])
            self.assertTrue(result["pending"])
            self.assertEqual(result["provider"], "dreamina")
            self.assertEqual(result["submit_id"], "video-submit-123")
            self.assertIn("query_result", result["error"])
            self.assertFalse(output.exists())

    def test_dreamina_image_dry_run_builds_text2image_command(self):
        with tempfile.TemporaryDirectory(prefix="godogen-dreamina-image.") as tmp:
            output = Path(tmp) / "assets" / "img" / "dreamina.png"
            proc = run_asset_gen(
                [
                    "image",
                    "--provider",
                    "dreamina",
                    "--dry-run",
                    "--prompt",
                    "top down grass tile",
                    "--size",
                    "1K",
                    "--aspect-ratio",
                    "16:9",
                    "--poll",
                    "3",
                    "-o",
                    str(output),
                ]
            )

            self.assertEqual(proc.returncode, 0, proc.stderr)
            result = parse_json_stdout(proc)
            self.assertTrue(result["ok"])
            self.assertTrue(result["dry_run"])
            self.assertEqual(result["provider"], "dreamina")
            command = result["command"]
            self.assertEqual(command[:2], ["dreamina", "text2image"])
            self.assertIn("--ratio=16:9", command)
            self.assertIn("--resolution_type=1k", command)
            self.assertIn("--poll=3", command)

    def test_dreamina_image_nonzero_submit_id_returns_pending(self):
        with tempfile.TemporaryDirectory(prefix="godogen-dreamina-pending-image.") as tmp:
            tmp_path = Path(tmp)
            fake_dreamina = tmp_path / "dreamina"
            write_fake_dreamina(fake_dreamina, submit_key="submitId", submit_id="image-submit-123", exit_code=43)
            output = tmp_path / "assets" / "img" / "dreamina.png"

            proc = run_asset_gen(
                [
                    "image",
                    "--provider",
                    "dreamina",
                    "--prompt",
                    "top down grass tile",
                    "--poll",
                    "3",
                    "-o",
                    str(output),
                ],
                env={"GODOGEN_DREAMINA_BIN": str(fake_dreamina)},
            )

            self.assertEqual(proc.returncode, 1)
            result = parse_json_stdout(proc)
            self.assertFalse(result["ok"])
            self.assertTrue(result["pending"])
            self.assertEqual(result["provider"], "dreamina")
            self.assertEqual(result["submit_id"], "image-submit-123")
            self.assertIn("query_result", result["error"])
            self.assertFalse(output.exists())

    def test_dreamina_image2image_requires_existing_reference_image(self):
        with tempfile.TemporaryDirectory(prefix="godogen-dreamina-missing-reference.") as tmp:
            tmp_path = Path(tmp)
            missing = tmp_path / "refs" / "missing.png"
            output = tmp_path / "assets" / "img" / "dreamina_edit.png"

            proc = run_asset_gen(
                [
                    "image",
                    "--provider",
                    "dreamina",
                    "--dry-run",
                    "--prompt",
                    "turn the grass tile into snow",
                    "--image",
                    str(missing),
                    "-o",
                    str(output),
                ]
            )

            self.assertEqual(proc.returncode, 1)
            result = parse_json_stdout(proc)
            self.assertFalse(result["ok"])
            self.assertEqual(result["provider"], "dreamina")
            self.assertIn("Reference image not found", result["error"])
            self.assertIn(str(missing), result["error"])
            self.assertFalse(output.exists())

    def test_dreamina_non_pending_failures_redact_raw_cli_output(self):
        with tempfile.TemporaryDirectory(prefix="godogen-dreamina-redact.") as tmp:
            tmp_path = Path(tmp)
            fake_dreamina = tmp_path / "dreamina"
            fake_dreamina.write_text(
                "#!/bin/sh\n"
                "printf 'account=user@example.test token=dreamina-token-secret balance=999\\n'\n"
                "printf 'stderr api_key=sk-dreamina-secret session=dreamina-session-secret\\n' >&2\n"
                "exit 44\n"
            )
            fake_dreamina.chmod(0o755)
            first_frame = tmp_path / "assets" / "img" / "first.png"
            first_frame.parent.mkdir(parents=True)
            first_frame.write_bytes(PNG_1X1)

            cases = [
                (
                    "video",
                    [
                        "video",
                        "--provider",
                        "dreamina",
                        "--prompt",
                        "slow camera push in",
                        "--image",
                        str(first_frame),
                        "--duration",
                        "4",
                        "--resolution",
                        "720p",
                        "-o",
                        str(tmp_path / "assets" / "video" / "failed.mp4"),
                    ],
                ),
                (
                    "image",
                    [
                        "image",
                        "--provider",
                        "dreamina",
                        "--prompt",
                        "top down grass tile",
                        "-o",
                        str(tmp_path / "assets" / "img" / "failed.png"),
                    ],
                ),
            ]

            for label, args in cases:
                with self.subTest(label=label):
                    proc = run_asset_gen(args, env={"GODOGEN_DREAMINA_BIN": str(fake_dreamina)})
                    self.assertEqual(proc.returncode, 1)
                    result = parse_json_stdout(proc)
                    self.assertFalse(result["ok"])
                    self.assertEqual(result["provider"], "dreamina")
                    self.assertIn("Dreamina", result["error"])
                    combined = proc.stdout + proc.stderr
                    for secret in [
                        "user@example.test",
                        "dreamina-token-secret",
                        "sk-dreamina-secret",
                        "dreamina-session-secret",
                        "balance=999",
                    ]:
                        self.assertNotIn(secret, combined)

    def test_help_no_longer_exposes_direct_api_key_providers(self):
        for subcommand in ("image", "texture", "video"):
            with self.subTest(subcommand=subcommand):
                proc = run_asset_gen([subcommand, "--help"])

                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertNotIn("openai", proc.stdout)
                self.assertNotIn("grok", proc.stdout)
                self.assertNotIn("gemini", proc.stdout)
                self.assertIn("codex", proc.stdout)

    def test_codex_image_provider_queues_task_without_api_key(self):
        with tempfile.TemporaryDirectory(prefix="godogen-codex-image.") as tmp:
            output = Path(tmp) / "assets" / "img" / "codex.png"
            proc = run_asset_gen(
                [
                    "image",
                    "--provider",
                    "codex",
                    "--prompt",
                    "clean top-down cobblestone game texture",
                    "--aspect-ratio",
                    "16:9",
                    "-o",
                    str(output),
                ],
                env={
                    "OPENAI_API_KEY": "sk-test-secret-value",
                    "GOOGLE_API_KEY": "google-secret-value",
                    "XAI_API_KEY": "xai-secret-value",
                },
            )

            self.assertEqual(proc.returncode, 1)
            result = parse_json_stdout(proc)
            self.assertFalse(result["ok"])
            self.assertTrue(result["pending"])
            self.assertEqual(result["provider"], "codex")
            self.assertEqual(result["target_path"], str(output))
            task_path = Path(result["task_path"])
            self.assertTrue(task_path.exists())
            task = json.loads(task_path.read_text())
            self.assertEqual(task["provider"], "codex")
            self.assertEqual(task["task_type"], "image")
            self.assertEqual(task["prompt"], "clean top-down cobblestone game texture")
            self.assertEqual(task["target_path"], str(output))
            self.assertEqual(task["status"], "pending")
            self.assertFalse(output.exists())
            combined = proc.stdout + proc.stderr + task_path.read_text()
            self.assertNotIn("sk-test-secret-value", combined)
            self.assertNotIn("google-secret-value", combined)
            self.assertNotIn("xai-secret-value", combined)

    def test_codex_image_provider_records_reference_image_task(self):
        with tempfile.TemporaryDirectory(prefix="godogen-codex-edit.") as tmp:
            source = Path(tmp) / "refs" / "source.png"
            output = Path(tmp) / "assets" / "img" / "codex_edit.png"
            source.parent.mkdir(parents=True)
            source.write_bytes(PNG_1X1)

            proc = run_asset_gen(
                [
                    "image",
                    "--provider",
                    "codex",
                    "--prompt",
                    "turn the grass tile into snow",
                    "--image",
                    str(source),
                    "-o",
                    str(output),
                ]
            )

            self.assertEqual(proc.returncode, 1)
            result = parse_json_stdout(proc)
            self.assertFalse(result["ok"])
            self.assertTrue(result["pending"])
            task = json.loads(Path(result["task_path"]).read_text())
            self.assertEqual(task["source_image"], str(source))
            self.assertEqual(task["task_type"], "image")

    def test_codex_video_provider_queues_task_with_reference_image(self):
        with tempfile.TemporaryDirectory(prefix="godogen-codex-video.") as tmp:
            first_frame = Path(tmp) / "assets" / "img" / "first.png"
            output = Path(tmp) / "assets" / "video" / "codex.mp4"
            first_frame.parent.mkdir(parents=True)
            first_frame.write_bytes(PNG_1X1)

            proc = run_asset_gen(
                [
                    "video",
                    "--provider",
                    "codex",
                    "--prompt",
                    "slow camera push across a stone floor",
                    "--image",
                    str(first_frame),
                    "--duration",
                    "4",
                    "--resolution",
                    "720p",
                    "--poll",
                    "2",
                    "-o",
                    str(output),
                ]
            )

            self.assertEqual(proc.returncode, 1)
            result = parse_json_stdout(proc)
            self.assertFalse(result["ok"])
            self.assertTrue(result["pending"])
            self.assertEqual(result["provider"], "codex")
            task = json.loads(Path(result["task_path"]).read_text())
            self.assertEqual(task["task_type"], "video")
            self.assertEqual(task["source_image"], str(first_frame))
            self.assertEqual(task["duration"], 4)
            self.assertEqual(task["resolution"], "720p")

    def test_texture_defaults_to_procedural_tile(self):
        with tempfile.TemporaryDirectory(prefix="godogen-texture-procedural.") as tmp:
            output = Path(tmp) / "assets" / "img" / "tile.png"
            proc = run_asset_gen(
                [
                    "texture",
                    "--prompt",
                    "simple stone floor",
                    "-o",
                    str(output),
                ]
            )

            self.assertEqual(proc.returncode, 0, proc.stderr)
            result = parse_json_stdout(proc)
            self.assertTrue(result["ok"])
            self.assertEqual(result["provider"], "procedural")
            self.assertEqual(result["path"], str(output))
            self.assertEqual(output.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")

    def test_texture_can_queue_codex_image_task(self):
        with tempfile.TemporaryDirectory(prefix="godogen-texture-codex.") as tmp:
            output = Path(tmp) / "assets" / "img" / "texture.png"
            proc = run_asset_gen(
                [
                    "texture",
                    "--provider",
                    "codex",
                    "--prompt",
                    "seamless wet cobblestone game texture",
                    "--aspect-ratio",
                    "1:1",
                    "-o",
                    str(output),
                ]
            )

            self.assertEqual(proc.returncode, 1)
            result = parse_json_stdout(proc)
            self.assertFalse(result["ok"])
            self.assertTrue(result["pending"])
            self.assertEqual(result["provider"], "codex")
            task = json.loads(Path(result["task_path"]).read_text())
            self.assertEqual(task["task_type"], "texture")
            self.assertEqual(task["target_path"], str(output))


if __name__ == "__main__":
    unittest.main()
