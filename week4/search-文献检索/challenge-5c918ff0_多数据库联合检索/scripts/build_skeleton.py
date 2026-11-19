#!/usr/bin/env python3
"""build_skeleton.py — Step 0 自动落骨架与材料清单（merge-skill）。

读取 case.json 提取 output_contract 全部字段名；对 /input 全部 JSON 文件做
**标志式命中**（按内容签名识别库响应与文献记录，不依据文件名/标签假设），
预填 databases[] / raw_hits[]；写入骨架 result.json 与 dedup_policy.json
策略模板（事前声明）。三级容错，绝不崩溃、绝不缺 result.json。

用法：
    python3 build_skeleton.py --case /input/case.json --input-root /input \
        --out /app/output/result.json --work-dir /app/work
退出码恒为 0。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

try:
    from dedup_core import extract_hits_from_case, signature_db, default_policy
except Exception as e:
    print("[build_skeleton] 无法导入 dedup_core: %s" % e)
    sys.exit(0)


def contract_fields(case):
    try:
        oc = case.get("output_contract") if isinstance(case, dict) else None
        if oc is None:
            return []
        if isinstance(oc, dict):
            for key in ("fields", "required_fields", "result.json", "result"):
                v = oc.get(key)
                if isinstance(v, list):
                    return [str(x) for x in v]
            return [str(k) for k in oc.keys()]
        if isinstance(oc, list):
            return [str(x) for x in oc]
    except Exception:
        pass
    return []


def scan_inputs(root):
    """扫描输入目录，返回 (全部文件, JSON 文件列表)。"""
    all_files, json_files = [], []
    try:
        for dirpath, dirnames, filenames in os.walk(root):
            for fn in sorted(filenames):
                rel = os.path.relpath(os.path.join(dirpath, fn), root).replace("\\", "/")
                all_files.append(rel)
                if fn.lower().endswith(".json"):
                    json_files.append(os.path.join(dirpath, fn))
    except Exception:
        pass
    return all_files, json_files


def main():
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--input-root", default="/input")
        ap.add_argument("--out", default="/app/output/result.json")
        ap.add_argument("--work-dir", default="/app/work")
        args = ap.parse_args()
    except Exception as e:
        print("[build_skeleton] 参数解析失败: %s" % e)
        return 0

    problems = []
    case = {}
    case_id = "unknown"
    try:
        if os.path.exists(args.case):
            with open(args.case, "r", encoding="utf-8") as f:
                case = json.load(f)
            case_id = str(case.get("case_id") or "unknown")
        else:
            problems.append("case.json 不存在: %s（case_id 填 unknown）" % args.case)
    except Exception as e:
        problems.append("case.json 读取失败（降级继续）: %s" % e)

    fields = contract_fields(case)
    all_files, json_files = scan_inputs(args.input_root)

    # 标志式命中：扫描全部 JSON，抽文献记录 + 按内容签名猜库
    hits, db_names, sig_notes = [], set(), []
    try:
        for jf in json_files:
            try:
                with open(jf, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:
                problems.append("JSON 读取失败 %s: %s" % (jf, e))
                continue
            rel = os.path.relpath(jf, args.input_root).replace("\\", "/")
            db_guess, n_sig = signature_db(jf, json.dumps(data, ensure_ascii=False))
            found = extract_hits_from_case(data)
            for item in found[:200]:
                rec = dict(item["record"])
                rec.setdefault("db_id", db_guess or "unassigned")
                rec.setdefault("query_id", None)
                rec.setdefault("raw_ref", "%s :: %s" % (rel, item["path"]))
                hits.append(rec)
            if db_guess:
                db_names.add(db_guess)
                sig_notes.append("%s → %s（签名命中 %d 处，记录 %d 条）"
                                 % (rel, db_guess, n_sig, len(found)))
    except Exception as e:
        problems.append("材料扫描异常: %s" % e)

    # 组装骨架（output_contract 键 + 本题业务键，一个不缺）
    try:
        inner = {
            "material_gaps": [],
            "environment": {"python_version": None, "packages": None,
                            "seed": None, "hardware_note": None},
            "databases": [{"db_id": d, "db_name": d, "status": None,
                           "queries": [], "fields_profile": None, "pending": True}
                          for d in sorted(db_names)],
            "raw_hits": hits,
            "dedup_policy": dict(default_policy(), pending=True),
            "merged_records": [],
            "dedup_decisions": [],
            "conflicts": [],
            "coverage_matrix": {},
            "dedup_metrics": {},
            "attributions": [],
            "steps": [],
            "run_status": {"state": None, "reason": None, "manual_takeover": []},
            "verdict": None,
            "verdict_basis": None,
        }
        skeleton = {"case_id": case_id, "status": "partial", "result": inner,
                    "claims": [], "uncertainties": {"unreported": [], "unverifiable": [],
                    "conflicts": [], "human_review": [],
                    "summary": "骨架已落盘，待 Step 1-4 回填"},
                    "changelog": [{"step": "step0", "change": "build_skeleton 落骨架+标志式命中扫描"}]}
        for f in fields:
            if f not in skeleton:
                skeleton[f] = "unknown"
    except Exception as e:
        problems.append("骨架组装异常: %s" % e)
        skeleton = {"case_id": case_id, "status": "partial", "result": {},
                    "claims": [], "uncertainties": {"summary": "骨架降级"}, "changelog": []}

    # 三级写盘
    out_path = args.out
    try:
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    except Exception:
        pass
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(skeleton, f, ensure_ascii=False, indent=1)
    except Exception as e:
        problems.append("骨架写出失败 %s: %s" % (out_path, e))
        try:
            fallback = os.path.join(args.work_dir or ".", "result.skeleton.json")
            os.makedirs(os.path.dirname(fallback) or ".", exist_ok=True)
            with open(fallback, "w", encoding="utf-8") as f:
                json.dump(skeleton, f, ensure_ascii=False, indent=1)
            problems.append("骨架已写到备用路径: %s" % fallback)
        except Exception as e2:
            problems.append("备用写盘也失败: %s" % e2)

    # 事前去重策略模板（任何匹配前必须填 basis/declared_at）
    try:
        os.makedirs(args.work_dir or ".", exist_ok=True)
        pol_path = os.path.join(args.work_dir, "dedup_policy.json")
        if not os.path.exists(pol_path):
            with open(pol_path, "w", encoding="utf-8") as f:
                json.dump({"note": "Step 1 匹配前必须填写 basis/declared_at；"
                                   "声明后禁止事后调参。须与 result.dedup_policy 同步。",
                           **default_policy()}, f, ensure_ascii=False, indent=1)
    except Exception as e:
        problems.append("策略模板写出失败: %s" % e)

    print("[build_skeleton] case_id=%s | contract 字段 %d | 文件 %d | 命中记录 %d | 库 %d 个"
          % (case_id, len(fields), len(all_files), len(hits), len(db_names)))
    for s in sig_notes[:10]:
        print("  signature: %s" % s)
    for p in problems:
        print("  WARN: %s" % p)
    print("[build_skeleton] 骨架已写: %s" % out_path)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[build_skeleton] 未预期异常（已降级，请手工落骨架）: %s" % e)
        sys.exit(0)
