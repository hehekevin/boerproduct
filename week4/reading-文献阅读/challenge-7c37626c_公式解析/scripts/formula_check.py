#!/usr/bin/env python3
"""formula_check.py — 公式解析结果校验器（加固版：新增 result 非空与 claims 非空检查）。"""
from __future__ import annotations

import argparse
import json
import sys

PROV = {"原文定义", "上下文推断", "常识补充"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--result", required=True)
    ap.add_argument("--case", default=None)
    ap.add_argument("--out", default="formula_check.json")
    args = ap.parse_args()

    problems = []
    try:
        with open(args.result, "r", encoding="utf-8") as f:
            res = json.load(f)
    except Exception as e:
        print("[formula_check] FAIL: result.json 不是合法 JSON: %s" % e)
        return 1

    if not res.get("case_id"):
        problems.append("缺少 case_id")
    for k in ("status", "result", "claims", "uncertainties"):
        if k not in res:
            problems.append("缺少通用契约字段: %s" % k)

    inner = res.get("result") if isinstance(res.get("result"), dict) else {}
    if not inner:
        problems.append("result 字段为空/非对象（主产物不得为空，任何分支都要有可用内容）")
    formulas = inner.get("formulas") or []
    for i, fm in enumerate(formulas):
        if not isinstance(fm, dict):
            continue
        fid = fm.get("formula_id", i)
        conv = fm.get("conversion")
        if conv not in ("full", "partial", "failed"):
            problems.append("[%s] conversion 非法: %r" % (fid, conv))
        if conv == "full" and not (fm.get("latex") or "").strip():
            problems.append("[%s] conversion=full 但 latex 为空" % fid)
        if conv == "partial" and not (fm.get("ambiguity_notes") or "").strip():
            problems.append("[%s] conversion=partial 但缺 ambiguity_notes" % fid)
        if conv != "failed" and not (fm.get("latex") or "").strip():
            problems.append("[%s] latex 为空串（产物非空生命线被破坏）" % fid)

    variables = inner.get("variables") or []
    for i, v in enumerate(variables):
        if not isinstance(v, dict):
            continue
        if v.get("provenance") not in PROV:
            problems.append("variables[%d] provenance 非法: %r" % (i, v.get("provenance")))
        if v.get("provenance") == "原文定义" and not (v.get("first_defined_at") or "").strip():
            problems.append("variables[%d] 原文定义但缺 first_defined_at" % i)

    verifs = inner.get("verification") or []
    if not verifs:
        problems.append("verification 数组为空（核验是必做交付：能算的算，"
                        "不能算的写 status=not_recomputable+missing）")
    for i, vr in enumerate(verifs):
        if not isinstance(vr, dict):
            continue
        st = vr.get("status")
        if st == "not_recomputable":
            if not (vr.get("missing") or vr.get("notes") or "").__str__().strip():
                if not vr.get("missing"):
                    problems.append("verification[%d] not_recomputable 但缺 missing 清单" % i)
            continue
        exp, comp = vr.get("expected"), vr.get("computed")
        if (exp is None) ^ (comp is None):
            problems.append("verification[%d] expected/computed 只填了一个" % i)
        wt = vr.get("within_tolerance")
        if wt is True and exp is not None and comp is not None:
            try:
                rel = abs(float(exp) - float(comp)) / max(abs(float(exp)), 1e-12)
                if rel > 0.05:
                    problems.append("verification[%d] within_tolerance=true 但相对误差 %.1f%%>5%%"
                                    % (i, rel * 100))
            except (TypeError, ValueError):
                problems.append("verification[%d] expected/computed 非数值却判定容差" % i)

    derivs = inner.get("derivations") or []
    gap_steps = [d for d in derivs if isinstance(d, dict) and d.get("gap")]
    if gap_steps:
        unc = res.get("uncertainties") or {}
        blob = json.dumps(unc, ensure_ascii=False)
        for d in gap_steps:
            key = str(d.get("step_no"))
            if key not in blob and "gap" not in blob:
                problems.append("推导步 %s 标 gap 但未列入 uncertainties" % key)

    claims = res.get("claims") or []
    if not claims:
        problems.append("claims 数组为空（每条关键论断都应带 evidence 指回原文）")
    for i, c in enumerate(claims):
        if isinstance(c, dict) and not (c.get("evidence") or []):
            problems.append("claims[%d] 缺 evidence" % i)

    cov = inner.get("coverage") or {}
    if cov.get("not_recomputable"):
        for i, vr in enumerate(verifs):
            if isinstance(vr, dict) and vr.get("computed") is not None:
                problems.append("coverage.not_recomputable=true 但 verification[%d] 有 computed（编造检测）" % i)

    report = {"ok": not problems, "problems": problems,
              "counts": {"formulas": len(formulas), "variables": len(variables),
                         "derivations": len(derivs), "verification": len(verifs),
                         "claims": len(claims)}}
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)

    if problems:
        print("[formula_check] FAIL（%d 处）" % len(problems))
        for p in problems[:50]:
            print("  - %s" % p)
        return 1
    print("[formula_check] PASS（%s）" % report["counts"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
