#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_result.py — result.json 生命周期管理（骨架先行 · 主产物嵌入 · 写盘自检）

设计目的: result.json 的完整性由本脚本保证，不依赖提示词纪律。
任何一次运行即使中途崩溃，/app/output/result.json 也始终是合法 JSON，
包含 case_id、output_contract 全部字段和诚实 status。

子命令:
  init      立即落骨架（Stage 0 第一步执行）: case_id + 契约字段 + status=partial
  embed     主产物分批嵌入: --key letter_markdown|revised_markdown|... --file F [--part 标签]
            可多次调用追加（按审稿人/按章节分批，规避单次响应 token 限制）
  set       回填字段: --set key=value（value 为 JSON 或原文）
  finalize  收尾: --status complete|partial|failed|blocked --notes --changelog；result.json 缺失时自愈重建
            并自动派生 triad/fact_source_map/version_boundary、嵌入 gain_evidence 与 efficiency
  verify    写盘自检: 契约字段齐全 / 嵌入非空 / 交付文件存在 / status 诚实
  （所有子命令退出码恒为 0：问题记录在报告与 verdict 里，绝不中断交付）

示例:
  python3 build_result.py init --case /input/case.json --out /app/output/result.json
  python3 build_result.py embed --key letter_markdown --file /app/work/letter_R1.md --part R1
  python3 build_result.py embed --key revised_markdown --file /app/work/revised_part1.md --part sec1-3
  python3 build_result.py finalize --out /app/output/result.json --status complete \
      --evidence /app/work/response_ledger.jsonl --audit /app/output/ledger_audit.json \
      --notes "C05 证据需作者确认" --changelog "Stage3 分批嵌入完成"
  python3 build_result.py verify --case /input/case.json --out /app/output/result.json
