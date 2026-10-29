#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批量打分器：一次加载权重，给多段文本打分。

为什么单独一个进程：引擎的 detect.py 与 scan.py 在同进程内共存时，导入顺序会让
transformers 的惰性模块解析失败（ModuleNotFoundError: BertForSequenceClassification）。
以前每段起一个子进程，代价是每段约十秒重载权重；本脚本把「加载一次、打分多段」
放进单独进程，既避开冲突，又把 N 段的总耗时压到接近一段。

用法（由 loop.py 调用，也可独立用）
  echo '{"texts":["正文一","正文二"],"bits":4}' | python score_batch.py
输出
  {"ok":true,"items":[{"ai_prob":0.99,"verdict":"...","n_win":1,"chars":123},...],"elapsed":1.2}
"""
import argparse
import io
import json
import os
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

def _engine_candidates():
    home = os.path.expanduser("~")
    name = "xiaoyu-chinese-ai-detect"
    return [
        os.path.join(home, ".workbuddy", "skills", name, "scripts"),
        os.path.join(home, ".claude", "skills", name, "scripts"),
        os.path.join(home, ".agents", "skills", name, "scripts"),
        os.path.join(home, ".codex", "skills", name, "scripts"),
        os.path.join(os.getcwd(), ".claude", "skills", name, "scripts"),
        os.path.join(os.getcwd(), ".agents", "skills", name, "scripts"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "engine", "scripts"),
    ]


CANDIDATES = _engine_candidates()


def engine_dir():
    for d in CANDIDATES:
        if os.path.isfile(os.path.join(d, "detect.py")):
            return d
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--payload", default=None, help="JSON 字符串；缺省从 stdin 读")
    ap.add_argument("--bits", type=int, default=None, choices=[4, 8, 32])
    a = ap.parse_args()

    raw = a.payload if a.payload else sys.stdin.read()
    try:
        payload = json.loads(raw)
        texts = payload["texts"]
        bits = a.bits or payload.get("bits")
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
    try:
        import detect as xy
        xy.build(bits=bits)
    except Exception as e:
        import traceback
        sys.stderr.write(traceback.format_exc())
        sys.stdout.write(json.dumps({"ok": False, "error": "引擎加载失败：%s" % str(e)[:160]},
                                    ensure_ascii=False))
        return 4

    t0 = time.time()
    items = []
    for t in texts:
        try:
            r = xy.detect(t, agg="eq", sent=False, bits=bits)["doc"]
            items.append({"ai_prob": r["ai_prob"], "verdict": r["verdict"],
                          "n_win": r["n_win"], "chars": r["chars"]})
        except Exception as e:
            items.append({"error": str(e)[:120]})
    sys.stdout.write(json.dumps({"ok": True, "items": items,
                                 "elapsed": round(time.time() - t0, 2),
                                 "n": len(items)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
