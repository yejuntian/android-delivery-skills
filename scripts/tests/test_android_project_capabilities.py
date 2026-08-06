#!/usr/bin/env python3
"""脚本名称：test_android_project_capabilities.py

用途：验证只读能力发现能够识别模块、variant、现有 Gradle task 和静态工具信号。

覆盖范围：任务解析、用途分组、settings include、wrapper 版本、配置/CI 信号和扫描截断。
测试只运行临时假的 Gradle wrapper，不接触真实 Android 项目、设备或网络。
"""

from __future__ import annotations

import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest import mock


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if globals().get("__package__") in {None, ""}:
    sys.path.insert(0, str(SCRIPTS_DIR.parent))
    __package__ = "scripts.tests"
    __spec__ = None

from .. import android_project_capabilities as android_project_capabilities_module  # noqa: E402
from ..test_support import patch_module_global  # noqa: E402
from ..android_project_capabilities import (  # noqa: E402
    classify_tasks,
    discover_capabilities,
    discover_static_analysis_signals,
    parse_gradle_tasks,
)


TASK_OUTPUT = """Android tasks
app:assembleDemoDebug - Assembles demo debug
app:bundleRelease - Bundles release
app:compileDemoDebugKotlin - Compiles Kotlin
app:testDemoDebugUnitTest - Runs unit tests
app:connectedDemoDebugAndroidTest - Runs device tests
app:lintDemoDebug - Runs lint
app:detekt - Runs detekt
app:checkApi - Checks API
benchmark:connectedBenchmarkAndroidTest - Runs benchmark
app:recordRoborazziDemoDebug - Records screenshots
"""


class AndroidProjectCapabilitiesTests(unittest.TestCase):
    """验证发现器只报告真实任务，不猜测项目业务或修改构建文件。"""

    def test_parses_and_groups_real_task_names(self) -> None:
        """验证未知说明行被忽略，已发现任务按稳定用途建立索引。"""
        tasks = parse_gradle_tasks(TASK_OUTPUT)
        groups = classify_tasks(tasks)
        self.assertIn("app:assembleDemoDebug", groups["assemble"])
        self.assertIn("app:testDemoDebugUnitTest", groups["unit_test"])
        self.assertIn("app:connectedDemoDebugAndroidTest", groups["instrumentation"])
        self.assertIn("app:detekt", groups["static_analysis"])
        self.assertIn("app:checkApi", groups["api_abi"])
        self.assertIn("app:recordRoborazziDemoDebug", groups["screenshot"])

    def test_discovers_modules_variants_and_wrapper_without_project_writes(self) -> None:
        """验证临时 wrapper 输出可形成完整能力快照，源码配置内容保持不变。"""
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            settings = root / "settings.gradle.kts"
            settings.write_text('include(":app", ":benchmark")\n', encoding="utf-8")
            wrapper_dir = root / "gradle" / "wrapper"
            wrapper_dir.mkdir(parents=True)
            (wrapper_dir / "gradle-wrapper.properties").write_text(
                "distributionUrl=https\\://services.gradle.org/distributions/gradle-8.10-bin.zip\n",
                encoding="utf-8",
            )
            gradlew = root / "gradlew"
            gradlew.write_text(
                "#!/bin/sh\n"
                "cat <<'EOF'\n"
                f"{TASK_OUTPUT}"
                "EOF\n",
                encoding="utf-8",
            )
            gradlew.chmod(gradlew.stat().st_mode | stat.S_IXUSR)
            before = settings.read_bytes()

            with mock.patch.dict(os.environ, {"XDG_CACHE_HOME": str(root / "cache")}):
                result = discover_capabilities(root)

            self.assertEqual(0, result["exit_code"])
            self.assertEqual(2, result["version"])
            self.assertEqual("8.10", result["gradle_version"])
            self.assertEqual([":app", ":benchmark"], result["modules"])
            self.assertIn("demoDebug", result["variants"])
            self.assertIn("release", result["variants"])
            self.assertEqual(before, settings.read_bytes())

    def test_discovers_static_tools_from_tasks_configs_and_ci(self) -> None:
        """验证非 Gradle 的 Semgrep/CodeQL 配置也进入只读能力清单，不伪装成已执行。"""
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            (root / "build.gradle.kts").write_text(
                'plugins { id("io.gitlab.arturbosch.detekt") }\n',
                encoding="utf-8",
            )
            config_dir = root / "config" / "detekt"
            config_dir.mkdir(parents=True)
            (config_dir / "detekt.yml").write_text("build: { maxIssues: 0 }\n", encoding="utf-8")
            workflows = root / ".github" / "workflows"
            workflows.mkdir(parents=True)
            (workflows / "static-analysis.yml").write_text(
                "steps:\n  - uses: github/codeql-action/analyze@v3\n  - run: semgrep scan\n",
                encoding="utf-8",
            )
            semgrep_rules = root / ".semgrep"
            semgrep_rules.mkdir()
            (semgrep_rules / "rules.yml").write_text("rules: []\n", encoding="utf-8")
            quality_config = root / "config" / "quality"
            quality_config.mkdir()
            (quality_config / "rules.yml").write_text(
                "engine: spotbugs\n",
                encoding="utf-8",
            )

            result = discover_static_analysis_signals(root, ["app:detekt"])

        tools = {item["id"]: item for item in result["tools"]}
        self.assertIn("app:detekt", tools["detekt"]["tasks"])
        self.assertIn("config/detekt/detekt.yml", tools["detekt"]["config_files"])
        self.assertIn(".github/workflows/static-analysis.yml", tools["codeql"]["ci_files"])
        self.assertIn(".github/workflows/static-analysis.yml", tools["semgrep"]["ci_files"])
        self.assertIn(".semgrep/rules.yml", tools["semgrep"]["config_files"])
        self.assertIn("config/quality/rules.yml", tools["spotbugs"]["config_files"])
        self.assertIn("config/detekt/detekt.yml", result["control_files"])
        self.assertFalse(result["discovery_truncated"])
        self.assertGreater(result["visited_files"], 0)

    def test_static_signal_discovery_reports_bounded_scan(self) -> None:
        """验证大仓库达到只读扫描上限时显式报告能力损失，而不是静默返回完整。"""
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            (root / "a.txt").write_text("ordinary\n", encoding="utf-8")
            (root / "b.txt").write_text("ordinary\n", encoding="utf-8")
            with patch_module_global(android_project_capabilities_module, "MAX_DISCOVERY_FILES", 1):
                result = discover_static_analysis_signals(root, [])

        self.assertTrue(result["discovery_truncated"])
        self.assertEqual(1, result["visited_files"])

    def test_unlaunchable_wrapper_is_reported_as_environment_failure(self) -> None:
        """验证 wrapper 不可执行时仍返回结构化失败，不抛出不可操作 traceback。"""
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            (root / "gradlew").write_text("not executable\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {"XDG_CACHE_HOME": str(root / "cache")}):
                result = discover_capabilities(root)

        self.assertEqual(127, result["exit_code"])
        self.assertIn("无法启动", result["stderr"])


if __name__ == "__main__":
    unittest.main()
