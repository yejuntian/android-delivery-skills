#!/usr/bin/env python3
"""
================================================================================
脚本名称：delivery.py
用    途：Android Delivery Workflow 的三阶段 CLI 流程编排器。

设计初衷：
为了防止 AI 在长篇 Prompt 中出现“认知过载、幻觉乱改、超时卡死”等问题，
本脚本将整个 Android 交付工作流拆分为离散的 CLI 步骤，并只保存当前需求 Git 基线：
1. `init`: 负责需求提炼与验收标准制定 (BDD)。
2. `check-env`: 负责编码前的环境安全校验与编码后的自动纠错约束。
3. `route`: 识别 UI、接口、数据、系统、构建、架构和测试影响候选，
   负责编码后的动态审查、测试与自修复闭环分发。

通过输出带 "👉 AI 指令" 的终端文本，强制 AI 采取“走一步看一步”的精准执行策略，
实现媲美高级 Android 开发工程师的稳定性与工程纪律。
================================================================================
"""

import argparse
import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

# 直接运行时建立包上下文；IDE 和 `python -m` 始终解析同一个相对导入。
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = "scripts"

from .config_paths import (  # noqa: E402
    baseline_path_for_config,
    resolve_config_paths as resolve_paths,
)
from .git_changes import (  # noqa: E402
    GitInspectionError,
    collect_changed_files,
    current_branch,
    write_baseline,
    working_tree_status,
)


SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = SKILL_ROOT / "profiles/local.yaml"
REQUIREMENTS_PATH = SKILL_ROOT / "requirements.txt"


class DeliveryError(RuntimeError):
    """表示已有明确原因、不能继续猜测的流程错误。"""


def parse_args(argv=None):
    """
    解析命令行参数，定义支持的三大核心生命周期命令。
    """
    parser = argparse.ArgumentParser(description="Android Delivery Workflow CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # 阶段一：init (需求分析阶段)
    parser_init = subparsers.add_parser("init", help="初始化需求理解")
    parser_init.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="配置文件路径")

    # 阶段二：check-env (环境与编码准备阶段)
    parser_check = subparsers.add_parser("check-env", help="检查项目分支和工作区")
    parser_check.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="配置文件路径")

    # 阶段三：route (动态路由审查阶段)
    parser_route = subparsers.add_parser("route", help="分析 diff 并路由到对应的审查 Skill")
    parser_route.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="配置文件路径")

    return parser.parse_args(argv)


def load_config(config_path):
    """读取 YAML 配置；依赖缺失时给出仓库内安装命令。"""
    path = Path(config_path).expanduser().resolve()
    if not path.is_file():
        raise DeliveryError(f"配置文件不存在: {path}")
    try:
        import yaml
    except ImportError as exc:
        raise DeliveryError(
            f"缺少 PyYAML，请执行: python3 -m pip install -r {REQUIREMENTS_PATH}"
        ) from exc
    try:
        config = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise DeliveryError(f"配置文件无法读取: {path}: {exc}") from exc
    if not isinstance(config, dict):
        raise DeliveryError(f"配置根节点必须是 YAML object: {path}")
    return config


def resolve_config_paths(config, config_path):
    """兼容既有调用；实际路径规则统一由 config_paths.py 维护。"""
    paths = resolve_paths(config, config_path)
    return paths.project_path, paths.requirement_path


def _read_docx(path):
    """DOCX 是标准 OOXML 压缩包，直接提取正文，避免额外文档依赖。"""
    try:
        with zipfile.ZipFile(path) as archive:
            root = ET.fromstring(archive.read("word/document.xml"))
    except (OSError, KeyError, zipfile.BadZipFile, ET.ParseError) as exc:
        raise DeliveryError(f"DOCX 文件损坏或结构不受支持: {path}: {exc}") from exc

    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    paragraphs = []
    for paragraph in root.iter(f"{namespace}p"):
        text = "".join(node.text or "" for node in paragraph.iter(f"{namespace}t")).strip()
        if text:
            paragraphs.append(text)
    return "\n".join(paragraphs)


