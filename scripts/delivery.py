#!/usr/bin/env python3
"""
================================================================================
脚本名称：delivery.py
用    途：Android Delivery Workflow 的核心流程编排器 (CLI 状态机)。

设计初衷：
为了防止 AI 在长篇 Prompt 中出现“认知过载、幻觉乱改、超时卡死”等问题，
本脚本将整个 Android 交付工作流拆分为离散的、由 CLI 驱动的步骤：
1. `init`: 负责需求提炼与验收标准制定 (BDD)。
2. `check-env`: 负责编码前的环境安全校验与编码后的自动纠错约束。
3. `route`: 负责编码后的动态审查、测试与自修复闭环分发。

通过输出带 "👉 AI 指令" 的终端文本，强制 AI 采取“走一步看一步”的精准执行策略，
实现媲美高级 Android 开发工程师的稳定性与工程纪律。
================================================================================
"""

import argparse
import os
import subprocess
import yaml
from pathlib import Path

def parse_args():
    """
    解析命令行参数，定义支持的三大核心生命周期命令。
    """
    parser = argparse.ArgumentParser(description="Android Delivery Workflow CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # 阶段一：init (需求分析阶段)
    parser_init = subparsers.add_parser("init", help="初始化需求理解")
    parser_init.add_argument("--config", default="profiles/local.yaml", help="配置文件路径")
    
    # 阶段二：check-env (环境与编码准备阶段)
    parser_check = subparsers.add_parser("check-env", help="检查项目分支和工作区")
    parser_check.add_argument("--config", default="profiles/local.yaml", help="配置文件路径")
    
    # 阶段三：route (动态路由审查阶段)
    parser_route = subparsers.add_parser("route", help="分析 diff 并路由到对应的审查 Skill")
    parser_route.add_argument("--config", default="profiles/local.yaml", help="配置文件路径")
    
    return parser.parse_args()


def load_config(config_path):
    """
    读取并解析 YAML 格式的项目配置文件。
    """
    path = Path(config_path)
    if not path.exists():
        print(f"❌ 配置文件不存在: {config_path}")
        exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def print_bdd_instruction():
    """打印 BDD 输出指令，要求 AI 用 Given/When/Then 结构写验收标准。"""
    print("👉 AI 指令：请根据以上内容强制使用 BDD (Given/When/Then) 格式输出【测试驱动验收标准】(Acceptance Criteria)。")
    print("  - Given：给定 / 前置条件")
    print("  - When：当 / 操作发生")
    print("  - Then：那么 / 期望结果")
    print("输出完毕后必须停止输出，等待用户确认！不要直接开写代码！")


def print_environment_rules():
    """打印环境检查后的编码约束，提示 AI 开始编码前后的必须行为。"""
    print("\n---")
    print("👉 AI 指令：环境检查完成。你已获准开始编码。")
    print("【强制规约】:")
    print("  1. 动笔前：必须先使用搜索工具主动在项目中检索现有的 Base 类、工具类或类似页面，确保代码风格贴合项目已有架构。")
    print("  2. 编码后（第一步）：必须自行运行 `./gradlew assembleDebug`。编译报错必须自行修复，直到编译通过。")
    print("  3. 编码后（第二步）：编译通过后，必须立即运行 `./gradlew lintDebug`。遇到 Error 级别 Lint 警告必须自行修复，直到 Lint 0 Error 通过。")
    print("  4. 测试左移：按已确认 BDD 生成可执行测试，不得只保留 Given/When/Then 文本。")
    print("  5. 闭环：任一测试、构建或 Lint 失败，定位根因并修改后重跑；同一根因连续 3 轮失败才暂停。")
    print("  6. 不得自动提交 Git；只有用户明确要求时才提交。")


def get_diff_files():
    """获取当前 Git 工作区相对于 HEAD 的变更文件列表，用于动态审查路由判断。"""
    try:
        diff_files = subprocess.check_output(["git", "diff", "HEAD", "--name-only"]).decode().strip().split('\n')
        return [f for f in diff_files if f.strip()]
    except subprocess.CalledProcessError:
        print("❌ 无法获取 git diff")
        exit(1)


def print_route_instructions(skills_to_run):
    """打印路由审查指令，提示 AI 根据实际改动逐个触发对应 Skill。"""
    print("\n---")
    print("👉 AI 指令：逐个调用以下 Skill。发现 P0/P1 或测试失败必须修复并重跑，不得止于报告：")
    for s in skills_to_run:
        print(f"  - {s}")
    print("注意：一次只调用一个。修复导致 diff 变化时重新执行 route，直到路由稳定。")
    print("最终必须执行 android-test-and-fix 全绿门禁；未执行项不得计为通过。")
    print("UI 校验(android-verify-ui)在存在 UI 变更且具备验证条件时作为最后一项执行。")


def cmd_init(args):
    """
    执行 `init` 命令：读取需求文档并向 AI 抛出提取验收标准的强制约束。
    防呆设计：严禁 AI 直接输出代码，强制采用 BDD (Given/When/Then) 格式。
    """
    config = load_config(args.config)
    project_path = config.get("project_path", "")
    req_file = config.get("requirement_file", "")
    
    print("=== 初始化需求分析 ===")
    print(f"📌 项目路径: {project_path}")
    print(f"📌 需求文档: {req_file}")
    
    if req_file and Path(req_file).exists():
        print("\n=== 需求正文内容 ===")
        with open(req_file, "r", encoding="utf-8") as f:
            print(f.read())
    else:
        print("\n⚠️ 需求文档不存在或未指定。")
        
    print("\n---")
    print_bdd_instruction()


def cmd_check_env(args):
    """
    执行 `check-env` 命令：在 AI 开始写代码前，锁定操作环境（检查 Git 状态）。
    防呆设计：包含主动检索要求、强制自我纠错要求（自动编译）和 Android CLI 辅助要求。
    """
    config = load_config(args.config)
    project_path = config.get("project_path")
    target_branch = config.get("branch")
    
    if not project_path or not os.path.isdir(project_path):
        print(f"❌ 项目路径无效: {project_path}")
        exit(1)
        
    os.chdir(project_path)
    
    print("=== 环境检查 ===")
    
    # 检查当前 Git 分支是否符合要求（防误切分支）
    try:
        current_branch = subprocess.check_output(["git", "branch", "--show-current"]).decode().strip()
        print(f"📂 当前分支: {current_branch}")
        if target_branch and current_branch != target_branch:
            print(f"❌ 警告：当前分支 ({current_branch}) 与目标分支 ({target_branch}) 不匹配！")
            exit(1)
        else:
            print("✅ 分支检查通过。")
    except subprocess.CalledProcessError:
        print("❌ Git 命令执行失败，请确认是否为 Git 仓库。")
        exit(1)

    # 检查工作区是否干净（只提示，不阻断，适合增量开发）
    try:
        status = subprocess.check_output(["git", "status", "--porcelain"]).decode().strip()
        if status:
            print("⚠️ 警告：工作区有未提交的代码！")
            print(status)
        else:
            print("✅ 工作区干净。")
    except subprocess.CalledProcessError:
        pass
        
    print_environment_rules()


def cmd_route(args):
    """
    执行 `route` 命令：基于实际的代码改动（Git Diff）动态决定触发哪些专项审查 Skill。
    防呆设计：严格遵循单一职责原则 (SRP)。没碰 UI 就不查 UI，没碰网络就不查 API。
    """
    config = load_config(args.config)
    project_path = config.get("project_path")
    
    if not project_path or not os.path.isdir(project_path):
        print(f"❌ 项目路径无效: {project_path}")
        exit(1)
        
    os.chdir(project_path)
    
    diff_files = get_diff_files()
    print("=== 审查路由分析 ===")
    
    if not diff_files:
        print("⚠️ 未检测到任何代码变更。")
        print("👉 AI 指令：审查结束，无变动文件。")
        return

    print("📜 变更文件列表:")
    for f in diff_files:
        print(f"  - {f}")
        
    # 基于关键字对变更文件进行分类
    ui_files = [f for f in diff_files if "res/layout" in f or "res/drawable" in f or "res/values" in f or "Activity.kt" in f or "Fragment.kt" in f or "Activity.java" in f or "Fragment.java" in f]
    api_files = [f for f in diff_files if "api" in f.lower() or "dto" in f.lower() or "request" in f.lower() or "response" in f.lower() or "repository" in f.lower()]
    
    print("\n🚀 触发的专项审查(按执行顺序):")
    print("\n【核心·业务逻辑层(必须先过,逐个执行)】")
    skills_to_run = ["android-review-diff"]
    print("  1. android-review-diff (默认:审查实际 diff 和影响范围)")

    # 动态路由：网络接口层变更 —— 业务逻辑核心
    if api_files:
        skills_to_run.append("android-verify-api-contract")
        print("  2. android-verify-api-contract (检测到接口契约变更)")
    else:
        print("  2. android-verify-api-contract (跳过:无接口契约变更)")

    skills_to_run.extend(["android-review-code-quality", "android-audit-stability", "android-test-and-fix"])
    print("  3. android-review-code-quality (默认:代码质量和架构一致性)")
    print("  4. android-audit-stability (默认:稳定性和兼容性风险)")
    print("  5. android-test-and-fix (必跑:测试、自修复和全绿门禁)")

    # 动态路由：UI 层变更 —— 作为最后一步，Skill 内部按环境降级。
    print("\n【最后·UI 验收(检测到 UI 变更时条件触发)】")
    if ui_files:
        skills_to_run.append("android-verify-ui")
        print("  6. [条件必跑] android-verify-ui (检测到 UI 层变更)")
        print("     └─ Skill 内部按设备情况降级(L1/L2/静态)。")
    else:
        print("  6. android-verify-ui (跳过:无 UI 层变更)")

    print_route_instructions(skills_to_run)


if __name__ == "__main__":
    args = parse_args()
    if args.command == "init":
        cmd_init(args)
    elif args.command == "check-env":
        cmd_check_env(args)
    elif args.command == "route":
        cmd_route(args)
