import os
import subprocess
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


if __name__ == "__main__":
    unittest.main()
