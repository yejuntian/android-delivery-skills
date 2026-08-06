#!/usr/bin/env python3
"""脚本名称：test_static_analysis.py

用途：验证通用 SARIF 摘要、稳定问题编号和静态门禁控制面审计。

覆盖范围：行号变化后的编号稳定性、Error 计数、工具与相对路径提取，以及源码抑制、
基线、排除和配置变化候选。测试只使用临时文件，不运行外部扫描器或修改真实项目。
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if globals().get("__package__") in {None, ""}:
    sys.path.insert(0, str(SCRIPTS_DIR.parent))
    __package__ = "scripts.tests"
    __spec__ = None

from ..git_changes import (  # noqa: E402
    GitChange,
    collect_changed_entries,
    current_delivery_snapshot,
    load_baseline,
    write_baseline,
)
from ..static_analysis import (  # noqa: E402
    CONTROL_AUDIT_PRODUCER,
    FINDING_ID_PATTERN,
    StaticAnalysisError,
    audit_control_changes,
    build_control_audit,
    stable_finding_id,
    summarize_sarif,
)


class StaticAnalysisTests(unittest.TestCase):
    """验证静态证据规范化不依赖具体工具插件或目标 Android 版本。"""

    def setUp(self) -> None:
        """建立临时项目和可重复改写的 SARIF 报告。"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.project = Path(self.temp_dir.name) / "project"
        self.project.mkdir()
        self.report = Path(self.temp_dir.name) / "detekt.sarif"

    def _write_sarif(
        self,
        line: int,
        level: str = "warning",
        baseline_state: str | None = None,
    ) -> None:
        """写入带工具、规则、逻辑符号和项目内位置的最小 SARIF。"""
        payload = {
            "version": "2.1.0",
            "runs": [{
                "tool": {
                    "driver": {
                        "name": "detekt",
                        "semanticVersion": "2.0.0",
                        "rules": [{
                            "id": "LifecycleLeak",
                            "defaultConfiguration": {"level": "warning"},
                        }],
                    }
                },
                "results": [{
                    "ruleId": "LifecycleLeak",
                    "level": level,
                    "message": {"text": "Singleton captures Activity"},
                    "locations": [{
                        "physicalLocation": {
                            "artifactLocation": {"uri": (self.project / "app/src/App.kt").as_uri()},
                            "region": {"startLine": line},
                        },
                        "logicalLocations": [{"fullyQualifiedName": "sample.Cache.callback"}],
                    }],
                    **({"baselineState": baseline_state} if baseline_state else {}),
                }],
            }],
        }
        self.report.write_text(json.dumps(payload), encoding="utf-8")

    def test_sarif_finding_id_survives_line_moves(self) -> None:
        """验证只移动代码行不会制造新问题编号，便于跨需求修订持续追踪。"""
        self._write_sarif(12)
        first = summarize_sarif(self.report, self.project)
        self._write_sarif(80)
        second = summarize_sarif(self.report, self.project)

        self.assertEqual(first["findings"][0]["id"], second["findings"][0]["id"])
        self.assertRegex(first["findings"][0]["id"], FINDING_ID_PATTERN)
        self.assertEqual("app/src/App.kt", first["findings"][0]["path"])
        self.assertEqual(12, first["findings"][0]["line"])
        self.assertEqual([{"name": "detekt", "version": "2.0.0"}], first["tools"])

    def test_sarif_error_is_counted_without_trusting_exit_code(self) -> None:
        """验证 SARIF Error 独立计数，外部命令即使返回零也不能隐藏报告问题。"""
        self._write_sarif(20, "error")
        summary = summarize_sarif(self.report, self.project)

        self.assertEqual(1, summary["errors"])
        self.assertEqual(1, summary["unknown_errors"])
        self.assertEqual(1, summary["blocking_errors"])
        self.assertEqual(0, summary["warnings"])
        self.assertEqual(1, summary["total"])

    def test_unchanged_historical_error_is_recorded_but_not_blocking(self) -> None:
        """验证工具明确标记 unchanged 的历史 Error 被保留，但不阻断增量需求。"""
        self._write_sarif(20, "error", "unchanged")
        summary = summarize_sarif(self.report, self.project)

        self.assertEqual(1, summary["errors"])
        self.assertEqual(1, summary["unchanged_errors"])
        self.assertEqual(0, summary["blocking_errors"])
        self.assertEqual("unchanged", summary["findings"][0]["baseline_state"])

    def test_updated_and_unknown_errors_remain_blocking(self) -> None:
        """验证更新问题和缺少可靠基线的问题不能被脑补成历史债务。"""
        self._write_sarif(20, "error", "updated")
        updated = summarize_sarif(self.report, self.project)
        self._write_sarif(20, "error", "unexpected-state")
        unknown = summarize_sarif(self.report, self.project)

        self.assertEqual(1, updated["updated_errors"])
        self.assertEqual(1, updated["blocking_errors"])
        self.assertEqual(1, unknown["unknown_errors"])
        self.assertEqual(1, unknown["blocking_errors"])

    def test_manual_finding_id_changes_only_when_identity_changes(self) -> None:
        """验证人工语义发现使用规则、路径和符号形成稳定身份，不绑定易变行号。"""
        first = stable_finding_id(
            tool="android-audit-stability",
            rule_id="static-async-lifetime",
            path="app/src/FeedFragment.kt",
            symbol="FeedFragment.load",
            message="任务超过 Fragment View 生命周期",
        )
        same = stable_finding_id(
            tool="android-audit-stability",
            rule_id="static-async-lifetime",
            path="app/src/FeedFragment.kt",
            symbol="FeedFragment.load",
            message="任务超过 Fragment View 生命周期",
        )
        changed = stable_finding_id(
            tool="android-audit-stability",
            rule_id="static-resource-pairing",
            path="app/src/FeedFragment.kt",
            symbol="FeedFragment.load",
            message="任务超过 Fragment View 生命周期",
        )

        self.assertEqual(first, same)
        self.assertNotEqual(first, changed)

    def test_stable_ids_preserve_case_sensitive_paths(self) -> None:
        """验证 Linux 中仅大小写不同的源码和配置不会发生稳定编号碰撞。"""
        upper_finding = stable_finding_id(
            tool="detekt", rule_id="Leak", path="app/src/Cache.kt", message="capture"
        )
        lower_finding = stable_finding_id(
            tool="detekt", rule_id="Leak", path="app/src/cache.kt", message="capture"
        )
        upper_control = audit_control_changes([GitChange(
            status="M",
            path="Config/detekt.yml",
            patch="+exclude: legacy",
        )])
        lower_control = audit_control_changes([GitChange(
            status="M",
            path="config/detekt.yml",
            patch="+exclude: legacy",
        )])

        self.assertNotEqual(upper_finding, lower_finding)
        self.assertNotEqual(upper_control[0]["id"], lower_control[0]["id"])

    def test_audits_suppression_baseline_exclusion_and_config_changes(self) -> None:
        """验证控制面候选只要求审查理由，不直接把配置命中脑补成生产缺陷。"""
        changes = [
            GitChange(
                status="M",
                path="app/src/main/java/sample/Feed.kt",
                patch="@@ -1,0 +2 @@\n+@Suppress(\"StaticFieldLeak\")\n",
            ),
            GitChange(
                status="M",
                path="config/detekt/detekt.yml",
                patch="@@ -1,0 +2,2 @@\n+baseline: detekt-baseline.xml\n+exclude: '**/legacy/**'\n",
            ),
        ]
        candidates = audit_control_changes(changes)
        kinds = {item["kind"] for item in candidates}

        self.assertEqual({"SUPPRESSION", "BASELINE", "EXCLUSION", "CONFIG"}, kinds)
        self.assertTrue(all(item["id"].startswith("CTL-") for item in candidates))
        self.assertTrue(all(item["summary"] for item in candidates))

    def test_audits_nested_and_generic_quality_config_paths(self) -> None:
        """验证隐藏规则目录和不带工具名的质量配置仍进入有界控制面审计。"""
        changes = [
            GitChange(status="M", path=".semgrep/rules.yml", patch="+rules: []\n"),
            GitChange(status="M", path="config/quality/rules.yml", patch="+rules: []\n"),
        ]

        candidates = audit_control_changes(changes)
        config_paths = {item["path"] for item in candidates if item["kind"] == "CONFIG"}

        self.assertEqual({".semgrep/rules.yml", "config/quality/rules.yml"}, config_paths)

    def test_audits_untracked_suppression_and_renamed_baseline(self) -> None:
        """验证未跟踪源码的原始正文和基线重命名不会绕过控制面候选。"""
        changes = [
            GitChange(
                status="A",
                path="app/src/main/java/sample/NewFeature.kt",
                patch='@Suppress("StaticFieldLeak")\nclass NewFeature\n',
            ),
            GitChange(
                status="R",
                old_path="config/detekt/detekt-baseline.xml",
                path="config/detekt/archive.xml",
                patch="diff --git a/config/detekt/detekt-baseline.xml b/config/detekt/archive.xml\n",
            ),
        ]

        candidates = audit_control_changes(changes)

        self.assertIn("SUPPRESSION", {item["kind"] for item in candidates})
        self.assertIn("BASELINE", {item["kind"] for item in candidates})

    def test_ordinary_code_change_does_not_create_control_candidate(self) -> None:
        """验证普通业务代码不会因包含生命周期词汇而被控制面审计误报。"""
        changes = [GitChange(
            status="M",
            path="app/src/main/java/sample/Feed.kt",
            patch="@@ -1 +1 @@\n-val old = 1\n+val current = 2\n",
        )]
        self.assertEqual([], audit_control_changes(changes))

    def test_build_control_audit_binds_current_baseline_and_snapshot(self) -> None:
        """验证 CLI 使用的审计结构来自真实 Git 基线、最终代码和完整候选集合。"""
        subprocess.run(["git", "init", "-q"], cwd=self.project, check=True)
        subprocess.run(["git", "config", "user.name", "Static Test"], cwd=self.project, check=True)
        subprocess.run(
            ["git", "config", "user.email", "static@example.invalid"],
            cwd=self.project,
            check=True,
        )
        source = self.project / "Feature.kt"
        source.write_text("class Feature\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=self.project, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "baseline"], cwd=self.project, check=True)
        baseline_path = Path(self.temp_dir.name) / "baseline.json"
        baseline = write_baseline(self.project, baseline_path)
        source.write_text('@Suppress("StaticFieldLeak")\nclass Feature\n', encoding="utf-8")

        audit = build_control_audit(self.project, baseline_path)

        self.assertEqual(CONTROL_AUDIT_PRODUCER, audit["producer"])
        self.assertEqual(baseline["id"], audit["baseline_id"])
        self.assertEqual(
            current_delivery_snapshot(self.project, baseline_path)["snapshot_sha256"],
            audit["snapshot_sha256"],
        )
        self.assertIn("SUPPRESSION", {item["kind"] for item in audit["control_changes"]})

    def test_control_audit_uses_delivery_snapshot_exclusions(self) -> None:
        """需求文档和审计产物不能改变控制面审计绑定的代码快照。"""
        subprocess.run(["git", "init", "-q"], cwd=self.project, check=True)
        subprocess.run(["git", "config", "user.name", "Static Test"], cwd=self.project, check=True)
        subprocess.run(
            ["git", "config", "user.email", "static@example.invalid"],
            cwd=self.project,
            check=True,
        )
        source = self.project / "Feature.kt"
        source.write_text("class Feature\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=self.project, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "baseline"], cwd=self.project, check=True)
        baseline_path = Path(self.temp_dir.name) / "baseline.json"
        write_baseline(self.project, baseline_path)
        document = self.project / "document" / "audit" / "quality.yml"
        document.parent.mkdir(parents=True)
        document.write_text("exclude: app/src/**\n", encoding="utf-8")

        audit = build_control_audit(
            self.project,
            baseline_path,
            exclude_paths={"document"},
        )

        expected = current_delivery_snapshot(
            self.project,
            baseline_path,
            exclude_paths={"document"},
        )
        self.assertEqual(expected["snapshot_sha256"], audit["snapshot_sha256"])
        self.assertEqual([], audit["control_changes"])

    def test_build_control_audit_rejects_concurrent_code_change(self) -> None:
        """验证多窗口在审计期间改代码时不会把旧候选绑定到新摘要。"""
        baseline_path = Path(self.temp_dir.name) / "baseline.json"
        replacements = {
            load_baseline.__name__: mock.Mock(return_value={"id": "baseline-1"}),
            collect_changed_entries.__name__: mock.Mock(return_value=([], [])),
            current_delivery_snapshot.__name__: mock.Mock(
                side_effect=[
                    {"snapshot_sha256": "a" * 64},
                    {"snapshot_sha256": "b" * 64},
                ]
            ),
        }
        with mock.patch.dict(build_control_audit.__globals__, replacements):
            with self.assertRaisesRegex(StaticAnalysisError, "审计期间代码发生变化"):
                build_control_audit(self.project, baseline_path)


if __name__ == "__main__":
    unittest.main()
