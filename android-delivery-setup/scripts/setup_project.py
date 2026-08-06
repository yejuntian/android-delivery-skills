#!/usr/bin/env python3
"""Inspect an Android repository and create confirmed project-side delivery scaffolding."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any

import yaml


MODULE_PATTERN = re.compile(r"['\"](:[^'\"]+)['\"]")
GENERATED_FILES = (
    Path(".android-delivery/project.yaml"),
    Path(".android-delivery/channel.example.yaml"),
    Path("docs/agents/android-delivery.md"),
)


class SetupError(RuntimeError):
    """Raised when setup cannot safely inspect or write the requested project."""


def _declares(build_text: str, configuration: str) -> bool:
    """Match one Gradle configuration name without confusing androidTest with test."""
    return re.search(
        rf"(?<![a-z0-9_]){re.escape(configuration.lower())}(?![a-z0-9_])",
        build_text,
    ) is not None


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _android_root(value: str | Path) -> Path:
    root = Path(value).expanduser().resolve()
    if not root.is_dir():
        raise SetupError(f"Android 项目目录不存在: {root}")
    if not any((root / name).is_file() for name in ("settings.gradle", "settings.gradle.kts")):
        raise SetupError(f"未找到 settings.gradle(.kts): {root}")
    return root


def _modules(root: Path) -> list[str]:
    modules: set[str] = set()
    for name in ("settings.gradle.kts", "settings.gradle"):
        text = _read_text(root / name)
        modules.update(MODULE_PATTERN.findall(text))
    return sorted(modules)


def _build_text(root: Path) -> str:
    files = [root / "build.gradle", root / "build.gradle.kts"]
    for module in _modules(root):
        module_root = root.joinpath(*module.strip(":").split(":"))
        files.extend((module_root / "build.gradle", module_root / "build.gradle.kts"))
    return "\n".join(_read_text(path) for path in files if path.is_file())


def _has_layout_xml(root: Path) -> bool:
    for module in _modules(root):
        module_root = root.joinpath(*module.strip(":").split(":"))
        if any(module_root.glob("src/*/res/layout/*.xml")):
            return True
    return False


def _ui_system(root: Path) -> str:
    build_text = _build_text(root).lower()
    has_compose = "androidx.compose" in build_text or re.search(
        r"\bcompose\s*=\s*true\b", build_text
    ) is not None
    has_xml = _has_layout_xml(root)
    if has_compose and has_xml:
        return "mixed"
    if has_compose:
        return "compose"
    if has_xml:
        return "xml"
    return "unknown"


def _figma_skill_path() -> Path:
    ai_skills_root = Path(__file__).resolve().parents[3]
    return ai_skills_root / "figma-android-xml" / "SKILL.md"


def inspect_project(project: str | Path) -> dict[str, Any]:
    root = _android_root(project)
    wrapper = root / "gradlew"
    build_text = _build_text(root).lower()
    modules = _modules(root)
    ui_system = _ui_system(root)
    figma_source = _figma_skill_path()
    return {
        "schema_version": 1,
        "project": {
            "root": str(root),
            "git": (root / ".git").exists(),
            "settings": next(
                (name for name in ("settings.gradle.kts", "settings.gradle") if (root / name).is_file()),
                None,
            ),
            "gradle_wrapper": wrapper.is_file(),
            "modules": modules,
            "ui_system": ui_system,
        },
        "capabilities": {
            "unit_tests_declared": _declares(build_text, "testImplementation"),
            "instrumentation_declared": _declares(build_text, "androidTestImplementation"),
            "lint_declared": "lint" in build_text,
            "screenshot_testing_declared": any(
                token in build_text for token in ("paparazzi", "roborazzi", "shot")
            ),
        },
        "integrations": {
            "figma_android_xml": {
                "applicable": ui_system in {"xml", "mixed"},
                "source_present": figma_source.is_file(),
                "source_path": str(figma_source) if figma_source.is_file() else None,
                "invocation_must_be_verified": True,
            }
        },
        "existing": {
            "agents_md": (root / "AGENTS.md").is_file(),
            "claude_md": (root / "CLAUDE.md").is_file(),
            "delivery_dir": (root / ".android-delivery").is_dir(),
            "document_dir": (root / "document").is_dir(),
            "generated_files": {
                path.as_posix(): (root / path).is_file() for path in GENERATED_FILES
            },
        },
    }


def _project_config(report: dict[str, Any]) -> str:
    project = report["project"]
    payload = {
        "schema_version": 1,
        "project_root": "..",
        "gradle": {
            "settings": project["settings"],
            "wrapper": "./gradlew" if project["gradle_wrapper"] else None,
            "modules": project["modules"],
        },
        "ui": {
            "system": project["ui_system"],
            "figma_android_xml": {
                "enabled": report["integrations"]["figma_android_xml"]["applicable"],
                "optional": True,
            },
        },
        "capabilities": report["capabilities"],
    }
    return yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)


def _agent_doc(report: dict[str, Any]) -> str:
    ui_system = report["project"]["ui_system"]
    figma = report["integrations"]["figma_android_xml"]
    figma_line = (
        "XML/Figma 页面可在需求和计划确认后使用 `figma-android-xml` 生产布局；"
        "Compose 页面不得调用该 Skill。"
        if figma["applicable"]
        else "当前未确认 XML View 能力；不要仅因存在 Figma 链接调用 `figma-android-xml`。"
    )
    return f"""# Android Delivery Agent 约定

