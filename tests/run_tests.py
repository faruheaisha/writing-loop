#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2026 faruheaisha
# SPDX-License-Identifier: GPL-3.0-only
"""writing-loop 2.2 全量回归测试套件（128 项断言，零第三方依赖）。

覆盖 15 个验证组：
  A 召回         全部 33 项正则规则的正例检出（33 项）
  B 豁免与对抗   引号豁免、未闭合引号防穿透、翻案腔配对边界、七月流火误用（15 项）
  C 段落构式     zero_subj 对正常名词主语句零误报 + 真零主语召回 + 同构分母（9 项）
  D 双门与单峰   破折号双门 + 塑料死喻单处放行 + 生理情绪单峰放行（4 项）
  E 零宽与BOM    多类隐形/双向控制符拦截、真实总命中计数、首字节 BOM 剥离（6 项）
  F 撤销         已证伪特征（句长 CV、被字句、进行+动词）不报错（3 项）
  G 元数据       规则字段完整性、正则可编译、分级合法、依据合法、id 唯一（5 项）
  H 个人画像     通用 vs 个人阈值放宽、白名单合并、引文脱敏与叙述人称纯净度（8 项）
  I 改写守卫     实词召回率地板、±20% 红线、短句体裁豁免、表格免疫 8 字噪声（7 项）
  J 文风与跨格式 特征唯一、句末切片、整句滚动窗口、--json 输出、docx 实体读取（10 项）
  K 管道健壮性   Windows 敏感字节（发/说）无乱码传输、缺引擎优雅返回 JSON（3 项）
  L 开局组装     10 场景、别名兼容、语域旋钮与微骨架、个人 DNA 联动注入（8 项）
  M 零返工定位   正则与段落同构/零主语精确 [行L] 坐标、首句大纲、loop 行号区间（5 项）
  N Markdown免疫 代码块/表格/链接URL遮罩、带序号小标题复读检出（5 项）
  O 协议与卫生   GPL-3.0 协议校验、engine SHA256 锁定、文档零自违、全仓纯 LF（7 项）

用法：python tests/run_tests.py [-v]
退出码：0 全过，1 有失败。
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT_DIR, "scripts"))

import scan  # noqa: E402
import loop  # noqa: E402
import style_profile as sp  # noqa: E402
import kickoff  # noqa: E402

VERBOSE = "-v" in sys.argv
PASS, FAIL = [], []


def ids(text, wl=None, prof=None):
    return {i["id"] for i in scan.scan(text, whitelist=wl, profile=prof)["issues"]}


def ok(group, name, cond, detail=""):
    (PASS if cond else FAIL).append((group, name, detail))
    if VERBOSE or not cond:
        print(("  ok   " if cond else "  FAIL ") + "[%s] %s%s"
              % (group, name, ("  ← " + detail) if detail and not cond else ""))


def _make_docx(path, paragraphs):
    body = "".join("<w:p><w:r><w:t>%s</w:t></w:r></w:p>" % p for p in paragraphs)
    xml = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
           '<w:body>%s</w:body></w:document>' % body)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("word/document.xml", xml.encode("utf-8"))


# ---------------------------------------------------------------- A 全量规则召回 (33)
RECALL = [
    ("flip", "这不是效率问题，而是制度问题。"),
    ("escalate", "这不仅体现在效率上，更深刻地作用于医患沟通。"),
    ("opener", "在当今社会，一切都在变化。"),
    ("closer", "综上所述，我们应当继续努力。"),
    ("triple", "首先，甲方案成本低。其次，乙方案周期短。最后，丙方案风险小。"),
    ("about_doc", "本文将讨论三个层面的问题。"),
    ("disclaimer", "这一点我无法确定。"),
    ("idiom_misuse", "旧方案早已成为昨日黄花，面对头部对手我们只能望其项背。"),
    ("colon_hint", "核心问题是：制度跟不上技术。关键还在于：执行层面缺人。"),
    ("colon_list", "项目进展情况具体如下：\n- 第一项工作已经完成\n- 第二项仍在推进"),
    ("em_dash", "正文开始。\n\n" + "这里——有个破折号。那里——也有一个。还有——一个。" * 3),
    ("authority", "研究表明这条路可行。数据显示转化率更高。"),
    ("essence", "这件事的本质在于协同，背后的本质是利益机制。"),
    ("only", "这是唯一的选择，也是唯一的出路。"),
    ("either", "我们要么推倒重来要么继续修补。我们要么全盘接受要么彻底决裂。"),
    ("advice", "记住：永远不要轻言放弃。我的建议是各位直接去现场调研。"),
    ("evenif", "就算付出再大代价我们也要做，就算面对再多阻力也绝不退缩。"),
    ("whybecause", "之所以推进缓慢是因为前期调研不够，之所以出现返工是因为标准不统一。"),
    ("frankly", "说实话，这项工作难度极大。说白了，就是资源不足。"),
    ("inflated_sig", "这一突破标志着新时代的开启，深刻见证了历史的巨变。"),
    ("abstract_pass", "持续进行全方位立体化深度协同赋能的核心机制是关键。在经历长达三年全方位深入调研后形成的方法体系在于落地。"),
    ("whenthen", "当系统在夜间完成全量数据更新时，工程师会收到通知。在系统进行高并发压力测试的过程中，必须有人值班。"),
    ("nominal", "我们要提升系统的可靠性、可用性、稳定性与规范化。"),
    ("dedede", "系统的底层的核心的机制的演进逻辑。"),
    ("connector", "此外，方案需要细化。与此同时，资源必须跟上。不仅如此，测试也要同步。从而确保交付。进而降低风险。换言之，不能掉以轻心。"),
    ("softadv", "她微微一笑，淡淡地看着远方，缓缓起身，轻轻关上了门。"),
    ("onesent", "他走了。\n\n她也走了。\n\n灯灭了。\n\n门关上了。\n\n然后呢。\n\n没有人回答。"),
    ("abstract_close", "从这一刻开始，所有人的命运彻底改写。从这一刻开始，历史翻开了新的一页。"),
    ("heading_echo", "### 系统架构设计\n系统架构设计是整个工程的核心基础。"),
    ("officialese", "我们要聚焦主责主业，持续发力，形成合力，狠抓落实。"),
    ("dead_meta", "技术是一把双刃剑，目前暴露的隐患只是冰山一角。"),
    ("somatic_cliche", "他瞳孔骤缩，喉头发紧，嘴里泛起一丝铁锈味。"),
    ("hollow_verb", "新方案实现了对传统瓶颈的突破，业务呈现出稳步增长的态势。"),
]

for rid, text in RECALL:
    ok("A", "召回规则 " + rid, rid in ids(text))

# ---------------------------------------------------------------- B 豁免与对抗边界 (15)
q = "他说：「这不是钱的问题，而是原则问题。」"
ok("B", "引号内翻案腔不计数", "flip" not in ids(q))
ok("B", "引号内容被遮罩", scan.scan(q)["metrics"]["masked_quotes"] >= 1)

long_quote = "引用文献：「" + "这是很长的长篇引文没有任何AI特征但是很长。" * 30 + "这不是A而是B。」"
ok("B", "同段长篇引用(>400字)遮罩豁免", "flip" not in ids(long_quote))

unclosed_ascii_q = '他买了一台 24" 显示器放在工位上。\n\n这不是效率问题，而是制度问题。\n\n老王说 "明天再看" 便关了灯。'
ok("B", "对抗防穿透：单处ASCII直引号不跨行吞噬中段病灶", "flip" in ids(unclosed_ascii_q))

unclosed_cn_q = "第一段漏了后引号：“今天先说到这。\n\n这不是技术问题，而是权力边界问题。\n\n第三段补了另一句对话：“好的。”"
ok("B", "对抗防穿透：未闭合中文引号不跨空行吞噬中段病灶", "flip" in ids(unclosed_cn_q))

ok("B", "正常人类递进否定(不是…更是…)不误判翻案腔",
   "flip" not in ids("这事不是老王经手的，老张更是连听都没听说过。"))
ok("B", "跨逗号长分句翻案腔(不在于…也不在于…而在于…)精准召回",
   "flip" in ids("真正卡住进度的不在于基层人员不肯干活，也不在于设备老化，而在于三套审批表互相打架。"))
ok("B", "七月流火误指酷暑精准召回",
   "idiom_misuse" in ids("工人们顶着七月流火的酷暑坚守在露天矿场。"))

wl_text = "我们要赋能基层。持续赋能。全面赋能。深度赋能。系统赋能。"
ok("B", "白名单内不计", "officialese" not in ids(wl_text, ["赋能"]))
ok("B", "白名单忽略#注释行", "officialese" not in ids(wl_text, ["# 专有词表", "赋能"]))
ok("B", "无白名单时计", "officialese" in ids(wl_text, None))

cross = "巴西的LGPD、印度的DPDPA、日本的APPI，三部法都讲了同一件事，只是路径不同，结论一致。"
ok("B", "跨顿号并列不误判层叠的的", "dedede" not in ids(cross))

lexical_de = "我们的的确确达到了预期目的的标准，合同标的的金额也核对无误。"
ok("B", "词内的确/目的/标的不误判层叠的的", "dedede" not in ids(lexical_de))

cross_line = "第一段只说不仅人手不够\n第二段另起一行写更是预算见底的原因在于排期太紧"
ok("B", "跨换行不误拼递增对比", "escalate" not in ids(cross_line))

cross_either = "甲说要么今天把账结清？\n乙说明天要么再议。丙说要么下周？\n丁说要么算了。"
ok("B", "跨句跨行不误拼要么要么", "either" not in ids(cross_either))

# ---------------------------------------------------------------- C 段落构式与零主语精度 (9)
many_heads = "\n\n".join(["## 小节 %d\n这是第 %d 段的内容，用来测试小标题密度。" % (i, i) for i in range(1, 9)])
ok("C", "小标题密集不报错（已撤销）", not ({"headings"} & ids(many_heads)))

with_ref = "\n\n".join(["这是一段正常的段落。"] * 12)
ok("C", "零主语全有回指时不报", "zero_subj" not in ids(with_ref))

normal_svo = "\n\n".join([
    "第一段交代事情的起因。",
    "张三是组里资历最老的工程师，干了整整十二年。",
    "预算是今年最大的瓶颈，财务部只批了一半额度。",
    "老王需要三天时间把旧冷库的铁锁全部换掉。",
    "服务器在凌晨三点是需要重启维护的，不能硬扛。",
    "这套办法应该能撑过年底的结算高峰期。",
    "车间主任是一位不爱多说话的老钳工。",
])
ok("C", "正常具体名词主语句绝不误报零主语", "zero_subj" not in ids(normal_svo))

adverb = "\n\n".join([
    "开头一段，交代背景和前提。",
    "值得注意的是这个方案有代价，但代价可控。",
    "进一步分析可以发现成本主要在后期，前期反而便宜。",
    "同时还要考虑人员培训的时间，这部分常被低估。",
    "此外预算需要留出余量，否则中途会卡住。",
    "从长期看这笔投入是划算的，短期则要咬牙。",
    "总之这件事值得做，但不要低估难度和周期。",
])
ok("C", "状语开头不算零主语", "zero_subj" not in ids(adverb))

bare_more = ["开始一段，讲背景。"] + ["更重要的是在执行层面落实，这一点常被忽略。"] * 8
ok("C", "更重要的是段首零主语精准召回", "zero_subj" in ids("\n\n".join(bare_more)))

bare_key = ["开始一段，讲背景。"] + ["关键在于制度供给和资源调配。"] * 8
ok("C", "关键在于段首零主语精准召回", "zero_subj" in ids("\n\n".join(bare_key)))

bare_deny = ["开始一段，讲背景。"] + ["不可否认的是，这套机制短期确实省了钱。"] * 8
ok("C", "不可否认的是段首零主语精准召回", "zero_subj" in ids("\n\n".join(bare_deny)))

iso3_paras = "\n\n".join(["甲乙丙丁戊己庚。辛壬癸子丑寅卯。辰巳午未申酉戌。"] * 10)
ok("C", "十段连续三句同构精准召回", "iso3" in ids(iso3_paras))

short_paras = "\n\n".join(["甲乙丙丁戊己庚。辛壬癸子丑寅卯。辰巳午未申酉戌。"] * 4)
ok("C", "不足十段时不虚报段落同构", "iso3" not in ids(short_paras))

# ---------------------------------------------------------------- D 双门与单峰放行 (4)
short_one = "这是一句话——只有一次破折号。"
ok("D", "短文单次破折号不报", "em_dash" not in ids(short_one))
ok("D", "长文多次破折号要报",
   "em_dash" in ids("正文开始。\n\n" + "这里——有个破折号。那里——也有一个。还有——一个。" * 3))
ok("D", "单处塑料死喻放行不误伤",
   "dead_meta" not in ids("目前看到的只是冰山一角。" + "老周把账本翻到最后一页核对电费单。" * 12))
ok("D", "单处生理情绪高峰放行不误伤",
   "somatic_cliche" not in ids("他额头渗出冷汗。" + "随后他把茶碗盖磕了三次才合拢，没吭声。" * 12))

# ---------------------------------------------------------------- E 零宽隐形作弊拦截与 BOM 兼容 (6)
ok("E", "正中零宽字符判违规", "zero_width" in ids("正常文字\u200b混入零宽。"))
ok("E", "双向覆盖符与隐形算子符精准拦截",
   "zero_width" in ids("正常文字\u202e混入方向符") and "zero_width" in ids("正常文字\u2061混入隐形算子"))
zw_six = scan.scan("甲\u200b乙\u200b丙\u200b丁\u200b戊\u200b己\u200b庚", samples=2)
zw_item = next((i for i in zw_six["issues"] if i["id"] == "zero_width"), {})
ok("E", "零宽字符统计真实总命中数而非截断于samples上限",
   zw_item.get("hits") == 6 and len(zw_item.get("locations", [])) == 2)
ok("E", "正常文本不判违规", "zero_width" not in ids("正常文字，没有任何隐藏字符。"))

with tempfile.TemporaryDirectory() as td_bom:
    bom_clean = os.path.join(td_bom, "bom_clean.txt")
    with open(bom_clean, "wb") as f:
        f.write(b"\xef\xbb\xbf" + "老周把搪瓷缸放在柜台角，核对了三遍铜板。".encode("utf-8"))
    t_bom = scan.read_text(bom_clean)
    ok("E", "文件头UTF-8 BOM自动剥离不冤判作弊", "zero_width" not in ids(t_bom))

    bom_cheat = os.path.join(td_bom, "bom_cheat.txt")
    with open(bom_cheat, "wb") as f:
        f.write(b"\xef\xbb\xbf" + "老周把\ufeff搪瓷缸放在柜台角。".encode("utf-8"))
    t_cheat = scan.read_text(bom_cheat)
    ok("E", "UTF-8 BOM文件正中夹零宽仍精准拦截", "zero_width" in ids(t_cheat))

# ---------------------------------------------------------------- F 撤销 (3)
uniform = "。".join(["这是一个长度完全相同的句子共十六个字"] * 10) + "。"
ok("F", "句长均匀不再报（配对实测无差异）", "sentence_cv" not in ids(uniform))
ok("F", "被字句不再报", "beisentence" not in ids("方案被否决了。计划被推迟了。预算被压缩了。"))
ok("F", "进行加动词不再报", "progress" not in ids("我们进行了分析工作，也进行了讨论工作。"))

# ---------------------------------------------------------------- G 规则元数据与编译完整性 (5)
need = {"id", "tier", "basis", "name", "pat", "per_kilo", "min_hits", "advice", "src"}
bad = [r.get("id") for r in scan.RULES if not need.issubset(r)]
ok("G", "规则字段完整", not bad, str(bad))
try:
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

# ---------------------------------------------------------------- H 个人画像基线与引文脱敏 (8)
dash_draft = "甲——乙。" * 12 + "丙" * 120
prof_dash = {"tolerance": 1.5, "s_tolerance": 2.5,
             "rules": {"em_dash": {"mean": 60.0}}, "whitelist": []}
ok("H", "无画像时报破折号", "em_dash" in ids(dash_draft))
ok("H", "有画像时不报（作者本就是该密度）", "em_dash" not in ids(dash_draft, prof=prof_dash))

flip_draft = "这不是效率问题，而是制度问题。" + "正文内容。" * 60
prof_flip = {"tolerance": 1.5, "s_tolerance": 2.5,
             "rules": {"flip": {"mean": 3.0}}, "whitelist": []}
ok("H", "无画像时 S 级翻案腔必报", "flip" in ids(flip_draft))
ok("H", "有画像时 S 级按个人基线放宽", "flip" not in ids(flip_draft, prof=prof_flip))

ok("H", "画像白名单合并生效",
   "officialese" not in ids("赋能。赋能。赋能。赋能。赋能。" + "正文。" * 80,
                            prof={"whitelist": ["赋能"], "rules": {}}))

prof_low = {"tolerance": 1.5, "s_tolerance": 2.5,
            "rules": {"em_dash": {"mean": 0.2}}, "whitelist": []}
ok("H", "个人基线更低时不反向收紧通用阈值", "em_dash" in ids(dash_draft, prof=prof_low))

with tempfile.TemporaryDirectory() as td_q:
    qf1 = os.path.join(td_q, "q1.txt")
    qf2 = os.path.join(td_q, "q2.txt")
    # 第三人称叙事旧稿，仅在角色对白引号内出现「我」与反讽官话
    q_body = ("老周合上账本，指着墙上的横幅没吭声。受访者说：「我觉得这不是态度问题，而是咱们赋能抓手没有形成合力。」"
              "老周转身去冷库锁好了铁门，把钥匙揣进兜里。") * 3
    for qp_ in (qf1, qf2):
        with open(qp_, "w", encoding="utf-8", newline="\n") as f:
            f.write(q_body)
    q_prof_p = os.path.join(td_q, "qprof.json")
    sp.build([qf1, qf2], store=q_prof_p, min_chars=50)
    q_prof = sp.load(q_prof_p)
    ok("H", "build构建个人基线时忽略引号内他人官话与翻案腔",
       q_prof["rules"]["flip"]["mean"] == 0.0 and q_prof["rules"]["officialese"]["mean"] == 0.0)
    ok("H", "叙述者第一人称统计自动剔除角色对白引号内的『我/咱们』",
       q_prof["baseline"]["first_person"] == 0.0 and scan.scan(q_body)["metrics"]["first_person"] == 0)

# ---------------------------------------------------------------- I 改写守卫与停止红线 (7)
long_base = "这是一篇完整的长文，包含详细的背景介绍、问题分析、具体方案以及后续推进计划。我们需要认真评估每一个细节。" * 5
extreme_rev = "首先是技术选型，其次是人员协同。"
g_extreme = loop.evaluate_revision(extreme_rev, long_base)
ok("I", "极端删改实词保留率地板拦截", g_extreme.get("retention", 1.0) < 0.20)
ok("I", "字数剧变超20%触发停止红线警告", "±20%" in g_extreme.get("warn", ""))

normal_doc = "人工智能正在深刻改变现代社会的各个行业和生产组织形式。许多企业已经开始探索自动化技术在日常业务中的实际应用场景，以期降低运营成本并提升协同效率。"
normal_rev = normal_doc.replace("各个行业", "诸多行业").replace("实际应用场景", "具体落地场景")
g_normal = loop.evaluate_revision(normal_rev, normal_doc)
ok("I", "正常微创修改保留率达标且无误警", g_normal.get("retention", 0.0) >= 0.85 and not g_normal.get("warn"))

chopped_rev = "人工智能在变。行业也在变。企业开始探索。他们用自动化。为了降低成本。为了提升效率。大家都这么干。效果还算不错。"
g_chopped = loop.evaluate_revision(chopped_rev, normal_doc)
ok("I", "长句稿被剁成短于15字碎句时触发红线", "15 字" in g_chopped.get("warn", ""))

short_script_base = ("先看这组账单。电费涨了三成。冷库不敢停机。老张连夜查表。发现阀门漏气。换件只要八十。"
                     "财务核对底单。月底结清尾款。车间恢复排班。全组准点下班。")
short_script_rev = short_script_base.replace("换件只要八十", "换件花了八十")
g_script = loop.evaluate_revision(short_script_rev, short_script_base)
ok("I", "原稿即属口播/短剧短句体裁(<15字)时不误报碎句红线",
   "15 字" not in g_script.get("warn", "") and not g_script.get("warn"))

noisy_doc = "同一段八字噪声词在文里反复出现，同一段八字噪声词让人没法正常读，同一段八字噪声词纯粹是为了刷分。"
ok("I", "正文8字片段重复三次检出语义噪声", loop.content_guard(noisy_doc)["noise_runs"] >= 1)

md_tables = "\n\n".join(["| 指标名称 | 当前数值 |\n|---|---|\n| 响应耗时 | 12ms |" for _ in range(4)]) + "\n\n老周核对了四组机房监控记录。"
ok("I", "Markdown重复表头不误报8字语义噪声", loop.content_guard(md_tables)["noise_runs"] == 0)

# ---------------------------------------------------------------- J 文风画像算法、整句窗口与跨格式 docx (10)
ok("J", "FEATS特征名严格唯一（无重复p:—）", len(sp.FEATS) == len(set(sp.FEATS)))
ok("J", "FEATS包含中文弯双引号特征", "p:“" in sp.FEATS and "p:”" in sp.FEATS)

excerpt_raw = "# 第一章 标题行应跳过\n\n老张把搪瓷缸放在柜台角，缸底掉了一块白瓷。他低头数了三遍铜板，始终差两文钱。" + "后来铺子里进来了两个挑夫，把濡湿的麻袋往地上一撂，震得算盘珠子乱跳。" * 4
ex_clean = sp._clean_excerpt(excerpt_raw, max_chars=140)
ok("J", "锚点切片跳过标题且在句末标点完整收口",
   not ex_clean.startswith("#") and ex_clean.endswith("。"))

win_src = "第一句正好二十个字用来测试整句切窗边界。第二句也是完整的二十个字绝不该被拦腰切断。第三句同样保持完整句末句号收尾不断裂。" * 3
wins = sp._sentence_windows(win_src, win=90)
ok("J", "滚动Delta窗口按完整句界聚合不拦腰截断句子",
   len(wins) >= 2 and all(seg.rstrip().endswith("。") for _, seg in wins))

author_doc1 = "因为这个问题的根源在底层架构，所以需要认真评估。虽然前期投入大，但是长远看值得。" * 3
author_doc2 = "我们在实际操作中发现，统一接口至关重要。通过建立清晰规范，团队可以减少沟通损耗。" * 3
author_t = "因为团队在扩张，所以模式必须调整。虽然短期阵痛，但是规范建立后效率就会释放。" * 2
luxun_t = "我翻开历史一查，满本都写着两个字是吃人！黑漆漆的，不知是日是夜。赵家的狗又叫起来了。" * 2

with tempfile.TemporaryDirectory() as td:
    f1 = os.path.join(td, "doc1.txt")
    f2 = os.path.join(td, "doc2.txt")
    f3 = os.path.join(td, "doc3.txt")
    for fp_, content_ in [(f1, author_doc1), (f2, author_doc2)]:
        with open(fp_, "w", encoding="utf-8", newline="\n") as f:
            f.write(content_)
    prof_p = os.path.join(td, "prof.json")
    sp.build([f1, f2], store=prof_p, min_chars=50)
    prof = sp.load(prof_p)
    d_auth, _, _ = sp.delta_of(author_t, prof)
    d_other, _, _ = sp.delta_of(luxun_t, prof)
    ok("J", "Burrows Delta 排序正确（同作者 < 异作者）", d_auth < d_other)
    ok("J", "留一法正对照结构完整", "entry_rate" in prof.get("control", {}))

    old_sm = prof["baseline"]["sent_mean"]
    with open(f3, "w", encoding="utf-8", newline="\n") as f:
        f.write(("我今天只写极短句。每句都只有七八字。绝不写长定语。" * 8))
    sp.build([f3], append=True, store=prof_p, min_chars=50)
    prof2 = sp.load(prof_p)
    new_only_sm = 8.0
    ok("J", "增量append按衰减合并句长基线而非直接覆盖",
       new_only_sm < prof2["baseline"]["sent_mean"] < old_sm)

    docx_p = os.path.join(td, "draft.docx")
    _make_docx(docx_p, [
        "研发与财务（R&amp;D &lt;一期&gt;）今天完成了对账。",
        "老周把三份合同锁进了铁皮柜，确认金额分毫不差。" * 5,
    ])
    docx_txt = scan.read_text(docx_p)
    ok("J", "read_text直读docx并正确反转义XML实体",
       "R&D <一期>" in docx_txt and "&amp;" not in docx_txt)
    rc_chk = sp.check(docx_p, store=prof_p)
    ok("J", "style_profile check直读docx不抛编码崩溃", rc_chk == 0)

    env_j = dict(os.environ, WRITING_LOOP_HOME=td)
    sp.save(prof2, os.path.join(td, "jtest.json"))
    p_chk_json = subprocess.run(
        [sys.executable, os.path.join(ROOT_DIR, "scripts", "style_profile.py"),
         "check", docx_p, "--name", "jtest", "--json"],
        env=env_j, capture_output=True, text=True, encoding="utf-8", timeout=15
    )
    p_dft_json = subprocess.run(
        [sys.executable, os.path.join(ROOT_DIR, "scripts", "style_profile.py"),
         "drift", docx_p, "--name", "jtest", "--win", "80", "--json"],
        env=env_j, capture_output=True, text=True, encoding="utf-8", timeout=15
    )
    chk_obj = json.loads(p_chk_json.stdout) if p_chk_json.returncode == 0 else {}
    dft_obj = json.loads(p_dft_json.stdout) if p_dft_json.returncode == 0 else {}
    ok("J", "style_profile check与drift均支持结构化--json输出",
       chk_obj.get("ok") is True and "top_deviations" in chk_obj
       and dft_obj.get("ok") is True and len(dft_obj.get("windows", [])) >= 1)

# ---------------------------------------------------------------- K 管道编码与缺依赖优雅降级 (3)
tricky_payload = json.dumps(
    {"texts": ["发展改革委发布最新通知，说明这项方案已经在基层落地。"], "bits": 4, "agg": "eq"},
    ensure_ascii=False,
)
proc = subprocess.run(
    [sys.executable, os.path.join(ROOT_DIR, "scripts", "score_batch.py")],
    input=tricky_payload, capture_output=True, text=True, encoding="utf-8", timeout=30
)
try:
    batch_json = json.loads(proc.stdout)
    valid_json = isinstance(batch_json, dict) and ("ok" in batch_json)
except Exception:
    batch_json, valid_json = {}, False
ok("K", "score_batch管道输入含0x8f敏感汉字(发)不抛编码崩溃且返回合法JSON", valid_json, repr(proc.stdout[:120]))
ok("K", "score_batch在已装或未装torch环境下均给出结构化状态而非空输出",
   batch_json.get("ok") is True or bool(batch_json.get("error")))

bad_pipe = subprocess.run(
    [sys.executable, os.path.join(ROOT_DIR, "scripts", "score_batch.py")],
    input="{bad_json", capture_output=True, text=True, encoding="utf-8", timeout=15
)
ok("K", "score_batch非法载荷返回退出码2与错误JSON",
   bad_pipe.returncode == 2 and "载荷解析失败" in bad_pipe.stdout)

# ---------------------------------------------------------------- L 开局章法与语域组装 (8)
ok("L", "kickoff覆盖全部10大核心场景", len(kickoff.SCENES) >= 10)

p_essay = kickoff.build_kickoff_prompt("技术官僚与基层损耗", scene="杂文随笔", stance="刺破套话")
ok("L", "杂文随笔Prompt包含正反合与流水句章法",
   "正题" in p_essay and "反题" in p_essay and "流水句" in p_essay)
ok("L", "kickoff注入语域旋钮与动笔前三行微骨架",
   "语域旋钮" in p_essay and "[起笔切口]" in p_essay and "[中段变奏]" in p_essay)
ok("L", "kickoff彻底剔除端架子套话与病句",
   "拥有深厚思想锋芒" not in p_essay and "断然断言" not in p_essay and "顶级主笔" not in p_essay)

p_alias = kickoff.build_kickoff_prompt("破界之战", scene="修仙网文")
ok("L", "kickoff兼容修仙网文与常见文体别名", "四阶推进" in p_alias)

p_baimiao = kickoff.build_kickoff_prompt("除夕夜小站", scene="白描叙事")
ok("L", "白描叙事Prompt含器物磨损与禁点破寓意准则",
   "磨损" in p_baimiao and "点破寓意" in p_baimiao)

with tempfile.TemporaryDirectory() as td_k:
    ex_f = os.path.join(td_k, "ex.docx")
    _make_docx(ex_f, ["他把那张盖着红章的买断协议折成四折，塞进秋裤贴肉的口袋。人跟厂子两清，原来只需要三分钟。"])
    rc_k = subprocess.run(
        [sys.executable, os.path.join(ROOT_DIR, "scripts", "kickoff.py"),
         "国企改制记忆", "--scene", "白描叙事", "--exemplar", ex_f],
        capture_output=True, text=True, encoding="utf-8", timeout=15
    )
    ok("L", "kickoff命令行支持--exemplar直读docx真人样例",
       rc_k.returncode == 0 and "买断协议折成四折" in rc_k.stdout)

    env_k = dict(os.environ, WRITING_LOOP_HOME=td_k)
    pf1, pf2 = os.path.join(td_k, "p1.txt"), os.path.join(td_k, "p2.txt")
    for pfp_, ptxt_ in [(pf1, author_doc1), (pf2, author_doc2)]:
        with open(pfp_, "w", encoding="utf-8", newline="\n") as f:
            f.write(ptxt_)
    subprocess.run([sys.executable, os.path.join(ROOT_DIR, "scripts", "style_profile.py"),
                    "build", pf1, pf2, "--name", "utest", "--min-chars", "50"],
                   env=env_k, capture_output=True, text=True, encoding="utf-8", timeout=15)
    rc_kp = subprocess.run(
        [sys.executable, os.path.join(ROOT_DIR, "scripts", "kickoff.py"),
         "研发流程改造", "--scene", "管理汇报", "--profile", "utest"],
        env=env_k, capture_output=True, text=True, encoding="utf-8", timeout=15
    )
    ok("L", "kickoff接入--profile同步注入表达DNA与KATE样例",
       rc_kp.returncode == 0 and "表达指纹：" in rc_kp.stdout and "样例 1" in rc_kp.stdout)

# ---------------------------------------------------------------- M 零返工行号定位与首句大纲 (5)
loc_doc = "第一行正常交代时间地点。\n\n第三行依然正常推进。\n第四行写这不是技术问题，而是制度问题。"
loc_res = scan.scan(loc_doc)
flip_issue = next((i for i in loc_res["issues"] if i["id"] == "flip"), {})
ok("M", "正则命中输出精确1-based行号与上下文切片",
   bool(flip_issue.get("locations")) and flip_issue["locations"][0]["line"] == 4
   and "[行4]" in flip_issue.get("sample", [""])[0])

iso3_res = scan.scan(iso3_paras)
iso3_issue = next((i for i in iso3_res["issues"] if i["id"] == "iso3"), {})
ok("M", "段落同构iso3输出精确行号定位而非无头报警",
   bool(iso3_issue.get("locations")) and iso3_issue["locations"][0]["line"] == 1)

zs_res = scan.scan("\n\n".join(bare_more))
zs_issue = next((i for i in zs_res["issues"] if i["id"] == "zero_subj"), {})
ok("M", "段首零主语输出精确行号定位",
   bool(zs_issue.get("locations")) and zs_issue["locations"][0]["line"] == 3)

ol_doc = "\n\n".join(["第%d段首句交代具体进展。随后补充第二句细节。" % i for i in range(1, 7)])
ol = scan.extract_outline(ol_doc)
ok("M", "extract_outline准确抽取正文首句与中段区间",
   ol["total_paras"] == 6 and ol["mid_range"] == [3, 4] and ol["items"][2]["in_mid_third"] is True)

l_s, l_e = scan.offset_span_to_lines("甲\n乙\n丙\n丁\n", 2, 4)
ok("M", "offset_span_to_lines准确映射分段行号闭区间", (l_s, l_e) == (2, 3))

# ---------------------------------------------------------------- N Markdown 结构免疫 (5)
_FENCE = "\x60" * 3
md_mixed = "\n".join([
    "---",
    "title: 测试文稿",
    "---",
    "",
    "# 主标题",
    "",
    "| 列一 | 列二 |",
    "|---|---|",
    "| 甲甲 | 乙乙 |",
    "| 丙丙 | 丁丁 |",
    "| 戊戊 | 己己 |",
    "",
    _FENCE + "python",
    "# 代码里的引号与句式不应计入正文",
    'msg = "这不是效率问题，而是制度问题。"',
    _FENCE,
    "",
    "老周早上八点打开冷库铁锁，核对了三遍电表读数。",
    "",
    "十点半县里检查组到了院门口，先问台账装订好了没有。",
])
md_res = scan.scan(md_mixed)
ok("N", "YAML头代码块与表格行不污染正文段数与引号计数",
   md_res["metrics"]["paragraphs"] == 2 and md_res["metrics"]["masked_quotes"] == 0)
ok("N", "代码块内伪翻案腔不误报", "flip" not in {i["id"] for i in md_res["issues"]})
ok("N", "小标题首句重复(heading_echo)在Markdown遮罩下仍正常检出",
   "heading_echo" in ids("### 核心调度策略\n核心调度策略决定了吞吐上限。"))
ok("N", "带序号小标题首句重复(### 一、…)同样精准检出",
   "heading_echo" in ids("### 一、核心调度策略   \n\n核心调度策略决定了吞吐上限。"))

md_link_doc = "详见[审计报告](https://example.com/2026/very/long/path/that/would/inflate/sentence/length/by/eighty/chars)第十四页。"
md_link_m = scan.scan(md_link_doc)["metrics"]
ok("N", "Markdown超长链接URL自动遮罩不虚增句长与字数分母",
   md_link_m["chars"] < 25 and (md_link_m["sent_mean"] or 99) < 25)

# ---------------------------------------------------------------- O 协议合规、引擎锁定与全仓卫生 (7)
skill_path = os.path.join(ROOT_DIR, "SKILL.md")
skill_txt = open(skill_path, encoding="utf-8").read()
fm_parts = skill_txt.split("---", 2)
fm_bytes = len(fm_parts[1].encode("utf-8")) if len(fm_parts) >= 3 else 9999
ok("O", "SKILL.md的YAML头小于600字节防截断与常驻膨胀", fm_bytes < 600, "bytes=%d" % fm_bytes)
ok("O", "SKILL.md剔除编程易误触裸词(写脚本)并含显式代码排他边界",
   "写脚本" not in fm_parts[1] and "程序脚本" in fm_parts[1] and "代码重构" in fm_parts[1])
ok("O", "SKILL.md正文控制在140行内且无断链章节号",
   len(skill_txt.splitlines()) <= 140 and "第四节底线" not in skill_txt,
   "lines=%d" % len(skill_txt.splitlines()))

lic_txt = open(os.path.join(ROOT_DIR, "LICENSE"), encoding="utf-8").read()
notice_txt = open(os.path.join(ROOT_DIR, "NOTICE.md"), encoding="utf-8").read()
ok("O", "根LICENSE采用完整GPL-3.0保守协议且与SKILL/NOTICE一致",
   "GNU GENERAL PUBLIC LICENSE" in lic_txt and "Version 3, 29 June 2007" in lic_txt
   and "license: GPL-3.0-only" in fm_parts[1] and "GPL-3.0" in notice_txt)

sums_file = os.path.join(ROOT_DIR, "engine", "SHA256SUMS.txt")
engine_intact = os.path.isfile(sums_file)
bad_sums = []
if engine_intact:
    for line in open(sums_file, encoding="utf-8").read().splitlines():
        if not line.strip():
            continue
        exp_hash, rel_p = line.strip().split(None, 1)
        rel_p = rel_p.lstrip("*").strip()
        if rel_p.startswith("./"):
            rel_p = rel_p[2:]
        if rel_p == "SKILL.md":
            if not os.path.isfile(os.path.join(ROOT_DIR, "engine", "SKILL.md.template")):
                bad_sums.append("SKILL.md.template:missing")
            continue
        abs_p = os.path.join(ROOT_DIR, "engine", rel_p)
        if not os.path.isfile(abs_p):
            bad_sums.append(rel_p + ":missing")
            continue
        got_hash = hashlib.sha256(open(abs_p, "rb").read()).hexdigest()
        if got_hash != exp_hash:
            bad_sums.append(rel_p)
ok("O", "内嵌engine组件通过SHA256SUMS字节级完整性校验", engine_intact and not bad_sums, str(bad_sums))

readme_txt = open(os.path.join(ROOT_DIR, "README.md"), encoding="utf-8").read()
doc_self_issues = (scan.scan(skill_txt, profile=None)["issues"]
                   + scan.scan(readme_txt, profile=None)["issues"])
ok("O", "SKILL.md与README.md自身通过机械扫描零违例",
   len(doc_self_issues) == 0, str([i["id"] for i in doc_self_issues]))

crlf_bad = []
for walk_root, dirs, files in os.walk(ROOT_DIR):
    dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", "engine")]
    for fn in files:
        if fn.endswith((".py", ".md", ".txt", ".csv", ".json")) or fn in ("LICENSE", ".gitignore", ".gitattributes"):
            full_p = os.path.join(walk_root, fn)
            if b"\r\n" in open(full_p, "rb").read():
                crlf_bad.append(os.path.relpath(full_p, ROOT_DIR))
ok("O", "全仓自有代码、文档与配置文件100%纯LF无CRLF", not crlf_bad, str(crlf_bad))

# ---------------------------------------------------------------- 汇总输出
print("\n" + "=" * 56)
print("writing-loop 2.2 测试汇总：通过 %d ／ 失败 %d ／ 合计 %d"
      % (len(PASS), len(FAIL), len(PASS) + len(FAIL)))
if FAIL:
    print("失败项：")
    for g, n, d in FAIL:
        print("  [%s] %s %s" % (g, n, ("(" + d + ")") if d else ""))
    sys.exit(1)
sys.exit(0)
