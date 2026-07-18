#!/usr/bin/env python3
"""脚本名称：run_journey.py

用途：通过独立 AGP 9 壳项目，对已安装的旧 Android 应用执行 UI Journey 测试。

主流程：预检 Journey -> 构建并安装目标 APK -> 从 APK 注入真实包名 -> 执行
Journey -> 归因失败 -> 输出 JSON/Markdown 报告。壳项目与目标项目相互隔离，因此
无需升级旧项目的 Gradle 或 AGP；Gradle 用户缓存、项目缓存和构建输出均写入 Skill
目录外，避免运行产物导致 Skill 超出体积限制。

退出码是自动修复的安全边界：0 表示真实通过、明确跳过或仅预检，必须结合状态读取；
1 表示壳、设备、结构化证据或环境不可用，只能降级，不得修改目标应用；2 表示连续
两次真实 UI 断言失败，允许进入测试根因分析，但仍需确认是实现缺陷还是用例问题。
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
SUITE_ROOT = SKILL_DIR.parent
DEFAULT_HARNESS = SKILL_DIR / "assets" / "journey-harness"
DEFAULT_CONFIG = SUITE_ROOT / "profiles" / "local.yaml"
JOURNEY_GRADLE_HOME_ENV = "ANDROID_DELIVERY_JOURNEY_GRADLE_HOME"
JOURNEY_BUILD_ROOT_ENV = "ANDROID_DELIVERY_JOURNEY_BUILD_ROOT"

# Journey 与总入口必须使用完全相同的配置路径语义。
if str(SUITE_ROOT) not in sys.path:
    sys.path.insert(0, str(SUITE_ROOT))
from scripts.config_paths import baseline_path_for_config, resolve_config_paths  # noqa: E402

PASS = "PASS"
PREFLIGHT_PASS = "PREFLIGHT_PASS"
SKIPPED_NO_UI = "SKIPPED_NO_UI"
SKIPPED_VISUAL_ONLY = "SKIPPED_VISUAL_ONLY"
# 只有 APP_ASSERTION_FAILED 允许分析目标实现；它不是“生产代码必然有错”的证明。
APP_ASSERTION_FAILED = "APP_ASSERTION_FAILED"
HARNESS_UNAVAILABLE = "HARNESS_UNAVAILABLE"
HARNESS_FAILED = "HARNESS_FAILED"
MALFORMED_JOURNEY = "MALFORMED_JOURNEY"
NO_JOURNEY_FOUND = "NO_JOURNEY_FOUND"

ADB_TIMEOUT_SECONDS = 120
GRADLE_TIMEOUT_SECONDS = 1800


def _default_harness_runtime_root(harness: Path) -> Path:
    """按壳路径生成稳定的本机运行目录，使不同 Skill 副本互不污染。"""
    cache_root = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    harness_key = hashlib.sha256(str(harness.resolve()).encode("utf-8")).hexdigest()[:12]
    return (cache_root.expanduser() / "android-delivery-skills" / "journey-runtime" / harness_key).resolve()


def resolve_harness_gradle_user_home(harness: Path) -> Path:
    """返回 Skill 目录外的独立 Gradle 用户缓存，避免依赖缓存撑大 Skill。"""
    explicit = os.environ.get(JOURNEY_GRADLE_HOME_ENV)
    if explicit:
        return Path(explicit).expanduser().resolve()
    return (_default_harness_runtime_root(harness) / "gradle-user-home").resolve()


def resolve_harness_build_root(harness: Path) -> Path:
    """返回 Skill 目录外的壳构建目录，供 Gradle、结果和截图读取共用。"""
    explicit = os.environ.get(JOURNEY_BUILD_ROOT_ENV)
    if explicit:
        return Path(explicit).expanduser().resolve()
    return (_default_harness_runtime_root(harness) / "harness-app-build").resolve()


def resolve_harness_project_cache(harness: Path) -> Path:
    """返回 Skill 目录外的 Gradle 项目缓存，避免壳根目录重新生成 .gradle。"""
    return (_default_harness_runtime_root(harness) / "project-cache").resolve()


def resolve_fallback_result_path(harness: Path) -> Path:
    """返回外部兜底报告路径，配置读取失败时也不在 Skill 内生成 build 目录。"""
    return (
        _default_harness_runtime_root(harness)
        / "reports"
        / "journey-harness"
        / "result.json"
    ).resolve()


@dataclass
class CommandResult:
    """保存外部命令、退出码和完整输出，供失败归因与报告复用。"""

    command: list[str]
    returncode: int
    output: str


@dataclass
class JourneyResult:
    """统一表达通过、跳过、环境失败和真实 UI 断言失败。"""

    status: str
    message: str
    exit_code: int
    device: str | None = None
    package: str | None = None
    apk: str | None = None
    task: str | None = None
    journey_files: list[str] = field(default_factory=list)
    action_count: int = 0
    executed_tests: int = 0
    attempts: int = 0
    screenshots: list[str] = field(default_factory=list)
    result_files: list[str] = field(default_factory=list)
    commands: list[list[str]] = field(default_factory=list)


@dataclass
class StructuredTestResult:
    """汇总本轮 Gradle 产生的 JUnit XML，作为实际测试数量和结论证据。"""

    executed: int = 0
    failures: int = 0
    errors: int = 0
    files: list[str] = field(default_factory=list)


@dataclass
class HarnessRunResult:
    """保存壳执行结论及其结构化证据，避免依赖位置含糊的 tuple。"""

    status: str
    attempts: int
    commands: list[list[str]]
    screenshots: list[str]
    output: str
    executed_tests: int = 0
    result_files: list[str] = field(default_factory=list)


def _redact_uri(value: str) -> str:
    """保留 DeepLink 的目标路径，但移除可能包含票据或 PII 的查询参数。"""
    try:
        parsed = urlsplit(value)
    except ValueError:
        return "<redacted-uri>"
    if not parsed.scheme:
        return value
    query = "<redacted>" if parsed.query else ""
    fragment = "<redacted>" if parsed.fragment else ""
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query, fragment))


def redact_command(cmd: list[str]) -> list[str]:
    """生成只用于终端和报告的安全命令，不改变实际执行参数。"""
    safe: list[str] = []
    hide_next = False
    sensitive_option = re.compile(r"(?:token|password|secret|cookie|authorization|api[-_]?key)", re.I)
    for value in cmd:
        text = str(value)
        if hide_next:
            safe.append("<redacted>")
            hide_next = False
        elif text.startswith("-") and sensitive_option.search(text):
            if "=" in text:
                safe.append(text.split("=", 1)[0] + "=<redacted>")
            else:
                safe.append(text)
                hide_next = True
        elif "://" in text:
            safe.append(_redact_uri(text))
        else:
            safe.append(text)
    return safe


def _redact_output(output: str, cmd: list[str]) -> str:
    """替换外部工具可能回显的敏感参数，避免报告重新泄漏原始 DeepLink。"""
    safe = output
    for raw, redacted in zip(cmd, redact_command(cmd)):
        if raw != redacted and raw:
            safe = safe.replace(raw, redacted)
    return safe


def run(
    cmd: list[str],
    *,
    cwd: Path | str | None = None,
    env: dict[str, str] | None = None,
    stream: bool = False,
    timeout: int = GRADLE_TIMEOUT_SECONDS,
) -> CommandResult:
    """执行外部命令但不抛退出码异常，确保上层按失败类型安全归因。"""
    safe_command = redact_command(cmd)
    print(f"$ {' '.join(safe_command)}")
    try:
        completed = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        return CommandResult(safe_command, 127, str(exc))
    except subprocess.TimeoutExpired as exc:
        raw_output = exc.stdout or ""
        if isinstance(raw_output, bytes):
            raw_output = raw_output.decode("utf-8", errors="replace")
        output = _redact_output(str(raw_output), cmd)
        message = f"{output}\n命令执行超时（{timeout} 秒）".strip()
        return CommandResult(safe_command, 124, message)
    output = _redact_output(completed.stdout or "", cmd)
    if stream and output:
        print(output, end="" if output.endswith("\n") else "\n")
    return CommandResult(safe_command, completed.returncode, output)


def load_config(path: Path) -> dict[str, Any]:
    """读取 Journey 配置，并拒绝非 object 的 YAML 根节点。"""
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("缺少 PyYAML，无法读取配置") from exc
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise RuntimeError("配置根节点必须是 YAML object")
    return data


def list_devices() -> list[str]:
    """只返回 adb 状态为 device 的在线设备，排除 offline/unauthorized。"""
    result = run(["adb", "devices"], timeout=ADB_TIMEOUT_SECONDS)
    if result.returncode != 0:
        return []
    devices = []
    for line in result.output.splitlines()[1:]:
        fields = line.strip().split("\t")
        if len(fields) == 2 and fields[1] == "device":
            devices.append(fields[0])
    return devices


def choose_device(explicit: str | None) -> tuple[str | None, str | None]:
    """显式设备优先；多设备时拒绝猜测，要求调用方指定 serial。"""
    devices = list_devices()
    if explicit:
        if explicit not in devices:
            return None, f"指定设备不在线: {explicit}"
        return explicit, None
    if not devices:
        return None, "adb devices 没有在线设备"
    if len(devices) > 1:
        return None, f"检测到多个设备，请用 --device 指定: {', '.join(devices)}"
    return devices[0], None


def validate_journeys(journeys_dir: Path) -> tuple[list[Path], int, str | None]:
    """校验 Journey 至少包含一个有效步骤，避免“零测试执行”造成假绿。"""
    files = sorted(journeys_dir.glob("*.xml"))
    if not files:
        return [], 0, "没有 Journey XML；拒绝以 0 个测试判绿"

    action_count = 0
    for path in files:
        try:
            document = ET.parse(path)
        except (ET.ParseError, OSError) as exc:
            return files, action_count, f"Journey XML 无法解析: {path}: {exc}"
        root_element = document.getroot()
        if root_element.tag.rsplit("}", 1)[-1] != "journey":
            return files, action_count, f"Journey 根节点必须是 <journey>: {path}"
        actions = [
            node for node in root_element.iter()
            if node.tag.rsplit("}", 1)[-1] in {"action", "step"}
            and "".join(node.itertext()).strip()
        ]
        if not actions:
            return files, action_count, f"Journey 不包含有效 action/step: {path}"
        action_count += len(actions)
    return files, action_count, None


def resolve_journeys_dir(
    config_path: Path,
    config: dict[str, Any],
    settings: dict[str, Any],
    explicit: str | None,
) -> Path:
    """定位当前需求的用例目录，避免不同项目共用壳源码目录而串用旧用例。"""
    paths = resolve_config_paths(config, config_path)
    configured = explicit or settings.get("cases_dir")
    if not configured:
        return (paths.requirement_dir / "test-cases" / "journeys" / requirement_scope_id(
            config_path, config
        )).resolve()
    source = Path(str(configured)).expanduser()
    return source.resolve() if source.is_absolute() else (paths.requirement_dir / source).resolve()


def requirement_scope_id(config_path: Path, config: dict[str, Any]) -> str:
    """优先使用本次 Git 基线隔离用例；单独调用时退回需求内容哈希。"""
    requirement_path = resolve_config_paths(config, config_path).requirement_path
    digest: str | None = None
    if requirement_path and requirement_path.is_file():
        try:
            digest = hashlib.sha256(requirement_path.read_bytes()).hexdigest()[:16]
        except OSError:
            pass

    baseline_path = baseline_path_for_config(config_path)
    try:
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        baseline = {}
    baseline_id = baseline.get("id") if isinstance(baseline, dict) else None
    if isinstance(baseline_id, str) and re.fullmatch(r"[A-Za-z0-9._-]+", baseline_id):
        return f"{baseline_id}-{digest}" if digest else baseline_id
    if digest:
        return f"requirement-{digest}"
    return "standalone"


def resolve_result_path(config_path: Path, config: dict[str, Any]) -> Path:
    """把报告放入当前需求目录并按需求作用域隔离，避免覆盖上一需求。"""
    paths = resolve_config_paths(config, config_path)
    return (
        paths.requirement_dir
        / "test-results"
        / "journey-harness"
        / requirement_scope_id(config_path, config)
        / "result.json"
    ).resolve()


def stage_journeys(files: list[Path], harness: Path) -> None:
    """把本次用例同步到壳的执行目录，并清除上一次需求留下的 XML。"""
    target = harness / "harness-app" / "src" / "main" / "journeys"
    target.mkdir(parents=True, exist_ok=True)
    if files and files[0].parent.resolve() == target.resolve():
        return
    for stale in target.glob("*.xml"):
        stale.unlink()
    for source in files:
        shutil.copy2(source, target / source.name)


def variant_task_suffix(variant: str) -> str:
    """把完整 variant 转成 Gradle task 后缀，同时拒绝非法任务注入。"""
    if not variant or not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", variant):
        raise ValueError(f"非法 variant: {variant!r}")
    return variant[0].upper() + variant[1:]


def module_parts(module: str) -> list[str]:
    """把 `app` 或 `feature:demo` 同时映射为 Gradle task 与真实模块目录。"""
    value = str(module).strip(":")
    parts = value.split(":") if value else []
    if not parts or any(not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]*", part) for part in parts):
        raise ValueError(f"非法 module: {module!r}")
    return parts


def module_output_root(project: Path, module: str) -> Path:
    """根据 Gradle module path 定位 APK 输出根目录。"""
    return project.joinpath(*module_parts(module), "build", "outputs", "apk")


def _tokens(value: str) -> set[str]:
    """把 camelCase、目录和连字符统一拆成 token，兼容老 AGP 的 flavor/buildType 路径。"""
    separated = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value)
    return {item.lower() for item in re.split(r"[^A-Za-z0-9]+", separated) if item}


def find_apk_from_metadata(
    project: Path, module: str, variant: str, not_before: float | None = None
) -> Path | None:
    """优先读取 AGP 输出元数据，准确定位指定变体及其实际 APK。"""
    output_root = module_output_root(project, module)
    for metadata in output_root.rglob("output-metadata.json") if output_root.exists() else []:
        try:
            data = json.loads(metadata.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if str(data.get("variantName", "")).lower() != variant.lower():
            continue
        elements = sorted(data.get("elements", []), key=lambda item: bool(item.get("filters")))
        for element in elements:
            output_file = element.get("outputFile")
            if output_file:
                apk = metadata.parent / output_file
                if apk.is_file() and (not_before is None or apk.stat().st_mtime >= not_before - 1):
                    return apk
    return None


def find_newest_apk(
    project: Path, module: str, variant: str, not_before: float | None = None
) -> Path | None:
    """元数据不可用时只在明确匹配目标 variant 的本轮 APK 中选择。"""
    metadata_apk = find_apk_from_metadata(project, module, variant, not_before)
    if metadata_apk:
        return metadata_apk
    output_root = module_output_root(project, module)
    candidates = [
        p for p in output_root.rglob("*.apk")
        if p.is_file()
        and "androidtest" not in str(p).lower()
        and (not_before is None or p.stat().st_mtime >= not_before - 1)
    ] if output_root.exists() else []
    variant_tokens = _tokens(variant)
    matched = [
        path for path in candidates
        if variant_tokens.issubset(_tokens(str(path.relative_to(output_root))))
    ]
    return max(matched, key=lambda p: p.stat().st_mtime) if matched else None


def build_target_apk(project: Path, module: str, variant: str) -> tuple[Path | None, CommandResult]:
    """使用目标项目自身 wrapper 构建，避免 AGP 9 壳污染旧项目工具链。"""
    # 使用目标项目自己的 wrapper，避免壳项目的 AGP/Gradle 版本侵入旧项目。
    gradlew = project / "gradlew"
    if not gradlew.is_file():
        result = CommandResult([str(gradlew)], 127, "老项目缺少 Gradle wrapper")
        return None, result
    task = f":{':'.join(module_parts(module))}:assemble{variant_task_suffix(variant)}"
    started_at = time.time()
    result = run(
        [str(gradlew), task, "--console=plain"],
        cwd=project,
        stream=True,
        timeout=GRADLE_TIMEOUT_SECONDS,
    )
    apk = find_newest_apk(project, module, variant, started_at) if result.returncode == 0 else None
    return apk, result


def resolve_android_sdk() -> str | None:
    """优先使用标准环境变量，再通过 android CLI 查询 SDK。"""
    configured = os.environ.get("ANDROID_SDK_ROOT") or os.environ.get("ANDROID_HOME")
    if configured and Path(configured).is_dir():
        return configured
    result = run(["android", "info", "sdk"], timeout=ADB_TIMEOUT_SECONDS)
    value = result.output.strip().splitlines()
    return value[-1].strip() if result.returncode == 0 and value and Path(value[-1].strip()).is_dir() else None


def sdk_tool(name: str, sdk: str | None = None) -> str | None:
    """从 PATH 或已确认 SDK 中定位工具，不下载或猜测版本。"""
    found = shutil.which(name)
    if found:
        return found
    sdk = sdk or os.environ.get("ANDROID_SDK_ROOT") or os.environ.get("ANDROID_HOME")
    if not sdk:
        return None
    candidates = [
        Path(sdk) / "cmdline-tools" / "latest" / "bin" / name,
        Path(sdk) / "tools" / "bin" / name,
        Path(sdk) / "build-tools",
    ]
    for candidate in candidates[:2]:
        if candidate.is_file():
            return str(candidate)
    if name == "aapt" and candidates[2].is_dir():
        versions = sorted(candidates[2].iterdir(), reverse=True)
        for version in versions:
            executable = version / "aapt"
            if executable.is_file():
                return str(executable)
    return None


def package_from_apk(apk: Path, sdk: str | None = None) -> tuple[str | None, list[list[str]]]:
    """从最终 APK 读取包名，以覆盖 suffix、flavor 和动态 Gradle 配置。"""
    commands: list[list[str]] = []
    apkanalyzer = sdk_tool("apkanalyzer", sdk)
    if apkanalyzer:
        result = run([apkanalyzer, "manifest", "application-id", str(apk)], timeout=ADB_TIMEOUT_SECONDS)
        commands.append(result.command)
        value = result.output.strip().splitlines()
        if result.returncode == 0 and value:
            return value[-1].strip(), commands
    aapt = sdk_tool("aapt", sdk)
    if aapt:
        result = run([aapt, "dump", "badging", str(apk)], timeout=ADB_TIMEOUT_SECONDS)
        commands.append(result.command)
        match = re.search(r"package: name='([^']+)'", result.output)
        if result.returncode == 0 and match:
            return match.group(1), commands
    return None, commands


def install_and_verify(apk: Path, package: str, device: str) -> tuple[bool, list[list[str]], str]:
    """安装后用 pm path 二次确认真实包已出现在指定设备。"""
    install = run(
        ["adb", "-s", device, "install", "-r", str(apk)],
        stream=True,
        timeout=ADB_TIMEOUT_SECONDS,
    )
    verify = run(
        ["adb", "-s", device, "shell", "pm", "path", package],
        timeout=ADB_TIMEOUT_SECONDS,
    )
    commands = [install.command, verify.command]
    ok = install.returncode == 0 and verify.returncode == 0 and "package:" in verify.output
    return ok, commands, install.output + verify.output


def verify_installed(package: str, device: str) -> tuple[bool, list[str]]:
    """skip-build 模式下只验证现有安装，不改变目标应用。"""
    result = run(
        ["adb", "-s", device, "shell", "pm", "path", package],
        timeout=ADB_TIMEOUT_SECONDS,
    )
    return result.returncode == 0 and "package:" in result.output, result.command


def apply_precondition(
    settings: dict[str, Any], package: str, device: str
) -> tuple[bool, list[list[str]], str]:
    """仅执行配置明确授权的清数据、授权或启动动作，并记录全部命令。"""
    # 清数据、授权和定向启动都会改变设备状态，仅执行配置中显式声明的操作。
    precondition = settings.get("precondition", {}) or {}
    if not isinstance(precondition, dict):
        return False, [], "testing.journey_harness.precondition 必须是 YAML object"
    commands: list[list[str]] = []
    if precondition.get("clear_app_data", False):
        result = run(
            ["adb", "-s", device, "shell", "pm", "clear", package],
            timeout=ADB_TIMEOUT_SECONDS,
        )
        commands.append(result.command)
        if result.returncode != 0 or "success" not in result.output.lower():
            return False, commands, f"清理应用数据失败: {result.output}"

    permissions = precondition.get("grant_permissions", []) or []
    if not isinstance(permissions, list):
        return False, commands, "precondition.grant_permissions 必须是 list"
    for permission in permissions:
        result = run(
            ["adb", "-s", device, "shell", "pm", "grant", package, str(permission)],
            timeout=ADB_TIMEOUT_SECONDS,
        )
        commands.append(result.command)
        if result.returncode != 0:
            return False, commands, f"授予权限失败 {permission}: {result.output}"

    deep_link = precondition.get("deep_link")
    activity = precondition.get("launch_activity")
    if deep_link and activity:
        return False, commands, "precondition.deep_link 与 launch_activity 只能配置一个"
    if deep_link:
        result = run([
            "adb", "-s", device, "shell", "am", "start", "-W",
            "-a", "android.intent.action.VIEW", "-d", str(deep_link), package,
        ], timeout=ADB_TIMEOUT_SECONDS)
        commands.append(result.command)
        if result.returncode != 0 or "error" in result.output.lower():
            return False, commands, f"DeepLink 前置失败: {result.output}"
    elif activity:
        result = run([
            "adb", "-s", device, "shell", "am", "start", "-W",
            "-n", f"{package}/{activity}",
        ], timeout=ADB_TIMEOUT_SECONDS)
        commands.append(result.command)
        if result.returncode != 0 or "error" in result.output.lower():
            return False, commands, f"Activity 前置失败: {result.output}"
    return True, commands, ""


def discover_journey_task(
    harness: Path, configured: str | None, sdk: str
) -> tuple[str | None, CommandResult | None]:
    """从壳任务列表唯一识别 Journey task；存在歧义时拒绝猜测。"""
    # Journey 仍是预览能力，任务名可能随 Android Studio/插件版本变化，不能硬编码猜测。
    if configured:
        return configured, None
    gradlew = harness / "gradlew"
    env = os.environ.copy()
    env["GRADLE_USER_HOME"] = str(resolve_harness_gradle_user_home(harness))
    env[JOURNEY_BUILD_ROOT_ENV] = str(resolve_harness_build_root(harness))
    env["ANDROID_HOME"] = sdk
    env["ANDROID_SDK_ROOT"] = sdk
    result = run(
        [
            str(gradlew),
            "--project-cache-dir",
            str(resolve_harness_project_cache(harness)),
            ":harness-app:tasks",
            "--all",
            "--console=plain",
        ],
        cwd=harness,
        env=env,
        timeout=GRADLE_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        return None, result
    tasks: list[str] = []
    for line in result.output.splitlines():
        task = line.strip().split(" ", 1)[0]
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", task) and "journey" in task.lower():
            tasks.append(f":harness-app:{task}")
    # 只接受名称同时表达 test 和 journey 的任务；生成/准备类任务不能作为执行门禁。
    candidates = [
        task for task in tasks
        if re.search(r"test.*journey|journey.*test", task, re.IGNORECASE)
    ]
    return (candidates[0], result) if len(candidates) == 1 else (None, result)


ENVIRONMENT_PATTERNS = (
    "task with path", "could not resolve", "could not compile", "authentication",
    "not authenticated", "sign in to gemini", "gemini authentication", "gemini is unavailable",
    "no connected devices", "no devices", "no-source", "journey xml", "configuration cache",
    "failed to apply plugin", "plugin with id", "sdk location not found", "执行超时", "timed out",
)
ASSERTION_PATTERNS = (
    "assertionerror", "assertion failed", "failed to complete action",
    "expectation failed", "verification failed",
)


def classify_failure(output: str) -> str:
    """保守区分环境故障与 UI 断言，防止误把壳故障归因给目标应用。"""
    lowered = output.lower()
    if re.search(r"task .* not found", lowered) or any(
        pattern in lowered for pattern in ENVIRONMENT_PATTERNS
    ):
        return HARNESS_FAILED
    if any(pattern in lowered for pattern in ASSERTION_PATTERNS):
        return APP_ASSERTION_FAILED
    return HARNESS_FAILED


def collect_structured_results(harness: Path, started_at: float) -> StructuredTestResult:
    """读取本轮生成的 JUnit XML；没有结构化执行数量时拒绝判绿。"""
    summary = StructuredTestResult()
    build_root = resolve_harness_build_root(harness)
    if not build_root.is_dir():
        return summary
    for path in build_root.rglob("*.xml"):
        relative = str(path.relative_to(build_root)).lower()
        if "journey" not in relative:
            continue
        if not path.is_file() or path.stat().st_mtime < started_at - 1:
            continue
        try:
            root = ET.parse(path).getroot()
        except (ET.ParseError, OSError):
            continue
        tag = root.tag.rsplit("}", 1)[-1]
        if tag == "testsuite":
            suites = [root]
        elif tag == "testsuites":
            suites = [node for node in root if node.tag.rsplit("}", 1)[-1] == "testsuite"]
        else:
            continue
        try:
            executed = sum(int(suite.attrib.get("tests", "0")) for suite in suites)
            failures = sum(int(suite.attrib.get("failures", "0")) for suite in suites)
            errors = sum(int(suite.attrib.get("errors", "0")) for suite in suites)
        except ValueError:
            continue
        if executed <= 0:
            continue
        summary.executed += executed
        summary.failures += failures
        summary.errors += errors
        summary.files.append(str(path.resolve()))
    summary.files.sort()
    return summary


def collect_screenshots(harness: Path, started_at: float) -> list[str]:
    """只收集 Journey/capture/screenshot 结果目录，排除普通构建图片资源。"""
    paths = []
    build_root = resolve_harness_build_root(harness)
    for pattern in ("**/*.png", "**/*.jpg", "**/*.jpeg", "**/*.webp"):
        for raw in glob.glob(str(build_root / pattern), recursive=True):
            path = Path(raw)
            relative = str(path.relative_to(build_root)).lower()
            is_evidence_dir = any(word in relative for word in ("journey", "screenshot", "capture"))
            if path.is_file() and is_evidence_dir and path.stat().st_mtime >= started_at - 1:
                paths.append(str(path.resolve()))
    return sorted(set(paths))


def run_harness(
    harness: Path,
    task: str,
    package: str,
    device: str,
    retries: int,
    sdk: str,
    settings: dict[str, Any],
) -> HarnessRunResult:
    """隔离运行壳并重试真实断言；环境失败立即停止且不得修目标代码。"""
    env = os.environ.copy()
    env["JOURNEYS_CUSTOM_APP_ID"] = package
    env["ANDROID_SERIAL"] = device
    env["ORG_GRADLE_PROJECT_org.gradle.configuration-cache"] = "false"
    # 使用 Skill 外的专用缓存，既隔离旧 ~/.gradle/init.d，也避免生成物撑大 Skill 目录。
    env["GRADLE_USER_HOME"] = str(resolve_harness_gradle_user_home(harness))
    env[JOURNEY_BUILD_ROOT_ENV] = str(resolve_harness_build_root(harness))
    env["ANDROID_HOME"] = sdk
    env["ANDROID_SDK_ROOT"] = sdk
    commands: list[list[str]] = []
    failures = 0
    last_output = ""
    started_at = time.time()
    executed_tests = 0
    result_files: list[str] = []

    for attempt in range(1, retries + 1):
        # 每轮先停止旧进程并重新应用显式 Given，避免第二次从第一次失败页面继续。
        force_stop = run(
            ["adb", "-s", device, "shell", "am", "force-stop", package],
            timeout=ADB_TIMEOUT_SECONDS,
        )
        commands.append(force_stop.command)
        if force_stop.returncode != 0:
            return HarnessRunResult(
                HARNESS_FAILED,
                attempt,
                commands,
                collect_screenshots(harness, started_at),
                force_stop.output,
                executed_tests,
                result_files,
            )
        prepared, prepare_commands, prepare_error = apply_precondition(settings, package, device)
        commands.extend(prepare_commands)
        if not prepared:
            return HarnessRunResult(
                HARNESS_FAILED,
                attempt,
                commands,
                collect_screenshots(harness, started_at),
                prepare_error,
                executed_tests,
                result_files,
            )

        attempt_started_at = time.time()
        # 强制重跑，且拒绝 NO-SOURCE/0 tests，避免复用缓存或空任务形成假绿。
        result = run(
            [
                str(harness / "gradlew"),
                "--project-cache-dir",
                str(resolve_harness_project_cache(harness)),
                task,
                "--rerun-tasks",
                "--console=plain",
            ],
            cwd=harness,
            env=env,
            stream=True,
            timeout=GRADLE_TIMEOUT_SECONDS,
        )
        commands.append(result.command)
        last_output = result.output
        structured = collect_structured_results(harness, attempt_started_at)
        executed_tests = structured.executed
        result_files = structured.files
        if result.returncode == 0:
            lowered = result.output.lower()
            if (
                "no-source" in lowered
                or re.search(r"\b0 tests?\b", lowered)
                or structured.executed <= 0
            ):
                message = result.output + "\n未发现本轮结构化测试结果，拒绝判绿"
                return HarnessRunResult(
                    HARNESS_FAILED,
                    attempt,
                    commands,
                    collect_screenshots(harness, started_at),
                    message,
                    structured.executed,
                    structured.files,
                )
            if structured.failures == 0 and structured.errors == 0:
                return HarnessRunResult(
                    PASS,
                    attempt,
                    commands,
                    collect_screenshots(harness, started_at),
                    result.output,
                    structured.executed,
                    structured.files,
                )
        classification = (
            APP_ASSERTION_FAILED
            if structured.executed > 0 and structured.failures > 0 and structured.errors == 0
            else classify_failure(result.output)
        )
        # 环境类失败重试没有意义，也绝不能累积成“应用连续断言失败”。
        if classification != APP_ASSERTION_FAILED:
            return HarnessRunResult(
                classification,
                attempt,
                commands,
                collect_screenshots(harness, started_at),
                result.output,
                structured.executed,
                structured.files,
            )
        failures += 1

    status = APP_ASSERTION_FAILED if failures == retries else HARNESS_FAILED
    return HarnessRunResult(
        status,
        retries,
        commands,
        collect_screenshots(harness, started_at),
        last_output,
        executed_tests,
        result_files,
    )


def write_result(result: JourneyResult, path: Path) -> None:
    """无论成功或降级都输出机器可读 JSON 和便于验收的 Markdown 证据。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(result), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = path.with_suffix(".md")
    journey_lines = "\n".join(f"- `{item}`" for item in result.journey_files) or "- 无"
    screenshot_lines = "\n".join(f"- `{item}`" for item in result.screenshots) or "- 无"
    result_file_lines = "\n".join(f"- `{item}`" for item in result.result_files) or "- 无"
    command_lines = "\n".join(
        f"- `{' '.join(command)}`" for command in result.commands
    ) or "- 无"
    report.write_text(
        "# Journey Harness 执行报告\n\n"
        f"- 状态：`{result.status}`\n"
        f"- 退出码：`{result.exit_code}`\n"
        f"- 设备：`{result.device or '未选择'}`\n"
        f"- applicationId：`{result.package or '未识别'}`\n"
        f"- APK：`{result.apk or '未构建'}`\n"
        f"- Journey task：`{result.task or '未识别'}`\n"
        f"- Journey 文件数：`{len(result.journey_files)}`\n"
        f"- action/step 数：`{result.action_count}`\n"
        f"- 实际执行测试数：`{result.executed_tests}`\n"
        f"- 执行轮次：`{result.attempts}`\n\n"
        "## Journey 文件\n\n"
        f"{journey_lines}\n\n"
        "## 截图证据\n\n"
        f"{screenshot_lines}\n\n"
        "## 结构化测试结果\n\n"
        f"{result_file_lines}\n\n"
        "## 执行命令\n\n"
        f"{command_lines}\n\n"
        "## 说明\n\n"
        f"{result.message}\n",
        encoding="utf-8",
    )
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    print(f"结果文件: {path.resolve()}")
    print(f"机器报告: {report.resolve()}")


