#!/usr/bin/env python3
"""
================================================================================
脚本名称：delivery.py
用    途：Android Delivery Workflow 的三阶段流程与需求修订确认 CLI 编排器。

设计初衷：
为了防止 AI 在长篇 Prompt 中出现“认知过载、幻觉乱改、超时卡死”等问题，
本脚本将整个 Android 交付工作流拆分为离散的 CLI 步骤，并只保存当前需求 Git 基线
与已确认需求快照：
1. `init`: 负责首次需求提炼，或对比最近确认修订汇总中途需求变化并制定 BDD。
2. `check-env`: 负责编码前的环境安全校验、Git 基线与需求起点建立。
3. `confirm-requirement-update`: 负责确认原子义务修订，不修改 Git 基线。
4. `route`: 识别七类工程影响和第二轮条件能力候选，负责编码后的动态审查、
   测试与自修复闭环分发；泄漏和性能仍由 AI 结合需求与真实 diff 终判。

通过输出带 "👉 AI 指令" 的终端文本，强制 AI 采取“走一步看一步”的精准执行策略，
实现媲美高级 Android 开发工程师的稳定性与工程纪律。
================================================================================
"""

from __future__ import annotations

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
    requirement_snapshot_path_for_config,
    resolve_config_paths as resolve_paths,
)
from .git_changes import (  # noqa: E402
    GitInspectionError,
    collect_changed_entries,
    collect_changed_files,
    current_branch,
    write_baseline,
    working_tree_status,
)
from .requirement_snapshot import (  # noqa: E402
    RequirementSnapshotError,
    apply_requirement_revision,
    load_requirement_snapshot,
    load_revision_manifest,
    render_requirement_diff,
    requirement_digest,
    write_requirement_snapshot,
)


SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = SKILL_ROOT / "profiles/local.yaml"
REQUIREMENTS_PATH = SKILL_ROOT / "requirements.txt"


class DeliveryError(RuntimeError):
    """表示已有明确原因、不能继续猜测的流程错误。"""


def parse_args(argv=None):
    """
    解析命令行参数，定义三大生命周期命令和独立需求修订确认命令。
    """
    parser = argparse.ArgumentParser(description="Android Delivery Workflow CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # 阶段一：init (需求分析阶段)
    parser_init = subparsers.add_parser("init", help="读取或刷新需求理解")
    parser_init.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="配置文件路径")

    # 阶段二：check-env (环境与编码准备阶段)
    parser_check = subparsers.add_parser("check-env", help="检查环境并记录需求起点")
    parser_check.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="配置文件路径")

    # 需求确认：只推进需求修订，不改变编码起点 Git 基线。
    parser_confirm = subparsers.add_parser(
        "confirm-requirement-update",
        help="确认需求修订清单并更新当前有效 BDD/Then",
    )
    parser_confirm.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="配置文件路径")
    parser_confirm.add_argument(
        "--revision-file",
        default=None,
        help="需求修订清单；默认 <requirement_dir>/test-cases/requirement-revision.json",
    )

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
    print("把复合 Then 拆成 BDD-001/T1 形式的原子验证义务，并初判 L1/L2/L3/BLOCKED 风险。")
    print("检测到变化时逐项输出 ADDED/CHANGED/REMOVED/UNCHANGED/SUPERSEDED 和确认决策。")
    print("PENDING/CONFLICT 不得推进修订；REJECTED 不进入总需求；删除项必须明确实现处置。")
    print("正文不足时最多一次提出 5 个真正影响实现或验收的问题；不得补写不存在的需求。")
    print("同时输出【最小修改预览】和架构边界卡片：组件/文件、职责、输入、输出、依赖方向、复用点、不修改范围。")
    print("无法确认落点或边界时列为待确认项，不得创建猜测性文件。")
    print("用户确认且 check-env 成功建立基线后，在 <requirement_dir>/test-cases/traceability.md 建立追溯表。")
    print("同时按 requirement-revision.schema.json 物化修订清单，并执行 confirm-requirement-update。")
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


