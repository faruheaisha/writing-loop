#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""writing-loop 机械扫描器

每条规则标依据等级：
  paired    270 对同题同事实配对复测，双侧显著（lieflat RESEARCH.md）
  corpus    单侧语料频次统计，无人类对照（晓语口癖榜）
  release   随模型版本变化，不是稳定特征（sepia style-pass §7）
  editorial 编辑经验，属文体问题不属 AI 特征

四条跨项目收敛的判定纪律：
  1 单次命中不算信号，要聚类（sepia：one hit means nothing）
  2 结构指标的分母是同类元素总数，不是字数（lieflat 六次失误第 5 条）
  3 引号内与白名单内不计入（sepia 白名单 / novel-studio .deslop-whitelist）
  4 短文按双门判定，最小命中数与密度同时满足才报（oh-story 双门）

用法
  python scan.py 文件.txt [--json] [--whitelist 白名单.txt] [--samples N]
  python scan.py --text "正文"
"""
import argparse
import io
import json
import os
import re
import statistics
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

TH_PARA_ISO2 = 4.81     # 连续两句同构，每百段。人类 4.81 / AI 9.41
TH_PARA_ISO3 = 0.41     # 连续三句同构，每百段。人类 0.41 / AI 0.84
TH_ZERO_SUBJ = 0.14     # 段首零主语评论，占非首段百分比。人类 0.14 / AI 0.61
SHORT_TEXT = 500        # 低于此字数启用双门（最小命中数）

# min_hits: 双门的最小命中数。短文放大倍数，防小基数误报
RULES = [
    dict(id="flip", tier="S", basis="paired", name="翻案腔（不是A而是B）",
         pat=r"(?:不是|并非|不在于|不只是|不仅仅是|与其说)[^，。！？\n]{1,20}[，]?(?:而是|而在于|不如说|更是)",
         per_kilo=0, min_hits=1,
         advice="删掉否定的一半，直接说正面。若否定部分在纠正真实误解才保留。",
         src="lieflat 配对 δ+0.88/+0.72；晓语口癖榜第 1 位 688 次"),
    dict(id="escalate", tier="S", basis="corpus", name="递增对比（不仅…更…）",
         pat=r"不仅[^，。]{1,30}[，]?(?:更|还)[^，。]{1,20}(?:体现|作用|意味|在于|是)",
         per_kilo=0, min_hits=1, advice="两件事并列说清楚，不用递进造势。",
         src="晓语口癖榜第 10 位 66 次"),
    dict(id="opener", tier="S", basis="corpus", name="套话开头",
         pat=r"^(?:在当今社会|自古以来|众所周知|随着[^，。]{0,24}的(?:发展|进步|普及|推进|深化|加快)|近年来[，、])",
         per_kilo=0, min_hits=1, advice="首句直接进问题或场景，放入时间、地点、数字。",
         src="qiqing-liuyu；Humanizer-zh §4"),
    dict(id="closer", tier="S", basis="corpus", name="总结式收尾",
         pat=r"综上所述|总而言之|总的来说|归根结底|由此可见|不难看出|不难发现|"
             r"为[^，。]{0,12}(?:贡献|提供)[^，。]{0,8}(?:力量|动力|支撑)",
         per_kilo=0, min_hits=1,
         advice="结尾用动作、具体判断或留白收住，不回头总结全文。",
         src="Humanizer-zh；novel-studio 章末禁区"),
    dict(id="triple", tier="S", basis="corpus", name="首先其次最后",
         pat=r"首先[，、][\s\S]{0,600}?其次[，、][\s\S]{0,600}?最后[，、]",
         per_kilo=0, min_hits=1, advice="按理由强弱排，不按序号排。",
         src="qiqing-liuyu；晓语口癖榜第 2 位"),
    dict(id="about_doc", tier="S", basis="corpus", name="写文档本身而非主题",
         pat=r"本文(?:将|拟|试图|旨在)|接下来(?:我们|本文)?(?:将)?(?:讨论|分析|介绍)|"
             r"下面(?:我们)?(?:来)?(?:看|讨论|分析)",
         per_kilo=0, min_hits=1, advice="直接说事，不要先说接下来要说什么。",
         src="blader/humanizer §25"),
    dict(id="disclaimer", tier="S", basis="corpus", name="知识边界免责语",
         pat=r"我(?:无法|不能)(?:确定|保证|核实)|仅供参考[，。]|请以(?:官方|实际)(?:为准|发布)",
         per_kilo=0, min_hits=1, advice="不确定就说不确定，不要用模板化免责句兜底。",
         src="blader/humanizer §23"),

    dict(id="colon_hint", tier="A", basis="paired", name="提示语冒号（核心是：）",
         pat=r"(?:核心|关键|本质|问题|答案|结论)(?:问题|点|区别|原因|矛盾|要害)?"
             r"(?:还|也)?(?:是|在于|就)[：:]|"
             r"(?:一句话|简单说|说白了)(?:总结|来说|概括)?[：:]",
         per_kilo=0.08, min_hits=2,
         advice="提示语冒号是强信号（人类 0.08、AI 0.29）。改成正常句子。",
         src="lieflat 配对 3.78×，人类两组均近零"),
    dict(id="colon_list", tier="A", basis="paired", name="空转句引列表",
         pat=r"[：:]\s*\n\s*(?:[-*•]|\d+[.、])",
         per_kilo=0.03, min_hits=1,
         advice="最强单条信号（人类 0.03、AI 0.29）。先写完那句话，再决定要不要列表。",
         src="lieflat 配对 9.38×"),
    dict(id="em_dash", tier="A", basis="release", name="破折号",
         pat=r"——|—{1,2}",
         per_kilo=2.0, min_hits=3,
         advice="按功能改：打断改动作或短句，拖长音改省略，插入说明改逗号。不要一律换句号。",
         src="sepia 分版本频次 GPT-4.1 10.62 / Opus 4.6 9.09 / GPT-5.4 1.43 / Llama 0.00，人类 3.23；lieflat 分模型 0.11 到 5.16"),
    dict(id="authority", tier="A", basis="corpus", name="借权威无出处",
         pat=r"(?:研究表明|数据显示|专家(?:指出|认为)|大量(?:研究|实践)(?:表明|证明)|"
             r"相关(?:研究|调查)(?:表明|显示))",
         per_kilo=0.3, min_hits=2,
         advice="给具体出处，或改成你自己的观察。无出处的研究表明是最常见的假权威。",
         src="blader/humanizer §17"),
    dict(id="essence", tier="A", basis="corpus", name="本质是",
         pat=r"本质(?:上)?(?:是|在于)|归根到底(?:是|在于)",
         per_kilo=1.0, min_hits=2, advice="直接说它是什么，不用更高层的抽象名词再解释一遍。",
         src="晓语口癖榜；blader/humanizer §3"),
    dict(id="only", tier="A", basis="corpus", name="唯一 / 只有一种",
         pat=r"唯一(?:的)?(?:办法|出路|选择|答案|标准|路径)|只有(?:一|这)种",
         per_kilo=1.0, min_hits=2, advice="给条件：在什么前提下这是最优解。",
         src="晓语口癖榜第 3、6 位；思辨 C11"),
    dict(id="either", tier="A", basis="corpus", name="要么…要么…",
         pat=r"要么[^，。]{1,25}要么", per_kilo=0.5, min_hits=2,
         advice="列第三选项，说明前两个为什么不够。", src="Purdue either/or；思辨 C29"),
    dict(id="advice", tier="A", basis="corpus", name="我的建议是 / 记住",
         pat=r"我的建议是|建议(?:你|大家|各位)?直接|记住[，：:]", per_kilo=0.5, min_hits=2,
         advice="给建议带适用条件和不适用的情况。", src="晓语口癖榜第 7、12 位"),
    dict(id="evenif", tier="A", basis="corpus", name="就算…也…",
         pat=r"就算[^，。]{1,25}也", per_kilo=0.5, min_hits=2,
         advice="具体让步加具体反驳。", src="晓语口癖榜第 13 位"),
    dict(id="whybecause", tier="A", basis="corpus", name="之所以…是因为…",
         pat=r"之所以[^，。]{1,40}是因为", per_kilo=1.0, min_hits=2,
         advice="拆两句：先现象后原因。", src="晓语口癖榜第 16 位"),
    dict(id="frankly", tier="A", basis="corpus", name="说实话 / 说白了",
         pat=r"说实话|说白了|坦白说", per_kilo=1.0, min_hits=2,
         advice="整篇不超过一处。", src="晓语口癖榜第 1、17 位"),

    dict(id="abstract_pass", tier="B", basis="paired", name="过长前置定语",
         pat=r"[^，。！？\n]{12,}的[一-龥]{2,4}(?:是|在于|成为|意味着)",
         per_kilo=0.42, min_hits=2, advice="拆成两句，或把定语后置。",
         src="lieflat 配对收录，人类侧差 2.6 到 5.3 倍"),
    dict(id="whenthen", tier="B", basis="paired", name="当…时 / 在…的过程中",
         pat=r"当[^，。]{2,20}时[，]|在[^，。]{2,20}的过程中", per_kilo=0.26, min_hits=2,
         advice="改成具体时点，或直接删。", src="lieflat 配对收录"),
    dict(id="nominal", tier="B", basis="paired", name="抽象后缀词（性/化/度）",
         pat=r"[一-龥]{2}(?:性|化|度)(?:[，。、；])", per_kilo=4.0, min_hits=3,
         advice="AI 比人类多 1.6 倍，可删就删。",
         src="lieflat：改用抽象后缀词测才成立，动词名词化本身人类更多"),
    dict(id="dedede", tier="B", basis="paired", name="层叠的的",
         pat=r"的[一-龥]{0,4}的[一-龥]{0,4}的", per_kilo=0.06, min_hits=1,
         advice="拆开长定语，注意别跨顿号误判正常并列。",
         src="lieflat 收紧后 0.06/千字"),
    dict(id="connector", tier="B", basis="paired", name="连接词密度",
         pat=r"此外|与此同时|另一方面|不仅如此|更重要的是|换言之|进而|从而",
         per_kilo=6.0, min_hits=3, advice="靠内容承接，不靠连接词铺路。",
         src="lieflat：衔接词总量 AI 14.4% / 人类 15.1% 无差异，只有堆叠才动"),
    dict(id="softadv", tier="B", basis="corpus", name="微微淡淡缓缓轻轻",
         pat=r"微微|淡淡|缓缓|轻轻|默默|静静", per_kilo=3.0, min_hits=3,
         advice="每千字超过 3 个再动。", src="novel-studio 阈值原文"),
    dict(id="onesent", tier="B", basis="corpus", name="单句成段（戏剧性碎片）",
         pat=r"(?m)^[^\n]{1,12}[。！？]\s*$",
         per_kilo=1.0, min_hits=3,
         advice="单句成段是制造停顿的手法，连用三次就成了节奏模板。合并其中一两句。",
         src="blader/humanizer §2"),
    dict(id="abstract_close", tier="B", basis="corpus", name="抽象概括式收束",
         pat=r"这一刻[^\n。！？]{0,24}(?:终于|才)(?:明白|意识到)|从这一刻开始|"
             r"(?:命运|宿命)[^\n。！？]{0,28}(?:齿轮|棋局|改写|推向|安排)|"
             r"前所未有的(?:决意|清醒|勇气|力量|信念)|才刚刚开始|全新的?开始",
         per_kilo=1.0, min_hits=2,
         advice="这是叙事文里最典型的机器收束。停在此刻的动作或一句对话上，不要替读者总结意义。",
         src="oh-story abstract-summary-tic（七条正则，双门 3 次加每千字 4 次）"),
    dict(id="inflated_sig", tier="A", basis="corpus", name="抬高意义（标志着/见证了）",
         pat=r"标志(?:着|性)|见证了|具有里程碑|开启(?:了)?新(?:的)?(?:篇章|阶段|局面)|"
             r"未来可期|前景广阔|彰显(?:了|出)|折射出|体现出[^，。]{0,8}(?:重要性|价值|意义)|"
             r"画上(?:了)?(?:圆满的)?句号|注入(?:了)?(?:新|强劲)(?:的)?(?:动力|活力)",
         per_kilo=0.5, min_hits=2,
         advice="把意义删掉，只留事实，停在最后一个具体事实上。"
                "「标志着里程碑」这类话是把普通细节说成转折、证明或承诺。",
         src="blader/humanizer §13 inflated significance"),
    dict(id="heading_echo", tier="B", basis="corpus", name="小标题在首句重复",
         pat=r"(?m)^#{1,6}\s*([^\n]{2,12})\n+(?:[^\n]{0,6})\1",
         per_kilo=0.2, min_hits=1,
         advice="删掉小标题下面那句重复标题的话，直接进内容。",
         src="blader/humanizer §24 heading repeated in first sentence"),
    dict(id="officialese", tier="B", basis="editorial", name="公文空转词",
         pat=r"协同发力|赋能|抓手|形成合力|高质量发展|深度融合|全面赋能|闭环管理|"
             r"持续发力|协同推进|聚焦主责主业|狠抓落实|对标对表|落地见效",
         per_kilo=1.0, min_hits=2,
         advice="换成谁在什么时间做了什么、花了多少、效果差多少。",
         src="编辑经验，非 AI 特征，属文体问题"),
]

BANNED_CHARS = {"\u200b": "零宽空格", "\u200c": "零宽非连接符",
                "\u200d": "零宽连接符", "\ufeff": "零宽不换行空格",
                "\u2060": "词连接符"}
SENT_SPLIT = re.compile(r"(?<=[。！？；\n])")
QUOTE = re.compile(r"「[^」]{0,400}」|“[^”]{0,400}”|\"[^\"]{0,400}\"|『[^』]{0,400}』")
ZERO_SUBJ_OK = re.compile(
    r"^(?:这|那|它|其|此|该|因此|所以|但|而|于是|结果|最终|后来|"
    r"值得|进一步|此外|同时|另外|首先|其次|再次|总之|换言之|"
    r"从|在|对|关于|通过|由于|随着|就|至于|如果说|相比|相较于|按照|依据|针对)")
PRED = re.compile(r"是|在|有|为|需要|应该|意味")


def split_sents(t):
    return [s.strip() for s in SENT_SPLIT.split(t) if s.strip()]


def split_paras(t):
    return [p.strip() for p in re.split(r"\n\s*\n|\n", t) if p.strip()]


def cv(v):
    if len(v) < 2:
        return None
    m = statistics.mean(v)
    return None if m == 0 else statistics.pstdev(v) / m


def mtld(tokens, threshold=0.72, min_len=10):
    if len(tokens) < min_len * 2:
        return None

    def f(seq):
        n_f, types, n = 0.0, set(), 0
        for tok in seq:
            n += 1
            types.add(tok)
            if len(types) / n <= threshold:
                n_f += 1
                types, n = set(), 0
        if n:
            partial = len(types) / n
            n_f += (1 - partial) / (1 - threshold) if partial < 1 else 0
        return n_f

    d = f(tokens) + f(list(reversed(tokens)))
    return len(tokens) / (d / 2) if d else None


def mask(text, whitelist):
    """把引号内容与白名单词替换为等长占位符，保持偏移不变。"""
    blank = lambda s: re.sub(r"[^\n]", "￭", s)
    out = QUOTE.sub(lambda m: blank(m.group()), text)
    for w in whitelist:
        if w:
            out = out.replace(w, "￭" * len(w))
    return out


def _personal_limit(rule, profile):
    """个人基线与通用阈值取大者。S 级放宽多，A/B 级放宽少。"""
    base = rule["per_kilo"]
    if not profile:
        return base, "通用"
    r = (profile.get("rules") or {}).get(rule["id"])
    if not r or not r.get("mean"):
        return base, "通用"
    tol = profile.get("s_tolerance", 2.5) if rule["tier"] == "S" else profile.get("tolerance", 1.5)
    personal = r["mean"] * tol
    return (personal, "个人") if personal > base else (base, "通用")


def load_profile(path=None):
    p = path or os.path.join(os.path.expanduser("~"), ".workbuddy",
                             "writing-loop", "profiles", "self.json")
    if not os.path.isfile(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def scan(text, samples=3, whitelist=None, profile=None):
    whitelist = [w.strip() for w in (whitelist or []) if w.strip()]
    if profile:
        whitelist += [w for w in profile.get("whitelist", []) if w not in whitelist]
    chars = len(text)
    kilo = max(chars / 1000.0, 0.001)
    short = chars < SHORT_TEXT
    masked = mask(text, whitelist)
    issues = []

    bad = [n for c, n in BANNED_CHARS.items() if c in text]
    if bad:
        issues.append(dict(id="zero_width", tier="X", basis="editorial",
                           name="检出零宽字符", hits=1,
                           detail="、".join(sorted(set(bad))),
                           advice="立即删除。字符级作弊，编码转换即暴露。",
                           src="RAID homoglyph 攻击一类"))

    for r in RULES:
        hits = [m.group() for m in re.finditer(r["pat"], masked, flags=re.MULTILINE)]
        n = len(hits)
        if not n:
            continue
        rate, source = _personal_limit(r, profile)
        allowed = rate * kilo
        by_density = n > allowed
        by_count = n >= r["min_hits"]
        if short and r["tier"] != "S":
            if not (by_density and by_count):
                continue
        elif not by_density:
            continue
        issues.append(dict(id=r["id"], tier=r["tier"], basis=r["basis"], name=r["name"],
                           hits=n,
                           limit=("0 处" if rate == 0 else
                                  "≤ %.1f 处（每千字 %.2f%s，最少命中 %d）"
                                  % (allowed, rate,
                                     "，个人基线" if source == "个人" else "",
                                     r["min_hits"])),
                           baseline=source,
                           sample=hits[:samples], advice=r["advice"], src=r["src"]))

    sents = split_sents(text)
    slen = [len(s) for s in sents]
    paras = split_paras(text)
    nonfirst = paras[1:]

    iso2 = iso3 = 0
    for p in paras:
        ps = split_sents(p)
        run = 1
        for i in range(1, len(ps)):
            if abs(len(ps[i]) - len(ps[i - 1])) <= 2:
                run += 1
            else:
                if run == 2:
                    iso2 += 1
                elif run >= 3:
                    iso3 += 1
                run = 1
        if run == 2:
            iso2 += 1
        elif run >= 3:
            iso3 += 1

    if len(paras) >= 10:
        r2 = iso2 / len(paras) * 100
        r3 = iso3 / len(paras) * 100
        if r2 > TH_PARA_ISO2:
            issues.append(dict(id="iso2", tier="A", basis="paired", name="连续两句同构",
                               hits=iso2, limit="≤ %.1f 处/百段" % TH_PARA_ISO2,
                               detail="%.1f 处/百段（人类 4.81 / AI 9.41）" % r2,
                               advice="合并相邻两句，或改其中一句的句式，不要只换词。",
                               src="lieflat 配对 1.96×"))
        if r3 > TH_PARA_ISO3:
            issues.append(dict(id="iso3", tier="A", basis="paired", name="连续三句同构",
                               hits=iso3, limit="≤ %.1f 处/百段" % TH_PARA_ISO3,
                               detail="%.1f 处/百段（人类 0.41 / AI 0.84）" % r3,
                               advice="三连同构是最硬的段落级信号，整段重排。",
                               src="lieflat 配对 2.03×"))

    zs = 0
    for p in nonfirst:
        ps = split_sents(p)
        if not ps:
            continue
        head = ps[0]
        if len(head) >= 6 and not ZERO_SUBJ_OK.match(head) and PRED.search(head):
            zs += 1
    if len(nonfirst) >= 5:
        zr = zs / len(nonfirst) * 100
        if zr > TH_ZERO_SUBJ:
            issues.append(dict(id="zero_subj", tier="A", basis="paired", name="段首零主语评论",
                               hits=zs, limit="≤ %.2f%%" % TH_ZERO_SUBJ,
                               detail="%.2f%% 的非首段以无回指的评论句开头（人类 0.14 / AI 0.61）" % zr,
                               advice="补一个「这」或「那」把回指接上，或删掉这句评论。",
                               src="lieflat 配对 4.38×，最稳的段落级信号"))

    metrics = dict(chars=chars, sentences=len(sents), paragraphs=len(paras),
                   sent_mean=round(statistics.mean(slen), 1) if slen else None,
                   sent_cv=round(cv(slen), 3) if cv(slen) else None,
                   first_person=len(re.findall(r"我|咱们", text)),
                   masked_quotes=len(QUOTE.findall(text)),
                   whitelist_hits=len(whitelist))
    m = mtld(re.findall(r"[一-龥]", text))
    if m:
        metrics["mtld"] = round(m, 1)

    order = {"X": 0, "S": 1, "A": 2, "B": 3}
    issues.sort(key=lambda x: (order.get(x["tier"], 9), -x.get("hits", 0)))
    return dict(metrics=metrics, issues=issues, note=NOTE)


NOTE = ("以下指标配对实测与人类无差异或方向相反，本扫描器不作为问题报出："
        "句长变异系数、相邻句长差、段落长度均匀度、句内排比（人类更多）、比喻密度（人类 2.4×）、"
        "正文问句（人类 17×）、正文序数词、被动句、进行加动词、被字句、值得注意的是、"
        "问句小标题、案例凑三个、标点密度、段落平均长度。依据见各规则的 src 字段。")


def render(res):
    m, iss = res["metrics"], res["issues"]
    L = ["字数 %d ｜ 句 %d ｜ 段 %d ｜ 引号豁免 %d 段 ｜ 白名单 %d 词"
         % (m["chars"], m["sentences"], m["paragraphs"],
            m["masked_quotes"], m["whitelist_hits"]),
         "句长均值 %s ｜ 变异系数 %s（仅参考）｜ 第一人称 %d 处"
         % (m["sent_mean"], m["sent_cv"], m["first_person"])]
    if m.get("mtld"):
        L[1] += " ｜ MTLD %s" % m["mtld"]
    L.append("")
    if not iss:
        L.append("机械层零命中。")
    else:
        tn = {"X": "违规", "S": "必改", "A": "建议改", "B": "弱信号"}
        cur = None
        for it in iss:
            if it["tier"] != cur:
                cur = it["tier"]
                L.append("【%s】" % tn[cur])
            L.append("  %-24s 命中 %-3s ｜ %s ｜ 依据 %s"
                     % (it["name"], it["hits"], it.get("limit", ""), it.get("basis", "")))
            if it.get("detail"):
                L.append("      " + it["detail"])
            if it.get("sample"):
                L.append("      例：%s" % " ；".join(str(s)[:30] for s in it["sample"]))
            L.append("      改法：%s" % it["advice"])
    L += ["", "说明：" + res["note"]]
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="writing-loop 机械扫描器")
    ap.add_argument("file", nargs="?")
    ap.add_argument("--text", default=None)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--whitelist", default=None, help="白名单文件，一行一个词，命中不计")
    ap.add_argument("--samples", type=int, default=3)
    ap.add_argument("--profile", default=None, help="文风画像 JSON，缺省读 ~/.workbuddy/writing-loop/profiles/self.json")
    ap.add_argument("--no-profile", action="store_true", help="忽略个人画像，只用通用阈值")
    a = ap.parse_args()
    if a.text:
        text = a.text
    elif a.file and os.path.isfile(a.file):
        text = open(a.file, encoding="utf-8").read()
    else:
        ap.error("需要文件路径或 --text")
    if not text.strip():
        sys.stderr.write("文本为空\n")
        sys.exit(2)
    wl = []
    if a.whitelist:
        if not os.path.isfile(a.whitelist):
            sys.stderr.write("白名单文件不存在：%s\n" % a.whitelist)
            sys.exit(2)
        wl = open(a.whitelist, encoding="utf-8").read().splitlines()
    prof = None if a.no_profile else load_profile(a.profile)
    res = scan(text, a.samples, wl, prof)
    res["profile_used"] = bool(prof)
    sys.stdout.write(json.dumps(res, ensure_ascii=False, indent=2) + "\n"
                     if a.json else render(res) + "\n")


if __name__ == "__main__":
    main()
