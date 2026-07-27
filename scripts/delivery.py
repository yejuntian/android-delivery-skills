#!/usr/bin/env python3
"""
================================================================================
脚本名称：delivery.py
用    途：Android Delivery Workflow 的需求、基线、修订与最终路由 CLI 编排器。

设计初衷：
为了防止 AI 在长篇 Prompt 中出现“认知过载、幻觉乱改、超时卡死”等问题，
本脚本将 Android 交付工作流拆分为离散的 CLI 步骤，并只保存当前需求 Git 基线
与已确认需求快照。首次准备、编码后局部迭代和最终交付的阶段选择由 Skill 负责：
1. `init`: 负责首次需求提炼，或对比最近确认修订汇总中途需求变化并制定 BDD。
2. `check-env`: 负责编码前的环境安全校验、Git 基线与需求起点建立。
3. `confirm-requirement-update`: 负责确认原子义务修订，不修改 Git 基线。
4. `confirm-plan`: 负责把用户确认的实施计划和影响半径绑定当前需求修订，不修改业务文件。
5. `route`: 识别七类工程影响和第二轮条件能力候选，保存绑定当前代码的路由快照，
   再负责编码后的动态审查、测试与自修复闭环分发；泄漏和性能仍由 AI 语义终判。

通过输出带 "👉 AI 指令" 的终端文本，强制 AI 采取“走一步看一步”的精准执行策略，
实现媲美高级 Android 开发工程师的稳定性与工程纪律。
================================================================================
"""

from __future__ import annotations

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
    delivery_snapshot_exclusions,
    requirement_snapshot_path_for_config,
    route_impact_path_for_config,
    resolve_config_paths as resolve_paths,
    _md_filename_for_dir,
)
from .git_changes import (  # noqa: E402
    GitInspectionError,
    collect_changed_entries,
    collect_changed_files,
    current_branch,
    current_delivery_snapshot,
    load_baseline,
    write_baseline,
    working_tree_status,
)
from .implementation_plan import (  # noqa: E402
    ImplementationPlanError,
    confirm_implementation_plan,
    implementation_plan_path,
    validate_plan_confirmation,
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
from .requirement_inputs import requirement_inputs_digest  # noqa: E402
from .route_impact import (  # noqa: E402
    RouteImpactError,
    build_route_impact,
    write_route_impact,
)
from .user_facing_labels import (  # noqa: E402
    CHANGE_TYPE_LABELS,
    DECISION_LABELS,
    GIT_CHANGE_LABELS,
    REMOVAL_DISPOSITION_LABELS,
    SNAPSHOT_STATUS_LABELS,
    ChineseArgumentParser,
    localize_machine_terms,
    revision_label,
)


SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = SKILL_ROOT / "profiles/local.yaml"
REQUIREMENTS_PATH = SKILL_ROOT / "requirements.txt"
class DeliveryError(RuntimeError):
    """表示已有明确原因、不能继续猜测的流程错误。"""


def _is_under_path(file_path: str, prefix: str) -> bool:
    """判断 git porcelain 输出的文件路径是否在指定目录前缀下（document/ 过滤用）。"""
    if not file_path or not prefix:
        return False
    normalized = file_path.replace("\\", "/").strip('"')
    return normalized == prefix or normalized.startswith(prefix.rstrip("/") + "/")


def format_requirement_change(change):
    """把机器稳定枚举转换成面向用户的中文需求变化说明。"""
    change_type = CHANGE_TYPE_LABELS.get(change.get("change_type"), "未知变化")
    decision = DECISION_LABELS.get(change.get("decision"), "未知决定")
    details = []
    disposition = change.get("disposition")
    if disposition:
        details.append(REMOVAL_DISPOSITION_LABELS.get(disposition, "未知删除处置"))
    reason = change.get("reason")
    if reason:
        details.append(str(reason))
    suffix = f"：{'；'.join(details)}" if details else ""
    return f"{change['id']}：{change_type}，{decision}{suffix}"


def summarize_revision_manifest(manifest):
    """把机器修订清单压缩成用户能扫一眼的中文数量摘要。"""
    counts = {"ADDED": 0, "CHANGED": 0, "REMOVED": 0, "SUPERSEDED": 0, "UNCHANGED": 0}
    rejected = 0
    unresolved = 0
    for item in manifest.get("changes", []):
        decision = item.get("decision")
        change_type = item.get("change_type")
        if decision in {"PENDING", "CONFLICT"}:
            unresolved += 1
        elif decision == "REJECTED":
            rejected += 1
        elif change_type in counts:
            counts[change_type] += 1
    parts = []
    labels = {
        "ADDED": "新增",
        "CHANGED": "修改",
        "REMOVED": "删除",
        "SUPERSEDED": "替代",
        "UNCHANGED": "未变化",
    }
    for key in ("ADDED", "CHANGED", "REMOVED", "SUPERSEDED", "UNCHANGED"):
        if counts[key]:
            parts.append(f"{labels[key]} {counts[key]} 项")
    if rejected:
        parts.append(f"已撤回/拒绝 {rejected} 项")
    if unresolved:
        parts.append(f"待确认/冲突 {unresolved} 项")
    return "，".join(parts) if parts else "无语义变化"


def parse_args(argv=None):
    """
    解析命令行参数，定义三大生命周期命令和独立需求修订确认命令。
    """
    parser = ChineseArgumentParser(description="Android 需求交付流程命令")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # 阶段一：init (需求分析阶段)
    parser_init = subparsers.add_parser("init", help="读取或刷新需求理解")
    parser_init.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="配置文件路径")

    # 阶段二：check-env (环境与编码准备阶段)
    parser_check = subparsers.add_parser("check-env", help="检查环境并记录需求起点")
    parser_check.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="配置文件路径")
    parser_check.add_argument(
        "--new-requirement",
        action="store_true",
        help="用户明确开始新的串行需求时，允许替换已有需求起点",
    )

    # 需求确认：只推进需求修订，不改变编码起点 Git 基线。
    parser_confirm = subparsers.add_parser(
        "confirm-requirement-update",
        help="确认需求修订清单并更新当前有效原子验收项",
    )
    parser_confirm.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="配置文件路径")
    parser_confirm.add_argument(
        "--revision-file",
        default=None,
        help="需求修订清单；默认 <requirement_dir>/test-cases/requirement-revision.json",
    )

    # 计划确认：只在用户明确确认已经展示的实施计划后执行。
    parser_confirm_plan = subparsers.add_parser(
        "confirm-plan",
        help="确认实施计划并生成绑定当前需求的机器收据",
    )
    parser_confirm_plan.add_argument(
        "--config",
        default=DEFAULT_CONFIG_PATH,
        help="配置文件路径",
    )

    # 阶段三：route (动态路由审查阶段)
    parser_route = subparsers.add_parser("route", help="分析代码改动并调用对应审查能力")
    parser_route.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="配置文件路径")

    # 测试映射：把需求义务结构化绑定到测试用例，需求增量后标记 STALE 由 AI 回填。
    parser_mapping = subparsers.add_parser(
        "init-test-mapping",
        help="为当前已确认义务生成测试映射骨架",
    )
    parser_mapping.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="配置文件路径")
    parser_mapping.add_argument(
        "--validate",
        action="store_true",
        help="只校验已有测试映射，不生成或覆盖骨架",
    )

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
    """打印中文需求验收指令（精简版），机器编号保留但不要求用户理解英文术语。"""
    print("👉 AI 指令：先形成初步需求理解，不要立即编码。")
    print("把复合预期结果拆成 BDD-001/T1 形式的原子验收项；每个功能写用户故事+AC+主流程/异常边界。")
    print("检测到变化时面向用户只展示：新增、修改、删除、未变化。决策只展示：已确认、待确认、已撤回、冲突。")
    print("首次确认前每次补充/修改/删除/纠正，先展示本轮变化摘要，再合并写回 requirement_file，重新 init 读取。")
    print("用户纯确认（不带新变化）才执行 check-env 和 confirm-requirement-update。确认后不得编码，先写实施计划和影响半径等待确认。")
    print("建立 test-cases/traceability.md 追溯表，按 requirement-revision.schema.json 物化修订清单。")
    print("输出完毕必须停止，等待用户确认！")


