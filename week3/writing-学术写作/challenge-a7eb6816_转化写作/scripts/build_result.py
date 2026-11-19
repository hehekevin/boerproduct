#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_result.py — 组装/更新 result.json（学术写作赛道统一收尾）
把 case_id、output_contract 原字段、主产物全文嵌入、证据映射、机械校验闸门、状态与不确定性
组装成 /app/output/result.json。已有骨架时只回填不覆盖（保留早期诚实状态）。

83 公式要素（本脚本强制落地）:
  1) 主产物全量嵌入 result.json（--embed-md，分块每块≤1500字，回验字符数）
  2) 每个可核验点机械三元组 {item, template_value, applied, match}，逐条嵌入 gates
  3) 闸门状态显式枚举 enforced / skipped_not_provided / not_found / unreadable；
     未运行 = warn + gate_note「下游不得宣称已核对」，不许静默
  4) 逐字证据回证：evidence_map 每条 evidence 空白归一化后必须子串匹配源文，unbacked 计入 fail
  5) fail 照实记录到 result.json（gate_summary.fail / gates[].verdict），**退出码恒 0 不中断交付**；
     --strict 仅作报告标记（ci_strict=true），不改变退出码
  6) status 诚实四级：complete / partial / failed / blocked
  7) 题面输出要求表的字段语义落地：目标产物 / 事实与来源映射 / 版本与边界
     （含逐段对照表、改动清单、待确认项），并把 output_contract 字段名按语义映射自动回填
  8) gain_evidence（真实 A/B 对照）与 efficiency（效率计数）原样嵌入

用法:
  python3 build_result.py --case /input/case.json --out /app/output/result.json \
      --artifact draft.docx --artifact-md draft.md --embed-md draft.md \
      --evidence evidence_map.jsonl --source /app/work/extracted \
      --fact-check fact_check.json --triage triage.jsonl \
      --consistency check_report.json --render render_log.json \
      --align align_table.json --gain gain_evidence.json --efficiency efficiency.json \
      --status complete --notes '[待核条目...]'
