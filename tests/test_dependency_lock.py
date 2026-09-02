import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCK_ENTRY = re.compile(
    r"^([a-z0-9-]+)==([^\s\\]+)\s+\\\s*$\n"
    r"^\s+--hash=sha256:([0-9a-f]{64})$",
    re.MULTILINE,
)


class DependencyLockTest(unittest.TestCase):
    def test_runtime_lock_is_exact_binary_only_and_hash_verified(self):
        lock_text = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        entries = {
            name: (version, digest)
            for name, version, digest in LOCK_ENTRY.findall(lock_text)
        }

        self.assertIn("--only-binary=:all:", lock_text)
        self.assertIn("--require-hashes", lock_text)
        self.assertEqual(
            entries,
            {
                "charset-normalizer": (
                    "3.4.4",
                    "a79cfe37875f822425b89a82333404539ae63dbdddf97f84dcbc3d339aae9525",
                ),
                "pillow": (
                    "12.1.0",
                    "d70534cea9e7966169ad29a903b99fc507e932069a881d0965a1a84bb57f6c6d",
                ),
                "pyside6": (
                    "6.11.1",
                    "0968877ab1fb4ef3587a284da6fe05e8647ada56a6a3750b6395188e01f4aba6",
                ),
                "pyside6-addons": (
                    "6.11.1",
                    "0d13c4dfd671b050a48e4f8d8ddc724b7248f9c0437e7fc47fdf316278572923",
                ),
                "pyside6-essentials": (
                    "6.11.1",
                    "63311bd48e32c584599ab04b9ef7c324082374cd2c9fa533f978fb893bb47e40",
                ),
                "reportlab": (
                    "4.4.9",
                    "68e2d103ae8041a37714e8896ec9b79a1c1e911d68c3bd2ea17546568cf17bfd",
                ),
                "shiboken6": (
                    "6.11.1",
                    "c2c6863aa80ec18c0f82cea3417837b279cdc60024ac17123461dc9042577df7",
                ),
            },
        )

    def test_direct_dependencies_match_locked_versions(self):
        source_lines = {
            line.casefold()
            for line in (ROOT / "requirements.in").read_text(encoding="utf-8").splitlines()
            if line and not line.startswith("#")
        }
        lock_text = (ROOT / "requirements.txt").read_text(encoding="utf-8").casefold()

        self.assertEqual(source_lines, {"pyside6==6.11.1", "reportlab==4.4.9"})
        self.assertTrue(all(line in lock_text for line in source_lines))

    def test_development_entry_point_includes_production_lock(self):
        development = (ROOT / "requirements-dev.txt").read_text(encoding="utf-8")

        active_lines = [
            line.strip()
            for line in development.splitlines()
            if line.strip() and not line.startswith("#")
        ]
        self.assertEqual(active_lines, ["-r requirements.txt"])


if __name__ == "__main__":
    unittest.main()
