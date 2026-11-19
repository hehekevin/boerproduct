#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ledger_audit.py — 审稿回复三方对齐机检 + 逐项指标 + 可消融对照

逐条三元组: 每个子要求每项检查输出 {sid, item, applied, match}，
全部结果写入报告（含 problems 与 unbacked 逐条清单），报告随 finalize 嵌入 result.json。
闸门状态显式枚举: enforced / skipped_not_provided / not_found / unreadable；
未运行 ≠ 通过——skipped 必须写 gate_note，下游不得宣称该项已核对。

检查项:
  letter_in_letter     letter_text 在回复信中可检索（回复↔回复信对齐）
  revised_in_revised   revision_log.revised 在修订稿可检索（修改↔修订稿对齐）
  original_in_baseline revision_log.original 在基线稿可检索（修改↔原稿对齐）
  revision_log_fields  四字段 original/revised/reason/basis 齐全（basis 含定位）
  decision_valid       决策 ∈ adopted/partially_adopted/rejected
  rejection_rationale  rejected/partially_adopted 有理由
  evidence_status_valid 证据状态合法
  evidence_backed      证据 source 引文在基线稿中逐字可查（unbacked 逐条列出）
  coverage             每个子要求有决策+回复文字（汇总项）
  tone_clean           回复信无冒犯/过度承诺词（汇总项）
  triad_ok             单条子要求三角对齐总判定（回复↔修订稿↔基线/台账）
  locator_present      每处修改带可检索定位（locator/pid）

消融对照（--ablate triad,verbatim,tone,coverage）:
  被消融的检查项仍会计算真实 match，但 applied=false 且不计入 problems；
  被抑制的问题逐条记入 suppressed_problems——即"关掉该机制就漏检了什么"的直接证据。
  无论消融与否，脚本退出码恒为 0（失败绝不中断交付），问题一律记在报告里。

用法:
  python3 ledger_audit.py --ledger /app/work/response_ledger.jsonl \
      --letter /app/output/response_letter.md --revised /app/output/revised.md \
      --original /app/work/extracted --out /app/output/ledger_audit.json \
      [--ablate triad,verbatim]