def finish(result: JourneyResult, result_path: Path) -> int:
    """落盘报告并输出与状态匹配的 AI 后续动作，返回约定退出码。"""
    if result.status == PASS and result.executed_tests <= 0:
        result.status = HARNESS_FAILED
        result.exit_code = 1
        result.message = f"{result.message}\n实际执行测试数为 0，拒绝判绿"
    write_result(result, result_path)
    if result.status == NO_JOURNEY_FOUND:
        print("👉 AI 指令：根据已确认需求和 BDD 自动生成当前 Journey 用例；仅在业务预期不明确时询问用户。")
    elif result.status in {HARNESS_UNAVAILABLE, HARNESS_FAILED, MALFORMED_JOURNEY}:
        print("👉 壳 Journey 不可用：不要修改目标项目，改用现有仪器测试或人工测试路径。")
    elif result.status == APP_ASSERTION_FAILED:
        print("👉 连续两次真实 UI 断言失败：先判断生产缺陷还是用例问题；修正对应一方后重跑。")
    return result.exit_code


def skip_result(ui_impact: str) -> JourneyResult | None:
    """在接触 SDK、设备和壳项目之前结束不适用的 Journey 测试。"""
    if ui_impact == "none":
        return JourneyResult(SKIPPED_NO_UI, "需求和实际 diff 均无 UI 影响，Journey 不适用", 0)
    if ui_impact == "visual":
        return JourneyResult(
            SKIPPED_VISUAL_ONLY,
            "仅涉及布局、样式或资源等视觉变化；改用截图测试或独立 UI 视觉验收",
            0,
        )
    return None


