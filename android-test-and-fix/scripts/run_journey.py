#!/usr/bin/env python3
"""通过独立 AGP 9 壳项目，对已安装的旧 Android 应用执行 UI Journey 测试。

主流程：预检 Journey -> 构建并安装目标 APK -> 从 APK 注入真实包名 -> 执行
Journey -> 归因失败 -> 输出 JSON/Markdown 报告。壳项目与目标项目相互隔离，因此
无需升级旧项目的 Gradle 或 AGP。

退出码是自动修复的安全边界：0 表示通过；1 表示壳、设备或环境不可用，只能降级，
不得修改目标应用；2 表示连续两次真实 UI 断言失败，允许进入测试根因分析，但仍需
确认是生产实现缺陷还是用例问题。
"""
from __future__ import annotations

import argparse
import glob
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

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
SUITE_ROOT = SKILL_DIR.parent
DEFAULT_HARNESS = SKILL_DIR / "assets" / "journey-harness"
DEFAULT_CONFIG = SUITE_ROOT / "profiles" / "local.yaml"

PASS = "PASS"
SKIPPED_NO_UI = "SKIPPED_NO_UI"
SKIPPED_VISUAL_ONLY = "SKIPPED_VISUAL_ONLY"
# 只有 APP_ASSERTION_FAILED 允许分析目标实现；它不是“生产代码必然有错”的证明。
APP_ASSERTION_FAILED = "APP_ASSERTION_FAILED"
HARNESS_UNAVAILABLE = "HARNESS_UNAVAILABLE"
HARNESS_FAILED = "HARNESS_FAILED"
MALFORMED_JOURNEY = "MALFORMED_JOURNEY"
NO_JOURNEY_FOUND = "NO_JOURNEY_FOUND"


@dataclass
class CommandResult:
    command: list[str]
    returncode: int
    output: str


@dataclass
class JourneyResult:
    status: str
    message: str
    exit_code: int
    device: str | None = None
    package: str | None = None
    apk: str | None = None
    task: str | None = None
    journey_files: list[str] = field(default_factory=list)
    action_count: int = 0
    attempts: int = 0
    screenshots: list[str] = field(default_factory=list)
    commands: list[list[str]] = field(default_factory=list)


def run(
    cmd: list[str],
    *,
    cwd: Path | str | None = None,
    env: dict[str, str] | None = None,
    stream: bool = False,
) -> CommandResult:
    print(f"$ {' '.join(cmd)}")
    try:
        completed = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
    except FileNotFoundError as exc:
        return CommandResult(cmd, 127, str(exc))
    if stream and completed.stdout:
        print(completed.stdout, end="" if completed.stdout.endswith("\n") else "\n")
    return CommandResult(cmd, completed.returncode, completed.stdout or "")


