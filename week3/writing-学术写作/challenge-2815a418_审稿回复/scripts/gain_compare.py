#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gain_compare.py — 同输入对照：全量机制 vs 退化模式（真实跑出来的数字）

做法（不使用预置答案，全部由本次运行的真实产物派生）：
  1. 取本次运行真实产出的 台账 / 回复信 / 修订稿 / 基线稿；
  2. 用**确定性规则**在同输入上派生若干"退化变体"，每个变体只抽掉一类机制：
     - baseline        模拟无本技能的基础产出：意见级合并回应 + 无留痕 + 无定位 + 无证据出处
     - no_decompose    只抽掉「子要求拆解」（意见级合并，留痕/定位/证据保留）
     - no_revision_log 只抽掉「修改留痕 original→revised」
     - no_locator      只抽掉「修改定位 locator」
     - no_verbatim     只抽掉「证据逐字回证出处」
  3. 对每个变体跑**同一个**机检器（ledger_audit.run_audit）与**同一套指标口径**；
     分母固定为全量模式的子要求数 / 证据条数 / 修改条数，保证可比；
  4. 输出 gain_evidence.json：逐项对照数字 + 机制→指标映射 + 效率计数 + 边界声明。

指标口径（全部写进产物，便于复核）：
  comment_response_coverage      子要求级：存在专属决策行、且其回复文字在回复信中可检索的子要求占比
  comment_response_coverage_cm   意见级：同上但按意见（cm）聚合（对退化模式公平，避免只报有利口径）
  reply_revision_consistency     每个子要求同时具备 可核验留痕(original↔revised 且可回溯/可检索)
                                  与 可检索回复文字 的占比
  evidence_verifiability         证据条目中状态合法且出处可逐字回证/明确说明的占比
  modification_locator_rate      修改条目中带可检索定位（locator）的占比
  manual_review_items            机器无法确认、必须人工核对的子要求数（越低越好）

用法:
  python3 gain_compare.py --ledger /app/work/response_ledger.jsonl \
      --letter /app/output/response_letter.md --revised /app/output/revised.md \
      --original /app/work/extracted --out /app/output/gain_evidence.json \
      [--runlog /app/work/run_log.jsonl]
