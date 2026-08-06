#!/usr/bin/env python3
"""Tests for the confirmed Android Delivery project setup scaffold."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
from types import ModuleType
import unittest

import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SETUP_SCRIPTS = REPOSITORY_ROOT / "android-delivery-setup" / "scripts"
SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if globals().get("__package__") in {None, ""}:
    sys.path.insert(0, str(SCRIPTS_DIR.parent))
    __package__ = "scripts.tests"
    __spec__ = None


def _load_setup_project() -> ModuleType:
    """从带连字符的 Skill 目录加载真实 setup_project.py。"""
    module_path = SETUP_SCRIPTS / "setup_project.py"
    spec = importlib.util.spec_from_file_location("android_delivery_setup_project", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载项目初始化脚本: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_SETUP_PROJECT = _load_setup_project()
SetupError = getattr(_SETUP_PROJECT, "SetupError")
apply_setup = getattr(_SETUP_PROJECT, "apply_setup")
inspect_project = getattr(_SETUP_PROJECT, "inspect_project")

from ..config_paths import resolve_config_paths  # noqa: E402


class SetupProjectTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name) / "app-project"
        self.project.mkdir()
        (self.project / "settings.gradle.kts").write_text(
            'pluginManagement {}\ninclude(":app", ":feature:login")\n', encoding="utf-8"
        )
        (self.project / "gradlew").write_text("#!/bin/sh\n", encoding="utf-8")
        app = self.project / "app"
        app.mkdir()
        (app / "build.gradle.kts").write_text(
            'dependencies { testImplementation("junit:junit:4.13.2") }\n', encoding="utf-8"
        )
        layout = app / "src" / "main" / "res" / "layout"
        layout.mkdir(parents=True)
        (layout / "activity_main.xml").write_text("<FrameLayout />\n", encoding="utf-8")

    def test_inspect_detects_modules_and_xml(self) -> None:
        report = inspect_project(self.project)
        self.assertEqual([":app", ":feature:login"], report["project"]["modules"])
        self.assertEqual("xml", report["project"]["ui_system"])
        self.assertTrue(report["integrations"]["figma_android_xml"]["applicable"])

    def test_instrumentation_dependency_does_not_imply_unit_tests(self) -> None:
        """androidTestImplementation 不得因子串重叠误报 testImplementation。"""
        (self.project / "app" / "build.gradle.kts").write_text(
            'dependencies { androidTestImplementation("androidx.test:runner:1.6.2") }\n',
            encoding="utf-8",
        )

        capabilities = inspect_project(self.project)["capabilities"]

        self.assertFalse(capabilities["unit_tests_declared"])
        self.assertTrue(capabilities["instrumentation_declared"])

    def test_apply_requires_confirmation_and_is_idempotent(self) -> None:
        with self.assertRaisesRegex(SetupError, "--confirm"):
            apply_setup(self.project, confirm=False, force=False)

        first = apply_setup(self.project, confirm=True, force=False)
        second = apply_setup(self.project, confirm=True, force=False)
        self.assertTrue(all(status == "WRITTEN" for status in first["files"].values()))
        self.assertTrue(all(status == "UNCHANGED" for status in second["files"].values()))
        self.assertFalse((self.project / "AGENTS.md").exists())

    def test_channel_example_is_compatible_with_current_path_resolver(self) -> None:
        apply_setup(self.project, confirm=True, force=False)
        config_path = self.project / ".android-delivery" / "channel.example.yaml"
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        paths = resolve_config_paths(config, config_path)
        self.assertEqual(self.project.resolve(), paths.workspace_root)
        self.assertEqual(self.project.resolve(), paths.project_path)
        self.assertEqual(
            (self.project / "document" / "YYYY-MM-DD-feature").resolve(),
            paths.requirement_dir,
        )

    def test_existing_changed_generated_file_is_not_overwritten(self) -> None:
        apply_setup(self.project, confirm=True, force=False)
        target = self.project / "docs" / "agents" / "android-delivery.md"
        target.write_text("user content\n", encoding="utf-8")
        with self.assertRaisesRegex(SetupError, "未覆盖"):
            apply_setup(self.project, confirm=True, force=False)

    def test_conflict_is_detected_before_any_generated_file_is_written(self) -> None:
        target = self.project / "docs" / "agents" / "android-delivery.md"
        target.parent.mkdir(parents=True)
        target.write_text("user content\n", encoding="utf-8")

        with self.assertRaisesRegex(SetupError, "未覆盖"):
            apply_setup(self.project, confirm=True, force=False)

        self.assertFalse((self.project / ".android-delivery" / "project.yaml").exists())
        self.assertFalse((self.project / ".android-delivery" / "channel.example.yaml").exists())
        self.assertEqual("user content\n", target.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
