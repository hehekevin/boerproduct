#!/usr/bin/env python3
"""verify_check.py — 科研资料库文件管理校验器（极简版）。
校验元数据覆盖 / 字段出处 / 目录规则 / 契约字段。退出码恒 0。"""
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
        recs = result.get("metadata_records", [])
        ids = {r.get("file_id") for r in recs}
        for f in files:
            # file_id 可能从 path 派生
            fid = f.get("file_id") or f.get("path")
            if fid not in ids:
                problems.append(f"file {fid} 未提取元数据")
        for r in recs:
            md = r.get("metadata", {})
            if not md:
                problems.append(f"{r.get('file_id')} metadata 空")
            for k, v in md.items():
                if isinstance(v, dict) and not v.get("source"):
                    problems.append(f"{r.get('file_id')}.{k} 缺 source")
            if not r.get("target_dir"):
                problems.append(f"{r.get('file_id')} 缺 target_dir")
        dt = result.get("dir_tree", {})
        if not dt.get("declared_at"):
            problems.append("dir_tree 缺 declared_at")

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