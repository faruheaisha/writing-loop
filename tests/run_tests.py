#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""writing-loop 规则测试。无第三方依赖。

每组测一个整合点，对应 references/闭环.md 的判定纪律：
  A 召回    每条规则至少一个正例被检出
  B 豁免    引号内、白名单内不计数（sepia 白名单 / novel-studio .deslop-whitelist）
  C 分母    结构指标用每百段，不用每千字（lieflat 六次失误第 5 条）
  D 双门    短文按最小命中数加密度双门（oh-story 双门）
  E 拦截    零宽字符直接判违规
  F 撤销    已证伪的指标不得再报
  G 结构    规则表字段完整、正则可编译

用法 python tests/run_tests.py [-v]
退出码 0 全过，1 有失败。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))

import scan  # noqa: E402

VERBOSE = "-v" in sys.argv
PASS, FAIL = [], []


def ids(text, wl=None, prof=None):
    return {i["id"] for i in scan.scan(text, whitelist=wl, profile=prof)["issues"]}


def ok(group, name, cond, detail=""):
    (PASS if cond else FAIL).append((group, name, detail))
    if VERBOSE or not cond:
        print(("  ok   " if cond else "  FAIL ") + "[%s] %s%s"
              % (group, name, ("  ← " + detail) if detail and not cond else ""))


# ---------------------------------------------------------------- A 召回
RECALL = [
    ("flip", "这不是效率问题，而是制度问题。"),
    ("escalate", "这不仅体现在效率上，更深刻地作用于医患沟通。"),
    ("opener", "在当今社会，一切都在变化。"),
    ("closer", "综上所述，我们应当继续努力。"),
    ("triple", "首先，甲方案成本低。其次，乙方案周期短。最后，丙方案风险小。"),
    ("about_doc", "本文将讨论三个层面的问题。"),
    ("disclaimer", "这一点我无法确定。"),
    ("colon_hint", "核心问题是：制度跟不上技术。关键还在于：执行层面缺人。"),
    ("authority", "研究表明这条路可行。数据显示转化率更高。"),
    ("onesent", "他走了。\n\n她也走了。\n\n灯灭了。\n\n门关上了。\n\n然后呢。\n\n没有人回答。"),
]

for rid, text in RECALL:
    ok("A", "召回 " + rid, rid in ids(text))

# ---------------------------------------------------------------- B 豁免
q = "他说：「这不是钱的问题，而是原则问题。」"
ok("B", "引号内翻案腔不计数", "flip" not in ids(q))
ok("B", "引号内容被遮罩", scan.scan(q)["metrics"]["masked_quotes"] >= 1)

wl_text = "我们要赋能基层。持续赋能。全面赋能。深度赋能。系统赋能。"
ok("B", "白名单内不计", "officialese" not in ids(wl_text, ["赋能"]))
ok("B", "无白名单时计", "officialese" in ids(wl_text, None))

cross = "巴西的LGPD、印度的DPDPA、日本的APPI，三部法都讲了同一件事，只是路径不同，结论一致。"
ok("B", "跨顿号并列不误判层叠的的", "dedede" not in ids(cross))

adverb = "\n\n".join([
    "开头一段，交代背景和前提。",
    "值得注意的是这个方案有代价，但代价可控。",
    "进一步分析可以发现成本主要在后期，前期反而便宜。",
    "同时还要考虑人员培训的时间，这部分常被低估。",
    "此外预算需要留出余量，否则中途会卡住。",
    "从长期看这笔投入是划算的，短期则要咬牙。",
    "总之这件事值得做，但不要低估难度和周期。",
])
ok("B", "状语开头不算零主语", "zero_subj" not in ids(adverb))

# ---------------------------------------------------------------- C 分母
many_heads = "\n\n".join(["## 小节 %d\n这是第 %d 段的内容，用来测试小标题密度。" % (i, i) for i in range(1, 9)])
ok("C", "小标题密集不报错（该规则已撤销）", not ({"headings"} & ids(many_heads)))

with_ref = "\n\n".join(["这是一段正常的段落。"] * 12)
ok("C", "零主语全有回指时不报", "zero_subj" not in ids(with_ref))

# 构造真零主语：12 段，非首段全以无回指评论句开头
bare = ["开始一段，讲背景。"] + ["更重要的是成本，这一点常被忽略。"] * 11
ok("C", "真零主语能报出", "zero_subj" in ids("\n\n".join(bare)))

