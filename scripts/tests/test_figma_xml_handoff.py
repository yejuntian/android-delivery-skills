#!/usr/bin/env python3
"""Tests for Figma XML handoff scope and semantic-change gates."""

from __future__ import annotations

from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if globals().get("__package__") in {None, ""}:
    sys.path.insert(0, str(SCRIPTS_DIR.parent))
    __package__ = "scripts.tests"
    __spec__ = None

from ..figma_xml_handoff import (
    changed_files_since_snapshot,
    create_project_snapshot,
    main as figma_handoff_main,
    validate_figma_xml_handoff,
)


FILE_CONTENT = b"<FrameLayout />\n"
FILE_SHA256 = hashlib.sha256(FILE_CONTENT).hexdigest()
REQUIREMENT_INPUTS_SHA256 = "a" * 64


def radius() -> dict:
    return {
        "allowed_files": ["app/src/main/res/layout/login.xml"],
        "allowed_dirs": ["app/src/main/res/drawable/", "app/src/main/res/values/"],
        "impacts": [{
            "expected_files": [
                "app/src/main/res/layout/login.xml",
                "app/src/main/res/drawable/",
                "app/src/main/res/values/",
            ]
        }],
    }


def result() -> dict:
    return {
        "version": 1,
        "producer": "figma-android-xml",
        "requirement_id": "REQ-1",
        "requirement_revision": 1,
        "requirement_inputs_sha256": REQUIREMENT_INPUTS_SHA256,
        "ui_technology": "XML",
        "source": {
            "design_links": ["https://www.figma.com/design/example"],
            "node_ids": ["1:2"],
            "source_sha256": "b" * 64,
        },
        "files": [{
            "path": "app/src/main/res/layout/login.xml",
            "kind": "LAYOUT",
            "sha256": FILE_SHA256,
        }],
        "semantic_change": "VISUAL_ONLY",
        "assumptions": [],
        "validation": [],
    }


class FigmaXmlHandoffTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name)
        target = self.project / "app" / "src" / "main" / "res" / "layout" / "login.xml"
        target.parent.mkdir(parents=True)
        target.write_bytes(FILE_CONTENT)

    def validate(
        self,
        payload: dict,
        impact_radius: dict,
        actual_changed_files: set[str] | None = None,
    ) -> list[str]:
        declared = {
            item["path"] for item in payload.get("files", []) if isinstance(item, dict) and "path" in item
        }
        return validate_figma_xml_handoff(
            payload,
            impact_radius,
            expected_requirement_id="REQ-1",
            expected_requirement_revision=1,
            expected_requirement_inputs_sha256=REQUIREMENT_INPUTS_SHA256,
            project_root=self.project,
            actual_changed_files=declared if actual_changed_files is None else actual_changed_files,
        )

    def test_visual_only_xml_in_radius_is_accepted(self) -> None:
        self.assertEqual([], self.validate(result(), radius()))

    def test_code_and_out_of_radius_files_are_rejected(self) -> None:
        payload = result()
        payload["files"] = [{
            "path": "app/src/main/java/LoginActivity.kt",
            "kind": "OTHER_RESOURCE",
            "sha256": "d" * 64,
        }]
        errors = self.validate(payload, radius())
        self.assertTrue(any("Kotlin/Java" in error for error in errors))
        self.assertTrue(any("超出已确认影响半径" in error for error in errors))

    def test_behavior_change_requires_requirement_revision(self) -> None:
        payload = result()
        payload["semantic_change"] = "BEHAVIOR_CHANGE"
        errors = self.validate(payload, radius())
        self.assertTrue(any("需求修订闭环" in error for error in errors))

    def test_stale_requirement_inputs_are_rejected(self) -> None:
        payload = result()
        payload["requirement_inputs_sha256"] = "e" * 64
        errors = self.validate(payload, radius())
        self.assertTrue(any("requirement_inputs_sha256 已失效" in error for error in errors))

    def test_file_digest_must_match_the_actual_project_file(self) -> None:
        target = self.project / "app" / "src" / "main" / "res" / "layout" / "login.xml"
        target.write_text("<LinearLayout />\n", encoding="utf-8")
        errors = self.validate(result(), radius())
        self.assertTrue(any("SHA-256 与实际文件不一致" in error for error in errors))

    def test_non_android_resource_cannot_be_disguised_as_other_resource(self) -> None:
        target = self.project / "docs" / "generated.txt"
        target.parent.mkdir()
        target.write_text("generated\n", encoding="utf-8")
        payload = result()
        payload["files"] = [{
            "path": "docs/generated.txt",
            "kind": "OTHER_RESOURCE",
            "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        }]
        impact_radius = radius()
        impact_radius["allowed_files"] = ["docs/generated.txt"]
        impact_radius["allowed_dirs"] = []
        impact_radius["impacts"][0]["expected_files"] = ["docs/generated.txt"]

        errors = self.validate(payload, impact_radius)
        self.assertTrue(any("必须位于 Android" in error for error in errors))

    def test_provider_cannot_omit_an_actual_changed_file(self) -> None:
        hidden = "app/src/main/java/LoginActivity.kt"
        errors = self.validate(
            result(),
            radius(),
            actual_changed_files={"app/src/main/res/layout/login.xml", hidden},
        )
        self.assertTrue(any("未在交接结果声明" in error and hidden in error for error in errors))

    def test_project_snapshot_detects_modified_and_added_files(self) -> None:
        subprocess.run(["git", "init", "-q", str(self.project)], check=True)
        before = create_project_snapshot(self.project)
        layout = self.project / "app" / "src" / "main" / "res" / "layout" / "login.xml"
        layout.write_text("<LinearLayout />\n", encoding="utf-8")
        hidden = self.project / "app" / "src" / "main" / "java" / "LoginActivity.kt"
        hidden.parent.mkdir(parents=True)
        hidden.write_text("class LoginActivity\n", encoding="utf-8")

        self.assertEqual(
            {
                "app/src/main/java/LoginActivity.kt",
                "app/src/main/res/layout/login.xml",
            },
            changed_files_since_snapshot(self.project, before),
        )

    def test_project_snapshot_detects_permission_mode_changes(self) -> None:
        subprocess.run(["git", "init", "-q", str(self.project)], check=True)
        before = create_project_snapshot(self.project)
        layout = self.project / "app" / "src" / "main" / "res" / "layout" / "login.xml"
        layout.chmod(0o755)

        self.assertEqual(
            {"app/src/main/res/layout/login.xml"},
            changed_files_since_snapshot(self.project, before),
        )

    def test_snapshot_and_validate_cli_flow(self) -> None:
        subprocess.run(["git", "init", "-q", str(self.project)], check=True)
        state = self.project / ".state"
        state.mkdir()
        impact_radius_path = state / "impact-radius.json"
        impact_radius_path.write_text(json.dumps(radius()), encoding="utf-8")
        before_path = state / "figma-before.json"

        with redirect_stdout(io.StringIO()):
            snapshot_exit = figma_handoff_main([
                "snapshot",
                "--project", str(self.project),
                "--output", str(before_path),
            ])
        self.assertEqual(0, snapshot_exit)

        layout = self.project / "app" / "src" / "main" / "res" / "layout" / "login.xml"
        layout.write_text("<LinearLayout />\n", encoding="utf-8")
        payload = result()
        payload["files"][0]["sha256"] = hashlib.sha256(layout.read_bytes()).hexdigest()
        result_path = state / "figma-result.json"
        result_path.write_text(json.dumps(payload), encoding="utf-8")

        with redirect_stdout(io.StringIO()):
            validate_exit = figma_handoff_main([
                "validate",
                "--result", str(result_path),
                "--impact-radius", str(impact_radius_path),
                "--before-snapshot", str(before_path),
                "--project", str(self.project),
                "--requirement-id", "REQ-1",
                "--requirement-revision", "1",
                "--requirement-inputs-sha256", REQUIREMENT_INPUTS_SHA256,
            ])
        self.assertEqual(0, validate_exit)


if __name__ == "__main__":
    unittest.main()
