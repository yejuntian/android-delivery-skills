#!/usr/bin/env python3
"""脚本名称：android_project_capabilities.py

用途：在静态门禁或特殊老项目确实无法判断 task 时，独立只读诊断 Gradle 能力及已有
静态分析配置和 CI 信号；普通单元测试不调用。

核心流程：读取 settings/wrapper 基本事实，使用项目外 Gradle 用户/项目缓存运行目标项目
自己的 ``gradlew tasks --all``，再有界扫描构建、静态配置与 CI 文件，结果写到项目之外。

职责边界：不读取普通业务源码、不判断扫描覆盖或业务影响、不选择最终命令、不执行构建
或测试、不安装工具、不修改 Gradle/AGP/JDK，也不把能力存在写成已经通过。
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

# 直接运行时建立包上下文，保证 IDE、python -m 和脚本调用使用同一导入。
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = "scripts"

from .config_paths import capabilities_path_for_config, resolve_config_paths  # noqa: E402
from .delivery import DeliveryError, load_config  # noqa: E402
from .execution_evidence import redact_output  # noqa: E402
from .user_facing_labels import ChineseArgumentParser, localize_machine_terms  # noqa: E402


TASK_LINE = re.compile(r"^([^\s]+)\s+-\s+.+$")
INCLUDE_CALL = re.compile(r"\binclude\s*\(?\s*([^\n]+)")
QUOTED_MODULE = re.compile(r"['\"](:[^'\"]+)['\"]")
STATIC_TOOL_TOKENS = {
    "android-lint": ("lint",),
    "detekt": ("detekt",),
    "error-prone": ("errorprone", "error-prone"),
    "infer": ("infer",),
    "nullaway": ("nullaway",),
    "pmd": ("pmd",),
    "semgrep": ("semgrep",),
    "codeql": ("codeql",),
    "spotbugs": ("spotbugs",),
    "checkstyle": ("checkstyle",),
    "sonar": ("sonar",),
}
IGNORED_DISCOVERY_DIRS = {
    ".git", ".gradle", ".idea", ".kotlin", "build", "out", "node_modules",
}
STATIC_CONFIG_DIRECTORIES = {".config", "config", "quality"}
STATIC_CONFIG_EXTENSIONS = {".json", ".properties", ".xml", ".yaml", ".yml"}
MAX_DISCOVERY_FILES = 50000


class CapabilityDiscoveryError(RuntimeError):
    """表示项目路径、Gradle wrapper 或任务发现无法继续。"""


def parse_gradle_tasks(output: str) -> list[str]:
    """从 ``tasks --all`` 文本提取稳定任务名，忽略标题、说明和日志行。"""
    tasks: list[str] = []
    for line in output.splitlines():
        match = TASK_LINE.match(line.strip())
        if not match:
            continue
        task = match.group(1)
        if re.fullmatch(r"[A-Za-z0-9_:.-]+", task) and task not in tasks:
            tasks.append(task)
    return sorted(tasks)


def _task_leaf(task: str) -> str:
    """返回模块前缀之后的 Gradle task 名。"""
    return task.rsplit(":", 1)[-1]


def classify_tasks(tasks: list[str]) -> dict[str, list[str]]:
    """按用途给原始任务建立索引；未知新工具仍保留在 ``all`` 中供模型读取。"""
    groups = {
        "all": list(tasks),
        "assemble": [],
        "compile": [],
        "unit_test": [],
        "instrumentation": [],
        "lint": [],
        "static_analysis": [],
        "api_abi": [],
        "performance": [],
        "screenshot": [],
        "release_r8": [],
    }
    for task in tasks:
        leaf = _task_leaf(task)
        lowered = leaf.lower()

        def add(group: str) -> None:
            """同一任务可属于多个用途，但每组内保持唯一。"""
            if task not in groups[group]:
                groups[group].append(task)

        if lowered.startswith("assemble") or lowered.startswith("bundle"):
            add("assemble")
        if lowered.startswith("compile"):
            add("compile")
        if lowered == "test" or (
            lowered.startswith("test")
            and not lowered.endswith(("classes", "fixtures", "sources"))
        ):
            add("unit_test")
        if "androidtest" in lowered or lowered.startswith("connected") or lowered.startswith("device"):
            add("instrumentation")
        if lowered.startswith("lint"):
            add("lint")
        if any(token in lowered for token in (
            "detekt", "ktlint", "spotbugs", "checkstyle", "pmd", "errorprone",
            "nullaway", "infer", "semgrep", "codeql",
        )):
            add("static_analysis")
        if any(token in lowered for token in ("api", "abi", "metalava")) and any(
            action in lowered for action in ("check", "validate", "dump", "update")
        ):
            add("api_abi")
        if "benchmark" in lowered or "baselineprofile" in lowered:
            add("performance")
        if any(token in lowered for token in ("paparazzi", "roborazzi", "screenshot", "shot")):
            add("screenshot")
        if any(token in lowered for token in ("release", "minify", "r8", "proguard")):
            add("release_r8")
    return groups


def discover_modules(project: Path, tasks: list[str]) -> list[str]:
    """合并 settings 中显式 include 与任务前缀，不根据模块名字猜依赖方向。"""
    modules: set[str] = set()
    for name in ("settings.gradle.kts", "settings.gradle"):
        path = project / name
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for call in INCLUDE_CALL.finditer(text):
            modules.update(QUOTED_MODULE.findall(call.group(1)))
    for task in tasks:
        if ":" not in task.strip(":"):
            continue
        prefix = task.rsplit(":", 1)[0].strip(":")
        if prefix:
            modules.add(":" + prefix)
    return sorted(modules)


def discover_variants(tasks: list[str]) -> list[str]:
    """从真实 assemble/bundle 任务提取候选 variant，不解析或执行 Gradle 模型。"""
    variants: set[str] = set()
    for task in tasks:
        leaf = _task_leaf(task)
        match = re.fullmatch(r"(?:assemble|bundle)([A-Z][A-Za-z0-9]*)", leaf)
        if not match:
            continue
        suffix = match.group(1)
        if suffix.lower() not in {"all", "androidtest", "unittest"}:
            variants.add(suffix[0].lower() + suffix[1:])
    return sorted(variants)


def _static_candidate_file(relative: Path) -> bool:
    """只选择构建、CI 和静态工具配置，避免遍历读取普通源码与 Android 资源。"""
    path = relative.as_posix().lower()
    name = relative.name.lower()
    if path.startswith(".github/workflows/") and relative.suffix.lower() in {".yml", ".yaml"}:
        return True
    if name in {
        "build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts",
        "libs.versions.toml", "lint.xml", "sonar-project.properties", ".inferconfig",
        ".semgrep.yml", ".semgrep.yaml",
    }:
        return True
    if path.startswith(("buildsrc/", "build-logic/")) and relative.suffix.lower() in {
        ".gradle", ".kts", ".kt",
    }:
        return True
    has_tool_token = any(
        token in path for tokens in STATIC_TOOL_TOKENS.values() for token in tokens
    )
    in_config_directory = bool(
        {part.lower() for part in relative.parts[:-1]} & STATIC_CONFIG_DIRECTORIES
    )
    return (
        has_tool_token
        and relative.suffix.lower() in {
            ".xml", ".yml", ".yaml", ".json", ".properties", ".gradle", ".kts",
        }
    ) or (
        in_config_directory and relative.suffix.lower() in STATIC_CONFIG_EXTENSIONS
    )


def _candidate_files(project: Path) -> tuple[list[Path], int, bool]:
    """有界遍历项目配置，并显式返回扫描数量和是否截断，避免静默漏报。"""
    candidates: list[Path] = []
    visited = 0
    for root, directories, files in os.walk(project):
        directories[:] = sorted(
            (name for name in directories if name.lower() not in IGNORED_DISCOVERY_DIRS),
            key=lambda name: (
                name.lower() not in {".github", ".config", "config", "quality", "buildsrc", "build-logic"},
                name.lower(),
            ),
        )
        root_path = Path(root)
        for name in sorted(files):
            visited += 1
            if visited > MAX_DISCOVERY_FILES:
                return sorted(candidates), visited - 1, True
            path = root_path / name
            try:
                relative = path.relative_to(project)
            except ValueError:
                continue
            if _static_candidate_file(relative):
                candidates.append(path)
    return sorted(candidates), visited, False


def discover_static_analysis_signals(project: str | Path, tasks: list[str]) -> dict[str, Any]:
    """合并 Gradle task、构建配置和 CI 信号；只证明能力存在，不推断实际覆盖范围。"""
    root = Path(project).expanduser().resolve()
    records: dict[str, dict[str, Any]] = {
        tool: {
            "id": tool,
            "tasks": [],
            "build_files": [],
            "config_files": [],
            "ci_files": [],
        }
        for tool in STATIC_TOOL_TOKENS
    }
    for task in tasks:
        lowered = task.lower()
        for tool, tokens in STATIC_TOOL_TOKENS.items():
            if any(token in lowered for token in tokens):
                records[tool]["tasks"].append(task)

    control_files: set[str] = set()
    candidate_files, visited_files, discovery_truncated = _candidate_files(root)
    for path in candidate_files:
        try:
            if path.stat().st_size > 1024 * 1024:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            relative = path.relative_to(root).as_posix()
        except OSError:
            continue
        haystack = f"{relative}\n{text}".lower()
        is_ci = relative.lower().startswith(".github/workflows/")
        is_build = path.name.lower() in {
            "build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts",
            "libs.versions.toml",
        } or relative.lower().startswith(("buildsrc/", "build-logic/"))
        for tool, tokens in STATIC_TOOL_TOKENS.items():
            if not any(token in haystack for token in tokens):
                continue
            field = "ci_files" if is_ci else "build_files" if is_build else "config_files"
            records[tool][field].append(relative)
            control_files.add(relative)

    tools = []
    for record in records.values():
        for field in ("tasks", "build_files", "config_files", "ci_files"):
            record[field] = sorted(set(record[field]))
        if any(record[field] for field in ("tasks", "build_files", "config_files", "ci_files")):
            tools.append(record)
    return {
        "tools": sorted(tools, key=lambda item: item["id"]),
        "control_files": sorted(control_files),
        "visited_files": visited_files,
        "discovery_truncated": discovery_truncated,
    }


def _wrapper_version(project: Path) -> str | None:
    """读取 wrapper distributionUrl 中的 Gradle 版本，不联网解析或更新。"""
    properties = project / "gradle" / "wrapper" / "gradle-wrapper.properties"
    if not properties.is_file():
        return None
    try:
        text = properties.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    match = re.search(r"gradle-([0-9][A-Za-z0-9.-]*)-(?:bin|all)\.zip", text)
    return match.group(1) if match else None


def discover_capabilities(project: str | Path, timeout_seconds: int = 120) -> dict[str, Any]:
    """运行只读任务发现并返回工程事实；Gradle 失败时仍保留命令和错误输出。"""
    root = Path(project).expanduser().resolve()
    if not root.is_dir():
        raise CapabilityDiscoveryError(f"项目路径无效: {root}")
    gradlew = root / "gradlew"
    if not gradlew.is_file():
        raise CapabilityDiscoveryError(f"项目缺少 Gradle wrapper: {gradlew}")
    if timeout_seconds <= 0:
        raise CapabilityDiscoveryError("timeout 必须大于 0 秒")
    cache_root = Path(
        os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))
    ).expanduser() / "android-delivery-skills" / "capabilities" / hashlib.sha256(
        str(root).encode("utf-8")
    ).hexdigest()[:16]
    gradle_user_home = cache_root / "gradle-home"
    project_cache = cache_root / "project-cache"
    gradle_user_home.mkdir(parents=True, exist_ok=True)
    project_cache.mkdir(parents=True, exist_ok=True)
    command = [
        str(gradlew),
        "--project-cache-dir",
        str(project_cache),
        "tasks",
        "--all",
        "--console=plain",
    ]
    env = os.environ.copy()
    env["GRADLE_USER_HOME"] = str(gradle_user_home)
    env.setdefault("GRADLE_OPTS", "-Dorg.gradle.daemon=false")
    try:
        completed = subprocess.run(
            command,
            cwd=root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=timeout_seconds,
        )
        exit_code = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
        timed_out = False
    except subprocess.TimeoutExpired as exc:
        exit_code = 124
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        timed_out = True
    except OSError as exc:
        exit_code = 127
        stdout = ""
        stderr = f"Gradle wrapper 无法启动: {exc}"
        timed_out = False
    tasks = parse_gradle_tasks(stdout) if exit_code == 0 else []
    return {
        "version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_path": str(root),
        "wrapper": str(gradlew),
        "gradle_version": _wrapper_version(root),
        "settings_file": next(
            (str(path) for path in (root / "settings.gradle.kts", root / "settings.gradle") if path.is_file()),
            None,
        ),
        "command": command,
        "gradle_user_home": str(gradle_user_home),
        "project_cache": str(project_cache),
        "exit_code": exit_code,
        "timed_out": timed_out,
        "stderr": redact_output(stderr).strip(),
        "modules": discover_modules(root, tasks),
        "variants": discover_variants(tasks),
        "tasks": classify_tasks(tasks),
        "static_analysis": discover_static_analysis_signals(root, tasks),
    }


def _write_result(path: Path, payload: dict[str, Any]) -> None:
    """原子写入项目外能力快照，避免半文件被其他模型读取。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise CapabilityDiscoveryError(f"能力结果无法写入: {path}: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    """从配置或显式项目路径发现能力，输出结果位置和发现摘要。"""
    parser = ChineseArgumentParser(description="只读发现 Android Gradle 项目能力")
    parser.add_argument("--config", default=None, help="配置文件路径")
    parser.add_argument("--project", default=None, help="Android 项目路径，优先于配置")
    parser.add_argument("--timeout", type=int, default=120, help="Gradle task 发现超时秒数")
    parser.add_argument("--output", default=None, help="输出 JSON，默认外部状态目录")
    args = parser.parse_args(argv)
    config_path = Path(args.config).expanduser().resolve() if args.config else (
        Path(__file__).resolve().parents[1] / "profiles" / "local.yaml"
    )
    try:
        if args.project:
            project = Path(args.project).expanduser().resolve()
        else:
            config = load_config(config_path)
            project = resolve_config_paths(config, config_path).project_path
            if not project:
                raise CapabilityDiscoveryError("配置缺少 project_path")
        result = discover_capabilities(project, args.timeout)
        output = Path(args.output).expanduser().resolve() if args.output else (
            capabilities_path_for_config(config_path)
        )
        _write_result(output, result)
    except (DeliveryError, CapabilityDiscoveryError) as exc:
        print(f"❌ {localize_machine_terms(exc)}", file=sys.stderr)
        return 1
    print(f"能力结果: {output}")
    print(f"Gradle 任务: {len(result['tasks']['all'])}")
    print(f"模块候选: {len(result['modules'])}，variant 候选: {len(result['variants'])}")
    static_signals = result["static_analysis"]
    print(f"已有静态工具信号: {len(static_signals['tools'])}")
    if static_signals["discovery_truncated"]:
        print(
            "⚠️ 静态配置扫描达到文件上限；当前结果不代表全仓发现完整，请只读核对需求影响范围。"
        )
    if result["exit_code"] != 0:
        print(f"❌ Gradle 能力发现失败，退出码 {result['exit_code']}: {result['stderr']}", file=sys.stderr)
        return result["exit_code"] or 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
