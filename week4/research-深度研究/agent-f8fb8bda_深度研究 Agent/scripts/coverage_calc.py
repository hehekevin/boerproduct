#!/usr/bin/env python3
"""coverage_calc.py — 覆盖面与证据强度机械汇总（deep-research-loop Step 4）。

从 result.json 读取 plan.sub_questions / findings / iterations，机械汇总：
  - 每个子问题按其结论最高强度分级：answered（含 strong/moderate 结论）、
    partially_answered（仅 weak/unverified 结论）、unanswered（无结论）；
  - answered_ratio = answered / sub_questions_total；
  - strength_summary：全部结论按 strong/moderate/weak/unverified 计数。
写 result.coverage 与 result.strength_summary 及 /app/work/coverage_ledger.json
（含指纹）。verify_check 会独立复算并与回写值逐项对照。

**键归属**：本脚本只写 result.coverage、result.strength_summary 与
/app/work/coverage_ledger.json；其余键一律不碰（多脚本禁写同一键）。

用法：
    python3 coverage_calc.py --result /app/output/result.json [--work-dir /app/work]
退出码恒为 0（结论记在 stdout 与台账，不中断交付）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

ANSWERED_STRENGTHS = ("strong", "moderate")
STRENGTH_KEYS = ("strong", "moderate", "weak", "unverified")


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_json(path, obj):
    try:
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)
        return True
    except Exception as e:
        print("[coverage_calc] 写盘失败 %s: %s" % (path, e))
        return False


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", default="/app/output/result.json")
        ap.add_argument("--work-dir", default="/app/work")
        args = ap.parse_args()
    except Exception as e:
        print("[coverage_calc] 参数解析失败（已降级）: %s" % e)
        return 0

    res = load_json(args.result)
    if not isinstance(res, dict) or not isinstance(res.get("result"), dict):
        print("[coverage_calc] FAIL: result.json 不存在/不可解析/无 result 对象: %s（不中断交付）"
              % args.result)
        return 0

    inner = res["result"]
    plan = inner.get("plan") or {}
    sqs = [s for s in (plan.get("sub_questions") or []) if isinstance(s, dict)]
    findings = [f for f in (inner.get("findings") or []) if isinstance(f, dict)]
    iterations = [r for r in (inner.get("iterations") or []) if isinstance(r, dict)]

    per_sq = {}
    for f in findings:
        st = str(f.get("strength") or "")
        for sid in (f.get("sq_ids") or []):
            per_sq.setdefault(str(sid), []).append(st)
    answered = partially = unanswered = 0
    sq_states = {}
    for s in sqs:
        sid = str(s.get("sq_id") or "")
        sts = per_sq.get(sid, [])
        if not sts:
            state = "unanswered"
            unanswered += 1
        elif any(x in ANSWERED_STRENGTHS for x in sts):
            state = "answered"
            answered += 1
        else:
            state = "partially_answered"
            partially += 1
        sq_states[sid] = state

    src_ids = set()
    for f in findings:
        for s in (f.get("sources") or []):
            if isinstance(s, dict) and s.get("source_id"):
                src_ids.add(str(s["source_id"]))

    total = len(sqs)
    coverage = {"sub_questions_total": total, "answered": answered,
                "partially_answered": partially, "unanswered": unanswered,
                "findings_total": len(findings), "iterations_count": len(iterations),
                "sources_total": len(src_ids),
                "answered_ratio": round(answered / total, 4) if total else None,
                "sq_states": sq_states,
                "rule": "answered=含 strong/moderate 结论；partially=仅 weak/unverified 结论；"
                        "unanswered=无结论。answered_ratio=answered/子问题总数。"}
    strength_summary = {k: sum(1 for f in findings if str(f.get("strength")) == k)
                        for k in STRENGTH_KEYS}
    strength_summary["total"] = len(findings)

    digest = None
    try:
        digest = hashlib.sha256(json.dumps({"coverage": coverage,
                                            "strength_summary": strength_summary},
                                           sort_keys=True, ensure_ascii=False)
                                .encode("utf-8")).hexdigest()[:16]
    except Exception:
        digest = None

    try:
        cur = load_json(args.result)
        if isinstance(cur, dict) and isinstance(cur.get("result"), dict):
            cur["result"]["coverage"] = coverage
            cur["result"]["strength_summary"] = strength_summary
            save_json(args.result, cur)
    except Exception as e:
        print("[coverage_calc] 回写 result.json 失败: %s" % e)

    save_json(os.path.join(args.work_dir or ".", "coverage_ledger.json"),
              {"digest": digest, "coverage": coverage, "strength_summary": strength_summary,
               "note": "覆盖面台账：verify_check 独立复算并与回写值对照。"})

    print("[coverage_calc] 子问题 %d | answered=%d partially=%d unanswered=%d | "
          "结论 %d（strong=%d moderate=%d weak=%d unverified=%d）| 来源 %d | digest=%s"
          % (total, answered, partially, unanswered, len(findings),
             strength_summary["strong"], strength_summary["moderate"],
             strength_summary["weak"], strength_summary["unverified"],
             len(src_ids), digest))
    for sid in sorted(sq_states):
        print("  %s: %s" % (sid, sq_states[sid]))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[coverage_calc] 未预期异常（已降级，不中断交付）: %s" % e)
        sys.exit(0)
