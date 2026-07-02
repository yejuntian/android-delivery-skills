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
3. `route`: 负责编码后的动态审查分发 (SRP，基于 Git Diff 决定走哪些 Review)。

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
    print("👉 AI 指令：请根据以上内容强制使用 BDD (Given/When/Then) 格式输出【测试驱动验收标准】(Acceptance Criteria)。输出完毕后必须停止输出，等待用户确认！不要直接开写代码！")


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
        
    print("\n---")
    print("👉 AI 指令：环境检查完成。你已获准开始编码。")
    print("【强制规约】:")
    print("  1. 动笔前：必须先使用搜索工具主动在项目中检索现有的 Base 类、工具类或类似页面，确保代码风格贴合项目“祖传”架构。")
    print("  2. 编码后：必须自行运行 `./gradlew assembleDebug` (或对应构建命令)。如果出现报错或问题，必须强制调用 `android` CLI 相关命令（如查阅文档或诊断环境）进行错误排查和处理。处理完之后继续修改代码，直到编译成功！")
    print("  3. 结束：编译通过后，输出简短总结，并必须结束当前回合！")


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
    
    try:
        # 获取改动文件列表 (含暂存和未暂存)
        diff_files = subprocess.check_output(["git", "diff", "HEAD", "--name-only"]).decode().strip().split('\n')
        diff_files = [f for f in diff_files if f.strip()]
    except subprocess.CalledProcessError:
        print("❌ 无法获取 git diff")
        exit(1)
        
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
    
    print("\n🚀 触发的专项审查：")
    skills_to_run = ["android-change-review", "android-code-quality-review"]
    print("  - android-change-review (默认)")
    print("  - android-code-quality-review (默认)")
    
    # 动态路由：UI 层变更
    if ui_files:
        print("  - [已跳过] android-ui-verify (按配置，UI 校验已延后处理)")
        
    # 动态路由：网络接口层变更
    if api_files:
        skills_to_run.append("android-api-contract-review")
        print("  - android-api-contract-review (检测到接口契约变更)")
        
    print("\n---")
    print(f"👉 AI 指令：代码已编写完毕，请在后续回合中，逐个调用以下 Skill 进行审查：")
    for s in skills_to_run:
        print(f"  - {s}")
    print("注意：一次只调用一个，不要一次性全部执行！未列出的审查项请跳过。")


if __name__ == "__main__":
    args = parse_args()
    if args.command == "init":
        cmd_init(args)
    elif args.command == "check-env":
        cmd_check_env(args)
    elif args.command == "route":
        cmd_route(args)
