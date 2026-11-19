#!/usr/bin/env python3
"""build_skeleton.py — Step 0 自动落骨架与批注清单（read-note-harvest）。

读取 case.json 提取 output_contract 全部字段名与待处理批注/材料清单（annotations/
notes/highlights/materials 等常见键），扫描输入目录补齐材料清单并计算 sha256，
写入骨架 result.json（全部键，待回填）与 /app/work/type_vocab.json 批注类型口径
模板（四类型口径须在任何批注判定之前声明，之后禁止调整）。
三级容错：任何一级失败都降级产出可用骨架，绝不崩溃、绝不缺 result.json。

用法：
    python3 build_skeleton.py --case /input/case.json --input-root /input \
        --out /app/output/result.json --work-dir /app/work
退出码恒为 0（失败以 problems 报告，骨架仍写出）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

ANN_KEYS = ("annotations", "notes", "highlights", "marks", "clippings",
            "items", "records", "results")
MAT_KEYS = ("materials", "documents", "files", "sources", "papers")


def contract_fields(case):
    """从 case.json 提取 output_contract 字段名（兼容多种排布）。"""
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


def _id_of(entry, idx, keys=("ann_id", "note_id", "item_id", "id", "doc_id", "uid")):
    if isinstance(entry, dict):
        for k in keys:
            if entry.get(k):
                return str(entry[k])
    return "item-%02d" % (idx + 1)


def extract_list(case, keys, kind):
    out = []
    for key in keys:
        v = case.get(key) if isinstance(case, dict) else None
        if isinstance(v, list) and v:
            for i, e in enumerate(v):
                title = ""
                if isinstance(e, dict):
                    for tk in ("title", "name", "text", "content", "note_text"):
                        if e.get(tk):
                            title = str(e[tk])[:120]
                            break
                elif isinstance(e, str):
                    title = e[:120]
                out.append({"item_id": _id_of(e, i), "title": title,
                            "source_ref": "%s[%d]" % (key, i)})
            return out, ""
    return out, "case.json 未含%s键（%s），请人工核对后手工填入" % (kind, ",".join(keys))


def sha256_of(path):
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


def scan_inputs(root):
    """递归扫描输入目录，返回全部文件相对路径清单与逐文件哈希。"""
    all_files, hashes = [], {}
    try:
        for dirpath, _dirnames, filenames in os.walk(root):
            for fn in sorted(filenames):
                rel = os.path.relpath(os.path.join(dirpath, fn), root).replace("\\", "/")
                all_files.append(rel)
                hashes[rel] = sha256_of(os.path.join(dirpath, fn))
    except Exception:
        pass
    return all_files, hashes


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

    # 一级：读 case.json
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
    anns, ann_note = extract_list(case, ANN_KEYS, "批注")
    if ann_note:
        problems.append(ann_note)
    mats, mat_note = extract_list(case, MAT_KEYS, "材料")
    if mat_note:
        problems.append(mat_note)
    all_files, hashes = scan_inputs(args.input_root)

    # 二级：组装骨架（output_contract 键 + 本题业务键，一个不缺）
    try:
        inner = {
            "material_gaps": [],
            "environment": {"python_version": None, "packages": None,
                            "seed": None, "hardware_note": None},
            "research_question": {"question": None, "scope": None, "time_range": None},
            "source_materials": [{"material_id": m["item_id"],
                                  "source_ref": m["source_ref"],
                                  "title": m["title"],
                                  "sha256": None, "kind": None,
                                  "version_of": None,
                                  "access_note": None} for m in mats],
            "input_files": [{"path": p, "sha256": hashes.get(p)} for p in all_files],
            "annotation_vocab": {"types": [], "declared_at": None,
                                 "note": "四类型口径须在任何批注判定之前声明；"
                                         "模板见 /app/work/type_vocab.json"},
            "annotations": [{"ann_id": a["item_id"], "source_ref": a["source_ref"],
                             "locator": None, "anchor_kind": None,
                             "ann_type": None, "quote": None,
                             "quote_location": None, "note_text": None,
                             "confidence": None, "duplicate_of": None,
                             "missing_metadata": [], "needs_verify": None,
                             "judged": False} for a in anns],
            "cards": [], "themes": [], "to_verify": [],
            "coverage": {"total_annotations": len(anns), "extracted": 0, "judged": 0,
                         "by_type": {}, "cards_total": 0, "themes_total": 0,
                         "to_verify_total": 0, "ratio": None},
            "conflicts": [], "steps": [],
            "run_status": {"state": None, "reason": None, "manual_takeover": []},
            "verdict": None, "verdict_basis": None,
        }
        skeleton = {"case_id": case_id, "status": "partial", "result": inner,
                    "claims": [], "uncertainties": {"unreported": [], "unverifiable": [],
                    "conflicts": [], "human_review": [],
                    "summary": "骨架已落盘，待逐条批注判定后回填"},
                    "changelog": [{"step": "step0", "change": "build_skeleton 落骨架"}]}
        for f in fields:
            if f not in skeleton:
                skeleton[f] = "unknown"
    except Exception as e:
        problems.append("骨架组装异常: %s" % e)
        skeleton = {"case_id": case_id, "status": "partial", "result": {},
                    "claims": [], "uncertainties": {"summary": "骨架降级"},
                    "changelog": []}

    # 三级：写盘（输出目录不存在则创建；仍失败则写到备用路径）
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

    # 类型口径模板（事前声明：批注判定前必须填写，之后禁止调整）
    try:
        os.makedirs(args.work_dir or ".", exist_ok=True)
        vocab_path = os.path.join(args.work_dir, "type_vocab.json")
        if not os.path.exists(vocab_path):
            with open(vocab_path, "w", encoding="utf-8") as f:
                json.dump({"note": "批注四类型口径须在任何批注判定之前声明（type_id + "
                                   "定义 + 判定规则）；声明后禁止调整，须与 "
                                   "result.annotation_vocab 一致。",
                           "declared_at": None,
                           "types": [
                               {"type_id": "question", "label": "疑问",
                                "definition": None, "rule": None},
                               {"type_id": "supplement", "label": "补充",
                                "definition": None, "rule": None},
                               {"type_id": "challenge", "label": "质疑",
                                "definition": None, "rule": None},
                               {"type_id": "association", "label": "联想",
                                "definition": None, "rule": None}]},
                          f, ensure_ascii=False, indent=1)
    except Exception as e:
        problems.append("type_vocab 模板写出失败: %s" % e)

    print("[build_skeleton] case_id=%s | contract 字段 %d 个 | 文件 %d 个 | "
          "批注 %d 条 | 材料 %d 项" % (case_id, len(fields), len(all_files),
                                      len(anns), len(mats)))
    for a in anns:
        print("  annotation: %s  %s" % (a["item_id"], a["title"][:60]))
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