"""
import argparse, json, os, re, sys, glob, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import _runlog
except Exception:  # pragma: no cover
    _runlog = None

BAD_TONE = ["显然你", "你没看", "错误百出", "胡说", "荒谬", "无聊",
            "抱歉耽误您时间我们马上全部照改"]
OVERPROMISE = ["我们将补所有", "全部重做", "保证接收", "完全按照您的一切意见"]
REV_FIELDS = ("original", "revised", "reason", "basis")
VALID_DECISION = ("adopted", "partially_adopted", "rejected")
VALID_EVIDENCE = ("done", "replaced_by_alternative", "not_possible", "planned")
QUOTE_MIN = 12  # source 引文最短长度（>=12 字符才做逐字回证）

# 检查项 → 消融分组
ABLATE_GROUPS = {
    "triad": ["letter_in_letter", "revised_in_revised", "original_in_baseline", "triad_ok"],
    "verbatim": ["evidence_backed", "evidence_unbacked"],
    "tone": ["tone_clean"],
    "coverage": ["coverage"],
}


def _norm(s):
    return re.sub(r"\s+", "", str(s))


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _gate(path_or_dir):
    """闸门状态显式枚举: enforced / skipped_not_provided / not_found / unreadable。"""
    if not path_or_dir:
        return "skipped_not_provided"
    if not os.path.exists(path_or_dir):
        return "not_found"
    if os.path.isdir(path_or_dir) and not glob.glob(os.path.join(path_or_dir, "*.txt")):
        return "unreadable"
    try:
        _read(path_or_dir) if os.path.isfile(path_or_dir) else glob.glob(
            os.path.join(path_or_dir, "*.txt"))[0]
        return "enforced"
    except Exception:
        return "unreadable"


def _load_original(path_or_dir):
    if not path_or_dir:
        return ""
    if os.path.isdir(path_or_dir):
        return "\n".join(_read(fp) for fp in sorted(glob.glob(os.path.join(path_or_dir, "*.txt"))))
    return _read(path_or_dir)


def _pct(a, b):
    return round(100.0 * a / b, 2) if b else 0.0


def run_audit(ledger_path, letter_path, revised_path, original=None, ablate=()):
    """核心机检（可被 gain_compare.py 直接调用）。返回 report dict。"""
    ablate = set(ablate or ())
    ablated_items = set()
    for g in ablate:
        ablated_items.update(ABLATE_GROUPS.get(g, []))

    gates = {}
    for name, p in (("ledger", ledger_path), ("letter", letter_path),
                    ("revised", revised_path), ("original", original)):
        gates[name] = {"state": _gate(p), "path": p or None}
    gate_notes = [f"gate[{k}]={v['state']}: 该项检查未运行，下游不得宣称已核对"
                  for k, v in gates.items() if v["state"] != "enforced"]

    problems, checks, unbacked = [], [], []
    suppressed = []
    rows = []
    per_sid = {}
    manual_items = []
    evidence_total = 0
    evidence_verifiable = 0

    def add_check(sid, item, applied, match, note=None):
        rec = {"sid": sid, "item": item, "applied": bool(applied), "match": bool(match)}
        if note:
            rec["note"] = note
        if item in ablated_items:
            rec["applied"] = False
            rec["ablated"] = True
            rec["note"] = (note + "；" if note else "") + "该项在本轮被消融（对照模式），不计入 verdict"
        checks.append(rec)
        if applied and not match:
            p = {"type": item, "sid": sid}
            if item in ablated_items:
                suppressed.append(p)
            else:
                problems.append(p)
        return rec

    if all(gates[k]["state"] == "enforced" for k in ("ledger", "letter", "revised")):
        rows, bad_lines = [], []
        for i, l in enumerate(_read(ledger_path).splitlines(), 1):
            l = l.strip()
            if not l:
                continue
            try:
                rows.append(json.loads(l))
            except Exception:
                bad_lines.append(i)
        if bad_lines:
            gate_notes.append(f"台账第 {bad_lines[:10]} 行 JSON 解析失败，已跳过（台账不完整）")
            problems.append({"type": "ledger_parse_error", "sid": f"lines{bad_lines[:10]}"})
        letter_norm = _norm(_read(letter_path))
        letter_raw = _read(letter_path)
        revised_norm = _norm(_read(revised_path))
        orig_enforced = gates["original"]["state"] == "enforced"
        orig_norm = _norm(_load_original(original)) if orig_enforced else ""

        for r in rows:
            sid = r.get("sid") or "?"
            lt = _norm(r.get("letter_text") or "")
            st = {"sid": sid, "cm": r.get("cm"), "decision": r.get("decision"),
                  "tone": r.get("tone"), "letter_found": False, "edits": 0,
                  "edits_revised_ok": 0, "edits_original_ok": 0,
                  "evidence_items": 0, "evidence_ok": 0, "triad_ok": False,
                  "manual": []}
            per_sid[sid] = st

            # 1) 回复↔回复信对齐
            m = add_check(sid, "letter_in_letter", True, bool(lt) and lt[:30] in letter_norm,
                          None if lt else "letter_text 为空")
            st["letter_found"] = bool(m["match"])
            if not st["letter_found"]:
                st["manual"].append("reply_not_in_letter")

            # 2/3) 修改↔修订稿/基线稿对齐
            edits = r.get("edits", []) or []
            st["edits"] = len(edits)
            for e in edits:
                rl = e.get("revision_log") or {}
                after = _norm(rl.get("revised") or e.get("after") or "")
                before = _norm(rl.get("original") or e.get("anchor_quote") or "")
                m_rev = add_check(sid, "revised_in_revised", bool(after),
                                  bool(after) and after[:30] in revised_norm)
                st["edits_revised_ok"] += 1 if m_rev["match"] else 0
                m_orig = add_check(sid, "original_in_baseline", bool(before),
                                   bool(before) and bool(orig_norm) and before[:30] in orig_norm,
                                   None if orig_norm else "基线稿未提供，未核对")
                st["edits_original_ok"] += 1 if m_orig["match"] else 0
                if before and orig_norm and not m_orig["match"]:
                    st["manual"].append("original_not_in_baseline")
                miss = [f for f in REV_FIELDS if not str(rl.get(f) or "").strip()]
                add_check(sid, "revision_log_fields", True, not miss,
                          None if not miss else f"缺 {miss}")
                basis = str(rl.get("basis") or "")
                add_check(sid, "basis_locator", True, len(basis) >= 4,
                          None if len(basis) >= 4 else "basis 无定位依据")
                loc = str(e.get("locator") or "").strip()
                add_check(sid, "locator_present", True, bool(loc),
                          None if loc else "缺 locator/定位串")
                if not loc:
                    st["manual"].append("no_locator")

            # 4) 决策合法 + rejected 有理由
            d = r.get("decision")
            add_check(sid, "decision_valid", True, d in VALID_DECISION)
            if d in ("rejected", "partially_adopted"):
                add_check(sid, "rejection_rationale", True,
                          len(str(r.get("decision_rationale") or "")) >= 10)
            if not d:
                st["manual"].append("no_decision")

            # 5) 证据状态合法 + source 引文逐字回证
            for ev in r.get("evidence", []) or []:
                evidence_total += 1
                st["evidence_items"] += 1
                add_check(sid, "evidence_status_valid", True, ev.get("status") in VALID_EVIDENCE)
                src = str(ev.get("source") or "")
                status = ev.get("status")
                ok = False
                if status == "done" and len(src) >= QUOTE_MIN:
                    if not orig_norm:
                        unbacked.append({"sid": sid, "source": src[:60],
                                         "reason": "基线稿未提供，无法逐字回证"})
                        ok = False
                    else:
                        ok = _norm(src)[:30] in orig_norm
                        if not ok:
                            unbacked.append({"sid": sid, "source": src[:60],
                                             "reason": "引文在基线稿中不可检索"})
                            add_check(sid, "evidence_backed", True, False,
                                      "引文不可检索")
                            if "evidence_unbacked" not in ablated_items:
                                problems.append({"type": "evidence_unbacked", "sid": sid})
                            else:
                                suppressed.append({"type": "evidence_unbacked", "sid": sid})
                elif status in ("replaced_by_alternative", "not_possible"):
                    ok = len(src) >= 4
                else:  # planned / 其他
                    ok = False
                if ok:
                    evidence_verifiable += 1
                    st["evidence_ok"] += 1
                else:
                    st["manual"].append("evidence_not_verifiable")

            if r.get("needs_author") or r.get("manual_confirm"):
                st["manual"].append("needs_author")
            if r.get("unresolvable"):
                st["manual"].append("comment_unresolvable")

            # 三角对齐总判定（回复↔修订稿↔基线/台账）
            edits_ok = (st["edits"] == 0) or (st["edits_revised_ok"] == st["edits"] and
                                              st["edits_original_ok"] == st["edits"])
            st["triad_ok"] = bool(st["letter_found"] and edits_ok and bool(d))
            add_check(sid, "triad_ok", True, st["triad_ok"],
                      None if st["triad_ok"] else "三角未对齐")

        # 6) 覆盖完整性 + 语气（汇总级）
        uncovered = [r.get("sid") for r in rows
                     if not r.get("decision") or not str(r.get("letter_text") or "").strip()]
        add_check("-", "coverage", True, not uncovered,
                  None if not uncovered else f"未覆盖 {uncovered[:10]}")
        tone_hits = [w for w in BAD_TONE + OVERPROMISE if w in letter_raw]
        add_check("-", "tone_clean", True, not tone_hits,
                  None if not tone_hits else f"命中 {tone_hits}")
    else:
        gate_notes.append("核心输入缺失，三方对齐机检未运行")

    # 逐项指标（真实产物质量，与消融无关）
    subs_total = len(rows)
    covered = sum(1 for st in per_sid.values() if st["decision"] and st["letter_found"])
    triad_ok_n = sum(1 for st in per_sid.values() if st["triad_ok"])
    for st in per_sid.values():
        for reason in st["manual"]:
            manual_items.append({"sid": st["sid"], "reason": reason})
    metrics = {
        "subs_total": subs_total,
        "comment_response_coverage": _pct(covered, subs_total),
        "comment_response_covered": covered,
        "reply_revision_consistency": _pct(triad_ok_n, subs_total),
        "reply_revision_consistent": triad_ok_n,
        "evidence_verifiability": _pct(evidence_verifiable, evidence_total),
        "evidence_items_total": evidence_total,
        "evidence_items_verifiable": evidence_verifiable,
        "manual_review_items": len(manual_items),
        "manual_review_breakdown": {
            k: sum(1 for m in manual_items if m["reason"] == k)
            for k in sorted({m["reason"] for m in manual_items})
        },
        "checks_total": len(checks),
        "checks_matched": sum(1 for c in checks if c["match"]),
        "unbacked_count": len(unbacked),
    }
    report = {"subs_total": subs_total, "verdict": "pass" if not problems else "fail",
              "fail": len(problems), "problems": problems, "checks": checks,
              "checks_total": len(checks), "checks_matched": sum(1 for c in checks if c["match"]),
              "unbacked": unbacked, "gates": gates, "gate_notes": gate_notes,
              "metrics": metrics, "per_sid": per_sid, "manual_review_items": manual_items,
              "ablate": sorted(ablate),
              "suppressed_problems": suppressed,
              "suppressed_count": len(suppressed),
              "exit_policy": "always_zero（问题记入本报告，不中断交付）",
              "hint": "fail/unbacked 逐条回台账、回复信或基线定位修复后重跑；报告始终写盘。"}
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--letter", required=True)
    ap.add_argument("--revised", required=True)
    ap.add_argument("--original", default=None, help="基线稿提取文本目录或文件")
    ap.add_argument("--out", default=None)
    ap.add_argument("--ablate", default="", help="消融组: triad,verbatim,tone,coverage（逗号分隔）")
    args = ap.parse_args()

    t0 = time.time()
    ablate = [x.strip() for x in str(args.ablate).split(",") if x.strip()]
    report = run_audit(args.ledger, args.letter, args.revised, args.original, ablate)
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        json.dump(report, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    mt = report["metrics"]
    print(json.dumps({"verdict": report["verdict"], "subs": report["subs_total"],
                      "checks": report["checks_total"], "matched": report["checks_matched"],
                      "unbacked": len(report["unbacked"]),
                      "problems": sorted({p["type"] for p in report["problems"]}),
                      "suppressed": report["suppressed_count"],
                      "ablate": report["ablate"],
                      "metrics": {k: mt[k] for k in
                                  ("comment_response_coverage", "reply_revision_consistency",
                                   "evidence_verifiability", "manual_review_items")},
                      "gates": {k: v["state"] for k, v in report["gates"].items()},
                      "exit_code": 0}, ensure_ascii=False))
    if _runlog:
        _runlog.log_event("ledger_audit", "audit", round(time.time() - t0, 3),
                          ok=(report["verdict"] == "pass"),
                          subs=report["subs_total"], verdict=report["verdict"],
                          ablate=report["ablate"], metrics=mt)
    return 0  # 失败绝不中断交付


if __name__ == "__main__":
    sys.exit(main())
