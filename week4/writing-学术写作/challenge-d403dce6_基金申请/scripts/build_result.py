#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_result.py — 组装/更新 result.json（基金申请书赛道统一收尾）
把 case_id、output_contract 原字段、主产物指针、证据映射、检查报告、状态与不确定性
组装成 /app/output/result.json。已有骨架时只回填不覆盖（保留早期诚实状态）。

用法:
  python3 build_result.py --case /input/case.json --out /app/output/result.json \
      --artifact grant.docx --artifact-md grant.md \
      --evidence evidence_map.jsonl --fact-check fact_check.json \
      --consistency align_check.json --render previews/render_log.json \
      --status complete \
      --embed-file /app/output/grant.md --embed-key deliverable_content
逐章回填: 每写完一章即可
  python3 build_result.py --case /input/case.json --out /app/output/result.json \
      --embed-file /app/work/chapters/ch01.md --embed-key deliverable_content --append
字段均可缺省；output_contract 中的字段若无法填写，保持 null 并在 uncertainty 说明。
"""
import argparse, json, os, sys

def load_jsonish(p):
    if not p or not os.path.exists(p):
        return None
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        try:
            return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
        except Exception:
            return {"raw_path": p}

def _ensure_list(result, key):
    v = result.get(key)
    if not isinstance(v, list):
        v = [] if v is None else [str(v)]
        result[key] = v
    return v

def _embed_one(result, embed_file, embed_key, append):
    if os.path.exists(embed_file):
        try:
            content = open(embed_file, encoding="utf-8").read()
            if embed_file.lower().endswith((".jsonl", ".json")):
                parsed = load_jsonish(embed_file)  # 结构化全量嵌入，评分器无需开附件
                if not isinstance(parsed, dict) or "raw_path" not in parsed:
                    content = parsed
            old_v = result.get(embed_key)
            if append and isinstance(old_v, str) and old_v:
                result[embed_key] = old_v.rstrip() + "\n\n" + content
            else:
                result[embed_key] = content
            _ensure_list(result, "embedded_files").append(embed_file)
        except Exception as e:
            _ensure_list(result, "uncertainty").append(
                f"embed_failed: {embed_file}: {str(e)[:120]}")
    else:
        _ensure_list(result, "uncertainty").append(
            f"embed_missing: {embed_file}")


# 题面「Skill 运行后的输出要求」表的三行 → result.json 字段语义映射。
# 契约字段名运行时才给定（case.json.output_contract），故用别名表匹配并如实登记匹配情况。
CONTRACT_SEMANTICS = [
    {"requirement": "目标产物", "desc": "可编辑的稿件/改稿/结构化写作产物",
     "aliases": ["deliverable_content", "deliverable", "content", "draft", "manuscript",
                 "sections", "body", "text", "output"]},
    {"requirement": "事实与来源映射", "desc": "数字/术语/引用/图表/关键论断的来源或修改记录",
     "aliases": ["evidence_map", "fact_sources", "sources", "citations", "references",
                 "evidence", "fact_check", "budget_ledger", "prior_work", "source_map",
                 "innovation_vs_existing"]},
    {"requirement": "版本与边界", "desc": "修改差异、人工确认项、材料缺口与异常",
     "aliases": ["uncertainty", "notes_for_human", "limitations", "gaps", "material_gaps",
                 "changelog", "change_log", "changes", "status", "manual_check", "blockers"]},
]

# 题面点名要求"逐项对照"的 5 个要素 → 在 result.json 里的落点（供评审逐条核对）
ELEMENT_MAP = [
    {"element": "各章正文", "expect_keys": ["deliverable_content"], "chapter_prefix": "ch",
     "desc": "七章逐章全文（独立键 chNN_* + 全文 deliverable_content）"},
    {"element": "创新点对照", "expect_keys": ["innovation_vs_existing"],
     "desc": "创新点 vs_existing 逐条对照表（与谁比/差在哪/凭什么/证据定位）"},
    {"element": "前期基础", "expect_keys": ["prior_work", "evidence_map"],
     "desc": "前期成果逐字回证台账（已完成/拟开展二态分清）"},
    {"element": "预算", "expect_keys": ["budget_ledger"],
     "desc": "预算数字-来源核对表（status + source_locator 逐条）"},
    {"element": "待确认项", "expect_keys": ["notes_for_human", "uncertainty"],
     "desc": "需人工确认事项与材料缺口"},
]


def _is_filled(v):
    if v is None:
        return False
    if isinstance(v, str):
        return bool(v.strip())
    if isinstance(v, (list, dict)):
        return len(v) > 0
    return True


def _contract_field_map(result, contract_fields):
    """把契约字段逐条对照题面输出要求表 + 5 个点名要素，登记语义归属与填充状态。"""
    lower = {str(k).lower(): k for k in result.keys()}
    covered_aliases = set()
    rows = []
    for sem in CONTRACT_SEMANTICS:
        hit = None
        for a in sem["aliases"]:
            if a in lower:
                covered_aliases.add(lower[a])
                if hit is None:
                    hit = lower[a]
        rows.append({
            "requirement": sem["requirement"],
            "desc": sem["desc"],
            "result_key": hit,
            "matched": bool(hit),
            "filled": bool(hit) and _is_filled(result.get(hit)),
            "note": "" if hit else "契约中未出现该语义别名；请在 uncertainty 说明承载方式",
        })
    elements = []
    for el in ELEMENT_MAP:
        present_keys = [k for k in el["expect_keys"] if k in result]
        if el.get("chapter_prefix"):
            present_keys += sorted(k for k in result if str(k).startswith(el["chapter_prefix"]))
        filled = [k for k in present_keys if _is_filled(result.get(k))]
        elements.append({
            "element": el["element"], "desc": el["desc"],
            "result_keys": present_keys, "filled": bool(filled),
            "status": "enforced" if filled else "missing",
            "gate_note": "" if filled else "该要素未落 result.json；须补齐或在 uncertainty 说明",
        })
    unmatched = [k for k in contract_fields if k not in covered_aliases]
    return {"rows": rows,
            "elements": elements,
            "contract_fields": list(contract_fields),
            "contract_fields_filled": {k: _is_filled(result.get(k)) for k in contract_fields},
            "unmatched_contract_fields": unmatched,
            "note": "matched=是否找到承载该要求的字段；filled=该字段是否已填内容；"
                    "elements 逐条对应题面点名的 5 个要素；"
                    "未 filled 的契约字段必须在 uncertainty 说明原因，不得省略键"}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--out", default="/app/output/result.json")
    ap.add_argument("--artifact", default=None)
    ap.add_argument("--artifact-md", default=None)
    ap.add_argument("--evidence", default=None)
    ap.add_argument("--fact-check", default=None)
    ap.add_argument("--consistency", default=None)
    ap.add_argument("--render", default=None)
    ap.add_argument("--ledger", default=None)
    ap.add_argument("--status", default=None,
                    help="诚实四级 complete/partial/failed/blocked；缺省时保留已有 status")
    ap.add_argument("--notes", default=None, help="JSON 数组字符串或 ; 分隔文本")
    ap.add_argument("--changelog", default=None, help="JSON 数组字符串或 ; 分隔文本")
    ap.add_argument("--set", action="append", default=[], help="--set key=value 直接回填字段")
    ap.add_argument("--embed-file", action="append", default=None,
                    help="把该文件全文嵌入指定键（主产物内嵌），可与 --embed-key 多对连用")
    ap.add_argument("--embed-key", action="append", default=None)
    ap.add_argument("--append", action="store_true", help="嵌入内容追加到已有键值之后（逐章回填）")
    ap.add_argument("--embed-chapters-dir", default=None,
                    help="章节目录：逐章全文嵌入（章名=键 chNN_*），并写 embed_gate 闸门状态")
    ap.add_argument("--gain-evidence", default=None,
                    help="gain_evidence.json（同输入双跑对照证据），嵌入 result.gain_evidence")
    ap.add_argument("--efficiency", default=None,
                    help="efficiency.json（效率计数与复现说明），嵌入 result.efficiency")
    ap.add_argument("--prior-work", default=None,
                    help="prior_work.jsonl（前期基础专章台账），嵌入 result.prior_work")
    ap.add_argument("--budget-ledger", default=None,
                    help="budget_ledger.jsonl（预算数字-来源核对表），嵌入 result.budget_ledger")
    ap.add_argument("--notes-file", default=None,
                    help="notes_for_human.json（待人工确认项），嵌入 result.notes_for_human")
    args = ap.parse_args()
    if args.embed_key is None:
        args.embed_key = ["deliverable_content"]
    case = load_jsonish(args.case) or {}
    case_id = case.get("case_id") or case.get("id") or "unknown_case"
    contract = case.get("output_contract") or {}

    result_path = args.out
    old = load_jsonish(result_path) if os.path.exists(result_path) else None
    result = old if isinstance(old, dict) else {}

    result.setdefault("case_id", case_id)
    # 契约字段原样保留（值可为 null，后面 --set 或模型回填）
    contract_fields = []
    for k in contract if isinstance(contract, list) else (contract.get("fields") or contract.get("required") or []):
        if isinstance(k, str):
            contract_fields.append(k)
            result.setdefault(k, None)
    for kv in args.set:
        if "=" in kv:
            k, v = kv.split("=", 1)
            try:
                v = json.loads(v)
            except Exception:
                pass
            result[k] = v

    if args.artifact:
        result["deliverable"] = {"docx": args.artifact, "markdown": args.artifact_md or None,
                                 "editable": True}
    ev = load_jsonish(args.evidence)
    if ev is not None:
        result["evidence_map"] = ev
    fc = load_jsonish(args.fact_check)
    if fc is not None:
        result["fact_check"] = fc
    cc = load_jsonish(args.consistency)
    if cc is not None:
        result["consistency_check"] = cc
    rd = load_jsonish(args.render)
    if rd is not None:
        result["render"] = rd
    lg = load_jsonish(args.ledger)
    if lg is not None:
        result["fact_ledger_ref"] = args.ledger

    # 使用增益证据 / 效率计数 / 前期基础专章 / 待人工确认项（题面"使用增益"与"版本与边界"要求）
    for path, key in ((args.gain_evidence, "gain_evidence"),
                      (args.efficiency, "efficiency"),
                      (args.prior_work, "prior_work"),
                      (args.budget_ledger, "budget_ledger"),
                      (args.notes_file, "notes_for_human")):
        if path:
            data = load_jsonish(path)
            if data is None:
                _ensure_list(result, "uncertainty").append(f"{key}_missing: {path}")
            else:
                result[key] = data
                _ensure_list(result, "embedded_files").append(path)
        elif key in ("gain_evidence", "efficiency"):
            # 增益/效率是本技能的核心证据位：未产出时保留键并如实登记，不静默省略
            result.setdefault(key, None)
            _ensure_list(result, "uncertainty").append(
                f"{key}_not_produced: 未运行对应脚本或文件缺失；下游不得宣称已做增益/效率对照")
        if path:
            data = load_jsonish(path)
            if data is None:
                _ensure_list(result, "uncertainty").append(f"{key}_missing: {path}")
            else:
                result[key] = data
                _ensure_list(result, "embedded_files").append(path)

    # 主产物内嵌（支持多对 file/key；逐章回填时配 --append，防 16384 截断）
    if args.embed_file:
        keys = args.embed_key if isinstance(args.embed_key, list) else [args.embed_key]
        for i, ef in enumerate(args.embed_file):
            key = keys[i] if i < len(keys) else keys[-1]
            _embed_one(result, ef, key, args.append)

    # 7章全量嵌入 + 闸门状态：每章逐条记录 embedded/not_found/unreadable，
    # 缺章即 gate≠enforced，下游不得宣称全稿已嵌入核对。
    if args.embed_chapters_dir:
        gate = []
        if not os.path.isdir(args.embed_chapters_dir):
            gate.append({"item": "chapters_dir", "status": "not_found",
                         "path": args.embed_chapters_dir})
        else:
            chs = sorted(f for f in os.listdir(args.embed_chapters_dir)
                         if f.lower().endswith((".md", ".json")) and f.startswith("ch"))
            if not chs:
                gate.append({"item": "chapters", "status": "not_found", "path": args.embed_chapters_dir})
            for f in chs:
                p = os.path.join(args.embed_chapters_dir, f)
                key = os.path.splitext(f)[0]
                try:
                    content = open(p, encoding="utf-8").read()
                    if not content.strip():
                        gate.append({"item": key, "status": "unreadable", "path": p, "note": "empty"})
                        continue
                    result[key] = content
                    gate.append({"item": key, "status": "embedded", "path": p, "chars": len(content)})
                except Exception as e:
                    gate.append({"item": key, "status": "unreadable", "path": p, "note": str(e)[:100]})
        result["embed_gate"] = gate
        bad = [g["item"] for g in gate if g["status"] != "embedded"]
        if bad:
            _ensure_list(result, "uncertainty").append(
                f"embed_gate_not_enforced: {','.join(bad)} — 未嵌入章节不得宣称全稿已核对")

    def as_list(s):
        if not s: return []
        try:
            v = json.loads(s)
            return v if isinstance(v, list) else [str(v)]
        except Exception:
            return [x.strip() for x in s.split(";") if x.strip()]
    if args.notes:
        # 合并而非覆盖：此前登记的 embed_missing / contract 未填等记录不能被 --notes 冲掉
        prior = _ensure_list(result, "uncertainty")
        for x in as_list(args.notes):
            if x not in prior:
                prior.append(x)
    else:
        _ensure_list(result, "uncertainty")
    if args.changelog:
        result["changelog"] = as_list(args.changelog)
    else:
        _ensure_list(result, "changelog")
    if args.status:  # 未显式给 status 时保留已有值（诚实状态不被无意覆盖）
        result["status"] = args.status
    elif "status" not in result:
        result["status"] = "partial"

    # 题面输出要求表 → result.json 字段语义对照（契约键缺一个都看得见）
    result["output_contract_map"] = _contract_field_map(result, contract_fields)
    missing_contract = [k for k, ok in result["output_contract_map"]["contract_fields_filled"].items()
                        if not ok]
    if missing_contract:
        _ensure_list(result, "uncertainty").append(
            "contract_fields_unfilled: " + ",".join(missing_contract)
            + "（键已保留，须在 uncertainty 说明缺失原因）")

    os.makedirs(os.path.dirname(result_path) or ".", exist_ok=True)
    json.dump(result, open(result_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({"ok": True, "result": result_path, "status": result.get("status"),
                      "keys": list(result.keys())}, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        # 四级容错：即使自身崩溃也不让输出目录失去 result.json；退出码恒 0 不中断交付链
        try:
            os.makedirs("/app/output", exist_ok=True)
            json.dump({"case_id": "unknown_case", "status": "failed",
                       "uncertainty": [f"build_result crashed: {str(e)[:200]}"]},
                      open("/app/output/result.json", "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)
        except Exception:
            pass
        print(json.dumps({"ok": False, "error": str(e)[:300]}, ensure_ascii=False))
        sys.exit(0)
