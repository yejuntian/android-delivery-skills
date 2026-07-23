#!/usr/bin/env python3
"""脚本名称：requirement_inputs.py

用途：为需求正文、已确认实施计划及本次配置声明的 UI/API 资料生成稳定输入摘要。

核心流程：规范化 ``ui``、``api`` 配置，流式摘要本地截图、资源、接口文件和 UI
目录内容，再与需求正文和实施计划摘要一起生成单一 SHA-256。远程链接只绑定 URL；
实际远程内容仍由对应专项记录版本、抓取时间和产物摘要。

职责边界：不访问网络、不读取 Android 源码、不判断资料是否适用、不修改任何文件。
``testing``、设备和重试等执行环境不属于需求输入，变化时不会制造需求修订。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .config_paths import resolve_config_paths


def _sha256_file(path: Path) -> str:
    """流式计算资料摘要，避免截图或契约文件一次性读入内存。"""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _json_safe(value: Any) -> Any:
    """把 YAML 值转换为稳定 JSON 类型，未知标量保留可读字符串。"""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {
            str(key): _json_safe(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    return str(value)


def _declared_paths(section: Any, fields: tuple[str, ...]) -> list[tuple[str, str]]:
    """提取配置明确声明的本地路径；无效类型也进入规范值而不在此处猜测。"""
    if not isinstance(section, dict):
        return []
    declared: list[tuple[str, str]] = []
    for field in fields:
        value = section.get(field)
        values = value if isinstance(value, list) else [value]
        for item in values:
            if isinstance(item, str) and item.strip():
                declared.append((field, item.strip()))
    return declared


def _source_record(requirement_dir: Path, field: str, declaration: str) -> list[dict[str, Any]]:
    """记录一个文件或目录的存在性与内容摘要，不把绝对工作区写入规范清单。"""
    raw = Path(declaration).expanduser()
    resolved = raw.resolve() if raw.is_absolute() else (requirement_dir / raw).resolve()
    label = declaration.replace("\\", "/")
    if not resolved.exists():
        return [{"field": field, "declared": label, "status": "MISSING"}]
    if resolved.is_file():
        try:
            return [{
                "field": field,
                "declared": label,
                "status": "FILE",
                "size": resolved.stat().st_size,
                "sha256": _sha256_file(resolved),
            }]
        except OSError:
            return [{"field": field, "declared": label, "status": "UNREADABLE"}]
    if not resolved.is_dir():
        return [{"field": field, "declared": label, "status": "UNSUPPORTED"}]

    records: list[dict[str, Any]] = []
    try:
        children = sorted(path for path in resolved.rglob("*") if path.is_file())
    except OSError:
        return [{"field": field, "declared": label, "status": "UNREADABLE"}]
    if not children:
        return [{"field": field, "declared": label, "status": "EMPTY_DIRECTORY"}]
    for child in children:
        try:
            records.append({
                "field": field,
                "declared": label,
                "relative": child.relative_to(resolved).as_posix(),
                "status": "FILE",
                "size": child.stat().st_size,
                "sha256": _sha256_file(child),
            })
        except OSError:
            records.append({
                "field": field,
                "declared": label,
                "relative": child.relative_to(resolved).as_posix(),
                "status": "UNREADABLE",
            })
    return records


def requirement_inputs_manifest(
    config: dict[str, Any],
    config_path: str | Path,
    requirement_file_sha256: str,
    *,
    implementation_plan_sha256: str | None = None,
) -> dict[str, Any]:
    """构造不含资料正文的规范清单，供摘要、诊断和测试共同使用。"""
    paths = resolve_config_paths(config, config_path)
    ui = _json_safe(config.get("ui", {}))
    api = _json_safe(config.get("api", {}))
    records: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for section_name, section, fields in (
        ("ui", config.get("ui", {}), ("directory", "screenshots", "assets")),
        ("api", config.get("api", {}), ("files",)),
    ):
        for field, declaration in _declared_paths(section, fields):
            key = (f"{section_name}.{field}", declaration)
            if key in seen:
                continue
            seen.add(key)
            records.extend(_source_record(paths.requirement_dir, key[0], declaration))
    manifest = {
        "version": 1,
        "requirement_file_sha256": requirement_file_sha256,
        "ui": ui,
        "api": api,
        "local_sources": records,
    }
    if implementation_plan_sha256 is not None:
        manifest["implementation_plan_sha256"] = implementation_plan_sha256
    return manifest


def requirement_inputs_digest(
    config: dict[str, Any],
    config_path: str | Path,
    requirement_file_sha256: str,
    *,
    implementation_plan_sha256: str | None = None,
) -> str:
    """返回需求、计划、UI/API 配置与本地资料共同形成的稳定 SHA-256。"""
    manifest = requirement_inputs_manifest(
        config,
        config_path,
        requirement_file_sha256,
        implementation_plan_sha256=implementation_plan_sha256,
    )
    canonical = json.dumps(
        manifest,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()
