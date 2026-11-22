#!/usr/bin/env python3
"""verify_check.py — 文献资料自动分类校验器（极简版）。
校验逐文件标签/归类覆盖 / 三级 category / 元数据缺失登记 / 契约字段。
退出码恒 0，判据写在 validator_verdict。"""
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
        files = case.get("files", [])
        cls = result.get("classifications", [])
        ids = {c.get("file_id") for c in cls}
        for f in files:
            if f.get("file_id") not in ids:
                problems.append(f"file {f.get('file_id')} 未分类")
        for c in cls:
            if not c.get("labels") and not c.get("boundary_note"):
                problems.append(f"{c.get('file_id')} labels 空且无 boundary_note")
            cat = c.get("category", {})
            for k in ("subject", "doc_type", "year_band"):
                if not cat.get(k):
                    problems.append(f"{c.get('file_id')} category 缺 {k}")
            if not c.get("basis"):
                problems.append(f"{c.get('file_id')} 缺 basis")

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