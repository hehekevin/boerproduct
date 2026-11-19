#!/usr/bin/env python3
"""build_workorder.py — 从 case.json 构建图表解析工单并落骨架 result.json。

工单来源（按优先级）：
1. case.json.organizer_supplied_scope.required_actual_image_files + required_literal_source_table_ids
2. 兜底：case.json 顶层 artifacts/*.png 与 material 中的表 id 引用

用法：
    python3 build_workorder.py --case /input/case.json --input-root /input --out /app/work/workorder.json
工单文件包含 images/tables 清单与骨架 result.json 路径提示。骨架同时写到 --skeleton 指定位置
（默认 /app/output/result.json）。

退出码：恒为 0（禁止中断交付）。输入读不进时落 status=input_error 的骨架并在
status_reason 写明原因与人工接管位置，退出码仍为 0。
"""
from __future__ import annotations

import argparse
import json
import os
import sys


def write_skeleton_error(path, case_path, reason):
    """输入不可读时仍落一份合法骨架，保证盘上永远有交付物。"""
    result = {
        "case_id": None,
        "status": "input_error",
        "status_reason": reason,
        "result": {"objects": [],
                   "object_inventory": {"images": 0, "tables": 0,
                                        "parsed": 0, "not_applicable": 0, "unreadable": 0}},
        "claims": [],
        "uncertainties": {"unreported": [], "unverifiable": [],
                          "conflicts": [], "human_review": [],
                          "summary": reason},
        "changelog": [{"step": "stage0", "change": "build_workorder 输入不可读：%s" % reason}],
    }
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=1)
    except Exception:
        pass
    return result


class _LenientParser(argparse.ArgumentParser):
    """参数用法错误也返回 0：绝不因调用姿势问题中断交付（错误信息照实打印）。"""

    def error(self, message):
        sys.stderr.write("[%s] 参数用法错误：%s\n用法：%s\n退出码 0（交付不中断）\n"
                         % (self.prog, message, self.format_usage().strip()))
        raise SystemExit(0)


def main() -> int:
    ap = _LenientParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--input-root", default="/input")
    ap.add_argument("--out", required=True)
    ap.add_argument("--skeleton", default="/app/output/result.json")
    args = ap.parse_args()

    try:
        with open(args.case, "r", encoding="utf-8") as f:
            case = json.load(f)
        if not isinstance(case, dict):
            raise ValueError("case.json 顶层不是对象")
    except Exception as e:
        reason = ("case.json 读取失败（%s）：%s；人工接管位置：确认 /input/case.json 存在且为合法 JSON"
                  % (args.case, e))
        write_skeleton_error(args.skeleton, args.case, reason)
        print("[build_workorder] verdict=input_error——%s；已落 input_error 骨架，退出码 0" % reason)
        return 0

    scope = case.get("organizer_supplied_scope") or {}
    images, tables = [], []

    for it in scope.get("required_actual_image_files") or []:
        fp = it.get("file") if isinstance(it, dict) else str(it)
        if not fp:
            continue
        cand = [fp, os.path.join(args.input_root, fp), os.path.join(args.input_root, "case", fp)]
        exists = next((c for c in cand if os.path.exists(c)), None)
        images.append({"object_id": os.path.splitext(os.path.basename(fp))[0],
                       "file": exists or fp, "declared_path": fp,
                       "exists": exists is not None,
                       "sha256": (it or {}).get("sha256") if isinstance(it, dict) else None})

    for tid in scope.get("required_literal_source_table_ids") or []:
        tables.append({"object_id": str(tid), "source_file": None, "found": False})

    # 兜底：扫描 material.json / 输入目录
    mat_candidates = []
    for root, _dirs, files in os.walk(args.input_root):
        for fn in files:
            if fn.lower().endswith((".json", ".md", ".txt")):
                mat_candidates.append(os.path.join(root, fn))
    table_blob = ""
    for mc in mat_candidates:
        try:
            with open(mc, "r", encoding="utf-8", errors="replace") as f:
                blob = f.read()
        except Exception:
            continue
        if not table_blob:
            table_blob = blob
        for t in tables:
            if not t["found"] and t["object_id"] in blob:
                t["found"] = True
                t["source_file"] = mc
        if len(images) == 0:
            base = os.path.dirname(mc)
            for fn in sorted(os.listdir(base) if os.path.isdir(base) else []):
                if fn.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp")):
                    fp = os.path.join(base, fn)
                    images.append({"object_id": os.path.splitext(fn)[0], "file": fp,
                                   "declared_path": fn, "exists": True, "sha256": None})

    workorder = {
        "case_id": case.get("case_id"),
        "images": images,
        "tables": tables,
        "note": "images 来自工单或兜底扫描；tables 未在材料中找到时 found=false（解析时须列为缺口）",
    }
    try:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(workorder, f, ensure_ascii=False, indent=1)
    except Exception as e:
        print("[build_workorder] WARN：工单写盘失败（%s）；继续落骨架，退出码 0" % e)

    # 骨架
    objects = []
    for im in images:
        objects.append({"object_id": im["object_id"], "kind": "image", "file": im["file"],
                        "image_class": "unknown", "status": "unprocessed", "axes": [],
                        "elements": {}, "readings": [], "table": None,
                        "gaps": [], "qualitative": None, "source_locator": im["declared_path"]})
    for t in tables:
        objects.append({"object_id": t["object_id"], "kind": "table", "file": t.get("source_file"),
                        "image_class": None, "status": "unprocessed", "axes": [],
                        "elements": {}, "readings": [], "table": None,
                        "gaps": [] if t["found"] else ["declared table id not found in provided material"],
                        "qualitative": None, "source_locator": t["object_id"]})

    result = {
        "case_id": case.get("case_id"),
        "status": "partial",
        "result": {"objects": objects,
                   "object_inventory": {"images": len(images), "tables": len(tables),
                                        "parsed": 0, "not_applicable": 0, "unreadable": 0}},
        "claims": [],
        "uncertainties": {"unreported": [], "unverifiable": [], "conflicts": [],
                          "human_review": [],
                          "summary": "骨架：全部工单对象待解析（unprocessed）"},
        "changelog": [{"step": "stage0", "change": "build_workorder 落骨架，images=%d tables=%d" % (len(images), len(tables))}],
    }
    try:
        os.makedirs(os.path.dirname(args.skeleton) or ".", exist_ok=True)
        with open(args.skeleton, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=1)
    except Exception as e:
        print("[build_workorder] WARN：骨架写盘失败（%s）；退出码 0" % e)

    print("[build_workorder] images=%d tables=%d；工单→%s，骨架→%s" % (
        len(images), len(tables), args.out, args.skeleton))
    missing = [im["declared_path"] for im in images if not im["exists"]]
    if missing:
        print("[build_workorder] 警告：工单声明但未找到的图片文件：%s（解析时按缺口处理）" % missing)
    return 0


if __name__ == "__main__":
    sys.exit(main())