def print_confirmed_fact_sources(
    requirement_path: Path,
    revision_file: Path,
    traceability_file: Path,
    *,
    action: str,
    plan_path: Path | None = None,
):
    """只展示事实源路径，不把正文、JSON 或追溯表内容塞进聊天。"""
    print("📄 你主要看:")
    print(f"  - 需求文件: {requirement_path}")
    if plan_path is not None:
        print(f"  - 已确认实施计划: {plan_path}")
    print("🤖 AI 执行前必须读取（只展示路径，不展示正文）:")
    print(f"  - 需求修订清单: {revision_file}")
    print(f"  - 追溯表: {traceability_file}")
    sources = "需求修订清单、追溯表和实施计划" if plan_path else "需求修订清单和追溯表"
    print(
        f"👉 AI 指令：{action}前必须重新读取已确认的 requirement_file、{sources}；"
        "确认前旧聊天理解、旧总结或旧方案不得作为执行依据。"
    )


def print_environment_rules():
    """打印通用编码约束，明确局部迭代与最终交付的执行边界。"""
    print("\n---")
    print("👉 AI 指令：实施计划确认完成。你已获准开始编码。")
    print("【事实源】：编码、测试、route 和最终报告前，必须重新读取已确认的 requirement_file、需求修订清单、追溯表、实施计划和影响半径；确认前旧聊天理解、旧总结或旧方案不得作为执行依据。")
    print("【强制规约】:")
    print("  1. 动笔前：必须先使用搜索工具主动在项目中检索现有的 Base 类、工具类或类似页面，确保代码风格贴合项目已有架构。")
    print("  2. 最小修改：只改已确认需求直接涉及的范围，复用现有分层，不跨职责塞逻辑或顺手重构。")
    print("  3. 局部迭代：编码后的完善、修改、删除或修复只运行受影响测试和必要编译，不自动 route 或全量审查。")
    print("  4. 需求变化：只有业务行为、边界或验收结果变化时才修订需求；确认后仍回到局部迭代。")
    print("  5. 测试左移：按 REQ/BDD 分配 TEST-###；缺陷或可观察行为变化优先保留能复现失败的测试，再最小修改至通过。")
    print("  6. 最终交付：仅在用户当前或最初明确要求最终检查、完整交付或准备提交时执行 route、assemble、lint 和完整门禁。")
    print("  7. 真实任务：根据实际模块、variant 和项目已有任务选择命令，不得写死 assembleDebug 或 lintDebug。")
    print("  8. 追溯与证据：局部结果只证明本轮范围；最终代码必须重新执行全部必需命令，需求映射率为 100%。")
    print("  9. 闭环：失败时定位根因并重跑受影响项；同一根因连续 3 轮失败才暂停。")
    print(" 10. 计划门禁：需求、实施计划或影响半径变化后，旧计划确认自动失效；重新展示并确认前不得继续受影响编码。")
    print(" 11. 不得自动提交 Git；只有用户明确要求时才提交。")


