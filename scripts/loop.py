#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""写作闭环 · 闭环驱动器

一次跑完三件事：机械扫描、整篇检测、分段定位。
分段定位不用检测器的句头概率（作者本人说它不能定位），而是把每个
400 字左右的段落块当作独立文档重新打分，这样每段的分数是一个真实
的整篇判定，能直接告诉你要重写哪几段。

用法
  python loop.py 稿件.txt
  python loop.py 稿件.txt --target 0.10 --segment 400
  python loop.py 稿件.txt --json
  python loop.py 稿件.txt --baseline 旧稿.txt     # 顺带检查改写有没有把文字改坏

退出码：0 正常；2 输入问题；3 命中字符级违规。
"""
import argparse
import io
import json
import os
import re
import statistics
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
scanner = None


def load_scanner():
    """延迟导入 scan。必须在检测引擎之后导入：先导入 scan 会让 transformers 的
    惰性模块解析失败（实测 ModuleNotFoundError: BertForSequenceClassification）。"""
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
        os.path.join(home, ".workbuddy", "skills", name, "scripts"),
        os.path.join(home, ".claude", "skills", name, "scripts"),
        os.path.join(home, ".agents", "skills", name, "scripts"),
        os.path.join(home, ".codex", "skills", name, "scripts"),
        # 项目级安装
        os.path.join(os.getcwd(), ".claude", "skills", name, "scripts"),
        os.path.join(os.getcwd(), ".agents", "skills", name, "scripts"),
    ]


XIAOYU_CANDIDATES = _engine_candidates()


def _engine_dir():
    for d in XIAOYU_CANDIDATES:
        if os.path.isfile(os.path.join(d, "detect.py")):
            return d
    return None


def score_many(texts, bits=None):
    """一次加载权重，给多段文本打分。

    走 score_batch.py 子进程：进程内 import 会与 scan 冲突（transformers 惰性模块
    解析失败），而逐段起子进程的代价是每段约十秒重载。批量把总耗时压到接近一段。
    """
    d = _engine_dir()
    if not d:
        return None, "找不到检测引擎 detect.py"
    payload = json.dumps({"texts": texts, "bits": bits}, ensure_ascii=False)
    cmd = [sys.executable, os.path.join(HERE, "score_batch.py"), "--payload", payload]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=1800)
        out = json.loads(r.stdout)
    except Exception as e:
        return None, "批量打分调用失败：%s" % str(e)[:120]
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
        # 长段按句切开，再按 target 拼
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


def pct(p, nd=2):
    if p is None:
        return "—"
    return ("%." + str(nd) + "f%%") % (100.0 * p)


def main():
    ap = argparse.ArgumentParser(description="写作闭环 · 扫描加检测加分段定位")
    ap.add_argument("file", help="待检稿件的文本文件")
    ap.add_argument("--target", type=float, default=0.10, help="目标上限，默认 0.10")
    ap.add_argument("--segment", type=int, default=400, help="分段字数，默认 400。低于 120 字的块跳过；300 至 400 字最稳")
    ap.add_argument("--bits", type=int, default=None, choices=[4, 8, 32], help="引擎权重档位")
    ap.add_argument("--agg", default="eq", choices=["eq", "len"], help="整篇聚合口径")
    ap.add_argument("--baseline", default=None, help="上一版稿件，用于检查改写有没有改坏")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--no-detect", action="store_true", help="只跑机械扫描，不加载模型")
    ap.add_argument("--profile", default=None, help="文风画像 JSON")
    ap.add_argument("--no-profile", action="store_true", help="忽略个人画像")
    a = ap.parse_args()

    if not os.path.isfile(a.file):
        sys.stderr.write("文件不存在：%s\n" % a.file)
        sys.exit(2)
    with open(a.file, encoding="utf-8") as f:
        text = f.read()
    if not text.strip():
        sys.stderr.write("文本为空\n")
        sys.exit(2)

    # ---------- 1. 检测引擎先载入，再载扫描器（顺序敏感，见 load_scanner 注释）
    sc_ = load_scanner()

    # ---------- 2. 机械扫描（带个人画像）
    prof = None if a.no_profile else sc_.load_profile(a.profile)
    sc = sc_.scan(text, profile=prof)

    # 字符级违规先行拦截
    fatal = [i for i in sc["issues"] if i["tier"] == "X"]
    if fatal:
        sys.stderr.write("\n[拦截] 检出零宽字符。这类字符只会在编码转换时暴露，属于作弊\n"
                         "       不是写作。删干净再继续。\n\n")
        if not a.json:
            sys.stdout.write(sc_.render(sc) + "\n")
        sys.exit(3)

    # ---------- 2. 检测
    det = {"available": False}
    segs = []
    chunks = [c for c in chunk(text, a.segment) if len(c[1].strip()) >= 120]
    if not a.no_detect:
        texts = [text] + [c[1] for c in chunks]
        out, err = score_many(texts, a.bits)
        if err:
            det = {"available": False, "error": err}
        else:
            items = out["items"]
            det = {"available": True, "doc": items[0], "bits": a.bits or 4,
                   "agg": a.agg, "elapsed": out.get("elapsed")}
            for (off, seg), it in zip(chunks, items[1:]):
                if "error" in it:
                    continue
                segs.append({"offset": off, "chars": len(seg),
                             "ai_prob": it["ai_prob"], "verdict": it["verdict"],
                             "head": seg.strip().replace("\n", " ")[:34]})
            segs.sort(key=lambda x: -x["ai_prob"])

    # ---------- 3. 质量守卫
    # 内容完整性守卫：实词保留率与语义噪声，依据 shuorenhua hard_metrics.py 与
    # novel-studio 的 contentIntegrityFloor。宁可判高，也不许用噪声换低分。
    def content_guard(new, old=None):
        g = {}
        toks = [new[i:i + 2] for i in range(len(new) - 1) if re.fullmatch(r"[一-龥]{2}", new[i:i + 2])]
        if old is not None:
            keep = sum(1 for t in set(toks) if t in old)
            g["retention"] = round(keep / max(len(set(toks)), 1), 3)
        # 语义噪声：同一 8 字片段重复出现 3 次以上
        from collections import Counter
        grams = [new[i:i + 8] for i in range(max(len(new) - 7, 1))]
        rep = [g_ for g_, c in Counter(grams).items() if c >= 3 and re.search(r"[一-龥]", g_)]
        g["noise_runs"] = len(rep)
        g["noise_sample"] = rep[:3]
        return g

    guard = content_guard(text, open(a.baseline, encoding="utf-8").read()
                          if a.baseline and os.path.isfile(a.baseline) else None)
    if a.baseline and os.path.isfile(a.baseline):
        with open(a.baseline, encoding="utf-8") as f:
            base = f.read()
        b_s = [len(x) for x in sc_.split_sents(base)]
        n_s = [len(x) for x in sc_.split_sents(text)]
        guard.update({
            "chars_before": len(base), "chars_after": len(text),
            "chars_delta": round((len(text) - len(base)) / max(len(base), 1) * 100, 1),
            "sent_median_before": round(statistics.median(b_s), 1) if b_s else None,
            "sent_median_after": round(statistics.median(n_s), 1) if n_s else None,
        })
        if len(n_s) > len(b_s) * 1.6:
            guard["warn"] = "句子数增加超过 60%，可能被过度拆碎了，读一遍。"
        ret = guard.get("retention")
        if ret is not None and ret < 0.85:
            guard["warn"] = "实词保留率 %.0f%%，低于 85%% 地板，改了字面也改了内容。" % (ret * 100)
        elif ret is not None and ret < 0.90:
            guard["warn"] = ((guard.get("warn") or "") + " 实词保留率 %.0f%%，略低于 90%% 目标。" % (ret * 100)).strip()
        ret = guard.get("retention")
        if ret is not None and ret < 0.85:
            guard["warn"] = "实词保留率 %.0f%%，低于 85%% 地板，改了字面也改了内容。" % (ret * 100)
        elif ret is not None and ret < 0.90:
            guard["warn"] = (guard.get("warn", "") + " 实词保留率 %.0f%%，略低于 90%% 目标。" % (ret * 100)).strip()

    # ---------- 4. 输出
    if a.json:
        out = {"scan": sc, "detect": det, "segments": segs, "guard": guard,
               "target": a.target}
        sys.stdout.write(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
        return

    lines = []
    lines.append("=" * 66)
    if det.get("available"):
        d = det["doc"]
        mark = "达标" if d["ai_prob"] <= a.target else "未达标"
        lines.append("整篇 AI 概率 %s（目标 ≤ %.0f%%，%s）｜ %s ｜ %s 聚合 ｜ %s 窗 ｜ %d 字"
                     % (pct(d["ai_prob"]), a.target * 100, mark, d["verdict"],
                        det["agg"], d["n_win"], d["chars"]))
        lines.append("权重 int%s ｜ 检测引擎 v3.3 ｜ 整篇加 %d 段一次载入，引擎耗时 %.1f 秒"
                     % (det.get("bits"), len(segs), det.get("elapsed") or 0))
    else:
        if a.no_detect:
            lines.append("已按 --no-detect 跳过检测，只输出机械扫描。")
        else:
            lines.append("检测未执行：%s" % det.get("error", "找不到检测引擎"))
            lines.append("装好检测引擎（本项目 xiaoyu-chinese-ai-detect 组件）即可启用；当前只输出机械扫描。")
    if prof:
        def _v(x):
            return x.get("mean", 0) if isinstance(x, dict) else (x or 0)
        b = prof.get("baseline", {})
        lines.append("画像 %s ｜ %d 篇 %d 字 ｜ 句长均值 %.1f ｜ 组内 Delta 均值 %.3f"
                     % (prof.get("updated_at", "?"), prof.get("samples", {}).get("files", 0),
                        prof.get("samples", {}).get("chars", 0),
                        _v(b.get("sent_mean")), _v(prof.get("within", {}).get("mean"))))
    else:
        lines.append("未用个人画像，按通用阈值判定。跑 profile.py build 旧稿目录/ 可建基线。")
    lines.append("=" * 66)

    if segs:
        bad = [s for s in segs if s["ai_prob"] > a.target]
        lines.append("")
        lines.append("分段定位（每段单独作为一篇文档打分，按分数降序）")
        lines.append("  %-6s %-8s %-6s %s" % ("偏移", "字数", "概率", "段首"))
        for s in segs[:12]:
            flag = "  " if s["ai_prob"] <= a.target else ">>"
            lines.append("%s%-6d %-8d %-6s %s" % (flag, s["offset"], s["chars"],
                                                  pct(s["ai_prob"], 1), s["head"]))
        if len(segs) > 12:
            lines.append("   ……其余 %d 段均低于目标" % (len(segs) - 12))
        lines.append("")
        if bad:
            lines.append("需重写 %d 段（标 >> 的那几条），优先从概率最高的开始。" % len(bad))
        else:
            lines.append("所有分段已达目标。")

    lines.append("")
    lines.append("-" * 66)
    lines.append(sc_.render(sc))
    if guard.get("noise_runs"):
        lines.append("")
        lines.append("内容完整性：检出 %d 处重复片段（如「%s」）。分数不可信，"
                     "这是噪声不是改写。" % (guard["noise_runs"], guard.get("noise_sample", [""])[0][:16]))
    if guard and "chars_before" in guard:
        lines.append("")
        lines.append("-" * 66)
        lines.append("质量守卫：%d 字 → %d 字（%+.1f%%）｜ 句长中位数 %s → %s ｜ 实词保留率 %s"
                     % (guard["chars_before"], guard["chars_after"], guard["chars_delta"],
                        guard["sent_median_before"], guard["sent_median_after"],
                        ("%.0f%%" % (guard["retention"] * 100)) if guard.get("retention") is not None else "未测"))
        if guard.get("warn"):
            lines.append("注意：" + guard["warn"])

    sys.stdout.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
