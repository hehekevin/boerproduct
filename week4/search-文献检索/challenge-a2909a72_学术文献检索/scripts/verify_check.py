#!/usr/bin/env python3
"""verify_check.py — 学术文献检索校验器（极简版）。
校验概念/检索式数量与布尔逻辑 / intent / 契约字段。退出码恒 0。"""
import argparse, json, os, sys

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
        concepts = result.get("concepts", [])
        queries = result.get("query_plan", [])
        if not concepts:
            problems.append("concepts 为空")
        if not queries:
            problems.append("query_plan 为空")
        for q in queries:
            qs = q.get("query_string", "")
            if not qs:
                problems.append("query_string 空")
            elif not any(op in qs.upper() for op in (" AND ", " OR ", " NOT ")):
                problems.append(f"query_string 缺布尔逻辑: {q.get('query_id')}")
            if not q.get("intent"):
                problems.append(f"{q.get('query_id')} 缺 intent")

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