def _restore_local_state(path: Path, previous: bytes | None) -> None:
    """回滚本轮外部状态写入；只恢复 AI 自己管理的基线文件，不触碰目标仓库。"""
    if previous is None:
        path.unlink(missing_ok=True)
        return
    temporary = path.with_suffix(path.suffix + ".rollback")
    temporary.write_bytes(previous)
    temporary.replace(path)


def _reuse_existing_requirement_start(
    project_path: Path,
    requirement_path: Path,
    requirement_content: str,
    baseline_path: Path,
    snapshot_path: Path,
    *,
    new_requirement: bool,
) -> bool:
    """复用同一需求起点；只有明确的新串行需求才允许覆盖已有状态。"""
    baseline_exists = baseline_path.is_file()
    snapshot_exists = snapshot_path.is_file()
    if new_requirement or (not baseline_exists and not snapshot_exists):
        return False
    if baseline_exists != snapshot_exists:
        raise DeliveryError(
            "当前配置的 Git 基线与需求快照不完整，拒绝自动覆盖。"
            "请先检查外部状态；脚本不会猜测哪一份可以删除。"
        )
    try:
        baseline = load_baseline(project_path, baseline_path)
        snapshot = load_requirement_snapshot(snapshot_path)
    except (GitInspectionError, RequirementSnapshotError) as exc:
        raise DeliveryError(
            f"当前配置已有需求起点但无法安全复用: {exc}\n"
            "确认开始新的串行需求后，才可使用 check-env --new-requirement。"
        ) from exc
    if snapshot is None:
        raise DeliveryError("当前配置的需求快照缺失，拒绝覆盖已有 Git 基线")
    if snapshot["requirement_id"] != baseline["id"]:
        raise DeliveryError(
            "当前配置的 Git 基线与需求快照不属于同一需求，拒绝复用或自动覆盖。"
            "请先检查外部状态；确认开始新的串行需求后，才可使用 "
            "check-env --new-requirement。"
        )
    if Path(str(snapshot["requirement_path"])).resolve() != requirement_path.resolve():
        raise DeliveryError(
            "当前配置仍绑定另一个需求文件，拒绝覆盖正在使用的 Git 基线。"
            "确认上一需求结束后，使用 check-env --new-requirement 开始新的串行需求。"
        )

    print("✅ 检测到当前需求已有起点，本次复用且不重建基线。")
    print(f"✅ 当前需求 Git 基线: {baseline['head'][:12]} ({baseline['id']})")
    snapshot_status = SNAPSHOT_STATUS_LABELS.get(snapshot["status"], "状态暂时无法识别")
    print(f"✅ 当前需求修订: {revision_label(snapshot['revision'])}（{snapshot_status}）")
    content_matches = snapshot["sha256"] == requirement_digest(requirement_content)
    if content_matches:
        print("✅ 当前需求正文与最近确认修订一致。")
    else:
        print("⚠️ 当前需求正文存在变化；请执行 init 和 confirm-requirement-update，Git 基线保持不变。")
    requirement_confirmed = (
        snapshot["status"] == "CONFIRMED"
        and not snapshot["pending_changes"]
        and content_matches
    )
    if requirement_confirmed:
        print(
            "👉 AI 指令：继续当前需求前，先重新读取已确认的 requirement_file、"
            "需求修订清单、追溯表和实施计划，并验证计划确认收据；不得沿用确认前"
            "旧聊天理解，不得重建需求起点或重复完整交付流程。"
        )
    else:
        print(
            "👉 AI 指令：继续完成当前需求确认；未成功执行 "
            "confirm-requirement-update 前不得编码、route 或生成最终结果。"
        )
    return True


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
    print("👉 AI 指令：逐个调用以下 Skill。已确认范围内的 P0/P1 技术问题或测试失败必须修复并重跑：")
    for skill in skills_to_run:
        print(f"  - {skill}")
    print("计划外旧业务影响、需求冲突或业务预期不明确即使是 P0/P1 也必须先询问用户，不得自动修复。")
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

    # 事实源优先用 md：docx 仅作初始输入，init 自动读取 docx 并转写成 <需求名>.md。
    # 以后所有增量、修订、门禁都以 md 为准，不碰 docx（docx 是 OOXML，AI 无法可靠增量编辑）。
    requirement_dir = paths.requirement_dir
    md_name = _md_filename_for_dir(requirement_dir)
    md_path = requirement_dir / md_name
    if requirement_path.suffix.lower() == ".docx" and md_path.is_file():
        print(f"\n💡 检测到 {md_name} 已存在，优先以它为事实源（不再读 docx）。")
        requirement_path = md_path
        paths = resolve_paths({**config, "requirement_file": md_name}, args.config)
        requirement_path = paths.requirement_path
    elif requirement_path.suffix.lower() == ".docx" and not md_path.is_file():
        # 首次：AI 自动读取 docx 正文并转写成 <需求名>.md（事实源切换）。
        docx_content = read_requirement(requirement_path)
        md_path.parent.mkdir(parents=True, exist_ok=True)
        if not docx_content.strip():
            # 图片型 docx 提取不到正文：用模板骨架建空文件，
            # AI 在后续沟通中根据截图/Figma/用户补充逐步填充，不脑补。
            template_path = SKILL_ROOT / "android-implement-and-verify" / "templates" / "requirement.md"
            if template_path.is_file():
                md_path.write_text(template_path.read_text(encoding="utf-8"), encoding="utf-8")
            else:
                md_path.write_text("# <需求标题>\n\n> 来源：图片型 docx，无文本正文，待 AI 后续填充\n\n## 需求说明\n\n（待填充）\n", encoding="utf-8")
            print(f"\n⚠️ 该 docx 是图片型，无法提取正文文字。")
            print(f"⚠️ 已用模板骨架创建 {md_name}，AI 将在后续沟通中根据截图/Figma/用户补充逐步填充。")
            print(f"⚠️ 填充后再次执行 init，流程会读取已填充的 {md_name}。")
        else:
            md_path.write_text(docx_content, encoding="utf-8")
            print(f"\n💡 已自动读取 docx 并转写为 {md_name}（事实源）。")
            print(f"💡 以后所有增量、修订和门禁都以 {md_name} 为准，原 docx 仅作初始记录保留。")
        requirement_path = md_path
        paths = resolve_paths({**config, "requirement_file": md_name}, args.config)
        requirement_path = paths.requirement_path

    content = read_requirement(requirement_path)
    print("\n=== 需求正文内容 ===")
    print(content)

    snapshot_path = requirement_snapshot_path_for_config(args.config)
    try:
        snapshot = load_requirement_snapshot(snapshot_path)
    except RequirementSnapshotError as exc:
        raise DeliveryError(str(exc)) from exc
    if snapshot and Path(str(snapshot["requirement_path"])).resolve() == requirement_path.resolve():
        _print_resume_brief(paths, snapshot)
        print(
            f"\n📚 当前确认修订: {snapshot['requirement_id']} "
            f"{revision_label(snapshot['revision'])} "
            f"({SNAPSHOT_STATUS_LABELS.get(snapshot['status'], '状态未知')})"
        )
        if snapshot["obligations"]:
            print("=== 当前有效原子验收项 ===")
            for obligation in snapshot["obligations"]:
                required = "必需" if obligation["required"] else "可选"
                print(f"  - {obligation['id']} [{required}] {obligation['text']}")
        if snapshot["pending_changes"]:
            print("=== 尚未确认的需求变化 ===")
            for change in snapshot["pending_changes"]:
                print(f"  - {format_requirement_change(change)}")
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
            print("如果用户明确这是新的串行需求，不沿用旧 ID；确认上一需求结束后，在干净工作区执行 check-env --new-requirement 建立新起点。")
            print("Git 基线保持原需求起点不变；只使受影响映射和证据失效，最终门禁仍基于最终代码重跑。")
        revision_file = paths.requirement_dir / "test-cases" / "requirement-revision.json"
        print(f"📄 默认修订清单: {revision_file}")

    _render_resume_guide(paths)
    _print_flow_position(paths)
    print("\n---")
    print_bdd_instruction()


