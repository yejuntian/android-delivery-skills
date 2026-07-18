#!/usr/bin/env python3
"""脚本名称：config_paths.py

用途：统一解析 Android Delivery 配置中的工作区、项目和需求路径。

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
