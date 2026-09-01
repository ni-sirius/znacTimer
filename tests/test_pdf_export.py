import tempfile
import unittest
from pathlib import Path

from znactime.core.models import MonthStats
from znactime.storage.errors import StorageConflict
from znactime.storage.pdf_export import export_pdf


class PdfExportTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.stats = MonthStats(year=2024, month="June", overtime=1.5)

    def tearDown(self):
        self.temporary.cleanup()

    def test_pdf_export_is_atomic_and_requires_explicit_overwrite(self):
        target = self.root / "report.pdf"
        export_pdf(self.stats, target)
        original = target.read_bytes()
        self.assertTrue(original.startswith(b"%PDF"))

        with self.assertRaises(FileExistsError):
            export_pdf(self.stats, target)
        self.assertEqual(target.read_bytes(), original)

        export_pdf(self.stats, target, overwrite=True)
        self.assertTrue(target.read_bytes().startswith(b"%PDF"))

    def test_pdf_export_rejects_a_protected_destination(self):
        protected = self.root / "active.db"
        protected.write_bytes(b"database")

        with self.assertRaises(StorageConflict):
            export_pdf(
                self.stats,
                protected,
                overwrite=True,
                protected_paths=(protected,),
            )

        self.assertEqual(protected.read_bytes(), b"database")


if __name__ == "__main__":
    unittest.main()
