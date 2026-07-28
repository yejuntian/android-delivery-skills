#!/usr/bin/env python3
"""验证聊天事实收件箱的状态、物化和损坏输入门禁。"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if __package__ in {None, ""}:
    sys.path.insert(0, str(SCRIPTS_DIR.parent))
    __package__ = "scripts.tests"

from ..fact_inbox import (  # noqa: E402
    FactInboxError,
    add_fact,
    blocking_facts,
    empty_fact_inbox,
    load_fact_inbox,
    materialize_confirmed_facts,
    resolve_fact,
    validate_fact_inbox,
)


class FactInboxTests(unittest.TestCase):
    """事实收件箱只记录候选，需求修订成功后才解除流程阻断。"""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.path = Path(self.temp_dir.name) / ".state" / "fact-inbox.json"

    def test_new_fact_is_pending_and_blocks(self) -> None:
        fact = add_fact(
            self.path,
            "还要支持空数组",
            missing=["scope", "expected_result"],
        )

        self.assertEqual("FACT-001", fact["id"])
        self.assertEqual("PENDING", fact["status"])
        self.assertEqual([fact], blocking_facts(load_fact_inbox(self.path)))

    def test_discussion_and_rejected_fact_do_not_block(self) -> None:
        discussion = add_fact(self.path, "也许以后支持批量导入", status="DISCUSSION")
        self.assertEqual([], blocking_facts(load_fact_inbox(self.path)))

        resolve_fact(self.path, discussion["id"], "REJECTED")
        self.assertEqual([], blocking_facts(load_fact_inbox(self.path)))

    def test_confirmed_fact_requires_complete_boundary_and_materialization(self) -> None:
        fact = add_fact(self.path, "还要支持空数组", missing=["expected_result"])
        resolve_fact(self.path, fact["id"], "CONFIRMED")
        self.assertEqual(1, len(blocking_facts(load_fact_inbox(self.path))))

        resolve_fact(self.path, fact["id"], "CONFIRMED", clear_missing=True)
        self.assertEqual(1, len(blocking_facts(load_fact_inbox(self.path))))

        sha256 = "a" * 64
        updated = materialize_confirmed_facts(self.path, 2, sha256)
        self.assertEqual([fact["id"]], updated)
        current = load_fact_inbox(self.path)["facts"][0]
        self.assertEqual(2, current["materialized_revision"])
        self.assertEqual(sha256, current["materialized_requirement_sha256"])
        self.assertEqual([], blocking_facts(load_fact_inbox(self.path)))

    def test_corrupt_or_duplicate_inbox_is_rejected(self) -> None:
        payload = empty_fact_inbox()
        payload["facts"] = [
            {
                "id": "FACT-001",
                "text": "事实 A",
                "source": "chat",
                "status": "PENDING",
                "meaning": "CLEAR",
                "missing": [],
                "created_at": "2026-07-29T00:00:00+00:00",
                "updated_at": "2026-07-29T00:00:00+00:00",
                "materialized_revision": None,
                "materialized_requirement_sha256": None,
            },
        ]
        payload["facts"].append(dict(payload["facts"][0]))
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps(payload), encoding="utf-8")

        errors = validate_fact_inbox(payload)
        self.assertTrue(any("重复 id" in error for error in errors))
        with self.assertRaises(FactInboxError):
            load_fact_inbox(self.path)


if __name__ == "__main__":
    unittest.main()
