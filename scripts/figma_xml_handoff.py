#!/usr/bin/env python3
"""Validate Figma XML producer output before Android Delivery accepts it."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

if globals().get("__package__") in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = "scripts"

from .atomic_write import write_json_atomic  # noqa: E402
from .impact_radius import path_allowed_by_radius  # noqa: E402


SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
ALLOWED_KINDS = {"LAYOUT", "DRAWABLE", "VALUES", "FONT", "BITMAP", "OTHER_RESOURCE"}
ALLOWED_SEMANTIC_CHANGES = {"NONE", "VISUAL_ONLY", "BEHAVIOR_CHANGE", "UNKNOWN"}
SNAPSHOT_VERSION = 1
ANDROID_RESOURCE_DIRS = {
    "anim",
    "animator",
    "color",
    "drawable",
    "font",
    "interpolator",
    "layout",
    "menu",
    "mipmap",
    "navigation",
    "raw",
    "transition",
    "values",
    "xml",
}
KIND_RESOURCE_DIRS = {
    "LAYOUT": {"layout"},
    "DRAWABLE": {"drawable"},
    "VALUES": {"values"},
    "FONT": {"font"},
    "BITMAP": {"drawable", "mipmap"},
    "OTHER_RESOURCE": ANDROID_RESOURCE_DIRS,
}


def _load_json(path: str | Path, label: str) -> Any:
    source = Path(path).expanduser().resolve()
    try:
        return json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} 无法读取: {source}: {exc}") from exc


def _git(root: Path, args: list[str]) -> bytes:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        raise ValueError(f"无法执行 Git: {exc}") from exc
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(f"Git 检查失败: {detail or 'unknown error'}")
    return completed.stdout


def _path_digest(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(f"mode:{path.lstat().st_mode & 0o7777:o}\0".encode("ascii"))
    if path.is_symlink():
        digest.update(b"symlink\0")
        digest.update(os.readlink(path).encode("utf-8", errors="surrogateescape"))
        return digest.hexdigest()
    if path.is_file():
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()
    if path.is_dir():
        digest.update(b"gitlink\0")
        digest.update(_git(path, ["rev-parse", "HEAD"]).strip())
        digest.update(b"\0")
        digest.update(_git(path, ["status", "--porcelain=v1", "-z"]))
        return digest.hexdigest()
    raise ValueError(f"Git 文件无法读取: {path}")


def create_project_snapshot(project_root: str | Path) -> dict[str, Any]:
    root = Path(project_root).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"Android 项目根目录不存在: {root}")
    top_level = Path(
        _git(root, ["rev-parse", "--show-toplevel"])
        .decode("utf-8", errors="surrogateescape")
        .strip()
    ).resolve()
    if top_level != root:
        raise ValueError(f"--project 必须是 Git worktree 根目录: {top_level}")
    raw_paths = _git(root, ["ls-files", "-z", "--cached", "--others", "--exclude-standard"])
    relative_paths = sorted(
        item.decode("utf-8", errors="surrogateescape")
        for item in raw_paths.split(b"\0")
        if item
    )
    files = {relative: _path_digest(root / relative) for relative in relative_paths}
    return {
        "version": SNAPSHOT_VERSION,
        "producer": "android-delivery/figma-xml-before-snapshot",
        "project_root": str(root),
        "files": files,
    }


def load_project_snapshot(path: str | Path) -> dict[str, Any]:
    payload = _load_json(path, "Figma 调用前快照")
    if not isinstance(payload, dict):
        raise ValueError("Figma 调用前快照根节点必须是 object")
    if payload.get("version") != SNAPSHOT_VERSION:
        raise ValueError(f"Figma 调用前快照 version 必须为 {SNAPSHOT_VERSION}")
    if payload.get("producer") != "android-delivery/figma-xml-before-snapshot":
        raise ValueError("Figma 调用前快照 producer 无效")
    files = payload.get("files")
    if not isinstance(files, dict) or any(
        not isinstance(key, str)
        or not isinstance(value, str)
        or SHA256_PATTERN.fullmatch(value) is None
        for key, value in files.items()
    ):
        raise ValueError("Figma 调用前快照 files 无效")
    return payload


def changed_files_since_snapshot(
    project_root: str | Path,
    before: dict[str, Any],
    *,
    exclude_paths: set[str] | None = None,
) -> set[str]:
    current = create_project_snapshot(project_root)
    if before.get("project_root") != current["project_root"]:
        raise ValueError("Figma 调用前快照与当前 Android 项目不一致")
    previous_files = before["files"]
    current_files = current["files"]
    changed = {
        path
        for path in set(previous_files) | set(current_files)
        if previous_files.get(path) != current_files.get(path)
    }
    excluded = {path.replace("\\", "/") for path in (exclude_paths or set())}
    return {path.replace("\\", "/") for path in changed if path not in excluded}


def _relative_path_if_inside(path: str | Path, root: Path) -> str | None:
    try:
        return Path(path).expanduser().resolve().relative_to(root).as_posix()
    except ValueError:
        return None


def _resource_directory(path: str) -> str | None:
    parts = Path(path).parts
    for index, part in enumerate(parts):
        if part != "src" or index + 3 >= len(parts) or parts[index + 2] != "res":
            continue
        return parts[index + 3].split("-", 1)[0]
    return None


def _validate_string_list(value: Any, label: str, errors: list[str], *, required: bool) -> None:
    if not isinstance(value, list) or (required and not value):
        qualifier = "非空" if required else ""
        errors.append(f"{label} 必须是{qualifier}字符串数组")
        return
    if any(not isinstance(item, str) or not item.strip() for item in value):
        errors.append(f"{label} 必须是字符串数组且不得包含空值")
    strings = [item for item in value if isinstance(item, str)]
    if len(strings) != len(set(strings)):
        errors.append(f"{label} 不得包含重复项")


def validate_figma_xml_handoff(
    payload: Any,
    impact_radius: Any,
    *,
    expected_requirement_id: str,
    expected_requirement_revision: int,
    expected_requirement_inputs_sha256: str,
    project_root: str | Path,
    actual_changed_files: set[str],
) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["Figma XML 交接结果根节点必须是 object"]
    if not isinstance(impact_radius, dict):
        return ["影响半径根节点必须是 object"]
    allowed_keys = {
        "version",
        "producer",
        "requirement_id",
        "requirement_revision",
        "requirement_inputs_sha256",
        "ui_technology",
        "module",
        "source",
        "files",
        "semantic_change",
        "assumptions",
        "validation",
    }
    extra = sorted(set(payload) - allowed_keys)
    if extra:
        errors.append("交接结果包含未知字段: " + ", ".join(extra))
    if payload.get("version") != 1:
        errors.append("version 必须为 1")
    if payload.get("producer") != "figma-android-xml":
        errors.append("producer 必须为 figma-android-xml")
    if payload.get("ui_technology") not in {"XML", "MIXED_XML_PAGE"}:
        errors.append("ui_technology 必须是 XML 或 MIXED_XML_PAGE")
    if payload.get("semantic_change") not in ALLOWED_SEMANTIC_CHANGES:
        errors.append("semantic_change 无效")
    for field in ("requirement_id",):
        if not isinstance(payload.get(field), str) or not payload[field].strip():
            errors.append(f"{field} 必须是非空字符串")
    if not isinstance(payload.get("requirement_revision"), int) or isinstance(
        payload.get("requirement_revision"), bool
    ) or payload.get("requirement_revision", 0) < 1:
        errors.append("requirement_revision 必须是正整数")
    if not isinstance(payload.get("requirement_inputs_sha256"), str) or not SHA256_PATTERN.fullmatch(
        payload.get("requirement_inputs_sha256", "")
    ):
        errors.append("requirement_inputs_sha256 必须是 64 位小写 SHA-256")
    if payload.get("requirement_id") != expected_requirement_id:
        errors.append("requirement_id 与当前需求不一致")
    if payload.get("requirement_revision") != expected_requirement_revision:
        errors.append("requirement_revision 与当前需求修订不一致")
    if payload.get("requirement_inputs_sha256") != expected_requirement_inputs_sha256:
        errors.append("requirement_inputs_sha256 已失效")
    module = payload.get("module")
    if module is not None and (not isinstance(module, str) or not module.strip()):
        errors.append("module 必须是非空字符串")

    source = payload.get("source")
    if not isinstance(source, dict):
        errors.append("source 必须是 object")
    else:
        source_extra = sorted(set(source) - {"design_links", "node_ids", "source_sha256"})
        if source_extra:
            errors.append("source 包含未知字段: " + ", ".join(source_extra))
        links = source.get("design_links")
        _validate_string_list(links, "source.design_links", errors, required=True)
        _validate_string_list(source.get("node_ids"), "source.node_ids", errors, required=False)
        if not isinstance(source.get("source_sha256"), str) or not SHA256_PATTERN.fullmatch(
            source.get("source_sha256", "")
        ):
            errors.append("source.source_sha256 必须是 64 位小写 SHA-256")

    root = Path(project_root).expanduser().resolve()
    if not root.is_dir():
        errors.append(f"Android 项目根目录不存在: {root}")

    files = payload.get("files")
    if not isinstance(files, list) or not files:
        errors.append("files 必须是非空数组")
        files = []
    seen: set[str] = set()
    for index, item in enumerate(files):
        if not isinstance(item, dict):
            errors.append(f"files[{index}] 必须是 object")
            continue
        item_extra = sorted(set(item) - {"path", "kind", "sha256"})
        if item_extra:
            errors.append(f"files[{index}] 包含未知字段: {', '.join(item_extra)}")
        path = item.get("path")
        if not isinstance(path, str) or not path.strip():
            errors.append(f"files[{index}].path 必须是非空字符串")
            continue
        normalized = path.strip().replace("\\", "/")
        if normalized in seen:
            errors.append(f"files 路径重复: {normalized}")
        seen.add(normalized)
        path_object = Path(normalized)
        invalid_relative = (
            path_object.is_absolute()
            or normalized == ".."
            or normalized.startswith("../")
            or "/../" in normalized
        )
        if invalid_relative:
            errors.append(f"files[{index}].path 必须是仓库相对路径: {normalized}")
        if path_object.suffix.lower() in {".kt", ".java"}:
            errors.append(f"figma-android-xml 不得交付 Kotlin/Java: {normalized}")
        if not path_allowed_by_radius(normalized, impact_radius):
            errors.append(f"Figma XML 产物超出已确认影响半径: {normalized}")
        kind = item.get("kind")
        if kind not in ALLOWED_KINDS:
            errors.append(f"files[{index}].kind 无效")
        resource_directory = _resource_directory(normalized)
        if resource_directory is None:
            errors.append(f"Figma XML 产物必须位于 Android src/<sourceSet>/res 目录: {normalized}")
        elif kind in KIND_RESOURCE_DIRS and resource_directory not in KIND_RESOURCE_DIRS[kind]:
            errors.append(
                f"files[{index}].kind={kind} 与资源目录 {resource_directory} 不一致"
            )
        if not isinstance(item.get("sha256"), str) or not SHA256_PATTERN.fullmatch(
            item.get("sha256", "")
        ):
            errors.append(f"files[{index}].sha256 必须是 64 位小写 SHA-256")
        if not invalid_relative and root.is_dir():
            candidate = (root / normalized).resolve()
            try:
                candidate.relative_to(root)
            except ValueError:
                errors.append(f"files[{index}].path 解析后越出 Android 项目: {normalized}")
            else:
                if not candidate.is_file():
                    errors.append(f"Figma XML 产物文件不存在: {normalized}")
                else:
                    try:
                        actual_sha256 = hashlib.sha256(candidate.read_bytes()).hexdigest()
                    except OSError as exc:
                        errors.append(f"Figma XML 产物文件无法读取: {normalized}: {exc}")
                    else:
                        if item.get("sha256") != actual_sha256:
                            errors.append(
                                f"Figma XML 产物 SHA-256 与实际文件不一致: {normalized}"
                            )
    normalized_changed = {path.replace("\\", "/") for path in actual_changed_files}
    undeclared = sorted(normalized_changed - seen)
    if undeclared:
        errors.append("Figma provider 存在未在交接结果声明的改动: " + ", ".join(undeclared))
    _validate_string_list(payload.get("assumptions"), "assumptions", errors, required=False)
    validation = payload.get("validation")
    if not isinstance(validation, list):
        errors.append("validation 必须是数组")
    else:
        for index, item in enumerate(validation):
            if not isinstance(item, dict):
                errors.append(f"validation[{index}] 必须是 object")
                continue
            item_extra = sorted(set(item) - {"command", "status", "receipt", "reason"})
            if item_extra:
                errors.append(f"validation[{index}] 包含未知字段: {', '.join(item_extra)}")
            _validate_string_list(
                item.get("command"), f"validation[{index}].command", errors, required=True
            )
            if item.get("status") not in {"PASS", "FAIL", "UNVERIFIED", "BLOCKED"}:
                errors.append(f"validation[{index}].status 无效")
            for field in ("receipt", "reason"):
                if field in item and (not isinstance(item[field], str) or not item[field].strip()):
                    errors.append(f"validation[{index}].{field} 必须是非空字符串")
    if payload.get("semantic_change") in {"BEHAVIOR_CHANGE", "UNKNOWN"}:
        errors.append("Figma 输入包含或可能包含行为语义变化，必须先进入需求修订闭环")
    return errors


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Snapshot or validate figma-android-xml output.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    snapshot = subparsers.add_parser("snapshot", help="调用 Figma provider 前记录项目文件快照")
    snapshot.add_argument("--project", required=True, help="Android 项目 Git worktree 根目录")
    snapshot.add_argument("--output", required=True, help="调用前快照输出路径")

    validate = subparsers.add_parser("validate", help="校验 Figma provider 交接结果")
    validate.add_argument("--result", required=True, help="figma-xml-result.json")
    validate.add_argument("--impact-radius", required=True, help="impact-radius.json")
    validate.add_argument("--before-snapshot", required=True, help="snapshot 子命令生成的调用前快照")
    validate.add_argument("--project", required=True, help="Android 项目 Git worktree 根目录")
    validate.add_argument("--requirement-id", required=True, help="当前 requirement_id")
    validate.add_argument("--requirement-revision", required=True, type=int, help="当前需求修订号")
    validate.add_argument(
        "--requirement-inputs-sha256",
        required=True,
        help="当前 requirement_inputs_sha256",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.command == "snapshot":
        try:
            snapshot = create_project_snapshot(args.project)
            write_json_atomic(args.output, snapshot)
        except (OSError, ValueError) as exc:
            print(f"Figma XML 调用前快照失败: {exc}", file=sys.stderr)
            return 2
        print(f"Figma XML 调用前快照已写入: {Path(args.output).expanduser().resolve()}")
        return 0

    try:
        payload = _load_json(args.result, "交接结果")
        impact_radius = _load_json(args.impact_radius, "影响半径")
        before = load_project_snapshot(args.before_snapshot)
        root = Path(args.project).expanduser().resolve()
        excluded = {
            relative
            for relative in (
                _relative_path_if_inside(args.before_snapshot, root),
                _relative_path_if_inside(args.result, root),
            )
            if relative is not None
        }
        actual_changed_files = changed_files_since_snapshot(
            root,
            before,
            exclude_paths=excluded,
        )
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    errors = validate_figma_xml_handoff(
        payload,
        impact_radius,
        expected_requirement_id=args.requirement_id,
        expected_requirement_revision=args.requirement_revision,
        expected_requirement_inputs_sha256=args.requirement_inputs_sha256,
        project_root=args.project,
        actual_changed_files=actual_changed_files,
    )
    if errors:
        print("Figma XML 交接校验失败：", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("Figma XML 交接校验通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
