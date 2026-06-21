import base64
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
                env={"GODOGEN_IMAGE_PROVIDER": "gemini"},
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

    def test_openai_image_dry_run_builds_images_api_request(self):
        with tempfile.TemporaryDirectory(prefix="godogen-openai-image.") as tmp:
            output = Path(tmp) / "assets" / "img" / "openai.png"
            proc = run_asset_gen(
                [
                    "image",
                    "--provider",
                    "openai",
                    "--dry-run",
                    "--prompt",
                    "clean top-down cobblestone game texture",
                    "--aspect-ratio",
                    "16:9",
                    "-o",
                    str(output),
                ]
            )

            self.assertEqual(proc.returncode, 0, proc.stderr)
            result = parse_json_stdout(proc)
            self.assertTrue(result["ok"])
            self.assertTrue(result["dry_run"])
            self.assertEqual(result["provider"], "openai")
            self.assertEqual(result["path"], str(output))
            request = result["request"]
            self.assertEqual(request["url"], "https://api.openai.com/v1/images/generations")
            self.assertEqual(request["payload"]["prompt"], "clean top-down cobblestone game texture")
            self.assertEqual(request["payload"]["size"], "1536x1024")
            self.assertEqual(request["payload"]["output_format"], "png")

    def test_openai_image_edit_dry_run_builds_edits_api_request(self):
        with tempfile.TemporaryDirectory(prefix="godogen-openai-edit.") as tmp:
            source = Path(tmp) / "refs" / "source.png"
            output = Path(tmp) / "assets" / "img" / "openai_edit.png"
            source.parent.mkdir(parents=True)
            source.write_bytes(PNG_1X1)

            proc = run_asset_gen(
                [
                    "image",
                    "--provider",
                    "openai",
                    "--dry-run",
                    "--prompt",
                    "turn the grass tile into snow",
                    "--image",
                    str(source),
                    "-o",
                    str(output),
                ]
            )

            self.assertEqual(proc.returncode, 0, proc.stderr)
            result = parse_json_stdout(proc)
            self.assertTrue(result["ok"])
            self.assertTrue(result["dry_run"])
            self.assertEqual(result["provider"], "openai")
            request = result["request"]
            self.assertEqual(request["url"], "https://api.openai.com/v1/images/edits")
            self.assertEqual(request["payload"]["prompt"], "turn the grass tile into snow")
            self.assertEqual(request["payload"]["images"][0]["image_url"], f"data:image/png;base64,{base64.b64encode(PNG_1X1).decode()}")
            self.assertEqual(request["payload"]["output_format"], "png")

    def test_openai_video_dry_run_builds_videos_api_request(self):
        with tempfile.TemporaryDirectory(prefix="godogen-openai-video.") as tmp:
            first_frame = Path(tmp) / "assets" / "img" / "first.png"
            output = Path(tmp) / "assets" / "video" / "openai.mp4"
            first_frame.parent.mkdir(parents=True)
            first_frame.write_bytes(PNG_1X1)

            proc = run_asset_gen(
                [
                    "video",
                    "--provider",
                    "openai",
                    "--dry-run",
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

            self.assertEqual(proc.returncode, 0, proc.stderr)
            result = parse_json_stdout(proc)
            self.assertTrue(result["ok"])
            self.assertTrue(result["dry_run"])
            self.assertEqual(result["provider"], "openai")
            self.assertEqual(result["path"], str(output))
            request = result["request"]
            self.assertEqual(request["url"], "https://api.openai.com/v1/videos")
            self.assertEqual(request["poll_url"], "https://api.openai.com/v1/videos/{video_id}")
            self.assertEqual(request["download_url"], "https://api.openai.com/v1/videos/{video_id}/content")
            self.assertEqual(request["payload"]["model"], "sora-2")
            self.assertEqual(request["payload"]["prompt"], "slow camera push across a stone floor")
            self.assertEqual(request["payload"]["seconds"], "4")
            self.assertEqual(request["payload"]["size"], "1280x720")
            self.assertEqual(
                request["payload"]["input_reference"]["image_url"],
                f"data:image/png;base64,{base64.b64encode(PNG_1X1).decode()}",
            )
            self.assertIn("deprecation", result)
            self.assertIn("September 24, 2026", result["deprecation"])

    def test_openai_video_env_provider_dry_run(self):
        with tempfile.TemporaryDirectory(prefix="godogen-openai-video-env.") as tmp:
            first_frame = Path(tmp) / "assets" / "img" / "first.png"
            output = Path(tmp) / "assets" / "video" / "openai.mp4"
            first_frame.parent.mkdir(parents=True)
            first_frame.write_bytes(PNG_1X1)

            proc = run_asset_gen(
                [
                    "video",
                    "--dry-run",
                    "--prompt",
                    "slow camera push",
                    "--image",
                    str(first_frame),
                    "--duration",
                    "8",
                    "--resolution",
                    "720p",
                    "-o",
                    str(output),
                ],
                env={"GODOGEN_VIDEO_PROVIDER": "openai"},
            )

            self.assertEqual(proc.returncode, 0, proc.stderr)
            result = parse_json_stdout(proc)
            self.assertTrue(result["ok"])
            self.assertEqual(result["provider"], "openai")
            self.assertEqual(result["request"]["payload"]["seconds"], "8")

    def test_openai_video_rejects_unsupported_duration(self):
        with tempfile.TemporaryDirectory(prefix="godogen-openai-video-duration.") as tmp:
            first_frame = Path(tmp) / "assets" / "img" / "first.png"
            output = Path(tmp) / "assets" / "video" / "openai.mp4"
            first_frame.parent.mkdir(parents=True)
            first_frame.write_bytes(PNG_1X1)

            proc = run_asset_gen(
                [
                    "video",
                    "--provider",
                    "openai",
                    "--dry-run",
                    "--prompt",
                    "slow camera push",
                    "--image",
                    str(first_frame),
                    "--duration",
                    "5",
                    "--resolution",
                    "720p",
                    "-o",
                    str(output),
                ]
            )

            self.assertEqual(proc.returncode, 1)
            result = parse_json_stdout(proc)
            self.assertFalse(result["ok"])
            self.assertEqual(result["provider"], "openai")
            self.assertIn("4, 8, 12", result["error"])

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

    def test_texture_can_use_image_provider_dry_run(self):
        with tempfile.TemporaryDirectory(prefix="godogen-texture-openai.") as tmp:
            output = Path(tmp) / "assets" / "img" / "texture.png"
            proc = run_asset_gen(
                [
                    "texture",
                    "--provider",
                    "openai",
                    "--dry-run",
                    "--prompt",
                    "seamless wet cobblestone game texture",
                    "--aspect-ratio",
                    "1:1",
                    "-o",
                    str(output),
                ]
            )

            self.assertEqual(proc.returncode, 0, proc.stderr)
            result = parse_json_stdout(proc)
            self.assertTrue(result["ok"])
            self.assertTrue(result["dry_run"])
            self.assertEqual(result["provider"], "openai")
            self.assertEqual(result["request"]["url"], "https://api.openai.com/v1/images/generations")


if __name__ == "__main__":
    unittest.main()
