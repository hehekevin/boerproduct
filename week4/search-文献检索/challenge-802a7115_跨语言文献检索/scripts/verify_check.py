#!/usr/bin/env python3
"""verify_check.py — 多维度覆盖 + 成文报告校验器（自动生成）。
校验 aspect 维度覆盖 / 逐字回证 / 严重度口径 / 成文报告 / 契约字段。
退出码恒 0，判据写在 validator_verdict。"""
import argparse, json, os, re, sys

ASPECTS = ('term_expansion', 'translation', 'crosslingual_match', 'language_detection', 'mistranslation_review')
CATEGORIES = ("fact_error", "insufficient_evidence", "norm_issue", "suggestion")
SEVERITIES = ("critical", "major", "minor")
STATUSES = ("confirmed", "pending")
MANU_KEYS = ("manuscript", "paper", "document", "full_text", "text", "body", "content")

def load(p):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def norm(s):
    return re.sub(r"\s+", "", str(s or ""))

def all_text(case):
    if not isinstance(case, dict):
        return ""
    buf = []
    def walk(o):
        if isinstance(o, dict):
            for v in o.values(): walk(v)
        elif isinstance(o, list):
            for v in o: walk(v)
        elif isinstance(o, str):
            if len(o.strip()) >= 4: buf.append(o)
    walk(case)
    return norm("".join(buf))

def contract_fields(case):
    oc = case.get("output_contract") if isinstance(case, dict) else None
    if oc is None: return []
    if isinstance(oc, dict):
        for k in ("fields", "required_fields"):
            if isinstance(oc.get(k), list): return [str(x) for x in oc[k]]
        return [str(k) for k in oc.keys()]
    if isinstance(oc, list): return [str(x) for x in oc]
    return []

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
        findings = result.get("findings", [])
        src = all_text(case)

        # 维度覆盖
        real = {k: sum(1 for f in findings if f.get("aspect") == k) for k in ASPECTS}
        cov = result.get("aspect_coverage", [])
        covered = {c.get("aspect") for c in cov if isinstance(c, dict)}
        for k in ASPECTS:
            if real.get(k, 0) == 0 and k not in covered:
                problems.append("方面 %s 未覆盖" % k)

        # findings 枚举 + 回证
        for i, f in enumerate(findings):
            fid = f.get("finding_id") or "F%d" % i
            if f.get("aspect") not in ASPECTS:
                problems.append("%s aspect 非法: %r" % (fid, f.get("aspect")))
            if f.get("category") not in CATEGORIES:
                problems.append("%s category 非法: %r" % (fid, f.get("category")))
            if f.get("severity") not in SEVERITIES:
                problems.append("%s severity 非法: %r" % (fid, f.get("severity")))
            if f.get("status") == "confirmed":
                q = norm(f.get("quote"))
                if not (src and len(q) >= 6 and q in src):
                    problems.append("%s quote 不在原文（逐字回证失败）" % fid)
                if not str(f.get("location") or "").strip():
                    problems.append("%s location 为空" % fid)

        # 严重度口径
        rub = result.get("severity_rubric", {})
        if not rub.get("declared_at"):
            problems.append("severity_rubric 未声明")
        for f in findings:
            if f.get("category") == "suggestion" and f.get("severity") != "minor":
                problems.append("%s suggestion 应为 minor" % f.get("finding_id"))
            if f.get("category") == "fact_error" and f.get("severity") not in ("critical", "major"):
                problems.append("%s fact_error 应为 critical/major" % f.get("finding_id"))

        # 成文报告
        rr = result.get('search_report') or ""
        if len(str(rr).strip()) < 200:
            problems.append("search_report 缺失或不足 200 字")

        # 契约字段
        for f_ in contract_fields(case):
            if f_ not in res:
                problems.append("缺 output_contract 字段: %s" % f_)

        verdict = "PASS" if not problems else "FAIL"
    except Exception as e:
        verdict = "FAIL"
        problems = ["verify 异常: %s" % e]

    report = {"validator_verdict": verdict, "problems": problems}
    try:
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=1)
        if args.emit_into:
            cur = load(args.result) or {}
            cur["validator_verdict"] = verdict
            cur.setdefault("self_check", []).append({"item": "verify_check", "verdict": verdict, "problems": len(problems)})
            with open(args.result, "w", encoding="utf-8") as f:
                json.dump(cur, f, ensure_ascii=False, indent=1)
    except Exception:
        pass
    print(json.dumps(report, ensure_ascii=False))
    sys.exit(0)

if __name__ == "__main__":
    main()
