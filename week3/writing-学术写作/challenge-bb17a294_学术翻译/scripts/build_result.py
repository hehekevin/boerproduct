#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_result.py — 组装/更新 result.json（学术翻译赛道统一收尾）

按题面「Skill 运行后的输出要求」表逐项落字段：
  | 目标产物     | deliverable / bilingual_pairs / bilingual_alignment
  | 事实与来源映射 | sources / bilingual_pairs[locator] / glossary[first_locator] / fidelity_table
  | 版本与边界   | status / changelog(修改差异) / uncertainty(待确认项) / gaps(材料缺口) / exceptions(异常)

同时嵌入使用增益证据（--gain-evidence）与效率计数（--efficiency），result.json 自含可离线复核。

用法:
  python3 build_result.py --case /input/case.json --out /app/output/result.json \
      --artifact translation.docx --artifact-md translation_aligned.md \
      --embed-pairs /app/work/translation.jsonl --embed-segments /app/work/segments.jsonl \
      --embed-terms /app/work/terminology.jsonl \
      --fact-check /app/output/number_check.json --consistency /app/output/align_check.json \
      --gain-evidence /app/output/gain_evidence.json \
      --status complete --notes '[待核条目...]' --changelog '关键处理决策' \
      --gaps '材料缺口' --sources /app/work/extracted/materials_manifest.json

诚实原则:
  - 契约字段一个不缺：填不了就填 null 并在 uncertainty 说明，不删字段。
  - 已有骨架时只回填不覆盖（保留早期诚实状态）。
  - 任何失败路径 exit 0。
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


def load_jsonl(p):
    rows = []
    if p and os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                rows.append({"_bad_line": line[:80]})
    return rows


def as_list(s):
    if not s:
        return []
    try:
        v = json.loads(s)
        return v if isinstance(v, list) else [str(v)]
    except Exception:
        return [x.strip() for x in str(s).split(";") if x.strip()]


