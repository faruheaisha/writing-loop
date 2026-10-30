#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2026 faruheaisha
# SPDX-License-Identifier: GPL-3.0-only
"""writing-loop 文风画像（v2.2：整句窗口滚动 Delta + 单遍向量化 + 全命令 .docx 与 JSON 支持）

方法出处（新近为主，经典方法仅作底座）
  The Width of a Voice: Placing Machine Imitation Inside Authors' Own Variation,
    Zenodo preprint v0.5.5, 2026-07（投 CHR 2027）。在 15 位已出版小说家上按 Burrows
    Delta 建立逐作者、按长度匹配的组内变异包络；留出自身文本回落包络率 84% 至 88%，
    作为正对照。给出作者原文片段优于只给作者名。
  StyloPrompt, AIED 2026（arXiv 收录）：把文体指纹转成自然语言描述比直接给数值更
    有效，NL-Distribution 编码在跨风格迁移上达 89% 成功率。本文件的 descriptor 照此。
  PersonalBench, 2026：推理时个性化能把输出调节到可区分（AUC 0.918），但跨不过
    人机边界；所有方法与真实作者的相似度 0.484 至 0.508，低于人类之间 0.626 至
    0.756。故本文件从不声称能让人写出「像你」的稿子，只报距离。
  Burrows 2002, Delta: A Measure of Stylistic Difference and a Guide to Likely
    Authorship, Literary and Linguistic Computing.
  Jannidis et al. 2015 / Smith & Aldridge 2011：本机短文本稀疏特征实测经典 Manhattan
    优于 Cosine，故采用经典 Manhattan。
  Liu et al. 2021（KATE）：按最近距离取 k 个样例作上下文示例，优于随机抽样。

用法
  python style_profile.py build 旧稿目录/ [--append]
  python style_profile.py drift 新稿.docx
  python style_profile.py exemplar 新稿.md --k 3
  python style_profile.py check 新稿.docx
"""
import argparse
import glob
import json
import math
import os
import re
import statistics
import sys
from datetime import datetime

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import scan as scanner  # noqa: E402

ROOT = os.environ.get("WRITING_LOOP_HOME") or os.path.join(
    os.path.expanduser("~"), ".writing-loop", "profiles")
STORE = os.path.join(ROOT, "self.json")

DECAY = 0.85
TEXT_EXT = scanner.TEXT_EXT
DOCX_EXT = scanner.DOCX_EXT
read_docx = scanner.read_docx

MIN_DOC_CHARS = 150
MAX_DOC_CHARS = 12000
N_FEATURES = 260


def store_for(name):
    root = os.environ.get("WRITING_LOOP_HOME") or ROOT
    safe = re.sub(r"[^\w\u4e00-\u9fff-]", "_", name)[:40] or "self"
    return os.path.join(root, safe + ".json")


# 中文功能词：严格剔除易与实词词素混淆的题材单字（如人、一、上、中、下、对、要、会、说、发等）
FUNC = """因为 所以 如果 虽然 即使 只是 已经 还是 还有 一些 怎么 为什么 时候 我们 他们
可以 应该 需要 能够 进行 通过 根据 以及 并且 而且 因此 但是 然而 不过 就是 一直 总是
常常 可能 大概 也许 其实 比较 里面 外面 上面 下面 前面 后面 之间 之后 之前 当时 现在
原来 本来 确实 显然 当然 一般 通常 往往 有时 有些 很多 不少 一点 完全 非常 特别 十分
相当 稍微 几乎 至少 的 了 着 过 吗 呢 吧 啊 却 则 若 虽 既 越 更 最 太 又 再 才 仅
都 也 还 把 被 让 给 从 向 其 之"""

PUNCT_ITEMS = ["，", "。", "、", "；", "：", "？", "！", "——", "…", "（", "）", "“", "”", "「", "」", "《", "》"]

SL_BINS = [(0, 10), (11, 20), (21, 35), (36, 60), (61, 10 ** 6)]


def feature_names():
    out = []
    seen = set()
    for w in FUNC.split():
        tag = "fw:" + w
        if tag not in seen:
            seen.add(tag)
            out.append(tag)
    for p in PUNCT_ITEMS:
        tag = "p:" + p
        if tag not in seen:
            seen.add(tag)
            out.append(tag)
    for a, b in SL_BINS:
        tag = "sl:%d-%d" % (a, b if b < 10 ** 6 else 999)
        if tag not in seen:
            seen.add(tag)
            out.append(tag)
    return out[:N_FEATURES]


