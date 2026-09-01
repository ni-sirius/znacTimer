import os
import tempfile
import unittest
from pathlib import Path

from znactime.storage.atomic_file import (
    paths_refer_to_same_file,
    publish_staged_file,
    reject_protected_destination,
)
from znactime.storage.errors import StorageConflict


class AtomicFileTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def test_no_clobber_publish_is_complete_and_removes_staging_name(self):
        staged = self.root / ".report.tmp"
        target = self.root / "report.csv"
        staged.write_bytes(b"complete")

        publish_staged_file(staged, target, overwrite=False)

        self.assertEqual(target.read_bytes(), b"complete")
        self.assertFalse(staged.exists())

    def test_no_clobber_publish_preserves_destination_that_won_race(self):
        staged = self.root / ".report.tmp"
        target = self.root / "report.csv"
        staged.write_bytes(b"new")
        target.write_bytes(b"other process")

        with self.assertRaises(FileExistsError):
            publish_staged_file(staged, target, overwrite=False)

        self.assertEqual(target.read_bytes(), b"other process")
        self.assertEqual(staged.read_bytes(), b"new")

    def test_hard_link_is_recognized_as_a_protected_alias(self):
        protected = self.root / "database.db"
        alias = self.root / "database-hardlink.db"
        protected.write_bytes(b"sqlite")
        os.link(protected, alias)

        self.assertTrue(paths_refer_to_same_file(protected, alias))
        with self.assertRaises(StorageConflict):
            reject_protected_destination(alias, (protected,))

    def test_symlink_is_recognized_as_a_protected_alias(self):
        protected = self.root / "database.db"
        alias = self.root / "database-symlink.db"
        protected.write_bytes(b"sqlite")
        try:
            alias.symlink_to(protected)
        except OSError as error:
            self.skipTest(f"Symlink creation is unavailable: {error}")

        self.assertTrue(paths_refer_to_same_file(protected, alias))
        with self.assertRaises(StorageConflict):
            reject_protected_destination(alias, (protected,))

    @unittest.skipUnless(os.path.normcase("A") == os.path.normcase("a"), "case-sensitive OS")
    def test_case_alias_is_recognized_as_the_same_destination(self):
        protected = self.root / "database.db"
        protected.write_bytes(b"sqlite")

        with self.assertRaises(StorageConflict):
            reject_protected_destination(
                self.root / "DATABASE.DB",
                (protected,),
            )


if __name__ == "__main__":
    unittest.main()
