#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2026 faruheaisha
# SPDX-License-Identifier: GPL-3.0-only
"""写作闭环 · 一令全闭环驱动器（v2.2：扫描 + 分段检测 + 行号定位 + 改写守卫 + 个人包络核对）

一次跑完四件事：机械扫描、整篇与 400 字块分段检测、改写质量守卫、Burrows Delta 个人包络核对。
支持 .txt / .md / .docx 与带 UTF-8 BOM 稿件；短稿单块自动免除重复推理；所有分段直报 [行L1-L2]。

用法
  python loop.py 稿件.md
  python loop.py 稿件.docx --target 0.10 --segment 400
  python loop.py 稿件.md --json
  python loop.py 稿件.md --baseline 旧稿.md     # 顺带核验实词保留率与拆句红线

退出码：0 正常；2 输入问题；3 命中正文内部零宽字符作弊。
"""
import argparse
import json
import os
import re
import statistics
import subprocess
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
scanner = None


def load_scanner():
    """加载机械扫描模块 scan.py（检测引擎隔离在 score_batch.py 子进程）。"""
    global scanner
    if scanner is None:
        sys.path.insert(0, HERE)
        import scan as _s
        scanner = _s
    return scanner


def _engine_candidates():
    home = os.path.expanduser("~")
    name = "xiaoyu-chinese-ai-detect"
    return [
        # 优先使用同目录内嵌引擎
        os.path.join(HERE, "..", "engine", "scripts"),
        os.path.join(home, ".workbuddy", "skills", name, "scripts"),
        os.path.join(home, ".claude", "skills", name, "scripts"),
        os.path.join(home, ".agents", "skills", name, "scripts"),
        os.path.join(home, ".codex", "skills", name, "scripts"),
        os.path.join(os.getcwd(), ".claude", "skills", name, "scripts"),
        os.path.join(os.getcwd(), ".agents", "skills", name, "scripts"),
    ]


XIAOYU_CANDIDATES = _engine_candidates()


def _engine_dir():
    for d in XIAOYU_CANDIDATES:
        if os.path.isfile(os.path.join(d, "detect.py")):
            return d
    return None


def score_many(texts, bits=None, agg="eq"):
    """一次加载权重给多段文本打分（经 stdin 传纯 ASCII JSON，免除命令行超限与 Windows 编码乱码）。"""
    d = _engine_dir()
    if not d:
        return None, "找不到检测引擎 detect.py"
    payload = json.dumps({"texts": texts, "bits": bits, "agg": agg}, ensure_ascii=True)
    cmd = [sys.executable, os.path.join(HERE, "score_batch.py")]
    try:
        r = subprocess.run(cmd, input=payload, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=1800)
        out = json.loads(r.stdout)
    except Exception as e:
        err_tail = (r.stderr or "").strip().splitlines()[0] if "r" in locals() and r.stderr else str(e)[:120]
        return None, "批量打分调用失败：%s" % err_tail
    if not out.get("ok"):
        return None, out.get("error", "引擎未返回结果")
    return out, None


def chunk(text, target=400):
    """按段落聚合到 target 字左右。无换行的单段长文按句切分，避免整篇只出一块。"""
    raw = [(m.start(), m.group()) for m in re.finditer(r"[^\n]+(?:\n(?!\n))?", text)]
    parts = []
    for off, seg in raw:
        if len(seg) <= target * 1.5:
            parts.append((off, seg))
            continue
        cur, cur_off = "", off
        for sent in re.findall(r"[^。！？；\n]*[。！？；]?", seg):
            if not sent:
                continue
            if len(cur) + len(sent) > target and cur:
                parts.append((cur_off, cur))
                cur_off += len(cur)
                cur = sent
            else:
                cur += sent
        if cur:
            parts.append((cur_off, cur))
    out, buf, start = [], "", None
    for off, seg in parts:
        if start is None:
            start = off
        if len(buf) + len(seg) > target and len(buf) >= target * 0.5:
            out.append((start, buf))
            start, buf = off, seg
        else:
            buf += seg
    if buf.strip():
        out.append((start if start is not None else 0, buf))
    return out


STOP_CHARS = set("的了着过是在有和与及或但而就都也还把被让给从向对于之其我你他她它们这那")


def _content_bigrams(s):
    return {s[i:i + 2] for i in range(len(s) - 1)
            if ("\u4e00" <= s[i] <= "\u9fa5") and ("\u4e00" <= s[i + 1] <= "\u9fa5")
            and not (s[i] in STOP_CHARS or s[i + 1] in STOP_CHARS)}


