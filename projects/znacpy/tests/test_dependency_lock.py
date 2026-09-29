import re
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = ROOT.parents[1]
OBSOLETE_REQUIREMENTS = (
    "requirements.in",
    "requirements.txt",
    "requirements-dev.txt",
)
TARGET_ENVIRONMENTS = {
    "sys_platform == 'win32' and platform_machine == 'AMD64'",
    "sys_platform == 'darwin' and platform_machine == 'arm64'",
}


def _requirement_name(requirement):
    return re.split(r"[<>=!~ ;\[]", requirement.casefold(), maxsplit=1)[0]


class DependencyLockTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.project = tomllib.loads(
            (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        )
        cls.lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))

    def test_project_declares_runtime_and_build_dependencies(self):
        runtime = {
            _requirement_name(item)
            for item in self.project["project"]["dependencies"]
        }
        build = {
            _requirement_name(item)
            for item in self.project["dependency-groups"]["build"]
        }

        self.assertEqual(runtime, {"pyside6", "reportlab"})
        self.assertEqual(build, {"pyinstaller"})
        self.assertEqual(
            self.project["build-system"]["build-backend"],
            "hatchling.build",
        )

    def test_uv_resolution_is_limited_to_supported_native_targets(self):
        uv = self.project["tool"]["uv"]

        self.assertRegex(uv["required-version"], r"^==\d+\.\d+\.\d+$")
        self.assertEqual(set(uv["environments"]), TARGET_ENVIRONMENTS)
        self.assertEqual(set(uv["required-environments"]), TARGET_ENVIRONMENTS)

    def test_lock_contains_project_and_declared_direct_dependencies(self):
        packages = {item["name"]: item for item in self.lock["package"]}
        project = self.project["project"]

        self.assertIn("znactime", packages)
        self.assertEqual(packages["znactime"]["version"], project["version"])
        for requirement in (
            *project["dependencies"],
            *self.project["dependency-groups"]["build"],
        ):
            self.assertIn(_requirement_name(requirement), packages)

    def test_legacy_requirements_entry_points_are_removed(self):
        self.assertTrue(
            all(not (ROOT / name).exists() for name in OBSOLETE_REQUIREMENTS)
        )

    def test_application_version_has_one_literal_source(self):
        configured = (ROOT / "znactime" / "config.py").read_text(encoding="utf-8")
        readmes = (
            (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8"),
            (ROOT / "README.md").read_text(encoding="utf-8"),
        )

        self.assertRegex(self.project["project"]["version"], r"^\d+\.\d+\.\d+$")
        self.assertIn('VERSION = version("znactime")', configured)
        self.assertTrue(
            all(self.project["project"]["version"] not in text for text in readmes)
        )

    def test_gui_entry_point_uses_existing_composition_root(self):
        self.assertEqual(
            self.project["project"]["gui-scripts"]["znactime"],
            "znactime.__main__:main",
        )


if __name__ == "__main__":
    unittest.main()
