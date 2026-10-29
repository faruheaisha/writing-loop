#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一键安装：把本技能与检测引擎装进任一技能的技能目录。

用法
  python install.py                     # 自动探测目标，下载权重，跑自测
  python install.py --target ~/.claude/skills
  python install.py --no-weights        # 只装文件不拉权重（离线可用扫描）
  python install.py --uninstall

目标目录探测顺序：~/.workbuddy/skills、~/.claude/skills、~/.agents/skills、~/.codex/skills
"""
import argparse
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE_SRC = os.path.join(HERE, "engine")
SKILL_NAME = "writing-loop"
ENGINE_NAME = "xiaoyu-chinese-ai-detect"
RUNTIMES = [".workbuddy", ".claude", ".agents", ".codex"]


def candidates():
    home = os.path.expanduser("~")
    out = [os.path.join(home, r, "skills") for r in RUNTIMES]
    out.append(os.path.join(os.getcwd(), ".claude", "skills"))
    out.append(os.path.join(os.getcwd(), ".agents", "skills"))
    return out


def pick_target(explicit):
    if explicit:
        return os.path.abspath(os.path.expanduser(explicit)), "指定"
    for c in candidates():
        if os.path.isdir(c):
            return c, "已存在"
    # 都没有就选第一个可写的
    for c in candidates():
        try:
            os.makedirs(c, exist_ok=True)
            return c, "新建"
        except Exception:
            continue
    sys.stderr.write("找不到可写的技能目录\n")
    return None, None


def copy_skill(src, dst, skip=()):
    shutil.rmtree(dst, ignore_errors=True)

    def _ignore(directory, names):
        out = set()
        for n in names:
            if n in (".git", "__pycache__") or n.endswith(".pyc") or n in skip:
                out.add(n)
        return out

    shutil.copytree(src, dst, ignore=_ignore)


def main():
    ap = argparse.ArgumentParser(description="writing-loop 一键安装")
    ap.add_argument("--target", default=None, help="技能目录根，缺省自动探测")
    ap.add_argument("--no-weights", action="store_true", help="不下载检测引擎权重")
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
    copy_skill(HERE, skill_dst, skip=("engine",))
    print("已装 %s" % SKILL_NAME)
    if os.path.isdir(ENGINE_SRC):
        copy_skill(ENGINE_SRC, engine_dst)
        print("已装 %s" % ENGINE_NAME)

    if not a.no_weights:
        dl = os.path.join(engine_dst, "scripts", "download.py")
        if os.path.isfile(dl):
            print("正在下载检测引擎权重，约需数分钟……")
            try:
                subprocess.run([sys.executable, dl], cwd=engine_dst, check=False)
            except Exception as e:
                print("权重下载出错，可稍后手动执行：python %s" % dl)
        else:
            print("找不到下载脚本，跳过权重")
    else:
        print("已跳过权重下载（检测功能暂不可用，扫描功能正常）")

    test = os.path.join(skill_dst, "tests", "run_tests.py")
    if os.path.isfile(test):
        print("自测：")
        subprocess.run([sys.executable, test], cwd=skill_dst, check=False)

    print()
    print("完成。用法：")
    print("  python %s/scripts/scan.py 稿件.txt" % skill_dst)
    print("  python %s/scripts/loop.py 稿件.txt" % skill_dst)
    print("  python %s/scripts/style_profile.py build 你的旧稿目录/ --name self" % skill_dst)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