def _print_resume_brief(paths, snapshot) -> None:
    """旧需求续接时，把续接指南摘要直接打印到终端，强制 AI 第一眼进入状态。

    单一职责：只读 snapshot/续接指南/mapping 派生摘要，不改任何状态。目的是让
    AI 执行 init 时被迫看到当前修订/计划/STALE 数/下一步，不靠自觉去读文件。
    """
    from .render_artifacts import _read_json

    revision = snapshot.get("revision", "?")
    status = SNAPSHOT_STATUS_LABELS.get(snapshot.get("status"), "状态未知")
    requirement_dir = getattr(paths, "requirement_dir", None)
    receipt = _read_json(
        Path(requirement_dir) / "test-cases" / "implementation-plan-receipt.json"
        if requirement_dir else None
    ) if requirement_dir else None
    plan_confirmed = bool(receipt and receipt.get("confirmed_at"))
    delivery_result = _read_json(
        Path(requirement_dir) / "test-results" / "delivery-result.json"
        if requirement_dir else None
    ) if requirement_dir else None
    conclusion = (delivery_result or {}).get("conclusion")
    mapping = _read_json(
        getattr(paths, "test_mapping_path", None)
        or (Path(requirement_dir) / "test-cases" / "test-mapping.json")
    ) if requirement_dir else None
    stale = [
        m for m in (mapping or {}).get("mappings", [])
        if m.get("mapping_status") == "STALE"
    ]
    title = Path(requirement_dir).name if requirement_dir else snapshot.get("requirement_id", "")
    last_activity = snapshot.get("confirmed_at") or snapshot.get("created_at") or ""
    print("\n📌 续接旧需求：" + title)
    summary = f"   修订：{revision_label(revision)}（{status}）｜计划：{'已确认' if plan_confirmed else '尚未确认或已失效'}"
    if last_activity:
        summary += f"｜上次活动：{last_activity[:10]}"
    if conclusion:
        summary += f"｜最终结论：{conclusion}"
    print(summary)
    if stale:
        names = "，".join(m.get("obligation_id", "?") for m in stale)
        print(f"   ⏳ {len(stale)} 个测试待回填：{names}")
    if plan_confirmed and not stale:
        print("   下一步：可直接进入编码，或用户要求时最终交付")
    elif plan_confirmed and stale:
        print("   下一步：先回填 STALE 测试（init-test-mapping），再继续")
    else:
        print("   下一步：展示实施计划.md 并 confirm-plan")
    print("   完整状态见：续接指南.md")


