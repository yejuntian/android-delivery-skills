#!/usr/bin/env python3
"""脚本名称：requirement_workspace.py

用途：为串行 Android 需求创建独立工作区，并按保留数量和时间延迟回收旧目录。

核心流程：读取 profiles 配置，校验目录和目标项目状态；默认只预览下一需求轮换或
过期回收；收到显式确认后创建新工作区、更新本机配置，并仅删除白名单内的过期目录。

职责边界：不理解业务需求、不修改 Android 源码、不执行测试、不操作 Git 提交，也不
删除当前活动或未完成需求。机器状态保存在工作区 JSON，用户说明写入中文 Markdown。
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from typing import Any


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = "scripts"

from .config_paths import _md_filename_for_dir, resolve_config_paths  # noqa: E402
from .channel_guard import ChannelGuardError, release_channel  # noqa: E402
from .delivery import DEFAULT_CONFIG_PATH, DeliveryError, load_config  # noqa: E402
from .git_changes import GitInspectionError, working_tree_status  # noqa: E402
from .user_facing_labels import ChineseArgumentParser  # noqa: E402


WORKSPACE_MODES = {"reuse", "rotate"}
OUTCOME_ALIASES = {
    "completed": "completed",
    "cancelled": "cancelled",
    "已完成": "completed",
    "已取消": "cancelled",
}
WORKSPACE_STATE_FILE = "requirement-workspace.json"
WORKSPACE_SUMMARY_FILE = Path("docs") / "需求说明.md"
# 只预创建流程始终需要的目录；接口、UI、配置和问题资料按需落盘。
REQUIRED_SUBDIRECTORIES = ("test-cases", "test-results", ".state")
OPTIONAL_SUBDIRECTORIES = ("api", "ui", "config", "issues")
ARCHIVE_ROOT_NAME = "archive"
WORKSPACE_INDEX_FILE = "需求总览.md"
INTEGRATION_REPORT_PREFIX = "integration-"
SUPPORTED_REQUIREMENT_SUFFIXES = {".docx", ".md", ".markdown", ".txt"}
STATE_VERSION = 1
WORKSPACE_LOCK_FILE = ".requirement-workspace.lock"


class RequirementWorkspaceError(RuntimeError):
    """表示工作区策略、路径或轮换条件不满足安全要求。"""


@dataclass(frozen=True)
class WorkspacePolicy:
    """保存解析后的工作区根目录和延迟回收参数。"""

    mode: str
    root: Path
    keep_completed: int
    retention_days: int
    tempfile_dir: Path


@dataclass(frozen=True)
class ReclaimPlan:
    """列出可回收内容，以及因状态异常而受保护的需求目录。"""

    workspaces: tuple[Path, ...]
    cache_entries: tuple[Path, ...]
    protected_workspaces: tuple[Path, ...]


@contextmanager
def workspace_mutation_lock(root: Path):
    """阻止两个窗口同时轮换或回收，并在正常结束或可捕获异常后释放。"""
    root.mkdir(parents=True, exist_ok=True)
    lock_path = root / WORKSPACE_LOCK_FILE
    descriptor: int | None = None
    lock_owned = False
    try:
        descriptor = os.open(
            lock_path,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o600,
        )
    except FileExistsError as exc:
        raise RequirementWorkspaceError(
            "另一个窗口正在执行需求轮换或回收；请等待其结束后重新预览。"
            f"如果上次进程异常退出，请确认没有操作仍在运行后删除锁文件: {lock_path}"
        ) from exc

    lock_owned = True
    try:
        os.write(
            descriptor,
            f"pid={os.getpid()} created_at={datetime.now(timezone.utc).isoformat()}\n".encode(
                "utf-8"
            ),
        )
        os.close(descriptor)
        descriptor = None
        yield
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if lock_owned:
            try:
                lock_path.unlink(missing_ok=True)
            except OSError:
                pass


def _is_relative_to(path: Path, parent: Path) -> bool:
    """兼容不同 Python 版本判断 path 是否严格位于 parent 内。"""
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _require_child(path: Path, parent: Path, label: str) -> None:
    """拒绝把工作区或缓存根目录指向工作区外部或公共根目录本身。"""
    if path == parent or not _is_relative_to(path, parent):
        raise RequirementWorkspaceError(
            f"{label} 必须位于本机工作区内部且不能等于工作区根目录: {path}"
        )


def _paths_overlap(first: Path, second: Path) -> bool:
    """判断两个路径是否相同或存在父子包含关系。"""
    return (
        first == second
        or _is_relative_to(first, second)
        or _is_relative_to(second, first)
    )


def load_workspace_policy(
    config: dict[str, Any], config_path: str | Path
) -> tuple[WorkspacePolicy, Any]:
    """解析 profiles 中的工作区策略，并验证所有可删除目录均在允许根目录内。"""
    paths = resolve_config_paths(config, config_path)
    raw = config.get("requirement_workspace", {}) or {}
    if not isinstance(raw, dict):
        raise RequirementWorkspaceError("requirement_workspace 必须是 YAML 对象")

    mode = str(raw.get("mode", "rotate"))
    if mode not in WORKSPACE_MODES:
        raise RequirementWorkspaceError(
            "requirement_workspace.mode 只能是 reuse 或 rotate"
        )
    root_value = raw.get("root", "ai-skills/requirements-runtime")
    root_candidate = Path(str(root_value)).expanduser()
    root = (
        root_candidate.resolve()
        if root_candidate.is_absolute()
        else (paths.workspace_root / root_candidate).resolve()
    )
    _require_child(root, paths.workspace_root, "需求工作区根目录")

    try:
        keep_completed = int(raw.get("keep_completed", 3))
        retention_days = int(raw.get("cache_retention_days", 7))
    except (TypeError, ValueError) as exc:
        raise RequirementWorkspaceError("工作区保留数量和天数必须是整数") from exc
    if keep_completed < 1:
        raise RequirementWorkspaceError("keep_completed 必须大于等于 1")
    if retention_days < 1:
        raise RequirementWorkspaceError("cache_retention_days 必须大于等于 1")

    tempfile_dir = (paths.workspace_root / "tempfile").resolve()
    _require_child(tempfile_dir, paths.workspace_root, "临时缓存目录")
    if paths.requirement_dir == paths.workspace_root:
        raise RequirementWorkspaceError("当前需求目录不能等于本机工作区根目录")
    if not _is_relative_to(paths.requirement_dir, paths.workspace_root):
        raise RequirementWorkspaceError("当前需求目录必须位于本机工作区内部")
    if paths.project_path:
        project_path = paths.project_path.resolve()
        for candidate, label in (
            (root, "需求工作区根目录"),
            (paths.requirement_dir, "当前需求目录"),
            (tempfile_dir, "临时缓存目录"),
        ):
            if _paths_overlap(candidate, project_path):
                raise RequirementWorkspaceError(
                    f"{label}不能与 Android 项目路径重叠: {candidate}"
                )

    return WorkspacePolicy(
        mode=mode,
        root=root,
        keep_completed=keep_completed,
        retention_days=retention_days,
        tempfile_dir=tempfile_dir,
    ), paths


def _read_json(path: Path) -> dict[str, Any] | None:
    """读取机器状态；缺失时返回 None，损坏时停止而不是猜测状态。"""
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RequirementWorkspaceError(f"需求工作区状态无法读取: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RequirementWorkspaceError(f"需求工作区状态必须是 JSON 对象: {path}")
    return value


def _write_text_atomic(path: Path, content: str) -> None:
    """代理到公共原子写；统一行为。本工作区文件不需要 0600 权限。"""
    from .atomic_write import write_text_atomic
    try:
        write_text_atomic(path, content)
    except OSError as exc:
        raise RequirementWorkspaceError(f"文件无法写入: {path}: {exc}") from exc


def _write_state(directory: Path, payload: dict[str, Any]) -> None:
    """写入机器工作区状态，供轮换和延迟回收可靠识别。"""
    _write_text_atomic(
        directory / WORKSPACE_STATE_FILE,
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
    )


def _snapshot_workspace_metadata(directory: Path) -> dict[str, str | None]:
    """在轮换前保存状态和中文说明，失败时恢复原始内容。"""
    snapshot: dict[str, str | None] = {}
    for name in (WORKSPACE_STATE_FILE, WORKSPACE_SUMMARY_FILE):
        path = directory / name
        if path.exists() and not path.is_file():
            raise RequirementWorkspaceError(f"需求工作区元数据不是普通文件: {path}")
        try:
            snapshot[name] = path.read_text(encoding="utf-8") if path.is_file() else None
        except (OSError, UnicodeError) as exc:
            raise RequirementWorkspaceError(f"需求工作区元数据无法读取: {path}: {exc}") from exc
    return snapshot


def _restore_workspace_metadata(
    directory: Path, snapshot: dict[str, str | None]
) -> None:
    """精确恢复轮换前的状态文件，不保留失败操作写入的完成标记。"""
    for name, content in snapshot.items():
        path = directory / name
        if content is None:
            path.unlink(missing_ok=True)
        else:
            _write_text_atomic(path, content)


def _status_label(status: str) -> str:
    """把工作区机器状态转换为用户可读中文。"""
    return {
        "ACTIVE": "正在处理",
        "COMPLETED": "已经完成",
        "CANCELLED": "已经取消",
    }.get(status, "状态暂时无法识别")


def _write_summary(directory: Path, state: dict[str, Any]) -> None:
    """生成用户可读的中文需求说明，不要求用户理解机器状态。"""
    title = str(state.get("title") or "未命名需求")
    status = _status_label(str(state.get("status") or ""))
    lines = [
        f"# {title}",
        "",
        f"- 需求编号：{state.get('requirement_id', '未生成')}",
        f"- 当前状态：{status}",
        f"- 开始时间：{state.get('created_at', '未记录')}",
        f"- 完成时间：{state.get('completed_at') or '尚未完成'}",
        f"- Android 项目：{state.get('project_path') or '未配置'}",
        f"- 目标分支：{state.get('branch') or '未限制'}",
        f"- 需求文档：{state.get('requirement_file') or '未配置'}",
        f"- 工作目录：{directory}",
        f"- 是否允许回收：{'否' if state.get('status') == 'ACTIVE' else '满足保留策略后允许'}",
        "",
        "> 本文件供用户阅读；同目录 JSON 保存稳定机器状态。",
        "",
    ]
    _write_text_atomic(directory / WORKSPACE_SUMMARY_FILE, "\n".join(lines))


def _sanitize_title(title: str) -> str:
    """保留中文可读性，同时移除路径分隔符、控制字符和连续空白。"""
    value = re.sub(r"[\\/:*?\"<>|\x00-\x1f]", "-", title.strip())
    value = re.sub(r"\s+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-._ ")
    if not value:
        raise RequirementWorkspaceError("需求名称不能为空或只包含非法路径字符")
    return value[:48].rstrip("-._ ")


def _next_requirement_id(root: Path, now: datetime, reserved: int = 0) -> str:
    """按本地日期和当日序号生成稳定需求编号。"""
    date_text = now.astimezone().strftime("%Y%m%d")
    pattern = re.compile(rf"^REQ-{date_text}-([0-9]{{3}})(?:-|$)")
    sequences = []
    if root.is_dir():
        for item in root.iterdir():
            match = pattern.match(item.name)
            if match:
                sequences.append(int(match.group(1)))
    sequence = max(sequences, default=0) + 1 + reserved
    if sequence > 999:
        raise RequirementWorkspaceError("当天需求工作区数量超过 999，无法生成稳定编号")
    return f"REQ-{date_text}-{sequence:03d}"


def _directory_has_content(path: Path) -> bool:
    """判断旧工作区是否包含需要保留的输入或产物。"""
    return path.is_dir() and any(path.iterdir())


def _validate_requirement_source(source: str | Path, active_dir: Path) -> Path:
    """要求新需求文件位于旧活动目录之外，避免轮换时误移动或覆盖。"""
    path = Path(source).expanduser().resolve()
    active_dir = active_dir.expanduser().resolve()
    if not path.is_file():
        raise RequirementWorkspaceError(f"新需求文件不存在: {path}")
    if path.suffix.lower() not in SUPPORTED_REQUIREMENT_SUFFIXES:
        raise RequirementWorkspaceError(
            "新需求文件仅支持 .docx、.md、.markdown 或 .txt"
        )
    if path == active_dir or _is_relative_to(path, active_dir):
        raise RequirementWorkspaceError(
            "新需求文件必须先放在当前需求目录之外，避免轮换时被当成旧资料"
        )
    return path


def _tree_latest_mtime(path: Path) -> float:
    """返回目录树最新修改时间，近期仍有写入时不回收缓存。"""
    latest = path.lstat().st_mtime
    if path.is_dir() and not path.is_symlink():
        for child in path.rglob("*"):
            try:
                latest = max(latest, child.lstat().st_mtime)
            except OSError:
                continue
    return latest


def _completed_timestamp(state: dict[str, Any], directory: Path) -> float:
    """优先使用完成时间排序，旧状态缺失时安全退回目录修改时间。"""
    completed_at = state.get("completed_at")
    if isinstance(completed_at, str) and completed_at:
        try:
            return datetime.fromisoformat(completed_at).timestamp()
        except ValueError:
            pass
    return directory.stat().st_mtime


def build_reclaim_plan(
    policy: WorkspacePolicy,
    active_dir: Path,
    now: datetime | None = None,
) -> ReclaimPlan:
    """只选择已完成且同时超过保留数量和保留天数的工作区。"""
    current_time = (now or datetime.now(timezone.utc)).timestamp()
    cutoff_seconds = policy.retention_days * 24 * 60 * 60
    completed: list[tuple[Path, float]] = []
    protected_workspaces: list[Path] = []
    if policy.root.is_dir():
        for directory in policy.root.iterdir():
            if not directory.is_dir() or directory.is_symlink():
                continue
            if directory.resolve() == active_dir.resolve():
                continue
            try:
                state = _read_json(directory / WORKSPACE_STATE_FILE)
            except RequirementWorkspaceError:
                protected_workspaces.append(directory)
                continue
            if not state:
                protected_workspaces.append(directory)
                continue
            if state.get("status") not in {"COMPLETED", "CANCELLED"}:
                continue
            completed.append((directory, _completed_timestamp(state, directory)))
    completed.sort(key=lambda item: item[1], reverse=True)
    workspaces = tuple(
        directory
        for index, (directory, timestamp) in enumerate(completed)
        if index >= policy.keep_completed and current_time - timestamp >= cutoff_seconds
    )

    cache_entries: list[Path] = []
    if policy.tempfile_dir.is_dir():
        for entry in policy.tempfile_dir.iterdir():
            try:
                old_enough = current_time - _tree_latest_mtime(entry) >= cutoff_seconds
            except OSError:
                old_enough = False
            if old_enough:
                cache_entries.append(entry)
    return ReclaimPlan(
        workspaces=tuple(sorted(workspaces)),
        cache_entries=tuple(sorted(cache_entries)),
        protected_workspaces=tuple(sorted(protected_workspaces)),
    )


def _remove_reclaim_target(path: Path, allowed_root: Path) -> None:
    """删除前再次验证目标是允许根目录的直接子项，拒绝路径穿越。"""
    resolved = path.resolve()
    if resolved.parent != allowed_root.resolve() or resolved == allowed_root.resolve():
        raise RequirementWorkspaceError(f"拒绝回收非白名单路径: {resolved}")
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.is_dir():
        shutil.rmtree(path)


def archive_before_reclaim(directory: Path, workspace_root: Path) -> Path | None:
    """回收前完整归档 docs/，机器 JSON 和原始证据随源目录清理。"""
    archive_root = (workspace_root / ARCHIVE_ROOT_NAME).resolve()
    requirement_id = directory.name
    try:
        dest = (archive_root / requirement_id).resolve()
        if dest.exists():
            shutil.rmtree(dest)
        dest.mkdir(parents=True, exist_ok=True)
        source_dir = directory / "docs"
        if source_dir.is_dir():
            shutil.copytree(source_dir, dest / "docs")
        return dest
    except OSError:
        return None


def build_workspace_index(workspace_root: Path) -> list[dict[str, str]]:
    """扫描所有需求目录，汇总一行一需求的索引数据，供需求总览.md 渲染。

    支持两种布局：rotate 的 requirements-runtime（每需求一个目录）和并行方案的
    project_path/document/<日期-英文名>（每 worktree 的 document 下各需求目录）。
    后者由 integrate 写入 integration_batch，index 据此显示分支和集成批次。
    """
    entries: list[dict[str, str]] = []
    if not workspace_root.is_dir():
        return entries
    for directory in sorted(workspace_root.iterdir()):
        if not directory.is_dir() or directory.is_symlink():
            continue
        if directory.name in {ARCHIVE_ROOT_NAME}:
            continue
        state = _read_json(directory / WORKSPACE_STATE_FILE)
        if not state:
            continue
        raw_status = state.get("status", "")
        status_label = {
            "ACTIVE": "进行中",
            "COMPLETED": "已完成",
            "CANCELLED": "已取消",
            "MERGED": "已合并",
        }.get(raw_status, raw_status or "未知")
        title = state.get("title") or directory.name
        revision = state.get("revision") or state.get("completed_at") or ""
        entries.append({
            "id": state.get("requirement_id", directory.name),
            "title": title,
            "status": status_label,
            "branch": state.get("branch") or "—",
            "batch": state.get("integration_batch") or "—",
            "revision": str(revision)[:10] if revision else "—",
            "dir": directory.name,
        })
    return entries


def render_workspace_index(workspace_root: Path) -> str:
    """把所有需求汇总成需求总览.md（六列含分支和集成批次），用户一眼看到全局。

    并行方案的总览放主工作树 document/，但各需求目录分散在各 worktree 的
    document/<需求> 下。本函数只渲染传入的 workspace_root 下的需求目录；
    并行场景由调用方把各通道目录软聚合（如扫描主工作树 document/ 的兄弟需求目录）。
    归档提示统一展示，避免在总览正文里硬编码 archive 路径断言。
    """
    entries = build_workspace_index(workspace_root)
    lines = ["# 需求总览", "", ">", "本文件扫描各需求目录自动生成；机器事实以各目录的 JSON 为准。", ""]
    if not entries:
        lines.append("暂无需求目录。")
        return "\n".join(lines)
    lines.extend([
        "| 目录（日期-英文名） | 中文标题 | 分支 | 状态 | 集成批次 | 最后修订 |",
        "|---|---|---|---|---|---|",
    ])
    for item in entries:
        lines.append(
            f"| `{item['dir']}` | {item['title']} | `{item['branch']}` | "
            f"{item['status']} | {item['batch']} | {item['revision']} |"
        )
    lines.extend([
        "",
        "- 续做某个需求时，先读对应目录的 `docs/续接指南.md`。",
        "- 代码在对应分支的 worktree 里（`MyApp-<英文名>/`）。",
        "- 集成批次详情见同目录 `integration-<日期>-<批次>.md`。",
        "- 已完成需求超保留数量与天数时回收前归档到 `archive/`；并行合并的需求原地保留。",
        "- 不冲突的并行需求各窗口独立闭环；私有分支集成前 rebase，主分支只用 git merge --ff-only。",
        "",
    ])
    return "\n".join(lines)


def execute_reclaim_plan(policy: WorkspacePolicy, plan: ReclaimPlan) -> None:
    """执行已经通过保留策略筛选的回收计划；回收前先归档完整 docs/。"""
    for directory in plan.workspaces:
        archive_before_reclaim(directory, policy.root)
        _remove_reclaim_target(directory, policy.root)
    for entry in plan.cache_entries:
        _remove_reclaim_target(entry, policy.tempfile_dir)


def _read_channel_state(channel_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """读单个并行通道的 workspace state 和最终结果；缺失时返回空 dict。

    单一职责：只读两个事实源，不校验、不渲染。供 integrate 汇总。
    """
    state = _read_json(channel_dir / WORKSPACE_STATE_FILE) or {}
    result_path = channel_dir / "test-results" / "delivery-result.json"
    result: dict[str, Any] = {}
    if result_path.is_file():
        try:
            loaded = json.loads(result_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                result = loaded
        except (OSError, UnicodeError, json.JSONDecodeError):
            result = {}
    return state, result


def render_integration_report(
    channels: list[tuple[Path, dict[str, Any], dict[str, Any]]],
    batch_label: str,
) -> str:
    """把本批次合并的各通道汇总成交付集成报告 md。

    单一职责：只读 state/result 派生 md，不校验、不重验证（验证靠 delivery_gate
    在最终代码重跑）。channels 为 (目录, state, result) 三元组列表。
    """
    lines = [
        f"# 交付集成报告 {batch_label}",
        "",
        "> 本报告汇总本批次合并的并行通道结论；各通道独立闭环的证据以各自目录为准。",
        "",
        "| 目录 | 中文标题 | 分支 | 最终结论 | 未验证项 | 残留风险 |",
        "|---|---|---|---|---|---|",
    ]
    for channel_dir, state, result in channels:
        conclusion = result.get("conclusion", "未生成")
        obligations = result.get("obligations", []) if isinstance(result, dict) else []
        unverified = [
            item.get("id", "?") for item in obligations
            if isinstance(item, dict) and item.get("status") == "UNVERIFIED"
        ]
        pending = result.get("pending_capabilities", []) if isinstance(result, dict) else []
        risk_parts: list[str] = []
        for cap in pending:
            if isinstance(cap, dict):
                risk_parts.append(str(cap.get("id", "?")))
        risk = "；".join(risk_parts) if risk_parts else "—"
        lines.append(
            f"| `{channel_dir.name}` | {state.get('title', channel_dir.name)} | "
            f"`{state.get('branch', '—')}` | {conclusion} | "
            f"{'，'.join(unverified) if unverified else '—'} | {risk} |"
        )
    lines.extend([
        "",
        "## 合入后注意",
        "",
        "- 各私有分支先 rebase 到最新主分支，再用 `git merge --ff-only` 保持主分支历史一条线。",
        "- 合入后的最终代码上重新执行 build/lint/test 和 delivery_gate。",
        "- 各通道文档目录原地保留，不物理合并；细查见各自 `续接指南.md`。",
        "",
    ])
    return "\n".join(lines)


def integrate_channels(
    main_worktree: Path,
    channel_dirs: list[Path],
    batch_label: str,
) -> Path:
    """汇总各通道结论生成交付集成报告，并把各通道标 MERGED + 批次号。

    单一职责：只汇总不验证。返回生成的集成报告路径。各通道 requirement_dir 的
    document 父目录不同（并行 worktree 各自隔离），报告写到主工作树 document/。
    """
    main_worktree = Path(main_worktree).expanduser().resolve()
    report_root = main_worktree / "document"
    report_root.mkdir(parents=True, exist_ok=True)
    triples: list[tuple[Path, dict[str, Any], dict[str, Any]]] = []
    release_targets: list[tuple[Path, Path]] = []
    for channel_dir in channel_dirs:
        channel_dir = Path(channel_dir).expanduser().resolve()
        state, result = _read_channel_state(channel_dir)
        triples.append((channel_dir, state, result))
        # 把状态标 MERGED + 批次号写回各通道 state（单一职责：只写本批次标记）。
        state_path = channel_dir / WORKSPACE_STATE_FILE
        existing = _read_json(state_path) or {}
        if isinstance(existing, dict):
            existing["status"] = "MERGED"
            existing["integration_batch"] = batch_label
            _write_state(channel_dir, existing)
            project_value = existing.get("project_path")
            if project_value:
                release_targets.append((Path(str(project_value)), channel_dir))
    report_path = report_root / f"{INTEGRATION_REPORT_PREFIX}{batch_label}.md"
    _write_text_atomic(report_path, render_integration_report(triples, batch_label))
    for project_path, channel_dir in release_targets:
        try:
            release_channel(project_path, channel_dir)
        except ChannelGuardError as exc:
            raise RequirementWorkspaceError(f"并行需求项目通道无法释放: {exc}") from exc
    return report_path


def _relative_config_path(path: Path, workspace_root: Path) -> str:
    """优先写入相对 workspace_root 的可迁移配置路径。"""
    try:
        return path.relative_to(workspace_root).as_posix()
    except ValueError:
        return str(path)


def _replace_top_level_yaml_scalar(content: str, key: str, value: str) -> str:
    """只替换指定顶层标量，保留 local.yaml 的详细注释和其他用户配置。"""
    pattern = re.compile(rf"^(?P<prefix>{re.escape(key)}\s*:\s*).*$", re.MULTILINE)
    matches = list(pattern.finditer(content))
    if len(matches) != 1:
        raise RequirementWorkspaceError(f"本机配置必须且只能包含一个顶层 {key}")
    rendered = json.dumps(value, ensure_ascii=False)
    return pattern.sub(lambda match: match.group("prefix") + rendered, content, count=1)


def update_active_config(
    config_path: Path,
    workspace_root: Path,
    requirement_dir: Path,
    requirement_file: str,
) -> None:
    """保持配置注释不变，只更新当前活动需求目录和正文文件名。"""
    try:
        content = config_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise RequirementWorkspaceError(f"本机配置无法读取: {config_path}: {exc}") from exc
    content = _replace_top_level_yaml_scalar(
        content,
        "requirement_dir",
        _relative_config_path(requirement_dir, workspace_root),
    )
    content = _replace_top_level_yaml_scalar(content, "requirement_file", requirement_file)
    _write_text_atomic(config_path, content)


def _mark_previous_workspace(
    directory: Path,
    requirement_id: str,
    title: str,
    outcome: str,
    project_path: Path | None,
    branch: Any,
    requirement_file: str,
    now: datetime,
) -> None:
    """为上一需求写入完成状态和中文说明，供后续延迟回收判断。"""
    existing = _read_json(directory / WORKSPACE_STATE_FILE) or {}
    state = {
        **existing,
        "schema_version": STATE_VERSION,
        "requirement_id": existing.get("requirement_id") or requirement_id,
        "title": existing.get("title") or title,
        "status": "COMPLETED" if outcome == "completed" else "CANCELLED",
        "created_at": existing.get("created_at") or now.isoformat(),
        "completed_at": now.isoformat(),
        "project_path": existing.get("project_path") or (
            str(project_path) if project_path else None
        ),
        "branch": existing.get("branch") or branch,
        "requirement_file": existing.get("requirement_file") or requirement_file,
    }
    _write_state(directory, state)
    _write_summary(directory, state)


def _prepare_new_workspace(
    directory: Path,
    requirement_id: str,
    title: str,
    source: Path,
    project_path: Path | None,
    branch: Any,
    now: datetime,
) -> str:
    """在新目录中复制需求正文、创建核心目录并写入双语义状态。"""
    if not directory.is_dir() or any(directory.iterdir()):
        raise RequirementWorkspaceError(f"新需求暂存目录必须存在且为空: {directory}")
    final_name = Path(f"{requirement_id}-{_sanitize_title(title)}")
    if source.suffix.lower() in {".md", ".markdown"}:
        requirement_name = Path("docs") / _md_filename_for_dir(final_name)
    else:
        requirement_name = Path("docs") / f"requirement{source.suffix.lower()}"
    (directory / "docs").mkdir()
    shutil.copy2(source, directory / requirement_name)
    for name in REQUIRED_SUBDIRECTORIES:
        (directory / name).mkdir()
    state = {
        "schema_version": STATE_VERSION,
        "requirement_id": requirement_id,
        "title": title,
        "status": "ACTIVE",
        "created_at": now.isoformat(),
        "completed_at": None,
        "project_path": str(project_path) if project_path else None,
        "branch": branch,
        "requirement_file": requirement_name.as_posix(),
    }
    _write_state(directory, state)
    _write_summary(directory, state)
    return requirement_name.as_posix()


def _ensure_project_clean(project_path: Path | None) -> None:
    """新串行需求必须从目标项目干净状态开始，不自动处理用户代码。"""
    if not project_path or not project_path.is_dir():
        raise RequirementWorkspaceError(f"Android 项目路径无效: {project_path}")
    try:
        status = working_tree_status(project_path)
    except GitInspectionError as exc:
        raise RequirementWorkspaceError(str(exc)) from exc
    if status:
        raise RequirementWorkspaceError(
            "Android 项目仍有未提交修改，不能轮换需求工作区。\n"
            f"{status}\n请先确认上一需求代码处置；脚本不会自动提交、暂存或清理。"
        )


def rotate_workspace(
    config_path: Path,
    config: dict[str, Any],
    policy: WorkspacePolicy,
    paths: Any,
    title: str,
    source: Path,
    previous_title: str,
    previous_outcome: str,
    now: datetime | None = None,
) -> tuple[Path, ReclaimPlan]:
    """归档上一活动目录、创建新目录并更新 profiles 中的活动指针。"""
    if policy.mode != "rotate":
        raise RequirementWorkspaceError(
            "requirement_workspace.mode 当前不是 rotate，拒绝自动轮换"
        )
    _ensure_project_clean(paths.project_path)
    latest_config = load_config(config_path)
    latest_paths = resolve_config_paths(latest_config, config_path)
    if (
        latest_paths.requirement_dir != paths.requirement_dir
        or latest_paths.requirement_path != paths.requirement_path
    ):
        raise RequirementWorkspaceError(
            "本机配置已被其他窗口更新，请重新执行预览后再确认轮换"
        )
    current_time = now or datetime.now(timezone.utc).astimezone()
    policy.root.mkdir(parents=True, exist_ok=True)
    safe_title = _sanitize_title(title)
    safe_previous_title = _sanitize_title(previous_title or "上一需求归档")
    current_dir = paths.requirement_dir.resolve()
    current_state: dict[str, Any] | None = None
    if _is_relative_to(current_dir, policy.root):
        current_state = _read_json(current_dir / WORKSPACE_STATE_FILE)
        if not current_state or not current_state.get("requirement_id"):
            raise RequirementWorkspaceError(
                "当前目录位于独立工作区根路径内，但缺少有效机器状态，拒绝猜测归属"
            )
    current_has_content = _directory_has_content(current_dir)
    metadata_before = (
        _snapshot_workspace_metadata(current_dir) if current_has_content else {}
    )
    legacy = current_has_content and not _is_relative_to(current_dir, policy.root)
    legacy_id = _next_requirement_id(policy.root, current_time) if legacy else None
    requirement_id = _next_requirement_id(
        policy.root, current_time, reserved=1 if legacy else 0
    )
    final_dir = policy.root / f"{requirement_id}-{safe_title}"
    if final_dir.exists():
        raise RequirementWorkspaceError(f"新需求目录已存在，拒绝覆盖: {final_dir}")

    archived_dir: Path | None = None
    requirement_name = ""
    config_before = config_path.read_text(encoding="utf-8")
    creating_dir: Path | None = None
    final_owned = False
    config_updated = False
    legacy_moved = False
    try:
        # 每次轮换使用唯一暂存目录，失败回滚时绝不删除其他窗口的产物。
        creating_dir = Path(
            tempfile.mkdtemp(
                prefix=f".{requirement_id}.creating-",
                dir=policy.root,
            )
        )
        requirement_name = _prepare_new_workspace(
            creating_dir,
            requirement_id,
            title.strip(),
            source,
            paths.project_path,
            config.get("branch"),
            current_time,
        )
        if legacy and legacy_id:
            archived_dir = policy.root / f"{legacy_id}-{safe_previous_title}"
            if archived_dir.exists():
                raise RequirementWorkspaceError(
                    f"上一需求归档目录已存在，拒绝覆盖: {archived_dir}"
                )
            current_dir.replace(archived_dir)
            legacy_moved = True
        elif current_has_content:
            archived_dir = current_dir

        creating_dir.replace(final_dir)
        creating_dir = None
        final_owned = True
        update_active_config(
            config_path,
            paths.workspace_root,
            final_dir,
            requirement_name,
        )
        config_updated = True
        if archived_dir:
            previous_state = _read_json(archived_dir / WORKSPACE_STATE_FILE) or {}
            previous_id = str(previous_state.get("requirement_id") or legacy_id)
            _mark_previous_workspace(
                archived_dir,
                previous_id,
                previous_title,
                previous_outcome,
                paths.project_path,
                config.get("branch"),
                str(Path(str(config.get("requirement_file", "requirement.docx"))).name),
                current_time,
            )
            if paths.project_path and (paths.project_path / ".git").exists():
                try:
                    release_channel(paths.project_path, paths.requirement_dir)
                except ChannelGuardError as exc:
                    raise RequirementWorkspaceError(f"上一需求项目通道无法释放: {exc}") from exc
    except Exception as exc:
        rollback_errors: list[str] = []
        # 只回滚本次调用实际修改的对象，避免并发失败误删其他窗口产物。
        if config_updated:
            try:
                _write_text_atomic(config_path, config_before)
            except (OSError, RequirementWorkspaceError) as rollback_exc:
                rollback_errors.append(f"本机配置恢复失败: {rollback_exc}")
        if final_owned and final_dir.exists():
            try:
                shutil.rmtree(final_dir)
            except OSError as rollback_exc:
                rollback_errors.append(f"新需求目录清理失败: {rollback_exc}")
        if creating_dir and creating_dir.exists():
            try:
                shutil.rmtree(creating_dir)
            except OSError as rollback_exc:
                rollback_errors.append(f"暂存目录清理失败: {rollback_exc}")
        if legacy_moved and archived_dir and archived_dir.exists():
            try:
                if current_dir.exists():
                    raise RequirementWorkspaceError(
                        f"原需求目录已经重新出现，拒绝覆盖: {current_dir}"
                    )
                archived_dir.replace(current_dir)
            except (OSError, RequirementWorkspaceError) as rollback_exc:
                rollback_errors.append(f"上一需求目录恢复失败: {rollback_exc}")
        if metadata_before and current_dir.is_dir():
            try:
                _restore_workspace_metadata(current_dir, metadata_before)
            except (OSError, RequirementWorkspaceError) as rollback_exc:
                rollback_errors.append(f"上一需求状态恢复失败: {rollback_exc}")
        if rollback_errors:
            details = "；".join(rollback_errors)
            raise RequirementWorkspaceError(
                f"需求工作区轮换失败，且自动恢复不完整: {details}"
            ) from exc
        raise

    plan = build_reclaim_plan(policy, final_dir, current_time)
    return final_dir, plan


def _print_reclaim_plan(plan: ReclaimPlan) -> None:
    """使用中文展示延迟回收候选，不直接倾倒机器状态。"""
    print("\n延迟回收候选:")
    if not plan.workspaces and not plan.cache_entries:
        print("- 当前没有满足保留数量和保留天数的内容。")
    for path in plan.workspaces:
        state = _read_json(path / WORKSPACE_STATE_FILE) or {}
        print(f"- 已完成需求：{state.get('title', path.name)}（{path}）")
    for path in plan.cache_entries:
        print(f"- 过期临时缓存：{path}")
    for path in plan.protected_workspaces:
        print(f"- 保留不删除：机器状态缺失或损坏（{path}）")


def _normalize_previous_outcome(value: str) -> str:
    """兼容中文和稳定英文参数，并统一成内部机器值。"""
    if value not in OUTCOME_ALIASES:
        raise ValueError("请填写“已完成”或“已取消”")
    return OUTCOME_ALIASES[value]


def print_status(config_path: Path, config: dict[str, Any]) -> int:
    """展示当前活动需求和保留策略。"""
    policy, paths = load_workspace_policy(config, config_path)
    state = _read_json(paths.requirement_dir / WORKSPACE_STATE_FILE)
    print("当前需求工作区:")
    print(f"- 管理模式：{'独立工作区轮换' if policy.mode == 'rotate' else '复用固定目录'}")
    print(f"- 当前目录：{paths.requirement_dir}")
    if state:
        print(f"- 需求名称：{state.get('title', '未记录')}")
        print(f"- 需求编号：{state.get('requirement_id', '未记录')}")
        print(f"- 当前状态：{_status_label(str(state.get('status') or ''))}")
    else:
        print("- 当前目录尚未由工作区脚本管理；首次轮换时会安全迁移。")
    print(f"- 保留最近完成需求：{policy.keep_completed} 个")
    print(f"- 最短保留时间：{policy.retention_days} 天")
    _print_reclaim_plan(build_reclaim_plan(policy, paths.requirement_dir))
    return 0


def print_next_preview(
    policy: WorkspacePolicy,
    paths: Any,
    title: str,
    source: Path,
    previous_title: str,
    previous_outcome: str,
) -> None:
    """展示轮换将发生的动作，默认不修改任何文件。"""
    print("下一需求工作区轮换预览:")
    print(f"- 上一需求：{previous_title}")
    print(f"- 上一需求结论：{'已经完成' if previous_outcome == 'completed' else '已经取消'}")
    print(f"- 当前目录：{paths.requirement_dir}")
    print(f"- 新需求名称：{title}")
    print(f"- 新需求文件：{source}")
    print(f"- 新目录根路径：{policy.root}")
    print("- 执行动作：保留上一需求，创建独立新目录并更新 local.yaml。")
    print("- 不会操作：Android 源码、Git 提交、当前配置中的其他字段。")
    plan = build_reclaim_plan(policy, paths.requirement_dir)
    _print_reclaim_plan(plan)
    if plan.workspaces or plan.cache_entries:
        print("- 确认轮换时，上述满足条件的候选也会执行延迟回收。")
    print("\n当前仅预览；确认开始新需求后使用同一命令追加 --confirm。")


def parse_args(argv: list[str] | None = None) -> Any:
    """定义状态查看、下一需求轮换和延迟回收三个独立命令。"""
    parser = ChineseArgumentParser(description="管理 Android 串行需求独立工作区")
    subparsers = parser.add_subparsers(dest="command", required=True)

    status = subparsers.add_parser("status", help="查看当前需求和回收候选")
    status.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="本机配置路径")

    next_parser = subparsers.add_parser("next", help="预览或创建下一需求独立工作区")
    next_parser.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="本机配置路径")
    next_parser.add_argument("--title", required=True, help="面向用户的中文需求名称")
    next_parser.add_argument(
        "--requirement-file", required=True, help="当前需求目录之外的新需求文件"
    )
    next_parser.add_argument(
        "--previous-title", default="上一需求归档", help="上一需求的中文名称"
    )
    next_parser.add_argument(
        "--previous-outcome",
        type=_normalize_previous_outcome,
        metavar="{已完成,已取消}",
        required=True,
        help="上一需求结论；推荐直接填写“已完成”或“已取消”",
    )
    next_parser.add_argument(
        "--confirm", action="store_true", help="确认执行预览中的工作区轮换"
    )

    prune = subparsers.add_parser("prune", help="预览或回收满足策略的旧目录")
    prune.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="本机配置路径")
    prune.add_argument(
        "--confirm", action="store_true", help="确认删除已经满足延迟回收条件的内容"
    )

    release = subparsers.add_parser("release", help="释放当前需求占用的 Git worktree 通道")
    release.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="本机配置路径")

    index_parser = subparsers.add_parser("index", help="渲染或刷新需求总览.md")
    index_parser.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="本机配置路径")
    index_parser.add_argument(
        "--main-worktree",
        default=None,
        help="主工作树路径；指定后总览写到 <主工作树>/document/需求总览.md",
    )

    integrate_parser = subparsers.add_parser(
        "integrate", help="汇总并行通道结论生成交付集成报告"
    )
    integrate_parser.add_argument(
        "--main-worktree", required=True, help="主工作树路径（集成报告写到其 document/）"
    )
    integrate_parser.add_argument(
        "--channels",
        required=True,
        help="逗号分隔的并行通道 requirement_dir 路径列表",
    )
    integrate_parser.add_argument(
        "--batch", required=True, help="集成批次标签，如 2026-07-25-批次1"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """执行用户选择的工作区管理命令，所有失败均输出可操作中文原因。"""
    args = parse_args(argv)
    config_path = Path(args.config).expanduser().resolve()
    try:
        config = load_config(config_path)
        policy, paths = load_workspace_policy(config, config_path)
        if args.command == "status":
            return print_status(config_path, config)
        if args.command == "release":
            if not paths.project_path:
                raise RequirementWorkspaceError("配置缺少 project_path，无法释放项目通道")
            try:
                released = release_channel(paths.project_path, paths.requirement_dir)
            except ChannelGuardError as exc:
                raise RequirementWorkspaceError(str(exc)) from exc
            print("✅ 项目通道已释放。" if released else "✅ 当前没有需要释放的项目通道。")
            return 0
        if args.command == "index":
            index_root = (
                Path(args.main_worktree).expanduser().resolve() / "document"
                if args.main_worktree
                else policy.root
            )
            index_root.mkdir(parents=True, exist_ok=True)
            content = render_workspace_index(policy.root if not args.main_worktree else index_root)
            index_path = index_root / WORKSPACE_INDEX_FILE
            _write_text_atomic(index_path, content)
            print(f"✅ 需求总览已刷新: {index_path}")
            return 0
        if args.command == "integrate":
            channel_dirs = [
                Path(item.strip()).expanduser().resolve()
                for item in args.channels.split(",")
                if item.strip()
            ]
            report_path = integrate_channels(
                Path(args.main_worktree).expanduser().resolve(),
                channel_dirs,
                args.batch,
            )
            print(f"✅ 交付集成报告已生成: {report_path}")
            print("各通道已标 MERGED 并记录批次号；合并后请在最终代码重跑 delivery_gate。")
            return 0
        if args.command == "prune":
            plan = build_reclaim_plan(policy, paths.requirement_dir)
            _print_reclaim_plan(plan)
            if not args.confirm:
                print("\n当前仅预览；确认回收后追加 --confirm。")
                return 0
            with workspace_mutation_lock(policy.root):
                # 获得单写锁后重新计算，避免删除锁等待期间已经变化的目录。
                plan = build_reclaim_plan(policy, paths.requirement_dir)
                execute_reclaim_plan(policy, plan)
            print("✅ 延迟回收完成；当前活动需求和保留范围未修改。")
            return 0

        if policy.mode != "rotate":
            raise RequirementWorkspaceError(
                "requirement_workspace.mode 当前不是 rotate，工作区轮换未启用"
            )
        source = _validate_requirement_source(args.requirement_file, paths.requirement_dir)
        previous_outcome = args.previous_outcome
        if not args.confirm:
            print_next_preview(
                policy,
                paths,
                args.title,
                source,
                args.previous_title,
                previous_outcome,
            )
            return 0
        with workspace_mutation_lock(policy.root):
            new_directory, plan = rotate_workspace(
                config_path,
                config,
                policy,
                paths,
                args.title,
                source,
                args.previous_title,
                previous_outcome,
            )
            try:
                execute_reclaim_plan(policy, plan)
            except (RequirementWorkspaceError, OSError) as exc:
                print(f"✅ 新需求工作区已创建: {new_directory}")
                print(f"中文需求说明: {new_directory / WORKSPACE_SUMMARY_FILE}")
                print(
                    f"⚠️ 工作区轮换已经成功，但延迟回收没有全部完成: {exc}",
                    file=sys.stderr,
                )
                print("请修正路径或权限后单独执行 requirement_workspace.py prune。")
                print(
                    "下一步：先执行 delivery.py init，确认需求理解后再执行 "
                    "check-env --new-requirement。"
                )
                return 1
        print(f"✅ 新需求工作区已创建: {new_directory}")
        print(f"中文需求说明: {new_directory / WORKSPACE_SUMMARY_FILE}")
        print("下一步：先执行 delivery.py init，确认需求理解后再执行 check-env --new-requirement。")
        return 0
    except (DeliveryError, RequirementWorkspaceError, OSError) as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
