#!/usr/bin/env python3
"""supp_check.py — 补检边际收益校验（防"补检空转"）（cov-gap-audit）。

对 result.supplementary 做机械校验并回填计算字段：
  1. 每条补检查询：query_id 不与原查询冲突；query_string 归一化后不得与任何
     原查询相同（同义重跑=空转预警）；based_on_category ∈ 漏检分类枚举；
  2. new_hits 必须全部是 hit_status=miss 的参考条目（补检只可能命中遗漏）；
  3. 边际收益：new_hits_total / marginal_gain / effective_actual 由本脚本机械
     复算；Agent 声称 effective=true 但新增命中为 0 → 判"补检空转" FAIL；
  4. 补检后口径：post_coverage_rate = (hit + 新增去重命中) / included、
     post_miss_rate 同口径复算；
  5. 残余遗漏：residual_misses 每条须是未被补检命中的 miss 且 explanation
     非空；effective=true 时 stop_rule 非空（何时停止补检）。
**键归属**：本脚本只写 result.supplementary，其余键一律不碰。

用法：
    python3 supp_check.py --result /app/output/result.json --case /input/case.json \
        [--out /app/work/supp_check.json] [--dry-run]
退出码恒为 0（结论记在 report verdict 字段与 stdout，不中断交付）。
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys

CATEGORIES = ("synonym_gap", "field_narrow", "time_window", "source_gap",
              "identifier_anomaly", "other")


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
        print("[supp_check] 写盘失败 %s: %s" % (path, e))
        return False


def norm_query(q):
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]", "", str(q or "").lower())


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", default="/app/output/result.json")
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--out", default=None)
        ap.add_argument("--dry-run", action="store_true")
        try:
            args = ap.parse_args()
        except SystemExit:
            print("[supp_check] 参数解析失败（argparse error，按契约退出码 0）")
            return 0
    except Exception as e:
        print("[supp_check] 参数初始化失败: %s" % e)
        return 0

    res = load_json(args.result)
    if not isinstance(res, dict) or not isinstance(res.get("result"), dict):
        print("[supp_check] FAIL: result.json 不存在/不可解析: %s（不中断交付）" % args.result)
        return 0
    case = load_json(args.case) if os.path.exists(args.case) else {}

    inner = res["result"]
    items = [it for it in (inner.get("items") or []) if isinstance(it, dict)]
    by_id = {str(it.get("ref_id")): it for it in items}
    miss_ids = {str(it.get("ref_id")) for it in items if it.get("hit_status") == "miss"}
    orig_qids, orig_norm = set(), set()
    for q in (inner.get("queries") or []):
        if isinstance(q, dict):
            if q.get("query_id"):
                orig_qids.add(str(q["query_id"]))
            orig_norm.add(norm_query(q.get("query_string")))
    for q in (case.get("queries") or []) if isinstance(case, dict) else []:
        if isinstance(q, dict):
            if q.get("query_id"):
                orig_qids.add(str(q["query_id"]))
            orig_norm.add(norm_query(q.get("query_string")))

    supp = inner.get("supplementary") if isinstance(inner.get("supplementary"), dict) else {}
    sqs = [q for q in (supp.get("queries") or []) if isinstance(q, dict)]
    report = {"verdict": "PASS", "problems": [], "queries": len(sqs), "query_flags": []}

    seen_sqids, all_new_hits = set(), []
    for i, q in enumerate(sqs):
        qid = str(q.get("query_id") or "")
        flags = {"query_id": qid, "category_valid": q.get("based_on_category") in CATEGORIES,
                 "id_unique": qid not in orig_qids and qid not in seen_sqids,
                 "not_duplicate_query": norm_query(q.get("query_string")) not in orig_norm,
                 "new_hits_valid": True}
        seen_sqids.add(qid)
        hits = [str(h) for h in (q.get("new_hits") or [])]
        for h in hits:
            if h not in miss_ids:
                flags["new_hits_valid"] = False
                report["problems"].append("补检 %s 的 new_hits 含非 miss 条目 %r（补检只能命中遗漏）" % (qid, h))
            else:
                all_new_hits.append(h)
        if not flags["category_valid"]:
            report["problems"].append("补检 %s based_on_category 非法: %r" % (qid, q.get("based_on_category")))
        if not flags["id_unique"]:
            report["problems"].append("补检 %s query_id 与原查询或其它补检查询冲突" % qid)
        if not flags["not_duplicate_query"]:
            report["problems"].append("补检 %s query_string 与原查询实质相同（同义重跑=补检空转预警）" % qid)
        if not str(q.get("rationale") or "").strip():
            report["problems"].append("补检 %s 缺 rationale（未说明针对哪类遗漏、为何这条查询可能新增命中）" % qid)
        report["query_flags"].append(flags)

    distinct_new = sorted(set(all_new_hits))
    new_total = len(distinct_new)
    included_n = sum(1 for it in items if it.get("ref_status") == "included")
    hit_n = sum(1 for it in items if it.get("hit_status") == "hit")
    cov = inner.get("coverage") or {}
    post_rate = round((hit_n + new_total) / included_n, 4) if included_n else None
    post_miss = round(max(included_n - hit_n - new_total, 0) / included_n, 4) if included_n else None
    effective_actual = bool(new_total)

    eff = supp.get("effective")
    if eff is True and not effective_actual:
        report["problems"].append("补检空转：声称 effective=true 但新增命中为 0（命中集合没有新增不得报告遗漏下降）")
    if eff is False and effective_actual:
        report["problems"].append("声称 effective=false 但新增命中 %d 条（口径矛盾）" % new_total)
    if effective_actual and not str(supp.get("stop_rule") or "").strip():
        report["problems"].append("补检有效但 stop_rule 为空（须写明何时停止补检）")

    resid_bad = []
    resid = [r for r in (supp.get("residual_misses") or []) if isinstance(r, dict)]
    for r in resid:
        rid = str(r.get("ref_id") or "")
        if rid not in miss_ids:
            resid_bad.append(rid)
            report["problems"].append("残余遗漏 %r 不是 miss 条目" % rid)
        elif rid in distinct_new:
            resid_bad.append(rid)
            report["problems"].append("残余遗漏 %r 已被补检命中（不应再列为残余）" % rid)
        if not str(r.get("explanation") or "").strip():
            resid_bad.append(rid)
            report["problems"].append("残余遗漏 %r 缺 explanation（残余遗漏必须有解释）" % rid)

    report["verdict"] = "FAIL" if report["problems"] else "PASS"
    print("[supp_check] 补检查询 %d 条 | 新增去重命中 %d 条 %s | 声称 effective=%r / 实际 effective_actual=%r"
          % (len(sqs), new_total, distinct_new, eff, effective_actual))
    print("  补检后口径：post_coverage_rate=%s  post_miss_rate=%s（分母 included=%d）" % (post_rate, post_miss, included_n))
    for f in report["query_flags"]:
        print("  %s  category_valid=%s id_unique=%s not_duplicate=%s new_hits_valid=%s"
              % (f["query_id"], f["category_valid"], f["id_unique"], f["not_duplicate_query"], f["new_hits_valid"]))
    for p in report["problems"]:
        print("  FAIL: %s" % p)
    print("[supp_check] verdict=%s" % report["verdict"])

    if args.dry_run:
        print("[supp_check] dry-run：不写盘。")
        return 0
    changed = copy.deepcopy(res)
    ch_supp = dict(changed["result"].get("supplementary") or {})
    ch_supp["new_hits_total"] = new_total
    ch_supp["new_hits_distinct"] = distinct_new
    ch_supp["marginal_gain"] = new_total
    ch_supp["effective_actual"] = effective_actual
    ch_supp["post_coverage_rate"] = post_rate
    ch_supp["post_miss_rate"] = post_miss
    ch_supp["residual_audit_bad"] = sorted(set(resid_bad))
    changed["result"]["supplementary"] = ch_supp
    if save_json(args.result, changed):
        print("[supp_check] 已回写 supplementary（含边际收益复算字段）→ %s" % args.result)
    _dump(args.out, report)
    return 0


def _dump(out_path, report):
    if not out_path:
        return
    try:
        d = os.path.dirname(out_path)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[supp_check] 未预期异常（已降级，不中断交付）: %s" % e)
        sys.exit(0)
