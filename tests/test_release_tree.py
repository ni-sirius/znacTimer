import unittest
from pathlib import Path

from scripts.check_release_tree import is_release_source, tracked_files


class ReleaseTreeTest(unittest.TestCase):
    def test_allowlist_accepts_reviewed_source_types(self):
        allowed = (
            "README.md",
            "requirements.in",
            "requirements.txt",
            "requirements-dev.txt",
            "tests/test_release_tree.py",
            "scripts/check_release_tree.py",
            "znactime/storage/sqlite/repository.py",
            "znactime/ui/qt/themes/dark.json",
            "docs/DATABASE_SCHEMA.md",
            "docs/images/dashboard.png",
        )

        self.assertTrue(all(is_release_source(path) for path in allowed))

    def test_allowlist_rejects_data_and_unreviewed_artifact_types(self):
        rejected = (
            "data/2024/2024_tmp_06.csv",
            "znactime.db",
            "tests/employment-history.csv",
            "docs/private-report.pdf",
            "znactime/ui/qt/assets/unreviewed.png",
            "dist/znactime.exe",
            "../outside.txt",
        )

        self.assertTrue(all(not is_release_source(path) for path in rejected))

    def test_current_tracked_tree_matches_allowlist(self):
        repository_root = Path(__file__).resolve().parents[1]
        rejected = tuple(
            path
            for path in tracked_files(repository_root)
            if not is_release_source(path)
        )

        self.assertEqual(rejected, ())


if __name__ == "__main__":
    unittest.main()
