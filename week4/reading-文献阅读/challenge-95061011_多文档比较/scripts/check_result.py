#!/usr/bin/env python3
"""check_result.py — 多文档比较结果校验器（r3 增强版）。

新增校验：pairwise 双文档引文、冲突双方不同文档、跨文档 claim 引文、coverage 统计。
所有异常均捕获降级，绝不崩溃。用法：
    python check_result.py --result R.json [--workorder WO.json] [--case C.json] [--out report.json]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

CELL_STATUS = {"reported", "not_reported", "not_comparable"}
VERDICTS = {"same", "partial", "different", "not_judged"}


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def contract_fields(case):
    try:
        oc = case.get("output_contract") if isinstance(case, dict) else None
        if oc is None:
            return []
        if isinstance(oc, dict):
            for key in ("fields", "required_fields", "result.json", "result"):
                v = oc.get(key)
                if isinstance(v, list):
                    return [str(x) for x in v]
            return [str(k) for k in oc.keys()]
        if isinstance(oc, list):
            return [str(x) for x in oc]
    except Exception:
        pass
    return []


def parse_docs(wo):
    docs = []
    try:
        for d in (wo.get("documents") or wo.get("corpus") or []):
            if isinstance(d, dict):
                docs.append(str(d.get("source_document_id") or d.get("id")))
            else:
                docs.append(str(d))
    except Exception:
        pass
    return docs


def parse_fields(wo):
    fields = []
    try:
        for fdef in (wo.get("fields") or wo.get("comparison_fields") or []):
            if isinstance(fdef, dict):
                fields.append(str(fdef.get("field_id") or fdef.get("name")))
            else:
                fields.append(str(fdef))
    except Exception:
        pass
    return fields


def distinct_doc_ids(entries):
    ids = set()
    for e in entries or []:
        if isinstance(e, dict):
            sid = str(e.get("source_document_id") or "")
            if sid:
                ids.add(sid)
    return ids


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--result", required=True)
    ap.add_argument("--workorder", default=None)
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--out", default="/app/output/check_report.json")
    args = ap.parse_args()

    problems = []
    res = load_json(args.result)
    if res is None:
        problems.append("result.json 不存在或不是合法 JSON")
        report = {"ok": False, "problems": problems}
        try:
            with open(args.out, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=1)
        except Exception:
            pass
        print("[check_result] FAIL: %s" % problems[0])
        return 1

    # 1) 通用契约五字段
    if not res.get("case_id"):
        problems.append("缺少 case_id")
    for k in ("status", "result", "claims", "uncertainties"):
        if k not in res:
            problems.append("缺少通用契约字段: %s" % k)

    # 2) output_contract 全键
    case = load_json(args.case) if args.case and os.path.exists(args.case) else None
    if case:
        for f in contract_fields(case):
            if f not in res:
                problems.append("缺少 output_contract 字段: %s" % f)

    inner = res.get("result") if isinstance(res.get("result"), dict) else {}

    # 3) 工单覆盖：matrix 文档 × 字段全格
    wo = load_json(args.workorder) if args.workorder and os.path.exists(args.workorder) else None
    docs = parse_docs(wo) if wo else []
    fields = parse_fields(wo) if wo else []

    matrix = inner.get("matrix")
    if not isinstance(matrix, list):
        problems.append("result.matrix 缺失或不是数组")
        matrix = []

    got_cells = set()
    n_reported = n_notrep = n_notcomp = 0
    for i, c in enumerate(matrix):
        if not isinstance(c, dict):
            problems.append("matrix[%d] 不是对象" % i)
            continue
        fid = str(c.get("field_id"))
        doc = str(c.get("source_document_id"))
        got_cells.add((fid, doc))
        st = c.get("cell_status")
        if st not in CELL_STATUS:
            problems.append("[%s@%s] cell_status 非法: %r" % (fid, doc, st))
            continue
        if st == "reported":
            n_reported += 1
            if c.get("value") is None and not (c.get("text") or "").strip():
                problems.append("[%s@%s] reported 但无值" % (fid, doc))
            ev = c.get("evidence") or {}
            if not ev.get("source_document_id") or not ev.get("paragraph_id") or not (ev.get("quote") or "").strip():
                problems.append("[%s@%s] reported 格缺完整 evidence" % (fid, doc))
        elif st == "not_reported":
            n_notrep += 1
        elif st == "not_comparable":
            n_notcomp += 1
            if not (c.get("incomparable_reason") or "").strip():
                problems.append("[%s@%s] not_comparable 缺 incomparable_reason" % (fid, doc))

    for d in docs:
        for f in fields:
            if (f, d) not in got_cells:
                problems.append("缺格: field=%s doc=%s" % (f, d))

    # 4) pairwise：verdict 非 not_judged 必须有双方（不同文档）引文
    pairwise = inner.get("pairwise")
    if not isinstance(pairwise, list):
        problems.append("result.pairwise 缺失或不是数组（两两比较矩阵为核心产出）")
        pairwise = []
    n_pair_valid = 0
    for i, p in enumerate(pairwise):
        if not isinstance(p, dict):
            problems.append("pairwise[%d] 不是对象" % i)
            continue
        vd = p.get("verdict")
        if vd not in VERDICTS:
            problems.append("pairwise[%d] verdict 非法: %r" % (i, vd))
            continue
        if vd == "not_judged":
            if not (p.get("note") or "").strip():
                problems.append("pairwise[%d] not_judged 缺 note 说明原因" % i)
            continue
        ev = p.get("evidence") or []
        ids = distinct_doc_ids(ev)
        if len(ev) < 2:
            problems.append("pairwise[%d]（%s）verdict=%s 但 evidence 少于 2 条（须双方引文）" % (
                i, p.get("dimension"), vd))
        elif len(ids) < 2:
            problems.append("pairwise[%d]（%s）evidence 两方来自同一文档: %s" % (
                i, p.get("dimension"), sorted(ids)))
        else:
            n_pair_valid += 1

    # 5) 可比性
    comp = inner.get("comparability") or {}
    if comp:
        subset = comp.get("comparable_subset") or []
        if comp.get("pooled") and len(subset) < 2:
            problems.append("pooled=true 但可比子集不足 2 篇（混池风险）")

    # 6) 冲突：引文 ≥2 且来自不同文档
    conflicts = ((inner.get("synthesis") or {}).get("conflicts")) or []
    for i, cf in enumerate(conflicts):
        q = cf.get("quotes") or []
        ids = distinct_doc_ids(q)
        if len(q) < 2:
            problems.append("conflicts[%d] 引文少于 2（冲突双方须并列）" % i)
        elif len(ids) < 2:
            problems.append("conflicts[%d] 引文全部来自同一文档: %s" % (i, sorted(ids)))
        if not (cf.get("attribution") or "").strip():
            problems.append("conflicts[%d] 缺 attribution" % i)

    # 7) claims：每条至少 1 条带定位引文；含多文档 evidence 的须 ≥2 条
    claims = res.get("claims")
    if not isinstance(claims, list):
        problems.append("claims 缺失或不是数组")
        claims = []
    for i, cl in enumerate(claims):
        if not isinstance(cl, dict):
            problems.append("claims[%d] 不是对象" % i)
            continue
        ev = cl.get("evidence") or []
        if not ev:
            problems.append("claims[%d] 缺 evidence" % i)
            continue
        ok_ev = all(
            isinstance(e, dict) and (e.get("paragraph_id") or e.get("location"))
            and (e.get("quote") or "").strip()
            for e in ev
        )
        if not ok_ev:
            problems.append("claims[%d] evidence 缺 paragraph_id/location 或 quote" % i)
        ids = distinct_doc_ids(ev)
        if len(ids) > 1 and len(ev) < 2:
            problems.append("claims[%d] 声明跨文档但引文不足 2 条" % i)

    n_conflicts = len(conflicts)

    # 8) coverage 统计块一致性
    cov = inner.get("coverage")
    if isinstance(cov, dict):
        if int(cov.get("cells") or 0) != len(matrix):
            problems.append("coverage.cells=%r 与实际 matrix 格数 %d 不符" % (cov.get("cells"), len(matrix)))
        if int(cov.get("reported") or 0) != n_reported:
            problems.append("coverage.reported=%r 与实际 %d 不符" % (cov.get("reported"), n_reported))
        if int(cov.get("pairwise_records") or 0) != len(pairwise):
            problems.append("coverage.pairwise_records=%r 与实际 %d 不符" % (
                cov.get("pairwise_records"), len(pairwise)))
        if int(cov.get("conflicts") or 0) != n_conflicts:
            problems.append("coverage.conflicts=%r 与实际 %d 不符" % (cov.get("conflicts"), n_conflicts))

    report = {
        "ok": not problems,
        "problems": problems,
        "cells": len(matrix),
        "docs": len(docs),
        "fields": len(fields),
        "reported": n_reported,
        "not_reported": n_notrep,
        "not_comparable": n_notcomp,
        "pairwise_records": len(pairwise),
        "pairwise_dual_evidence": n_pair_valid,
        "conflicts": n_conflicts,
        "claims": len(claims),
    }
    try:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=1)
    except Exception:
        pass

    if problems:
        print("[check_result] FAIL（%d 处）" % len(problems))
        for p in problems[:50]:
            print("  - %s" % p)
        return 1
    print("[check_result] PASS（%d 格 = %d 文档 × %d 字段；reported %d / not_reported %d / not_comparable %d；"
          "pairwise %d 条（双引文 %d）；冲突 %d；claims %d）" % (
              len(matrix), len(docs), len(fields), n_reported, n_notrep, n_notcomp,
              len(pairwise), n_pair_valid, n_conflicts, len(claims)))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[check_result] 异常降级: %s" % e)
        sys.exit(1)
