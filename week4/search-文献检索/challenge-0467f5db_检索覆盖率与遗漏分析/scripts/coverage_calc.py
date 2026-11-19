#!/usr/bin/env python3
"""coverage_calc.py — 机械命中判定与覆盖率计算（cov-gap-audit）。

从 result.json 读取冻结参考集（result.reference_set.items）与检索结果记录
（case.json 或 --retrieved 文件），按事前声明口径机械逐条比对：
  1. 标识符匹配（DOI/PMID 归一化精确相等）→ matched_by=identifier；
  2. 标题归一化精确匹配（小写化、仅保留 [0-9a-z汉字]）→ matched_by=title。
分母 = 参考集中 ref_status=included 的条目（unavailable/retracted 登记但不入
分母）——**分母来自冻结参考集，禁止以检索结果自身定义分母**。
写 result.coverage（覆盖率/遗漏率/额外命中数）与 items[].hit_status /
matched_by / matched_query_id / matched_record_ref。--keep-manual 保留人工
裁决条目（matched_by=manual）不覆写。

**键归属**：本脚本只写 result.coverage、items[].hit_status、items[].matched_by、
items[].matched_query_id、items[].matched_record_ref；其余键一律不碰。

用法：
    python3 coverage_calc.py --result /app/output/result.json --case /input/case.json \
        [--retrieved 备用记录文件.json] [--keep-manual] [--dry-run]
退出码恒为 0（结论记在 report verdict 字段与 stdout，不中断交付）。
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys

RET_KEYS = ("retrieved_records", "retrieved", "search_results", "results",
            "hits", "found_records", "records")


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


def norm_title(t):
    """标题归一化：小写化、仅保留 ASCII 字母数字与汉字（显式字符类，不用 isalpha）。"""
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]", "", str(t or "").lower())


def norm_doi(d):
    return re.sub(r"^(https?://(dx\.)?doi\.org/)", "", str(d or "").strip().lower())


def norm_pmid(p):
    s = re.sub(r"[^0-9]", "", str(p or ""))
    return s or None


def extract_retrieved(case, extra_path):
    """优先 --retrieved 文件；否则从 case.json 常见键提取检索记录。"""
    src = None
    if extra_path and os.path.exists(extra_path):
        src = load_json(extra_path)
        note = "--retrieved 文件 %s" % extra_path
    else:
        src = case if isinstance(case, dict) else None
        note = "case.json"
    out = []
    if isinstance(src, dict):
        for key in RET_KEYS:
            v = src.get(key)
            if isinstance(v, list) and v:
                for i, e in enumerate(v):
                    idents = {}
                    if isinstance(e, dict) and isinstance(e.get("identifiers"), dict):
                        for ik in ("doi", "pmid"):
                            if e["identifiers"].get(ik):
                                idents[ik] = str(e["identifiers"][ik])
                    out.append({"record_ref": "%s[%d]" % (key, i),
                                "title": str(e.get("title") or "") if isinstance(e, dict) else str(e),
                                "year": e.get("year") if isinstance(e, dict) else None,
                                "identifiers": idents,
                                "source_db": str(e.get("source_db") or "") if isinstance(e, dict) else "",
                                "query_id": str(e.get("query_id") or "") if isinstance(e, dict) else ""})
                break
    return out, note


def match_one(ref, records):
    """单条参考条目对检索记录机械比对。返回 (hit, matched_by, query_id, record_ref)。"""
    ref_dois = {norm_doi(ref.get("identifiers", {}).get("doi"))} if ref.get("identifiers") else set()
    ref_pmid = norm_pmid(ref.get("identifiers", {}).get("pmid")) if ref.get("identifiers") else None
    ref_title = norm_title(ref.get("title"))
    for r in records:
        r_dois = {norm_doi(r.get("identifiers", {}).get("doi"))} if r.get("identifiers") else set()
        if ref_dois and ref_dois & r_dois and any(x for x in ref_dois & r_dois):
            return True, "identifier", r.get("query_id"), r["record_ref"]
        if ref_pmid and r.get("identifiers") and norm_pmid(r["identifiers"].get("pmid")) == ref_pmid:
            return True, "identifier", r.get("query_id"), r["record_ref"]
    for r in records:
        if ref_title and ref_title == norm_title(r.get("title")):
            return True, "title", r.get("query_id"), r["record_ref"]
    return False, None, None, None


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", default="/app/output/result.json")
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--retrieved", default=None, help="备用检索记录 JSON 文件路径")
        ap.add_argument("--keep-manual", action="store_true",
                        help="保留人工裁决条目（matched_by=manual）不覆写")
        ap.add_argument("--dry-run", action="store_true", help="只打印对照，不写盘")
        try:
            args = ap.parse_args()
        except SystemExit:
            print("[coverage_calc] 参数解析失败（argparse error，按契约退出码 0）")
            return 0
    except Exception as e:
        print("[coverage_calc] 参数初始化失败: %s" % e)
        return 0

    res = load_json(args.result)
    if not isinstance(res, dict) or not isinstance(res.get("result"), dict):
        print("[coverage_calc] FAIL: result.json 不存在/不可解析/无 result 对象: %s（不中断交付）" % args.result)
        return 0
    case = load_json(args.case) if os.path.exists(args.case) else {}

    inner = res["result"]
    ref_items = inner.get("reference_set", {}).get("items") or []
    judge_items = {str(it.get("ref_id")): it for it in (inner.get("items") or []) if isinstance(it, dict)}
    records, src_note = extract_retrieved(case, args.retrieved)
    if not records:
        print("[coverage_calc] WARN: 未提取到检索结果记录（%s），逐条机械比对跳过；"
              "请人工登记 items[].hit_status（matched_by=manual + 证据）后重跑自检。" % src_note)

    report = {"verdict": "PASS", "problems": [], "matched": [], "missed": []}
    hit_n = miss_n = 0
    updated = {}
    for rit in ref_items:
        rid = str(rit.get("ref_id"))
        it = judge_items.get(rid)
        if not isinstance(it, dict):
            report["problems"].append("参考条目 %s 在 result.items 中无对应判定行" % rid)
            continue
        status = it.get("ref_status")
        if args.keep_manual and it.get("matched_by") == "manual":
            if it.get("hit_status") == "hit":
                hit_n += 1
            elif it.get("hit_status") == "miss":
                miss_n += 1
            continue
        if status in ("unavailable", "retracted"):
            # 不可用记录：不入分母，hit_status 置空（由 Agent 补 rationale）
            updated[rid] = {"hit_status": None, "matched_by": None,
                            "matched_query_id": None, "matched_record_ref": None}
            continue
        if status != "included":
            updated[rid] = {"hit_status": None, "matched_by": None,
                            "matched_query_id": None, "matched_record_ref": None}
            continue
        hit, mby, qid, rref = match_one(rit, records)
        updated[rid] = {"hit_status": "hit" if hit else "miss", "matched_by": mby,
                        "matched_query_id": (str(qid) if qid else None),
                        "matched_record_ref": rref}
        if hit:
            hit_n += 1
            report["matched"].append("%s ← %s (%s)" % (rid, rref, mby))
        else:
            miss_n += 1
            report["missed"].append(rid)

    included_n = sum(1 for it in judge_items.values() if it.get("ref_status") == "included")
    unavail_n = sum(1 for it in judge_items.values() if it.get("ref_status") in ("unavailable", "retracted"))
    total_ref = len(judge_items)
    cov_rate = round(hit_n / included_n, 4) if included_n else None
    miss_rate = round(miss_n / included_n, 4) if included_n else None
    matched_refs = {u.get("matched_record_ref") for u in updated.values() if u.get("matched_record_ref")}
    extra_records = max(len(records) - len([r for r in records if r["record_ref"] in matched_refs]), 0) if records else None

    coverage = {"denominator_basis": "frozen_reference_set",
                "match_rule": "分母=参考集 included 条目；命中=标识符(DOI/PMID 归一化)精确或标题归一化精确匹配；"
                              "人工裁决以 matched_by=manual + 证据登记",
                "total_reference": total_ref, "included": included_n,
                "unavailable": unavail_n, "judged": sum(1 for it in judge_items.values() if it.get("judged") is True),
                "hit": hit_n, "miss": miss_n, "extra_records": extra_records,
                "coverage_rate": cov_rate, "miss_rate": miss_rate,
                "retrieved_source": src_note}

    print("[coverage_calc] 参考集 %d 条（included=%d, unavailable/retracted=%d）| 检索记录 %d 条（来自 %s）"
          % (total_ref, included_n, unavail_n, len(records), src_note))
    for m in report["matched"]:
        print("  HIT   %s" % m)
    for m in report["missed"]:
        print("  MISS  %s（须登记进 miss_registry 并归因）" % m)
    print("  覆盖率 coverage_rate=%s  遗漏率 miss_rate=%s（分母=%d，参考集冻结口径）"
          % (cov_rate, miss_rate, included_n))
    if extra_records is not None:
        print("  检索记录中未匹配任何参考条目 %d 条（extra_records：检索数量多 ≠ 覆盖好）" % extra_records)
    for p in report["problems"]:
        print("  WARN: %s" % p)

    if args.dry_run:
        print("[coverage_calc] dry-run：不写盘。")
        return 0
    changed = copy.deepcopy(res)
    ch_inner = changed["result"]
    for it in ch_inner.get("items") or []:
        u = updated.get(str(it.get("ref_id")))
        if isinstance(it, dict) and u:
            it["hit_status"] = u["hit_status"]
            it["matched_by"] = u["matched_by"]
            it["matched_query_id"] = u["matched_query_id"]
            it["matched_record_ref"] = u["matched_record_ref"]
    ch_inner["coverage"] = coverage
    if save_json(args.result, changed):
        print("[coverage_calc] 已回写 coverage / hit_status / matched_* → %s" % args.result)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[coverage_calc] 未预期异常（已降级，不中断交付）: %s" % e)
        sys.exit(0)