def _restore_local_state(path: Path, previous: bytes | None) -> None:
    """回滚本轮外部状态写入；只恢复 AI 自己管理的基线文件，不触碰目标仓库。"""
    if previous is None:
        path.unlink(missing_ok=True)
        return
    temporary = path.with_suffix(path.suffix + ".rollback")
    temporary.write_bytes(previous)
    temporary.replace(path)


def get_diff_files(baseline_path):
    """只获取当前需求基线后的 Git 变化，避免串行需求互相污染。"""
    return collect_changed_files(Path.cwd(), baseline_path=baseline_path)


def get_diff_changes(baseline_path):
    """获取当前需求基线后的 Git 状态和真实修改片段，供动态路由使用。"""
    return collect_changed_entries(Path.cwd(), baseline_path=baseline_path)


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


def classify_route_impacts(diff_files, project_root=None, route_signals=None):
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
        content = ""
        if route_signals is not None:
            content = route_signals.get(path, "")
        if not content:
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


def classify_conditional_gate_candidates(impacts):
    """把七类工程候选映射到第二轮门禁；泄漏和性能保留给 AI 语义终判。"""
    return {
        "openapi": bool(impacts.get("api")),
        "migration": bool(impacts.get("data")),
        "ui_a11y": bool(impacts.get("ui")),
        "security_privacy": bool(
            impacts.get("api") or impacts.get("data") or impacts.get("system")
        ),
        # 文件名不足以证明生命周期或热路径变化，避免脚本替代业务判断。
        "dynamic_leak": None,
        "performance": None,
    }


def print_route_instructions(skills_to_run):
    """打印路由审查指令，提示 AI 根据实际改动逐个触发对应 Skill。"""
    print("\n---")
    print("👉 AI 指令：逐个调用以下 Skill。发现 P0/P1 或测试失败必须修复并重跑，不得止于报告：")
    for skill in skills_to_run:
        print(f"  - {skill}")
    print("注意：一次只调用一个。修复导致 diff 变化时重新执行 route，直到路由稳定。")
    print("候选分类必须结合已确认需求和真实 diff 复核，不得凭文件名脑补业务变化。")
    print("第二轮条件能力只在候选适用时执行；无真机继续其他门禁，动态能力未验证不得写成通过。")
    print("最终必须执行 android-test-and-fix 全绿门禁；未执行项不得计为通过。")
    print("UI 校验(android-verify-ui)不进自动队列；检测到 UI 变更时提示用户单独执行。")


