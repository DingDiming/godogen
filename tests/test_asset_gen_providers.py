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