def _print_flow_position(paths) -> None:
    """打印当前流程位置（半状态驱动），让 AI 永远知道下一步该执行哪个命令。

    单一职责：根据已存在的事实文件推断五步流程当前位置，只读不写。脚本仍是
    检查点模型，本函数补一个常驻指示器，逼近 codex 状态驱动的体验。
    """
    from .render_artifacts import _read_json, execution_progress_items

    requirement_dir = getattr(paths, "requirement_dir", None)
    snapshot_path = requirement_snapshot_path_for_config(
        getattr(paths, "config_path", None) or DEFAULT_CONFIG_PATH
    )
    try:
        snapshot = load_requirement_snapshot(snapshot_path)
    except RequirementSnapshotError:
        snapshot = None
    receipt = _read_json(
        Path(requirement_dir) / "test-cases" / "implementation-plan-receipt.json"
        if requirement_dir else None
    ) if requirement_dir else None
    mapping = _read_json(
        getattr(paths, "test_mapping_path", None)
        or (Path(requirement_dir) / "test-cases" / "test-mapping.json")
    ) if requirement_dir else None
    delivery_result = _read_json(
        Path(requirement_dir) / "test-results" / "delivery-result.json"
        if requirement_dir else None
    ) if requirement_dir else None
    print("\n🧭 当前流程位置 / 当前执行进度")
    for item in execution_progress_items(snapshot, mapping, receipt, delivery_result):
        print(f"   {item}")


