#!/usr/bin/env python3
"""verify_check.py — 学术文献检索校验器（结果集交付版）。
校验记录来自材料/去重/排序/成文报告/契约字段。退出码恒 0。"""
import argparse, json, os, sys, re

def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)

def norm(s):
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", (s or "").lower())

def material_text(case):
    # 收集 materials 的 snippet 文本，用于回证记录不编造
    buf = []
    for m in (case.get("materials") or []):
        if isinstance(m, dict):
            buf.append(m.get("snippet") or "")
            buf.append(m.get("title") or "")
    return norm("".join(buf))

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
        records = result.get("records", [])
        if not records:
            problems.append("records 为空（须交付可用文献结果集）")
        mat_text = material_text(case)
        for r in records:
            title = norm(r.get("title"))
            if not title:
                problems.append(f"{r.get('record_id','?')} 缺 title")
            elif len(title) >= 6 and title not in mat_text:
                problems.append(f"{r.get('record_id','?')} title 不在材料中（疑似编造）")
        dedup = result.get("dedup", [])
        rec_ids = {r.get("record_id") for r in records}
        for d in dedup:
            if d.get("merged") and d.get("merged") in rec_ids:
                problems.append(f"dedup.merged {d.get('merged')} 不应是独立记录（应合并）")
        ranked = result.get("ranked_records", [])
        if ranked and not set(ranked).issubset(rec_ids):
            problems.append("ranked_records 引用了 records 外的 id")
        sr = result.get("search_report") or ""
        if len(str(sr).strip()) < 200:
            problems.append("search_report 缺失或不足 200 字（须成文检索报告嵌入 result）")

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