def cmd_init(args):
    """
    执行 `init`：读取需求；存在已确认快照时补充差异和追溯表，但不触碰 Git 基线。
    防呆设计：严禁 AI 直接编码，强制先确认 BDD 和中途需求增删改。
    """
    config = load_config(args.config)
    paths = resolve_paths(config, args.config)
    project_path = paths.project_path
    requirement_path = paths.requirement_path

    print("=== 初始化需求分析 ===")
    print(f"📌 项目路径: {project_path or '未配置'}")
    print(f"📌 需求文档: {requirement_path or '未配置'}")

    if not requirement_path:
        raise DeliveryError("未配置 requirement_file，无法读取需求正文")
    content = read_requirement(requirement_path)
    print("\n=== 需求正文内容 ===")
    print(content)

    snapshot_path = requirement_snapshot_path_for_config(args.config)
    try:
        snapshot = load_requirement_snapshot(snapshot_path)
    except RequirementSnapshotError as exc:
        raise DeliveryError(str(exc)) from exc
    if snapshot and Path(str(snapshot["requirement_path"])).resolve() == requirement_path.resolve():
        print(
            f"\n📚 当前确认修订: {snapshot['requirement_id']} "
            f"r{snapshot['revision']} ({snapshot['status']})"
        )
        if snapshot["obligations"]:
            print("=== 当前有效原子义务 ===")
            for obligation in snapshot["obligations"]:
                required = "必需" if obligation["required"] else "可选"
                print(f"  - {obligation['id']} [{required}] {obligation['text']}")
        if snapshot["pending_changes"]:
            print("=== 尚未确认的需求变化 ===")
            for change in snapshot["pending_changes"]:
                reason = f": {change.get('reason')}" if change.get("reason") else ""
                print(
                    f"  - {change['id']} {change['change_type']}/"
                    f"{change['decision']}{reason}"
                )
        if snapshot["sha256"] == requirement_digest(content):
            print("\n=== 需求变化 ===")
            print("✅ 当前需求正文与最近确认修订一致。")
        else:
            print("\n=== 需求变化候选 ===")
            print(render_requirement_diff(str(snapshot["content"]), content))
            traceability = paths.requirement_dir / "test-cases" / "traceability.md"
            try:
                if traceability.is_file() and traceability.stat().st_size <= 1024 * 1024:
                    print("\n=== 当前需求追溯表 ===")
                    print(traceability.read_text(encoding="utf-8", errors="replace"))
            except OSError as exc:
                raise DeliveryError(f"当前需求追溯表无法读取: {traceability}: {exc}") from exc
            print("\n👉 AI 指令：把差异与追溯表按业务语义汇总为增改删、替代和逐项确认决策。")
            print("同一需求保留未变化 ID；修改和新增项重新确认，删除项必须选择实现处置。")
            print("只在聊天中出现的变化必须同步到 requirement_file；不得把待定内容写成已确认。")
            print("如果用户明确这是新的串行需求，不沿用旧 ID；确认后由干净工作区上的 check-env 覆盖旧起点。")
            print("Git 基线保持原需求起点不变；只使受影响映射和证据失效，最终门禁仍基于最终代码重跑。")
        revision_file = paths.requirement_dir / "test-cases" / "requirement-revision.json"
        print(f"📄 默认修订清单: {revision_file}")

    print("\n---")
    print_bdd_instruction()


def cmd_check_env(args):
    """
    执行 `check-env`：工作区干净时同时锁定 Git 起点和已确认需求正文。
    防呆设计：任何一份起点证据写入失败都不允许进入编码阶段。
    """
    config = load_config(args.config)
    paths = resolve_paths(config, args.config)
    project_path = paths.project_path
    requirement_path = paths.requirement_path
    target_branch = config.get("branch")

    if not project_path or not os.path.isdir(project_path):
        raise DeliveryError(f"项目路径无效: {project_path}")
    if not requirement_path:
        raise DeliveryError("未配置 requirement_file，无法保存已确认需求快照")
    requirement_content = read_requirement(requirement_path)

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
        previous_baseline = baseline_path.read_bytes() if baseline_path.is_file() else None
    except OSError as exc:
        raise DeliveryError(f"无法备份原 Git 基线: {baseline_path}: {exc}") from exc
    try:
        baseline = write_baseline(project_path, baseline_path)
    except OSError as exc:
        raise DeliveryError(f"无法写入当前需求 Git 基线: {baseline_path}: {exc}") from exc
    try:
        requirement_snapshot = write_requirement_snapshot(
            requirement_snapshot_path_for_config(args.config),
            requirement_path,
            requirement_content,
            requirement_id=baseline["id"],
        )
    except RequirementSnapshotError as exc:
        # 两份起点证据必须一起成功；快照失败时恢复调用前的基线，而不是误删旧需求起点。
        try:
            _restore_local_state(baseline_path, previous_baseline)
        except OSError as restore_exc:
            raise DeliveryError(
                f"{exc}\n同时无法恢复原 Git 基线: {baseline_path}: {restore_exc}"
            ) from restore_exc
        raise DeliveryError(str(exc)) from exc
    print(f"✅ 当前需求 Git 基线: {baseline['head'][:12]} ({baseline['id']})")
    print(f"✅ 需求起点快照: {requirement_snapshot['sha256'][:12]}")
    print(f"✅ 当前需求集合: {requirement_snapshot['requirement_id']} r0")
    revision_file = paths.requirement_dir / "test-cases" / "requirement-revision.json"
    print("👉 AI 指令：先把用户已确认的全部原子 Then 写入需求修订清单，再确认修订。")
    print(f"修订清单: {revision_file}")
    print("未成功执行 confirm-requirement-update 前不得开始编码。")