def _render_resume_guide(paths, revision_manifest=None) -> None:
    """刷新续接指南.md 及配套人读影子；传入 manifest 时附本次增量波及清单。

    init 末尾不传 manifest（只反映当前状态）；confirm-requirement-update 成功后
    传入本轮修订清单，让续接指南列出受影响义务及其测试/计划影响半径。
    """
    from .render_artifacts import (
        _read_json,
        render_resume_guide,
        render_revision_md,
        render_test_mapping_md,
        write_resume_guide,
    )
    from .atomic_write import write_text_atomic

    config_path = getattr(paths, "config_path", None) or DEFAULT_CONFIG_PATH
    snapshot_path = requirement_snapshot_path_for_config(config_path)
    try:
        snapshot = load_requirement_snapshot(snapshot_path)
    except RequirementSnapshotError as exc:
        print(f"⚠️ {exc}")
        return
    requirement_dir = getattr(paths, "requirement_dir", None)
    if requirement_dir is None:
        return
    requirement_dir = Path(requirement_dir)
    # 路径优先用 ConfigPaths 属性；测试或旧调用方用 SimpleNamespace 时按 requirement_dir 派生。
    mapping = _read_json(
        getattr(paths, "test_mapping_path", None)
        or (requirement_dir / "test-cases" / "test-mapping.json")
    )
    receipt = _read_json(requirement_dir / "test-cases" / "implementation-plan-receipt.json")
    delivery_result = _read_json(requirement_dir / "test-results" / "delivery-result.json")
    resume_path = getattr(paths, "resume_guide_path", None) or (
        requirement_dir / "续接指南.md"
    )
    title = Path(requirement_dir).name
    try:
        guide = render_resume_guide(
            snapshot, mapping, receipt, delivery_result, title, revision_manifest
        )
        write_resume_guide(Path(resume_path), guide)
        if snapshot is not None:
            write_text_atomic(
                requirement_dir / "test-cases" / "需求修订说明.md",
                render_revision_md(snapshot),
            )
        if mapping is not None and snapshot is not None:
            write_text_atomic(
                requirement_dir / "test-cases" / "测试映射说明.md",
                render_test_mapping_md(mapping, snapshot),
            )
        # P9: traceability.md 不存在时提示 AI 建立（gate 会校验其存在）。
        traceability = requirement_dir / "test-cases" / "traceability.md"
        if not traceability.is_file() and snapshot is not None and snapshot.get("obligations"):
            print(f"⚠️ test-cases/traceability.md 尚未建立，请按追溯表格式建立（gate 会校验每个义务 ID 登记）。")
        print(f"📄 续接指南已刷新: {resume_path}")
    except OSError as exc:
        print(f"⚠️ 续接指南无法写入: {exc}")


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

    # chdir 前先把 config 解析成绝对路径，避免 os.chdir 后对相对 --config 路径重新
    # resolve 时算出不同的状态路径（cwd 漂移导致 init/check-env 状态分裂）。
    resolved_config = Path(args.config).expanduser().resolve()
    os.chdir(project_path)

    print("=== 环境检查 ===")

    # 分支和工作区事实统一由只读 Git 脚本提供，编排器不直接执行 Git 命令。
    branch = current_branch(project_path)
    print(f"📂 当前分支: {branch}")
    if target_branch and branch != target_branch:
        raise DeliveryError(f"当前分支 ({branch}) 与目标分支 ({target_branch}) 不匹配")
    print("✅ 分支检查通过。")

    status = working_tree_status(project_path)
    # document/ 是交付文档（git 跟踪、可 commit），不算代码改动，不阻断 check-env。
    # 只检查代码工作区是否干净，文档随时改不卡流程；防串需求靠代码基线 + document 日期目录隔离。
    requirement_dir_rel = None
    try:
        requirement_dir_rel = paths.requirement_dir.resolve().relative_to(project_path.resolve())
    except ValueError:
        pass
    code_status = status
    if status and requirement_dir_rel:
        # 过滤掉 requirement_dir 下的所有行（文档/状态变化不算代码脏）。
        prefix = str(requirement_dir_rel).replace("\\", "/")
        code_lines = [
            line for line in status.splitlines()
            if not _is_under_path(line.split(maxsplit=1)[-1] if " " in line else "", prefix)
        ]
        code_status = "\n".join(code_lines).strip()
    if code_status:
        raise DeliveryError(
            "代码工作区存在需求开始前的改动，无法建立不串需求的基线。\n"
            f"{code_status}\n请先自行确认并处理；脚本不会自动 stash、提交或清理。\n"
            "（交付文档 document/ 的改动不算代码脏，已自动忽略。）"
        )
    print("✅ 代码工作区干净（交付文档改动已忽略）。")

    baseline_path = baseline_path_for_config(resolved_config)
    snapshot_path = requirement_snapshot_path_for_config(resolved_config)
    if _reuse_existing_requirement_start(
        project_path,
        requirement_path,
        requirement_content,
        baseline_path,
        snapshot_path,
        new_requirement=getattr(args, "new_requirement", False),
    ):
        return
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
            snapshot_path,
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
    print("👉 AI 指令：先把用户已确认的全部原子验收项写入需求修订清单，再确认修订。")
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
                print(f"  - {format_requirement_change(change)}")
        print("解决全部待确认项和冲突项并更新修订清单后，重新执行本命令。")
        return 2

    print(
        f"✅ 需求修订已确认: {snapshot['requirement_id']} "
        f"{revision_label(snapshot['revision'])}"
    )
    print(f"✅ 本轮变化摘要: {summarize_revision_manifest(manifest)}")
    print("✅ Git 基线未修改；后续 route 仍覆盖本需求起点后的全部代码变化。")
    _sync_test_mapping_after_revision(paths, snapshot)
    _render_resume_guide(paths, manifest)
    plan_path = implementation_plan_path(paths.requirement_dir)
    impact_path = getattr(paths, "impact_radius_path", None) or (
        paths.requirement_dir / "test-cases" / "impact-radius.json"
    )
    print("\n📋 进入计划阶段（只读，暂不编码）")
    print("┌─ 实施计划 ─────────────────────────────────────────────┐")
    print(f"│ 写入: {plan_path}")
    print(f"│ 影响半径: {impact_path}")
    print("│ 必含: 实现范围 / 已上线业务影响 / 预计修改文件")
    print("│       / 测试方案 / 影响半径摘要 / 明确不修改范围")
    print("└─ 用户确认后执行 delivery.py confirm-plan ──────────────┘")
    print("\n👉 下一步")
    print("  1. 把实施计划写入上述 md（填 android-implement-and-verify/templates/plan.md 骨架）")
    print("  2. 把影响半径写入上述 JSON（参考 android-implement-and-verify/references/impact-radius.example.json，并按 references/impact-radius.schema.json 生成，覆盖当前需求基线以来的全部语义变化）")
    print("  3. 展示简短摘要给用户，停止等待确认")
    print("  4. 确认后 confirm-plan → init-test-mapping 登记测试 → 编码")
    mapping_path = getattr(paths, "test_mapping_path", None)
    if mapping_path is not None:
        print(
            f"\n👉 确认计划后先执行 delivery.py init-test-mapping 生成测试映射骨架 "
            f"({mapping_path})，为每个义务登记真实 test_ids 并回填 CURRENT。"
        )
        print("需求后续增量时，义务 sha256 变化的旧登记会自动标记 STALE，必须重新登记测试才能通过最终门禁。")
    print_confirmed_fact_sources(
        requirement_path,
        revision_file,
        (paths.requirement_dir / "test-cases" / "traceability.md").resolve(),
        action="拆分测试并生成实施计划和影响半径",
    )
    return 0


