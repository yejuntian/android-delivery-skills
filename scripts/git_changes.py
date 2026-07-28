#!/usr/bin/env python3
"""
================================================================================
脚本名称：git_changes.py
用    途：只读检查 Git 分支、工作区状态、变更状态/片段和最终代码摘要。

职责边界：
1. 记录当前需求开始时的仓库、分支和 HEAD，并校验基线没有失效。
2. 收集基线后的 committed、staged、unstaged、untracked 四类变化并去重。
3. 保留新增、修改、删除、重命名状态和零上下文 patch，计算最终工作树摘要。
4. 独立诊断时才使用显式 base_branch 或本地 upstream，不 fetch、不猜测主分支。
5. 不判断 Android 业务含义，不决定调用哪个 Skill，不修改 Git 状态。
================================================================================
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

GIT_TIMEOUT_SECONDS = 30


class GitInspectionError(RuntimeError):
    """表示 Git 仓库或只读检查命令无法继续执行。"""


@dataclass(frozen=True)
class GitChange:
    """保存一个需求范围内文件的 Git 状态和真实变更片段。"""

    status: str
    path: str
    old_path: str | None = None
    patch: str = ""


def _git(repo, args, optional=False):
    """执行只读 Git 命令；optional=True 仅用于本地基准探测。"""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repo,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        if optional:
            return None
        raise GitInspectionError(
            f"Git 命令执行超时（{GIT_TIMEOUT_SECONDS} 秒）: git {' '.join(args)}"
        ) from exc
    if result.returncode == 0:
        return result.stdout
    if optional:
        return None
    message = result.stderr.decode("utf-8", errors="replace").strip()
    raise GitInspectionError(f"Git 命令执行失败: git {' '.join(args)}\n{message}")


def _require_repository(repo):
    """所有公开检查共用同一仓库门禁。"""
    repo = Path(repo).expanduser().resolve()
    if _git(repo, ["rev-parse", "--is-inside-work-tree"], True) is None:
        raise GitInspectionError(f"项目不是 Git 仓库: {repo}")
    return repo


def current_branch(repo):
    """返回当前分支；detached HEAD 时返回空字符串。"""
    repo = _require_repository(repo)
    return _git(repo, ["branch", "--show-current"]).decode("utf-8").strip()


def current_head(repo):
    """返回当前 HEAD commit，供一次需求记录稳定的 diff 起点。"""
    repo = _require_repository(repo)
    return _git(repo, ["rev-parse", "HEAD"]).decode("utf-8").strip()


def working_tree_status(repo, *, untracked_files="normal"):
    """返回 Git porcelain 状态，空字符串表示工作区干净。

    check-env 需要展开未跟踪目录，才能精确判断新增文件是否只属于当前
    requirement_dir；默认保持 Git 原生 normal 行为，避免影响其他调用方。
    """
    repo = _require_repository(repo)
    args = ["status", "--porcelain"]
    if untracked_files == "all":
        args.append("--untracked-files=all")
    elif untracked_files != "normal":
        raise GitInspectionError("untracked_files 只能是 normal 或 all")
    return _git(repo, args).decode("utf-8", errors="replace").strip()


def write_baseline(repo, path):
    """记录当前仓库、分支和 HEAD；不提交、不暂存，也不修改目标仓库。"""
    repo = _require_repository(repo)
    head = current_head(repo)
    now = datetime.now(timezone.utc)
    payload = {
        "version": 1,
        "id": f"{time.time_ns()}-{head[:8]}",
        "repo": str(repo),
        "branch": current_branch(repo),
        "head": head,
        "created_at": now.isoformat(),
    }
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(target)
    except OSError:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return payload


def load_baseline(repo, path):
    """校验基线属于当前仓库/分支，且仍是 HEAD 祖先，拒绝使用过期范围。"""
    repo = _require_repository(repo)
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise GitInspectionError(f"当前需求 Git 基线不存在: {source}；请先运行 check-env")
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise GitInspectionError(f"当前需求 Git 基线无法读取: {source}: {exc}") from exc
    required = {"id", "repo", "branch", "head", "created_at"}
    if not isinstance(payload, dict) or not required.issubset(payload):
        raise GitInspectionError(f"当前需求 Git 基线格式无效: {source}")
    if Path(str(payload["repo"])).resolve() != repo:
        raise GitInspectionError("当前需求 Git 基线属于其他项目；请重新运行 check-env")
    branch = current_branch(repo)
    if payload["branch"] != branch:
        raise GitInspectionError(
            f"当前分支 ({branch}) 与需求基线分支 ({payload['branch']}) 不一致"
        )
    head = str(payload["head"])
    if _git(repo, ["merge-base", "--is-ancestor", head, "HEAD"], True) is None:
        raise GitInspectionError("当前需求 Git 基线不再是 HEAD 祖先；请重新运行 check-env")
    return payload


def collect_changed_files(repo, base_branch=None, baseline_path=None):
    """合并 committed、staged、unstaged、untracked，并按路径去重。"""
    repo = _require_repository(repo)

    def paths(args):
        """用 NUL 分隔读取路径，避免空格或中文文件名被错误拆分。"""
        output = _git(repo, args)
        return {
            item.decode("utf-8", errors="surrogateescape")
            for item in output.split(b"\0")
            if item
        }

    warnings = []
    if baseline_path:
        base_ref = str(load_baseline(repo, baseline_path)["head"])
        use_merge_base = False
    else:
        base_ref = base_branch
        use_merge_base = True
        if base_ref and _git(
            repo, ["rev-parse", "--verify", f"{base_ref}^{{commit}}"], True
        ) is None:
            warnings.append(f"配置的 base_branch 不存在: {base_ref}；已提交差异未验证")
            base_ref = None
        if not base_ref and not base_branch:
            upstream = _git(
                repo,
                ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"],
                True,
            )
            base_ref = upstream.decode("utf-8").strip() if upstream else None
            if not base_ref:
                warnings.append("未配置 base_branch 且当前分支没有 upstream；只检查工作区变化")

    files = set()
    if base_ref:
        if use_merge_base:
            merge_base = _git(repo, ["merge-base", base_ref, "HEAD"], True)
            comparison = merge_base.decode().strip() if merge_base else None
        else:
            comparison = base_ref
        if comparison:
            files.update(
                paths(["diff", "--name-only", "-z", comparison, "HEAD"])
            )
        else:
            warnings.append(f"无法计算 {base_ref} 与 HEAD 的 merge-base；已提交差异未验证")

    # 三条命令分别覆盖暂存、未暂存和未跟踪文件，避免 `git diff HEAD` 漏报。
    files.update(paths(["diff", "--cached", "--name-only", "-z"]))
    files.update(paths(["diff", "--name-only", "-z"]))
    files.update(paths(["ls-files", "--others", "--exclude-standard", "-z"]))
    return sorted(files), warnings


def _parse_name_status(output: bytes) -> list[tuple[str, str | None, str]]:
    """解析 Git NUL 分隔的 name-status，保留删除和重命名的原始路径。"""
    tokens = [item.decode("utf-8", errors="surrogateescape") for item in output.split(b"\0") if item]
    entries: list[tuple[str, str | None, str]] = []
    index = 0
    while index < len(tokens):
        raw_status = tokens[index]
        index += 1
        status = raw_status[0]
        if status in {"R", "C"}:
            if index + 1 >= len(tokens):
                raise GitInspectionError("Git 重命名状态输出不完整")
            old_path, path = tokens[index], tokens[index + 1]
            index += 2
            entries.append((status, old_path, path))
        else:
            if index >= len(tokens):
                raise GitInspectionError("Git 文件状态输出不完整")
            path = tokens[index]
            index += 1
            entries.append((status, None, path))
    return entries


def collect_changed_entries(repo, baseline_path) -> tuple[list[GitChange], list[str]]:
    """返回基线后的状态与零上下文补丁，供路由识别真实增删改而非整文件旧内容。"""
    repo = _require_repository(repo)
    baseline = load_baseline(repo, baseline_path)
    base_ref = str(baseline["head"])
    files, warnings = collect_changed_files(repo, baseline_path=baseline_path)
    raw_status = _git(
        repo,
        ["diff", "--name-status", "-z", "--find-renames", base_ref],
    )
    status_by_path = {
        path: (status, old_path)
        for status, old_path, path in _parse_name_status(raw_status)
    }
    untracked = {
        item.decode("utf-8", errors="surrogateescape")
        for item in _git(repo, ["ls-files", "--others", "--exclude-standard", "-z"]).split(b"\0")
        if item
    }

    changes: list[GitChange] = []
    for path in files:
        status, old_path = status_by_path.get(path, ("A" if path in untracked else "M", None))
        patch_paths = [old_path, path] if old_path else [path]
        patch = _git(
            repo,
            [
                "--literal-pathspecs",
                "diff",
                "--no-ext-diff",
                "--unified=0",
                "--find-renames",
                base_ref,
                "--",
                *[item for item in patch_paths if item],
            ],
        ).decode("utf-8", errors="replace")
        # 未跟踪文件没有 Git patch，用当前文本作为路由信号；业务结论仍由 AI 复核。
        if not patch and path in untracked:
            candidate = repo / path
            try:
                if candidate.is_file() and candidate.stat().st_size <= 512 * 1024:
                    patch = candidate.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                patch = ""
        changes.append(GitChange(status=status, path=path, old_path=old_path, patch=patch))
    return sorted(changes, key=lambda item: item.path), warnings


def current_delivery_snapshot(
    repo,
    baseline_path,
    exclude_paths: set[str] | None = None,
) -> dict[str, str]:
    """计算基线到当前工作树的稳定摘要，可排除最终报告自身以避免自引用。"""
    repo = _require_repository(repo)
    baseline = load_baseline(repo, baseline_path)
    excluded = {path.replace("\\", "/") for path in (exclude_paths or set())}
    diff_args = ["diff", "--binary", "--no-ext-diff", str(baseline["head"])]
    if excluded:
        diff_args.extend(["--", "."])
        diff_args.extend(f":(exclude,literal){path}" for path in sorted(excluded))
    digest = hashlib.sha256()
    digest.update(_git(repo, diff_args))
    untracked = sorted(
        item.decode("utf-8", errors="surrogateescape")
        for item in _git(repo, ["ls-files", "--others", "--exclude-standard", "-z"]).split(b"\0")
        if item
    )
    for relative in untracked:
        if relative in excluded:
            continue
        # 目录前缀排除：exclude_paths 含 "document" 时，document/ 下所有 untracked 也排除。
        if any(relative == prefix or relative.startswith(prefix.rstrip("/") + "/")
               for prefix in excluded):
            continue
        digest.update(b"\0untracked\0")
        digest.update(relative.encode("utf-8", errors="surrogateescape"))
        path = repo / relative
        try:
            with path.open("rb") as source:
                while chunk := source.read(1024 * 1024):
                    digest.update(chunk)
        except OSError as exc:
            raise GitInspectionError(f"无法读取未跟踪文件以计算交付摘要: {relative}: {exc}") from exc
    return {
        "baseline_id": str(baseline["id"]),
        "baseline_head": str(baseline["head"]),
        "head": current_head(repo),
        "snapshot_sha256": digest.hexdigest(),
    }


def main(argv=None):
    """以 JSON 输出只读检查结果，供 AI 或其他脚本独立调用。"""
    parser = argparse.ArgumentParser(description="只读检查 Git 分支、状态和变更文件")
    parser.add_argument("--repo", default=".", help="Git 仓库路径")
    parser.add_argument("--base-branch", help="可选的已提交差异对比分支")
    args = parser.parse_args(argv)

    try:
        files, warnings = collect_changed_files(args.repo, args.base_branch)
        result = {
            "repo": str(Path(args.repo).expanduser().resolve()),
            "branch": current_branch(args.repo),
            "working_tree": working_tree_status(args.repo),
            "changed_files": files,
            "warnings": warnings,
        }
    except GitInspectionError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