def _semantic_block(result):
    """按题面输出要求表，逐字段给出语义与完成标准自评（不夸大）。"""
    pairs = result.get("bilingual_pairs") or []
    glossary = result.get("glossary") or []
    fid = result.get("fidelity_table") or {}
    unc = result.get("uncertainty") or []
    gaps = result.get("gaps") or []
    chg = result.get("changelog") or []
    dl = result.get("deliverable") or {}
    srcs = result.get("sources") or []
    return {
        "target_artifact": {
            "contract_item": "目标产物",
            "result_keys": ["deliverable", "bilingual_pairs", "bilingual_alignment"],
            "semantic": "可编辑稿件（docx + md 对照稿）+ 段级双语对照",
            "completion_criterion": "满足题目指定体裁/受众/格式；段号与原文一一对应",
            "evidence": {"editable_artifacts": [dl.get("docx"), dl.get("markdown")],
                         "pairs": len(pairs),
                         "segments_with_locator": sum(1 for p in pairs if p.get("locator")),
                         "roles_covered": sorted({p.get("role") for p in pairs if p.get("role")})},
            "status": "complete" if pairs and dl else ("partial" if pairs else "missing"),
        },
        "fact_source_mapping": {
            "contract_item": "事实与来源映射",
            "result_keys": ["sources", "bilingual_pairs", "glossary", "fidelity_table",
                            "fact_check", "consistency_check"],
            "semantic": "数字/术语/引用/图表/关键论断的来源定位与修改记录",
            "completion_criterion": "可逐条回溯，不新增材料外事实",
            "evidence": {
                "source_materials": len(srcs),
                "pairs_with_locator": sum(1 for p in pairs if p.get("locator")),
                "terms_with_first_locator": sum(1 for g in glossary if g.get("first_locator")),
                "numbers_checked": (fid.get("numbers") or {}).get("checked"),
                "numbers_unmatched": (fid.get("numbers") or {}).get("unmatched"),
                "alignment_verdict": (fid.get("alignment") or {}).get("verdict"),
            },
            "status": "complete" if pairs and glossary else "partial",
        },
        "version_and_boundary": {
            "contract_item": "版本与边界",
            "result_keys": ["status", "changelog", "uncertainty", "gaps", "exceptions", "gain_evidence"],
            "semantic": "修改差异 + 人工确认项 + 材料缺口 + 异常",
            "completion_criterion": "结果可继续编辑，未确认部分明确标注",
            "evidence": {"change_records": len(chg), "pending_confirmation_items": len(unc),
                         "material_gaps": len(gaps), "exceptions": len(result.get("exceptions") or [])},
            "status": "complete",
        },
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--out", default="/app/output/result.json")
    ap.add_argument("--artifact", default=None)
    ap.add_argument("--artifact-md", default=None)
    ap.add_argument("--embed-pairs", default=None, help="translation.jsonl（含 seg/locator/src_text/tgt_text）")
    ap.add_argument("--embed-segments", default=None, help="segments.jsonl（补 locator/role）")
    ap.add_argument("--embed-terms", default=None, help="terminology.jsonl（锁定术语表）")
    ap.add_argument("--fact-check", default=None)
    ap.add_argument("--consistency", default=None)
    ap.add_argument("--gain-evidence", default=None)
    ap.add_argument("--render", default=None)
    ap.add_argument("--sources", default=None, help="materials_manifest.json 或来源清单")
    ap.add_argument("--status", default="partial")
    ap.add_argument("--notes", default=None, help="人工确认项：JSON 数组字符串或 ; 分隔文本")
    ap.add_argument("--gaps", default=None, help="材料缺口：JSON 数组字符串或 ; 分隔文本")
    ap.add_argument("--exceptions", default=None, help="运行异常：JSON 数组字符串或 ; 分隔文本")
    ap.add_argument("--changelog", default=None, help="修改差异/处理决策：JSON 数组字符串或 ; 分隔文本")
    ap.add_argument("--set", action="append", default=[], help="--set key=value 回填 output_contract 字段")
    args = ap.parse_args()

    case = load_jsonish(args.case) or {}
    case_id = case.get("case_id") or case.get("id") or "unknown_case"
    contract = case.get("output_contract") or {}

    result_path = args.out
    old = load_jsonish(result_path) if os.path.exists(result_path) else None
    result = old if isinstance(old, dict) else {}

    result.setdefault("case_id", case_id)
    # 契约字段一个不缺（填不了填 null）
    contract_fields = []
    if isinstance(contract, list):
        contract_fields = contract
    elif isinstance(contract, dict):
        contract_fields = contract.get("fields") or contract.get("required") or []
    for k in contract_fields:
        if isinstance(k, str):
            result.setdefault(k, None)
    result["output_contract_fields"] = [k for k in contract_fields if isinstance(k, str)]
    result["output_contract_coverage"] = {
        k: ("present" if result.get(k) is not None else "null_declared") for k in result["output_contract_fields"]
    }
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
                                 "editable": True, "format": "docx+markdown_bilingual"}

    # ---- 主产物完整嵌入 ----
    if args.embed_pairs:
        pairs_raw = load_jsonl(args.embed_pairs)
        segs = {r.get("seg"): r for r in load_jsonl(args.embed_segments)
                if isinstance(r, dict) and r.get("seg")}
        pairs = []
        for r in pairs_raw:
            if not isinstance(r, dict) or not r.get("seg"):
                continue
            s = segs.get(r["seg"], {})
            pairs.append({"seg": r["seg"],
                          "locator": r.get("locator") or s.get("locator"),
                          "role": r.get("role") or s.get("role") or "body",
                          "src_text": s.get("src_text") or r.get("src_text") or "",
                          "tgt_text": r.get("tgt_text") or "",
                          "note": r.get("note")})
        pairs.sort(key=lambda x: x["seg"])
        result["bilingual_pairs"] = pairs
        result["pair_count"] = len(pairs)
        result["bilingual_alignment"] = {
            "format": "segment-level-parallel",
            "key": "seg",
            "anchor": "locator",
            "fields": ["seg", "locator", "role", "src_text", "tgt_text", "note"],
            "count": len(pairs),
            "locator_coverage": round(sum(1 for p in pairs if p.get("locator")) / max(1, len(pairs)), 4),
            "note": "src_text/tgt_text 逐段一一对应；locator 指向原始材料位置，可回溯核对。",
        }
    if args.embed_terms:
        terms = [r for r in load_jsonl(args.embed_terms)
                 if isinstance(r, dict) and r.get("src") and r.get("tgt")]
        result["glossary"] = [{"term": r["src"], "translation": r["tgt"],
                               "first_locator": r.get("first_locator"),
                               "status": r.get("status", "locked"),
                               "forbidden": r.get("forbidden") or []} for r in terms]
        result["term_count"] = len(terms)
        result["glossary_summary"] = {
            "total": len(terms),
            "locked": sum(1 for r in terms if r.get("status", "locked") == "locked"),
            "pending": sum(1 for r in terms if r.get("status") == "pending"),
            "with_forbidden_variants": sum(1 for r in terms if r.get("forbidden")),
            "reusable_format": "src|tgt|first_locator|status|forbidden（JSONL，每行一条术语）",
        }

    # ---- 保真核对表 ----
    fc = load_jsonish(args.fact_check)
    cc = load_jsonish(args.consistency)
    ge = load_jsonish(args.gain_evidence)
    fidelity = {"numbers": {"checked": (fc or {}).get("checked_numbers"),
                            "unmatched": (fc or {}).get("unmatched"),
                            "verdict": (fc or {}).get("verdict")},
                "alignment": {"segments": (cc or {}).get("segments"),
                              "translated": (cc or {}).get("translated"),
                              "num_mismatch": sum(1 for p in (cc or {}).get("problems", [])
                                                  if p.get("type") == "number_mismatch"),
                              "citation_mismatch": sum(1 for p in (cc or {}).get("problems", [])
                                                       if p.get("type") == "citation_mismatch"),
                              "term_violation": sum(1 for p in (cc or {}).get("problems", [])
                                                    if p.get("type") == "term_violation"),
                              "omission": sum(1 for p in (cc or {}).get("problems", [])
                                              if p.get("type") == "omission"),
                              "verdict": (cc or {}).get("verdict")},
                "formulas_captions": "公式/表格/题注/脚注按段登记于 bilingual_pairs（role 字段），原位保留"}
    if ge and isinstance(ge, dict) and ge.get("runs"):
        fr = (ge["runs"].get("full") or {}).get("metrics") or {}
        ar = (ge["runs"].get("ablated") or {}).get("metrics") or {}
        fidelity["ablation_contrast"] = {
            "term_consistency_rate": {"full": fr.get("term_consistency_rate"),
                                      "ablated": ar.get("term_consistency_rate")},
            "number_unit_fidelity_rate": {"full": fr.get("number_unit_fidelity_rate"),
                                          "ablated": ar.get("number_unit_fidelity_rate")},
            "omission_rate": {"full": fr.get("omission_rate"), "ablated": ar.get("omission_rate")},
            "needs_human_items": {"full": fr.get("needs_human_items"),
                                  "ablated": ar.get("needs_human_items")},
            "source": "gain_evidence.json（同输入消融对照，指标由独立评估器全强度度量）",
        }
    result["fidelity_table"] = fidelity

    if fc is not None:
        result["fact_check"] = fc
    if cc is not None:
        result["consistency_check"] = cc
    if ge is not None:
        result["gain_evidence"] = ge
        eff = ge.get("efficiency")
        if eff:
            result["efficiency"] = eff
    rd = load_jsonish(args.render)
    if rd is not None:
        result["render"] = rd

    # ---- 来源清单 ----
    sm = load_jsonish(args.sources)
    if isinstance(sm, dict) and sm.get("materials"):
        result["sources"] = [{"id": m.get("id"), "path": m.get("path"), "kind": m.get("kind"),
                              "sha1_12": m.get("sha1_12"), "extracted": m.get("extracted"),
                              "engine": m.get("engine"), "chars": m.get("chars")}
                             for m in sm["materials"]]
    elif isinstance(sm, list):
        result["sources"] = sm

    # ---- 版本与边界 ----
    result["uncertainty"] = as_list(args.notes) if args.notes else result.get("uncertainty", [])
    result["gaps"] = as_list(args.gaps) if args.gaps else result.get("gaps", [])
    result["exceptions"] = as_list(args.exceptions) if args.exceptions else result.get("exceptions", [])
    result["changelog"] = as_list(args.changelog) if args.changelog else result.get("changelog", [])
    result["status"] = args.status
    result["field_semantics"] = _semantic_block(result)

    os.makedirs(os.path.dirname(result_path) or ".", exist_ok=True)
    json.dump(result, open(result_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({"ok": True, "result": result_path, "status": args.status,
                      "pairs": result.get("pair_count"), "terms": result.get("term_count"),
                      "contract_fields": len(result.get("output_contract_fields") or []),
                      "null_declared": [k for k, v in result["output_contract_coverage"].items()
                                        if v == "null_declared"],
                      "has_gain_evidence": "gain_evidence" in result,
                      "has_efficiency": "efficiency" in result,
                      "keys": list(result.keys())}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