FEATS = feature_names()
# 模块加载期预排功能词长度并解析特征规格，消除每次 vector() 重复排序与五次切句开销
_FW_KEYS_SORTED = sorted([f[3:] for f in FEATS if f.startswith("fw:")], key=lambda x: -len(x))
_FEAT_SPECS = []
for _fn in FEATS:
    _kind, _key = _fn.split(":", 1)
    if _kind == "sl":
        _lo, _hi = [int(x) for x in _key.split("-")]
        _FEAT_SPECS.append((_kind, (_lo, _hi)))
    else:
        _FEAT_SPECS.append((_kind, _key))


def vector(text):
    """相对频率向量：先剥离 Markdown 非正文块，再按长词优先遮罩统计功能词，单次切句分箱，按正文字数归一。"""
    clean = scanner.strip_md_for_structure(text)
    if "￭" in clean:
        clean = clean.replace("￭", "")
    if not clean.strip():
        clean = text
    n = max(len(clean), 1)

    fw_counts = {}
    buf = clean
    for k in _FW_KEYS_SORTED:
        c = buf.count(k)
        fw_counts[k] = c
        if len(k) > 1 and c > 0:
            buf = buf.replace(k, "\ufffd" * len(k))

    slens = [len(s) for s in scanner.split_sents(clean)]
    v = []
    for kind, key in _FEAT_SPECS:
        if kind == "fw":
            c = fw_counts.get(key, 0)
        elif kind == "p":
            c = clean.count(key)
        else:
            lo, hi = key
            c = sum(1 for sl in slens if lo <= sl <= hi)
        v.append(c / n * 1000.0)
    return v


Z_CAP = 4.0


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
    return sum(abs(x - y) for x, y in zip(a, b)) / max(len(a), 1)


def delta(a, b):
    return mean_abs_dev(a, b)


def _clean_excerpt(text, max_chars=260):
    """跳过 Markdown 非正文块与标题行，按完整句末标点截取干净的原文片段供 few-shot 使用。"""
    struct = scanner.strip_md_for_structure(text)
    lines = [ln.replace("￭", "").strip() for ln in struct.splitlines()
             if ln.replace("￭", "").strip()]
    body = "\n".join(lines).strip() or text.strip()
    if len(body) <= max_chars:
        return body
    cut = body[:max_chars]
    last_end = max(cut.rfind("。"), cut.rfind("！"), cut.rfind("？"), cut.rfind("\n"))
    if last_end >= 80:
        return cut[:last_end + 1].strip()
    return cut.strip()


def load(store=STORE):
    if not os.path.isfile(store):
        legacy = os.path.join(os.path.expanduser("~"), ".workbuddy", "writing-loop",
                              "profiles", os.path.basename(store))
        if os.path.isfile(legacy):
            store = legacy
        else:
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
        elif os.path.isfile(p) and p.lower().endswith(TEXT_EXT + DOCX_EXT):
            files.append(p)
    return sorted(set(files))


