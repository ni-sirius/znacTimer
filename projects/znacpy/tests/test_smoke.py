import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from znactime.__main__ import main
from znactime import smoke


class SmokeModeTest(unittest.TestCase):
    def test_real_smoke_checks_pass_with_temporary_artifacts(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            report = smoke.run_smoke_test(workspace)

            self.assertTrue((workspace / "smoke.db").is_file())
            self.assertTrue((workspace / "smoke.pdf").is_file())

        self.assertTrue(report["success"])
        self.assertEqual(
            set(report["checks"]),
            {"isolation", "qt", "sqlite", "themes", "pdf"},
        )
        self.assertTrue(
            all(check["status"] == "passed" for check in report["checks"].values())
        )
        self.assertFalse(workspace.exists())

    def test_failed_check_is_reported_and_returns_failure(self):
        def fail(_workspace, _runtime):
            raise RuntimeError("diagnostic failure")

        with tempfile.TemporaryDirectory() as temporary, patch.object(
            smoke, "_CHECKS", (("qt", fail),)
        ):
            report = smoke.run_smoke_test(temporary)

        self.assertFalse(report["success"])
        self.assertEqual(report["checks"]["qt"]["status"], "failed")
        self.assertEqual(
            report["checks"]["qt"]["error"],
            {"message": "diagnostic failure", "type": "RuntimeError"},
        )

    def test_nonempty_data_directory_is_rejected_without_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            existing = workspace / "existing.db"
            existing.write_bytes(b"user data")

            report = smoke.run_smoke_test(workspace)

            self.assertFalse(report["success"])
            self.assertEqual(report["checks"]["isolation"]["status"], "failed")
            self.assertEqual(existing.read_bytes(), b"user data")
            self.assertEqual(tuple(workspace.iterdir()), (existing,))

    def test_cli_prints_and_writes_the_same_json_report(self):
        expected = {
            "checks": {"qt": {"status": "passed"}},
            "success": True,
        }
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "reports" / "smoke.json"
            stream = io.StringIO()
            with (
                patch.object(smoke, "run_smoke_test", return_value=expected),
                patch.object(smoke.sys, "stdout", stream),
            ):
                result = smoke.cli_main(
                    [
                        "--smoke-test",
                        "--data-dir",
                        temporary,
                        "--report",
                        str(output),
                    ]
                )

            self.assertEqual(result, 0)
            self.assertEqual(json.loads(stream.getvalue()), expected)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), expected)

    def test_cli_returns_failure_and_still_writes_report(self):
        expected = {
            "checks": {"qt": {"status": "failed"}},
            "success": False,
        }
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "smoke.json"
            with (
                patch.object(smoke, "run_smoke_test", return_value=expected),
                patch.object(smoke.sys, "stdout", io.StringIO()),
            ):
                result = smoke.cli_main(
                    [
                        "--smoke-test",
                        "--data-dir",
                        temporary,
                        "--report",
                        str(output),
                    ]
                )

            self.assertEqual(result, 1)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), expected)

    def test_application_entry_point_dispatches_before_gui_startup(self):
        with (
            patch.object(smoke, "cli_main", return_value=0) as smoke_main,
            patch("znactime.__main__.QApplication") as application,
        ):
            result = main(argv=["--smoke-test"])

        self.assertEqual(result, 0)
        smoke_main.assert_called_once_with(["--smoke-test"])
        application.assert_not_called()


if __name__ == "__main__":
    unittest.main()
