#!/usr/bin/env python3
"""脚本名称：config_paths.py

用途：统一解析 Android Delivery 配置路径及机器状态、证据位置。

核心设计：机器状态（基线/快照/route/证据/能力）放在 ``<requirement_dir>/.state/``，
跟着需求目录走（文档和状态自包含）。requirement_dir 由 profile 显式提供绝对路径，
不依赖运行时 cwd，因此不再有按 config 路径 hash 命名导致的漂移或跨项目残留。

职责边界：只根据配置文件内容解析路径，不读取需求正文、不检查 Git，也不决定 Skill 路由。
"""

from __future__ import annotations

import hashlib
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

    @property
    def test_mapping_path(self) -> Path:
        """返回当前需求测试映射路径，与追溯表同目录，便于人和机器同步查阅。"""
        return (self.requirement_dir / "test-cases" / "test-mapping.json").resolve()

    @property
    def impact_radius_path(self) -> Path:
        """返回当前需求影响半径路径，供计划确认和最终 diff 越界门禁共用。"""
        return (self.requirement_dir / "test-cases" / "impact-radius.json").resolve()

    @property
    def plan_dir(self) -> Path:
        """返回计划补充/影响预览目录，AI 手写产物，轮换时自动创建。"""
        return (self.requirement_dir / "plan").resolve()

    @property
    def review_dir(self) -> Path:
        """返回变更审查目录，AI 手写 Diff+Context 双表。"""
        return (self.requirement_dir / "review").resolve()

    @property
    def decisions_dir(self) -> Path:
        """返回决策留痕目录，重大取舍按 MADR 轻量版记录，推翻用 superseded。"""
        return (self.requirement_dir / "decisions").resolve()

    @property
    def resume_guide_path(self) -> Path:
        """返回续接指南路径，脚本渲染当前状态快照，是 AI 续做的第一入口。"""
        return (self.requirement_dir / "续接指南.md").resolve()

    @property
    def communications_path(self) -> Path:
        """返回协作待办路径，AI 手写 blocker/待确认/已发送/低风险直回。"""
        return (self.requirement_dir / "协作待办.md").resolve()

    @property
    def state_dir(self) -> Path:
        """机器状态根目录（基线/快照/route/证据/能力），跟 requirement_dir 走。"""
        return (self.requirement_dir / ".state").resolve()


def _resolve(value: Any, base: Path) -> Path | None:
    """只基于明确父目录解析路径，不搜索同名文件或猜测其他根目录。"""
    if value is None or value == "":
        return None
    path = Path(str(value)).expanduser()
    return path.resolve() if path.is_absolute() else (base / path).resolve()


def _md_filename_for_dir(requirement_dir: Path) -> str:
    """从 requirement_dir 目录名提取需求名，生成 <需求名>.md（如 ig-video-feed.md）。

    目录名格式为 <日期>-<英文名>（如 2026-07-25-ig-video-feed），
    取第一个 - 之后的部分作为需求名；无日期前缀时用整个目录名。
    """
    name = requirement_dir.name
    parts = name.split("-", 3)
    # 格式 YYYY-MM-DD-<slug>：取第 4 段；否则用整个目录名。
    slug = parts[3] if len(parts) >= 4 and len(parts[0]) == 4 and parts[0].isdigit() else name
    return f"{slug}.md"


def resolve_config_paths(config: dict[str, Any], config_path: str | Path) -> ConfigPaths:
    """按 config目录 -> workspace -> requirement_dir 的固定层级解析配置。

    事实源优先 md：如果 requirement_file 指向 docx，但同目录已有转写的 <需求名>.md，
    自动切换到该 md（init 转写后的后续命令全部读 md，不再绑 docx）。
    """
    resolved_config = Path(config_path).expanduser().resolve()
    config_dir = resolved_config.parent
    workspace = _resolve(config.get("workspace_root"), config_dir) or config_dir
    requirement_dir = _resolve(config.get("requirement_dir"), workspace) or workspace
    requirement_file_value = config.get("requirement_file")
    # 事实源优先 md：docx 已转写 md 后，所有命令统一读 md。
    if isinstance(requirement_file_value, str) and requirement_file_value.lower().endswith(".docx"):
        md_name = _md_filename_for_dir(requirement_dir)
        md_candidate = requirement_dir / md_name
        if md_candidate.is_file():
            config = {**config, "requirement_file": md_name}
    return ConfigPaths(
        config_path=resolved_config,
        workspace_root=workspace,
        project_path=_resolve(config.get("project_path"), workspace),
        requirement_dir=requirement_dir,
        requirement_path=_resolve(config.get("requirement_file"), requirement_dir),
    )


