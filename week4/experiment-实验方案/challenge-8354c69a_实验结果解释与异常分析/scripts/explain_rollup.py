#!/usr/bin/env python3
"""explain_rollup.py — Step 4 配对/回证/可执行性机械汇总（exp-result-explain）。

对每组分析机械复算：异常-原因配对完备性（pairing）、无证据解释数
（unbound_explanations）、可执行复核数（executable_rechecks）、对齐判定口径
一致性（alignment_consistency）、仅猜测无证据的原因数（speculation_only）、
penalty_total / overall / direction，写入 result.explain_summary（仅此键）。
口径取 --rules 台账（缺省回退 result.judge_rules）。全捕获容错，退出码恒为 0。

用法：
    python3 explain_rollup.py --result /app/output/result.json [--rules /app/work/judge_rules.json]
"""
from __future__ import annotations

import argparse
import json
import os
import sys


def load_rules(path, result):
    rules = None
    try:
        if path and os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                rules = json.load(f)
    except Exception:
        rules = None
    if not isinstance(rules, dict):
        rules = (result.get("result") or {}).get("judge_rules") or {}
    return rules


def penalty_of(rules, judgment):
    try:
        return int((rules.get("penalty_map") or {}).get(judgment, 1))
    except Exception:
        return 1


def grade_band(rules, total):
    try:
        bands = rules.get("grade_bands") or {"low": [0, 1], "some_concerns": [2, 4], "high": [5, 9999]}
        for name, (lo, hi) in bands.items():
            if lo <= total <= hi:
                return name
    except Exception:
        pass
    return "uncertain"


def has_evidence(item):
    if not isinstance(item, dict):
        return False
    q = str(item.get("evidence_quote") or "").strip()
    loc = str(item.get("evidence_location") or "").strip()
    return bool(q) and bool(loc)


def vague_action(rules, action):
    words = rules.get("vague_recheck_words") or ["检查数据质量", "check data quality"]
    a = str(action or "").strip().lower()
    if not a:
        return True
    for w in words:
        if str(w).lower() in a:
            return True
    return False


def rollup_analysis(a, rules, pending_review):
    aid = str(a.get("analysis_id") or "?")
    anomalies = a.get("anomalies") or []
    causes = a.get("causes") or []
    rechecks = a.get("rechecks") or []
    followups = a.get("followups") or []
    trend = a.get("trend") or {}
    align = a.get("alignment") or {}
    out = {"analysis_id": aid}

    # 1) 异常-原因配对
    anom_ids = {str(x.get("anomaly_id")) for x in anomalies if isinstance(x, dict) and x.get("anomaly_id")}
    orphan_causes = [str(c.get("cause_id")) for c in causes
                     if isinstance(c, dict) and str(c.get("anomaly_id") or "") not in anom_ids]
    bound = {}
    for c in causes:
        if isinstance(c, dict) and c.get("anomaly_id"):
            bound.setdefault(str(c.get("anomaly_id")), 0)
            bound[str(c.get("anomaly_id"))] += 1
    unpaired = [i for i in anom_ids if bound.get(i, 0) < 1]
    out["orphan_causes"] = orphan_causes
    out["unpaired_anomalies"] = sorted(unpaired)
    out["pairing_complete"] = not orphan_causes and not unpaired

    # 2) 解释回证
    unbound = []
    if not has_evidence(trend):
        unbound.append("trend")
    if not has_evidence(align):
        unbound.append("alignment")
    for x in anomalies:
        if not has_evidence(x):
            unbound.append(str(x.get("anomaly_id") or "anomaly"))
    for x in causes:
        if not has_evidence(x):
            unbound.append(str(x.get("cause_id") or "cause"))
    for x in rechecks:
        if not has_evidence(x):
            unbound.append(str(x.get("recheck_id") or "recheck"))
    for x in followups:
        if not has_evidence(x):
            unbound.append(str(x.get("followup_id") or "followup"))
    out["unbound_explanations"] = unbound
    out["unbound_count"] = len(unbound)

    # 3) 复核可执行性（四要素）
    executable, non_exec = 0, []
    for r in rechecks:
        if not isinstance(r, dict):
            continue
        ok = bool(str(r.get("action") or "").strip()) and bool(str(r.get("target_file") or "").strip()) \
            and (bool(str(r.get("target_field") or "").strip()) or bool(str(r.get("method") or "").strip())) \
            and bool(str(r.get("expected_outcome") or "").strip())
        if ok and not vague_action(rules, r.get("action")):
            executable += 1
            if r.get("executable") is False:
                non_exec.append("%s(标记 executable=false 但四要素齐备，请核对)" % r.get("recheck_id"))
        else:
            non_exec.append(str(r.get("recheck_id") or "recheck"))
    out["executable_rechecks"] = executable
    out["non_executable_rechecks"] = non_exec

    # 4) 对齐判定口径一致性
    verdicts = rules.get("alignment_verdicts") or ["supported", "partially_supported", "not_supported", "unassessable"]
    v = align.get("verdict")
    problems = []
    if not v:
        problems.append("alignment.verdict 缺失")
    elif v not in verdicts:
        problems.append("alignment.verdict=%s 非法" % v)
    if not str(align.get("basis") or "").strip():
        problems.append("alignment.basis 缺失")
    neg_judgments = {"inadequate", "unreported"}
    appraisals = a.get("appraisals") or []
    has_neg = any(x.get("judgment") in neg_judgments for x in appraisals if isinstance(x, dict))
    has_unassessable = any(x.get("judgment") == "unassessable" for x in appraisals if isinstance(x, dict))
    if v == "supported" and (has_neg or has_unassessable):
        problems.append("verdict=supported 但存在负面/弃权条目（口径矛盾）")
    if v == "unassessable":
        pr_ids = {str(p.get("analysis_id")) for p in pending_review if isinstance(p, dict)}
        if aid not in pr_ids:
            problems.append("verdict=unassessable 未登记 pending_review")
    out["alignment_consistent"] = not problems
    out["alignment_problems"] = problems
    out["alignment_verdict"] = v

    # 5) 仅猜测无证据的原因
    verbs = rules.get("speculation_verbs") or ["可能是", "推测", "疑为"]
    spec = []
    for c in causes:
        if not isinstance(c, dict):
            continue
        sup = c.get("supporting_evidence") or []
        hyp = str(c.get("hypothesis") or "")
        if not sup and any(str(w).lower() in hyp.lower() for w in verbs):
            spec.append(str(c.get("cause_id") or "cause"))
    out["speculation_only"] = spec

    # 6) penalty / overall / direction
    total = 0
    abstain = 0
    has_against = has_favors = False
    for x in appraisals:
        if not isinstance(x, dict):
            continue
        j = x.get("judgment")
        total += penalty_of(rules, j)
        if j == "unassessable":
            abstain += 1
        bd = str(x.get("bias_direction") or "")
        if bd == "against_conclusion":
            has_against = True
        elif bd == "favors_conclusion":
            has_favors = True
    overall = grade_band(rules, total)
    if abstain >= 2 or (abstain >= 1 and total <= 1):
        overall = "uncertain"
    direction = "against_conclusion" if has_against else ("favors_conclusion" if has_favors else "unclear")
    out["penalty_total"] = total
    out["overall"] = overall
    out["direction"] = direction
    return out


