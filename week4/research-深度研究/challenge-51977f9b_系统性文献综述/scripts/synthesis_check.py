#!/usr/bin/env python3
"""synthesis_check.py — 证据综合与结论强度分级一致性审计（sysrev-review-synthesis）。

对 result.synthesis 做机械审计（与题面"结论强度分级一致"机检点对应）：
  1. 每条综合结论 strength ∈ {strong, moderate, weak, insufficient}
     （resources/strength_rules.json）；
  2. **强度分级一致**：declared strength 必须等于按规则自上而下机械推导的级别
     （strong: ≥3 支持且无冲突且支持研究质量 ∈ {high, moderate}；moderate: ≥2 支持
     且冲突 ≤1；weak: ≥1 支持；insufficient: 0 支持）。支持研究的质量等级取自
     quality_appraisal.assessments（缺失按 unknown，unknown 不得支撑 strong/moderate）；
  3. supporting_records / conflicting_records 必须是真实存在的 included 记录 id；
  4. 结论与冲突证据矩阵、研究空白、偏倚登记齐备：gaps / bias_registry 为空时须有
     gaps_note / bias_note 说明为何为空（缺口与偏倚登记环节）。
纯函数 analyze_synthesis(inner) 供 verify_check.py 复用；CLI 只读审计。退出码恒 0。
用法：
    python3 synthesis_check.py --result /app/output/result.json [--out /app/work/synthesis_check.json]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

BUILTIN_LEVELS = ("strong", "moderate", "weak", "insufficient")
BUILTIN_RULES = {
    "strong": {"min_supporting": 3, "max_conflicting": 0, "allowed_support_grades": ("high", "moderate")},
    "moderate": {"min_supporting": 2, "max_conflicting": 1, "allowed_support_grades": ("high", "moderate")},
    "weak": {"min_supporting": 1, "max_conflicting": 999, "allowed_support_grades": ("high", "moderate", "low", "unknown")},
    "insufficient": {"min_supporting": 0, "max_conflicting": 999, "allowed_support_grades": ("high", "moderate", "low", "unknown")},
}


def load_rules():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "resources", "strength_rules.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict) and d.get("rules") and d.get("recompute_order"):
            return d
    except Exception:
        pass
    return {"levels": list(BUILTIN_LEVELS), "rules": BUILTIN_RULES,
            "recompute_order": list(BUILTIN_LEVELS),
            "consistency_rule": "declared strength == 机械推导级别"}


def derive_strength(n_support, n_conflict, grades, rules_doc):
    """按 recompute_order 自上而下取第一个满足全部条件的级别（纯函数）。"""
    for lvl in rules_doc.get("recompute_order") or list(BUILTIN_LEVELS):
        rule = (rules_doc.get("rules") or BUILTIN_RULES).get(lvl) or BUILTIN_RULES.get(lvl)
        if rule is None:
            continue
        if n_support < int(rule.get("min_supporting", 0)):
            continue
        if n_conflict > int(rule.get("max_conflicting", 999)):
            continue
        allowed = set(rule.get("allowed_support_grades") or ())
        if n_support > 0 and any(g not in allowed for g in grades):
            continue
        return lvl
    return "insufficient"


def analyze_synthesis(inner):
    """纯函数审计（不写盘）。返回 {problems, self_check, recomputed}。"""
    rules_doc = load_rules()
    levels = [str(x) for x in (rules_doc.get("levels") or BUILTIN_LEVELS)]
    problems, self_check, recomputed = [], [], {}
    syn = inner.get("synthesis") if isinstance(inner, dict) else None
    syn = syn if isinstance(syn, dict) else {}
    qa = inner.get("quality_appraisal") if isinstance(inner, dict) else None
    qa = qa if isinstance(qa, dict) else {}
    grade_map = {str(a.get("record_id")): str(a.get("overall_grade") or "unknown")
                 for a in (qa.get("assessments") or []) if isinstance(a, dict)}
    records = [r for r in (inner.get("records") or []) if isinstance(r, dict)]
    included_ids = {str(r.get("record_id")) for r in records
                    if r.get("decision") == "included" and not r.get("duplicate_of")}
    known_ids = {str(r.get("record_id")) for r in records}
    conclusions = [c for c in (syn.get("conclusions") or []) if isinstance(c, dict)]

    for i, c in enumerate(conclusions):
        cid = str(c.get("conclusion_id") or "synthesis.conclusions[%d]" % i)
        declared = c.get("strength")
        sup = [str(x) for x in (c.get("supporting_records") or [])]
        con = [str(x) for x in (c.get("conflicting_records") or [])]
        ok_level = declared in levels
        self_check.append({"item": "synthesis[%s].level_valid" % cid,
                           "template_value": "strength ∈ {strong,moderate,weak,insufficient}",
                           "applied": True, "match": ok_level})
        if not ok_level:
            problems.append("%s strength=%r 非法（须 ∈ %s）" % (cid, declared, levels))
        bad_sup = [x for x in sup if x not in included_ids]
        if bad_sup:
            problems.append("%s supporting_records 引用了不存在或非 included 的记录: %s" % (cid, bad_sup))
        bad_con = [x for x in con if x not in known_ids]
        if bad_con:
            problems.append("%s conflicting_records 引用了不存在的记录: %s" % (cid, bad_con))
        grades = [grade_map.get(x, "unknown") for x in sup]
        rec = derive_strength(len(sup), len(con), grades, rules_doc)
        recomputed[cid] = {"declared": declared, "recomputed": rec, "support_grades": grades,
                           "n_supporting": len(sup), "n_conflicting": len(con)}
        ok_cons = declared == rec
        self_check.append({"item": "synthesis[%s].strength_consistent" % cid,
                           "template_value": "declared == 机械推导(%s)" % rec,
                           "applied": True, "match": ok_cons})
        if ok_level and not ok_cons:
            problems.append("%s strength 声明为 %r，按规则推导应为 %r（%d 项支持/冲突 %d/支持质量 %s）"
                            % (cid, declared, rec, len(sup), len(con), grades))
        if not str(c.get("strength_basis") or "").strip():
            problems.append("%s 缺 strength_basis（须写明分级依据）" % cid)
        if not str(c.get("text") or "").strip():
            problems.append("%s 结论 text 为空" % cid)

    gaps, bias = syn.get("gaps"), syn.get("bias_registry")
    ok_gaps = isinstance(gaps, list) and (bool(gaps) or bool(str(syn.get("gaps_note") or "").strip()))
    self_check.append({"item": "synthesis.gaps_registered",
                       "template_value": "gaps 非空或以 gaps_note 说明", "applied": True, "match": ok_gaps})
    if not ok_gaps:
        problems.append("synthesis.gaps 为空或缺失且未以 gaps_note 说明（研究空白登记缺位）")
    ok_bias = isinstance(bias, list) and (bool(bias) or bool(str(syn.get("bias_note") or "").strip()))
    self_check.append({"item": "synthesis.bias_registered",
                       "template_value": "bias_registry 非空或以 bias_note 说明", "applied": True, "match": ok_bias})
    if not ok_bias:
        problems.append("synthesis.bias_registry 为空或缺失且未以 bias_note 说明（偏倚登记缺位）")
    cm = syn.get("conflict_matrix")
    ok_cm = isinstance(cm, list)
    self_check.append({"item": "synthesis.conflict_matrix_present",
                       "template_value": "conflict_matrix 落键（可为空数组）", "applied": True, "match": ok_cm})
    if not ok_cm:
        problems.append("synthesis.conflict_matrix 缺失（冲突证据矩阵须落键，可为空数组+说明）")
    return {"problems": problems, "self_check": self_check, "recomputed": recomputed,
            "n_conclusions": len(conclusions)}


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", required=True)
        ap.add_argument("--out", default="/app/work/synthesis_check.json")
        args = ap.parse_args()
    except Exception as e:
        print("[synthesis_check] 参数解析失败（已降级）: %s" % e)
        return 0
    try:
        with open(args.result, "r", encoding="utf-8") as f:
            res = json.load(f)
        inner = res.get("result") if isinstance(res, dict) else None
        if not isinstance(inner, dict):
            raise ValueError("result 非对象")
    except Exception as e:
        print("[synthesis_check] FAIL: result.json 不可读: %s（不中断交付）" % e)
        _dump(args.out, {"verdict": "FAIL", "problems": ["读取失败: %s" % e]})
        return 0
    rep = analyze_synthesis(inner)
    verdict = "FAIL" if rep["problems"] else "PASS"
    _dump(args.out, {"verdict": verdict, **rep})
    print("[synthesis_check] %s: 结论 %d 条 / 分级推导 %s"
          % (verdict, rep["n_conclusions"], json.dumps(rep["recomputed"], ensure_ascii=False)[:300]))
    for p in rep["problems"][:20]:
        print("  - %s" % p)
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
        print("[synthesis_check] 未预期异常（已降级，不中断交付）: %s" % e)
        sys.exit(0)
