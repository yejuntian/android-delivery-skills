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
import re
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
    def docs_dir(self) -> Path:
        """返回当前需求的人读 Markdown 根目录。"""
        return (self.requirement_dir / "docs").resolve()

    @property
    def resume_guide_path(self) -> Path:
        """返回续接指南路径，脚本渲染当前状态快照，是 AI 续做的第一入口。"""
        return (self.docs_dir / "续接指南.md").resolve()

    @property
    def communications_path(self) -> Path:
        """返回协作待办路径，只记录待确认或阻塞事项。"""
        return (self.docs_dir / "协作待办.md").resolve()

    @property
    def state_dir(self) -> Path:
        """机器状态根目录（基线/快照/route/证据/能力），跟 requirement_dir 走。"""
        return (self.requirement_dir / ".state").resolve()

    @property
    def tdd_cycle_path(self) -> Path:
        """返回当前需求唯一的 TDD Red/Green 周期记录路径。"""
        return self.state_dir / "tdd-cycle.json"

    @property
    def fact_inbox_path(self) -> Path:
        """返回聊天事实收件箱路径；讨论和待确认事实跟当前需求隔离。"""
        return self.state_dir / "fact-inbox.json"


def _resolve(value: Any, base: Path) -> Path | None:
    """只基于明确父目录解析路径，不搜索同名文件或猜测其他根目录。"""
    if value is None or value == "":
        return None
    path = Path(str(value)).expanduser()
    return path.resolve() if path.is_absolute() else (base / path).resolve()


def _md_filename_for_dir(requirement_dir: Path) -> str:
    """根据需求目录名生成稳定的 ``<需求名>.md`` 事实源文件名。"""
    name = requirement_dir.name
    req_match = re.match(r"^REQ-\d{8}-\d{3}-(?P<slug>.+)$", name)
    if req_match:
        slug = req_match.group("slug")
    else:
        date_match = re.match(r"^\d{4}-\d{2}-\d{2}-(?P<slug>.+)$", name)
        slug = date_match.group("slug") if date_match else name
    return f"{slug}.md"


def _today_stamp() -> str:
    """返回今天的 ``YYYY-MM-DD``。

    单独抽出便于测试注入；脚本运行时无法访问系统时钟时由调用方传入。
    """
    import datetime as _dt

    return _dt.date.today().isoformat()


def _derive_requirement_dir(
    project_path: Path | None,
    requirement_name: str | None,
    today_stamp: str | None = None,
) -> Path | None:
    """项目内通道缺省推导：project_path/document/<日期>-<需求名>。

    没有 project_path 或 requirement_name 时返回 None，由调用方决定报错还是降级。
    """
    if not project_path or not requirement_name:
        return None
    stamp = today_stamp or _today_stamp()
    slug = _sanitize_dir_segment(requirement_name)
    return (project_path / "document" / f"{stamp}-{slug}").resolve()


_DIR_SEGMENT_PATTERN = re.compile(r"[^\w.-]+", re.UNICODE)


def _sanitize_dir_segment(name: str) -> str:
    """把需求名收敛成安全的目录段：保留字母数字下划线点短横（含中文等 unicode 字），其余折叠为单短横。"""
    cleaned = _DIR_SEGMENT_PATTERN.sub("-", name.strip()).strip("-")
    return cleaned or "requirement"


