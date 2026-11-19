#!/usr/bin/env python3
"""quality_audit.py — 质量评价一致性审计（sysrev-review-synthesis）。

对 result.quality_appraisal 做机械审计（与题面"质量评价"环节对应）：
  1. 每条纳入（非重复）记录必须有一条质量评价 assessment；
  2. 每个维度判定取值必须 ∈ 量表 allowed_judgments（resources/quality_scales.json）；
  3. overall_grade 必须等于按量表 derive_rule 由维度得分机械推导的等级
     （yes=1, partly=0.5, no/unclear=0；mean>=0.8→high, >=0.5→moderate, <0.5→low）。
纯函数 analyze_quality(inner, scale=None) 供 verify_check.py 复用；CLI 模式只读
审计、不改写 result.json，报告写 --out。退出码恒为 0（结论记在 verdict 字段）。
用法：
    python3 quality_audit.py --result /app/output/result.json [--out /app/work/quality_audit.json]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

BUILTIN_DIMS = ("Q1", "Q2", "Q3", "Q4", "Q5", "Q6")
BUILTIN_JUDGMENTS = ("yes", "partly", "no", "unclear")
SCORES = {"yes": 1.0, "partly": 0.5, "no": 0.0, "unclear": 0.0}


def load_scale():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "resources", "quality_scales.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict) and d.get("dimensions"):
            return d
    except Exception:
        pass
    return {"scale_id": "BUILTIN", "version": "v0", "dimensions": [{"dim_id": k, "text": k} for k in BUILTIN_DIMS],
            "allowed_judgments": list(BUILTIN_JUDGMENTS), "scores": SCORES,
            "derive_rule": {"thresholds": {"high": 0.8, "moderate": 0.5}}}


def derive_grade(scores_list, scale):
    """按量表 derive_rule 机械推导等级（与 derive_rule.formula 同口径）。"""
    th = ((scale.get("derive_rule") or {}).get("thresholds")) or {"high": 0.8, "moderate": 0.5}
    if not scores_list:
        return "low"
    mean = sum(scores_list) / float(len(scores_list))
    if mean >= float(th.get("high", 0.8)):
        return "high"
    if mean >= float(th.get("moderate", 0.5)):
        return "moderate"
    return "low"


def analyze_quality(inner, scale=None):
    """纯函数审计（不写盘）。返回 {problems, self_check, recomputed, missing}。"""
    sc = scale or load_scale()
    dims = {str(d.get("dim_id")) for d in (sc.get("dimensions") or []) if isinstance(d, dict)}
    allowed = {str(x) for x in (sc.get("allowed_judgments") or BUILTIN_JUDGMENTS)}
    scores_map = dict(SCORES)
    scores_map.update({k: float(v) for k, v in (sc.get("scores") or {}).items() if isinstance(v, (int, float))})
    problems, self_check, recomputed = [], [], {}
    qa = inner.get("quality_appraisal") if isinstance(inner, dict) else None
    qa = qa if isinstance(qa, dict) else {}
    assessments = [a for a in (qa.get("assessments") or []) if isinstance(a, dict)]
    aidx = {str(a.get("record_id")): a for a in assessments}
    records = [r for r in (inner.get("records") or []) if isinstance(r, dict)]
    included = [r for r in records if r.get("decision") == "included" and not r.get("duplicate_of")]
    missing = []

    for r in included:
        rid = str(r.get("record_id") or "")
        a = aidx.get(rid)
        ok_present = a is not None
        self_check.append({"item": "quality[%s].present" % rid,
                           "template_value": "included ⇒ 质量评价 assessment 存在", "applied": True,
                           "match": ok_present})
        if not ok_present:
            missing.append(rid)
            problems.append("纳入记录 %s 缺质量评价 assessment（每条纳入研究须逐条评价）" % rid)
            recomputed[rid] = "unknown"
            continue
        ds = a.get("dimensions") or []
        vals, dim_ok = [], True
        for d in ds if isinstance(ds, list) else []:
            if not isinstance(d, dict):
                dim_ok = False
                continue
            did, j = str(d.get("dim_id")), d.get("judgment")
            if did not in dims:
                problems.append("%s 质量维度 %r 不在量表 %s 维度清单中" % (rid, did, sc.get("scale_id")))
                dim_ok = False
            if j not in allowed:
                problems.append("%s 维度 %s 判定 %r 非法（须 ∈ %s）" % (rid, did, j, sorted(allowed)))
                dim_ok = False
            vals.append(scores_map.get(j if j in allowed else "unclear", 0.0))
        rec = derive_grade(vals, sc)
        recomputed[rid] = rec
        declared = a.get("overall_grade")
        ok_grade = declared == rec
        self_check.append({"item": "quality[%s].grade_consistent" % rid,
                           "template_value": "overall_grade == 量表机械推导等级(%s)" % rec,
                           "applied": True, "match": ok_grade})
        if not ok_grade:
            problems.append("%s overall_grade 声明为 %r，按量表推导应为 %r（等级与维度判定不一致）"
                            % (rid, declared, rec))
        if not dim_ok:
            problems.append("%s 质量评价维度判定存在非法项（维度 id 或 judgment 越界）" % rid)
        if not str(a.get("grade_basis") or "").strip():
            problems.append("%s 缺 grade_basis（须写明等级如何由维度判定得出）" % rid)
    # 未纳入记录出现多余评价不算违规，但登记数量供报告
    extra = sorted(set(aidx) - {str(r.get("record_id")) for r in included})
    return {"problems": problems, "self_check": self_check, "recomputed": recomputed,
            "missing": missing, "extra_assessments": extra,
            "n_included": len(included), "n_assessed": len(assessments)}


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", required=True)
        ap.add_argument("--out", default="/app/work/quality_audit.json")
        args = ap.parse_args()
    except Exception as e:
        print("[quality_audit] 参数解析失败（已降级）: %s" % e)
        return 0
    try:
        with open(args.result, "r", encoding="utf-8") as f:
            res = json.load(f)
        inner = res.get("result") if isinstance(res, dict) else None
        if not isinstance(inner, dict):
            raise ValueError("result 非对象")
    except Exception as e:
        print("[quality_audit] FAIL: result.json 不可读: %s（不中断交付）" % e)
        _dump(args.out, {"verdict": "FAIL", "problems": ["读取失败: %s" % e]})
        return 0
    rep = analyze_quality(inner)
    verdict = "FAIL" if rep["problems"] else "PASS"
    _dump(args.out, {"verdict": verdict, **rep})
    print("[quality_audit] %s: 纳入 %d 条 / 已评价 %d 条 / 缺评 %d 条 / 推导等级 %s"
          % (verdict, rep["n_included"], rep["n_assessed"], len(rep["missing"]),
             json.dumps(rep["recomputed"], ensure_ascii=False)))
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
        print("[quality_audit] 未预期异常（已降级，不中断交付）: %s" % e)
        sys.exit(0)