def cmd_confirm_requirement_update(args):
    """确认需求修订及有效义务集合；有待定或冲突时保留上一确认版本。"""
    config = load_config(args.config)
    paths = resolve_paths(config, args.config)
    requirement_path = paths.requirement_path
    if not requirement_path:
        raise DeliveryError("未配置 requirement_file，无法确认需求修订")
    content = read_requirement(requirement_path)
    revision_file = (
        Path(args.revision_file).expanduser().resolve()
        if args.revision_file
        else (paths.requirement_dir / "test-cases" / "requirement-revision.json").resolve()
    )
    manifest = load_revision_manifest(revision_file)
    snapshot, confirmed = apply_requirement_revision(
        requirement_snapshot_path_for_config(args.config),
        requirement_path,
        content,
        manifest,
    )
    if not confirmed:
        print("⚠️ 需求修订尚未确认，上一确认版本和 Git 基线均保持不变。")
        for change in snapshot["pending_changes"]:
            if change["decision"] in {"PENDING", "CONFLICT"}:
                print(
                    f"  - {change['id']} {change['change_type']}/"
                    f"{change['decision']}: {change.get('reason', '')}"
                )
        print("解决全部 PENDING/CONFLICT 并更新修订清单后重新执行本命令。")
        return 2

    print(
        f"✅ 需求修订已确认: {snapshot['requirement_id']} "
        f"r{snapshot['revision']} ({snapshot['sha256'][:12]})"
    )
    print("✅ 当前有效原子义务:")
    for obligation in snapshot["obligations"]:
        required = "必需" if obligation["required"] else "可选"
        print(f"  - {obligation['id']} [{required}] {obligation['text']}")
    print("✅ Git 基线未修改；后续 route 仍覆盖本需求起点后的全部代码变化。")
    print_environment_rules()
    return 0


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

    changes, warnings = get_diff_changes(baseline_path_for_config(args.config))
    diff_files = [change.path for change in changes]
    print("=== 审查路由分析 ===")

    for warning in warnings:
        print(f"⚠️ {warning}")
    if not diff_files:
        print("⚠️ 未检测到任何代码变更。")
        print("👉 AI 指令：当前需求基线后没有变化；不得把之前需求的 diff 当成本次结果。")
        return

    print("📜 变更文件列表:")
    for change in changes:
        rename = f" <- {change.old_path}" if change.old_path else ""
        print(f"  - [{change.status}] {change.path}{rename}")

    # 路径和内容只生成候选，最终路由必须结合已确认需求和实际 diff。
    impacts = classify_route_impacts(
        diff_files,
        project_root=project_path,
        route_signals={change.path: change.patch for change in changes},
    )
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

    conditional_gates = classify_conditional_gate_candidates(impacts)
    print("\n🔬 第二轮条件能力候选:")
    conditional_labels = {
        "openapi": "OpenAPI 契约",
        "migration": "数据迁移",
        "ui_a11y": "UI/A11y",
        "security_privacy": "安全隐私",
    }
    for gate, label in conditional_labels.items():
        status = "候选适用，交由对应 Skill 终判" if conditional_gates[gate] else "无候选，默认不适用"
        print(f"  - {label}: {status}")
    print("  - 动态泄漏: 由 android-audit-stability 结合需求、生命周期和资源释放语义终判")
    print("  - 性能: 由 android-audit-stability 结合验收指标和性能敏感路径语义终判")
    print("  - 设备降级: 无真机时继续其他门禁；真机专项标未验证，不得冒充通过")

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
        elif args.command == "confirm-requirement-update":
            return cmd_confirm_requirement_update(args)
        elif args.command == "route":
            cmd_route(args)
    except (DeliveryError, GitInspectionError, RequirementSnapshotError) as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