def main():
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", required=True)
        ap.add_argument("--rules", default=None, help="judge_rules 台账路径")
        args = ap.parse_args()
    except Exception as e:
        print("[explain_rollup] 参数解析失败（已降级）: %s" % e)
        return 0

    marker = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "SKILL.md")
    marker_hit = os.path.exists(marker)
    if not marker_hit:
        print("[explain_rollup] WARN: 定位标志未命中（脚本未与 SKILL.md 同包），仍继续")

    try:
        with open(args.result, "r", encoding="utf-8") as f:
            result = json.load(f)
    except Exception as e:
        print("[explain_rollup] FAIL: result.json 读取失败：%s（不中断交付）" % e)
        return 0

    rules = load_rules(args.rules, result)
    inner = result.get("result") or {}
    analyses = inner.get("analyses") or []
    pending = inner.get("pending_review") or []

    per, problems = [], []
    totals = {"pairing_complete": 0, "unbound_total": 0, "executable_rechecks": 0,
              "alignment_inconsistent": 0, "speculation_only_total": 0}
    for a in analyses:
        try:
            r = rollup_analysis(a, rules, pending)
        except Exception as e:
            problems.append("%s 汇总异常: %s" % (a.get("analysis_id"), e))
            continue
        per.append(r)
        if r.get("pairing_complete"):
            totals["pairing_complete"] += 1
        else:
            problems.append("%s: 配对不完备 unpaired=%s orphan=%s"
                            % (r["analysis_id"], r.get("unpaired_anomalies"), r.get("orphan_causes")))
        totals["unbound_total"] += r.get("unbound_count", 0)
        if r.get("unbound_count"):
            problems.append("%s: %d 条解释缺证据 %s" % (r["analysis_id"], r["unbound_count"], r["unbound_explanations"]))
        totals["executable_rechecks"] += r.get("executable_rechecks", 0)
        if not r.get("alignment_consistent"):
            totals["alignment_inconsistent"] += 1
            problems.append("%s: %s" % (r["analysis_id"], "; ".join(r.get("alignment_problems") or [])))
        totals["speculation_only_total"] += len(r.get("speculation_only") or [])

    out = {"computed_by": "scripts/explain_rollup.py", "per_analysis": per,
           "totals": totals, "rules_version": str(rules.get("version") or "unknown")}
    try:
        if isinstance(inner, dict):
            inner["explain_summary"] = out  # 仅此键归本脚本
        with open(args.result, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=1)
    except Exception as e:
        problems.append("回写失败: %s" % e)

    print("[explain_rollup] case_id=%s | 组数 %d | marker_hit=%s"
          % (result.get("case_id"), len(per), marker_hit))
    print("  totals: %s" % json.dumps(totals, ensure_ascii=False))
    for pr in problems:
        print("  WARN: %s" % pr)
    print("[explain_rollup] 已回写 result.explain_summary")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[explain_rollup] 未预期异常（已降级）: %s" % e)
        sys.exit(0)
