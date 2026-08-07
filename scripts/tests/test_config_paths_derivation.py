#!/usr/bin/env python3
"""脚本名称：test_config_paths_derivation.py

用途：验证 local.yaml 字段缺失时的缺省推导（项目内通道）。

核心覆盖：requirement_dir / workspace_root / requirement_file 缺失时自动按
project_path + requirement_name 推导；已填字段不被覆盖（向后兼容）。
"""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if globals().get("__package__") in {None, ""}:
    sys.path.insert(0, str(SCRIPTS_DIR.parent))
    __package__ = "scripts.tests"
    __spec__ = None

from ..config_paths import (  # noqa: E402
    _derive_requirement_dir,
    _derive_requirement_paths,
    _sanitize_dir_segment,
    resolve_config_paths,
)


class DeriveRequirementDirTests(unittest.TestCase):
    """缺省推导 requirement_dir = project_path/document/<日期>-<需求名>。"""

    def test_derives_from_project_and_name(self) -> None:
        project = Path("/tmp/proj")
        result = _derive_requirement_dir(project, "videoFeed", today_stamp="2026-08-07")
        self.assertEqual(result, (project / "document" / "2026-08-07-videoFeed").resolve())

    def test_returns_none_without_project(self) -> None:
        self.assertIsNone(_derive_requirement_dir(None, "videoFeed"))

    def test_returns_none_without_name(self) -> None:
        self.assertIsNone(_derive_requirement_dir(Path("/tmp/proj"), None))


class SanitizeSegmentTests(unittest.TestCase):
    """需求名中的非法目录字符被折叠为短横。"""

    def test_keeps_alnum_and_separators(self) -> None:
        self.assertEqual(_sanitize_dir_segment("videoFeed"), "videoFeed")
        self.assertEqual(_sanitize_dir_segment("login_v2"), "login_v2")

    def test_collapses_unsafe_chars(self) -> None:
        cleaned = _sanitize_dir_segment("foo bar/baz")
        self.assertNotIn(" ", cleaned)
        self.assertTrue(cleaned.startswith("foo"))

    def test_empty_falls_back(self) -> None:
        self.assertEqual(_sanitize_dir_segment("   "), "requirement")


class DerivePathsTests(unittest.TestCase):
    """workspace_root / requirement_dir 缺失时按层级推导。"""

    def test_workspace_defaults_to_project_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "proj"
            project.mkdir()
            workspace, req_dir, proj = _derive_requirement_paths(
                {"project_path": str(project)}, tmp
            )
            self.assertEqual(proj, project.resolve())
            self.assertEqual(workspace, project.resolve())

    def test_requirement_dir_derived_from_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "proj"
            project.mkdir()
            workspace, req_dir, proj = _derive_requirement_paths(
                {"project_path": str(project), "requirement_name": "videoFeed"},
                tmp,
            )
            self.assertTrue(req_dir.name.startswith(self._today_prefix()))
            self.assertEqual(req_dir.name.split("-", 3)[-1], "videoFeed")
            self.assertEqual(req_dir.parent.name, "document")

    def test_explicit_fields_not_overwritten(self) -> None:
        """已填的 requirement_dir / workspace_root 不被推导覆盖（向后兼容）。"""
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "proj"
            project.mkdir()
            explicit_dir = Path(tmp) / "explicit"
            explicit_dir.mkdir()
            workspace, req_dir, proj = _derive_requirement_paths(
                {
                    "project_path": str(project),
                    "workspace_root": str(Path(tmp)),
                    "requirement_dir": str(explicit_dir),
                },
                tmp,
            )
            self.assertEqual(req_dir, explicit_dir.resolve())
            self.assertEqual(workspace, Path(tmp).resolve())

    @staticmethod
    def _today_prefix() -> str:
        import datetime as _dt

        return _dt.date.today().isoformat()


class ResolveConfigPathsDerivationTests(unittest.TestCase):
    """端到端：resolve_config_paths 在字段不全时自动推导。"""

    def test_derives_dir_and_file_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "proj"
            project.mkdir()
            paths = resolve_config_paths(
                {
                    "project_path": str(project),
                    "requirement_name": "videoFeed",
                    "requirement_file": "requirement.docx",
                },
                tmp,
            )
            self.assertEqual(paths.project_path, project.resolve())
            self.assertEqual(paths.requirement_dir.parent.name, "document")
            self.assertTrue(paths.requirement_dir.name.endswith("videoFeed"))
            self.assertEqual(paths.requirement_path.name, "requirement.docx")

    def test_legacy_full_config_still_works(self) -> None:
        """旧的全字段 local.yaml（requirement_dir 显式）依然解析正确。"""
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "proj"
            project.mkdir()
            req_dir = project / "document" / "2026-08-07-videoFeed"
            req_dir.mkdir(parents=True)
            (req_dir / "docs").mkdir()
            (req_dir / "docs" / "videoFeed.md").write_text("# x")
            paths = resolve_config_paths(
                {
                    "project_path": str(project),
                    "workspace_root": str(project),
                    "requirement_dir": str(req_dir),
                    "requirement_file": "docs/videoFeed.md",
                },
                tmp,
            )
            self.assertEqual(paths.requirement_dir, req_dir.resolve())
            self.assertEqual(paths.requirement_path, (req_dir / "docs" / "videoFeed.md").resolve())


if __name__ == "__main__":
    unittest.main()
