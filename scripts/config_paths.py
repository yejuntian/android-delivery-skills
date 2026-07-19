#!/usr/bin/env python3
"""脚本名称：config_paths.py

用途：统一解析 Android Delivery 配置路径及项目外基线、路由和证据位置。

职责边界：只根据配置文件位置和显式字段解析路径，不读取需求正文、不检查 Git，
也不决定 Skill 路由。Delivery 与 Journey 共用本模块，避免同一相对路径指向不同位置。
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ConfigPaths:
    """保存完成解析后的配置路径，调用方无需再次拼接相对目录。"""

    config_path: Path
    workspace_root: Path
    project_path: Path | None
    requirement_dir: Path
    requirement_path: Path | None


def _resolve(value: Any, base: Path) -> Path | None:
    """只基于明确父目录解析路径，不搜索同名文件或猜测其他根目录。"""
    if value is None or value == "":
        return None
    path = Path(str(value)).expanduser()
    return path.resolve() if path.is_absolute() else (base / path).resolve()


def resolve_config_paths(config: dict[str, Any], config_path: str | Path) -> ConfigPaths:
    """按 config目录 -> workspace -> requirement_dir 的固定层级解析配置。"""
    resolved_config = Path(config_path).expanduser().resolve()
    config_dir = resolved_config.parent
    workspace = _resolve(config.get("workspace_root"), config_dir) or config_dir
    requirement_dir = _resolve(config.get("requirement_dir"), workspace) or workspace
    return ConfigPaths(
        config_path=resolved_config,
        workspace_root=workspace,
        project_path=_resolve(config.get("project_path"), workspace),
        requirement_dir=requirement_dir,
        requirement_path=_resolve(config.get("requirement_file"), requirement_dir),
    )


def _state_path_for_config(config_path: str | Path, suffix: str | None = None) -> Path:
    """按配置路径生成外部状态文件名，使同名配置和不同项目互不覆盖。"""
    path = Path(config_path).expanduser().resolve()
    state_root = Path(
        os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local" / "state"))
    ).expanduser()
    # 同名 local.yaml 可能属于不同项目，用绝对路径摘要避免需求基线互相覆盖。
    digest = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:16]
    filename = f"{path.stem}-{digest}-{suffix}.json" if suffix else f"{path.stem}-{digest}.json"
    return (state_root / "android-delivery-skills" / filename).resolve()


def baseline_path_for_config(config_path: str | Path) -> Path:
    """返回当前配置的 Git 基线路径，文件始终位于目标仓库之外。"""
    # 保留既有文件名，升级脚本后仍能继续读取正在执行的需求基线。
    return _state_path_for_config(config_path)


def requirement_snapshot_path_for_config(config_path: str | Path) -> Path:
    """返回外部需求修订路径，供连续确认、义务校验和中途差异分析共用。"""
    return _state_path_for_config(config_path, "requirement")


def route_impact_path_for_config(config_path: str | Path) -> Path:
    """返回路由影响快照路径，使条件门禁绑定最近一次最终 diff 分析。"""
    return _state_path_for_config(config_path, "route-impact")


def evidence_directory_for_config(config_path: str | Path) -> Path:
    """返回执行收据目录；日志和收据放在目标项目外，避免改变交付代码摘要。"""
    marker = _state_path_for_config(config_path, "evidence")
    return marker.with_suffix("")


def evidence_scope_directory(
    evidence_root: str | Path,
    requirement_id: str,
    requirement_revision: int,
    snapshot_sha256: str,
) -> Path:
    """按需求、修订和代码摘要隔离证据，防止串行需求覆盖上一轮收据。"""
    requirement_scope = hashlib.sha256(requirement_id.encode("utf-8")).hexdigest()[:12]
    scope = f"{requirement_scope}-r{requirement_revision}-{snapshot_sha256[:12]}"
    return Path(evidence_root).expanduser().resolve() / scope


def evidence_scope_directory_for_config(
    config_path: str | Path,
    requirement_id: str,
    requirement_revision: int,
    snapshot_sha256: str,
) -> Path:
    """根据配置入口返回当前需求的隔离证据目录。"""
    return evidence_scope_directory(
        evidence_directory_for_config(config_path),
        requirement_id,
        requirement_revision,
        snapshot_sha256,
    )


def specialist_directory_for_config(
    config_path: str | Path,
    requirement_id: str,
    requirement_revision: int,
    snapshot_sha256: str,
) -> Path:
    """返回当前需求和代码的统一专项结果目录，避免跨需求覆盖或串用。"""
    return evidence_scope_directory_for_config(
        config_path,
        requirement_id,
        requirement_revision,
        snapshot_sha256,
    ) / "specialists"


def capabilities_path_for_config(config_path: str | Path) -> Path:
    """返回 Android 项目能力发现结果路径，供不同模型复用同一工程事实。"""
    return _state_path_for_config(config_path, "capabilities")
