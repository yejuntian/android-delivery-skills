#!/usr/bin/env python3
"""脚本名称：test_requirement_inputs.py

用途：验证需求正文、实施计划、UI 与 API 资料共同形成稳定输入摘要，并忽略执行环境配置。

覆盖范围：配置字段变化、本地文件内容变化、缺失文件和与需求无关的 testing 配置。
测试只使用临时目录，不访问远程链接或真实 Android 项目。
"""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if __package__ in {None, ""}:
    sys.path.insert(0, str(SCRIPTS_DIR.parent))
    __package__ = "scripts.tests"

from ..requirement_inputs import (  # noqa: E402
    RequirementInputError,
    requirement_inputs_digest,
    validate_requirement_input_boundaries,
)


class RequirementInputsTests(unittest.TestCase):
    """验证只有真实需求资料变化才会使 route 和旧证据失效。"""

    def setUp(self) -> None:
        """建立需求目录、本地 UI 截图和接口契约样例。"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.config_path = self.root / "profiles" / "local.yaml"
        self.config_path.parent.mkdir()
        self.requirement_dir = self.root / "requirements"
        self.requirement_dir.mkdir()
        (self.requirement_dir / "ui").mkdir()
        self.screenshot = self.requirement_dir / "ui" / "home.png"
        self.screenshot.write_bytes(b"image-v1")
        self.contract = self.requirement_dir / "openapi.json"
        self.contract.write_text('{"version":1}\n', encoding="utf-8")
        self.config = {
            "workspace_root": str(self.root),
            "requirement_dir": "requirements",
            "ui": {
                "links": ["https://figma.example/design/1"],
                "directory": "ui",
                "screenshots": ["ui/home.png"],
                "assets": [],
                "notes": "首页",
            },
            "api": {
                "links": ["https://api.example/openapi"],
                "files": ["openapi.json"],
                "status": "confirmed",
                "notes": "正式契约",
            },
            "testing": {"journey_harness": {"retries": 2}},
        }

    def digest(self, config: dict | None = None) -> str:
        """返回固定需求正文摘要下的完整输入摘要。"""
        return requirement_inputs_digest(
            config or self.config,
            self.config_path,
            "a" * 64,
        )

    def test_ui_api_config_and_local_files_change_digest(self) -> None:
        """验证链接、说明和本地资料变化都会让旧 route 与证据失效。"""
        original = self.digest()
        changed_link = {**self.config, "api": {**self.config["api"], "links": ["https://api.example/v2"]}}
        self.assertNotEqual(original, self.digest(changed_link))

        self.contract.write_text('{"version":2}\n', encoding="utf-8")
        self.assertNotEqual(original, self.digest())

    def test_testing_environment_does_not_change_requirement_digest(self) -> None:
        """验证重试次数和设备配置属于执行环境，不制造虚假的需求修订。"""
        changed = {
            **self.config,
            "testing": {"journey_harness": {"retries": 5, "device": "emulator-5554"}},
        }
        self.assertEqual(self.digest(), self.digest(changed))

    def test_missing_declared_source_is_part_of_digest(self) -> None:
        """验证声明文件缺失不会被静默忽略，文件随后出现会改变摘要。"""
        missing_config = {
            **self.config,
            "api": {**self.config["api"], "files": ["future-openapi.json"]},
        }
        missing_digest = self.digest(missing_config)
        (self.requirement_dir / "future-openapi.json").write_text("{}\n", encoding="utf-8")
        self.assertNotEqual(missing_digest, self.digest(missing_config))

    def test_confirmed_plan_change_invalidates_input_digest(self) -> None:
        """验证计划变化会让旧 route、测试收据和专项证据失效。"""
        first = requirement_inputs_digest(
            self.config,
            self.config_path,
            "a" * 64,
            implementation_plan_sha256="b" * 64,
        )
        second = requirement_inputs_digest(
            self.config,
            self.config_path,
            "a" * 64,
            implementation_plan_sha256="c" * 64,
        )
        self.assertNotEqual(first, second)

    def test_confirmed_impact_radius_change_invalidates_input_digest(self) -> None:
        """验证影响半径变化会让旧 route、测试收据和专项证据失效。"""
        first = requirement_inputs_digest(
            self.config,
            self.config_path,
            "a" * 64,
            implementation_plan_sha256="b" * 64,
            impact_radius_sha256="c" * 64,
        )
        second = requirement_inputs_digest(
            self.config,
            self.config_path,
            "a" * 64,
            implementation_plan_sha256="b" * 64,
            impact_radius_sha256="d" * 64,
        )
        self.assertNotEqual(first, second)

    def test_output_directory_cannot_be_used_as_ui_input(self) -> None:
        """验证截图输入不能指向运行时 evidence 输出目录。"""
        config = {**self.config, "ui": {**self.config["ui"], "directory": "evidence/ui"}}

        with self.assertRaisesRegex(RequirementInputError, "与运行输出目录重叠"):
            validate_requirement_input_boundaries(config, self.config_path)

    def test_read_only_ui_input_directory_is_allowed(self) -> None:
        """验证独立只读参考目录不受输出边界门禁影响。"""
        config = {**self.config, "ui": {**self.config["ui"], "directory": "ui/reference"}}

        validate_requirement_input_boundaries(config, self.config_path)


if __name__ == "__main__":
    unittest.main()
