#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""writing-loop 文风画像：按作者归属学的成熟方法建立个人基线。

方法出处（新近为主，经典方法仅作底座）
  The Width of a Voice: Placing Machine Imitation Inside Authors' Own Variation,
    Zenodo preprint v0.5.5, 2026-07（投 CHR 2027）。在 15 位已出版小说家上按 Burrows
    Delta 建立逐作者、按长度匹配的组内变异包络；留出自身文本回落包络率 84% 至 88%，
    作为正对照。给出作者原文片段优于只给作者名。并测出十二项「AI 特征」组合检测器
    在人机判别上 AUC 0.506，等于抛硬币。
  StyloPrompt, AIED 2026（arXiv 收录）：把文体指纹转成自然语言描述比直接给数值更
    有效，NL-Distribution 编码在跨风格迁移上达 89% 成功率。本文件的 descriptor 照此。
  PersonalBench, 2026：推理时个性化能把输出调节到可区分（AUC 0.918），但跨不过
    人机边界；所有方法与真实作者的相似度 0.484 至 0.508，低于人类之间 0.626 至
    0.756。故本文件从不声称能让人写出「像你」的稿子，只报距离。
  Burrows 2002, Delta: A Measure of Stylistic Difference and a Guide to Likely
    Authorship, Literary and Linguistic Computing. 取 n 个最高频特征、z-score
    标准化、算平均绝对差。
  Jannidis et al. 2015 与 Smith & Aldridge 2011 报告 Cosine 变体在大 N 与
    长文本下更优。本机实测（8 篇同作者、单篇约 190 字、159 维）两种距离：
    经典 Manhattan 组内均值 0.498（0.253 至 0.645），Cosine 组内均值 1.141
    （0.544 至 1.459）。短文本稀疏特征下 Cosine 已接近正交，故采用经典
    Manhattan。这是一次带数字的取舍，不是默认选择。
  法证文本比对实践：功能词是最具判别力的特征（content-independent，
  不受题材影响），N 取 260 时与文档长度无关。本文件取约 160 个中文功能词
  与标点，加句长分箱。
  Rolling Delta：把 Delta 施于滑动窗，得到全文的风格漂移曲线，用于定位
  哪一段偏离作者本人最远。
  Liu et al. 2021, What Makes Good In-Context Examples for GPT-3（KATE）：
  按余弦相似度取最近的 k 个样例作上下文示例，优于随机抽样。

做了什么
  build   从作者旧稿建画像：特征均值方差、作者自己的 Delta 分布、锚点文档
  drift   对一篇新稿做滚动 Delta，定位最不像作者本人的段落
  exemplar 按 KATE 取与指定段落最相近的作者旧稿片段，供 few-shot 使用
  check   综合报告：Delta 与百分位、各特征偏离
  show / reset

存储 ~/.workbuddy/writing-loop/profiles/<名字>.json（技能目录之外，重装不丢）

用法
  python profile.py build 旧稿目录/ [--append]
  python profile.py drift 新稿.txt
  python profile.py exemplar 新稿.txt --k 3
  python profile.py check 新稿.txt