# ---------------------------------------------------------------- D 双门
short_one = "这是一句话——只有一次破折号。"
ok("D", "短文单次破折号不报", "em_dash" not in ids(short_one))
ok("D", "长文多次破折号要报",
   "em_dash" in ids("正文开始。\n\n" + "这里——有个破折号。那里——也有一个。还有——一个。" * 3))

# ---------------------------------------------------------------- E 拦截
ok("E", "零宽字符判违规", "zero_width" in ids("正常文字\u200b混入零宽。"))
ok("E", "正常文本不判违规", "zero_width" not in ids("正常文字，没有任何隐藏字符。"))

# ---------------------------------------------------------------- F 撤销
uniform = "。".join(["这是一个长度完全相同的句子共十六个字"] * 10) + "。"
ok("F", "句长均匀不再报（配对实测无差异）", "sentence_cv" not in ids(uniform))
ok("F", "被字句不再报", "beisentence" not in ids("方案被否决了。计划被推迟了。预算被压缩了。"))
ok("F", "进行加动词不再报", "progress" not in ids("我们进行了分析工作，也进行了讨论工作。"))

# ---------------------------------------------------------------- G 结构
need = {"id", "tier", "basis", "name", "pat", "per_kilo", "min_hits", "advice", "src"}
bad = [r.get("id") for r in scan.RULES if not need.issubset(r)]
ok("G", "规则字段完整", not bad, str(bad))
try:
    import re
    for r in scan.RULES:
        re.compile(r["pat"])
    ok("G", "全部正则可编译", True)
except re.error as e:
    ok("G", "全部正则可编译", False, str(e))
tiers = {r["tier"] for r in scan.RULES}
ok("G", "分级合法", tiers.issubset({"X", "S", "A", "B"}), str(tiers))
bases = {r["basis"] for r in scan.RULES}
ok("G", "依据分级合法", bases.issubset({"paired", "corpus", "release", "editorial"}), str(bases))
dup = [r["id"] for r in scan.RULES]
ok("G", "规则 id 唯一", len(dup) == len(set(dup)))


# ---------------------------------------------------------------- H 画像
# 个人基线抬高阈值：作者本来就用破折号，不该按通用阈值报
dash_draft = "甲——乙。" * 12 + "丙" * 120          # 约 200 字，破折号 12 处
prof_dash = {"tolerance": 1.5, "s_tolerance": 2.5,
             "rules": {"em_dash": {"mean": 60.0}}, "whitelist": []}
ok("H", "无画像时报破折号", "em_dash" in ids(dash_draft))
ok("H", "有画像时不报（作者本就是这个密度）",
   "em_dash" not in ids(dash_draft, prof=prof_dash))

# S 级也能放宽，但幅度更小
flip_draft = "这不是效率问题，而是制度问题。" + "正文内容。" * 60
prof_flip = {"tolerance": 1.5, "s_tolerance": 2.5,
             "rules": {"flip": {"mean": 3.0}}, "whitelist": []}
ok("H", "无画像时 S 级翻案腔必报", "flip" in ids(flip_draft))
ok("H", "有画像时 S 级按个人基线放宽", "flip" not in ids(flip_draft, prof=prof_flip))

# 画像白名单与命令行白名单合并生效
ok("H", "画像白名单生效",
   "officialese" not in ids("赋能。赋能。赋能。赋能。赋能。" + "正文。" * 80,
                            prof={"whitelist": ["赋能"], "rules": {}}))

# 个人基线低于通用阈值时不放宽，仍用通用
prof_low = {"tolerance": 1.5, "s_tolerance": 2.5,
            "rules": {"em_dash": {"mean": 0.2}}, "whitelist": []}
ok("H", "个人基线更低时不放宽", "em_dash" in ids(dash_draft, prof=prof_low))

# ---------------------------------------------------------------- 汇报
print()
print("通过 %d ／ 失败 %d ／ 合计 %d" % (len(PASS), len(FAIL), len(PASS) + len(FAIL)))
if FAIL:
    print("失败项：")
    for g, n, d in FAIL:
        print("  [%s] %s %s" % (g, n, d))
sys.exit(1 if FAIL else 0)
