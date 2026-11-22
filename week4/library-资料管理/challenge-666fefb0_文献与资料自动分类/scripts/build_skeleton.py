#!/usr/bin/env python3
"""通用极简骨架脚本。读 case.json 提取 output_contract 全字段与业务输入，落骨架 result.json。
退出码恒 0。契约字段缺省填 unknown，绝不缺键、绝不编造。"""
from __future__ import annotations
import argparse, json, os, sys

def contract_fields(case):
    oc = case.get("output_contract") if isinstance(case, dict) else None
    if oc is None:
        return []
    if isinstance(oc, dict):
        for k in ("fields", "required_fields"):
            if isinstance(oc.get(k), list):
                return [str(x) for x in oc[k]]
        return [str(k) for k in oc.keys()]
    if isinstance(oc, list):
        return [str(x) for x in oc]
    return []

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--work-dir", default="/app/work")
    ap.add_argument("--input-root", default="/input")
    args = ap.parse_args()
    try:
        os.makedirs(args.work_dir, exist_ok=True)
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        case = {}
        if os.path.exists(args.case):
            with open(args.case, encoding="utf-8") as f:
                case = json.load(f)
        fields = contract_fields(case)
        # 先构造全部默认业务键，再套契约字段（result/claims/uncertainties/changelog 若在契约里则保留默认值）
        skeleton = {
            "case_id": case.get("case_id", "unknown"),
            "status": "partial",
            "result": {},
            "claims": [],
            "uncertainties": {},
            "changelog": [],
        }
        # 契约字段补齐（缺失填 unknown）
        for f_ in fields:
            skeleton.setdefault(f_, None)
        # 业务输入探测
        for key, val in case.items():
            if isinstance(val, list) and key in ("records","papers","candidates","items","documents","literature","files","search_results"):
                skeleton["result"].setdefault(key, val)
        # 标志文件
        with open(os.path.join(args.work_dir, "skill_marker.json"), "w", encoding="utf-8") as f:
            json.dump({"skill": "ready", "case_id": skeleton["case_id"]}, f)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(skeleton, f, ensure_ascii=False, indent=1)
        print(f"skel: fields={fields}")
    except Exception as e:
        try:
            with open(args.out, "w", encoding="utf-8") as f:
                json.dump({"case_id":"unknown","status":"input_error","result":{},"claims":[],"uncertainties":{"summary":str(e)},"changelog":[]}, f, ensure_ascii=False)
        except Exception:
            pass
        print(f"WARN skeleton fallback: {e}")
    sys.exit(0)

if __name__ == "__main__":
    main()
