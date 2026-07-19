#!/usr/bin/env python3
"""脚本名称：test_android_project_capabilities.py

用途：验证只读能力发现能够识别模块、variant 和现有 Gradle task。

覆盖范围：任务解析、用途分组、settings include 和 wrapper 版本。测试只运行临时假的
Gradle wrapper，不接触真实 Android 项目、设备或网络。
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
if __package__ in {None, ""}:
    sys.path.insert(0, str(SCRIPTS_DIR.parent))
    __package__ = "scripts.tests"

from ..android_project_capabilities import (  # noqa: E402
    classify_tasks,
    discover_capabilities,
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
            self.assertEqual("8.10", result["gradle_version"])
            self.assertEqual([":app", ":benchmark"], result["modules"])
            self.assertIn("demoDebug", result["variants"])
            self.assertIn("release", result["variants"])
            self.assertEqual(before, settings.read_bytes())

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