def cmd_confirm_plan(args):
    """确认用户已经审阅的实施计划；成功后才输出编码授权与执行约束。"""
    config = load_config(args.config)
    paths = resolve_paths(config, args.config)
    requirement_path = paths.requirement_path
    if not requirement_path:
        raise DeliveryError("未配置 requirement_file，无法确认实施计划")
    content = read_requirement(requirement_path)
    snapshot = load_requirement_snapshot(requirement_snapshot_path_for_config(args.config))
    if snapshot is None:
        raise DeliveryError("尚未建立需求修订，请先执行 check-env 和 confirm-requirement-update")
    if Path(str(snapshot["requirement_path"])).resolve() != requirement_path.resolve():
        raise DeliveryError("当前 requirement_file 与需求修订记录路径不一致")

    receipt, receipt_path = confirm_implementation_plan(snapshot, content, paths.requirement_dir)
    plan_path = implementation_plan_path(paths.requirement_dir)
    print(f"✅ 实施计划已确认: {plan_path}")
    print(f"✅ 影响半径已确认: {receipt['impact_radius_path']}")
    print(f"✅ 计划确认收据: {receipt_path}")
    print("✅ 收据已绑定当前需求修订、需求摘要、计划摘要和影响半径；任一内容变化后自动失效。")
    print_confirmed_fact_sources(
        requirement_path.resolve(),
        (paths.requirement_dir / "test-cases" / "requirement-revision.json").resolve(),
        (paths.requirement_dir / "test-cases" / "traceability.md").resolve(),
        action="编码、测试、route 和最终报告",
        plan_path=plan_path,
    )
    print_environment_rules()
    return 0


def cmd_route(args):
    """
    基于实际 Git diff 路由专项 Skill，并保存最终门禁使用的候选影响快照。

    防呆设计：没碰 UI 就不查 UI，没碰网络就不查 API；代码变化后旧快照失效。
    """
    config = load_config(args.config)
    paths = resolve_paths(config, args.config)
    project_path = paths.project_path

    if not project_path or not os.path.isdir(project_path):
        raise DeliveryError(f"项目路径无效: {project_path}")

    # chdir 前固定绝对 config 路径，避免 cwd 漂移导致状态路径分裂。
    resolved_config = Path(args.config).expanduser().resolve()
    os.chdir(project_path)
    target_branch = config.get("branch")
    branch = current_branch(project_path)
    if target_branch and branch != target_branch:
        raise DeliveryError(f"当前分支 ({branch}) 与目标分支 ({target_branch}) 不匹配")

    baseline_path = baseline_path_for_config(resolved_config)
    changes, warnings = get_diff_changes(baseline_path)
    diff_files = sorted({
        path.replace("\\", "/")
        for change in changes
        for path in (change.old_path, change.path)
        if path
    })
    print("=== 审查路由分析 ===")

    for warning in warnings:
        print(f"⚠️ {warning}")
    # 路径和内容只生成候选，最终路由必须结合已确认需求和实际 diff。
    impacts = classify_route_impacts(
        diff_files,
        project_root=project_path,
        route_signals={change.path: change.patch for change in changes},
    )
    ui_files = impacts["ui"]
    api_files = impacts["api"]
    conditional_gates = classify_conditional_gate_candidates(impacts)

    if not paths.requirement_path or not paths.requirement_path.is_file():
        raise DeliveryError(f"需求文件无效: {paths.requirement_path}")
    requirement_content = read_requirement(paths.requirement_path)
    requirement_sha256 = requirement_digest(requirement_content)
    try:
        requirement_snapshot = load_requirement_snapshot(
            requirement_snapshot_path_for_config(resolved_config)
        )
    except RequirementSnapshotError as exc:
        raise DeliveryError(str(exc)) from exc
    if not requirement_snapshot:
        raise DeliveryError("尚未建立需求修订，请先执行 check-env 和 confirm-requirement-update")
    if requirement_snapshot["status"] != "CONFIRMED" or requirement_snapshot["pending_changes"]:
        raise DeliveryError("需求修订仍有待定或冲突项，不能生成最终路由影响快照")
    if requirement_snapshot["sha256"] != requirement_sha256:
        raise DeliveryError("当前需求正文尚未确认为最新修订，不能生成最终路由影响快照")
    plan_context = validate_plan_confirmation(
        requirement_snapshot,
        requirement_content,
        paths.requirement_dir,
    )
    requirement_inputs_sha256 = requirement_inputs_digest(
        config,
        resolved_config,
        requirement_sha256,
        implementation_plan_sha256=plan_context["implementation_plan_sha256"],
        impact_radius_sha256=plan_context["impact_radius_sha256"],
    )
    print_confirmed_fact_sources(
        paths.requirement_path.resolve(),
        (paths.requirement_dir / "test-cases" / "requirement-revision.json").resolve(),
        (paths.requirement_dir / "test-cases" / "traceability.md").resolve(),
        action="route、专项审查和最终报告",
        plan_path=implementation_plan_path(paths.requirement_dir),
    )

    excluded = delivery_snapshot_exclusions(project_path, paths.requirement_dir)
    try:
        code_snapshot = current_delivery_snapshot(
            project_path,
            baseline_path,
            exclude_paths=excluded,
        )
        route_payload = build_route_impact(
            {
                **code_snapshot,
                "requirement_id": requirement_snapshot["requirement_id"],
                "requirement_revision": requirement_snapshot["revision"],
                "requirement_file_sha256": requirement_sha256,
                "requirement_inputs_sha256": requirement_inputs_sha256,
                **plan_context,
            },
            impacts,
            conditional_gates,
        )
        route_path = route_impact_path_for_config(resolved_config)
        write_route_impact(route_path, route_payload)
    except (GitInspectionError, RouteImpactError) as exc:
        raise DeliveryError(str(exc)) from exc
    print(f"📄 路由影响快照: {route_path}")

    if not diff_files:
        print("⚠️ 未检测到任何代码变更。")
        print("👉 AI 指令：当前需求基线后没有变化；不得把之前需求的 diff 当成本次结果。")
        return

    print("📜 变更文件列表:")
    for change in changes:
        rename = f" <- {change.old_path}" if change.old_path else ""
        change_status = GIT_CHANGE_LABELS.get(change.status, "文件状态暂时无法识别")
        print(f"  - [{change_status}] {change.path}{rename}")

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
    print("  5. android-test-and-fix (必跑:测试、自修复和全绿门禁；界面流程自动化测试仅适用时执行)")

    # UI 验收依赖设备和设计基准，保持为独立手动闭环。
    print("\n【独立·UI 验收(不进自动队列)】")
    if ui_files:
        print("  6. [建议单独执行] android-verify-ui (检测到 UI 候选，需结合 diff 复核)")
        print("     └─ 只做截图与设计还原；界面流程功能测试由 android-test-and-fix 负责。")
    else:
        print("  6. android-verify-ui (跳过:无 UI 候选)")

    print_route_instructions(skills_to_run)


