#!/usr/bin/env python3
"""verify_check.py — 科研选题与创新性评估校验器（极简版）。
校验 research_question 五要素 / 创新点四类判定 / 可行性四要素 / 契约字段。
退出码恒 0，判据写在 validator_verdict。"""
import argparse, json, os, sys

TYPE_ENUM = {"method", "data", "scenario", "theory"}
COV_ENUM = {"novel", "overlapped", "partially_overlapped"}
FEAS_STATUS = {"satisfied", "conditional", "missing"}
FEAS_ELEMS = ("data", "method", "resource", "time")

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
        props = case.get("proposals", [])
        assessed = result.get("proposals", [])
        ids = {a.get("proposal_id") for a in assessed}
        for p in props:
            if p.get("proposal_id") not in ids:
                problems.append(f"proposal {p.get('proposal_id')} 未评估")

        for a in assessed:
            rq = a.get("research_question", {})
            for k in ("object", "variables", "baseline", "expected", "falsifiable_condition"):
                if not rq.get(k):
                    problems.append(f"{a.get('proposal_id')} research_question 缺 {k}")
            claims = a.get("innovation_claims", [])
            if not claims:
                problems.append(f"{a.get('proposal_id')} innovation_claims 空")
            for c in claims:
                if c.get("type") not in TYPE_ENUM:
                    problems.append(f"{a.get('proposal_id')} type 非法: {c.get('type')}")
                if c.get("coverage") not in COV_ENUM:
                    problems.append(f"{a.get('proposal_id')} coverage 非法")
                if c.get("coverage") != "novel" and not c.get("basis"):
                    problems.append(f"{a.get('proposal_id')} {c.get('coverage')} 缺 basis")
            feas = a.get("feasibility", {})
            for e in FEAS_ELEMS:
                if e not in feas:
                    problems.append(f"{a.get('proposal_id')} 缺可行性要素 {e}")
                else:
                    st = feas[e].get("status")
                    if st not in FEAS_STATUS:
                        problems.append(f"{a.get('proposal_id')} {e}.status 非法: {st}")
                    if st in ("conditional", "missing") and not feas[e].get("basis"):
                        problems.append(f"{a.get('proposal_id')} {e} 缺 basis")

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