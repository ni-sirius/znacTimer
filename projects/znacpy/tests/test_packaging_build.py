import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "znactime_packaging_build", PROJECT_ROOT / "packaging" / "build.py"
)
packaging_build = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = packaging_build
_spec.loader.exec_module(packaging_build)


class PackagingBuildTest(unittest.TestCase):
    def test_supported_hosts_resolve_to_native_targets(self):
        self.assertEqual(
            packaging_build.detect_host("Windows", "AMD64"),
            "windows-x64",
        )
        self.assertEqual(
            packaging_build.detect_host("Darwin", "arm64"),
            "macos-arm64",
        )

    def test_unsupported_host_and_cross_compile_are_rejected(self):
        with self.assertRaisesRegex(packaging_build.BuildError, "Unsupported build host"):
            packaging_build.detect_host("Linux", "x86_64")
        with self.assertRaisesRegex(packaging_build.BuildError, "cannot be built"):
            packaging_build.resolve_target(
                "macos-arm64",
                system="Windows",
                machine="AMD64",
            )

    def test_pyinstaller_command_uses_shared_spec_and_target_paths(self):
        context = packaging_build.BuildContext(
            "windows-x64",
            "Windows",
            "AMD64",
            "0.6.0",
        )

        command = packaging_build._pyinstaller_command(context)

        self.assertEqual(command[:3], [packaging_build.sys.executable, "-m", "PyInstaller"])
        self.assertIn("--clean", command)
        self.assertIn("--noconfirm", command)
        self.assertEqual(Path(command[-1]), packaging_build.SPEC_PATH)
        self.assertIn(str(context.work_path), command)
        self.assertIn(str(context.dist_path), command)

    def test_shared_spec_embeds_the_existing_icon_in_native_bundles(self):
        spec_text = packaging_build.SPEC_PATH.read_text(encoding="utf-8")

        self.assertEqual(spec_text.count("icon=str(APP_ICON)"), 2)

    def test_manifest_records_reproducibility_inputs_without_absolute_paths(self):
        original_dist_root = packaging_build.DIST_ROOT
        try:
            with tempfile.TemporaryDirectory(dir=PROJECT_ROOT) as temporary:
                packaging_build.DIST_ROOT = Path(temporary)
                context = packaging_build.BuildContext(
                    "windows-x64",
                    "Windows",
                    "AMD64",
                    "0.6.0",
                )
                bundle = context.bundle_path
                bundle.mkdir(parents=True)
                (bundle / "znacTime.exe").write_bytes(b"executable")
                (bundle / "_internal").mkdir()
                (bundle / "_internal" / "runtime.dll").write_bytes(b"runtime")
                with (
                    patch.object(
                        packaging_build,
                        "_source_state",
                        return_value={"commit": "a" * 40, "dirty": False},
                    ),
                    patch.object(packaging_build, "_uv_version", return_value="uv 0.12.19"),
                    patch.object(
                        packaging_build.metadata,
                        "version",
                        return_value="6.22.3",
                    ),
                ):
                    manifest = packaging_build._manifest(context)

                encoded = json.dumps(manifest)
                self.assertEqual(manifest["build"]["target"], "windows-x64")
                self.assertEqual(manifest["bundle"]["file_count"], 2)
                self.assertEqual(manifest["application"]["version"], "0.6.0")
                self.assertNotIn(str(PROJECT_ROOT), encoded)
        finally:
            packaging_build.DIST_ROOT = original_dist_root

    def test_bundle_rejects_editable_environment_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary)
            metadata = bundle / "_internal" / "znactime-0.6.0.dist-info"
            metadata.mkdir(parents=True)
            (metadata / "METADATA").write_text("Version: 0.6.0\n", encoding="utf-8")

            packaging_build._validate_bundle(bundle)

            (metadata / "direct_url.json").write_text(
                '{"url": "file:///developer/checkout"}',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(packaging_build.BuildError, "unexpected editable"):
                packaging_build._validate_bundle(bundle)


if __name__ == "__main__":
    unittest.main()