def _derive_requirement_paths(
    config: dict[str, Any],
    config_path: str | Path,
) -> tuple[Path, Path | None, Path | None]:
    """统一推导 workspace_root / requirement_dir / project_path，缺省时自动补全。

    解析基准保持与原逻辑一致：workspace_root 相对配置目录，project_path /
    requirement_dir 相对 workspace。缺省推导只在字段未配置时生效：
    - workspace_root 缺失 → project_path（若已配置），否则配置目录。
    - requirement_dir 缺失 → project_path/document/<今天>-<requirement_name>，
      需要 project_path 与 requirement_name 才能推导；都没有时退回 workspace。
    """
    resolved_config = Path(config_path).expanduser().resolve()
    config_dir = resolved_config.parent

    # 1. workspace_root：填了相对配置目录；未填暂置空，待 project_path 解析后再补。
    workspace_value = config.get("workspace_root")
    workspace = _resolve(workspace_value, config_dir) if workspace_value else None

    # 2. project_path：相对 workspace（若有）或配置目录。
    project_path = _resolve(config.get("project_path"), workspace or config_dir)

    # 3. workspace_root 缺省推导：用 project_path；都没有则配置目录。
    if workspace is None:
        workspace = project_path or config_dir

    # 4. requirement_dir：填了相对 workspace；未填则按项目内通道推导。
    requirement_dir_value = config.get("requirement_dir")
    if requirement_dir_value:
        requirement_dir = _resolve(requirement_dir_value, workspace) or workspace
    else:
        requirement_name = config.get("requirement_name")
        derived = _derive_requirement_dir(project_path, requirement_name)
        requirement_dir = derived or workspace
    return workspace, requirement_dir, project_path


def resolve_config_paths(config: dict[str, Any], config_path: str | Path) -> ConfigPaths:
    """按 config目录 -> workspace -> requirement_dir 的固定层级解析配置。

    缺省推导：requirement_dir / workspace_root 未配置时自动按项目内通道推导
    （见 ``_derive_requirement_paths``），用户只需配置 project_path 与 requirement_name。

    事实源优先 md：如果 requirement_file 指向 docx，但 ``docs/<需求名>.md``
    已存在，自动切换到该 md（init 转写后的后续命令全部读 md，不再绑 docx）。
    """
    resolved_config = Path(config_path).expanduser().resolve()
    workspace, requirement_dir, project_path = _derive_requirement_paths(config, resolved_config)
    requirement_file_value = config.get("requirement_file")
    resolved_file_value = requirement_file_value
    # 事实源优先 md：docx 已转写 md 后，所有命令统一读 md。
    if isinstance(resolved_file_value, str) and resolved_file_value.lower().endswith(".docx"):
        md_name = _md_filename_for_dir(requirement_dir)
        md_candidate = requirement_dir / "docs" / md_name
        if md_candidate.is_file():
            resolved_file_value = (Path("docs") / md_name).as_posix()
    requirement_path = _resolve(resolved_file_value, requirement_dir)
    # 缺省推导 requirement_file：未配置且 requirement_dir 已推导（≠workspace）时，
    # 默认约定名 requirement.docx（new-requirement 挪入名）。显式配置或 md 切换优先。
    if (
        requirement_path is None
        and requirement_file_value is None
        and requirement_dir != workspace
    ):
        requirement_path = (requirement_dir / "requirement.docx").resolve()
    return ConfigPaths(
        config_path=resolved_config,
        workspace_root=workspace,
        project_path=project_path,
        requirement_dir=requirement_dir,
        requirement_path=requirement_path,
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


def tdd_cycle_path_for_config(config_path: str | Path) -> Path:
    """返回当前需求的 TDD 周期记录路径。"""
    return _state_dir_for(config_path) / "tdd-cycle.json"


def fact_inbox_path_for_config(config_path: str | Path) -> Path:
    """返回当前需求聊天事实收件箱路径。"""
    return _state_dir_for(config_path) / "fact-inbox.json"


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
    """返回显式 Android 项目能力诊断结果路径，不作为普通单测门禁依据。"""
    return _state_dir_for(config_path) / "capabilities.json"


def delivery_snapshot_exclusions(project_path: str | Path, requirement_dir: str | Path) -> set[str]:
    """返回 route/final 共同排除的交付文档路径，避免代码摘要规则漂移。"""
    project_resolved = Path(project_path).expanduser().resolve()
    requirement_resolved = Path(requirement_dir).expanduser().resolve()
    excluded: set[str] = set()
    for generated_path in (
        requirement_resolved / "test-results" / "delivery-result.json",
        requirement_resolved / "docs" / "交付结论.md",
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
