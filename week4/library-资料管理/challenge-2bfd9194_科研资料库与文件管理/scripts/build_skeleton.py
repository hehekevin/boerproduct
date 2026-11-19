#!/usr/bin/env python3
"""build_skeleton.py — Step 0 自动落骨架 + 文件清单 + 内容哈希（lib-file-organizer）。

读取 case.json 提取 output_contract 字段名与文件清单（files/file_list/documents 等
常见键，或内联 content），并递归扫描输入目录补齐；对每个文件计算 sha256、识别类型、
从文件名保守抽取元数据（年份/版本线索，逐字段记录出处，不脑补）。
写出骨架 result.json（全部键一个不缺）与 /app/work/classification_rules.json
分类规则模板（任何归类之前必须事前声明，声明后禁止调整）。
三级容错：任何一级失败都降级产出可用骨架，绝不崩溃、绝不缺 result.json。
防汉字陷阱：文件名匹配一律用子串/正则，不用 str.isalpha（汉字会返回 True）。

用法：
    python3 build_skeleton.py --case /input/case.json --input-root /input \
        --out /app/output/result.json --work-dir /app/work
退出码恒为 0（失败以 WARN 报告，骨架仍写出）。
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import sys

FILE_KEYS = ("files", "file_list", "documents", "materials", "items",
             "entries", "records", "library", "artifacts")
VERSION_TOKEN_RE = re.compile(
    r"(v\d+|final|draft|copy|backup|old|new|rev\d*|定稿|终稿|初稿|草稿|修改稿?|副本|备份|旧|新)", re.IGNORECASE)
YEAR_RE = re.compile(r"(19|20)\d{2}")


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


def _sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def file_type_of(name):
    ext = os.path.splitext(name)[1].lower().lstrip(".")
    return ext if ext else "no_ext"


def extract_meta(name):
    """从文件名保守抽取元数据，逐字段记录出处；抽不到就留空，不猜。"""
    meta, source = {"year": None, "version_hint": None}, {"year": "not_extracted",
                                                          "version_hint": "not_extracted"}
    stem = os.path.splitext(name)[0]
    m = VERSION_TOKEN_RE.search(stem)
    if m:
        meta["version_hint"] = m.group(1).lower()
        source["version_hint"] = "filename"
    years = YEAR_RE.findall(stem)
    if years:
        m2 = YEAR_RE.search(stem)
        meta["year"] = int(m2.group(0))
        source["year"] = "filename"
    return meta, source


def normalize_entries(case):
    """从 case.json 常见键提取文件条目，返回 [{path, content}]。"""
    out = []
    if not isinstance(case, dict):
        return out
    for key in FILE_KEYS:
        v = case.get(key)
        if isinstance(v, list) and v:
            for i, e in enumerate(v):
                if isinstance(e, str):
                    out.append({"path": e, "content": None})
                elif isinstance(e, dict):
                    path = None
                    for k in ("path", "relative_path", "filename", "name", "file"):
                        if e.get(k):
                            path = str(e[k])
                            break
                    content = e.get("content")
                    if isinstance(content, str) and "content_b64" not in e:
                        out.append({"path": path or ("case-entry-%03d" % (i + 1)),
                                    "content": content})
                    elif path:
                        out.append({"path": path, "content": None})
            if out:
                return out
    return out


def scan_inputs(root):
    """递归扫描输入目录，返回相对路径清单（跳过 case.json 自身与符号链接）。"""
    all_files = []
    try:
        for dirpath, _dirnames, filenames in os.walk(root):
            for fn in sorted(filenames):
                rel = os.path.relpath(os.path.join(dirpath, fn), root).replace("\\", "/")
                if rel == "case.json":
                    continue
                all_files.append(rel)
    except Exception:
        pass
    return all_files


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
    case, case_id = {}, "unknown"

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
    entries = normalize_entries(case)
    disk_files = scan_inputs(args.input_root)
    seen, merged = set(), list(entries)
    for p in disk_files:
        if p not in {e["path"] for e in entries}:
            merged.append({"path": p, "content": None})
    if not merged:
        problems.append("未发现任何文件条目（case.json 无清单键且 %s 无文件）" % args.input_root)

    # 文件清单：哈希 / 类型 / 保守元数据（逐字段出处）
    files = []
    for i, e in enumerate(merged):
        fid = "F%02d" % (i + 1)
        path = e["path"]
        name = os.path.basename(path)
        sha, sha_status, size, mtime = None, "no_content", None, None
        try:
            full = os.path.join(args.input_root, path) if not os.path.isabs(path) else path
            if e["content"] is not None:
                sha = _sha256_bytes(e["content"].encode("utf-8"))
                sha_status, size = "ok_inline", len(e["content"].encode("utf-8"))
            elif os.path.isfile(full):
                sha = sha256_file(full)
                sha_status = "ok"
                st = os.stat(full)
                size = st.st_size
                mtime = datetime.datetime.fromtimestamp(
                    st.st_mtime).strftime("%Y-%m-%dT%H:%M:%S")
            elif os.path.exists(full):
                sha_status = "unreadable"
                problems.append("%s 存在但不是常规文件，未计算哈希" % path)
        except PermissionError:
            sha_status = "unreadable"
            problems.append("无权限读取: %s（登记 skipped_conflicts，不静默跳过）" % path)
        except OSError as e2:
            sha_status = "unreadable"
            problems.append("读取失败 %s: %s" % (path, e2))
        meta, msrc = extract_meta(name)
        files.append({
            "file_id": fid, "source_ref": path, "path": path, "file_type": file_type_of(name),
            "size_bytes": size, "mtime": mtime, "sha256": sha, "sha256_status": sha_status,
            "metadata": {"author": None, "year": meta["year"], "project": None,
                         "instrument": None, "version_hint": meta["version_hint"]},
            "metadata_source": {"author": "not_extracted", "year": msrc["year"],
                                "project": "not_extracted", "instrument": "not_extracted",
                                "version_hint": msrc["version_hint"]},
            "category": None, "rule_hit": None, "rename_suggestion": None, "action": None,
            "duplicate_of": None, "version_group": None, "version_rank": None,
            "skip_reason": None, "judged": False})

    # 骨架（output_contract 键 + 本题业务键，一个不缺）
    try:
        inner = {
            "material_gaps": [], "environment": {"python_version": None, "packages": "stdlib-only",
                                                 "seed": None, "hardware_note": None},
            "library_profile": {"root": args.input_root, "scope": None, "file_count": len(files),
                                "total_bytes": sum(f["size_bytes"] or 0 for f in files),
                                "type_summary": {}},
            "classification_rules": {"declared_at": None, "declared_by": None,
                                     "rules": [], "fallback_category": "unsorted",
                                     "naming_convention": {"pattern": None, "regex": None, "example": None}},
            "files": files,
            "directory_plan": {"target_root": None, "tree": None, "note": "classify_files.py 回填"},
            "duplicates": [], "versions": [], "ops": [],
            "coverage": {"total_files": len(files), "judged_files": 0, "classified": 0,
                         "duplicates_groups": 0, "version_groups": 0, "skipped": 0,
                         "ops_count": 0, "ratio": None},
            "skipped_conflicts": [], "steps": [],
            "run_status": {"state": None, "reason": None, "manual_takeover": []},
            "verdict": None, "verdict_basis": None,
            "gain_evidence": {"available": None, "runs": [], "delta_normal_minus_degraded": {},
                              "mechanism_to_metric_map": [], "boundaries": [], "failure_conditions": []},
            "efficiency": {"available": None, "wall_clock_seconds_total": None, "checker_runs": 0,
                           "files_processed": len(files), "manual_items": None, "reproduce": None},
        }
        for f in files:
            t = f["file_type"]
            inner["library_profile"]["type_summary"][t] = inner["library_profile"]["type_summary"].get(t, 0) + 1
        skeleton = {"case_id": case_id, "status": "partial", "result": inner,
                    "claims": [], "uncertainties": {"unreported": [], "unverifiable": [],
                    "conflicts": [], "human_review": [], "summary": "骨架已落盘，待逐文件归类后回填"},
                    "changelog": [{"step": "step0", "change": "build_skeleton 落骨架+清单+哈希"}]}
        for fname in fields:
            if fname not in skeleton:
                skeleton[fname] = "unknown"
    except Exception as e:
        problems.append("骨架组装异常: %s" % e)
        skeleton = {"case_id": case_id, "status": "partial", "result": {},
                    "claims": [], "uncertainties": {"summary": "骨架降级"}, "changelog": []}

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

    # 分类规则模板（事前声明：任何归类之前必须填写，之后禁止调整）
    try:
        os.makedirs(args.work_dir or ".", exist_ok=True)
        rules_path = os.path.join(args.work_dir, "classification_rules.json")
        if not os.path.exists(rules_path):
            with open(rules_path, "w", encoding="utf-8") as f:
                json.dump({"note": "任何归类之前必须声明分类规则与命名规范；声明后禁止调整，"
                                   "须与 result.classification_rules 一致。match 三类条件"
                                   "（ext/path_contains/name_contains）任一命中即归入 category，"
                                   "按 priority 升序取首个命中。中文匹配请用子串，勿用 isalpha。",
                           "declared_at": None, "declared_by": None,
                           "rules": [{"rule_id": "R-01", "priority": 1,
                                      "match": {"ext": [], "path_contains": [], "name_contains": []},
                                      "category": None, "basis": None}],
                           "fallback_category": "unsorted",
                           "naming_convention": {"pattern": None, "regex": None, "example": None}},
                          f, ensure_ascii=False, indent=1)
    except Exception as e:
        problems.append("classification_rules 模板写出失败: %s" % e)

    print("[build_skeleton] case_id=%s | contract 字段 %d 个 | 文件 %d 个 | 已哈希 %d 个"
          % (case_id, len(fields), len(files),
             sum(1 for f in files if f["sha256_status"].startswith("ok"))))
    for fi in files:
        print("  file: %s  %s  [%s]" % (fi["file_id"], fi["path"], fi["file_type"]))
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