def read_requirement(path):
    """读取 Word/Markdown/TXT；失败时停止，不搜索同名文件、不脑补正文。"""
    path = Path(path)
    if not path.is_file():
        raise DeliveryError(
            f"需求文件不存在: {path}\n"
            "请检查 workspace_root、requirement_dir 和 requirement_file。"
        )

    suffix = path.suffix.lower()
    if suffix in {".md", ".markdown", ".txt"}:
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise DeliveryError(f"需求文本必须是可读的 UTF-8 文件: {path}: {exc}") from exc
    elif suffix == ".docx":
        content = _read_docx(path)
    else:
        raise DeliveryError(
            f"不支持的需求文件格式: {suffix or '(无扩展名)'}。"
            "当前支持 .docx、.md、.markdown、.txt；请转换后重试。"
        )

    if not content.strip():
        raise DeliveryError(f"需求文件未提取到正文: {path}")
    return content.strip()


def print_bdd_instruction():
    """打印 BDD 输出指令，要求 AI 用 Given/When/Then 结构写验收标准。"""
    print("👉 AI 指令：先输出【当前需求理解】及 UI/API/业务/存储/系统能力影响，再输出 BDD 验收标准。")
    print("为需求、场景分配稳定 REQ-### / BDD-###；检查主流程、备选、异常、恢复和非功能场景。")
    print("BDD 使用 Given/When/Then 格式，缺失类别标记待确认或不适用及原因，不得为凑数量脑补。")
    print("  - Given：给定 / 前置条件")
    print("  - When：当 / 操作发生")
    print("  - Then：那么 / 期望结果")
    print("正文不足时最多一次提出 5 个真正影响实现或验收的问题；不得补写不存在的需求。")
    print("同时输出【最小修改预览】和架构边界卡片：组件/文件、职责、输入、输出、依赖方向、复用点、不修改范围。")
    print("无法确认落点或边界时列为待确认项，不得创建猜测性文件。")
    print("用户确认且 check-env 成功建立基线后，在 <requirement_dir>/test-cases/traceability.md 建立追溯表。")
    print("输出完毕后必须停止输出，等待用户确认！不要直接开写代码！")


def print_environment_rules():
    """打印环境检查后的编码约束，提示 AI 开始编码前后的必须行为。"""
    print("\n---")
    print("👉 AI 指令：环境检查完成。你已获准开始编码。")
    print("【强制规约】:")
    print("  1. 动笔前：必须先使用搜索工具主动在项目中检索现有的 Base 类、工具类或类似页面，确保代码风格贴合项目已有架构。")
    print("  2. 最小修改：只改已确认需求直接涉及的范围，复用现有分层，不跨职责塞逻辑或顺手重构。")
    print("  3. 编码后：根据实际模块、variant 和项目已有任务选择 assemble，不得写死 assembleDebug。")
    print("  4. 编译后：根据实际模块、variant 和项目已有任务选择 lint，不得写死 lintDebug。")
    print("  5. 测试左移：按 REQ/BDD 分配 TEST-###；Bug 或可观察行为变化优先先保留 Red，再最小修改转 Green。")
    print("  6. 追溯：同步实现文件、测试、命令和证据；全部已确认需求的映射率必须为 100%。")
    print("  7. 闭环：任一测试、构建或 Lint 失败，定位根因并修改后重跑；同一根因连续 3 轮失败才暂停。")
    print("  8. 新鲜证据：最后一次修复后重新执行全部必需命令，旧轮次通过结果不能作为最终门禁。")
    print("  9. 不得自动提交 Git；只有用户明确要求时才提交。")


def get_diff_files(baseline_path):
    """只获取当前需求基线后的 Git 变化，避免串行需求互相污染。"""
    return collect_changed_files(Path.cwd(), baseline_path=baseline_path)