def content_guard(new, old=None):
    """内容完整性守卫：剥离 Markdown 代码与表格等非正文块后，核算原稿实词真实召回率与 8 字重复噪声。"""
    sc_ = load_scanner()
    clean_new = sc_.strip_md_for_structure(new).replace("￭", "").strip() or new
    g = {}
    if old is not None:
        clean_old = sc_.strip_md_for_structure(old).replace("￭", "").strip() or old
        old_bg = _content_bigrams(clean_old)
        new_bg = _content_bigrams(clean_new)
        keep = len(old_bg & new_bg)
        g["retention"] = round(keep / max(len(old_bg), 1), 3)
    from collections import Counter
    grams = [clean_new[i:i + 8] for i in range(max(len(clean_new) - 7, 1))]
    rep = [g_ for g_, c in Counter(grams).items()
           if c >= 3 and any("\u4e00" <= ch <= "\u9fa5" for ch in g_)]
    g["noise_runs"] = len(rep)
    g["noise_sample"] = rep[:3]
    return g


def evaluate_revision(new_text, base_text):
    """完整改写质量守卫：合并实词保留率与字数变化（±20%）、句长中位数（15字，豁免原短句体裁）、拆句膨胀（1.6倍）红线。"""
    sc_ = load_scanner()
    guard = content_guard(new_text, base_text)
    if base_text is None:
        return guard
    c_base = sc_.strip_md_for_structure(base_text).replace("￭", "").strip() or base_text
    c_new = sc_.strip_md_for_structure(new_text).replace("￭", "").strip() or new_text
    b_s = [len(x) for x in sc_.split_sents(c_base)]
    n_s = [len(x) for x in sc_.split_sents(c_new)]
    delta_pct = round((len(c_new) - len(c_base)) / max(len(c_base), 1) * 100, 1)
    med_before = round(statistics.median(b_s), 1) if b_s else None
    med_after = round(statistics.median(n_s), 1) if n_s else None
    guard.update({
        "chars_before": len(c_base),
        "chars_after": len(c_new),
        "chars_delta": delta_pct,
        "sent_median_before": med_before,
        "sent_median_after": med_after,
    })
    warns = []
    if abs(delta_pct) > 20.0:
        warns.append("字数变化 %+.1f%%，超过 ±20%% 停止红线。" % delta_pct)
    if med_after is not None and med_after < 15.0:
        if med_before is None or med_before >= 15.0 or med_after < med_before * 0.85:
            warns.append("句长中位数降至 %.1f 字，低于 15 字停止红线，句子过碎。" % med_after)
    if b_s and len(n_s) > len(b_s) * 1.6:
        warns.append("句子数增加超过 60%，可能被过度拆碎了，读一遍。")
    ret = guard.get("retention")
    if ret is not None and ret < 0.85:
        warns.append("实词保留率 %.0f%%，低于 85%% 地板，改了字面也改了内容。" % (ret * 100))
    elif ret is not None and ret < 0.90:
        guard["hint"] = "实词保留率 %.0f%%，略低于 90%% 目标。" % (ret * 100)
    if warns:
        guard["warn"] = " ".join(warns)
    return guard


def _check_profile_envelope(text, prof):
    """在不新起进程的前提下顺带完成 Burrows Delta 包络核对（省去单独跑 style_profile.py check）。"""
    if not prof or not prof.get("mu") or not prof.get("anchors"):
        return None
    try:
        sys.path.insert(0, HERE)
        import style_profile as sp
        en = sp.envelope_entry(text, prof)
        if not en:
            return None
        corpus_chars = prof.get("samples", {}).get("chars", 0)
        n_files = prof.get("samples", {}).get("files", 0)
        med_all = statistics.median([a["chars"] for a in prof["anchors"]]) if prof["anchors"] else 0
        en["weak_corpus"] = bool(corpus_chars < 3000 or n_files < 5 or med_all < 300)
        return en
    except Exception:
        return None


def pct(p, nd=2):
    if p is None:
        return "—"
    return ("%." + str(nd) + "f%%") % (100.0 * p)