def build(paths, append=False, store=STORE, min_chars=None):
    files = collect(paths)
    if not files:
        sys.stderr.write("没有找到 .md、.txt 或 .docx 稿件\n")
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
            t = scanner.read_text(f)[:MAX_DOC_CHARS]
        except Exception as e:
            sys.stderr.write("跳过 %s：%s\n" % (f, e))
            continue
        if len(t.strip()) < (min_chars or MIN_DOC_CHARS):
            continue
        docs.append((os.path.abspath(f), t, vector(t)))
    if not docs:
        lens = []
        for f in todo:
            if not os.path.isfile(f):
                continue
            try:
                lens.append(len(scanner.read_text(f).strip()))
            except Exception:
                pass
        lens = sorted(lens, reverse=True)[:5]
        sys.stderr.write(
            "所有稿件都短于 %d 字，无法建模。文体距离需要足够长的样本。\n"
            "  你给的最长几篇：%s 字\n"
            "  三条出路：改用更长的稿件；把同一主题的多篇合并成一篇；先只建锚点（build --min-chars 调低，但结果不稳）。\n"
            % (min_chars or MIN_DOC_CHARS, lens or ["?"]))
        return 2

    # 均值方差：新增样本与旧画像按衰减权重合并（平行轴定理补齐组间均值差平方项）
    n_new = len(docs)
    n_old = (old or {}).get("n", 0) * DECAY
    mu_new = [statistics.mean(d[2][i] for d in docs) for i in range(len(FEATS))]
    sd_new = [statistics.pstdev([d[2][i] for d in docs]) if n_new > 1 else 0.0
              for i in range(len(FEATS))]
    if old and old.get("mu") and len(old["mu"]) == len(FEATS):
        w = n_old + n_new
        mu = [(o * n_old + n_ * n_new) / w for o, n_ in zip(old["mu"], mu_new)]
        sd = []
        for o_mu, n_mu, c_mu, o_sd, n_sd in zip(old["mu"], mu_new, mu, old.get("sd", sd_new), sd_new):
            v_old = (o_sd ** 2) + (o_mu - c_mu) ** 2
            v_new = (n_sd ** 2) + (n_mu - c_mu) ** 2
            combined_var = (v_old * n_old + v_new * n_new) / max(w, 1e-6)
            sd.append(math.sqrt(max(combined_var, 0.0)))
    else:
        mu, sd = mu_new, sd_new
    sd = [s if s > 1e-6 else 1e-6 for s in sd]

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

    anchors = list((old or {}).get("anchors", []))
    new_anchor_objs = []
    for f, t, v in docs:
        a_obj = {
            "src": os.path.basename(f),
            "chars": len(t),
            "z": [round(x, 3) for x in zscore(v, mu, sd)],
            "text": _clean_excerpt(t, 260),
        }
        anchors.append(a_obj)
        new_anchor_objs.append(a_obj)
    anchors = anchors[-40:]

    # 逐规则频次基线：先行遮罩引号内他人引文与 Markdown 非正文块，避免引语污染作者个人习惯
    masked_docs = [(scanner.mask(d[1], []), max(len(d[1]) / 1000.0, 0.001)) for d in docs]
    rules = {}
    for r in scanner.RULES:
        cre = scanner.compiled_rule(r)
        vals = [len(cre.findall(m_txt)) / kilo_d for m_txt, kilo_d in masked_docs]
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

    sm_vals, fp_vals = [], []
    for d in docs:
        st_clean = scanner.strip_md_for_structure(d[1])
        st_sents = [len(s) for s in scanner.split_sents(st_clean)]
        sm_vals.append(statistics.mean(st_sents) if st_sents else len(d[1]))
        narr_prose = scanner.QUOTE.sub("", st_clean).replace("￭", "")
        fp_vals.append(len(re.findall(r"我|咱们", narr_prose)) / max(len(narr_prose.strip()) or len(d[1]), 1) * 1000)
    sm_new = statistics.mean(sm_vals)
    fp_new = statistics.mean(fp_vals)
    if old and old.get("baseline"):
        ob = old["baseline"]
        w_b = max(n_old + n_new, 1e-6)
        sm_merged = (ob.get("sent_mean", sm_new) * n_old + sm_new * n_new) / w_b
        fp_merged = (ob.get("first_person", fp_new) * n_old + fp_new * n_new) / w_b
    else:
        sm_merged, fp_merged = sm_new, fp_new

    ctrl = []
    for (f, t, v), self_a in zip(docs, new_anchor_objs):
        zv_doc = zscore(v, mu, sd)
        cand = [a for a in anchors if a is not self_a and 0.5 * len(t) <= a["chars"] <= 2.0 * len(t)]
        if len(cand) < 2:
            cand = [a for a in anchors if a is not self_a]
        if len(cand) >= 2:
            pair_ds = sorted(delta(cand[x]["z"], cand[y]["z"])
                             for x in range(len(cand)) for y in range(x + 1, len(cand)))
            thr = pair_ds[min(len(pair_ds) - 1, max(0, int(len(pair_ds) * 0.9) - 1))]
            own = min(delta(zv_doc, a["z"]) for a in cand)
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
            "sent_mean": round(sm_merged, 2),
            "first_person": round(fp_merged, 2),
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
        sys.stderr.write("没有画像。先跑：python style_profile.py build 你的旧稿目录/\n")
        return None
    return p


def descriptor(prof):
    b = prof["baseline"]
    sm = b["sent_mean"]
    fp = b["first_person"]
    parts = []
    parts.append("句长以 %s 字为主" % (
        "八到十五" if sm < 16 else "十五到二十二" if sm < 23 else "二十二到三十二" if sm < 33 else "三十字以上"))
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
    parts.append("组内变异宽度：你自己各篇之间的 Delta 均值 %.3f，最大 %.3f，比较的基准是这条线，不是满分"
                 % (prof["within"]["mean"], prof["within"]["max"]))
    return "；".join(parts) + "。"


def envelope_entry(text, prof):
    v = zscore(vector(text), prof["mu"], prof["sd"])
    n = len(text)
    anchors = prof.get("anchors", [])
    pool = [a for a in anchors if 0.5 * n <= a["chars"] <= 2.0 * n]
    matched = True
    if len(pool) < 3:
        pool, matched = anchors, False
    if not pool:
        return None

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


