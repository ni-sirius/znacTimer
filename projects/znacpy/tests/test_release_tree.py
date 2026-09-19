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
            "README.md",
            "projects/znacpy/requirements.in",
            "projects/znacpy/requirements.txt",
            "projects/znacpy/requirements-dev.txt",
            "projects/znacpy/.vscode/settings.json",
            "projects/znacpy/tests/test_release_tree.py",
            "projects/znacpy/scripts/verify_legacy_import.py",
            "projects/otherplatform/README.md",
            "contracts/README.md",
            "contracts/schemas/README.md",
            "contracts/fixtures/README.md",
            "scripts/check_release_tree.py",
            "projects/znacpy/znactime/storage/sqlite/repository.py",
            "projects/znacpy/znactime/ui/qt/themes/dark.json",
            "docs/DATABASE_SCHEMA.md",
            "docs/images/dashboard.png",
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

    def test_working_tree_includes_new_sources_and_force_added_ignored_data(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            def git(*args):
                subprocess.run(
                    ("git", *args), cwd=root, check=True, capture_output=True
                )

            git("init", "--quiet")
            (root / ".gitignore").write_text("*.db\n", encoding="utf-8")
            (root / "README.md").write_text("Original", encoding="utf-8")
            (root / "private.db").write_bytes(b"private fixture")
            (root / "ignored.db").write_bytes(b"ignored fixture")
            git("add", ".gitignore", "README.md")
            git("add", "--force", "private.db")
            (root / "README.md").rename(root / "new.md")

            self.assertEqual(
                set(tracked_files(root)), {".gitignore", "README.md", "private.db"}
            )
            self.assertEqual(
                set(tracked_files(root, working_tree=True)),
                {".gitignore", "new.md", "private.db"},
            )
            self.assertFalse(is_release_source("private.db"))


if __name__ == "__main__":
    unittest.main()