def _read_route_signal(path):
    """只读取体积合理的文本改动，内容不可读时安全退回路径候选。"""
    text_suffixes = {
        ".gradle", ".gql", ".graphql", ".java", ".json", ".kt", ".kts",
        ".pro", ".properties", ".proto", ".toml", ".xml", ".yaml", ".yml",
    }
    if path.suffix.lower() not in text_suffixes:
        return ""
    try:
        if not path.is_file() or path.stat().st_size > 512 * 1024:
            return ""
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def classify_route_impacts(diff_files, project_root=None):
    """按路径和轻量内容信号生成影响候选；业务结论仍由 AI 结合 diff 复核。"""
    ui_resource_dirs = {
        "layout", "drawable", "values", "navigation", "menu", "font", "color",
        "anim", "animator", "mipmap",
    }
    ui_name = re.compile(r"(?:Activity|Fragment|Adapter|ViewHolder|Screen|Composable|View)$", re.I)
    api_name = re.compile(
        r"(?:Api|Dto|Request|Response|Repository|Endpoint|Mapper|DataSource)$",
        re.I,
    )
    api_segments = {"api", "network", "remote", "dto", "openapi", "swagger"}
    data_name = re.compile(
        r"(?:Dao|Entity|Database|Migration|DataStore|Preferences|Cache|LocalDataSource)$",
        re.I,
    )
    data_segments = {
        "database", "db", "local", "room", "datastore", "preferences", "cache",
        "schema", "schemas", "proto",
    }
    system_name = re.compile(
        r"(?:Service|Receiver|Provider|Worker|WebView|DeepLink|Notification|FileProvider)$",
        re.I,
    )
    architecture_name = re.compile(
        r"(?:Module|Component|Subcomponent|Injector|Binds|Provides)$",
        re.I,
    )
    build_files = {
        "build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts",
        "gradle.properties", "libs.versions.toml", "proguard-rules.pro", "consumer-rules.pro",
    }
    test_name = re.compile(r"(?:Test|Tests|Spec)$", re.I)
    root = Path(project_root) if project_root is not None else Path.cwd()
    impacts = {
        "ui": [],
        "api": [],
        "data": [],
        "system": [],
        "build": [],
        "architecture": [],
        "tests": [],
    }

    def add(category, path):
        """同一类别内去重，同时保留 Git 返回的稳定顺序。"""
        if path not in impacts[category]:
            impacts[category].append(path)

    for path in diff_files:
        normalized = path.replace("\\", "/")
        parts = normalized.split("/")
        lowered_parts = {part.lower() for part in parts if part}
        filename = parts[-1].lower()
        stem = Path(parts[-1]).stem
        suffix = Path(parts[-1]).suffix.lower()
        is_ui = any(
            parts[index - 1].lower() == "res" and part.lower() in ui_resource_dirs
            for index, part in enumerate(parts)
            if index > 0
        ) or bool(lowered_parts & {"ui", "presentation"}) or bool(ui_name.search(stem))
        is_api = (
            bool(lowered_parts & api_segments)
            or bool(api_name.search(stem))
            or suffix in {".graphql", ".gql"}
        )
        is_data = (
            bool(lowered_parts & data_segments)
            or bool(data_name.search(stem))
            or suffix == ".proto"
        )
        is_system = filename == "androidmanifest.xml" or bool(system_name.search(stem))
        is_build = (
            filename in build_files
            or "build-logic" in lowered_parts
            or ("gradle" in lowered_parts and filename.endswith((".gradle", ".kts", ".properties")))
            or filename.startswith(("proguard-", "r8-"))
        )
        is_architecture = (
            is_build
            or bool(lowered_parts & {"di", "impl"})
            or bool(architecture_name.search(stem))
        )
        is_test = (
            bool(lowered_parts & {"test", "androidtest", "testfixtures"})
            or bool(test_name.search(stem))
        )

        # 内容只补充候选，不覆盖路径判断，也不把注解本身解释成业务变化。
        content = _read_route_signal(root / normalized)
        if content:
            is_ui = is_ui or bool(re.search(r"@Composable\b", content))
            is_api = is_api or bool(re.search(
                r"@(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS|HTTP)\b",
                content,
            ))
            is_data = is_data or bool(re.search(
                r"@(Entity|Dao|Database|TypeConverter)\b|\bMigration\s*\(",
                content,
            ))
            is_system = is_system or bool(re.search(
                r"<uses-permission\b|<(service|receiver|provider)\b|\b(registerReceiver|PendingIntent|NotificationManager|WebView)\b",
                content,
                re.I,
            ))
            is_architecture = is_architecture or bool(re.search(
                r"@(Module|InstallIn|Binds|Provides|Component|Subcomponent)\b|\b(api|implementation|compileOnly|runtimeOnly)\s*\(\s*project\(",
                content,
            ))
            is_test = is_test or bool(re.search(r"@(Test|ParameterizedTest|RunWith)\b", content))

        for category, matched in (
            ("ui", is_ui),
            ("api", is_api),
            ("data", is_data),
            ("system", is_system),
            ("build", is_build),
            ("architecture", is_architecture),
            ("tests", is_test),
        ):
            if matched:
                add(category, path)
    return impacts


