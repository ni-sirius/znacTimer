import importlib.util
import json
import plistlib
import struct
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
    @staticmethod
    def _write_windows_x64_executable(path):
        content = bytearray(0x88)
        content[0:2] = b"MZ"
        content[0x3C:0x40] = struct.pack("<I", 0x80)
        content[0x80:0x84] = b"PE\0\0"
        content[0x84:0x86] = struct.pack("<H", 0x8664)
        path.write_bytes(content)

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

    def test_uv_manifest_version_falls_back_to_central_project_pin(self):
        with (
            patch.object(packaging_build.shutil, "which", return_value=None),
            patch.object(packaging_build.Path, "is_file", return_value=False),
        ):
            version = packaging_build._uv_version()

        self.assertEqual(version, "uv 0.12.19 (required; not invoked)")

    def test_uv_version_accepts_build_metadata_for_the_pinned_version(self):
        detected = "uv 0.12.19 (bea138450 2026-09-24 x86_64-pc-windows-msvc)"
        with (
            patch.object(packaging_build.shutil, "which", return_value="uv"),
            patch.object(packaging_build, "_command_output", return_value=detected),
        ):
            version = packaging_build._uv_version()

        self.assertEqual(version, detected)

    def test_uv_version_rejects_a_different_semantic_version(self):
        detected = "uv 0.12.20 (different build)"
        with (
            patch.object(packaging_build.shutil, "which", return_value="uv"),
            patch.object(packaging_build, "_command_output", return_value=detected),
        ):
            with self.assertRaisesRegex(packaging_build.BuildError, "==0.12.19"):
                packaging_build._uv_version()

    def test_shared_spec_uses_native_icons_and_macos_entitlements(self):
        spec_text = packaging_build.SPEC_PATH.read_text(encoding="utf-8")

        self.assertIn(
            'icon=str(WINDOWS_ICON if TARGET == "windows-x64" else MACOS_ICON)',
            spec_text,
        )
        self.assertIn('exe_options["entitlements_file"] = str(MACOS_ENTITLEMENTS)', spec_text)
        self.assertIn("icon=str(MACOS_ICON)", spec_text)
        icon = packaging_build.WINDOWS_ICON_PATH.read_bytes()
        self.assertEqual(icon[:4], b"\0\0\1\0")
        self.assertEqual(struct.unpack("<H", icon[4:6])[0], 7)
        macos_icon = packaging_build.MACOS_ICON_PATH.read_bytes()
        self.assertEqual(macos_icon[:4], b"icns")
        entitlements = plistlib.loads(
            packaging_build.MACOS_ENTITLEMENTS_PATH.read_bytes()
        )
        self.assertEqual(entitlements, {})

    def test_macos_commands_verify_app_signature_and_create_compressed_dmg(self):
        context = packaging_build.BuildContext(
            "macos-arm64",
            "Darwin",
            "arm64",
            "0.6.0",
        )
        tools = packaging_build.MacOSTools(
            Path("/usr/bin/codesign"),
            Path("/usr/bin/ditto"),
            Path("/usr/bin/hdiutil"),
            Path("/usr/bin/xcodebuild"),
            "Xcode 18.0",
        )
        source_path = Path("/tmp/znactime-dmg")

        verify = packaging_build._codesign_verify_command(context, tools)
        create = packaging_build._hdiutil_create_command(context, tools, source_path)

        self.assertEqual(verify[1:5], ["--verify", "--deep", "--strict", "--verbose=2"])
        self.assertEqual(create[1:4], ["create", "-volname", "znacTime"])
        self.assertIn("-srcfolder", create)
        self.assertIn(str(source_path), create)
        self.assertIn("UDZO", create)
        self.assertEqual(Path(create[-1]), context.disk_image_path)

    def test_macos_dmg_creates_checksum_and_release_manifest(self):
        original_dist_root = packaging_build.DIST_ROOT
        original_release_root = packaging_build.RELEASE_ROOT
        try:
            with tempfile.TemporaryDirectory(dir=PROJECT_ROOT) as temporary:
                root = Path(temporary)
                packaging_build.DIST_ROOT = root / "bundle"
                packaging_build.RELEASE_ROOT = root / "release"
                context = packaging_build.BuildContext(
                    "macos-arm64",
                    "Darwin",
                    "arm64",
                    "0.6.0",
                )
                executable = context.bundle_path / "Contents" / "MacOS" / "znacTime"
                executable.parent.mkdir(parents=True)
                executable.write_bytes(b"Mach-O")
                context.manifest_path.write_text(
                    json.dumps({"tools": {"python": "3.12.14"}}),
                    encoding="utf-8",
                )
                tools = packaging_build.MacOSTools(
                    Path("/usr/bin/codesign"),
                    Path("/usr/bin/ditto"),
                    Path("/usr/bin/hdiutil"),
                    Path("/usr/bin/xcodebuild"),
                    "Xcode 18.0\nBuild version 18A1",
                )

                def create_disk_image(command, **kwargs):
                    if len(command) > 1 and command[1] == "create":
                        content = bytearray(1024)
                        content[-512:-508] = b"koly"
                        context.disk_image_path.write_bytes(content)

                with patch.object(
                    packaging_build.subprocess,
                    "run",
                    side_effect=create_disk_image,
                ) as run:
                    result = packaging_build.build_macos_dmg(context, tools)

                release_manifest = json.loads(
                    context.release_manifest_path.read_text(encoding="utf-8")
                )
                commands = [call.args[0] for call in run.call_args_list]
                staged_bundle = Path(commands[0][-1])
                self.assertEqual(result, context.disk_image_path)
                self.assertEqual(run.call_count, 4)
                self.assertEqual(commands[0][0], str(tools.ditto))
                self.assertEqual(staged_bundle.name, context.bundle_path.name)
                self.assertEqual(Path(commands[1][-1]), staged_bundle)
                source_index = commands[2].index("-srcfolder") + 1
                self.assertEqual(Path(commands[2][source_index]), staged_bundle.parent)
                self.assertEqual(
                    release_manifest["disk_image"]["path"],
                    context.disk_image_path.relative_to(PROJECT_ROOT).as_posix(),
                )
                self.assertEqual(release_manifest["signature"]["application"], "ad-hoc")
                self.assertEqual(release_manifest["tools"]["xcode"], tools.xcode_version)
                self.assertIn(
                    context.disk_image_name,
                    context.disk_image_checksum_path.read_text(),
                )
        finally:
            packaging_build.DIST_ROOT = original_dist_root
            packaging_build.RELEASE_ROOT = original_release_root

    def test_macos_dmg_creation_retries_transient_hdiutil_failure(self):
        context = packaging_build.BuildContext(
            "macos-arm64",
            "Darwin",
            "arm64",
            "0.6.0",
        )
        tools = packaging_build.MacOSTools(
            Path("/usr/bin/codesign"),
            Path("/usr/bin/ditto"),
            Path("/usr/bin/hdiutil"),
            Path("/usr/bin/xcodebuild"),
            "Xcode 18.0",
        )
        calls = 0

        def create_disk_image(command, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise packaging_build.subprocess.CalledProcessError(1, command)

        with (
            patch.object(
                packaging_build.subprocess,
                "run",
                side_effect=create_disk_image,
            ),
            patch.object(packaging_build.time, "sleep") as sleep,
        ):
            packaging_build._create_dmg_with_retries(
                context,
                tools,
                Path("/tmp/znactime-dmg"),
            )

        self.assertEqual(calls, 2)
        sleep.assert_called_once_with(2)

    def test_dmg_verification_requires_udif_trailer(self):
        with tempfile.TemporaryDirectory() as temporary:
            artifact = Path(temporary) / "znacTime.dmg"
            content = bytearray(512)
            content[0:4] = b"koly"
            artifact.write_bytes(content)

            packaging_build._validate_dmg(artifact)

            artifact.write_bytes(bytes(512))
            with self.assertRaisesRegex(packaging_build.BuildError, "UDIF trailer"):
                packaging_build._validate_dmg(artifact)

    def test_macos_package_rejects_non_macos_target(self):
        context = packaging_build.BuildContext(
            "windows-x64",
            "Windows",
            "AMD64",
            "0.6.0",
        )

        with self.assertRaisesRegex(packaging_build.BuildError, "only for macos-arm64"):
            packaging_build.validate_macos_package_inputs(context)

    def test_macos_scripts_are_thin_local_entry_points(self):
        run_script = (PROJECT_ROOT / "scripts" / "run_dev.sh").read_text(
            encoding="utf-8"
        )
        build_script = (PROJECT_ROOT / "scripts" / "build_macos.sh").read_text(
            encoding="utf-8"
        )

        self.assertTrue(run_script.startswith("#!/usr/bin/env bash\n"))
        self.assertIn('"$PROJECT_PYTHON" -m znactime "$@"', run_script)
        self.assertIn('"$(uname -s)" != "Darwin"', build_script)
        self.assertIn('"$(uname -m)" != "arm64"', build_script)
        self.assertIn("PACKAGE_ARGUMENTS=(--package)", build_script)
        self.assertIn("--target macos-arm64", build_script)
        self.assertIn('open "$APP_BUNDLE"', build_script)

    def test_inno_setup_definition_is_per_user_and_installs_the_full_bundle(self):
        definition = packaging_build.INNO_SETUP_SCRIPT_PATH.read_text(encoding="utf-8")

        self.assertIn("AppId={{B9DA5C75-3877-4A4B-BF19-2C8EF8D04EA1}", definition)
        self.assertIn("PrivilegesRequired=lowest", definition)
        self.assertIn(r"DefaultDirName={localappdata}\Programs\znacTime", definition)
        self.assertIn("SetupArchitecture=x64", definition)
        self.assertIn('Source: "{#BundleDir}\\*"', definition)
        self.assertIn(r'Name: "{autoprograms}\znacTime"', definition)
        self.assertNotIn("[UninstallDelete]", definition)

    def test_installer_command_uses_pinned_tool_and_release_paths(self):
        context = packaging_build.BuildContext(
            "windows-x64",
            "Windows",
            "AMD64",
            "0.6.0",
        )
        compiler = Path("C:/tools/ISCC.exe")

        command = packaging_build._inno_setup_command(context, compiler)

        self.assertEqual(packaging_build.INNO_SETUP_VERSION, "7.0.2")
        self.assertEqual(
            packaging_build.INNO_SETUP_VERSION,
            packaging_build.NATIVE_TOOLS["inno_setup"]["version"],
        )
        self.assertRegex(
            packaging_build.NATIVE_TOOLS["inno_setup"]["sha256"],
            r"^[0-9a-f]{64}$",
        )
        self.assertEqual(command[0], str(compiler))
        self.assertIn("/DAppVersion=0.6.0", command)
        self.assertIn(f"/DBundleDir={context.bundle_path}", command)
        self.assertIn(
            "/DOutputBaseFilename=znacTime-0.6.0-windows-x64-Setup",
            command,
        )

    def test_inno_setup_version_is_read_from_banner_and_latest_history_entry(self):
        with tempfile.TemporaryDirectory() as temporary:
            compiler = Path(temporary) / "ISCC.exe"
            compiler.write_bytes(b"compiler")
            (compiler.parent / "whatsnew.htm").write_text(
                '<span class="ver">7.0.2 </span><span class="date">date</span>\n'
                '<span class="ver">7.0.1 </span>',
                encoding="utf-8",
            )
            with patch.object(
                packaging_build,
                "_inno_setup_banner",
                return_value="Inno Setup 7 Command-Line Compiler",
            ):
                version = packaging_build.validate_inno_setup_compiler(compiler)

        self.assertEqual(version, "7.0.2")

    def test_windows_artifact_verification_requires_x64_pe(self):
        with tempfile.TemporaryDirectory() as temporary:
            artifact = Path(temporary) / "setup.exe"
            self._write_windows_x64_executable(artifact)

            packaging_build._validate_windows_x64_executable(artifact)

            content = bytearray(artifact.read_bytes())
            content[0x84:0x86] = struct.pack("<H", 0x014C)
            artifact.write_bytes(content)
            with self.assertRaisesRegex(packaging_build.BuildError, "not x64"):
                packaging_build._validate_windows_x64_executable(artifact)

    def test_installer_creates_checksum_and_release_manifest(self):
        original_dist_root = packaging_build.DIST_ROOT
        original_release_root = packaging_build.RELEASE_ROOT
        try:
            with tempfile.TemporaryDirectory(dir=PROJECT_ROOT) as temporary:
                root = Path(temporary)
                packaging_build.DIST_ROOT = root / "bundle"
                packaging_build.RELEASE_ROOT = root / "release"
                context = packaging_build.BuildContext(
                    "windows-x64",
                    "Windows",
                    "AMD64",
                    "0.6.0",
                )
                context.dist_path.mkdir(parents=True)
                context.manifest_path.write_text(
                    json.dumps({"tools": {"python": "3.12.14"}}),
                    encoding="utf-8",
                )

                def create_installer(*args, **kwargs):
                    self._write_windows_x64_executable(context.installer_path)

                with patch.object(
                    packaging_build.subprocess,
                    "run",
                    side_effect=create_installer,
                ):
                    result = packaging_build.build_windows_installer(
                        context,
                        Path("C:/tools/ISCC.exe"),
                        "7.0.2",
                    )

                release_manifest = json.loads(
                    context.release_manifest_path.read_text(encoding="utf-8")
                )
                self.assertEqual(result, context.installer_path)
                self.assertEqual(release_manifest["tools"]["inno_setup"], "7.0.2")
                self.assertEqual(
                    release_manifest["installer"]["path"],
                    context.installer_path.relative_to(PROJECT_ROOT).as_posix(),
                )
                self.assertIn(context.installer_name, context.installer_checksum_path.read_text())
        finally:
            packaging_build.DIST_ROOT = original_dist_root
            packaging_build.RELEASE_ROOT = original_release_root

    def test_installer_rejects_non_windows_target(self):
        context = packaging_build.BuildContext(
            "macos-arm64",
            "Darwin",
            "arm64",
            "0.6.0",
        )

        with self.assertRaisesRegex(packaging_build.BuildError, "only for windows-x64"):
            packaging_build.validate_installer_inputs(context)

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

    def test_bundle_deduplicates_macos_metadata_crosslink_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary)
            metadata = bundle / "Contents" / "Resources" / "znactime-0.6.0.dist-info"
            metadata.mkdir(parents=True)
            (metadata / "METADATA").write_text("Version: 0.6.0\n", encoding="utf-8")
            alias = metadata / ".." / metadata.name
            original_rglob = Path.rglob

            def macos_crosslinks(path, pattern):
                if path == bundle and pattern == "znactime-*.dist-info":
                    return iter((metadata, alias))
                return original_rglob(path, pattern)

            with patch.object(Path, "rglob", new=macos_crosslinks):
                packaging_build._validate_bundle(bundle)


if __name__ == "__main__":
    unittest.main()