def load_config(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("缺少 PyYAML，无法读取配置") from exc
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise RuntimeError("配置根节点必须是 YAML object")
    return data


def list_devices() -> list[str]:
    result = run(["adb", "devices"])
    if result.returncode != 0:
        return []
    devices = []
    for line in result.output.splitlines()[1:]:
        fields = line.strip().split("\t")
        if len(fields) == 2 and fields[1] == "device":
            devices.append(fields[0])
    return devices


def choose_device(explicit: str | None) -> tuple[str | None, str | None]:
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
    workspace_value = config.get("workspace_root")
    workspace = Path(str(workspace_value)).expanduser() if workspace_value else config_path.parent
    if not workspace.is_absolute():
        workspace = (config_path.parent / workspace).resolve()

    requirement_value = config.get("requirement_dir")
    requirement = Path(str(requirement_value)).expanduser() if requirement_value else config_path.parent
    if not requirement.is_absolute():
        requirement = workspace / requirement

    configured = explicit or settings.get("cases_dir")
    if not configured:
        return (requirement / "test-cases" / "journeys").resolve()
    source = Path(str(configured)).expanduser()
    return source.resolve() if source.is_absolute() else (requirement / source).resolve()


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
    if not variant or not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", variant):
        raise ValueError(f"非法 variant: {variant!r}")
    return variant[0].upper() + variant[1:]


def find_apk_from_metadata(project: Path, module: str, variant: str) -> Path | None:
    """优先读取 AGP 输出元数据，准确定位指定变体及其实际 APK。"""
    output_root = project / module / "build" / "outputs" / "apk"
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
                if apk.is_file():
                    return apk
    return None


def find_newest_apk(project: Path, module: str, variant: str) -> Path | None:
    metadata_apk = find_apk_from_metadata(project, module, variant)
    if metadata_apk:
        return metadata_apk
    output_root = project / module / "build" / "outputs" / "apk"
    candidates = [
        p for p in output_root.rglob("*.apk")
        if p.is_file() and "androidtest" not in str(p).lower()
    ] if output_root.exists() else []
    variant_candidates = [p for p in candidates if variant.lower() in str(p).lower()]
    selected = variant_candidates or candidates
    return max(selected, key=lambda p: p.stat().st_mtime) if selected else None


def build_target_apk(project: Path, module: str, variant: str) -> tuple[Path | None, CommandResult]:
    # 使用目标项目自己的 wrapper，避免壳项目的 AGP/Gradle 版本侵入旧项目。
    gradlew = project / "gradlew"
    if not gradlew.is_file():
        result = CommandResult([str(gradlew)], 127, "老项目缺少 Gradle wrapper")
        return None, result
    task = f":{module}:assemble{variant_task_suffix(variant)}"
    result = run([str(gradlew), task, "--console=plain"], cwd=project, stream=True)
    return (find_newest_apk(project, module, variant) if result.returncode == 0 else None), result


def resolve_android_sdk() -> str | None:
    configured = os.environ.get("ANDROID_SDK_ROOT") or os.environ.get("ANDROID_HOME")
    if configured and Path(configured).is_dir():
        return configured
    result = run(["android", "info", "sdk"])
    value = result.output.strip().splitlines()
    return value[-1].strip() if result.returncode == 0 and value and Path(value[-1].strip()).is_dir() else None


def sdk_tool(name: str, sdk: str | None = None) -> str | None:
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
        result = run([apkanalyzer, "manifest", "application-id", str(apk)])
        commands.append(result.command)
        value = result.output.strip().splitlines()
        if result.returncode == 0 and value:
            return value[-1].strip(), commands
    aapt = sdk_tool("aapt", sdk)
    if aapt:
        result = run([aapt, "dump", "badging", str(apk)])
        commands.append(result.command)
        match = re.search(r"package: name='([^']+)'", result.output)
        if result.returncode == 0 and match:
            return match.group(1), commands
    return None, commands


def install_and_verify(apk: Path, package: str, device: str) -> tuple[bool, list[list[str]], str]:
    install = run(["adb", "-s", device, "install", "-r", str(apk)], stream=True)
    verify = run(["adb", "-s", device, "shell", "pm", "path", package])
    commands = [install.command, verify.command]
    ok = install.returncode == 0 and verify.returncode == 0 and "package:" in verify.output
    return ok, commands, install.output + verify.output


def verify_installed(package: str, device: str) -> tuple[bool, list[str]]:
    result = run(["adb", "-s", device, "shell", "pm", "path", package])
    return result.returncode == 0 and "package:" in result.output, result.command


def apply_precondition(
    settings: dict[str, Any], package: str, device: str
) -> tuple[bool, list[list[str]], str]:
    # 清数据、授权和定向启动都会改变设备状态，仅执行配置中显式声明的操作。
    precondition = settings.get("precondition", {}) or {}
    commands: list[list[str]] = []
    if precondition.get("clear_app_data", False):
        result = run(["adb", "-s", device, "shell", "pm", "clear", package])
        commands.append(result.command)
        if result.returncode != 0 or "success" not in result.output.lower():
            return False, commands, f"清理应用数据失败: {result.output}"

    for permission in precondition.get("grant_permissions", []) or []:
        result = run(["adb", "-s", device, "shell", "pm", "grant", package, str(permission)])
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
        ])
        commands.append(result.command)
        if result.returncode != 0 or "error" in result.output.lower():
            return False, commands, f"DeepLink 前置失败: {result.output}"
    elif activity:
        result = run([
            "adb", "-s", device, "shell", "am", "start", "-W",
            "-n", f"{package}/{activity}",
        ])
        commands.append(result.command)
        if result.returncode != 0 or "error" in result.output.lower():
            return False, commands, f"Activity 前置失败: {result.output}"
    return True, commands, ""