def select_exemplars(prof, query_text=None, k=3):
    anchors = prof.get("anchors", [])
    if not anchors:
        return []
    if query_text and query_text.strip():
        target_z = zscore(vector(query_text), prof["mu"], prof["sd"])
    else:
        target_z = [0.0] * len(prof.get("mu", FEATS))
    scored = sorted(((delta(target_z, a["z"]), a) for a in anchors), key=lambda x: x[0])
    return [a for _, a in scored[:k]]


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
    print("## 代表性语料样例（中心最近 %d 段，优先于任何抽象描述）" % k)
    for a in select_exemplars(prof, None, k=k):
        print("- [%s｜%d 字] %s" % (a["src"], a["chars"], a["text"].replace("\n", " ")))
    print()
    print("## 诚实边界")
    print("- 蒸馏的是表面纹理。实测显示风格提示几乎不动功能词结构（The Width of a Voice 2026）。")
    print("- 与目标作者的距离可以收窄，但跨不过人机边界；方法与真人相似度 0.484 至 0.508，真人之间 0.626 至 0.756（PersonalBench 2026）。")
    print("- 样本少于 3000 字或 5 篇时，包络有效范围窄，跨题材易失真。")
    print("- 本卡不主张作者身份，只描述统计距离。")
    print()
    print("## 用法")
    print("1 用 kickoff.py --profile %s 自动将本卡 DNA 与最近邻样例注入开局；" % name)
    print("2 写完跑 loop.py 或 style_profile.py check 复检 Delta。")
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
    w = prof["within"]
    if w["max"] <= w["mean"]:
        return 0
    return max(0, min(100, int((d - w["mean"]) / max(w["max"] - w["mean"], 1e-6) * 50 + 50)))


def _sentence_windows(text, win=200):
    """按完整句界聚合滚动窗口，避免硬切截断多字功能词与伪造短残句污染句长分箱。"""
    chunks = []
    buf = ""
    start = None
    for m in re.finditer(r"[^。！？；\n]*[。！？；\n]+|[^\n]+$", text):
        piece = m.group()
        if not piece:
            continue
        off = m.start()
        if len(piece) > win * 1.6:
            if buf.strip() and len(buf.strip()) >= 60:
                chunks.append((start, buf))
            buf, start = "", None
            for k in range(0, len(piece), win):
                sub_s = piece[k:k + win]
                if len(sub_s.strip()) >= 60:
                    chunks.append((off + k, sub_s))
            continue
        if start is None:
            start = off
        if buf and len(buf) + len(piece) > win and len(buf.strip()) >= 60:
            chunks.append((start, buf))
            start, buf = off, piece
        else:
            buf += piece
    if buf.strip() and len(buf.strip()) >= 60:
        chunks.append((start if start is not None else 0, buf))
    return chunks


def drift(path, store=STORE, win=200, as_json=False):
    prof = _need(store)
    if not prof:
        return 2
    t = scanner.read_text(path)
    line_starts = scanner.build_line_index(t)
    chunks = _sentence_windows(t, win=win)
    if not chunks:
        if as_json:
            print(json.dumps({"ok": True, "windows": [], "note": "稿件太短，无法做滚动 Delta"},
                             ensure_ascii=False, indent=2))
        else:
            print("稿件太短，无法做滚动 Delta")
        return 0
    rows = []
    for off, seg in chunks:
        dmin, _, _ = delta_of(seg, prof)
        l_s, l_e = scanner.offset_span_to_lines(t, off, len(seg), line_starts)
        rows.append({
            "line_start": l_s,
            "line_end": l_e,
            "chars": len(seg),
            "delta_min": round(dmin, 4),
            "percentile": percentile(dmin, prof),
            "head": seg.strip()[:26].replace("\n", " "),
        })
    rows.sort(key=lambda x: -x["delta_min"])
    if as_json:
        print(json.dumps({
            "ok": True,
            "window": win,
            "within": prof["within"],
            "windows": rows,
        }, ensure_ascii=False, indent=2))
        return 0
    print("滚动 Delta（整句窗口 ~%d 字）｜ 组内基准 均值 %.4f 最大 %.4f"
          % (win, prof["within"]["mean"], prof["within"]["max"]))
    print("%-11s %-7s %8s %8s %s" % ("行号区间", "字数", "最小Δ", "百分位", "段首"))
    for r in rows[:10]:
        l_tag = "行%d-%d" % (r["line_start"], r["line_end"])
        print("%-11s %-7d %8.4f %7d%% %s"
              % (l_tag, r["chars"], r["delta_min"], r["percentile"], r["head"]))
    print()
    print("Δ 越小越像你本人。最大值那段偏离最远，优先按行号区间改那一段。")
    return 0