字段均可缺省；缺省的闸门如实标 skipped_not_provided / not_found。
"""
import argparse, json, os, re, sys

GATE_NOTE = "下游不得宣称已核对"

def load_jsonish(p):
    """返回 (data, state)。state: enforced_ok / not_found / unreadable"""
    if not p:
        return None, "skipped_not_provided"
    if not os.path.exists(p):
        return None, "not_found"
    try:
        return json.load(open(p, encoding="utf-8")), "enforced_ok"
    except Exception:
        try:
            return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()], "enforced_ok"
        except Exception:
            try:
                open(p, encoding="utf-8").read()
                return {"raw_path": p}, "unreadable"
            except Exception:
                return None, "unreadable"

def _norm(s):
    return re.sub(r"\s+", "", str(s or ""))

def evidence_gate(evidence_rows, source_dir):
    """逐字回证：每条 evidence 空白归一化后必须在源文中子串匹配。"""
    items = []
    if source_dir and os.path.isdir(source_dir):
        import glob as _g
        corpus = _norm("".join(open(fp, encoding="utf-8").read()
                        for fp in sorted(_g.glob(os.path.join(source_dir, "*.txt")))))
    else:
        corpus = None
    unbacked = 0
    for r in (evidence_rows or []):
        ev = _norm(r.get("evidence"))
        ok = bool(ev) and corpus is not None and ev in corpus
        if not ok:
            unbacked += 1
        items.append({"item": r.get("claim_id") or r.get("id") or "?",
                      "template_value": str(r.get("evidence", ""))[:60],
                      "applied": "substring_of_source" if corpus is not None else "source_missing",
                      "match": ok})
    total = len(items)
    verdict = "pass" if (total > 0 and unbacked == 0) else ("fail" if unbacked else "warn")
    return {"gate": "evidence_verbatim", "state": "enforced", "total": total,
            "unbacked": unbacked, "verdict": verdict, "items": items[:200],
            "gate_note": "" if verdict == "pass" else "unbacked 逐条回源文核对或改写 evidence 摘录"}

def check_gate(name, data, state, extractor):
    """把检查报告转成三元组逐条 + 闸门状态。extractor(data)->(items, verdict)"""
    if data is None or state != "enforced_ok":
        note = {"skipped_not_provided": "参数未提供，未运行校验；" + GATE_NOTE,
                "not_found": "文件不存在，未运行校验；" + GATE_NOTE,
                "unreadable": "文件存在但不可解析；" + GATE_NOTE}[state]
        return {"gate": name, "state": state, "verdict": "warn", "items": [],
                "gate_note": note, "warn": True}
    items, verdict, note = extractor(data)
    return {"gate": name, "state": "enforced", "verdict": verdict,
            "items": items, "gate_note": note or ""}

def _ex_fact(data):
    items = []
    unmatched = data.get("unmatched_detail") or []
    for row in unmatched[:100]:
        items.append({"item": "line%s:%s" % (row.get("line"), row.get("value")),
                      "template_value": str(row.get("reason", ""))[:60],
                      "applied": "ledger_lookup", "match": False})
    verdict = "pass" if data.get("verdict") == "pass" else "fail"
    return items, verdict, "" if verdict == "pass" else "稿件存在台账外数值，回源文核对或标[待核]"

def _ex_audit(data):
    items, verdict = [], "pass"
    for p in data.get("problems") or []:
        t = p.get("type")
        if t in ("keep_missed", "strength_violations", "data_lost_with_drop"):
            verdict = "fail"
            for d in (p.get("detail") or p.get("samples") or [])[:50]:
                items.append({"item": "%s:%s" % (t, d.get("sid", d.get("w", ""))),
                              "template_value": _norm(d.get("probe", d.get("ctx", str(d))))[:60],
                              "applied": t, "match": False})
    if verdict == "pass":
        items = [{"item": "keep_landed", "template_value": "keep=%s" % data.get("keep"),
                  "applied": "triage_audit", "match": True}]
    return items, verdict, "" if verdict == "pass" else "keep 缺落点或强度升级，修复后重跑"

def _ex_render(data):
    ok = data.get("status") == "ok"
    return [{"item": "preview_render", "template_value": data.get("status"),
             "applied": data.get("engine") or "none", "match": ok}], \
           ("pass" if ok else "warn"), \
           ("" if ok else "渲染未成功（如实登记，不伪造）；评审可依据 md/docx 版本")

# ---------------------------------------------------------------- 契约字段语义映射
# 题面「Skill 运行后的输出要求」三块：目标产物 / 事实与来源映射 / 版本与边界。
# 平台给的 output_contract 字段名各不相同（rewrite / fact_map / open_questions ...），
# 这里按关键词把契约字段映射到本地语义槽位，保证「字段名一个不缺、内容不空壳」。
FIELD_SLOTS = [
    ("rewrite", ["rewrite", "draft", "article", "content", "text", "main", "deliverable",
                 "artifact", "output", "manuscript", "稿", "改写", "正文", "主产物"]),
    ("fact_map", ["fact", "evidence", "source", "map", "trace", "cite", "citation",
                  "事实", "来源", "溯源", "证据", "引用"]),
    ("open_questions", ["open", "question", "uncertain", "confirm", "pending", "manual",
                        "待确认", "人工", "不确定", "疑问"]),
    ("version_boundary", ["version", "boundary", "change", "diff", "revision", "log",
                          "版本", "边界", "差异", "改动", "修改"]),
    ("segment_map", ["segment", "para", "align", "compare", "逐段", "对照", "分段"]),
]

def _classify_field(name):
    """把契约字段名归类到语义槽位；无法归类返回 None（仍照抄字段名，内容留 None）。"""
    low = str(name).lower()
    for slot, keys in FIELD_SLOTS:
        for k in keys:
            if k in low:
                return slot
    return None

def derive_efficiency(result, align, gain, agent_eff):
    """效率字段：脚本可测量的部分（measured）来自实际产物；模型请求数等由 agent 如实上报（reported）。

    分开标注 measured / reported，避免把模型自述当成实测数字。
    measured 优先取 efficiency.json 里的 A/B 双臂实测（A=完整 Skill，B=机制关闭基线），
    并给出逐项差值；缺失时回落到单臂 metrics。
    """
    eff = {"source": "measured_by_scripts+agent_reported", "measured": {}, "reported": {}}
    m = (result.get("metrics") or {})
    measured = {
        "manual_edit_items": m.get("manual_edit_items"),
        "rework_rounds": m.get("rework_rounds"),
        "fact_drift_count": m.get("fact_drift_count"),
        "audience_mismatch_count": m.get("audience_mismatch_count"),
        "term_inconsistency_count": m.get("term_inconsistency_count"),
        "key_conclusion_retention_ratio": (m.get("key_conclusion_retention") or {}).get("ratio"),
        "segment_rows": len(result.get("segment_map") or []),
        "evidence_rows": len(result.get("evidence_map") or []),
        "main_artifact_chars": (result.get("main_artifact_text") or {}).get("total_chars"),
        "script_elapsed_ms": {
            "align_audit": (align or {}).get("elapsed_ms"),
            "gain_compare": (gain or {}).get("elapsed_ms"),
        },
    }
    # A/B 双臂实测（若 efficiency.json 提供了）——这才是「增益」意义上的效率计数
    ab = None
    if isinstance(agent_eff, dict):
        ab = agent_eff.get("measured")
        if isinstance(ab, dict) and ab and not any(
                isinstance(v, dict) and "fact_drift_count" in v for v in ab.values()):
            ab = None
    if isinstance(ab, dict):
        arms = ab
        measured["ab_arms"] = arms
        a = arms.get("A_full_skill") or {}
        b = arms.get("B_degraded") or {}
        measured["ab_delta_b_minus_a"] = {
            k: (None if a.get(k) is None or b.get(k) is None
                else round(b.get(k) - a.get(k), 4))
            for k in ("fact_drift_count", "audience_mismatch_count",
                      "term_inconsistency_count", "manual_edit_items", "rework_rounds")
        }
        measured["ab_delta_b_minus_a"]["key_conclusion_retention_ratio"] = (
            None if a.get("key_conclusion_retention_ratio") is None
            or b.get("key_conclusion_retention_ratio") is None
            else round(b.get("key_conclusion_retention_ratio")
                       - a.get("key_conclusion_retention_ratio"), 4))
        measured["ab_note"] = ("delta = B - A（机制关闭基线 − 完整 Skill）；"
                               "负值表示完整 Skill 臂更优。")
    eff["measured"] = measured
    if isinstance(agent_eff, dict):
        rep = agent_eff.get("reported")
        eff["reported"] = rep if isinstance(rep, dict) else {}
        if agent_eff.get("measurement_note"):
            eff["measurement_note"] = agent_eff["measurement_note"]
    eff["measurement_note"] = (
        eff.get("measurement_note")
        or ("measured 项由 scripts/align_audit.py 从实际产物统计（A/B 双臂同源文、"
            "同 rubric、同读者约束、同一统计代码实测）；reported 项由 agent 如实上报"
            "（模型请求数、墙钟耗时），未实测者留空不臆造。"))
    return eff


def build_slot_payloads(result, case, args, emb):
    """构造题面三块语义内容（目标产物/事实来源映射/版本边界）+ 逐段对照表。"""
    payload = {}
    # 目标产物：可编辑稿件 + 全文嵌入
    payload["rewrite"] = {
        "deliverable": result.get("deliverable"),
        "embedded_chars": (emb.get("total_chars") if emb.get("state") == "enforced" else None),
        "main_artifact_text": result.get("main_artifact_text"),
        "editable": True,
        "format": "docx+markdown",
    }
    # 事实与来源映射：证据逐条 + 台账校验 + 逐段对照
    payload["fact_map"] = {
        "evidence_map": result.get("evidence_map"),
        "fact_check": result.get("fact_check"),
        "segment_map": result.get("segment_map"),
        "audit_rule": "evidence 空白归一化后须在源文中子串匹配；台账外数值记为事实漂移候选",
    }
    # 版本与边界：改动清单 + 待确认项 + 不确定性 + changelog
    payload["version_boundary"] = {
        "change_log": result.get("change_log"),
        "open_questions": result.get("open_questions"),
        "uncertainty": result.get("uncertainty"),
        "changelog": result.get("changelog"),
        "status": result.get("status"),
        "boundary_note": "未确认部分以 [待人工确认]/[待核] 标注；材料缺口与运行异常分别登记",
    }
    payload["open_questions"] = result.get("open_questions") or []
    payload["segment_map"] = result.get("segment_map")
    payload["change_log"] = result.get("change_log")
    return payload

def embed_markdown(path, chunk=1500):
    """全量嵌入主产物文本，分块每块≤chunk字，回验字符数。"""
    if not path or not os.path.exists(path):
        return {"state": "not_found" if path else "skipped_not_provided",
                "gate_note": "主产物未提供嵌入；" + GATE_NOTE}
    try:
        text = open(path, encoding="utf-8").read()
    except Exception as e:
        return {"state": "unreadable", "gate_note": "主产物不可读: %s" % e}
    chunks = [text[i:i + chunk] for i in range(0, len(text), chunk)]
    embedded = sum(len(c) for c in chunks)
    ok = embedded == len(text) and len(chunks) > 0
    return {"state": "enforced", "chunks": chunks, "total_chars": len(text),
            "embedded_chars": embedded, "complete": ok,
            "gate_note": "" if ok else "嵌入字符数不一致"}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--out", default="/app/output/result.json")
    ap.add_argument("--artifact", default=None)
    ap.add_argument("--artifact-md", default=None)
    ap.add_argument("--embed-md", default=None, help="主产物 md 全文嵌入 result.json")
    ap.add_argument("--evidence", default=None, help="evidence_map.jsonl")
    ap.add_argument("--source", default=None, help="extracted 源文目录，供逐字回证")
    ap.add_argument("--fact-check", default=None)
    ap.add_argument("--triage", default=None, help="triage.jsonl（登记数量用）")
    ap.add_argument("--consistency", default=None)
    ap.add_argument("--render", default=None)
    ap.add_argument("--ledger", default=None)
    ap.add_argument("--align", default=None, help="align_audit.py 产出的 align_table.json（逐段对照+改动清单+指标）")
    ap.add_argument("--gain", default=None, help="gain_evidence.json（A/B 真实对照证据）")
    ap.add_argument("--efficiency", default=None, help="efficiency.json（效率计数）")
    ap.add_argument("--status", default="partial",
                    help="complete|partial|failed|blocked（诚实四级）")
    ap.add_argument("--notes", default=None, help="JSON 数组字符串或 ; 分隔文本")
    ap.add_argument("--changelog", default=None, help="JSON 数组字符串或 ; 分隔文本")
    ap.add_argument("--set", action="append", default=[], help="--set key=value 直接回填 output_contract 字段")
    ap.add_argument("--strict", action="store_true",
                    help="保留兼容：仅在报告中标记 ci_strict=true，**不改变退出码**（退出码恒 0）")
    args = ap.parse_args()

    case, _st = load_jsonish(args.case)
    case = case or {}
    case_id = case.get("case_id") or case.get("id") or "unknown_case"
    contract = case.get("output_contract") or {}

    result_path = args.out
    old, _st2 = load_jsonish(result_path)
    result = old if isinstance(old, dict) else {}

    result.setdefault("case_id", case_id)
    contract_fields = (contract if isinstance(contract, list)
                       else (contract.get("fields") or contract.get("required") or []))
    for k in contract_fields:
        if isinstance(k, str):
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

    # --- 主产物全量嵌入 ---
    emb = embed_markdown(args.embed_md)
    if emb.get("state") == "enforced":
        result["main_artifact_text"] = {"chunks": emb["chunks"], "total_chars": emb["total_chars"],
                                        "embedded_chars": emb["embedded_chars"],
                                        "complete": emb["complete"]}
    else:
        result.setdefault("main_artifact_text", None)

    # --- 各检查报告原样留存 ---
    for argname, key in (("fact_check", "fact_check"), ("consistency", "consistency_check"),
                         ("render", "render")):
        val, st = load_jsonish(getattr(args, argname))
        if val is not None:
            result[key] = val

    ev, ev_state = load_jsonish(args.evidence)
    if ev is not None:
        result["evidence_map"] = ev

    # --- 逐段对照表 / 改动清单 / 待确认项（align_audit.py 产出）---
    align, _astate = load_jsonish(args.align)
    if isinstance(align, dict):
        result["segment_map"] = align.get("alignment") or []
        result["change_log"] = align.get("change_log") or []
        result["open_questions"] = align.get("open_questions") or []
        result["metrics"] = align.get("metrics") or {}
        result["metrics_detail"] = align.get("metrics_detail") or {}
    else:
        for k in ("segment_map", "change_log", "open_questions"):
            result.setdefault(k, [])

    # --- 增益证据（A/B 真实对照）---
    gain, _gstate = load_jsonish(args.gain)
    if gain is not None:
        result["gain_evidence"] = gain
    else:
        result.setdefault("gain_evidence", None)

    # --- 效率计数（measured 由脚本从实际产物统计；reported 由 agent 上报）---
    # 先算闸门区，再算效率：效率的 measured 需要 gate_summary。
    eff, _estate = load_jsonish(args.efficiency)
    eff_agent = eff if isinstance(eff, dict) else None
    # --- 闸门区：显式枚举 + 三元组 ---
    gates = []
    gates.append(check_gate("fact_ledger_check", result.get("fact_check"),
                            "enforced_ok" if result.get("fact_check") is not None else
                            ("skipped_not_provided" if not args.fact_check else "not_found"), _ex_fact))
    gates.append(check_gate("triage_audit", result.get("consistency_check"),
                            "enforced_ok" if result.get("consistency_check") is not None else
                            ("skipped_not_provided" if not args.consistency else "not_found"), _ex_audit))
    gates.append(check_gate("render_preview", result.get("render"),
                            "enforced_ok" if result.get("render") is not None else
                            ("skipped_not_provided" if not args.render else "not_found"), _ex_render))
    if ev is not None:
        gates.append(evidence_gate(ev, args.source))
    else:
        gates.append({"gate": "evidence_verbatim", "state": "skipped_not_provided",
                      "verdict": "warn", "items": [],
                      "gate_note": "evidence_map 未提供；" + GATE_NOTE})
    if emb.get("state") == "enforced":
        gates.append({"gate": "artifact_embedded", "state": "enforced",
                      "verdict": "pass" if emb["complete"] else "fail",
                      "items": [{"item": "main_artifact_text", "template_value": emb["total_chars"],
                                 "applied": "chunked_embed<=1500", "match": emb["complete"]}],
                      "gate_note": ""})
    else:
        gates.append({"gate": "artifact_embedded", "state": emb["state"], "verdict": "warn",
                      "items": [], "gate_note": emb["gate_note"]})
    # 逐段对照表 / 改动清单（题面「结果可核验性」要求）
    seg = result.get("segment_map")
    chg = result.get("change_log")
    if seg:
        missing_reason = [c for c in (chg or [])
                          if c.get("tier") in (None, "drop") and not str(c.get("reason", "")).strip()]
        gates.append({
            "gate": "segment_alignment", "state": "enforced",
            "verdict": "pass" if not missing_reason else "fail",
            "items": [{"item": "segment:%s" % s.get("sid"),
                       "template_value": s.get("edit_type"),
                       "applied": "aligned_to_transfer", "match": bool(s.get("landed"))}
                      for s in seg[:80]],
            "gate_note": "" if not missing_reason else "删除类改动缺理由；补理由后重跑",
        })
    else:
        gates.append({"gate": "segment_alignment", "state": "skipped_not_provided",
                      "verdict": "warn", "items": [],
                      "gate_note": "未提供 align_table.json；" + GATE_NOTE})
    # 增益证据（A/B 真实对照）
    if gain is not None:
        comp = gain.get("metric_comparison") or []
        improved = [c for c in comp if c.get("improved") is True]
        gates.append({
            "gate": "gain_evidence", "state": "enforced",
            "verdict": "pass" if comp else "warn",
            "items": [{"item": c.get("metric"), "template_value": c.get("a"),
                       "applied": "A/B_same_rubric", "match": c.get("improved")} for c in comp[:30]],
            "gate_note": "" if comp else "gain_evidence 无对照项；" + GATE_NOTE,
        })
    else:
        gates.append({"gate": "gain_evidence", "state": "skipped_not_provided",
                      "verdict": "warn", "items": [],
                      "gate_note": "未提供 gain_evidence.json；" + GATE_NOTE})
    hard = [g for g in gates if g["verdict"] == "fail"]
    warns = [g for g in gates if g.get("warn") or g["verdict"] == "warn"]
    result["gates"] = gates
    result["gate_summary"] = {"enforced": sum(1 for g in gates if g["state"] == "enforced"),
                              "skipped_not_provided": sum(1 for g in gates if g["state"] == "skipped_not_provided"),
                              "not_found": sum(1 for g in gates if g["state"] == "not_found"),
                              "unreadable": sum(1 for g in gates if g["state"] == "unreadable"),
                              "fail": len(hard), "warn": len(warns)}
    # 闸门区就绪后再派生 efficiency（measured 含 gate_summary 与 A/B 双臂实测）
    result["efficiency"] = derive_efficiency(result, align, gain, eff_agent)
    result["efficiency"]["measured"]["gates_enforced"] = result["gate_summary"]["enforced"]
    result["efficiency"]["measured"]["gates_failed"] = result["gate_summary"]["fail"]
    result["efficiency"]["measured"]["gates_skipped_not_provided"] = \
        result["gate_summary"]["skipped_not_provided"]

    def as_list(s):
        if not s: return []
        try:
            v = json.loads(s)
            return v if isinstance(v, list) else [str(v)]
        except Exception:
            return [x.strip() for x in s.split(";") if x.strip()]
    if args.notes:
        result["uncertainty"] = as_list(args.notes)
    else:
        result.setdefault("uncertainty", [])
    if args.changelog:
        result["changelog"] = as_list(args.changelog)
    else:
        result.setdefault("changelog", [])
    result["status"] = args.status

    # --- 题面输出要求表：字段语义落地 + output_contract 字段名按语义自动回填 ---
    payloads = build_slot_payloads(result, case, args, emb)
    for slot, val in payloads.items():
        result.setdefault(slot, val)
    result["output_contract_map"] = {
        "contract_fields": [k for k in contract_fields if isinstance(k, str)],
        "mapped": {}, "unmapped": [],
        "semantic_slots": {
            "rewrite": "目标产物（可编辑稿件 + 全文嵌入）",
            "fact_map": "事实与来源映射（证据逐条 + 台账校验 + 逐段对照）",
            "version_boundary": "版本与边界（改动清单 + 待确认项 + 不确定性）",
            "segment_map": "逐段对照表",
            "open_questions": "待确认项",
        },
    }
    for k in contract_fields:
        if not isinstance(k, str):
            continue
        slot = _classify_field(k)
        if slot and payloads.get(slot) is not None and result.get(k) in (None, "", [], {}):
            result[k] = payloads[slot]
            result["output_contract_map"]["mapped"][k] = slot
        elif not slot:
            result["output_contract_map"]["unmapped"].append(k)

    # 写盘前 JSON 自检
    os.makedirs(os.path.dirname(result_path) or ".", exist_ok=True)
    payload = json.dumps(result, ensure_ascii=False, indent=1)
    json.loads(payload)
    with open(result_path, "w", encoding="utf-8") as f:
        f.write(payload)

    print(json.dumps({"ok": True, "result": result_path, "status": args.status,
                      "gate_fail": len(hard), "gate_warn": len(warns),
                      "embedded": emb.get("state") == "enforced",
                      "contract_mapped": len(result["output_contract_map"]["mapped"]),
                      "contract_unmapped": result["output_contract_map"]["unmapped"],
                      "keys": list(result.keys())}, ensure_ascii=False))
    # 失败也交付：退出码恒 0，fail 已照实记入 gates/gate_summary
    result["ci_strict"] = bool(args.strict)
    return 0

if __name__ == "__main__":
    sys.exit(main())