def discover_journey_task(
    harness: Path, configured: str | None, sdk: str
) -> tuple[str | None, CommandResult | None]:
    # Journey 仍是预览能力，任务名可能随 Android Studio/插件版本变化，不能硬编码猜测。
    if configured:
        return configured, None
    gradlew = harness / "gradlew"
    env = os.environ.copy()
    env["GRADLE_USER_HOME"] = str(harness / ".gradle-user-home")
    env["ANDROID_HOME"] = sdk
    env["ANDROID_SDK_ROOT"] = sdk
    result = run(
        [str(gradlew), ":harness-app:tasks", "--all", "--console=plain"],
        cwd=harness,
        env=env,
    )
    if result.returncode != 0:
        return None, result
    tasks: list[str] = []
    for line in result.output.splitlines():
        task = line.strip().split(" ", 1)[0]
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", task) and "journey" in task.lower():
            tasks.append(f":harness-app:{task}")
    preferred = [t for t in tasks if re.search(r"test.*journey|journey.*test", t, re.IGNORECASE)]
    candidates = preferred or tasks
    return (candidates[0], result) if len(candidates) == 1 else (None, result)


ENVIRONMENT_PATTERNS = (
    "task with path", "could not resolve", "could not compile", "authentication",
    "not authenticated", "sign in to gemini", "gemini authentication", "gemini is unavailable",
    "no connected devices", "no devices", "no-source", "journey xml", "configuration cache",
    "failed to apply plugin", "plugin with id", "sdk location not found",
)
ASSERTION_PATTERNS = (
    "assertionerror", "assertion failed", "journey failed",
    "failed to complete action", "expectation", "verification failed",
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


def collect_screenshots(harness: Path, started_at: float) -> list[str]:
    paths = []
    for pattern in ("**/*.png", "**/*.jpg", "**/*.jpeg", "**/*.webp"):
        for raw in glob.glob(str(harness / "harness-app" / "build" / pattern), recursive=True):
            path = Path(raw)
            if path.is_file() and path.stat().st_mtime >= started_at - 1:
                paths.append(str(path.resolve()))
    return sorted(set(paths))


def run_harness(
    harness: Path,
    task: str,
    package: str,
    device: str,
    retries: int,
    sdk: str,
) -> tuple[str, int, list[list[str]], list[str], str]:
    env = os.environ.copy()
    env["JOURNEYS_CUSTOM_APP_ID"] = package
    env["ANDROID_SERIAL"] = device
    env["ORG_GRADLE_PROJECT_org.gradle.configuration-cache"] = "false"
    # 隔离 Gradle 用户目录，避免旧 ~/.gradle/init.d 脚本和缓存污染 AGP 9 壳项目。
    env["GRADLE_USER_HOME"] = str(harness / ".gradle-user-home")
    env["ANDROID_HOME"] = sdk
    env["ANDROID_SDK_ROOT"] = sdk
    commands: list[list[str]] = []
    failures = 0
    last_output = ""
    started_at = time.time()

    for attempt in range(1, retries + 1):
        # 强制重跑，且拒绝 NO-SOURCE/0 tests，避免复用缓存或空任务形成假绿。
        result = run(
            [str(harness / "gradlew"), task, "--rerun-tasks", "--console=plain"],
            cwd=harness,
            env=env,
            stream=True,
        )
        commands.append(result.command)
        last_output = result.output
        if result.returncode == 0:
            lowered = result.output.lower()
            if "no-source" in lowered or re.search(r"\b0 tests?\b", lowered):
                return HARNESS_FAILED, attempt, commands, collect_screenshots(harness, started_at), result.output
            return PASS, attempt, commands, collect_screenshots(harness, started_at), result.output
        classification = classify_failure(result.output)
        # 环境类失败重试没有意义，也绝不能累积成“应用连续断言失败”。
        if classification != APP_ASSERTION_FAILED:
            return classification, attempt, commands, collect_screenshots(harness, started_at), result.output
        failures += 1

    status = APP_ASSERTION_FAILED if failures == retries else HARNESS_FAILED
    return status, retries, commands, collect_screenshots(harness, started_at), last_output


def write_result(result: JourneyResult, path: Path) -> None:
    """无论成功或降级都输出机器可读 JSON 和便于验收的 Markdown 证据。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(result), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = path.with_suffix(".md")
    journey_lines = "\n".join(f"- `{item}`" for item in result.journey_files) or "- 无"
    screenshot_lines = "\n".join(f"- `{item}`" for item in result.screenshots) or "- 无"
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
        f"- 执行轮次：`{result.attempts}`\n\n"
        "## Journey 文件\n\n"
        f"{journey_lines}\n\n"
        "## 截图证据\n\n"
        f"{screenshot_lines}\n\n"
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


def main() -> int:
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
    args = parser.parse_args()

    harness = Path(args.harness_dir).resolve()
    result_path = harness / "build" / "reports" / "journey-harness" / "result.json"
    skipped = skip_result(args.ui_impact)
    if skipped:
        return finish(skipped, result_path)

    config_path = Path(args.config).resolve()
    try:
        config = load_config(config_path)
    except (OSError, RuntimeError) as exc:
        return finish(JourneyResult(HARNESS_UNAVAILABLE, str(exc), 1), result_path)

    settings = config.get("testing", {}).get("journey_harness", {}) or {}
    project_value = config.get("project_path")
    project = Path(project_value).resolve() if project_value else None
    module = args.module or settings.get("module", "app")
    variant = args.variant or settings.get("variant", "debug")
    retries = args.retries or int(settings.get("retries", 2))
    configured_package = settings.get("app_package_name") or config.get("app_package_name")
    configured_device = args.device or settings.get("device")
    configured_task = args.journey_task or settings.get("task")
    journeys_dir = resolve_journeys_dir(config_path, config, settings, args.journeys_dir)

    # 第一阶段只检查壳、SDK、Journey、设备和任务，不触碰目标项目。
    if retries < 2:
        return finish(JourneyResult(HARNESS_UNAVAILABLE, "retries 必须 >= 2", 1), result_path)
    if not harness.is_dir():
        return finish(JourneyResult(HARNESS_UNAVAILABLE, f"壳项目不存在: {harness}", 1), result_path)
    gradlew = harness / "gradlew"
    if not gradlew.is_file():
        return finish(JourneyResult(HARNESS_UNAVAILABLE, "壳项目缺少 Gradle wrapper", 1), result_path)
    sdk = resolve_android_sdk()
    if not sdk:
        return finish(JourneyResult(HARNESS_UNAVAILABLE, "无法定位 Android SDK", 1), result_path)

    files, action_count, journey_error = validate_journeys(journeys_dir)
    if journey_error:
        status = NO_JOURNEY_FOUND if not files else MALFORMED_JOURNEY
        message = f"{journey_error}\n用例目录: {journeys_dir}"
        if status == NO_JOURNEY_FOUND:
            message += "\n应由 android-test-and-fix 根据已确认需求和 BDD 自动生成，不要求用户编写 XML"
        return finish(JourneyResult(status, message, 1, journey_files=[str(p) for p in files]), result_path)
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
        return finish(JourneyResult(PASS, "壳 Journey 预检通过", 0, device=device, task=task,
                                    journey_files=[str(p) for p in files], action_count=action_count,
                                    commands=commands), result_path)

    # 预检通过后再准备目标应用，避免壳本身不可用时无意义地构建或安装 APK。
    if not project or not project.is_dir():
        return finish(JourneyResult(HARNESS_UNAVAILABLE, f"老项目路径无效: {project_value}", 1,
                                    device=device, task=task, journey_files=[str(p) for p in files],
                                    action_count=action_count, commands=commands), result_path)

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

    precondition_ok, precondition_commands, precondition_error = apply_precondition(
        settings, package, device
    )
    commands.extend(precondition_commands)
    if not precondition_ok:
        return finish(JourneyResult(HARNESS_UNAVAILABLE, precondition_error, 1,
                                    device=device, package=package, apk=str(apk) if apk else None,
                                    task=task, journey_files=[str(p) for p in files],
                                    action_count=action_count, commands=commands), result_path)

    # 最终仅连续 UI 断言失败返回 2；任何壳/设备/构建问题都以 1 安全降级。
    status, attempts, journey_commands, screenshots, output = run_harness(
        harness, task, package, device, retries, sdk
    )
    commands.extend(journey_commands)
    if status == PASS:
        message, exit_code = "Journey 已真实执行并通过", 0
    elif status == APP_ASSERTION_FAILED:
        message, exit_code = f"Journey 连续 {attempts} 次 UI 断言失败\n{output[-3000:]}", 2
    else:
        message, exit_code = f"壳 Journey 环境或运行器失败\n{output[-3000:]}", 1
    return finish(JourneyResult(
        status, message, exit_code, device=device, package=package,
        apk=str(apk) if apk else None, task=task,
        journey_files=[str(p) for p in files], action_count=action_count,
        attempts=attempts, screenshots=screenshots, commands=commands,
    ), result_path)


if __name__ == "__main__":
    sys.exit(main())