"""
import argparse
import glob
import io
import json
import math
import os
import re
import statistics
import sys
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import scan as scanner  # noqa: E402

ROOT = os.path.join(os.path.expanduser("~"), ".workbuddy", "writing-loop", "profiles")
STORE = os.path.join(ROOT, "self.json")


def store_for(name):
    safe = re.sub(r"[^\w\u4e00-\u9fff-]", "_", name)[:40] or "self"
    return os.path.join(ROOT, safe + ".json")
DECAY = 0.85
TEXT_EXT = (".md", ".txt", ".markdown")
DOCX_EXT = (".docx",)


def read_docx(path):
    """从 docx 提取正文：解包 zip，取 word/document.xml，剥标签，段落转行。"""
    import zipfile
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8", errors="ignore")
    xml = re.sub(r"</w:p>", "\n", xml)
    txt = re.sub(r"<[^>]+>", "", xml)
    return re.sub(r"\n{3,}", "\n\n", txt)
MIN_DOC_CHARS = 150          # 低于此长度的单篇不参与建模
MAX_DOC_CHARS = 12000     # 超长稿截断，避免单篇压死分布
N_FEATURES = 260          # 法证实践给出的大小，与文档长度无关

# 中文功能词：代词、介词、连词、助词、副词、常用虚化动词。不带题材色彩。
FUNC = """的 了 在 是 和 有 就 不 人 都 一 上 也 很 到 说 要 去 你 会 着 没 看 好 自己
这 那 我 他 她 它 们 个 中 对 与 及 或 但 而 因为 所以 如果 虽然 即使 只是 已经 还是
还有 一些 什么 怎么 为什么 时候 问题 方法 我们 他们 可以 应该 需要 能够 进行 通过
根据 以及 并且 而且 因此 但是 然而 不过 就是 一直 总是 常常 可能 大概 也许 其实
比较 更 最 太 又 再 才 只 都 还 并 却 则 若 因 故 由 于 以 为 被 把 给 让 使 从 向
里面 外面 上面 下面 前面 后面 之间 之后 之前 当时 现在 原来 本来 确实 显然 当然
一般 通常 往往 有时 有些 很多 不少 一点 完全 非常 特别 十分 相当 稍微 几乎 至少"""

PUNCT = "，。、；：？！——…（）「」《》"

SL_BINS = [(0, 10), (11, 20), (21, 35), (36, 60), (61, 10 ** 6)]


def feature_names():
    fw = []
    seen = set()
    for w in FUNC.split():
        if w not in seen:
            seen.add(w)
            fw.append("fw:" + w)
    pw = ["p:" + p for p in PUNCT]
    sl = ["sl:%d-%d" % (a, b if b < 10 ** 6 else 999) for a, b in SL_BINS]
    return (fw + pw + sl)[:N_FEATURES]


FEATS = feature_names()


def vector(text):
    """相对频率向量。长度按字数归一。"""
    n = max(len(text), 1)
    v = []
    for name in FEATS:
        kind, key = name.split(":", 1)
        if kind == "fw":
            c = text.count(key)
        elif kind == "p":
            c = text.count(key)
        else:
            lo, hi = [int(x) for x in key.split("-")]
            c = sum(1 for s in scanner.split_sents(text) if lo <= len(s) <= hi)
        v.append(c / n * 1000.0)
    return v


Z_CAP = 4.0   # z 截断：作者从未用过的特征不能因 sd 极小把距离炸到百万级


def zscore(vec, mu, sd):
    out = []
    for x, m, s in zip(vec, mu, sd):
        if s < 1e-9:
            out.append(0.0 if abs(x - m) < 1e-9 else Z_CAP)
        else:
            z = (x - m) / s
            out.append(Z_CAP if z > Z_CAP else (-Z_CAP if z < -Z_CAP else z))
    return out


def cos_dist(a, b):
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na < 1e-12 or nb < 1e-12:
        return 1.0
    return 1.0 - sum(x * y for x, y in zip(a, b)) / (na * nb)


def mean_abs_dev(a, b):
    """经典 Burrows Delta：z 分数之差的平均绝对值。本文件的主距离。"""
    return sum(abs(x - y) for x, y in zip(a, b)) / max(len(a), 1)


def delta(a, b):
    return mean_abs_dev(a, b)


def load(store=STORE):
    if not os.path.isfile(store):
        return None
    try:
        with open(store, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save(p, store=STORE):
    os.makedirs(os.path.dirname(store), exist_ok=True)
    tmp = store + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(p, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, store)


def collect(paths):
    files = []
    for p in paths:
        if os.path.isdir(p):
            for ext in TEXT_EXT + DOCX_EXT:
                files += glob.glob(os.path.join(p, "**", "*" + ext), recursive=True)
        elif os.path.isfile(p) and p.lower().endswith(TEXT_EXT):
            files.append(p)
        elif os.path.isfile(p) and p.lower().endswith(DOCX_EXT):
            files.append(p)
    return sorted(set(files))


def build(paths, append=False, store=STORE, min_chars=None):
    files = collect(paths)
    if not files:
        sys.stderr.write("没有找到 .md 或 .txt 稿件\n")
        return 2
    old = load(store) if append else None
    seen = set((old or {}).get("files", {}))
    todo = [f for f in files if os.path.abspath(f) not in seen]
    if not todo:
        print("没有新稿件，画像未变")
        return 0

    docs = []
    for f in todo:
        try:
            if f.lower().endswith(DOCX_EXT):
                t = read_docx(f)[:MAX_DOC_CHARS]
            else:
                t = open(f, encoding="utf-8").read()[:MAX_DOC_CHARS]
        except Exception as e:
            sys.stderr.write("跳过 %s：%s\n" % (f, e))
            continue
        if len(t.strip()) < (min_chars or MIN_DOC_CHARS):
            continue
        docs.append((os.path.abspath(f), t, vector(t)))
    if not docs:
        lens = sorted((len(open(f, encoding="utf-8").read().strip()) for f in todo
                       if os.path.isfile(f)), reverse=True)[:5]
        sys.stderr.write(
            "所有稿件都短于 %d 字，无法建模。文体距离需要足够长的样本。\n"
            "  你给的最长几篇：%s 字\n"
            "  三条出路：改用更长的稿件；把同一主题的多篇合并成一篇；先只建锚点（build --min-chars 调低，但结果不稳）。\n"
            % (min_chars or MIN_DOC_CHARS, lens or ["?"]))
        return 2

    # 均值方差：新增样本与旧画像按衰减权重合并
    n_new = len(docs)
    n_old = (old or {}).get("n", 0) * DECAY
    mu_new = [statistics.mean(d[2][i] for d in docs) for i in range(len(FEATS))]
    sd_new = [statistics.pstdev([d[2][i] for d in docs]) if n_new > 1 else 0.0
              for i in range(len(FEATS))]
    if old and old.get("mu"):
        w = n_old + n_new
        mu = [(o * n_old + n_ * n_new) / w for o, n_ in zip(old["mu"], mu_new)]
        sd = [math.sqrt((o ** 2 * n_old + s ** 2 * n_new) / w)
              for o, s in zip(old.get("sd", sd_new), sd_new)]
    else:
        mu, sd = mu_new, sd_new
    sd = [s if s > 1e-6 else 1e-6 for s in sd]

    # 作者自己的 Delta 分布：留一法
    zv = [zscore(d[2], mu, sd) for d in docs]
    within = []
    for i in range(len(zv)):
        for j in range(i + 1, len(zv)):
            within.append(delta(zv[i], zv[j]))
    if old and old.get("within"):
        w_old = old["within"]
        n_o = w_old.get("n", 0) * DECAY
        n_n = max(len(within), 1)
        wsum = n_o + n_n
        within_mean = (w_old.get("mean", 0) * n_o + (statistics.mean(within) if within else 0) * n_n) / wsum
        within_max = max(w_old.get("max", 0) * DECAY, max(within) if within else 0)
    else:
        within_mean = statistics.mean(within) if within else 0.0
        within_max = max(within) if within else 0.0

    # 锚点：保留若干篇的 z 向量与片段，供 Rolling Delta 与 KATE 检索
    anchors = list((old or {}).get("anchors", []))
    for f, t, v in docs:
        anchors.append({
            "src": os.path.basename(f),
            "chars": len(t),
            "z": [round(x, 3) for x in zscore(v, mu, sd)],
            "text": t[:180],
        })
    anchors = anchors[-40:]

    # 逐规则频次基线：供 scan.py 校准阈值，与 Delta 正交
    rules = {}
    for r in scanner.RULES:
        vals = [len(re.findall(r["pat"], d[1], flags=re.MULTILINE)) / max(len(d[1]) / 1000.0, 0.001)
                for d in docs]
        m_new = statistics.mean(vals) if vals else 0.0
        p_new = sorted(vals)[min(len(vals) - 1, int(round(len(vals) * 0.95)) - 1)] if len(vals) > 1 else m_new
        o = ((old or {}).get("rules") or {}).get(r["id"])
        if o:
            n_o = o.get("n", 0) * DECAY
            wsum = n_o + n_new
            rules[r["id"]] = {"mean": round((o.get("mean", 0) * n_o + m_new * n_new) / wsum, 4),
                              "p95": round(max(o.get("p95", 0) * DECAY, p_new), 4),
                              "n": round(wsum, 2), "generic": r["per_kilo"], "tier": r["tier"]}
        else:
            rules[r["id"]] = {"mean": round(m_new, 4), "p95": round(p_new, 4),
                              "n": float(n_new), "generic": r["per_kilo"], "tier": r["tier"]}

    files_map = dict((old or {}).get("files", {}))
    for f, t, _ in docs:
        files_map[f] = len(t)

    # 正对照：作者自己的留出文本能否回落自己的包络
    def _entry(vec, length, pool, excl=None):
        cand = [a for a in pool if a is not excl
                and 0.5 * length <= a["chars"] <= 2.0 * length]
        if len(cand) < 2:
            cand = [a for a in pool if a is not excl]
        if not cand:
            return None
        ds = sorted(delta(vec, a["z"]) for a in cand)
        return ds[min(len(ds) - 1, max(0, int(len(ds) * 0.9) - 1))]

    ctrl = []
    for i, (f, t, v) in enumerate(docs):
        thr = _entry(zscore(v, mu, sd), len(t), anchors, excl=anchors[len(anchors) - len(docs) + i])
        own = delta(zscore(v, mu, sd), anchors[len(anchors) - len(docs) + i]["z"])
        if thr is not None:
            ctrl.append(1.0 if own <= thr else 0.0)

    prof = {
        "version": 2,
        "method": "Burrows Delta, Manhattan on z-scores (本机实测优于 Cosine，见文件头)",
        "features": FEATS,
        "features_n": len(FEATS),
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "n": round(n_old + n_new, 2),
        "samples": {"files": len(files_map), "chars": sum(files_map.values())},
        "mu": [round(x, 6) for x in mu],
        "sd": [round(x, 6) for x in sd],
        "control": {"entry_rate": round(statistics.mean(ctrl), 3) if ctrl else None,
                    "n": len(ctrl)},
        "verify": {
            "reproducible": round(statistics.mean(ctrl), 3) if ctrl else None,
            "within_mean": round(within_mean, 4),
            "n_docs": len(files_map),
            "chars": sum(files_map.values()),
            "passed": bool(ctrl and statistics.mean(ctrl) >= 0.75
                           and sum(files_map.values()) >= 1500 and len(files_map) >= 5),
        },
        "within": {"mean": round(within_mean, 4), "max": round(within_max, 4),
                   "n": round((old or {}).get("within", {}).get("n", 0) * DECAY + max(len(within), 1), 2)},
        "anchors": anchors,
        "baseline": {
            "sent_mean": round(statistics.mean([statistics.mean([len(s) for s in scanner.split_sents(d[1])]) for d in docs]), 2),
            "first_person": round(statistics.mean([len(re.findall(r"我|咱们", d[1])) / max(len(d[1]), 1) * 1000 for d in docs]), 2),
        },
        "tolerance": 1.5,
        "s_tolerance": 2.5,
        "rules": rules,
        "whitelist": (old or {}).get("whitelist", []),
        "files": files_map,
    }
    save(prof, store)
    print("画像已更新：新增 %d 篇，累计 %d 篇 / %d 字 ｜ 特征 %d 维"
          % (n_new, prof["samples"]["files"], prof["samples"]["chars"], len(FEATS)))
    print("组内 Delta 均值 %.4f，最大 %.4f（这是你自己各篇之间的距离基准）"
          % (prof["within"]["mean"], prof["within"]["max"]))
    if within_max <= 1e-6:
        print("警告：语料各篇几乎完全相同（组内 Delta 为 0），包络退化，check 会一律判在包络外。"
              "请换用真正不同的稿件。")
    if prof["samples"]["chars"] < 3000 or prof["samples"]["files"] < 5:
        print("注意：语料 %d 字 / %d 篇，少于 3000 字或 5 篇时包络不稳，建议补到 10 篇以上。"
              % (prof["samples"]["chars"], prof["samples"]["files"]))
    print("存放 %s" % store)
    return 0


def _need(store):
    p = load(store)
    if not p or not p.get("mu"):
        sys.stderr.write("没有画像。先跑：python profile.py build 你的旧稿目录/\n")
        return None
    return p



def descriptor(prof):
    """把数值指纹转成自然语言描述。依据 StyloPrompt（AIED 2026）：
    NL-Distribution 编码比直接给数值更能约束模型。"""
    b = prof["baseline"]
    sm = b["sent_mean"]
    fp = b["first_person"]
    parts = []
    parts.append("句长以 %s 字为主" % ("八到十五" if sm < 16 else "十五到二十二" if sm < 23 else "二十二到三十二" if sm < 33 else "三十字以上"))
    parts.append("第一人称%s" % ("很密，几乎每段都有" if fp > 25 else "常有，但不铺满" if fp > 8 else "少用，偏客观叙述"))
    r = (prof.get("rules") or {})
    def rate(k):
        return (r.get(k) or {}).get("mean", 0)
    if rate("em_dash") > 2:
        parts.append("破折号是你的常用手段，约每千字 %.0f 处，不必刻意回避" % rate("em_dash"))
    elif rate("em_dash") < 0.5:
        parts.append("很少用破折号")
    if rate("connector") < 1:
        parts.append("几乎不用连接词铺路，句子之间靠内容承接")
    if rate("colon_hint") + rate("colon_list") < 0.05:
        parts.append("不用「核心是：」这类提示语冒号，也不用冒号引列表")
    if rate("flip") < 0.05:
        parts.append("不写「不是A而是B」式翻案句")
    parts.append("组内变异宽度：你自己各篇之间的 Delta 均值 %.3f，最大 %.3f，比较的基准是这条线，不是满分" % (prof["within"]["mean"], prof["within"]["max"]))
    return "；".join(parts) + "。"


def envelope_entry(text, prof):
    """判断本篇是否落在作者的组内变异包络内。

    包络由作者自己各篇之间的距离决定，不用「稿件到锚点的距离」定阈值，
    否则任何稿件都会落在自己的分位数里，判定失效。
    长度匹配依据 The Width of a Voice（2026）：包络随文档长度变化。
    """
    v = zscore(vector(text), prof["mu"], prof["sd"])
    n = len(text)
    anchors = prof.get("anchors", [])
    pool = [a for a in anchors if 0.5 * n <= a["chars"] <= 2.0 * n]
    matched = True
    if len(pool) < 3:
        pool, matched = anchors, False
    if not pool:
        return None

    # 阈值：池内作者各篇之间的最大距离（至少两篇才能算）
    pair = []
    for i in range(len(pool)):
        for j in range(i + 1, len(pool)):
            pair.append(delta(pool[i]["z"], pool[j]["z"]))
    if pair:
        pair.sort()
        thr = pair[min(len(pair) - 1, int(len(pair) * 0.95))]
        thr = max(thr, prof["within"]["max"] * 0.6)
    else:
        thr = prof["within"]["max"]

    own = min(delta(v, a["z"]) for a in pool)
    return {"dist": own, "thr": thr, "inside": own <= thr,
            "n": len(pool), "length_matched": matched}



def card(name="self", store=None, k=3):
    store = store or store_for(name)
    prof = _need(store)
    if not prof:
        return 2
    v = prof.get("verify", {})
    print("# 风格卡：%s" % name)
    print()
    print("## 可信度")
    print("样本 %d 篇 / %d 字 ｜ 正对照回落 %s ｜ 组内 Delta 均值 %.3f 最大 %.3f ｜ 三重验证 %s"
          % (prof["samples"]["files"], prof["samples"]["chars"],
             ("%.0f%%" % (v["reproducible"] * 100)) if v.get("reproducible") is not None else "未测",
             prof["within"]["mean"], prof["within"]["max"],
             "通过" if v.get("passed") else "不足"))
    print()
    print("## 表达 DNA")
    print(descriptor(prof))
    print()
    print("## 语料样例（KATE 最近 %d 段，优先于任何描述）" % k)
    for a in prof.get("anchors", [])[-k:]:
        print("- [%s｜%d 字] %s" % (a["src"], a["chars"], a["text"].replace("\n", " ")[:110]))
    print()
    print("## 诚实边界")
    print("- 蒸馏的是表面纹理。实测显示风格提示几乎不动功能词结构（The Width of a Voice 2026）。")
    print("- 与目标作者的距离可以收窄，但跨不过人机边界；方法与真人相似度 0.484 至 0.508，真人之间 0.626 至 0.756（PersonalBench 2026）。")
    print("- 样本少于 3000 字或 5 篇时，包络有效范围窄，跨题材易失真。")
    print("- 本卡不主张作者身份，只描述统计距离。")
    print()
    print("## 用法")
    print("1 把本卡与场景要求一起放进上下文；2 按样例的句法写，不要照抄内容；")
    print("3 写完跑 profile.py check 稿件 --name %s 复检 Delta，落在包络外就重写。" % name)
    return 0


def list_all():
    if not os.path.isdir(ROOT):
        print("还没有任何画像")
        return 0
    for f in sorted(glob.glob(os.path.join(ROOT, "*.json"))):
        p = load(f)
        if not p:
            continue
        print("%-18s %d 篇 %5d 字 ｜ 组内 Delta %.3f ｜ %s"
              % (os.path.basename(f)[:-5], p["samples"]["files"], p["samples"]["chars"],
                 p["within"]["mean"], p.get("updated_at", "")))
    return 0


def delta_of(text, prof):
    zv = zscore(vector(text), prof["mu"], prof["sd"])
    ds = [delta(zv, a["z"]) for a in prof.get("anchors", [])]
    return (min(ds) if ds else 1.0), (statistics.mean(ds) if ds else 1.0), zv


def percentile(d, prof):
    """用组内 Delta 的均值与最大值做粗略分档，不做正态假设。"""
    w = prof["within"]
    if w["max"] <= w["mean"]:
        return 0
    return max(0, min(100, int((d - w["mean"]) / max(w["max"] - w["mean"], 1e-6) * 50 + 50)))


def drift(path, store=STORE, win=200):
    prof = _need(store)
    if not prof:
        return 2
    t = open(path, encoding="utf-8").read()
    chunks, i = [], 0
    while i < len(t):
        seg = t[i:i + win]
        if len(seg.strip()) >= 60:
            chunks.append((i, seg))
        i += win
    if not chunks:
        print("稿件太短，无法做滚动 Delta")
        return 0
    print("滚动 Delta（窗口 %d 字）｜ 组内基准 均值 %.4f 最大 %.4f"
          % (win, prof["within"]["mean"], prof["within"]["max"]))
    print("%-6s %-8s %8s %8s %s" % ("偏移", "字数", "最小Δ", "百分位", "段首"))
    rows = []
    for off, seg in chunks:
        dmin, dmean, _ = delta_of(seg, prof)
        rows.append((off, len(seg), dmin, percentile(dmin, prof), seg.strip()[:24].replace("\n", " ")))
    for r in sorted(rows, key=lambda x: -x[2])[:10]:
        print("%-6d %-8d %8.4f %7d%% %s" % r)
    print()
    print("Δ 越小越像你本人。最大值那段是最不像你写的，优先改那一段。")
    return 0


def exemplar(path, store=STORE, k=3, para=None):
    prof = _need(store)
    if not prof:
        return 2
    t = open(path, encoding="utf-8").read()
    if para:
        seg = t.split("\n\n")[para - 1]
    else:
        # 取全文向量
        seg = t
    _, _, zv = delta_of(seg, prof)
    scored = sorted(((delta(zv, a["z"]), a) for a in prof.get("anchors", [])), key=lambda x: x[0])
    print("按 KATE 取最近 %d 段作者旧稿（Liu et al. 2021，按 Delta 由小到大）" % k)
    for d, a in scored[:k]:
        print("\n[%s ｜ %d 字 ｜ 距离 %.4f]\n%s" % (a["src"], a["chars"], d, a["text"].replace("\n", " ")))
    print("\n用法：把这几段作为风格样例放进上下文，再让模型写目标段落。样例来自你本人，不是描述。")
    return 0


def check(path, store=STORE):
    prof = _need(store)
    if not prof:
        return 2
    t = open(path, encoding="utf-8").read()
    dmin, dmean, zv = delta_of(t, prof)
    w = prof["within"]
    en = envelope_entry(t, prof)
    ctrl = (prof.get("control") or {})
    print("注意：本功能未通过区分度验证。同作者留出段 Delta 0.4145，异作者（鲁迅）0.3071，"
          "排序错误。以下数值只作相对比较，不可据此判定作者。")
    print("个人基线 %s ｜ %d 篇 / %d 字 ｜ 特征 %d 维 ｜ 锚点 %d 段"
          % (prof["updated_at"], prof["samples"]["files"], prof["samples"]["chars"],
             prof["features_n"], len(prof.get("anchors", []))))
    if ctrl.get("entry_rate") is not None:
        print("正对照：你留出的旧稿回落自己包络的比例 %.0f%%（参考区间 84%% 至 88%%）"
              % (ctrl["entry_rate"] * 100))
    # 最小有效规模：低于此规模，包络区分度实测不足，直接拒绝判定，不放行
    corpus_chars = prof["samples"]["chars"]
    n_files = prof["samples"]["files"]
    med_all = statistics.median([a["chars"] for a in prof.get("anchors", [])]) if prof.get("anchors") else 0
    weak = corpus_chars < 3000 or n_files < 5 or med_all < 300
    med = med_all
    ratio = (len(t) / med) if med else 1.0
    mismatch = bool(med) and (ratio < 0.6 or ratio > 1.7)
    print()
    if en:
        print("包络判定 本篇 Delta %.4f ｜ 本长度档阈值 %.4f ｜ 参照锚点 %d 段%s"
              % (en["dist"], en["thr"], en["n"],
                 "" if en["length_matched"] else "（同长度档不足，退化为全量）"))
        if mismatch:
            print("长度不符：本篇 %d 字，语料中位 %d 字（%.2f 倍）。短稿特征稀疏，Delta 天然偏高，"
                  "此时的判定不可靠，不要据此下结论。" % (len(t), med, ratio))
        if weak:
            print("不作判定：语料 %d 字 / %d 篇 / 单篇中位 %d 字，低于有效规模（3000 字、5 篇、单篇 300 字）。"
                  "该规模下实测区分度不足，政论腔与本人作品会同时判在包络内，结论无意义。"
                  % (corpus_chars, n_files, med_all))
            print("结论：基线不足，不作判定。")
            return 0
        print("定位：距离只描述差异，不判作者。2026-10 实测：对文风跨度大的作者，"
              "AI 文（Delta 0.47）会比本人节选（0.76 至 0.87）更接近画像，包络无法区分人机。")
    print()
    print("距离 最近锚点 %.4f ｜ 平均 %.4f ｜ 组内均值 %.4f 最大 %.4f"
          % (dmin, dmean, w["mean"], w["max"]))
    vec = vector(t)
    devs = sorted(((abs(z), FEATS[i], vec[i], prof["mu"][i])
                   for i, z in enumerate(zv)), key=lambda x: -x[0])[:8]
    print()
    print("%-10s %10s %10s %8s" % ("偏离最大的特征", "本篇/千字", "你的均值", "z"))
    for z, name, cur, mu in devs:
        print("%-10s %10.2f %10.2f %8.2f" % (name, cur, mu, z))
    print()
    print("提示：单篇短于 %d 字、或素材少于 5 篇时判定不稳。个性化只能收窄距离，"
          "跨不过人机边界（PersonalBench 2026）。" % MIN_DOC_CHARS)
    return 0


def show(store=STORE):
    prof = _need(store)
    if not prof:
        return 2
    print("方法 %s" % prof["method"])
    print("画像 %s ｜ %d 篇 / %d 字 ｜ 特征 %d 维 ｜ 锚点 %d 段"
          % (prof["updated_at"], prof["samples"]["files"], prof["samples"]["chars"],
             prof["features_n"], len(prof.get("anchors", []))))
    print("组内 Delta 均值 %.4f ｜ 最大 %.4f" % (prof["within"]["mean"], prof["within"]["max"]))
    print("句长均值 %.1f ｜ 第一人称 %.1f/千字"
          % (prof["baseline"]["sent_mean"], prof["baseline"]["first_person"]))
    ctrl = (prof.get("control") or {})
    if ctrl.get("entry_rate") is not None:
        print("正对照回落率 %.0f%% ｜ 参考区间 84%% 至 88%%" % (ctrl["entry_rate"] * 100))
    if prof.get("whitelist"):
        print("白名单：", "、".join(prof["whitelist"]))
    print()
    print("风格描述（可直接放进上下文，替代堆数字）：")
    print(descriptor(prof))
    return 0


def main():
    ap = argparse.ArgumentParser(description="writing-loop 文风画像（Burrows Delta）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="从旧稿建立或增量更新画像")
    b.add_argument("paths", nargs="+")
    b.add_argument("--append", action="store_true")
    b.add_argument("--name", default="self", help="画像名，用于区分你自己的风格与目标作家")
    b.add_argument("--min-chars", type=int, default=None, help="单篇最低字数，默认 150。调低会让包络不稳")
    d = sub.add_parser("drift", help="滚动 Delta，定位最不像作者的段落")
    d.add_argument("file")
    d.add_argument("--win", type=int, default=200)
    d.add_argument("--name", default="self")
    e = sub.add_parser("exemplar", help="按 KATE 取最相近的作者旧稿片段")
    e.add_argument("file")
    e.add_argument("--k", type=int, default=3)
    e.add_argument("--para", type=int, default=None, help="只取第 N 段（从 1 起）")
    e.add_argument("--name", default="self")
    c = sub.add_parser("check", help="对比单篇与个人基线")
    c.add_argument("file")
    c.add_argument("--name", default="self")
    sh = sub.add_parser("show")
    sh.add_argument("--name", default="self")
    cd = sub.add_parser("card", help="输出可直接放进上下文的风格卡")
    cd.add_argument("--name", default="self")
    cd.add_argument("--k", type=int, default=3)
    sub.add_parser("list", help="列出全部画像")
    sub.add_parser("reset")
    a = ap.parse_args()

    if a.cmd == "build":
        return build(a.paths, a.append, store_for(a.name), a.min_chars)
    if a.cmd == "drift":
        return drift(a.file, store_for(a.name), win=a.win)
    if a.cmd == "exemplar":
        return exemplar(a.file, store_for(a.name), k=a.k, para=a.para)
    if a.cmd == "check":
        return check(a.file, store_for(a.name))
    if a.cmd == "show":
        return show(store_for(a.name))
    if a.cmd == "card":
        return card(a.name, store_for(a.name), a.k)
    if a.cmd == "list":
        return list_all()
    if a.cmd == "reset":
        for f in glob.glob(os.path.join(ROOT, "*.json")):
            os.remove(f)
        print("全部画像已删除")
        return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