def main():
    ap = argparse.ArgumentParser(description="写作闭环 · 扫描 + 分段检测 + 改写守卫 + 包络核对")
    ap.add_argument("file", help="待检稿件文件（支持 .txt / .md / .docx）")
    ap.add_argument("--target", type=float, default=0.10, help="目标上限，默认 0.10")
    ap.add_argument("--segment", type=int, default=400, help="分段字数，默认 400。低于 120 字跳过")
    ap.add_argument("--bits", type=int, default=None, choices=[4, 8, 32], help="引擎权重档位")
    ap.add_argument("--agg", default="eq", choices=["eq", "len"], help="整篇聚合口径")
    ap.add_argument("--baseline", default=None, help="上一版稿件，用于核验改写质量守卫")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--no-detect", action="store_true", help="只跑机械扫描与守卫，不加载检测模型")
    ap.add_argument("--profile", default=None, help="文风画像 JSON")
    ap.add_argument("--no-profile", action="store_true", help="忽略个人画像")
    ap.add_argument("--whitelist", default=None, help="词汇白名单文本文件（每行一词）")
    a = ap.parse_args()

    if not os.path.isfile(a.file):
        sys.stderr.write("文件不存在：%s\n" % a.file)
        sys.exit(2)
    sc_ = load_scanner()
    text = sc_.read_text(a.file)
    if not text.strip():
        sys.stderr.write("文本为空\n")
        sys.exit(2)

    prof = None if a.no_profile else sc_.load_profile(a.profile)
    wl = None
    if a.whitelist:
        if not os.path.isfile(a.whitelist):
            sys.stderr.write("白名单文件不存在：%s\n" % a.whitelist)
            sys.exit(2)
        wl = [ln.strip() for ln in sc_.read_text(a.whitelist).splitlines()
              if ln.strip() and not ln.strip().startswith("#")]
    sc = sc_.scan(text, whitelist=wl, profile=prof)

    fatal = [i for i in sc["issues"] if i["tier"] == "X"]
    if fatal:
        sys.stderr.write("\n[拦截] 检出正文内部零宽字符。这类字符只会在编码转换时暴露，属于作弊\n"
                         "       不是写作。删干净再继续。\n\n")
        if not a.json:
            sys.stdout.write(sc_.render(sc) + "\n")
        sys.exit(3)

    det = {"available": False}
    segs = []
    line_starts = sc_.build_line_index(text)
    struct_masked = sc_.strip_md_for_structure(text)
    doc_prose = struct_masked.replace("￭", "").strip() or text

    prose_chunks = []
    for off, seg in chunk(text, a.segment):
        m_slice = struct_masked[off:off + len(seg)]
        p_seg = m_slice.replace("￭", "").strip()
        if len(p_seg) < 120:
            continue
        # 紧缩至真实正文起止偏移，避免行号区间虚跨 YAML 头或代码块
        rel_s = 0
        while rel_s < len(m_slice) and m_slice[rel_s] in ("￭", "\n", "\r", " ", "\t"):
            rel_s += 1
        rel_e = len(m_slice) - 1
        while rel_e > rel_s and m_slice[rel_e] in ("￭", "\n", "\r", " ", "\t"):
            rel_e -= 1
        prose_chunks.append((off + rel_s, rel_e - rel_s + 1, p_seg))

    if not a.no_detect:
        # 单块且与全文等价时只跑 1 次推理，避免短稿重复算两遍
        single_dup = (len(prose_chunks) == 1 and prose_chunks[0][2] == doc_prose)
        texts = [doc_prose] if single_dup else ([doc_prose] + [c[2] for c in prose_chunks])
        out, err = score_many(texts, a.bits, a.agg)
        if err:
            det = {"available": False, "error": err}
        else:
            items = out["items"]
            use_bits = out.get("bits") or a.bits or 4
            det = {"available": True, "doc": items[0], "bits": use_bits,
                   "agg": a.agg, "elapsed": out.get("elapsed")}
            chunk_items = [items[0]] if single_dup else items[1:]
            for (p_off, p_span, p_seg), it in zip(prose_chunks, chunk_items):
                if "error" in it:
                    continue
                l_start, l_end = sc_.offset_span_to_lines(text, p_off, p_span, line_starts)
                segs.append({
                    "offset": p_off,
                    "line_start": l_start,
                    "line_end": l_end,
                    "chars": len(p_seg),
                    "ai_prob": it["ai_prob"],
                    "verdict": it["verdict"],
                    "head": p_seg.replace("\n", " ")[:34],
                })
            segs.sort(key=lambda x: -x["ai_prob"])

    base_txt = None
    if a.baseline:
        if not os.path.isfile(a.baseline):
            sys.stderr.write("基线文件不存在：%s\n" % a.baseline)
            sys.exit(2)
        base_txt = sc_.read_text(a.baseline)
    guard = evaluate_revision(text, base_txt)
    prof_check = _check_profile_envelope(text, prof)

    if a.json:
        out = {"scan": sc, "detect": det, "segments": segs, "guard": guard,
               "profile_check": prof_check, "target": a.target}
        sys.stdout.write(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
        return

    lines = []
    lines.append("=" * 68)
    if det.get("available"):
        d = det["doc"]
        mark = "达标" if d["ai_prob"] <= a.target else "未达标"
        lines.append("整篇 AI 概率 %s（目标 ≤ %.0f%%，%s）｜ %s ｜ %s 聚合 ｜ %s 窗 ｜ %d 字"
                     % (pct(d["ai_prob"]), a.target * 100, mark, d["verdict"],
                        det["agg"], d["n_win"], d["chars"]))
        tier_lbl = "fp32" if det.get("bits") == 32 else ("int%s" % det.get("bits"))
        lines.append("权重 %s ｜ 检测引擎 v3.3 ｜ 批量去重推理（%d 分段），引擎耗时 %.2f 秒"
                     % (tier_lbl, len(segs), det.get("elapsed") or 0))
    else:
        if a.no_detect:
            lines.append("已按 --no-detect 跳过检测，只输出机械扫描与质量守卫。")
        else:
            lines.append("检测未执行：%s" % det.get("error", "找不到检测引擎"))
            lines.append("装好检测引擎依赖与权重即可启用；当前输出机械扫描与守卫结果。")
    if prof:
        def _v(x):
            return x.get("mean", 0) if isinstance(x, dict) else (x or 0)
        b = prof.get("baseline", {})
        p_line = "画像 %s ｜ %d 篇 %d 字 ｜ 句长均值 %.1f ｜ 组内 Delta 均值 %.3f" % (
            prof.get("updated_at", "?"), prof.get("samples", {}).get("files", 0),
            prof.get("samples", {}).get("chars", 0),
            _v(b.get("sent_mean")), _v(prof.get("within", {}).get("mean")))
        if prof_check:
            if prof_check.get("weak_corpus"):
                p_line += " ｜ 包络：样本未满 5 篇/3000 字暂不判定"
            else:
                tag = "包络内" if prof_check["inside"] else "偏离包络外"
                p_line += " ｜ 本篇 Delta %.3f（阈值 %.3f，%s）" % (
                    prof_check["dist"], prof_check["thr"], tag)
        lines.append(p_line)
    else:
        lines.append("未用个人画像，按通用阈值判定。跑 style_profile.py build 旧稿目录/ 可建基线。")
    lines.append("=" * 68)

    if segs:
        bad = [s for s in segs if s["ai_prob"] > a.target]
        lines.append("")
        lines.append("分段定位（每段独立作为文档打分，按概率降序，直接按行号改写）")
        lines.append("  %-11s %-7s %-7s %s" % ("行号区间", "字数", "概率", "段首"))
        for s in segs[:12]:
            flag = "  " if s["ai_prob"] <= a.target else ">>"
            l_tag = "行%d-%d" % (s["line_start"], s["line_end"])
            lines.append("%s%-11s %-7d %-7s %s" % (flag, l_tag, s["chars"],
                                                    pct(s["ai_prob"], 1), s["head"]))
        if len(segs) > 12:
            lines.append("   ……其余 %d 段均低于目标" % (len(segs) - 12))
        lines.append("")
        if bad:
            lines.append("需重写 %d 段（标 >> 的行号区间），优先从概率最高的开始。" % len(bad))
        else:
            lines.append("所有分段已达目标。")

    lines.append("")
    lines.append("-" * 68)
    lines.append(sc_.render(sc))
    if guard.get("noise_runs"):
        lines.append("")
        lines.append("内容完整性：检出 %d 处重复片段（如「%s」）。分数不可信，"
                     "这是噪声不是改写。" % (guard["noise_runs"], guard.get("noise_sample", [""])[0][:16]))
    if guard and "chars_before" in guard:
        lines.append("")
        lines.append("-" * 68)
        lines.append("质量守卫：%d 字 → %d 字（%+.1f%%）｜ 句长中位数 %s → %s ｜ 实词保留率 %s"
                     % (guard["chars_before"], guard["chars_after"], guard["chars_delta"],
                        guard["sent_median_before"], guard["sent_median_after"],
                        ("%.0f%%" % (guard["retention"] * 100)) if guard.get("retention") is not None else "未测"))
        if guard.get("warn"):
            lines.append("注意：" + guard["warn"])
        if guard.get("hint"):
            lines.append("提示：" + guard["hint"])

    sys.stdout.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
