#!/usr/bin/env python3
"""verify_check.py — 检索覆盖率遗漏分析校验器（极简版）。
校验覆盖计量一致 / miss_reason 枚举 / 漏检证据 / 契约字段。
退出码恒 0，判据写在 validator_verdict。"""
import argparse, json, os, sys

MISS_ENUM = {"synonym_not_covered", "field_too_narrow", "time_window", "source_not_indexed", "identifier_anomaly"}

def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--result", required=True)
    ap.add_argument("--case", required=True)
    ap.add_argument("--out", default="/app/work/verify_check.json")
    ap.add_argument("--emit-into", action="store_true")
    args = ap.parse_args()
    problems = []
    try:
        res = load(args.result)
        case = load(args.case)
        result = res.get("result", {}) if isinstance(res.get("result"), dict) else {}
        cm = result.get("coverage_metrics", {})
        misses = result.get("misses", [])
        matches = result.get("matches", [])
        if cm.get("hit", 0) != len(matches):
            problems.append("coverage_metrics.hit 与 matches 计数不一致")
        if cm.get("miss", 0) != len(misses):
            problems.append("coverage_metrics.miss 与 misses 计数不一致")
        for m in misses:
            if m.get("miss_reason") not in MISS_ENUM:
                problems.append(f"miss_reason 非法或未填: {m.get('ref_id')}")
            if not m.get("evidence"):
                problems.append(f"miss 缺 evidence: {m.get('ref_id')}")
        mr = result.get("match_rule", {})
        if not mr.get("declared_at"):
            problems.append("match_rule 缺 declared_at")

        oc = case.get("output_contract", {})
        fields = oc.get("fields", []) if isinstance(oc, dict) else oc
        for f_ in fields:
            if f_ not in res:
                problems.append(f"缺 output_contract 字段: {f_}")
        verdict = "PASS" if not problems else "FAIL"
    except Exception as e:
        verdict = "FAIL"
        problems = [f"verify 异常: {e}"]

    report = {"validator_verdict": verdict, "problems": problems}
    try:
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=1)
        if args.emit_into:
            try:
                res = load(args.result)
            except Exception:
                res = {}
            res["validator_verdict"] = verdict
            res.setdefault("self_check", []).append({"item": "verify_check", "verdict": verdict, "problems": len(problems)})
            with open(args.result, "w", encoding="utf-8") as f:
                json.dump(res, f, ensure_ascii=False, indent=1)
    except Exception:
        pass
    print(json.dumps(report, ensure_ascii=False))
    sys.exit(0)

if __name__ == "__main__":
    main()