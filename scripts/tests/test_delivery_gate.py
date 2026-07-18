#!/usr/bin/env python3
"""脚本名称：test_delivery_gate.py

用途：验证最终交付门禁只接受当前代码上的完整原子义务、专项门禁和真实证据。

覆盖范围：通过报告、过期摘要、缺失证据、人工证据类型、未完成结论，以及隔离 Git
仓库中的当前摘要。测试不运行 Android 构建、不修改真实仓库。
"""

from __future__ import annotations

import sys
import json
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if __package__ in {None, ""}:
    sys.path.insert(0, str(SCRIPTS_DIR.parent))
    __package__ = "scripts.tests"

from ..delivery_gate import current_context, main, validate_delivery_result  # noqa: E402
from ..git_changes import write_baseline  # noqa: E402


class DeliveryGateTests(unittest.TestCase):
    """验证最终结论不能越过原子义务、门禁和证据新鲜度。"""

    def setUp(self) -> None:
        """建立同一基线和代码摘要下的最小有效交付报告。"""
        self.snapshot = "a" * 64
        self.requirement = "b" * 64
        self.context = {
            "baseline_id": "baseline-1",
            "baseline_head": "head-1",
            "head": "head-2",
            "snapshot_sha256": self.snapshot,
            "requirement_file_sha256": self.requirement,
            "result_path": "/tmp/result.json",
        }
        self.payload = {
            "version": 1,
            "baseline_id": "baseline-1",
            "requirement_file_sha256": self.requirement,
            "snapshot_sha256": self.snapshot,
            "conclusion": "FULL_PASS",
            "obligations": [
                {
                    "id": "BDD-001/T1",
                    "required": True,
                    "status": "COVERED_AUTOMATED",
                    "evidence_ids": ["E-TEST"],
                }
            ],
            "gates": [
                {
                    "id": "android-test-and-fix",
                    "required": True,
                    "status": "PASS",
                    "evidence_ids": ["E-TEST"],
                },
                {
                    "id": "android-review-diff",
                    "required": True,
                    "status": "PASS",
                    "evidence_ids": ["E-REVIEW"],
                },
                {
                    "id": "android-review-code-quality",
                    "required": True,
                    "status": "PASS",
                    "evidence_ids": ["E-REVIEW"],
                },
                {
                    "id": "android-audit-stability",
                    "required": True,
                    "status": "PASS",
                    "evidence_ids": ["E-REVIEW"],
                },
                {
                    "id": "android-build",
                    "required": True,
                    "status": "PASS",
                    "evidence_ids": ["E-TEST"],
                },
                {
                    "id": "android-lint",
                    "required": True,
                    "status": "PASS",
                    "evidence_ids": ["E-TEST"],
                },
            ],
            "evidence": [
                {
                    "id": "E-TEST",
                    "kind": "AUTOMATED",
                    "snapshot_sha256": self.snapshot,
                    "command": ["./gradlew", ":app:testDebugUnitTest"],
                    "exit_code": 0,
                    "executed_tests": 2,
                },
                {
                    "id": "E-REVIEW",
                    "kind": "REVIEW",
                    "snapshot_sha256": self.snapshot,
                    "summary": "实际 diff 与需求范围一致，未发现阻断项。",
                },
            ],
        }

    def test_accepts_complete_fresh_result(self) -> None:
        """验证全部必需义务和门禁引用当前代码证据时允许通过。"""
        self.assertEqual([], validate_delivery_result(self.payload, self.context))

    def test_rejects_stale_snapshot_and_missing_evidence(self) -> None:
        """验证测试后代码变化或引用不存在时，旧报告不能继续判绿。"""
        self.payload["snapshot_sha256"] = "c" * 64
        self.payload["obligations"][0]["evidence_ids"] = ["E-MISSING"]
        errors = validate_delivery_result(self.payload, self.context)

        self.assertTrue(any("旧证据已经失效" in error for error in errors))
        self.assertTrue(any("不存在的证据" in error for error in errors))

    def test_requires_matching_manual_evidence(self) -> None:
        """验证计划人工执行不能冒充已经完成的人工覆盖。"""
        obligation = self.payload["obligations"][0]
        obligation["status"] = "COVERED_MANUAL"
        errors = validate_delivery_result(self.payload, self.context)

        self.assertTrue(any("缺少实际人工证据" in error for error in errors))

    def test_requires_every_core_review_build_and_lint_gate(self) -> None:
        """验证 AI 不能通过省略质量、稳定性、构建或 lint 门禁缩短完整交付。"""
        self.payload["gates"] = [
            gate for gate in self.payload["gates"]
            if gate["id"] != "android-review-code-quality"
        ]
        errors = validate_delivery_result(self.payload, self.context)

        self.assertTrue(any("缺少核心 gate: android-review-code-quality" in error for error in errors))

    def test_incomplete_conclusion_is_truthful_but_not_passing(self) -> None:
        """验证未完成报告可以保留缺口，不会被结构校验误写成通过。"""
        self.payload["conclusion"] = "INCOMPLETE"
        self.payload["obligations"][0]["status"] = "UNVERIFIED"
        self.payload["obligations"][0]["evidence_ids"] = []

        self.assertEqual([], validate_delivery_result(self.payload, self.context))

    def test_current_context_binds_requirement_and_git_snapshot(self) -> None:
        """验证门禁上下文来自真实需求文件和当前 Git 工作树，而不是报告自行声明。"""
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            repo = root / "repo"
            repo.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "Gate Test"], cwd=repo, check=True)
            subprocess.run(
                ["git", "config", "user.email", "gate@example.invalid"],
                cwd=repo,
                check=True,
            )
            (repo / "App.kt").write_text("class App\n", encoding="utf-8")
            subprocess.run(["git", "add", "App.kt"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "baseline"], cwd=repo, check=True)
            baseline = root / "baseline.json"
            baseline_payload = write_baseline(repo, baseline)
            (repo / "App.kt").write_text("class AppChanged\n", encoding="utf-8")
            requirement_dir = root / "requirement"
            requirement_dir.mkdir()
            requirement = requirement_dir / "requirement.md"
            requirement.write_text("修改 App\n", encoding="utf-8")
            config = {
                "workspace_root": str(root),
                "project_path": str(repo),
                "requirement_dir": str(requirement_dir),
                "requirement_file": str(requirement),
            }
            with mock.patch("scripts.delivery_gate.baseline_path_for_config", return_value=baseline):
                context = current_context(root / "local.yaml", config)

        self.assertEqual(baseline_payload["id"], context["baseline_id"])
        self.assertEqual(64, len(context["snapshot_sha256"]))
        self.assertEqual(64, len(context["requirement_file_sha256"]))

    def test_cli_validate_accepts_fresh_report(self) -> None:
        """验证 CLI 能读取结果文件并以退出码 0 表达机器门禁通过。"""
        with tempfile.TemporaryDirectory() as raw_root:
            result = Path(raw_root) / "delivery-result.json"
            result.write_text(
                json.dumps(self.payload, ensure_ascii=False),
                encoding="utf-8",
            )
            with (
                mock.patch("scripts.delivery_gate.load_config", return_value={}),
                mock.patch("scripts.delivery_gate.current_context", return_value=self.context),
                redirect_stdout(io.StringIO()),
            ):
                exit_code = main([
                    "validate",
                    "--config", str(Path(raw_root) / "local.yaml"),
                    "--result", str(result),
                ])

        self.assertEqual(0, exit_code)


if __name__ == "__main__":
    unittest.main()