def main(argv: list[str] | None = None) -> int:
    """按“适用性判断 → 壳预检 → 目标应用准备 → Journey”顺序执行。"""
    parser = argparse.ArgumentParser(description="通过独立 AGP 9 壳执行 Journey UI 测试")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--harness-dir", default=str(DEFAULT_HARNESS))
    parser.add_argument("--module", default=None)
    parser.add_argument("--variant", default=None)
    parser.add_argument("--device", default=None)
    parser.add_argument("--journey-task", default=None)
    parser.add_argument("--journeys-dir", default=None)
    parser.add_argument(
        "--ui-impact",
        choices=("none", "visual", "behavior"),
        required=True,
        help="Journey 适用性：无 UI、纯视觉或 UI 行为/状态流转",
    )
    parser.add_argument("--retries", type=int, default=None)
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args(argv)

    harness = Path(args.harness_dir).expanduser().resolve()
    fallback_result_path = resolve_fallback_result_path(harness)
    config_path = Path(args.config).expanduser().resolve()
    try:
        config = load_config(config_path)
    except (OSError, RuntimeError) as exc:
        return finish(JourneyResult(HARNESS_UNAVAILABLE, str(exc), 1), fallback_result_path)

    result_path = resolve_result_path(config_path, config)
    skipped = skip_result(args.ui_impact)
    if skipped:
        return finish(skipped, result_path)

    testing = config.get("testing", {}) or {}
    if not isinstance(testing, dict):
        return finish(JourneyResult(HARNESS_UNAVAILABLE, "testing 必须是 YAML object", 1), result_path)
    settings = testing.get("journey_harness", {}) or {}
    if not isinstance(settings, dict):
        return finish(
            JourneyResult(HARNESS_UNAVAILABLE, "testing.journey_harness 必须是 YAML object", 1),
            result_path,
        )
    project = resolve_config_paths(config, config_path).project_path
    module = args.module or settings.get("module", "app")
    variant = args.variant or settings.get("variant", "debug")
    try:
        retries = args.retries if args.retries is not None else int(settings.get("retries", 2))
    except (TypeError, ValueError):
        return finish(JourneyResult(HARNESS_UNAVAILABLE, "retries 必须是整数", 1), result_path)
    configured_package = settings.get("app_package_name") or config.get("app_package_name")
    configured_device = args.device or settings.get("device")
    configured_task = args.journey_task or settings.get("task")
    journeys_dir = resolve_journeys_dir(config_path, config, settings, args.journeys_dir)

    # 先校验当前需求用例；缺用例时直接给出隔离目录，不要求 SDK 或设备就绪。
    if retries < 2:
        return finish(JourneyResult(HARNESS_UNAVAILABLE, "retries 必须 >= 2", 1), result_path)
    files, action_count, journey_error = validate_journeys(journeys_dir)
    if journey_error:
        status = NO_JOURNEY_FOUND if not files else MALFORMED_JOURNEY
        message = f"{journey_error}\n用例目录: {journeys_dir}"
        if status == NO_JOURNEY_FOUND:
            message += "\n应由 android-test-and-fix 根据已确认需求和 BDD 自动生成，不要求用户编写 XML"
        return finish(JourneyResult(status, message, 1, journey_files=[str(p) for p in files]), result_path)

    # 用例就绪后再检查壳、SDK、设备和任务，不触碰目标项目源码。
    if not harness.is_dir():
        return finish(JourneyResult(HARNESS_UNAVAILABLE, f"壳项目不存在: {harness}", 1), result_path)
    gradlew = harness / "gradlew"
    if not gradlew.is_file():
        return finish(JourneyResult(HARNESS_UNAVAILABLE, "壳项目缺少 Gradle wrapper", 1), result_path)
    sdk = resolve_android_sdk()
    if not sdk:
        return finish(JourneyResult(HARNESS_UNAVAILABLE, "无法定位 Android SDK", 1), result_path)

    try:
        stage_journeys(files, harness)
    except OSError as exc:
        return finish(JourneyResult(HARNESS_UNAVAILABLE, f"同步 Journey 用例失败: {exc}", 1,
                                    journey_files=[str(p) for p in files],
                                    action_count=action_count), result_path)

    device, device_error = choose_device(configured_device)
    if device_error:
        return finish(JourneyResult(HARNESS_UNAVAILABLE, device_error, 1,
                                    journey_files=[str(p) for p in files], action_count=action_count), result_path)

    task, discovery = discover_journey_task(harness, configured_task, sdk)
    commands = [discovery.command] if discovery else []
    if not task:
        output = discovery.output[-2000:] if discovery else ""
        message = "无法唯一识别 Journey task；请用官方模板生成后在配置中填写 task"
        if output:
            message += f"\n{output}"
        return finish(JourneyResult(HARNESS_UNAVAILABLE, message, 1, device=device,
                                    journey_files=[str(p) for p in files], action_count=action_count,
                                    commands=commands), result_path)

    if args.preflight_only:
        return finish(JourneyResult(PREFLIGHT_PASS, "壳 Journey 预检通过，尚未执行测试", 0, device=device, task=task,
                                    journey_files=[str(p) for p in files], action_count=action_count,
                                    commands=commands), result_path)

    # 预检通过后再准备目标应用，避免壳本身不可用时无意义地构建或安装 APK。
    apk: Path | None = None
    package = configured_package
    if args.skip_build:
        if not package:
            return finish(JourneyResult(HARNESS_UNAVAILABLE,
                                        "--skip-build 必须配置 app_package_name", 1,
                                        device=device, task=task, journey_files=[str(p) for p in files],
                                        action_count=action_count, commands=commands), result_path)
        installed, command = verify_installed(package, device)
        commands.append(command)
        if not installed:
            return finish(JourneyResult(HARNESS_UNAVAILABLE,
                                        f"目标包未安装到设备: {package}", 1,
                                        device=device, package=package, task=task,
                                        journey_files=[str(p) for p in files], action_count=action_count,
                                        commands=commands), result_path)
    else:
        if not project or not project.is_dir():
            return finish(JourneyResult(HARNESS_UNAVAILABLE, f"老项目路径无效: {project}", 1,
                                        device=device, task=task, journey_files=[str(p) for p in files],
                                        action_count=action_count, commands=commands), result_path)
        try:
            apk, build = build_target_apk(project, module, variant)
        except ValueError as exc:
            return finish(JourneyResult(HARNESS_UNAVAILABLE, str(exc), 1, device=device,
                                        task=task, journey_files=[str(p) for p in files],
                                        action_count=action_count, commands=commands), result_path)
        commands.append(build.command)
        if build.returncode != 0 or not apk:
            return finish(JourneyResult(HARNESS_UNAVAILABLE,
                                        f"老项目构建失败或未找到 APK\n{build.output[-2000:]}", 1,
                                        device=device, task=task, journey_files=[str(p) for p in files],
                                        action_count=action_count, commands=commands), result_path)
        # 正式执行以 APK 为准；源码正则无法可靠处理 flavor/applicationIdSuffix。
        detected_package, package_commands = package_from_apk(apk, sdk)
        commands.extend(package_commands)
        package = detected_package or configured_package
        if not package:
            return finish(JourneyResult(HARNESS_UNAVAILABLE,
                                        "无法从 APK 读取 applicationId；请配置 app_package_name", 1,
                                        device=device, apk=str(apk), task=task,
                                        journey_files=[str(p) for p in files], action_count=action_count,
                                        commands=commands), result_path)
        installed, install_commands, install_output = install_and_verify(apk, package, device)
        commands.extend(install_commands)
        if not installed:
            return finish(JourneyResult(HARNESS_UNAVAILABLE,
                                        f"APK 安装或包名校验失败\n{install_output[-2000:]}", 1,
                                        device=device, package=package, apk=str(apk), task=task,
                                        journey_files=[str(p) for p in files], action_count=action_count,
                                        commands=commands), result_path)

    # 最终仅连续 UI 断言失败返回 2；任何壳/设备/构建问题都以 1 安全降级。
    harness_result = run_harness(
        harness, task, package, device, retries, sdk, settings
    )
    commands.extend(harness_result.commands)
    if harness_result.status == PASS:
        message, exit_code = "Journey 已真实执行并通过", 0
    elif harness_result.status == APP_ASSERTION_FAILED:
        message = (
            f"Journey 连续 {harness_result.attempts} 次 UI 断言失败\n"
            f"{harness_result.output[-3000:]}"
        )
        exit_code = 2
    else:
        message = f"壳 Journey 环境或运行器失败\n{harness_result.output[-3000:]}"
        exit_code = 1
    return finish(JourneyResult(
        harness_result.status, message, exit_code, device=device, package=package,
        apk=str(apk) if apk else None, task=task,
        journey_files=[str(p) for p in files], action_count=action_count,
        executed_tests=harness_result.executed_tests,
        attempts=harness_result.attempts,
        screenshots=harness_result.screenshots,
        result_files=harness_result.result_files,
        commands=commands,
    ), result_path)


if __name__ == "__main__":
    sys.exit(main())
