#!/usr/bin/env python3
"""
================================================================================
脚本名称：delivery.py
用    途：作为 android-delivery-workflow 的流程编排器，取代庞大的 Prompt。
================================================================================
"""

import argparse
import os
import subprocess
import yaml
from pathlib import Path

def parse_args():
    parser = argparse.ArgumentParser(description="Android Delivery Workflow CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # init
    parser_init = subparsers.add_parser("init", help="初始化需求理解")
    parser_init.add_argument("--config", default="profiles/local.yaml", help="配置文件路径")
    
    # check-env
    parser_check = subparsers.add_parser("check-env", help="检查项目分支和工作区")
    parser_check.add_argument("--config", default="profiles/local.yaml", help="配置文件路径")
    
    # route
    parser_route = subparsers.add_parser("route", help="分析 diff 并路由到对应的审查 Skill")
    parser_route.add_argument("--config", default="profiles/local.yaml", help="配置文件路径")
    
    return parser.parse_args()


def load_config(config_path):
    path = Path(config_path)
    if not path.exists():
        print(f"❌ 配置文件不存在: {config_path}")
        exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def cmd_init(args):
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
    config = load_config(args.config)
    project_path = config.get("project_path")
    target_branch = config.get("branch")
    
    if not project_path or not os.path.isdir(project_path):
        print(f"❌ 项目路径无效: {project_path}")
        exit(1)
        
    os.chdir(project_path)
    
    print("=== 环境检查 ===")
    
    # 检查分支
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

    # 检查脏工作区 (只提示，不强行阻断)
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
    print("  2. 编码后：必须自行运行 `./gradlew assembleDebug` (或对应构建命令)。如果报错，自己分析日志并修改代码，直到编译成功！")
    print("  3. 结束：编译通过后，输出简短总结，并必须结束当前回合！")


def cmd_route(args):
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
        
    ui_files = [f for f in diff_files if "res/layout" in f or "res/drawable" in f or "res/values" in f or "Activity.kt" in f or "Fragment.kt" in f or "Activity.java" in f or "Fragment.java" in f]
    api_files = [f for f in diff_files if "api" in f.lower() or "dto" in f.lower() or "request" in f.lower() or "response" in f.lower() or "repository" in f.lower()]
    
    print("\n🚀 触发的专项审查：")
    skills_to_run = ["android-change-review", "android-code-quality-review"]
    print("  - android-change-review (默认)")
    print("  - android-code-quality-review (默认)")
    
    if ui_files:
        print("  - [已跳过] android-ui-verify (按配置，UI 校验已延后处理)")
        
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
