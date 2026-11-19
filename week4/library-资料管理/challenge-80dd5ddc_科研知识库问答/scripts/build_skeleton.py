#!/usr/bin/env python3
"""build_skeleton.py — Step 0 自动落骨架与知识库盘点（kbqa-cite 科研知识库问答）。

读取 case.json 提取 output_contract 全部字段名、知识库条目（kb_entries/entries/
documents/notes/faqs/files 等常见键）与问题清单（questions/queries 等键），递归
扫描输入目录补齐文件形态条目；为每个可读条目建立 /app/work/entries.json 内容
台账（后续引用回证的真值来源），写入骨架 result.json（全部键，待回填）。
三级容错：任何一级失败都降级产出可用骨架，绝不崩溃、绝不缺 result.json。

用法：
    python3 build_skeleton.py --case /input/case.json --input-root /input \
        --out /app/output/result.json --work-dir /app/work
退出码恒为 0（失败以 WARN 报告，骨架仍写出）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

KB_KEYS = ("kb_entries", "entries", "knowledge_base", "documents", "notes",
           "faqs", "files", "materials", "corpus", "items")
Q_KEYS = ("questions", "queries", "qa", "question_list", "tasks")
TEXT_EXTS = (".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".yaml",
             ".yml", ".log", ".rst", ".bib", ".tex", ".py", ".r", ".ipynb")
MAX_CONTENT = 300000  # 单条目内容入台账上限（字节）


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


def _first(entry, keys, default=None):
    if not isinstance(entry, dict):
        return default
    for k in keys:
        if entry.get(k) not in (None, ""):
            return entry.get(k)
    return default


def extract_kb(case):
    """从 case.json 常见键提取知识库条目（id + 标题 + 类型 + 版本线索）。"""
    out, inline_manifest = [], []
    if not isinstance(case, dict):
        return out, inline_manifest, "case.json 非对象，知识库条目未提取"
    for key in KB_KEYS:
        v = case.get(key)
        if isinstance(v, list) and v:
            for i, e in enumerate(v):
                eid = str(_first(e, ("entry_id", "doc_id", "id", "file_id", "uid"),
                                 "E%02d" % (i + 1)))
                title = str(_first(e, ("title", "name", "filename", "path"), "") or "")[:120]
                kind = str(_first(e, ("kind", "type", "entry_type"), "unknown"))
                version = str(_first(e, ("version", "ver", "updated_at", "date"), "") or "")
                out.append({"entry_id": eid, "source_ref": "%s[%d]" % (key, i),
                            "title": title, "kind": kind, "version": version,
                            "path": str(_first(e, ("path", "file", "location"), "") or ""),
                            "readable": True, "chars": None, "missing_metadata": []})
                body = _first(e, ("content", "text", "body", "body_text"))
                if body:
                    inline_manifest.append({"entry_id": eid,
                                            "source_ref": "%s[%d]" % (key, i),
                                            "content": str(body)})
            return out, inline_manifest, ""
    return out, inline_manifest, ("case.json 未含知识库条目键（%s），请人工核对后填入 "
                                  "result.knowledge_base.entries" % ",".join(KB_KEYS))


def extract_questions(case):
    """从 case.json 常见键提取问题清单。"""
    out = []
    if not isinstance(case, dict):
        return out, "case.json 非对象，问题清单未提取"
    for key in Q_KEYS:
        v = case.get(key)
        if isinstance(v, list) and v:
            for i, e in enumerate(v):
                qid = str(_first(e, ("question_id", "qid", "id"), "Q%d" % (i + 1)))
                q = e.get("question") if isinstance(e, dict) else e
                out.append({"question_id": qid,
                            "question": str(q or "")[:300],
                            "decomposed": False,
                            "subquestions": []})
            return out, ""
    return out, "case.json 未含问题键（%s），请人工核对后填入 result.questions" % ",".join(Q_KEYS)


def scan_inputs(root, exclude_marker=("case.json", "task.md")):
    """递归扫描输入目录：返回 (文件相对路径清单, 内容台账)。"""
    all_files, manifest = [], []
    try:
        for dirpath, _dirnames, filenames in os.walk(root):
            for fn in sorted(filenames):
                rel = os.path.relpath(os.path.join(dirpath, fn), root).replace("\\", "/")
                all_files.append(rel)
    except Exception:
        pass
    for rel in all_files:
        base = os.path.basename(rel).lower()
        if any(base.endswith(m) for m in exclude_marker):
            continue
        full = os.path.join(root, rel)
        content = None
        try:
            if os.path.splitext(rel)[1].lower() in TEXT_EXTS and \
                    os.path.getsize(full) <= MAX_CONTENT:
                with open(full, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
        except Exception:
            content = None
        manifest.append({"entry_id": "F%02d" % (len(manifest) + 1),
                         "source_ref": "file:%s" % rel,
                         "content": content})
    return all_files, manifest


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
    entries, inline_manifest, kb_note = extract_kb(case)
    if kb_note:
        problems.append(kb_note)
    questions, q_note = extract_questions(case)
    if q_note:
        problems.append(q_note)
    all_files, manifest = scan_inputs(args.input_root)
    seen = {m["entry_id"] for m in manifest}
    for m in inline_manifest:
        if m["entry_id"] not in seen:
            manifest.insert(0, m)
            seen.add(m["entry_id"])

    # 二级：组装骨架（output_contract 键 + 本题业务键，一个不缺）
    try:
        inner = {
            "material_gaps": [],
            "environment": {"python_version": None, "packages": None,
                            "seed": None, "hardware_note": None},
            "knowledge_base": {"entries": entries, "total_entries": len(entries),
                               "duplicates": []},
            "questions": questions,
            "answers": [],
            "gaps": [],
            "retrieval": {"queries": None, "topk": None, "miss_registered": None,
                          "index_tool": "scripts/kb_index.py",
                          "note": "kb_index.py 运行后回填；未运行则不得宣称已检索"},
            "coverage": {"total_questions": len(questions), "decomposed": 0,
                         "total_subquestions": 0, "answered": 0, "partial": 0,
                         "miss": 0, "uncovered_subquestions": 0, "ratio": None},
            "conflicts": [],
            "steps": [],
            "run_status": {"state": None, "reason": None, "manual_takeover": []},
            "verdict": None,
            "verdict_basis": None,
        }
        skeleton = {"case_id": case_id, "status": "partial", "result": inner,
                    "claims": [],
                    "uncertainties": {"unreported": [], "unverifiable": [],
                                      "conflicts": [], "human_review": [],
                                      "summary": "骨架已落盘，待逐问逐句作答后回填"},
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

    # 条目内容台账（引用回证真值来源；verify_check 读取）
    try:
        os.makedirs(args.work_dir or ".", exist_ok=True)
        with open(os.path.join(args.work_dir, "entries.json"), "w", encoding="utf-8") as f:
            json.dump({"note": "条目内容台账：verify_check 引用回证的真值来源；"
                               "content=null 表示不可读/未入台账，引用只能降级走 claims 回证。",
                       "entries": manifest}, f, ensure_ascii=False, indent=1)
    except Exception as e:
        problems.append("entries.json 台账写出失败: %s" % e)

    print("[build_skeleton] case_id=%s | contract 字段 %d 个 | 文件 %d 个 | "
          "知识库条目 %d 条 | 问题 %d 个 | 台账 %d 条"
          % (case_id, len(fields), len(all_files), len(entries), len(questions),
             len(manifest)))
    for e in entries:
        print("  entry: %s  [%s]  %s" % (e["entry_id"], e["kind"], e["title"][:50]))
    for q in questions:
        print("  question: %s  %s" % (q["question_id"], q["question"][:60]))
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
