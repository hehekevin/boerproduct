#!/usr/bin/env python3
"""verify_check.py — 实验方案可行性评估校验器（资源四态核验极简版）。
校验资源四态判定枚举 / 逐方案覆盖 / feasibility 与条件一致性 / 契约字段。
退出码恒 0，判据写在 validator_verdict。"""
import argparse, json, os, sys

STATUS_ENUM = {"available", "external", "to_purchase", "unavailable", "to_confirm"}
FEAS_ENUM = {"feasible", "conditionally_feasible", "infeasible"}

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
        plans = case.get("plans", [])
        checks = result.get("plan_checks", [])

        checked_ids = {c.get("plan_id") for c in checks}
        for p in plans:
            if p.get("plan_id") not in checked_ids:
                problems.append(f"plan {p.get('plan_id')} 未核验")

        for c in checks:
            rc = c.get("resource_checks", [])
            if not rc and not result.get("material_gaps"):
                problems.append(f"{c.get('plan_id')} resource_checks 空且无 material_gaps")
            for r in rc:
                if r.get("status") not in STATUS_ENUM:
                    problems.append(f"{c.get('plan_id')} status 非法: {r.get('status')}")
                if not r.get("basis") or not r.get("source_ref"):
                    problems.append(f"{c.get('plan_id')} 缺 basis/source_ref: {r.get('item')}")
            feas = c.get("feasibility")
            if feas not in FEAS_ENUM:
                problems.append(f"{c.get('plan_id')} feasibility 非法: {feas}")
            if feas != "feasible" and not c.get("conditions"):
                problems.append(f"{c.get('plan_id')} {feas} 缺 conditions")

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