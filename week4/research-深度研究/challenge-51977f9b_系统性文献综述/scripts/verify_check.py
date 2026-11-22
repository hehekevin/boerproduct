#!/usr/bin/env python3
"""verify_check.py — 系统性文献综述筛选闭环校验器（极简版）。
校验 criteria 事前声明 / 逐条纳排判定 / 漏斗计数闭合 / 契约字段齐全。
退出码恒 0，判据写在 --out 的 validator_verdict 与 result.validator_verdict。"""
import argparse, json, os, sys

KNOWN_DECISION = {"included", "excluded", "pending_review"}

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

        cr = result.get("criteria", {})
        if not cr.get("version") or not cr.get("declared_at"):
            problems.append("criteria 缺 version/declared_at")

        recs = result.get("records", [])
        included = excluded = pending = 0
        for i, r in enumerate(recs):
            dec = r.get("decision")
            if dec not in KNOWN_DECISION:
                problems.append(f"records[{i}] decision 枚举非法: {dec}")
                continue
            if dec == "included":
                included += 1
                if not r.get("criteria_ref"):
                    problems.append(f"records[{i}] included 缺 criteria_ref")
            elif dec == "excluded":
                excluded += 1
                if not r.get("reason_code"):
                    problems.append(f"records[{i}] excluded 缺 reason_code")
            else:
                pending += 1
                if not r.get("pending_reason") and not r.get("reason_code"):
                    problems.append(f"records[{i}] pending 缺 pending_reason")
            if r.get("judged") is True and not r.get("evidence_quote"):
                problems.append(f"records[{i}] 缺 evidence_quote")

        fn = result.get("funnel", {})
        if fn.get("identified", 0) != len(recs):
            problems.append(f"funnel.identified {fn.get('identified')} != records {len(recs)}")
        if fn.get("included", -1) != included or fn.get("excluded", -1) != excluded or fn.get("pending_review", -1) != pending:
            problems.append(f"funnel 计数与判定不符 (inc {included}/exc {excluded}/pend {pending})")
        if fn.get("closure") != "closed":
            problems.append("funnel.closure != closed")

        oc = case.get("output_contract", {})
        fields = oc.get("fields", []) if isinstance(oc, dict) else oc
        for f_ in fields:
            if f_ not in res:
                problems.append(f"缺 output_contract 字段: {f_}")

        verdict = "PASS" if not problems else "FAIL"
    except Exception as e:
        verdict = "FAIL"
        problems = [f"verify 异常: {e}"]

    report = {"validator_verdict": verdict, "problems": problems, "checked": True}
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