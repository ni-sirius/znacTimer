import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROJECT_ROOT.parents[1]
WORKFLOW_PATH = REPOSITORY_ROOT / ".github" / "workflows" / "znacpy-ci.yml"


class GitHubActionsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    def test_workflow_is_root_scoped_and_runs_on_main_push_or_manually(self):
        self.assertTrue(WORKFLOW_PATH.is_file())
        self.assertFalse((PROJECT_ROOT / ".github").exists())
        self.assertIn(
            "on:\n  push:\n    branches:\n      - main\n    paths:",
            self.workflow,
        )
        self.assertIn('      - "projects/znacpy/**"', self.workflow)
        self.assertIn('      - ".github/workflows/znacpy-ci.yml"', self.workflow)
        self.assertIn("  workflow_dispatch:", self.workflow)
        self.assertNotIn("pull_request:", self.workflow)
        self.assertIn("permissions:\n  contents: read", self.workflow)
        self.assertNotIn("pull_request_target:", self.workflow)

    def test_matrix_targets_windows_x64_and_macos_arm64(self):
        self.assertIn("target: windows-x64\n            runner: windows-2025", self.workflow)
        self.assertIn("target: macos-arm64\n            runner: macos-15", self.workflow)
        self.assertIn('$env:PROCESSOR_ARCHITECTURE -ne "AMD64"', self.workflow)
        self.assertIn('test "$(uname -m)" = "arm64"', self.workflow)
        self.assertIn("fail-fast: false", self.workflow)

    def test_actions_are_pinned_to_full_commit_shas(self):
        uses = re.findall(r"^\s*uses:\s*([^\s#]+)", self.workflow, re.MULTILINE)

        self.assertEqual(len(uses), 4)
        self.assertTrue(
            all(re.fullmatch(r"[^@]+@[0-9a-f]{40}", reference) for reference in uses)
        )

    def test_workflow_uses_central_pins_and_local_build_entry_points(self):
        self.assertIn("version-file: pyproject.toml", self.workflow)
        self.assertIn("working-directory: projects/znacpy", self.workflow)
        self.assertIn("uv sync --locked --group build", self.workflow)
        self.assertIn("packaging/native-tools.json", self.workflow)
        self.assertIn(r"scripts\build_windows.cmd --release", self.workflow)
        self.assertIn("bash scripts/build_macos.sh --release", self.workflow)

    def test_packaged_smoke_reports_and_unsigned_artifacts_are_uploaded(self):
        self.assertEqual(self.workflow.count("--smoke-test"), 2)
        self.assertIn("znactime-windows-x64-unsigned", self.workflow)
        self.assertIn("znactime-macos-arm64-unsigned", self.workflow)
        self.assertIn("windows-x64-Setup.exe.sha256", self.workflow)
        self.assertIn("macos-arm64.dmg.sha256", self.workflow)
        self.assertEqual(self.workflow.count("if-no-files-found: error"), 2)
        self.assertEqual(self.workflow.count("retention-days: 14"), 2)


if __name__ == "__main__":
    unittest.main()
