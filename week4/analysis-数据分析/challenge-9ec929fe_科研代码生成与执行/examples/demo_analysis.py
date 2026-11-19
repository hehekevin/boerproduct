#!/usr/bin/env python3
"""demo_analysis.py — 合成演示分析脚本（示意，非正式答案）。

角色：模拟“Agent 在 Step 2 生成的自包含分析脚本”。只用标准库，路径全部
argparse 参数化，不写死本机路径；按 case.json 内联数据集 exp_a 完成清洗与
统计，并把每条结果以 stat_id=值 的行打印出来（供执行日志与 claims 回证）。

用法：
    python3 demo_analysis.py --case examples/example-case.json [--out /tmp/demo_out.json]
退出码：正常 0；输入不可用 1（错误信息打到 stderr，留失败现场）。
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys

MISSING = {"", "na", "n/a", "null", "none", "-", "nan"}


def is_missing(v):
    return str(v or "").strip().lower() in MISSING


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="examples/example-case.json")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    if not os.path.exists(args.case):
        print("case 文件不存在: %s" % args.case, file=sys.stderr)
        return 1
    with open(args.case, "r", encoding="utf-8") as f:
        case = json.load(f)
    ds = (case.get("datasets") or [{}])[0]
    if ds.get("format") != "csv_inline":
        print("演示脚本仅支持 csv_inline 数据集", file=sys.stderr)
        return 1
    raw = list(csv.DictReader(io.StringIO(ds["content"])))

    n_score_missing = sum(1 for r in raw if is_missing(r.get("score")))
    rows = [r for r in raw if not is_missing(r.get("score"))]      # CR-01 dropna score
    seen, dedup = set(), []
    for r in rows:                                                  # CR-02 dedup record_id
        k = r.get("record_id")
        if k in seen:
            continue
        seen.add(k)
        dedup.append(r)
    rows = [r for r in dedup if r.get("batch") in ("A", "B")]      # CR-03 filter batch
    for r in rows:                                                  # CR-04 clip score [0,100]
        v = float(r["score"])
        r["score"] = str(min(max(v, 0.0), 100.0))

    n_after_clean = len(rows)
    a_vals = [float(r["score"]) for r in rows if r["batch"] == "A"]
    b_vals = [float(r["score"]) for r in rows if r["batch"] == "B"]
    mean_a = sum(a_vals) / len(a_vals) if a_vals else 0.0
    mean_b = sum(b_vals) / len(b_vals) if b_vals else 0.0

    print("n_score_missing_raw=%d" % n_score_missing)
    print("n_after_clean=%d" % n_after_clean)
    print("mean_score_A=%s" % ("%g" % round(mean_a, 4)))
    print("mean_score_B=%s" % ("%g" % round(mean_b, 4)))

    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump({"n_score_missing_raw": n_score_missing,
                       "n_after_clean": n_after_clean,
                       "mean_score_A": round(mean_a, 4),
                       "mean_score_B": round(mean_b, 4)}, f, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