"""
import argparse, json, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import _runlog
except Exception:  # pragma: no cover
    _runlog = None


def _load_json(p):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _load_jsonl(p):
    rows = []
    try:
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        return []
    return rows


def _contract_fields(case):
    c = case.get("output_contract") if isinstance(case, dict) else None
    if isinstance(c, list):
        return [k for k in c if isinstance(k, str)]
    if isinstance(c, dict):
        for key in ("fields", "required", "keys"):
            v = c.get(key)
            if isinstance(v, list):
                return [k for k in v if isinstance(k, str)]
        return list(c.keys())
    return []


def _write(result, out):
    """tmp 写入后替换，避免中途崩溃留下半截 JSON。"""
    d = os.path.dirname(out) or "."
    os.makedirs(d, exist_ok=True)
    tmp = out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    os.replace(tmp, out)


def _ensure_skeleton(result, case):
    """幂等补齐: case_id + 契约字段 + 基础结构。缺什么补什么，不覆盖已有值。"""
    case_id = case.get("case_id") or case.get("id") or "unknown_case"
    result.setdefault("case_id", case_id)
    result.setdefault("embedded", {})          # 主产物嵌入区
    result.setdefault("deliverable", {})       # 可编辑文件指针
    result.setdefault("uncertainty", [])
    result.setdefault("changelog", [])
    for k in _contract_fields(case):
        result.setdefault(k, None)
    # 题面《输出要求》三行语义字段：目标产物 / 事实与来源映射 / 版本与边界
    for k in ("triad", "fact_source_map", "version_boundary", "efficiency",
              "gain_evidence"):
        result.setdefault(k, None)
    return result


def _norm(s):
    import re
    return re.sub(r"\s+", "", str(s))


def _derive_triad(ledger_rows, audit):
    """意见逐条回应 ↔ 修改点 ↔ 回复信 ↔ 修订稿 四角对应表。
    每条子要求给：意见原文、决策、回复文字、修改定位、留痕、证据状态、
    以及"回复在回复信中/新句在修订稿中/原句在基线稿中"三个机检事实。"""
    per_sid = (audit or {}).get("per_sid") or {}
    out = []
    for r in ledger_rows:
        sid = r.get("sid") or "?"
        st = per_sid.get(sid, {})
        edits = []
        for e in r.get("edits", []) or []:
            rl = e.get("revision_log") or {}
            edits.append({
                "eid": e.get("eid"), "locator": e.get("locator"),
                "original": rl.get("original"), "revised": rl.get("revised"),
                "reason": rl.get("reason"), "basis": rl.get("basis"),
                "in_revised": bool(st.get("edits_revised_ok")),
                "in_baseline": bool(st.get("edits_original_ok")),
            })
        out.append({
            "sid": sid, "cm": r.get("cm"), "comment_type": r.get("type"),
            "severity": r.get("severity"),
            "comment_quote": r.get("raw_quote") or r.get("comment"),
            "decision": r.get("decision"),
            "decision_rationale": r.get("decision_rationale"),
            "tone": r.get("tone"),
            "response_text": r.get("letter_text"),
            "in_letter": bool(st.get("letter_found")),
            "edits": edits,
            "evidence": r.get("evidence", []),
            "triad_aligned": bool(st.get("triad_ok")),
            "manual_review": st.get("manual", []),
        })
    return out


def _derive_fact_source_map(ledger_rows):
    """事实与来源映射：每个数字/术语/引用/关键论断 → 来源 + 修改记录。"""
    out = []
    for r in ledger_rows:
        sid = r.get("sid") or "?"
        for ev in r.get("evidence", []) or []:
            out.append({
                "sid": sid,
                "item": ev.get("what"),
                "kind": ev.get("kind") or "data_or_citation",
                "status": ev.get("status"),
                "source": ev.get("source"),
                "locator": ev.get("locator"),
                "basis_material": ev.get("material_id"),
                "note": ev.get("note"),
            })
        for e in r.get("edits", []) or []:
            rl = e.get("revision_log") or {}
            if rl.get("basis") or rl.get("original"):
                out.append({
                    "sid": sid,
                    "item": (rl.get("revised") or "")[:60] or e.get("eid"),
                    "kind": "claim_revision",
                    "status": "revised",
                    "source": rl.get("basis"),
                    "locator": e.get("locator"),
                    "original": rl.get("original"),
                    "revised": rl.get("revised"),
                    "reason": rl.get("reason"),
                })
    return out


def _derive_version_boundary(ledger_rows, audit, case):
    """版本与边界：基线版本标识、差异摘要、需人工确认项、材料缺口、异常。"""
    manual = []
    for r in ledger_rows:
        sid = r.get("sid") or "?"
        st = ((audit or {}).get("per_sid") or {}).get(sid, {})
        reasons = st.get("manual", []) or []
        if r.get("needs_author") or r.get("manual_confirm"):
            reasons = list(reasons) + ["needs_author"]
        if reasons:
            manual.append({"sid": sid, "reasons": sorted(set(reasons)),
                           "evidence": r.get("evidence", []),
                           "decision": r.get("decision")})
    diff = []
    for r in ledger_rows:
        for e in r.get("edits", []) or []:
            rl = e.get("revision_log") or {}
            diff.append({"sid": r.get("sid"), "eid": e.get("eid"),
                         "locator": e.get("locator"),
                         "original": rl.get("original"), "revised": rl.get("revised"),
                         "reason": rl.get("reason"), "basis": rl.get("basis")})
    gates = (audit or {}).get("gates") or {}
    gaps = [f"gate[{k}]={v.get('state')}" for k, v in gates.items()
            if v.get("state") != "enforced"]
    for u in (audit or {}).get("unbacked", []) or []:
        gaps.append(f"evidence_unbacked@{u.get('sid')}: {u.get('reason')}")
    baseline_version = (case or {}).get("baseline_version") or \
        (case or {}).get("manuscript_version") or \
        (ledger_rows[0].get("baseline_version") if ledger_rows else None) or \
        "未声明（以 materials/manuscript-baseline 实际文本为准）"
    return {
        "baseline_version": baseline_version,
        "edit_count": len(diff),
        "revision_diff": diff,
        "human_confirm_items": manual,
        "material_gaps": gaps,
        "anomalies": (audit or {}).get("problems", [])[:50],
        "gates": gates,
        "audit_verdict": (audit or {}).get("verdict"),
    }


def _collect_efficiency(runlog_path=None):
    """从运行日志自动采集效率计数（真实值，不靠自述）。"""
    events = _runlog.read_events(runlog_path) if _runlog else []
    scripts = {}
    total = 0.0
    for e in events:
        s = e.get("script", "?")
        scripts[s] = scripts.get(s, 0) + 1
        try:
            total += float(e.get("seconds") or 0)
        except Exception:
            pass
    return {
        "measured_by": "run_log.jsonl（脚本真实调用计数）",
        "script_calls": scripts,
        "script_call_total": sum(scripts.values()),
        "wall_seconds_sum": round(total, 2),
        "pipeline_steps": len(events) or None,
        "model_request_budget": {"skill_cap": 48, "platform_cap": 64},
        "note": "脚本调用数与墙钟耗时由脚本自记；模型请求数由宿主平台记录，本包不虚构。",
    }


def cmd_init(args):
    case = _load_json(args.case) or {}
    result = _ensure_skeleton({}, case)
    result["status"] = "partial"
    result["changelog"].append({"event": "skeleton", "at": time.strftime("%H:%M:%S"),
                                "contract_fields": _contract_fields(case)})
    _write(result, args.out)
    print(json.dumps({"ok": True, "cmd": "init", "out": args.out,
                      "case_id": result["case_id"],
                      "contract_fields": _contract_fields(case)}, ensure_ascii=False))
    if _runlog:
        _runlog.log_event("build_result", "init", None, ok=True)
    return 0


def cmd_embed(args):
    result = _load_json(args.out)
    if not isinstance(result, dict):
        print(json.dumps({"ok": False, "cmd": "embed",
                          "error": "result.json 不存在或损坏，先跑 init 或 finalize 自愈"},
                         ensure_ascii=False))
        return 0
    if not os.path.exists(args.file):
        print(json.dumps({"ok": False, "cmd": "embed", "error": f"file 不存在: {args.file}"},
                         ensure_ascii=False))
        return 0
    with open(args.file, encoding="utf-8") as f:
        text = f.read()
    emb = result.setdefault("embedded", {})
    if args.mode == "replace" or key_empty(emb, args.key):
        emb[args.key] = text
    else:
        sep = "\n\n<!-- embed part: %s -->\n\n" % (args.part or "part")
        emb[args.key] = str(emb.get(args.key) or "") + sep + text
    meta = emb.setdefault("_parts", {})
    meta.setdefault(args.key, []).append({"part": args.part or "part", "file": args.file,
                                          "chars": len(text), "at": time.strftime("%H:%M:%S")})
    _write(result, args.out)
    print(json.dumps({"ok": True, "cmd": "embed", "key": args.key, "part": args.part,
                      "chars": len(text), "total_chars": len(str(emb.get(args.key) or ""))},
                     ensure_ascii=False))
    if _runlog:
        _runlog.log_event("build_result", "embed", None, ok=True, key=args.key, chars=len(text))
    return 0


def key_empty(emb, key):
    return len(str(emb.get(key) or "")) < 10


def cmd_set(args):
    result = _load_json(args.out)
    if not isinstance(result, dict):
        result = {}
    case = _load_json(args.case) or {}
    _ensure_skeleton(result, case)
    for kv in args.set:
        if "=" not in kv:
            continue
        k, v = kv.split("=", 1)
        try:
            v = json.loads(v)
        except Exception:
            pass
        result[k] = v
    _write(result, args.out)
    print(json.dumps({"ok": True, "cmd": "set", "keys": list(result.keys())}, ensure_ascii=False))
    if _runlog:
        _runlog.log_event("build_result", "set", None, ok=True, n=len(args.set))
    return 0


def cmd_finalize(args):
    result = _load_json(args.out)
    if not isinstance(result, dict):
        result = {}
    case = _load_json(args.case) or {}
    _ensure_skeleton(result, case)   # 自愈: init 未跑/损坏也能补出合法骨架

    def as_list(s):
        if not s:
            return []
        try:
            v = json.loads(s)
            return v if isinstance(v, list) else [str(v)]
        except Exception:
            return [x.strip() for x in s.split(";") if x.strip()]

    ledger_rows = []
    if args.evidence:
        ev = _load_json(args.evidence)
        if ev is not None:
            result["response_ledger"] = ev
        result["ledger_ref"] = args.evidence
        ledger_rows = _load_jsonl(args.evidence)
    audit = None
    if args.audit:
        au = _load_json(args.audit)
        if au is not None:
            result["consistency_check"] = au
            audit = au
    if args.render:
        rd = _load_json(args.render)
        if rd is not None:
            result["render"] = rd
    if args.gain:
        gn = _load_json(args.gain)
        if gn is not None:
            result["gain_evidence"] = gn
    if args.artifact:
        result["deliverable"] = {"docx": args.artifact, "markdown": args.artifact_md,
                                 "editable": True}
    if args.notes:
        result["uncertainty"] = as_list(args.notes)
    if args.changelog:
        result["changelog"].extend([{"event": e, "at": time.strftime("%H:%M:%S")}
                                    for e in as_list(args.changelog)])

    # 题面《输出要求》三行语义：由台账 + 审计报告派生（脚本保证，不靠提示词纪律）
    if ledger_rows:
        result["triad"] = _derive_triad(ledger_rows, audit)
        result["fact_source_map"] = _derive_fact_source_map(ledger_rows)
        result["version_boundary"] = _derive_version_boundary(ledger_rows, audit, case)
    result["efficiency"] = _collect_efficiency(args.runlog)
    result["status"] = args.status
    result["finalized_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    _write(result, args.out)
    print(json.dumps({"ok": True, "cmd": "finalize", "out": args.out, "status": args.status,
                      "embedded_keys": sorted(result.get("embedded", {}).keys()),
                      "triad_rows": len(result.get("triad") or []),
                      "fact_source_rows": len(result.get("fact_source_map") or []),
                      "gain_evidence": bool(result.get("gain_evidence")),
                      "efficiency_calls": (result.get("efficiency") or {}).get("script_call_total"),
                      "contract_null_fields": [k for k, v in result.items() if v is None
                                               and k in _contract_fields(case)]},
                     ensure_ascii=False))
    if _runlog:
        _runlog.log_event("build_result", "finalize", None, ok=True, status=args.status)
    return 0


def cmd_verify(args):
    """写盘自检。partial 状态: 只报 warning（诚实部分交付不应被误杀）；
    complete 状态: 严格机检（字段缺失/嵌入过短/文件不存在 → fail）。
    退出码恒为 0——verdict 如实写进报告，失败绝不中断交付。"""
    result = _load_json(args.out)
    hard, warns = [], []
    if not isinstance(result, dict):
        hard.append("result.json 不存在或不是合法 JSON")
        result = {}
    case = _load_json(args.case) or {}
    fields = _contract_fields(case)
    strict = result.get("status") == "complete"
    has_uncertainty = bool(result.get("uncertainty"))

    def add(msg):
        (hard if strict and not (has_uncertainty and msg.startswith("契约字段")) else warns).append(msg)

    missing = [k for k in fields if k not in result]
    if missing:
        add(f"契约字段缺失: {missing}")
    nulls = [k for k in fields if result.get(k) is None]
    if nulls:
        add(f"契约字段为 null{'（complete 且未在 uncertainty 说明则需修复）' if strict else '（partial 可接受，如实报告）'}: {nulls}")
    emb = result.get("embedded") or {}
    if strict:
        for key in ("letter_markdown", "revised_markdown"):
            if len(str(emb.get(key) or "")) < 200:
                hard.append(f"status=complete 但嵌入 {key} 缺失或过短(<200字)")
    dl = result.get("deliverable") or {}
    for k in ("docx", "markdown"):
        p = dl.get(k)
        if p and not os.path.exists(p):
            add(f"交付文件不存在: {p}")
    if result.get("status") not in ("complete", "partial", "failed", "blocked"):
        hard.append(f"status 非法: {result.get('status')}")
    # 题面《输出要求》三行语义：目标产物/事实与来源映射/版本与边界
    for key, label in (("triad", "意见-修改-回复-修订稿三角对应表"),
                       ("fact_source_map", "事实与来源映射"),
                       ("version_boundary", "版本与边界")):
        v = result.get(key)
        if strict and not v:
            hard.append(f"status=complete 但缺《输出要求》字段 {key}（{label}）")
        elif v is None:
            warns.append(f"《输出要求》字段 {key}（{label}）为空")
    if strict and not result.get("gain_evidence"):
        hard.append("status=complete 但缺 gain_evidence（同输入增益对照未产出）")
    if strict and not result.get("efficiency"):
        hard.append("status=complete 但缺 efficiency（效率计数未采集）")
    if strict:
        # 级联机检: complete 必须内嵌审计报告且 verdict=pass（闸门未运行 ≠ 通过）
        au = result.get("consistency_check") or {}
        if not isinstance(au, dict) or not au:
            hard.append("status=complete 但未嵌入 consistency_check 审计报告（--audit 缺失）")
        elif au.get("verdict") not in ("pass", None):
            hard.append(f"status=complete 但审计 verdict={au.get('verdict')}，必须先修复")
        elif au.get("verdict") is None:
            hard.append("status=complete 但审计报告无 verdict 字段")
        elif au.get("gate_notes"):
            for gn in au.get("gate_notes"):
                warns.append(f"gate_note: {gn}")
    if not result.get("case_id") or result.get("case_id") == "unknown_case":
        hard.append("case_id 缺失或 unknown")
    report = {"verdict": "pass" if not hard else "fail", "problems": hard,
              "warnings": warns,
              "case_id": result.get("case_id"), "status": result.get("status"),
              "semantic_fields": {k: (len(result.get(k)) if isinstance(result.get(k), list)
                                      else bool(result.get(k)))
                                  for k in ("triad", "fact_source_map", "version_boundary",
                                            "efficiency", "gain_evidence")},
              "embedded_chars": {k: len(str(v)) for k, v in emb.items()
                                 if not k.startswith("_")}}
    if args.report:
        _write(report, args.report)
    print(json.dumps(report, ensure_ascii=False))
    if _runlog:
        _runlog.log_event("build_result", "verify", None,
                          ok=(not hard), verdict=report["verdict"])
    return 0  # 失败不中断交付


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="Stage 0 立即落骨架")
    p.add_argument("--case", default="/input/case.json")
    p.add_argument("--out", default="/app/output/result.json")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("embed", help="主产物分批嵌入")
    p.add_argument("--out", default="/app/output/result.json")
    p.add_argument("--key", required=True, help="letter_markdown / revised_markdown / ...")
    p.add_argument("--file", required=True)
    p.add_argument("--part", default=None, help="分批标签，如 R1 / sec1-3")
    p.add_argument("--mode", default="append", choices=["append", "replace"])
    p.set_defaults(func=cmd_embed)

    p = sub.add_parser("set", help="回填字段")
    p.add_argument("--case", default="/input/case.json")
    p.add_argument("--out", default="/app/output/result.json")
    p.add_argument("--set", action="append", default=[])
    p.set_defaults(func=cmd_set)

    p = sub.add_parser("finalize", help="收尾（失败也交付的自愈路径）")
    p.add_argument("--case", default="/input/case.json")
    p.add_argument("--out", default="/app/output/result.json")
    p.add_argument("--artifact", default=None)
    p.add_argument("--artifact-md", default=None)
    p.add_argument("--evidence", default=None, help="response_ledger.jsonl")
    p.add_argument("--audit", default=None, help="ledger_audit.json")
    p.add_argument("--render", default=None, help="render_log.json")
    p.add_argument("--gain", default=None, help="gain_evidence.json（同输入对照）")
    p.add_argument("--runlog", default=None, help="run_log.jsonl（效率计数来源）")
    p.add_argument("--status", default="partial", choices=["complete", "partial", "failed", "blocked"])
    p.add_argument("--notes", default=None, help="uncertainty: JSON 数组或 ; 分隔")
    p.add_argument("--changelog", default=None, help="追加事件: ; 分隔")
    p.set_defaults(func=cmd_finalize)

    p = sub.add_parser("verify", help="写盘自检")
    p.add_argument("--case", default="/input/case.json")
    p.add_argument("--out", default="/app/output/result.json")
    p.add_argument("--report", default=None)
    p.set_defaults(func=cmd_verify)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
