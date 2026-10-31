#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2026 faruheaisha
# SPDX-License-Identifier: GPL-3.0-only
"""一键安装：默认以单技能内嵌模式安装 writing-loop（含内嵌 engine/），避免双技能触发冲突与常驻膨胀。

用法
  python install.py                       # 自动探测目标，单技能内嵌安装，按需拉取权重，跑全量自测
  python install.py --target ~/.claude/skills
  python install.py --no-weights          # 离线安装，只装代码与规则（扫描与画像立即可用）
  python install.py --standalone-engine   # 可选：额外暴露同级独立的 xiaoyu-chinese-ai-detect 技能
  python install.py --uninstall           # 卸载

目标目录探测顺序：~/.workbuddy/skills、~/.claude/skills、~/.agents/skills、~/.codex/skills
"""
import argparse
import os
import shutil
import subprocess
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE_SRC = os.path.join(HERE, "engine")
SKILL_NAME = "writing-loop"
ENGINE_NAME = "xiaoyu-chinese-ai-detect"
RUNTIMES = [".workbuddy", ".claude", ".agents", ".codex"]

DEV_SKIP_EXACT = {
    "install.py",
    "README.md",
    "tests",
}


def candidates():
    home = os.path.expanduser("~")
    out = [os.path.join(home, r, "skills") for r in RUNTIMES]
    out.append(os.path.join(os.getcwd(), ".claude", "skills"))
    out.append(os.path.join(os.getcwd(), ".agents", "skills"))
    out.append(os.path.join(os.getcwd(), ".codex", "skills"))
    return out


def pick_target(explicit):
    if explicit:
        return os.path.abspath(os.path.expanduser(explicit)), "指定"
    for c in candidates():
        if os.path.isdir(c):
            return c, "已存在"
    for c in candidates():
        try:
            os.makedirs(c, exist_ok=True)
            return c, "新建"
        except Exception:
            continue
    sys.stderr.write("找不到可写的技能目录\n")
    return None, None


def copy_skill(src, dst, extra_skip=(), skip_dev=True):
    shutil.rmtree(dst, ignore_errors=True)
    skip_set = set(extra_skip) | (DEV_SKIP_EXACT if skip_dev else set())

    def _ignore(directory, names):
        is_root = os.path.abspath(directory) == os.path.abspath(src)
        out = set()
        for n in names:
            if n == "__pycache__" or n.endswith((".pyc", ".tmp")):
                out.add(n)
            elif n.startswith(".") or n.startswith("specs_"):
                out.add(n)
            elif is_root and n in skip_set:
                out.add(n)
        return out

    shutil.copytree(src, dst, ignore=_ignore)


def _preserve_legacy_weights(legacy_engine_dst, embedded_engine_dst):
    """若旧版同级独立引擎目录内放有离线权重，迁移至内嵌引擎 assets/ 后再清理。"""
    src_assets = os.path.join(legacy_engine_dst, "assets")
    dst_assets = os.path.join(embedded_engine_dst, "assets")
    if not os.path.isdir(src_assets):
        return
    os.makedirs(dst_assets, exist_ok=True)
    for fn in os.listdir(src_assets):
        if fn.endswith(".pt") or fn == "fp32":
            s_p = os.path.join(src_assets, fn)
            d_p = os.path.join(dst_assets, fn)
            if not os.path.exists(d_p):
                if os.path.isdir(s_p):
                    shutil.copytree(s_p, d_p)
                else:
                    shutil.copy2(s_p, d_p)


def main():
    ap = argparse.ArgumentParser(description="writing-loop 一键安装")
    ap.add_argument("--target", default=None, help="技能目录根，缺省自动探测")
    ap.add_argument("--no-weights", action="store_true", help="不下载检测引擎权重")
    ap.add_argument("--standalone-engine", action="store_true",
                    help="同时安装独立的 xiaoyu-chinese-ai-detect 同级技能（默认内嵌防触发冲突）")
    ap.add_argument("--uninstall", action="store_true", help="卸载")
    a = ap.parse_args()

    target, how = pick_target(a.target)
    if not target:
        return 2
    skill_dst = os.path.join(target, SKILL_NAME)
    engine_dst = os.path.join(target, ENGINE_NAME)

    if a.uninstall:
        for d in (skill_dst, engine_dst):
            if os.path.isdir(d):
                shutil.rmtree(d)
                print("已移除", d)
        return 0

    print("目标目录：%s（%s）" % (target, how))
    # 默认把 engine/ 内嵌在 writing-loop/engine/ 内（保留 SKILL.md.template 后缀，不产生重复技能索引）
    copy_skill(HERE, skill_dst)
    embedded_engine = os.path.join(skill_dst, "engine")
    print("已装 %s（含内嵌检测引擎）" % SKILL_NAME)

    if a.standalone_engine and os.path.isdir(ENGINE_SRC):
        copy_skill(ENGINE_SRC, engine_dst, skip_dev=False)
        tpl = os.path.join(engine_dst, "SKILL.md.template")
        if os.path.isfile(tpl):
            os.replace(tpl, os.path.join(engine_dst, "SKILL.md"))
        print("已额外部署独立技能 %s" % ENGINE_NAME)
    elif os.path.isdir(engine_dst):
        _preserve_legacy_weights(engine_dst, embedded_engine)
        shutil.rmtree(engine_dst, ignore_errors=True)
        print("已收敛旧版同级目录 %s（消除双技能触发碰撞）" % ENGINE_NAME)

    active_engine = engine_dst if (a.standalone_engine and os.path.isdir(engine_dst)) else embedded_engine
    if not a.no_weights:
        dl = os.path.join(active_engine, "scripts", "download.py")
        if os.path.isfile(dl):
            print("检查并按需拉取检测引擎权重……")
            try:
                subprocess.run([sys.executable, dl], cwd=active_engine, check=False)
            except Exception:
                print("权重拉取未完成，可稍后手动执行：python %s" % dl)
        else:
            print("找不到下载脚本，跳过权重")
    else:
        print("已跳过权重下载（章法、扫描与画像立即可用）")

    test = os.path.join(HERE, "tests", "run_tests.py")
    if os.path.isfile(test):
        print("自测：")
        subprocess.run([sys.executable, test], cwd=HERE, check=False)

    print()
    print("完成。常用命令：")
    print("  python \"%s/scripts/kickoff.py\" \"写作主题\" --scene 杂文随笔" % skill_dst)
    print("  python \"%s/scripts/scan.py\" 稿件.md --outline" % skill_dst)
    print("  python \"%s/scripts/loop.py\" 稿件.md" % skill_dst)
    print("  python \"%s/scripts/style_profile.py\" build 你的旧稿目录/ --name self" % skill_dst)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