def _requirement_dir_from_config(config_path: str | Path) -> Path:
    """从 config 解析出 requirement_dir，供仍以 config_path 为参数的旧调用方使用。

    单一职责：只 resolve 路径，不读取正文。config 必须能被 load（含 requirement_dir）。
    """
    import yaml  # 延迟导入，避免纯路径模块强依赖 PyYAML

    source = Path(config_path).expanduser().resolve()
    try:
        config = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ValueError(f"配置无法读取，无法定位 requirement_dir: {source}: {exc}") from exc
    paths = resolve_config_paths(config if isinstance(config, dict) else {}, source)
    return paths.requirement_dir


def _state_dir_for(config_path: str | Path) -> Path:
    """返回机器状态根目录 = requirement_dir/.state，自动创建。

    状态跟 requirement_dir 走（文档和状态自包含），不再放全局 ~/.local/state，也不按
    config 路径 hash 命名。requirement_dir 是绝对路径，不依赖运行时 cwd。
    """
    state_dir = _requirement_dir_from_config(config_path) / ".state"
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir.resolve()


def baseline_path_for_config(config_path: str | Path) -> Path:
    """返回当前配置的 Git 基线路径，位于 requirement_dir/.state/baseline.json。"""
    return _state_dir_for(config_path) / "baseline.json"


def requirement_snapshot_path_for_config(config_path: str | Path) -> Path:
    """返回需求修订路径，供连续确认、义务校验和中途差异分析共用。"""
    return _state_dir_for(config_path) / "requirement-snapshot.json"


def route_impact_path_for_config(config_path: str | Path) -> Path:
    """返回路由影响快照路径，使条件门禁绑定最近一次最终 diff 分析。"""
    return _state_dir_for(config_path) / "route-impact.json"


def evidence_directory_for_config(config_path: str | Path) -> Path:
    """返回执行收据目录；收据放在 requirement_dir/.state/evidence，跟需求走。"""
    directory = _state_dir_for(config_path) / "evidence"
    directory.mkdir(parents=True, exist_ok=True)
    return directory.resolve()


def evidence_scope_directory(
    evidence_root: str | Path,
    requirement_id: str,
    requirement_revision: int,
    snapshot_sha256: str,
    requirement_inputs_sha256: str,
) -> Path:
    """按需求、输入与代码摘要隔离证据，防止资料变化覆盖上一轮收据。"""
    requirement_scope = hashlib.sha256(requirement_id.encode("utf-8")).hexdigest()[:12]
    scope = (
        f"{requirement_scope}-r{requirement_revision}-"
        f"i{requirement_inputs_sha256[:12]}-{snapshot_sha256[:12]}"
    )
    return Path(evidence_root).expanduser().resolve() / scope


def evidence_scope_directory_for_config(
    config_path: str | Path,
    requirement_id: str,
    requirement_revision: int,
    snapshot_sha256: str,
    requirement_inputs_sha256: str,
) -> Path:
    """根据配置入口返回当前需求的隔离证据目录。"""
    return evidence_scope_directory(
        evidence_directory_for_config(config_path),
        requirement_id,
        requirement_revision,
        snapshot_sha256,
        requirement_inputs_sha256,
    )


def specialist_directory_for_config(
    config_path: str | Path,
    requirement_id: str,
    requirement_revision: int,
    snapshot_sha256: str,
    requirement_inputs_sha256: str,
) -> Path:
    """返回当前需求和代码的统一专项结果目录，避免跨需求覆盖或串用。"""
    return evidence_scope_directory_for_config(
        config_path,
        requirement_id,
        requirement_revision,
        snapshot_sha256,
        requirement_inputs_sha256,
    ) / "specialists"


def capabilities_path_for_config(config_path: str | Path) -> Path:
    """返回 Android 项目能力发现结果路径，供不同模型复用同一工程事实。"""
    return _state_dir_for(config_path) / "capabilities.json"


def delivery_snapshot_exclusions(project_path: str | Path, requirement_dir: str | Path) -> set[str]:
    """返回 route/final 共同排除的交付文档路径，避免代码摘要规则漂移。"""
    project_resolved = Path(project_path).expanduser().resolve()
    requirement_resolved = Path(requirement_dir).expanduser().resolve()
    excluded: set[str] = set()
    for generated_path in (
        requirement_resolved / "test-results" / "delivery-result.json",
        requirement_resolved / "test-results" / "delivery-summary.md",
    ):
        try:
            excluded.add(generated_path.resolve().relative_to(project_resolved).as_posix())
        except ValueError:
            pass
    document_dir = project_resolved / "document"
    try:
        excluded.add(document_dir.relative_to(project_resolved).as_posix())
    except ValueError:
        pass
    return excluded
