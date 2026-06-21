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


if __name__ == "__main__":
    unittest.main()
