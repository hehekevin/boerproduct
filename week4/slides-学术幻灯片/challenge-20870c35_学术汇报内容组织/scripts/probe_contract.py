#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""probe_contract.py — 第1步：契约抄录 + result.json 骨架 + 材料探查。

- 读 /input/case.json：抄 case_id 与 output_contract 全部字段名（只增不减）。
- 写 /app/output/result.json 骨架：已存在则合并更新，绝不删除已有键。
- 扫 /input 材料：逐个候选「校验式命中」（可读+可解码+非空才算命中），
  纯文本汇总到 /app/work/source_text.txt，PDF 登记为需平台 pdf-text-tool 处理。
- 从题面文本提取约束（听众/时长/页数/目标）到 /app/work/constraints.json。
退出码恒 0；失败写进返回 JSON 的 status 字段。
"""
import argparse, json, os, re, sys


def note(msg, buf):
    buf.append(msg)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--input-dir", default="/input")
    ap.add_argument("--task", default="/input/task.md")
    ap.add_argument("--out", default="/app/output/result.json")
    ap.add_argument("--work", default="/app/work")
    args = ap.parse_args()
    log = []
    status = "ok"
    contract_fields = []
    case_id = None
    case = None
    try:
        if os.path.exists(args.case):
            case = json.load(open(args.case, encoding="utf-8"))
            case_id = case.get("case_id") or case.get("id")
            oc = case.get("output_contract")
            if isinstance(oc, dict):
                contract_fields = sorted(oc.keys())
            elif isinstance(oc, list):
                contract_fields = sorted(str(x) for x in oc)
            if not contract_fields:
                note("output_contract 缺失或为空：骨架仅含 case_id+通用字段，须人工补齐", log)
        else:
            status = "case_json_missing"
            note("case.json 不存在，按契约探查失败处理", log)
    except Exception as e:
        status = "case_json_unreadable"
        note("case.json 解析失败: %s" % e, log)

    # ---- result.json 骨架（合并更新，不删键） ----
    result = {}
    if os.path.exists(args.out):
        try:
            result = json.load(open(args.out, encoding="utf-8"))
        except Exception:
            result = {}
            note("已有 result.json 不可解析，骨架重建", log)
    if case_id:
        result["case_id"] = case_id
    for f in contract_fields:
        result.setdefault(f, None)
    result.setdefault("status", "in_progress")
    result.setdefault("uncertainty", [])
    result.setdefault("changelog", [])
    result["contract_fields"] = contract_fields
    result["probe"] = {"status": status, "notes": log}
    try:
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=1)
    except Exception as e:
        status = "write_failed"
        note("result.json 写盘失败: %s" % e, log)

    # ---- 材料探查（校验式命中，禁 find|head -1） ----
    materials = []
    text_parts = []
    try:
        os.makedirs(args.work, exist_ok=True)
        idir = args.input_dir if os.path.isdir(args.input_dir) else "."
        for fn in sorted(os.listdir(idir)):
            p = os.path.join(idir, fn)
            if not os.path.isfile(p):
                continue
            low = fn.lower()
            if low.endswith(".pdf"):
                materials.append({"file": p, "kind": "pdf",
                                  "status": "needs_platform_pdf_tool",
                                  "note": "PDF 原件须用平台 pdf-text-tool/pdf-render-tool 提取，本脚本不伪造文本"})
                continue
            if low.endswith((".txt", ".md", ".json", ".csv", ".tex")):
                try:
                    raw = open(p, encoding="utf-8", errors="strict").read()
                except Exception:
                    try:
                        raw = open(p, encoding="utf-8", errors="ignore").read()
                    except Exception as e:
                        materials.append({"file": p, "kind": "text", "status": "unreadable", "error": str(e)})
                        continue
                if raw.strip():
                    materials.append({"file": p, "kind": "text", "status": "ok",
                                      "chars": len(raw)})
                    text_parts.append("===== SOURCE: %s =====\n%s" % (fn, raw))
                else:
                    materials.append({"file": p, "kind": "text", "status": "empty"})
    except Exception as e:
        note("材料扫描失败: %s" % e, log)
    src_path = os.path.join(args.work, "source_text.txt")
    try:
        with open(src_path, "w", encoding="utf-8") as f:
            f.write("\n".join(text_parts))
        src_chars = sum(len(t) for t in text_parts)
    except Exception as e:
        src_path = None
        src_chars = 0
        note("source_text.txt 写盘失败: %s" % e, log)
    mats_path = os.path.join(args.work, "materials.json")
    try:
        json.dump({"materials": materials, "notes": log}, open(mats_path, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
    except Exception:
        mats_path = None

    # ---- 约束提取（听众/时长/页数/目标） ----
    constraints = {"audience": None, "duration_min": None, "slide_limit": None,
                   "goal": None, "extraction": "keyword_best_effort"}
    blob = ""
    for c in (case or {}):
        try:
            blob += json.dumps(case.get(c), ensure_ascii=False)
        except Exception:
            pass
    if os.path.exists(args.task):
        try:
            blob += open(args.task, encoding="utf-8", errors="ignore").read()
        except Exception:
            pass
    m = re.search(r"(听众|评委|评审|组会|答辩|合作者)[：:为]?\s*([^，。；\n]{2,20})", blob)
    if m:
        constraints["audience"] = m.group(2).strip()
    m = re.search(r"(\d{1,3})\s*分钟", blob)
    if m:
        constraints["duration_min"] = int(m.group(1))
    m = re.search(r"(?:页数|不超过|至多|≤)\s*(\d{1,3})\s*页", blob)
    if m:
        constraints["slide_limit"] = int(m.group(1))
    try:
        json.dump(constraints, open(os.path.join(args.work, "constraints.json"), "w",
                   encoding="utf-8"), ensure_ascii=False, indent=1)
    except Exception:
        pass

    print(json.dumps({"status": status, "case_id": case_id,
                      "contract_fields": contract_fields,
                      "result_json": args.out, "materials": materials,
                      "source_text": src_path, "source_chars": src_chars,
                      "constraints": constraints, "notes": log}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        sys.exit(0)  # 所有失败路径（含 argparse error）一律退出码 0

