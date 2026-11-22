#!/usr/bin/env python3
"""verify_check.py — 文献筛选智能排序校验器（极简版）。
校验相关性三分枚举 / 覆盖 / 排序规则事前声明 / 契约字段。退出码恒 0。"""
import argparse, json, os, sys

REL_ENUM = {"directly_relevant", "indirectly_relevant", "irrelevant"}

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
        cands = case.get("candidates", [])
        scr = result.get("screening", [])
        ids = {s.get("paper_id") for s in scr}
        for c in cands:
            if c.get("paper_id") not in ids:
                problems.append(f"candidate {c.get('paper_id')} 未筛选")
        for s in scr:
            if s.get("relevance") not in REL_ENUM:
                problems.append(f"relevance 非法: {s.get('paper_id')}")
            if not s.get("basis"):
                problems.append(f"{s.get('paper_id')} 缺 basis")
        rr = result.get("rank_rule", {})
        if not rr.get("declared_at"):
            problems.append("rank_rule 缺 declared_at")
        if not result.get("ranked_order"):
            problems.append("缺 ranked_order")

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