import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CLI = REPO_ROOT / "bin" / "godogen-ddm"


class GodogenDdmCliTests(unittest.TestCase):
    def test_check_env_reports_key_status_without_values(self):
        env = os.environ.copy()
        env["OPENAI_API_KEY"] = "sk-test-secret-value"
        env["GODOGEN_IMAGE_PROVIDER"] = "procedural"

        proc = subprocess.run(
            [str(CLI), "check-env"],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("dotnet:", proc.stdout)
        self.assertIn("godot:", proc.stdout)
        self.assertIn("magick:", proc.stdout)
        self.assertIn("ffmpeg:", proc.stdout)
        self.assertIn("dreamina:", proc.stdout)
        self.assertIn("GODOGEN_IMAGE_PROVIDER=set", proc.stdout)
        self.assertIn("OPENAI_API_KEY=set", proc.stdout)
        self.assertNotIn("sk-test-secret-value", proc.stdout)

    def test_publish_godot_codex_generates_runtime_layout(self):
        with tempfile.TemporaryDirectory(prefix="godogen-ddm-publish.") as tmp:
            proc = subprocess.run(
                [
                    str(CLI),
                    "publish",
                    "--engine",
                    "godot",
                    "--agent",
                    "codex",
                    "--out",
                    tmp,
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(proc.returncode, 0, proc.stderr)
            root = Path(tmp)
            self.assertTrue((root / "AGENTS.md").exists())
            self.assertTrue((root / ".agents" / "skills" / "godogen" / "SKILL.md").exists())
            self.assertTrue((root / ".agents" / "skills" / "godot-api" / "SKILL.md").exists())
            self.assertTrue((root / ".codex" / "hooks" / "capture_result.sh").exists())

            output = root / "assets" / "img" / "runtime_checker.png"
            asset_proc = subprocess.run(
                [
                    sys.executable,
                    str(root / ".agents" / "skills" / "godogen" / "tools" / "asset_gen.py"),
                    "texture",
                    "--prompt",
                    "runtime checker",
                    "--procedural-kind",
                    "checker",
                    "-o",
                    str(output),
                ],
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(asset_proc.returncode, 0, asset_proc.stderr)
            result = json.loads(asset_proc.stdout)
            self.assertTrue(result["ok"])
            self.assertEqual(result["provider"], "procedural")
            self.assertEqual(output.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")

    def test_smoke_runs_provider_and_godot_csharp_checks(self):
        proc = subprocess.run(
            [str(CLI), "smoke"],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("godot-csharp: ok", proc.stdout)
        self.assertIn("smoke: ok", proc.stdout)

    def test_external_smoke_defaults_to_non_paid_dry_run_without_leaking_keys(self):
        env = os.environ.copy()
        env["OPENAI_API_KEY"] = "sk-test-secret-value"
        env["TRIPO3D_API_KEY"] = "tripo-secret-value"

        with tempfile.TemporaryDirectory(prefix="godogen-ddm-external-dry.") as tmp:
            proc = subprocess.run(
                [str(CLI), "external-smoke", "--out", tmp],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("external-smoke: dry-run", proc.stdout)
            self.assertIn("dreamina-video: dry-run", proc.stdout)
            self.assertIn("openai-image: dry-run", proc.stdout)
            self.assertIn("openai-video: dry-run", proc.stdout)
            self.assertIn("tripo3d-glb: skipped", proc.stdout)
            self.assertIn("--yes-charge", proc.stdout)
            self.assertNotIn("sk-test-secret-value", proc.stdout)
            self.assertNotIn("tripo-secret-value", proc.stdout)

    def test_external_smoke_yes_charge_requires_credentials(self):
        env = os.environ.copy()
        env.pop("OPENAI_API_KEY", None)
        env.pop("TRIPO3D_API_KEY", None)
        env["GODOGEN_DREAMINA_BIN"] = str(REPO_ROOT / "missing-dreamina")

        proc = subprocess.run(
            [str(CLI), "external-smoke", "--yes-charge"],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(proc.returncode, 2)
        self.assertIn("OPENAI_API_KEY=missing", proc.stderr)
        self.assertIn("TRIPO3D_API_KEY=missing", proc.stderr)
        self.assertIn("dreamina=missing", proc.stderr)

    def test_external_smoke_yes_charge_can_run_against_fake_asset_provider(self):
        with tempfile.TemporaryDirectory(prefix="godogen-ddm-external-paid.") as tmp:
            root = Path(tmp)
            fake_asset = root / "fake_asset_gen.py"
            fake_asset.write_text(
                "import json, sys\n"
                "from pathlib import Path\n"
                "args = sys.argv[1:]\n"
                "out = Path(args[args.index('-o') + 1])\n"
                "out.parent.mkdir(parents=True, exist_ok=True)\n"
                "if args[0] in {'image', 'texture'}:\n"
                "    out.write_bytes(bytes.fromhex('89504e470d0a1a0a0000000d4948445200000001000000010802000000907753de0000000c49444154789c63606060000000040001f61738550000000049454e44ae426082'))\n"
                "elif args[0] == 'video':\n"
                "    out.write_bytes(b'fake mp4')\n"
                "elif args[0] == 'glb':\n"
                "    out.write_bytes(b'fake glb')\n"
                "print(json.dumps({'ok': True, 'path': str(out), 'cost_cents': 0}))\n"
            )
            fake_dreamina = root / "dreamina"
            fake_dreamina.write_text("#!/bin/sh\nexit 0\n")
            fake_dreamina.chmod(0o755)

            env = os.environ.copy()
            env["GODOGEN_DDM_ASSET_GEN"] = str(fake_asset)
            env["GODOGEN_DREAMINA_BIN"] = str(fake_dreamina)
            env["OPENAI_API_KEY"] = "sk-test-secret-value"
            env["TRIPO3D_API_KEY"] = "tripo-secret-value"

            proc = subprocess.run(
                [str(CLI), "external-smoke", "--yes-charge", "--out", str(root / "out"), "--poll", "1"],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("external-smoke: paid-run", proc.stdout)
            self.assertIn("dreamina-video: ok", proc.stdout)
            self.assertIn("openai-image: ok", proc.stdout)
            self.assertIn("openai-video: ok", proc.stdout)
            self.assertIn("tripo3d-glb: ok", proc.stdout)
            self.assertNotIn("sk-test-secret-value", proc.stdout)
            self.assertNotIn("tripo-secret-value", proc.stdout)

    def test_external_smoke_yes_charge_summarizes_pending_provider(self):
        with tempfile.TemporaryDirectory(prefix="godogen-ddm-external-pending.") as tmp:
            root = Path(tmp)
            fake_asset = root / "fake_asset_gen.py"
            fake_asset.write_text(
                "import json, sys\n"
                "from pathlib import Path\n"
                "args = sys.argv[1:]\n"
                "out = Path(args[args.index('-o') + 1])\n"
                "out.parent.mkdir(parents=True, exist_ok=True)\n"
                "provider = args[args.index('--provider') + 1] if '--provider' in args else 'procedural'\n"
                "if args[0] == 'video' and provider == 'dreamina':\n"
                "    print(json.dumps({'ok': False, 'pending': True, 'provider': 'dreamina', 'submit_id': 'dreamina-submit-123', 'error': 'pending'}))\n"
                "    sys.exit(1)\n"
                "if args[0] in {'image', 'texture'}:\n"
                "    out.write_bytes(bytes.fromhex('89504e470d0a1a0a0000000d4948445200000001000000010802000000907753de0000000c49444154789c63606060000000040001f61738550000000049454e44ae426082'))\n"
                "elif args[0] == 'video':\n"
                "    out.write_bytes(b'fake mp4')\n"
                "elif args[0] == 'glb':\n"
                "    out.write_bytes(b'fake glb')\n"
                "print(json.dumps({'ok': True, 'path': str(out), 'cost_cents': 0}))\n"
            )
            fake_dreamina = root / "dreamina"
            fake_dreamina.write_text("#!/bin/sh\nexit 0\n")
            fake_dreamina.chmod(0o755)

            env = os.environ.copy()
            env["GODOGEN_DDM_ASSET_GEN"] = str(fake_asset)
            env["GODOGEN_DREAMINA_BIN"] = str(fake_dreamina)
            env["OPENAI_API_KEY"] = "sk-test-secret-value"
            env["TRIPO3D_API_KEY"] = "tripo-secret-value"

            proc = subprocess.run(
                [str(CLI), "external-smoke", "--yes-charge", "--out", str(root / "out"), "--poll", "1"],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(proc.returncode, 1)
            self.assertIn("external-smoke: incomplete", proc.stdout)
            self.assertIn("dreamina-video: pending", proc.stdout)
            self.assertIn("dreamina-submit-123", proc.stdout)
            self.assertIn("openai-image: ok", proc.stdout)
            self.assertIn("openai-video: ok", proc.stdout)
            self.assertIn("tripo3d-glb: ok", proc.stdout)
            self.assertNotIn("sk-test-secret-value", proc.stdout)
            self.assertNotIn("tripo-secret-value", proc.stdout)


if __name__ == "__main__":
    unittest.main()