def exemplar(path, store=STORE, k=3, para=None):
    prof = _need(store)
    if not prof:
        return 2
    t = scanner.read_text(path)
    if para:
        paras = [p for p in t.split("\n\n") if p.strip()]
        seg = paras[min(max(para - 1, 0), len(paras) - 1)] if paras else t
    else:
        seg = t
    _, _, zv = delta_of(seg, prof)
    scored = sorted(((delta(zv, a["z"]), a) for a in prof.get("anchors", [])), key=lambda x: x[0])
    print("按 KATE 取最近 %d 段作者旧稿（Liu et al. 2021，按 Delta 由小到大）" % k)
    for d, a in scored[:k]:
        print("\n[%s ｜ %d 字 ｜ 距离 %.4f]\n%s" % (a["src"], a["chars"], d, a["text"].replace("\n", " ")))
    print("\n用法：把这几段作为风格样例放进上下文，再让模型写目标段落。样例来自你本人，不是描述。")
    return 0


def check(path, store=STORE, as_json=False):
    prof = _need(store)
    if not prof:
        return 2
    t = scanner.read_text(path)
    dmin, dmean, zv = delta_of(t, prof)
    w = prof["within"]
    en = envelope_entry(t, prof)
    ctrl = (prof.get("control") or {})
    corpus_chars = prof["samples"]["chars"]
    n_files = prof["samples"]["files"]
    med_all = statistics.median([a["chars"] for a in prof.get("anchors", [])]) if prof.get("anchors") else 0
    weak = corpus_chars < 3000 or n_files < 5 or med_all < 300
    med = med_all
    ratio = (len(t) / med) if med else 1.0
    mismatch = bool(med) and (ratio < 0.6 or ratio > 1.7)
    vec = vector(t)
    devs = sorted(((abs(z), FEATS[i], vec[i], prof["mu"][i])
                   for i, z in enumerate(zv)), key=lambda x: -x[0])[:8]
    if as_json:
        print(json.dumps({
            "ok": True,
            "samples": prof["samples"],
            "within": w,
            "envelope": en,
            "weak_corpus": weak,
            "length_mismatch": mismatch,
            "delta_min": round(dmin, 4),
            "delta_mean": round(dmean, 4),
            "top_deviations": [
                {"feature": name, "current_per_kilo": round(cur, 2),
                 "profile_mean": round(mu, 2), "abs_z": round(z, 2)}
                for z, name, cur, mu in devs
            ],
        }, ensure_ascii=False, indent=2))
        return 0
    print("个人基线 %s ｜ %d 篇 / %d 字 ｜ 特征 %d 维 ｜ 锚点 %d 段"
          % (prof["updated_at"], prof["samples"]["files"], prof["samples"]["chars"],
             prof["features_n"], len(prof.get("anchors", []))))
    if ctrl.get("entry_rate") is not None:
        print("正对照：你留出的旧稿回落自己包络的比例 %.0f%%（参考区间 84%% 至 88%%）"
              % (ctrl["entry_rate"] * 100))
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
    b.add_argument("--min-chars", type=int, default=None, help="单篇最低字数，默认 150")
    d = sub.add_parser("drift", help="滚动 Delta，定位最不像作者的段落")
    d.add_argument("file")
    d.add_argument("--win", type=int, default=200)
    d.add_argument("--name", default="self")
    d.add_argument("--json", action="store_true", help="输出 JSON")
    e = sub.add_parser("exemplar", help="按 KATE 取最相近的作者旧稿片段")
    e.add_argument("file")
    e.add_argument("--k", type=int, default=3)
    e.add_argument("--para", type=int, default=None, help="只取第 N 段（从 1 起）")
    e.add_argument("--name", default="self")
    c = sub.add_parser("check", help="对比单篇与个人基线")
    c.add_argument("file")
    c.add_argument("--name", default="self")
    c.add_argument("--json", action="store_true", help="输出 JSON")
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
        return drift(a.file, store_for(a.name), win=a.win, as_json=a.json)
    if a.cmd == "exemplar":
        return exemplar(a.file, store_for(a.name), k=a.k, para=a.para)
    if a.cmd == "check":
        return check(a.file, store_for(a.name), as_json=a.json)
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