项目 UI 技术栈发现结果：`{ui_system}`。该值是初始化时的静态快照，项目结构变化后重新运行 setup。

- 完整 Android 新需求、需求变更和 Bug 修复使用 `android-implement-and-verify`。
- 需求和实施计划确认前不得修改生产代码；增量需求变化必须先写回需求事实源。
- 最终交付继续使用 SHA、STALE、影响半径、route 和新鲜证据门禁。
- {figma_line}
- `figma-android-xml` 只生产 XML/资源；业务接入、测试和真机视觉验收分别由总入口、`android-test-and-fix` 和 `android-verify-ui` 接管。
- 项目级无密配置见 `.android-delivery/project.yaml`，每个需求使用独立 channel 配置和 `document/<日期-英文名>/`。
"""


def _channel_template() -> str:
    source = Path(__file__).resolve().parents[1] / "assets" / "channel.example.yaml"
    if not source.is_file():
        raise SetupError(f"缺少 channel 模板: {source}")
    return source.read_text(encoding="utf-8")


def _write_atomic(path: Path, content: str, force: bool) -> str:
    if path.is_file():
        current = path.read_text(encoding="utf-8")
        if current == content:
            return "UNCHANGED"
        if not force:
            raise SetupError(f"文件已存在且内容不同，未覆盖: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return "WRITTEN"


def _planned_write_status(path: Path, content: str, force: bool) -> str:
    """Preflight one generated file so ordinary conflicts cannot leave a partial setup."""
    if not path.exists():
        return "WRITTEN"
    if not path.is_file():
        raise SetupError(f"生成路径已存在但不是普通文件: {path}")
    current = path.read_text(encoding="utf-8")
    if current == content:
        return "UNCHANGED"
    if not force:
        raise SetupError(f"文件已存在且内容不同，未覆盖: {path}")
    return "WRITTEN"


def apply_setup(project: str | Path, *, confirm: bool, force: bool) -> dict[str, Any]:
    if not confirm:
        raise SetupError("apply 必须显式提供 --confirm")
    root = _android_root(project)
    report = inspect_project(root)
    outputs = {
        Path(".android-delivery/project.yaml"): _project_config(report),
        Path(".android-delivery/channel.example.yaml"): _channel_template(),
        Path("docs/agents/android-delivery.md"): _agent_doc(report),
    }
    planned = {
        relative: _planned_write_status(root / relative, content, force)
        for relative, content in outputs.items()
    }
    results: dict[str, str] = {}
    for relative, content in outputs.items():
        status = planned[relative]
        if status == "WRITTEN":
            status = _write_atomic(root / relative, content, force)
        results[relative.as_posix()] = status
    return {"project": str(root), "files": results, "agent_file_modified": False}


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect or initialize Android Delivery project files.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    inspect_parser = subparsers.add_parser("inspect", help="只读检查 Android 项目")
    inspect_parser.add_argument("--project", required=True)
    apply_parser = subparsers.add_parser("apply", help="确认后创建项目侧配置")
    apply_parser.add_argument("--project", required=True)
    apply_parser.add_argument("--confirm", action="store_true")
    apply_parser.add_argument("--force", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        result = (
            inspect_project(args.project)
            if args.command == "inspect"
            else apply_setup(args.project, confirm=args.confirm, force=args.force)
        )
    except (OSError, SetupError, yaml.YAMLError) as exc:
        print(f"Android Delivery setup 失败: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
