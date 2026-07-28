#!/usr/bin/env python3
"""脚本名称：test_test_mapping.py

用途：验证测试映射在需求增量后正确标记 STALE，以及最终门禁前的结构校验。

覆盖范围：初始骨架、修订后 STALE 标记、CURRENT 一致性、登记已删除义务和缺失义务。
测试不运行 Android 构建、不修改真实仓库，也不访问网络。
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if __package__ in {None, ""}:
    sys.path.insert(0, str(SCRIPTS_DIR.parent))
    __package__ = "scripts.tests"

from ..test_mapping import (  # noqa: E402
    MAPPING_VERSION,
    TestMappingError,
    build_initial_mapping,
    mark_stale_after_revision,
    validate_test_mapping,
)


def make_snapshot(obligations):
    """构造最小需求快照，只提供校验所需字段。"""
    return {"obligations": obligations}


class TestMappingTests(unittest.TestCase):
    """验证测试映射的结构校验与需求增量联动。"""

    def setUp(self) -> None:
        """建立两个义务的快照，对应初始测试映射。"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.temp_root = Path(self.temp_dir.name)
        self.obligations = [
            {"id": "BDD-001/T1", "sha256": "a" * 64, "text": "显示错误", "required": True},
            {"id": "BDD-002/T1", "sha256": "b" * 64, "text": "跳转主页", "required": True},
        ]

    def test_initial_mapping_marks_all_stale(self) -> None:
        """初始骨架全部 STALE，提示 AI 回填测试后才能 CURRENT。"""
        mapping = build_initial_mapping(make_snapshot(self.obligations))
        self.assertEqual(mapping["version"], MAPPING_VERSION)
        self.assertTrue(all(item["mapping_status"] == "STALE" for item in mapping["mappings"]))

    def test_current_mapping_validates_when_covered(self) -> None:
        """CURRENT 且 test_ids 与义务摘要对齐时校验通过。"""
        mapping = {
            "version": MAPPING_VERSION,
            "mappings": [
                {
                    "obligation_id": "BDD-001/T1",
                    "obligation_sha256": "a" * 64,
                    "test_ids": ["FeatureTest#t1"],
                    "mapping_status": "CURRENT",
                    "manual_reason": None,
                },
                {
                    "obligation_id": "BDD-002/T1",
                    "obligation_sha256": "b" * 64,
                    "test_ids": ["FeatureTest#t2"],
                    "mapping_status": "CURRENT",
                    "manual_reason": None,
                },
            ],
        }
        self.assertEqual([], validate_test_mapping(mapping, make_snapshot(self.obligations)))

    def test_current_mapping_rejects_stale_manual_reason(self) -> None:
        """CURRENT 不能继续携带要求重新登记的过期说明。"""
        mapping = {
            "version": MAPPING_VERSION,
            "mappings": [
                {
                    "obligation_id": item["id"],
                    "obligation_sha256": item["sha256"],
                    "test_ids": [f"FeatureTest#t{index}"],
                    "mapping_status": "CURRENT",
                    "manual_reason": "需求已变化，请重新登记测试" if index == 1 else None,
                }
                for index, item in enumerate(self.obligations, start=1)
            ],
        }

        errors = validate_test_mapping(mapping, make_snapshot(self.obligations))
        self.assertTrue(any("仍表示映射过期" in error for error in errors))

    def test_template_test_cannot_cover_business_obligations(self) -> None:
        """Android Studio 默认模板测试不能作为业务义务证据。"""
        mapping = {
            "version": MAPPING_VERSION,
            "mappings": [
                {
                    "obligation_id": item["id"],
                    "obligation_sha256": item["sha256"],
                    "test_ids": ["example.ExampleUnitTest#addition_isCorrect"],
                    "mapping_status": "CURRENT",
                    "manual_reason": None,
                }
                for item in self.obligations
            ],
        }

        errors = validate_test_mapping(mapping, make_snapshot(self.obligations))
        self.assertTrue(any("无业务语义的模板测试" in error for error in errors))

    def test_revision_marks_changed_obligations_stale(self) -> None:
        """义务 sha256 变化后，脚本自动把对应登记刷新为 STALE。"""
        mapping_path = self.temp_root / "test-mapping.json"
        mapping = {
            "version": MAPPING_VERSION,
            "mappings": [
                {
                    "obligation_id": "BDD-001/T1",
                    "obligation_sha256": "a" * 64,
                    "test_ids": ["FeatureTest#t1"],
                    "mapping_status": "CURRENT",
                    "manual_reason": None,
                },
                {
                    "obligation_id": "BDD-002/T1",
                    "obligation_sha256": "b" * 64,
                    "test_ids": ["FeatureTest#t2"],
                    "mapping_status": "CURRENT",
                    "manual_reason": None,
                },
            ],
        }
        mapping_path.write_text(json.dumps(mapping), encoding="utf-8")
        # 需求增量：BDD-001/T1 语义变化，BDD-002/T1 不变。
        revised = make_snapshot([
            {"id": "BDD-001/T1", "sha256": "c" * 64, "text": "显示验证码", "required": True},
            self.obligations[1],
        ])
        mark_stale_after_revision(mapping_path, revised)
        updated = json.loads(mapping_path.read_text(encoding="utf-8"))
        statuses = {item["obligation_id"]: item["mapping_status"] for item in updated["mappings"]}
        self.assertEqual(statuses["BDD-001/T1"], "STALE")
        self.assertEqual(statuses["BDD-002/T1"], "CURRENT")
        sha = {item["obligation_id"]: item["obligation_sha256"] for item in updated["mappings"]}
        self.assertEqual(sha["BDD-001/T1"], "c" * 64)

    def test_current_mapping_with_stale_sha_rejected(self) -> None:
        """声明 CURRENT 但摘要与当前修订不符时校验失败。"""
        mapping = {
            "version": MAPPING_VERSION,
            "mappings": [
                {
                    "obligation_id": "BDD-001/T1",
                    "obligation_sha256": "0" * 64,
                    "test_ids": ["FeatureTest#t1"],
                    "mapping_status": "CURRENT",
                    "manual_reason": None,
                },
                {
                    "obligation_id": "BDD-002/T1",
                    "obligation_sha256": "b" * 64,
                    "test_ids": ["FeatureTest#t2"],
                    "mapping_status": "CURRENT",
                    "manual_reason": None,
                },
            ],
        }
        errors = validate_test_mapping(mapping, make_snapshot(self.obligations))
        self.assertTrue(any("声明 CURRENT 但未绑定当前需求语义摘要" in error for error in errors))

    def test_mapping_for_removed_obligation_rejected(self) -> None:
        """登记了已删除义务时校验失败。"""
        mapping = {
            "version": MAPPING_VERSION,
            "mappings": [
                {
                    "obligation_id": "BDD-001/T1",
                    "obligation_sha256": "a" * 64,
                    "test_ids": ["FeatureTest#t1"],
                    "mapping_status": "CURRENT",
                    "manual_reason": None,
                },
                {
                    "obligation_id": "BDD-009/T1",
                    "obligation_sha256": "9" * 64,
                    "test_ids": ["FeatureTest#t9"],
                    "mapping_status": "CURRENT",
                    "manual_reason": None,
                },
            ],
        }
        errors = validate_test_mapping(mapping, make_snapshot(self.obligations))
        self.assertTrue(any("登记了已删除或非当前的义务" in error for error in errors))

    def test_missing_obligation_rejected(self) -> None:
        """缺少当前义务登记时校验失败。"""
        mapping = {
            "version": MAPPING_VERSION,
            "mappings": [
                {
                    "obligation_id": "BDD-001/T1",
                    "obligation_sha256": "a" * 64,
                    "test_ids": ["FeatureTest#t1"],
                    "mapping_status": "CURRENT",
                    "manual_reason": None,
                },
            ],
        }
        errors = validate_test_mapping(mapping, make_snapshot(self.obligations))
        self.assertTrue(any("缺少当前确认义务的登记: BDD-002/T1" in error for error in errors))

    def test_architecture_tests_validated(self) -> None:
        """architecture_tests 必须是非重复字符串数组；结构合法时不影响 CURRENT 校验。"""
        mapping = {
            "version": MAPPING_VERSION,
            "mappings": [
                {
                    "obligation_id": "BDD-001/T1",
                    "obligation_sha256": "a" * 64,
                    "test_ids": ["FeatureTest#t1"],
                    "mapping_status": "CURRENT",
                    "manual_reason": None,
                    "architecture_tests": ["埋点只在统一出口", "X 不依赖 Y"],
                },
                {
                    "obligation_id": "BDD-002/T1",
                    "obligation_sha256": "b" * 64,
                    "test_ids": ["FeatureTest#t2"],
                    "mapping_status": "CURRENT",
                    "manual_reason": None,
                },
            ],
        }
        self.assertEqual([], validate_test_mapping(mapping, make_snapshot(self.obligations)))

        mapping["mappings"][0]["architecture_tests"] = ["dup", "dup"]
        errors = validate_test_mapping(mapping, make_snapshot(self.obligations))
        self.assertTrue(any("architecture_tests 不得重复" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
