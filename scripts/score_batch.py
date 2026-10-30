#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2026 faruheaisha
# SPDX-License-Identifier: GPL-3.0-only
"""批量打分器（v2.2：跨文本窗口去重 + 按长度排序凑批推理 + 内嵌引擎优先）。

为什么单独一个进程：在独立子进程中一次性加载模型权重，隔离 torch/transformers 依赖；
同时把全文滑窗与各分段块合并去重、按长度分桶凑批（batch=8）统一前向传播，
消除逐段 batch=1 串行扫描百兆权重的内存带宽开销，不改动 engine/ 任何字节。

用法（由 loop.py 通过 stdin 管道调用，也可独立用）
  echo '{"texts":["正文一","正文二"],"bits":4}' | python score_batch.py
输出
  {"ok":true,"items":[{"ai_prob":0.99,"verdict":"...","n_win":1,"chars":123},...],"elapsed":0.6}
"""
import argparse
import contextlib
import io
import json
import os
import sys
import time

for _stream in (sys.stdin, sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass


def _engine_candidates():
    here = os.path.dirname(os.path.abspath(__file__))
    home = os.path.expanduser("~")
    name = "xiaoyu-chinese-ai-detect"
    return [
        # 优先使用同目录内嵌引擎（单技能安装与克隆直跑零冲突）
        os.path.join(here, "..", "engine", "scripts"),
        os.path.join(home, ".workbuddy", "skills", name, "scripts"),
        os.path.join(home, ".claude", "skills", name, "scripts"),
        os.path.join(home, ".agents", "skills", name, "scripts"),
        os.path.join(home, ".codex", "skills", name, "scripts"),
        os.path.join(os.getcwd(), ".claude", "skills", name, "scripts"),
        os.path.join(os.getcwd(), ".agents", "skills", name, "scripts"),
    ]


CANDIDATES = _engine_candidates()


def engine_dir():
    for d in CANDIDATES:
        if os.path.isfile(os.path.join(d, "detect.py")):
            return d
    return None


def score_texts_batched(xy, texts, agg="eq", batch=8):
    """跨文本合并滑窗、去重并按长度凑批推理，与 detect.score_full 保持完全一致的切窗和聚合口径。"""
    c = xy.build()
    torch, tok, model = c["torch"], c["tok"], c["model"]
    if not os.environ.get("OMP_NUM_THREADS") and torch.get_num_threads() > 8:
        torch.set_num_threads(8)

    plans = []
    unique_wins = {}
    for t in texts:
        if not isinstance(t, str) or not t.strip():
            plans.append(("err", "文本为空", 0))
            continue
        ntok = len(tok(t, add_special_tokens=False)["input_ids"])
        segs = [] if ntok <= xy.LIM else xy.build_windows(t)
        if len(segs) <= 1:
            unique_wins[t] = None
            plans.append(("single", t, len(t)))
        else:
            for s in segs:
                unique_wins[s] = None
            plans.append(("multi", segs, len(t)))

    # 按字符长度排序凑批，最小化同一 batch 内的 [PAD] 列浪费
    sorted_wins = sorted(unique_wins.keys(), key=len)
    with torch.no_grad():
        for k in range(0, len(sorted_wins), batch):
            bw = sorted_wins[k:k + batch]
            enc = tok(bw, padding=True, truncation=True, max_length=xy.MAXLEN, return_tensors="pt")
            enc = {kk: vv for kk, vv in enc.items()
                   if kk in ("input_ids", "attention_mask", "token_type_ids")}
            ps = xy._p(torch, model(**enc).logits).float().cpu().tolist()
            for w_str, p_val in zip(bw, ps):
                unique_wins[w_str] = float(p_val)

    items = []
    for kind, data, n_chars in plans:
        if kind == "err":
            items.append({"error": data})
        elif kind == "single":
            p = unique_wins[data]
            items.append({"ai_prob": p, "verdict": xy.verdict_of(p),
                          "n_win": 1, "chars": n_chars})
        else:
            ps = [unique_wins[s] for s in data]
            lens = [len(s) for s in data]
            p = xy.aggregate(ps, lens, agg)
            items.append({"ai_prob": p, "verdict": xy.verdict_of(p),
                          "n_win": len(ps), "chars": n_chars})
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--payload", default=None, help="JSON 字符串；缺省从 stdin 读")
    ap.add_argument("--bits", type=int, default=None, choices=[4, 8, 32])
    a = ap.parse_args()

    try:
        raw = a.payload if a.payload is not None else sys.stdin.read()
        payload = json.loads(raw)
        texts = payload["texts"]
        bits = a.bits or payload.get("bits")
        agg = payload.get("agg", "eq")
    except Exception as e:
        sys.stdout.write(json.dumps({"ok": False, "error": "载荷解析失败：%s" % e},
                                    ensure_ascii=False))
        return 2

    d = engine_dir()
    if not d:
        sys.stdout.write(json.dumps({"ok": False, "error": "找不到检测引擎 detect.py"},
                                    ensure_ascii=False))
        return 3

    sys.path.insert(0, d)
    err_buf = io.StringIO()
    try:
        with contextlib.redirect_stderr(err_buf):
            import detect as xy
            c_info = xy.build(bits=bits)
    except (Exception, SystemExit) as e:
        captured = err_buf.getvalue().strip()
        msg = captured.splitlines()[0] if captured else ("引擎加载失败：%s" % str(e)[:160])
        if captured:
            sys.stderr.write(captured + "\n")
        sys.stdout.write(json.dumps({"ok": False, "error": msg, "detail": captured[:400]},
                                    ensure_ascii=False))
        return 4

    t0 = time.time()
    try:
        with contextlib.redirect_stderr(err_buf):
            items = score_texts_batched(xy, texts, agg=agg, batch=8)
    except (Exception, SystemExit) as e:
        sys.stdout.write(json.dumps({"ok": False, "error": "推理失败：%s" % str(e)[:160]},
                                    ensure_ascii=False))
        return 5

    sys.stdout.write(json.dumps({"ok": True, "items": items,
                                 "bits": c_info.get("bits", bits or 4),
                                 "elapsed": round(time.time() - t0, 2),
                                 "n": len(items)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