退出码恒为 0：任何异常写进产物 notes，绝不中断交付。
"""
import argparse, glob, json, os, re, shutil, sys, tempfile, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import ledger_audit
except Exception:  # pragma: no cover
    ledger_audit = None
try:
    import _runlog
except Exception:  # pragma: no cover
    _runlog = None

GENERIC_REPLY = "感谢审稿人的宝贵意见，我们已在修订稿中作出相应修改，并在正文中补充了说明。"


# ---------------------------------------------------------------- 工具

def _norm(s):
    return re.sub(r"\s+", "", str(s))


def _read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def _write(p, s):
    d = os.path.dirname(p)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(s)


def _load_rows(path):
    rows = []
    for line in _read(path).splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def _dump_rows(rows, path):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _collapse(rows):
    """按意见(cm)合并子要求 —— 退化「子要求拆解」。
    合并后每条意见只剩一条回复（取该意见首个子要求的回复文字），
    但 edits 全部保留并用 _subs 记住原属子要求，便于逐子要求核对。"""
    order, groups = [], {}
    for r in rows:
        cm = r.get("cm") or r.get("sid")
        if cm not in groups:
            groups[cm] = []
            order.append(cm)
        groups[cm].append(r)
    out = []
    for cm in order:
        g = groups[cm]
        edits = []
        for r in g:
            for e in r.get("edits", []) or []:
                e2 = json.loads(json.dumps(e, ensure_ascii=False))
                e2["_subs"] = [r.get("sid")]
                edits.append(e2)
        ev = []
        for r in g:
            for x in r.get("evidence", []) or []:
                x2 = json.loads(json.dumps(x, ensure_ascii=False))
                x2["_subs"] = [r.get("sid")]
                ev.append(x2)
        first = g[0]
        out.append({
            "sid": cm, "cm": cm,
            "subs": [r.get("sid") for r in g],
            "decision": first.get("decision") or "adopted",
            "decision_rationale": first.get("decision_rationale") or "已按意见修改",
            "tone": first.get("tone") or "accept",
            "letter_text": first.get("letter_text") or GENERIC_REPLY,
            "edits": edits, "evidence": ev,
        })
    return out


def _strip(rows, what):
    out = []
    for r in rows:
        r2 = json.loads(json.dumps(r, ensure_ascii=False))
        if what == "revision_log":
            for e in r2.get("edits", []) or []:
                e.pop("revision_log", None)
                e.pop("after", None)
                e.pop("anchor_quote", None)
        elif what == "locator":
            for e in r2.get("edits", []) or []:
                e.pop("locator", None)
                e.pop("pid", None)
        elif what == "verbatim":
            for ev in r2.get("evidence", []) or []:
                ev["source"] = "见修订稿"
        out.append(r2)
    return out


def _baseline_letter(rows):
    """退化回复信：按意见合并、只留通用致谢，不含逐条回应与新文本摘录。"""
    order = []
    for r in rows:
        cm = r.get("cm") or r.get("sid")
        if cm not in order:
            order.append(cm)
    L = ["# 回复信（退化模式：意见级合并回应，无逐条回应与新文本摘录）", ""]
    for cm in order:
        L += [f"## {cm}", "意见：见审稿意见清单。", f"回应：{GENERIC_REPLY}", ""]
    return "\n".join(L)


# ---------------------------------------------------------------- 指标

def _metrics_from(mode_rows, mode_letter, mode_revised, mode_orig_norm,
                  full_rows, ev_ids, edit_ids):
    """固定分母 = 全量模式的子要求数 / 证据条数 / 修改条数。"""
    full_sids = [r.get("sid") for r in full_rows]
    full_cms = []
    for r in full_rows:
        cm = r.get("cm") or r.get("sid")
        if cm not in full_cms:
            full_cms.append(cm)
    n = len(full_sids) or 1

    by_sid = {r.get("sid"): r for r in mode_rows}
    by_cm = {}
    for r in mode_rows:
        by_cm.setdefault(r.get("cm") or r.get("sid"), r)
    cm_of = {r.get("sid"): (r.get("cm") or r.get("sid")) for r in full_rows}

    letter_norm = _norm(mode_letter)
    revised_norm = _norm(mode_revised)

    def hits(text):
        t = _norm(text or "")
        return bool(t) and t[:30] in letter_norm

    def row_for(sid):
        """该子要求在本模式下的可达行：优先专属行，否则按意见合并行。"""
        r = by_sid.get(sid)
        if r is not None:
            return r, True          # 专属行（拆解未退化）
        cm = cm_of.get(sid)
        r = by_cm.get(cm)
        if r is not None and sid in (r.get("subs") or []):
            return r, False         # 合并行（拆解退化，子要求无专属行）
        return None, False

    def edits_of(row, sid):
        out = []
        for e in row.get("edits", []) or []:
            subs = e.get("_subs")
            if subs is None or sid in subs:
                out.append(e)
        return out

    def evidence_of(row, sid):
        out = []
        for ev in row.get("evidence", []) or []:
            subs = ev.get("_subs")
            if subs is None or sid in subs:
                out.append(ev)
        return out

    covered = covered_cm = consistent = manual = 0
    covered_cm_set = set()
    for r in full_rows:
        sid = r.get("sid")
        cm = cm_of.get(sid)
        row, dedicated = row_for(sid)

        # 子要求级覆盖：必须存在专属行（decision 合法 + 回复文字可检索）
        ok_cov = False
        if dedicated and row is not None and row.get("decision") in ledger_audit.VALID_DECISION:
            ok_cov = hits(row.get("letter_text"))
        if ok_cov:
            covered += 1

        # 意见级覆盖（对退化模式公平的补充口径）
        rcm = by_cm.get(cm)
        if rcm is not None and rcm.get("decision") in ledger_audit.VALID_DECISION \
                and hits(rcm.get("letter_text")):
            covered_cm_set.add(cm)
        covered_cm = len(covered_cm_set)

        # 一致性：可达行中存在留痕(original↔revised)、原句可回溯、新句可检索，且回复文字可检索
        ok_cons = False
        if row is not None:
            for e in edits_of(row, sid):
                rl = e.get("revision_log") or {}
                before = _norm(rl.get("original") or "")
                after = _norm(rl.get("revised") or "")
                if not before or not after:
                    continue
                back_ok = (not mode_orig_norm) or (before[:30] in mode_orig_norm)
                if back_ok and after[:30] in revised_norm and hits(row.get("letter_text")):
                    ok_cons = True
                    break
        if ok_cons:
            consistent += 1
        else:
            manual += 1

    # 证据可核验率（分母固定为全量模式证据条数）
    ev_total = len(ev_ids) or 1
    ev_ok = 0
    for sid, what in ev_ids:
        row, _ = row_for(sid)
        if row is None:
            continue
        for ev in evidence_of(row, sid):
            if (ev.get("what") or ev.get("status") or "") != what:
                continue
            src = str(ev.get("source") or "")
            st = ev.get("status")
            if st == "done":
                ok = len(src) >= ledger_audit.QUOTE_MIN and bool(mode_orig_norm) \
                    and _norm(src)[:30] in mode_orig_norm
            elif st in ("replaced_by_alternative", "not_possible"):
                ok = len(src) >= 4
            else:
                ok = False
            if ok:
                ev_ok += 1
            break

    # 修改定位率（分母固定为全量模式修改条数）
    edit_total = len(edit_ids) or 1
    edit_loc = 0
    for sid, eid in edit_ids:
        row, _ = row_for(sid)
        if row is None:
            continue
        for e in edits_of(row, sid):
            if e.get("eid") != eid:
                continue
            if str(e.get("locator") or "").strip():
                edit_loc += 1
            break

    return {
        "comment_response_coverage": round(100.0 * covered / n, 2),
        "comment_response_coverage_cm": round(100.0 * covered_cm / (len(full_cms) or 1), 2),
        "reply_revision_consistency": round(100.0 * consistent / n, 2),
        "evidence_verifiability": round(100.0 * ev_ok / ev_total, 2),
        "modification_locator_rate": round(100.0 * edit_loc / edit_total, 2),
        "manual_review_items": manual,
        "denominators": {"sub_requirements": n, "comments": len(full_cms),
                         "evidence_items": len(ev_ids), "modifications": len(edit_ids)},
        "counts": {"covered_subs": covered, "covered_comments": covered_cm,
                   "consistent_subs": consistent, "evidence_verifiable": ev_ok,
                   "locator_present": edit_loc},
    }


def _evidence_ids(full_rows):
    ids = []
    for r in full_rows:
        for ev in r.get("evidence", []) or []:
            ids.append((r.get("sid"), ev.get("what") or ev.get("status") or ""))
    return ids


def _edit_ids(full_rows):
    ids = []
    for r in full_rows:
        for e in r.get("edits", []) or []:
            ids.append((r.get("sid"), e.get("eid") or ("_" + str(id(e)))))
    return ids


# ---------------------------------------------------------------- 主流程

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--letter", required=True)
    ap.add_argument("--revised", required=True)
    ap.add_argument("--original", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--runlog", default=None)
    ap.add_argument("--steps-full", type=int, default=None,
                    help="全量模式流程步数（未给则从 runlog 推断）")
    args = ap.parse_args()

    t0 = time.time()
    notes = []
    if ledger_audit is None:
        out = {"ok": False, "error": "ledger_audit 不可用", "notes": ["机检器导入失败"]}
        print(json.dumps(out, ensure_ascii=False))
        if args.out:
            _write(args.out, json.dumps(out, ensure_ascii=False, indent=1))
        return 0

    try:
        full_rows = _load_rows(args.ledger)
        letter_full = _read(args.letter)
        revised_full = _read(args.revised)
        orig_norm = ""
        if args.original and os.path.exists(args.original):
            if os.path.isdir(args.original):
                orig_norm = _norm("\n".join(
                    _read(fp) for fp in sorted(glob.glob(os.path.join(args.original, "*.txt")))))
            else:
                orig_norm = _norm(_read(args.original))
    except Exception as e:
        out = {"ok": False, "error": str(e)[:300], "notes": ["读取真实产物失败"]}
        print(json.dumps(out, ensure_ascii=False))
        if args.out:
            _write(args.out, json.dumps(out, ensure_ascii=False, indent=1))
        return 0

    ev_ids = _evidence_ids(full_rows)
    edit_ids = _edit_ids(full_rows)

    b_rows = _collapse(full_rows)
    b_rows = _strip(b_rows, "revision_log")
    b_rows = _strip(b_rows, "locator")
    b_rows = _strip(b_rows, "verbatim")
    for r in b_rows:
        r["letter_text"] = GENERIC_REPLY

    variants = {
        "full": {
            "label": "全量模式（本次运行真实产物）",
            "rows": full_rows, "letter": letter_full, "revised": revised_full,
            "orig": orig_norm,
            "description": "子要求拆解 + 修改留痕 + 定位 + 证据出处 + 机检全部开启",
        },
        "baseline": {
            "label": "退化模式（意见级合并回应 / 无留痕 / 无定位 / 无证据出处）",
            "rows": b_rows, "letter": _baseline_letter(full_rows),
            "revised": revised_full, "orig": orig_norm,
            "description": "同输入下只保留意见级通用致谢，删除修改留痕/定位/证据出处",
        },
        "no_decompose": {
            "label": "消融：抽掉子要求拆解（意见级合并，留痕/定位/证据保留）",
            "rows": _collapse(full_rows), "letter": letter_full,
            "revised": revised_full, "orig": orig_norm,
            "description": "一条意见只回一条，子要求不再各有专属决策行",
        },
        "no_revision_log": {
            "label": "消融：抽掉修改留痕 revision_log(original→revised)",
            "rows": _strip(full_rows, "revision_log"), "letter": letter_full,
            "revised": revised_full, "orig": orig_norm,
            "description": "编辑条目不留 original→revised 对",
        },
        "no_locator": {
            "label": "消融：抽掉修改定位 locator",
            "rows": _strip(full_rows, "locator"), "letter": letter_full,
            "revised": revised_full, "orig": orig_norm,
            "description": "编辑条目不带 locator",
        },
        "no_verbatim": {
            "label": "消融：抽掉证据逐字回证出处",
            "rows": _strip(full_rows, "verbatim"), "letter": letter_full,
            "revised": revised_full, "orig": orig_norm,
            "description": "证据 source 退化为指针",
        },
    }

    results = {}
    tmp = tempfile.mkdtemp(prefix="gain_")
    try:
        for name, v in variants.items():
            d = os.path.join(tmp, name)
            os.makedirs(d, exist_ok=True)
            lp = os.path.join(d, "letter.md")
            rp = os.path.join(d, "revised.md")
            gp = os.path.join(d, "ledger.jsonl")
            _write(lp, v["letter"])
            _write(rp, v["revised"])
            _dump_rows(v["rows"], gp)
            op = os.path.join(d, "original.txt")
            if v["orig"]:
                _write(op, v["orig"])
            rep = ledger_audit.run_audit(gp, lp, rp, op if v["orig"] else None, [])
            m = _metrics_from(v["rows"], v["letter"], v["revised"], v["orig"],
                               full_rows, ev_ids, edit_ids)
            m["audit_verdict"] = rep["verdict"]
            m["audit_problem_types"] = sorted({p["type"] for p in rep["problems"]})
            m["audit_problem_count"] = len(rep["problems"])
            m["audit_checks"] = rep["checks_total"]
            m["audit_matched"] = rep["checks_matched"]
            m["unbacked"] = len(rep["unbacked"])
            results[name] = m
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # ---- 效率计数（runlog 实测 + 台账实数）
    run_events = []
    if _runlog and args.runlog:
        run_events = _runlog.read_events(args.runlog)
    script_calls = {}
    total_seconds = 0.0
    for e in run_events:
        s = e.get("script", "?")
        script_calls[s] = script_calls.get(s, 0) + 1
        try:
            total_seconds += float(e.get("seconds") or 0)
        except Exception:
            pass
    steps_full = args.steps_full
    if steps_full is None:
        steps_full = len(run_events) or None

    full_m = results["full"]
    base_m = results["baseline"]

    def d(primary, mode):
        return round(full_m[primary] - results[mode][primary], 2)

    mechanism_map = [
        {"mechanism": "子要求拆解（一条意见拆多问，广度优先）",
         "ablation": "no_decompose", "baseline": "baseline",
         "primary_metric": "comment_response_coverage",
         "full": full_m["comment_response_coverage"],
         "ablated": results["no_decompose"]["comment_response_coverage"],
         "baseline_value": base_m["comment_response_coverage"],
         "delta_full_minus_ablated": d("comment_response_coverage", "no_decompose"),
         "delta_full_minus_baseline": d("comment_response_coverage", "baseline"),
         "why": "拆解后每个子要求各有专属决策行与可检索回复文字；不拆解只剩意见级一条通用致谢"},
        {"mechanism": "修改留痕 revision_log(original→revised)",
         "ablation": "no_revision_log", "baseline": "baseline",
         "primary_metric": "reply_revision_consistency",
         "full": full_m["reply_revision_consistency"],
         "ablated": results["no_revision_log"]["reply_revision_consistency"],
         "baseline_value": base_m["reply_revision_consistency"],
         "delta_full_minus_ablated": d("reply_revision_consistency", "no_revision_log"),
         "delta_full_minus_baseline": d("reply_revision_consistency", "baseline"),
         "why": "留痕把「声称已改」绑定到可回溯原句与可检索新句，缺它则一致性不可核验"},
        {"mechanism": "修改定位（locator/锚点）",
         "ablation": "no_locator", "baseline": "baseline",
         "primary_metric": "modification_locator_rate",
         "full": full_m["modification_locator_rate"],
         "ablated": results["no_locator"]["modification_locator_rate"],
         "baseline_value": base_m["modification_locator_rate"],
         "delta_full_minus_ablated": d("modification_locator_rate", "no_locator"),
         "delta_full_minus_baseline": d("modification_locator_rate", "baseline"),
         "why": "定位串让修改在指定版本稿件中可被独立找到；缺它只能人工全文找"},
        {"mechanism": "证据逐字回证（source 引文可在基线稿检索）",
         "ablation": "no_verbatim", "baseline": "baseline",
         "primary_metric": "evidence_verifiability",
         "full": full_m["evidence_verifiability"],
         "ablated": results["no_verbatim"]["evidence_verifiability"],
         "baseline_value": base_m["evidence_verifiability"],
         "delta_full_minus_ablated": d("evidence_verifiability", "no_verbatim"),
         "delta_full_minus_baseline": d("evidence_verifiability", "baseline"),
         "why": "引文级出处可被机器逐字回证；退化为指针后证据不可核验"},
        {"mechanism": "机检前置（把核验交给脚本而非人工比对）",
         "ablation": "baseline", "baseline": "baseline",
         "primary_metric": "manual_review_items",
         "full": full_m["manual_review_items"],
         "ablated": base_m["manual_review_items"],
         "baseline_value": base_m["manual_review_items"],
         "delta_full_minus_ablated": round(full_m["manual_review_items"]
                                           - base_m["manual_review_items"], 2),
         "delta_full_minus_baseline": round(full_m["manual_review_items"]
                                            - base_m["manual_review_items"], 2),
         "why": "留痕+定位+出处齐全时子要求可被机器独立确认，人工只需核对少量条目"},
    ]

    gain = {
        "schema_version": "gain_evidence/1",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "comparison_design": {
            "same_input": True,
            "input_artifacts": {"ledger": args.ledger, "letter": args.letter,
                                "revised": args.revised, "original": args.original},
            "method": "在同一次运行的真实产物上按确定性规则派生退化变体，"
                      "对每个变体跑同一个机检器与同一套指标口径；"
                      "分母固定为全量模式计数（子要求数/证据条数/修改条数）",
            "fixed_denominators": full_m["denominators"],
            "variant_definitions": {k: v["description"] for k, v in variants.items()},
            "not_a_claim": "退化变体由规则派生，用于隔离本技能各机制的贡献；"
                           "不等同于平台基础 Agent 的实跑产物，平台白板对照由平台提供",
        },
        "metrics": results,
        "mechanism_to_metric": mechanism_map,
        "efficiency": {
            "measured_by": "run_log.jsonl（本轮脚本真实调用计数）" if run_events
                           else "run_log 缺失，仅给台账实数",
            "script_calls": script_calls,
            "script_call_total": sum(script_calls.values()),
            "wall_seconds_sum": round(total_seconds, 2),
            "pipeline_steps_full": steps_full,
            "pipeline_steps_baseline": 2,
            "steps_note": "全量模式步数=本轮实际脚本调用数（可核）；"
                          "退化模式=生成+写盘两步（按定义）",
            "manual_review_items_full": full_m["manual_review_items"],
            "manual_review_items_baseline": base_m["manual_review_items"],
            "manual_review_saved": base_m["manual_review_items"] - full_m["manual_review_items"],
            "manual_review_note": "人工核对条目数越低说明交付越可独立复核；"
                                  "全量模式把大部分核验前移给脚本",
            "reproducible": "同输入同脚本可复跑本产物，数字可逐项复核",
        },
        "boundaries": [
            "对照数字来自本次运行的真实产物与真实派生变体，不是预置答案；"
            "平台与基础 Agent 的对照由平台提供。",
            "退化变体由规则派生而非真实基础 Agent 输出，只用于机制归因，不能当作基线能力评测。",
            "指标全部基于机检口径（可检索性、字段完整性），不衡量文学质量与学术判断对错。",
            "样本为单个案例的一次运行，结论不外推到其他稿件长度/意见规模。",
            "证据可核验率依赖基线稿可提取；基线稿缺失时该项按未回证计并在 audit.gates 标注。",
        ],
        "notes": notes,
        "exit_policy": "always_zero",
    }
    if _runlog:
        _runlog.log_event("gain_compare", "compare", round(time.time() - t0, 3), ok=True,
                          modes=list(results.keys()))
    if args.out:
        _write(args.out, json.dumps(gain, ensure_ascii=False, indent=1))
    print(json.dumps({
        "ok": True,
        "modes": {k: {m: v[m] for m in ("comment_response_coverage",
                                        "comment_response_coverage_cm",
                                        "reply_revision_consistency",
                                        "evidence_verifiability",
                                        "modification_locator_rate",
                                        "manual_review_items")}
                  for k, v in results.items()},
        "manual_review_saved": gain["efficiency"]["manual_review_saved"],
        "script_call_total": gain["efficiency"]["script_call_total"],
        "out": args.out, "exit_code": 0}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
