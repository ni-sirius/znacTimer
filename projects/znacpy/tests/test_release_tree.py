import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location(
    "check_release_tree", REPOSITORY_ROOT / "scripts" / "check_release_tree.py"
)
_release_tree = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_release_tree)
is_release_source = _release_tree.is_release_source
tracked_files = _release_tree.tracked_files


class ReleaseTreeTest(unittest.TestCase):
    def test_allowlist_accepts_reviewed_source_types(self):
        allowed = (
            "projects/znacpy/.python-version",
            "projects/znacpy/pyproject.toml",
            "projects/znacpy/uv.lock",
            "projects/znacpy/.vscode/settings.json",
            "projects/znacpy/packaging/build.py",
            "projects/znacpy/packaging/launcher.py",
            "projects/znacpy/packaging/native-tools.json",
            "projects/znacpy/packaging/znactime.spec",
            "projects/znacpy/packaging/windows/znactime.ico",
            "projects/znacpy/packaging/windows/znactime.iss",
            "projects/znacpy/packaging/macos/znactime.icns",
            "projects/znacpy/packaging/macos/znactime.icon/icon.json",
            "projects/znacpy/packaging/macos/znactime.icon/Assets/artwork.png",
            "projects/znacpy/packaging/macos/entitlements.plist",
            "projects/znacpy/scripts/build_windows.cmd",
            "projects/znacpy/scripts/build_macos.sh",
            "projects/znacpy/scripts/run_dev.cmd",
            "projects/znacpy/scripts/run_dev.sh",
            "projects/znacpy/tests/test_release_tree.py",
            "projects/znacpy/scripts/verify_legacy_import.py",
            "projects/znacpy/znactime/storage/sqlite/repository.py",
            "projects/znacpy/znactime/ui/qt/themes/dark.json",
        )

        self.assertTrue(all(is_release_source(path) for path in allowed))

    def test_allowlist_rejects_data_and_unreviewed_artifact_types(self):
        rejected = (
            "projects/znacpy/data/2024/2024_tmp_06.csv",
            "projects/znacpy/znactime.db",
            "projects/znacpy/tests/employment-history.csv",
            "docs/private-report.pdf",
            "projects/znacpy/znactime/ui/qt/assets/unreviewed.png",
            "projects/znacpy/dist/znactime.exe",
            "projects/znacpy/build/output.py",
            "projects/znacpy/.venv/Lib/site-packages/package.py",
            "projects/znacpy/.native-tools/installer.exe",
            "projects/znacpy/packaging/unreviewed.json",
            "projects/znacpy/packaging/unreviewed.ico",
            "projects/znacpy/packaging/windows/compiler.exe",
            "projects/znacpy/packaging/windows/unreviewed.json",
            "projects/znacpy/packaging/macos/compiler.bin",
            "projects/znacpy/packaging/macos/unreviewed.json",
            "projects/znacpy/packaging/macos/znactime.icon/Assets/unreviewed.png",
            ".github/workflows/unreviewed.ps1",
            ".github/private-token.txt",
            "projects/znacpy/scripts/unreviewed.bat",
            "projects/znacpy/scripts/unreviewed.zsh",
            "projects/otherplatform/unreviewed.js",
            "contracts/fixtures/personal-records.csv",
            "requirements.txt",
            "znactime/__main__.py",
            "../outside.txt",
        )

        self.assertTrue(all(not is_release_source(path) for path in rejected))

    def test_current_working_tree_matches_allowlist(self):
        rejected = tuple(
            path
            for path in tracked_files(REPOSITORY_ROOT, working_tree=True)
            if not is_release_source(path)
        )

        self.assertEqual(rejected, ())

    def test_allowlist_is_limited_to_the_znacpy_project(self):
        outside_project = (
            "README.md", "LICENSE", ".gitattributes", ".vscode/settings.json",
            ".github/workflows/znacpy-ci.yml", "scripts/check_release_tree.py",
            "docs/DATABASE_SCHEMA.md", "docs/images/dashboard.png",
            "contracts/README.md", "projects/otherplatform/README.md",
            "projects/znac-expo/package.json", "projects/znacpy-extra/README.md",
        )

        self.assertTrue(all(not is_release_source(path) for path in outside_project))

    def test_scan_limits_both_modes_to_znacpy_and_keeps_new_and_force_added_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "projects" / "znacpy"
            project.mkdir(parents=True)

            def git(*args):
                subprocess.run(
                    ("git", *args), cwd=root, check=True, capture_output=True
                )

            git("init", "--quiet")
            (root / ".gitignore").write_text("*.db\n", encoding="utf-8")
            (project / "README.md").write_text("Original", encoding="utf-8")
            (project / "private.db").write_bytes(b"private fixture")
            (project / "ignored.db").write_bytes(b"ignored fixture")
            for name in (
                "README.md", "private.db", "projects/znac-expo/app.tsx",
                "projects/otherplatform/file.bin", "projects/znacpy-extra/file.py",
            ):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("Outside the desktop project", encoding="utf-8")
                git("add", "--force", name)
            git("add", ".gitignore", "projects/znacpy/README.md")
            git("add", "--force", "projects/znacpy/private.db")
            (project / "znactime").mkdir()
            (project / "README.md").rename(project / "znactime" / "new.py")
            (root / "projects" / "znac-expo" / "new.tsx").write_text("Other new file", encoding="utf-8")

            self.assertEqual(
                set(tracked_files(root)),
                {"projects/znacpy/README.md", "projects/znacpy/private.db"},
            )
            self.assertEqual(
                set(tracked_files(root, working_tree=True)),
                {"projects/znacpy/znactime/new.py", "projects/znacpy/private.db"},
            )
            self.assertTrue(is_release_source("projects/znacpy/znactime/new.py"))
            self.assertFalse(is_release_source("projects/znacpy/private.db"))


if __name__ == "__main__":
    unittest.main()
