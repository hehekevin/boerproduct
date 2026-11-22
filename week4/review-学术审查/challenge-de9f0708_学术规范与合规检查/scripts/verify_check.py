#!/usr/bin/env python3
"""verify_check.py — 学术规范与合规检查校验器（引用核验极简版）。
校验引文标号核验的状态/严重度枚举 / 逐字quote / 依据 / 契约字段。
退出码恒 0，判据写在 validator_verdict。"""
import argparse, json, os, sys

STATUS_ENUM = {"ok", "not_in_refs", "mismatch", "uncertain"}
SEV_ENUM = {"critical", "major", "minor"}

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
        checks = result.get("citation_checks", [])
        ms = case.get("manuscript", {}) or {}
        # 检测正文是否有引用标号
        has_cites = False
        for s in ms.get("sections", []):
            if any(ch.isdigit() for ch in s.get("text", "")) and ("[" in s.get("text","") or "（" in s.get("text","")):
                has_cites = True
        # 简化：只要求 citations 非空时逐条合法
        for c in checks:
            if c.get("status") not in STATUS_ENUM:
                problems.append(f"status 非法: {c.get('status')}")
            if c.get("severity") not in SEV_ENUM:
                problems.append(f"severity 非法: {c.get('severity')}")
            if not c.get("claim_quote"):
                problems.append(f"缺 claim_quote: {c.get('cite_marker')}")
            if c.get("status") in ("not_in_refs", "mismatch") and not c.get("basis"):
                problems.append(f"{c.get('status')} 缺 basis: {c.get('cite_marker')}")
        if not checks and has_cites:
            problems.append("稿件有引用标号但 citation_checks 为空")

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