#!/usr/bin/env python3
"""flow_audit.py — PRISMA 流程漏斗机械复算与闭合审计（sysrev-search-screen）。

从 result.records 机械复算漏斗五级计数并校验闭合（与题面"审计/流程计数一致"
机检点对应），复算结果写回 result.funnel（键归属：本脚本只写 result.funnel）：

    identified        = records 总条数（含重复导出）
    duplicates_removed= duplicate_of 非空的条数（去重合并移除）
    screened          = identified − duplicates_removed（进入逐条筛选的条数）
    included/excluded/pending_review = 仅对**非重复**记录按 decision 计数
    excluded_by_reason = 非重复排除记录按 reason_code 分组（合计须 == excluded）

闭合判据（closure=closed 须全部成立）：
    identified == duplicates_removed + screened
    screened   == included + excluded + pending_review
    sum(excluded_by_reason) == excluded
闭合失败时 closure=open，closure_note 逐条写明差在哪一级；不静默改平。

用法：
    python3 flow_audit.py --result /app/output/result.json \
        [--report /app/work/funnel_audit.json]
退出码恒为 0（结论记在报告 stdout，不中断交付）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

DECISIONS = ("included", "excluded", "pending_review")


def recompute(records):
    """从 records 机械复算漏斗计数（纯函数，不写盘）。"""
    recs = [r for r in records if isinstance(r, dict)]
    identified = len(recs)
    dup = [r for r in recs if r.get("duplicate_of")]
    non_dup = [r for r in recs if not r.get("duplicate_of")]
    dups_removed = len(dup)
    screened = identified - dups_removed
    included = sum(1 for r in non_dup if r.get("decision") == "included")
    excluded = sum(1 for r in non_dup if r.get("decision") == "excluded")
    pending = sum(1 for r in non_dup if r.get("decision") == "pending_review")
    by_reason = {}
    for r in non_dup:
        if r.get("decision") == "excluded" and r.get("reason_code"):
            by_reason[str(r["reason_code"])] = by_reason.get(str(r["reason_code"]), 0) + 1
    return {
        "identified": identified, "duplicates_removed": dups_removed, "screened": screened,
        "excluded": excluded, "included": included, "pending_review": pending,
        "excluded_by_reason": dict(sorted(by_reason.items())),
    }


def closure_checks(f):
    """闭合判据逐条核对，返回 (ok, [问题描述])。"""
    problems = []
    if f["identified"] != f["duplicates_removed"] + f["screened"]:
        problems.append("identified(%d) != duplicates_removed(%d) + screened(%d)"
                        % (f["identified"], f["duplicates_removed"], f["screened"]))
    if f["screened"] != f["included"] + f["excluded"] + f["pending_review"]:
        problems.append("screened(%d) != included(%d) + excluded(%d) + pending_review(%d)"
                        % (f["screened"], f["included"], f["excluded"], f["pending_review"]))
    if sum(f["excluded_by_reason"].values()) != f["excluded"]:
        problems.append("excluded_by_reason 合计(%d) != excluded(%d)"
                        % (sum(f["excluded_by_reason"].values()), f["excluded"]))
    return (not problems), problems


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", required=True)
        ap.add_argument("--report", default="/app/work/funnel_audit.json")
        args = ap.parse_args()
    except Exception as e:
        print("[flow_audit] 参数解析失败（已降级）: %s" % e)
        return 0

    try:
        if not os.path.exists(args.result):
            print("[flow_audit] result.json 不存在: %s（不中断交付）" % args.result)
            _dump(args.report, {"verdict": "FAIL", "problems": ["result.json 不存在"]})
            return 0
        with open(args.result, "r", encoding="utf-8") as f:
            res = json.load(f)
    except Exception as e:
        print("[flow_audit] result.json 读取失败: %s（不中断交付）" % e)
        _dump(args.report, {"verdict": "FAIL", "problems": ["读取失败: %s" % e]})
        return 0

    inner = res.get("result") if isinstance(res, dict) else None
    if not isinstance(inner, dict):
        print("[flow_audit] FAIL: result 非对象（不中断交付）")
        _dump(args.report, {"verdict": "FAIL", "problems": ["result 非对象"]})
        return 0

    stored = dict(inner.get("funnel") or {})
    recomputed = recompute(inner.get("records") or [])
    ok, probs = closure_checks(recomputed)

    # 与旧存值对照（先记差异再覆盖，不静默改平）
    diffs = []
    for k in ("identified", "duplicates_removed", "screened", "excluded",
              "included", "pending_review"):
        old = stored.get(k)
        if isinstance(old, int) and old != recomputed[k]:
            diffs.append("%s: 存值 %d → 复算 %d" % (k, old, recomputed[k]))

    recomputed["closure"] = "closed" if ok else "open"
    recomputed["closure_note"] = ("五级计数逐级闭合（识别→去重→筛选→纳入/排除/待复核）。"
                                  if ok else "闭合失败：" + "；".join(probs))
    inner["funnel"] = recomputed

    try:
        with open(args.result, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
    except Exception as e:
        probs.append("写回 result.json 失败: %s" % e)

    rep = {"verdict": "FAIL" if (probs or diffs) else "PASS",
           "problems": probs, "stored_value_diffs": diffs, "funnel": recomputed}
    _dump(args.report, rep)
    print("[flow_audit] 漏斗复算: identified=%d → 去重 %d → 筛选 %d → 纳入 %d / 排除 %d / 待复核 %d"
          % (recomputed["identified"], recomputed["duplicates_removed"], recomputed["screened"],
             recomputed["included"], recomputed["excluded"], recomputed["pending_review"]))
    print("[flow_audit] 排除原因分布: %s" % (recomputed["excluded_by_reason"] or "{}"))
    print("[flow_audit] closure=%s%s" % (recomputed["closure"],
          ("（%d 处差异）" % len(diffs)) if diffs else ""))
    for d in diffs:
        print("  DIFF: %s" % d)
    for p in probs:
        print("  WARN: %s" % p)
    return 0


def _dump(path, obj):
    if not path:
        return
    try:
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[flow_audit] 未预期异常（已降级，不中断交付）: %s" % e)
        sys.exit(0)