def classify_route_files(diff_files):
    """兼容原有 UI/API 调用；完整候选由 classify_route_impacts 提供。"""
    impacts = classify_route_impacts(diff_files)
    return impacts["ui"], impacts["api"]


def print_route_instructions(skills_to_run):
    """打印路由审查指令，提示 AI 根据实际改动逐个触发对应 Skill。"""
    print("\n---")
    print("👉 AI 指令：逐个调用以下 Skill。发现 P0/P1 或测试失败必须修复并重跑，不得止于报告：")
    for skill in skills_to_run:
        print(f"  - {skill}")
    print("注意：一次只调用一个。修复导致 diff 变化时重新执行 route，直到路由稳定。")
    print("候选分类必须结合已确认需求和真实 diff 复核，不得凭文件名脑补业务变化。")
    print("最终必须执行 android-test-and-fix 全绿门禁；未执行项不得计为通过。")
    print("UI 校验(android-verify-ui)不进自动队列；检测到 UI 变更时提示用户单独执行。")


def cmd_init(args):
    """
    执行 `init` 命令：读取需求文档并向 AI 抛出提取验收标准的强制约束。
    防呆设计：严禁 AI 直接输出代码，强制采用 BDD (Given/When/Then) 格式。
    """
    config = load_config(args.config)
    project_path, requirement_path = resolve_config_paths(config, args.config)
    baseline_path = baseline_path_for_config(args.config)
    try:
        baseline_path.unlink(missing_ok=True)
    except OSError as exc:
        raise DeliveryError(f"无法清除上一需求 Git 基线: {baseline_path}: {exc}") from exc

    print("=== 初始化需求分析 ===")
    print(f"📌 项目路径: {project_path or '未配置'}")
    print(f"📌 需求文档: {requirement_path or '未配置'}")

    if not requirement_path:
        raise DeliveryError("未配置 requirement_file，无法读取需求正文")
    print("\n=== 需求正文内容 ===")
    print(read_requirement(requirement_path))

    print("\n---")
    print_bdd_instruction()


def cmd_check_env(args):
    """
    执行 `check-env` 命令：在 AI 开始写代码前，锁定操作环境（检查 Git 状态）。
    防呆设计：包含主动检索要求、强制自我纠错要求（自动编译）和 Android CLI 辅助要求。
    """
    config = load_config(args.config)
    project_path, _ = resolve_config_paths(config, args.config)
    target_branch = config.get("branch")

    if not project_path or not os.path.isdir(project_path):
        raise DeliveryError(f"项目路径无效: {project_path}")

    os.chdir(project_path)

    print("=== 环境检查 ===")

    # 分支和工作区事实统一由只读 Git 脚本提供，编排器不直接执行 Git 命令。
    branch = current_branch(project_path)
    print(f"📂 当前分支: {branch}")
    if target_branch and branch != target_branch:
        raise DeliveryError(f"当前分支 ({branch}) 与目标分支 ({target_branch}) 不匹配")
    print("✅ 分支检查通过。")

    status = working_tree_status(project_path)
    if status:
        raise DeliveryError(
            "工作区存在需求开始前的改动，无法建立不串需求的基线。\n"
            f"{status}\n请先自行确认并处理；脚本不会自动 stash、提交或清理。"
        )
    print("✅ 工作区干净。")

    baseline_path = baseline_path_for_config(args.config)
    try:
        baseline = write_baseline(project_path, baseline_path)
    except OSError as exc:
        raise DeliveryError(f"无法写入当前需求 Git 基线: {baseline_path}: {exc}") from exc
    print(f"✅ 当前需求 Git 基线: {baseline['head'][:12]} ({baseline['id']})")

    print_environment_rules()


