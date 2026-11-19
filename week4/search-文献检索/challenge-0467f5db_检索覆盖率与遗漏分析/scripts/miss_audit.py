#!/usr/bin/env python3
"""miss_audit.py — 漏检登记完备性与归因可追溯审计（cov-gap-audit）。

对 result.json 中每一条 hit_status=miss 的参考条目，逐条核对 miss_registry
登记是否完备、归因是否可追溯到具体查询式/字段/来源：
  1. 每条 miss 必须恰有一条 miss_registry 登记（遗漏不得被划掉或漏登记）；
  2. category ∈ synonym_gap / field_narrow / time_window / source_gap /
     identifier_anomaly / other（other 须写 reason 说明）；
  3. attribution.query_id / field / source_db / reason 均非空，且 query_id
     必须存在于 result.queries 或 case.json 的查询清单（归因泛泛即 FAIL）。
回写 result.miss_registry（附加 audit 校验标记）。**键归属**：本脚本只写
result.miss_registry，其余键一律不碰。

用法：
    python3 miss_audit.py --result /app/output/result.json --case /input/case.json \
        [--out /app/work/miss_audit.json] [--dry-run]
退出码恒为 0（结论记在 report verdict 字段与 stdout，不中断交付）。
"""
from __future__ import annotations

import argparse
import copy
import json
import os
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
        print("[miss_audit] 写盘失败 %s: %s" % (path, e))
        return False


def known_query_ids(res, case):
    ids = set()
    for src in (res, case):
        for q in ((src or {}).get("result", {}).get("queries") if isinstance(src, dict) and isinstance(src.get("result"), dict) else None) \
                 or ((src or {}).get("queries") if isinstance(src, dict) else None) or []:
            if isinstance(q, dict) and q.get("query_id"):
                ids.add(str(q["query_id"]))
    return ids


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
            print("[miss_audit] 参数解析失败（argparse error，按契约退出码 0）")
            return 0
    except Exception as e:
        print("[miss_audit] 参数初始化失败: %s" % e)
        return 0

    res = load_json(args.result)
    if not isinstance(res, dict) or not isinstance(res.get("result"), dict):
        print("[miss_audit] FAIL: result.json 不存在/不可解析: %s（不中断交付）" % args.result)
        return 0
    case = load_json(args.case) if os.path.exists(args.case) else {}
    qids = known_query_ids(res, case)

    inner = res["result"]
    items = [it for it in (inner.get("items") or []) if isinstance(it, dict)]
    miss_ids = [str(it.get("ref_id")) for it in items if it.get("hit_status") == "miss"]
    reg = [r for r in (inner.get("miss_registry") or []) if isinstance(r, dict)]
    reg_by_id = {}
    for r in reg:
        reg_by_id.setdefault(str(r.get("ref_id")), []).append(r)

    report = {"verdict": "PASS", "problems": [], "miss_total": len(miss_ids),
              "registered": 0, "audit_flags": []}
    new_reg = []
    for rid in miss_ids:
        entries = reg_by_id.get(rid) or []
        if not entries:
            report["problems"].append("%s hit_status=miss 但未登记进 miss_registry（遗漏不得划掉）" % rid)
            new_reg.append({"ref_id": rid, "category": None,
                            "attribution": {"query_id": None, "field": None,
                                            "source_db": None, "reason": None},
                            "evidence": None, "needed_action": None,
                            "audit": {"registered": False, "category_valid": False,
                                      "attribution_complete": False,
                                      "query_id_exists": False}})
            continue
        if len(entries) > 1:
            report["problems"].append("%s 在 miss_registry 中重复登记 %d 条（须恰一条）" % (rid, len(entries)))
        e = entries[0]
        cat = e.get("category")
        att = e.get("attribution") if isinstance(e.get("attribution"), dict) else {}
        cat_ok = cat in CATEGORIES
        other_reasoned = cat != "other" or bool(str(att.get("reason") or "").strip())
        att_complete = all(str(att.get(k) or "").strip() for k in ("query_id", "field", "source_db", "reason"))
        qid_ok = str(att.get("query_id") or "") in qids
        flags = {"registered": True, "category_valid": bool(cat_ok and other_reasoned),
                 "attribution_complete": bool(att_complete), "query_id_exists": bool(qid_ok)}
        if not cat_ok:
            report["problems"].append("%s category 非法: %r（须 %s，other 须写 reason）" % (rid, cat, ",".join(CATEGORIES)))
        if not att_complete:
            report["problems"].append("%s 归因不完整（attribution.query_id/field/source_db/reason 均须非空）" % rid)
        if not qid_ok:
            report["problems"].append("%s 归因 query_id=%r 不存在于任何查询清单（归因泛泛、无法回溯）" % (rid, att.get("query_id")))
        if not str(e.get("needed_action") or "").strip():
            report["problems"].append("%s 登记缺 needed_action（补检动作不明确）" % rid)
        entry = dict(e)
        entry["audit"] = flags
        new_reg.append(entry)
        report["registered"] += 1
        report["audit_flags"].append({"ref_id": rid, **flags})
    # 登记了但不是 miss 的条目（错登记）
    for rid in reg_by_id:
        if rid not in miss_ids:
            report["problems"].append("%s 登记在 miss_registry 但 hit_status≠miss（错登记）" % rid)

    report["verdict"] = "FAIL" if report["problems"] else "PASS"
    print("[miss_audit] miss=%d 条 | 已登记 %d 条 | query 清单 id=%s"
          % (len(miss_ids), report["registered"], sorted(qids) or "(空)"))
    for f in report["audit_flags"]:
        print("  %s  category_valid=%s attribution_complete=%s query_id_exists=%s"
              % (f["ref_id"], f["category_valid"], f["attribution_complete"], f["query_id_exists"]))
    for p in report["problems"]:
        print("  FAIL: %s" % p)
    print("[miss_audit] verdict=%s" % report["verdict"])

    if args.dry_run:
        print("[miss_audit] dry-run：不写盘。")
        return 0
    changed = copy.deepcopy(res)
    changed["result"]["miss_registry"] = new_reg
    if save_json(args.result, changed):
        print("[miss_audit] 已回写 miss_registry（含 audit 校验标记）→ %s" % args.result)
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
        print("[miss_audit] 未预期异常（已降级，不中断交付）: %s" % e)
        sys.exit(0)
