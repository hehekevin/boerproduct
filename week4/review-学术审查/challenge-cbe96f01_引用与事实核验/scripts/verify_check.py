#!/usr/bin/env python3
"""verify_check.py — 引用与事实核验校验器（六方面覆盖 + 成文报告）。
校验 aspect 六方面覆盖 / 逐字回证 / 严重度口径 / review_report 成文 / 契约字段。
退出码恒 0，判据写在 validator_verdict。"""
import argparse, json, os, re, sys

ASPECTS = ("citation_support", "fact_source_reliability", "evidence_location",
           "numeric_stat_consistency", "argument_chain", "integrity_norms")
CATEGORIES = ("fact_error", "insufficient_evidence", "norm_issue", "suggestion")
SEVERITIES = ("critical", "major", "minor")
STATUSES = ("confirmed", "pending")
RUN_STATES = ("success", "partial", "unable_to_determine", "refused", None)
MANU_KEYS = ("manuscript", "paper", "document", "full_text", "text", "body", "content")

def load(p):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def norm(s):
    return re.sub(r"\s+", "", str(s or ""))

def manuscript_text(case):
    if not isinstance(case, dict):
        return ""
    root = None
    for k in MANU_KEYS:
        if k in case and isinstance(case[k], (dict, list, str)):
            root = case[k]; break
    if root is None:
        root = {k: v for k, v in case.items() if k != "output_contract"}
    buf = []
    def walk(o):
        if isinstance(o, dict):
            for v in o.values(): walk(v)
        elif isinstance(o, list):
            for v in o: walk(v)
        elif isinstance(o, str):
            if len(o.strip()) >= 4: buf.append(o)
    walk(root)
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
        src = manuscript_text(case)

        # 六方面覆盖
        real = {k: sum(1 for f in findings if f.get("aspect") == k) for k in ASPECTS}
        cov = result.get("aspect_coverage", [])
        covered = {c.get("aspect") for c in cov if isinstance(c, dict)}
        for k in ASPECTS:
            if real.get(k, 0) == 0 and k not in covered:
                problems.append(f"方面 {k} 未覆盖（既无 finding 也未在 aspect_coverage 登记）")

        # findings 枚举 + 回证
        for i, f in enumerate(findings):
            fid = f.get("finding_id") or f"F{i}"
            if f.get("aspect") not in ASPECTS:
                problems.append(f"{fid} aspect 非法: {f.get('aspect')}")
            if f.get("category") not in CATEGORIES:
                problems.append(f"{fid} category 非法: {f.get('category')}")
            if f.get("severity") not in SEVERITIES:
                problems.append(f"{fid} severity 非法: {f.get('severity')}")
            if f.get("status") == "confirmed":
                q = norm(f.get("quote"))
                if not (src and len(q) >= 6 and q in src):
                    problems.append(f"{fid} quote 不在稿件原文（逐字回证失败）")
                if not str(f.get("location") or "").strip():
                    problems.append(f"{fid} location 为空")

        # 严重度口径
        rub = result.get("severity_rubric", {})
        if not rub.get("declared_at"):
            problems.append("severity_rubric 未声明")
        for f in findings:
            if f.get("category") == "suggestion" and f.get("severity") != "minor":
                problems.append(f"{f.get('finding_id')} suggestion 应为 minor")
            if f.get("category") == "fact_error" and f.get("severity") not in ("critical", "major"):
                problems.append(f"{f.get('finding_id')} fact_error 应为 critical/major")

        # 成文报告
        rr = result.get("review_report") or ""
        if len(str(rr).strip()) < 200:
            problems.append("review_report 缺失或不足 200 字")

        # 契约字段
        for f_ in contract_fields(case):
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