def cmd_route(args):
    """
    执行 `route` 命令：基于实际的代码改动（Git Diff）动态决定触发哪些专项审查 Skill。
    防呆设计：严格遵循单一职责原则 (SRP)。没碰 UI 就不查 UI，没碰网络就不查 API。
    """
    config = load_config(args.config)
    project_path, _ = resolve_config_paths(config, args.config)

    if not project_path or not os.path.isdir(project_path):
        raise DeliveryError(f"项目路径无效: {project_path}")

    os.chdir(project_path)
    target_branch = config.get("branch")
    branch = current_branch(project_path)
    if target_branch and branch != target_branch:
        raise DeliveryError(f"当前分支 ({branch}) 与目标分支 ({target_branch}) 不匹配")

    diff_files, warnings = get_diff_files(baseline_path_for_config(args.config))
    print("=== 审查路由分析 ===")

    for warning in warnings:
        print(f"⚠️ {warning}")
    if not diff_files:
        print("⚠️ 未检测到任何代码变更。")
        print("👉 AI 指令：当前需求基线后没有变化；不得把之前需求的 diff 当成本次结果。")
        return

    print("📜 变更文件列表:")
    for path in diff_files:
        print(f"  - {path}")

    # 路径和内容只生成候选，最终路由必须结合已确认需求和实际 diff。
    impacts = classify_route_impacts(diff_files, project_root=project_path)
    ui_files = impacts["ui"]
    api_files = impacts["api"]

    print("\n🧭 语义影响候选(不是业务结论):")
    impact_labels = {
        "ui": "UI",
        "api": "接口契约",
        "data": "数据存储",
        "system": "系统能力",
        "build": "构建配置",
        "architecture": "架构依赖",
        "tests": "测试",
    }
    print("  类别 | 状态 | 候选文件")
    for category, label in impact_labels.items():
        candidates = impacts[category]
        status = f"检测到 {len(candidates)} 个" if candidates else "未检测到"
        files = ", ".join(candidates) if candidates else "-"
        print(f"  {label} | {status} | {files}")

    attention = []
    if impacts["data"]:
        attention.append("数据存储：diff/稳定性/测试必须复核 schema、迁移、旧数据和回滚")
    if impacts["system"]:
        attention.append("系统能力：diff/稳定性/测试必须复核权限、生命周期和 Android 版本")
    if impacts["build"]:
        attention.append("构建配置：diff/质量/测试必须复核依赖解析、任务和老项目兼容")
    if impacts["architecture"]:
        attention.append("架构依赖：diff/质量必须复核模块方向、DI 和公共边界")
    if impacts["tests"]:
        attention.append("测试：diff/测试门禁必须复核断言有效性和覆盖映射")
    if attention:
        print("\n⚠️ 强制关注点:")
        for item in attention:
            print(f"  - {item}")

    print("\n🚀 触发的专项审查(按执行顺序):")
    print("\n【核心·业务逻辑层(必须先过,逐个执行)】")
    skills_to_run = ["android-review-diff"]
    print("  1. android-review-diff (默认:审查实际 diff 和影响范围)")

    # 接口候选拥有独立契约 Skill；其他候选进入既有 diff/质量/稳定性/测试职责。
    if api_files:
        skills_to_run.append("android-verify-api-contract")
        print("  2. android-verify-api-contract (检测到接口契约候选)")
    else:
        print("  2. android-verify-api-contract (跳过:无接口契约候选)")

    skills_to_run.extend(["android-review-code-quality", "android-audit-stability", "android-test-and-fix"])
    print("  3. android-review-code-quality (默认:代码质量和架构一致性)")
    print("  4. android-audit-stability (默认:稳定性和兼容性风险)")
    print("  5. android-test-and-fix (必跑:测试、自修复和全绿门禁；Journey 仅适用时执行)")

    # UI 验收依赖设备和设计基准，保持为独立手动闭环。
    print("\n【独立·UI 验收(不进自动队列)】")
    if ui_files:
        print("  6. [建议单独执行] android-verify-ui (检测到 UI 候选，需结合 diff 复核)")
        print("     └─ 只做截图与设计还原；Journey 功能测试由 android-test-and-fix 负责。")
    else:
        print("  6. android-verify-ui (跳过:无 UI 候选)")

    print_route_instructions(skills_to_run)


def main(argv=None):
    """执行命令，并把可预期错误转换成简洁、可操作的提示。"""
    try:
        args = parse_args(argv)
        if args.command == "init":
            cmd_init(args)
        elif args.command == "check-env":
            cmd_check_env(args)
        elif args.command == "route":
            cmd_route(args)
    except (DeliveryError, GitInspectionError) as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