def _sync_test_mapping_after_revision(paths, snapshot) -> None:
    """需求修订推进后，把义务 sha256 已变化的测试登记标记为 STALE。

    机器只负责刷新过期的语义摘要并打标；AI 必须据此重新登记测试并把状态回填
    CURRENT，最终门禁才会放行。这是“需求增量后必须同步测试”的机器兜底。
    """
    from .test_mapping import TestMappingError, mark_stale_after_revision

    mapping_path = getattr(paths, "test_mapping_path", None)
    if mapping_path is None or not Path(mapping_path).is_file():
        return
    try:
        mark_stale_after_revision(Path(mapping_path), snapshot)
    except TestMappingError as exc:
        print(f"⚠️ {exc}")


def cmd_init_test_mapping(args):
    """为当前已确认义务生成测试映射骨架，或校验已有映射。"""
    from .test_mapping import (
        TestMappingError,
        build_initial_mapping,
        load_test_mapping,
        validate_test_mapping,
        _atomic_write,
    )

    config = load_config(args.config)
    paths = resolve_paths(config, args.config)
    resolved_config = Path(args.config).expanduser().resolve()
    snapshot = load_requirement_snapshot(requirement_snapshot_path_for_config(resolved_config))
    if snapshot is None:
        raise DeliveryError("尚未建立需求快照，请先执行 check-env 和 confirm-requirement-update")
    if snapshot["status"] != "CONFIRMED" or not snapshot.get("obligations"):
        raise DeliveryError("当前需求尚未确认原子义务，无法生成测试映射")
    mapping_path = paths.test_mapping_path
    if args.validate:
        payload = load_test_mapping(mapping_path)
        errors = validate_test_mapping(payload, snapshot)
        if errors:
            print("❌ 测试映射未通过校验:", file=sys.stderr)
            for error in errors:
                print(f"- {error}", file=sys.stderr)
            return 1
        print(f"✅ 测试映射有效: {mapping_path}")
        return 0
    existing_mapping = None
    if mapping_path.is_file():
        try:
            from .test_mapping import load_test_mapping
            existing_mapping = load_test_mapping(mapping_path)
        except Exception:
            existing_mapping = None
    payload = build_initial_mapping(snapshot, existing_mapping)
    _atomic_write(mapping_path, payload)
    print(f"✅ 测试映射骨架已生成: {mapping_path}")
    print("👉 AI 指令：为每个义务登记真实测试用例 id，把 mapping_status 回填为 CURRENT。")
    print("义务 sha256 已与当前需求修订绑定；需求再次增量时旧登记会自动标记 STALE。")
    _render_resume_guide(paths)
    return 0


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
        elif args.command == "confirm-plan":
            return cmd_confirm_plan(args)
        elif args.command == "route":
            cmd_route(args)
        elif args.command == "init-test-mapping":
            return cmd_init_test_mapping(args)
    except (
        DeliveryError,
        GitInspectionError,
        ImplementationPlanError,
        RequirementSnapshotError,
    ) as exc:
        print(f"❌ {localize_machine_terms(exc)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
