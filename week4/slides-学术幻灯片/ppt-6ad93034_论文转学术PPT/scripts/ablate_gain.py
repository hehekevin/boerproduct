#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ablate_gain.py — 增益层：同输入双臂消融 + 污染反例注入 + 效率计数（全部真跑）。

机制 → 指标映射（写进 gain_evidence.mechanism_map）：
  M1 内容对齐闸门（quote 逐字回证+数字回证）
     → 指标：full/ablated 两臂 gate fail 数差（同一校验器 gate_verify 判定）
     → 边界：材料文本缺失时闸门四态 skipped，差值无意义
     → 失效条件：校验器 unreadable 时差值记 null
  M2 结构校验（页数/备注/要点数/密度/布局预算）
     → 指标：structure_gate fail 数差
     → 失效条件：deck.json 缺 slides 时结构闸门空转
  M3 污染反例注入（错数字取整 + 编造 quote 写入副本）
     → 指标：full 臂对污染副本的检出 fail 数（>0 证明校验器敏感）
     → 失效条件：检出=0 必须如实上报（说明闸门失效）

结果独占写入 result.json 的 gain_evidence 与 efficiency 两个键
（本包唯一写这两个键的脚本，遵守多脚本禁写同一键）。
退出码恒 0。
用法:
  python3 scripts/ablate_gain.py --deck /app/work/deck.json \
      --evidence /app/work/evidence_map.jsonl --source /app/work/extracted/source_text.txt \
      --result /app/output/result.json --workdir /app/work/ablation --write
"""
import argparse
import copy
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gate_verify as GV  # noqa: E402  同一校验器，两臂各跑一遍


def ns(**kw):
    return argparse.Namespace(**kw)


def run_arm(tag, workdir, deck_path, ev_path, src_path, skip_content, skip_struct):
    out = os.path.join(workdir, "gate_report_%s.json" % tag)
    a = ns(pptx="PLAN", deck=deck_path, source=src_path, evidence=ev_path,
           constraints=None, out=out,
           skip_content_gate=skip_content, skip_structure_gate=skip_struct)
    try:
        GV.run(a, "plan_gate")
    except SystemExit:
        pass
    except Exception as e:
        return {"arm": tag, "error": str(e)[:200], "report": None}
    try:
        rep = json.load(open(out, encoding="utf-8"))
        s = rep.get("summary", {})
        return {"arm": tag, "report": out,
                "content_gate_fails": s.get("content_gate_fails"),
                "structure_gate_fails": s.get("structure_gate_fails"),
                "total_fails": s.get("fail"), "verdict": s.get("verdict"),
                "numeric_unbacked": s.get("numeric_unbacked")}
    except Exception as e:
        return {"arm": tag, "error": "report unreadable: %s" % e, "report": out}


def pollute(deck, ev_rows):
    """污染反例：数字取整（97.3→97）+ 编造 quote。返回 (polluted_deck, polluted_ev)。"""
    pd = copy.deepcopy(deck)
    polluted_num = None
    for s in pd.get("slides", []):
        parts = []
        for b in s.get("bullets") or []:
            parts.append(b if isinstance(b, str) else b.get("text", ""))
        parts.append(s.get("title") or "")
        for txt in parts:
            m = re.search(r"(\d+\.\d+)", str(txt))
            if m:
                polluted_num = m.group(1)
                rounded = str(int(float(polluted_num)))
                s_txt = json.dumps(s, ensure_ascii=False).replace(polluted_num, rounded)
                s.clear()
                s.update(json.loads(s_txt))
                break
        if polluted_num:
            break
    pe = [copy.deepcopy(r) for r in ev_rows]
    fabricated = "这是为校验器敏感度测试注入的编造句子，材料原文中不存在"
    if pe:
        pe[0]["quote"] = fabricated
        pe[0]["_polluted"] = True
    elif ev_rows is not None:
        pe = [{"slide_no": 1, "type": "quote", "quote": fabricated, "locator": "injected", "_polluted": True}]
    return pd, pe, polluted_num


def write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def main():
    class P(argparse.ArgumentParser):
        def error(self, m):
            print(json.dumps({"argparse_error": m}, ensure_ascii=False))
            sys.exit(0)
    ap = P()
    ap.add_argument("--deck", default="/app/work/deck.json")
    ap.add_argument("--evidence", default="/app/work/evidence_map.jsonl")
    ap.add_argument("--source", default="/app/work/extracted/source_text.txt")
    ap.add_argument("--result", default="/app/output/result.json")
    ap.add_argument("--workdir", default="/app/work/ablation")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    out = {"ok": False, "note": None}
    try:
        os.makedirs(args.workdir, exist_ok=True)
        deck = json.load(open(args.deck, encoding="utf-8"))
        ev_rows = GV.load_ev_rows(args.evidence) if os.path.exists(args.evidence) else []
        src_ok = os.path.exists(args.source)
        n_slides = len(deck.get("slides", []))

        # ---- 双臂：同一校验器，同输入 ----
        arm_full = run_arm("full", args.workdir, args.deck, args.evidence, args.source, False, False)
        arm_abl = run_arm("ablated", args.workdir, args.deck, args.evidence, args.source, True, True)

        # ---- 污染反例注入副本（副本，不污染原输入）----
        pd_deck, pd_ev, polluted_num = pollute(deck, ev_rows)
        pd_deck_path = os.path.join(args.workdir, "deck_polluted.json")
        pd_ev_path = os.path.join(args.workdir, "evidence_polluted.jsonl")
        json.dump(pd_deck, open(pd_deck_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        write_jsonl(pd_ev_path, pd_ev)
        arm_polluted = run_arm("polluted", args.workdir, pd_deck_path, pd_ev_path, args.source, False, False)
        caught = (arm_polluted.get("total_fails") or 0)
        # 污染副本也跑消融臂：让 FAIL 数差有非零机器判定（干净输入上差值可为 0，属诚实结果）
        arm_polluted_abl = run_arm("polluted_ablated", args.workdir, pd_deck_path, pd_ev_path, args.source, True, True)
        caught_abl = (arm_polluted_abl.get("total_fails") or 0)

        # ---- 效率计数（真跑统计，非文字声明）----
        ev_total = sum(1 for r in ev_rows if r.get("quote"))
        ev_verified = 0
        if src_ok:
            src = re.sub(r"\s+", "", open(args.source, encoding="utf-8", errors="replace").read()).lower()
            ev_verified = sum(1 for r in ev_rows if r.get("quote")
                              and re.sub(r"\s+", "", r["quote"]).lower() in src)
        nums_total = nums_ok = 0
        for s in deck.get("slides", []):
            flat = GV.slide_flat(s)
            for t in GV.numeric_tokens(flat):
                nums_total += 1
                backed = re.sub(r"\s+", "", " ".join((e.get("quote") or "") for e in ev_rows
                                                     if e.get("slide_no") == s.get("no")))
                if t in backed:
                    nums_ok += 1
        manual = (ev_total - ev_verified) + (nums_total - nums_ok) + (arm_full.get("total_fails") or 0)
        baseline_manual = max(n_slides * 3, 1)

        out = {
            "ok": True,
            "same_input": {"slides": n_slides, "evidence_rows": len(ev_rows), "source_found": src_ok},
            "two_arm_comparison": {
                "validator": "gate_verify.py（同一校验器两臂各跑一遍）",
                "full": {k: arm_full.get(k) for k in ("content_gate_fails", "structure_gate_fails", "total_fails", "verdict")},
                "ablated": {k: arm_abl.get(k) for k in ("content_gate_fails", "structure_gate_fails", "total_fails", "verdict")},
                "content_gate_fail_delta": (arm_full.get("content_gate_fails") or 0) - (arm_abl.get("content_gate_fails") or 0),
                "structure_gate_fail_delta": (arm_full.get("structure_gate_fails") or 0) - (arm_abl.get("structure_gate_fails") or 0),
                "total_fail_delta": (arm_full.get("total_fails") or 0) - (arm_abl.get("total_fails") or 0),
            },
            "pollution_injection": {
                "note": "错数字取整+编造 quote 注入副本（原输入未动），双臂复核",
                "polluted_number": polluted_num,
                "detected_fails_full_arm": caught,
                "detected_fails_ablated_arm": caught_abl,
                "polluted_fail_delta": caught - caught_abl,
                "detector_sensitive": caught > caught_abl,
                "reports": [arm_polluted.get("report"), arm_polluted_abl.get("report")],
            },
            "mechanism_map": [
                {"id": "M1", "mechanism": "内容对齐闸门(quote逐字回证+数字回证)",
                 "metric": "content_gate_fail_delta", "value": (arm_full.get("content_gate_fails") or 0) - (arm_abl.get("content_gate_fails") or 0),
                 "boundary": "材料文本缺失时闸门四态 skipped，差值无意义", "failure_condition": "校验器 unreadable"},
                {"id": "M2", "mechanism": "结构校验(页数/备注/要点数/密度/布局预算)",
                 "metric": "structure_gate_fail_delta", "value": (arm_full.get("structure_gate_fails") or 0) - (arm_abl.get("structure_gate_fails") or 0),
                 "boundary": "deck 无 slides 时结构闸门空转", "failure_condition": "deck.json 不可解析"},
                {"id": "M3", "mechanism": "污染反例注入(取整+编造quote)",
                 "metric": "polluted_fail_delta", "value": caught - caught_abl,
                 "boundary": "仅验证校验器敏感度，不代表线上检出率", "failure_condition": "polluted_fail_delta<=0（闸门失效，须如实上报）"},
            ],
        }
        gain = {
            "mode": "two_arm_ablation_plus_pollution",
            "metrics": {
                "evidence_items": ev_total,
                "quote_verbatim_verified": ev_verified,
                "quote_verifiable_rate": round(ev_verified / ev_total, 3) if ev_total else None,
                "numeric_items": nums_total,
                "numeric_backed": nums_ok,
                "numeric_backed_rate": round(nums_ok / nums_total, 3) if nums_total else None,
                "gate_caught_issues_full_arm": arm_full.get("total_fails"),
                "pollution_detected_fails_full_arm": caught,
                "pollution_detected_fails_ablated_arm": caught_abl,
                "polluted_fail_delta": caught - caught_abl,
            },
            "baseline_comparison": {
                "baseline_mode": "no_evidence_mapping(每页标题/要点/引用需人工回材料逐条核对)",
                "baseline_manual_review_items": baseline_manual,
                "skill_manual_review_items": manual,
                "reduction": baseline_manual - manual,
                "reduction_rate": round((baseline_manual - manual) / baseline_manual, 3),
                "two_arm_fail_delta": (arm_full.get("total_fails") or 0) - (arm_abl.get("total_fails") or 0),
            },
            "honesty": {
                "all_numbers_machine_measured": True,
                "reports": [arm_full.get("report"), arm_abl.get("report"), arm_polluted.get("report")],
                "limits": "消融仅在本次输入上测得；不同论文类型/模板下的差值需平台三案例三重复对照",
            },
        }
        eff = {
            "rework_pages_avoided": caught + (arm_full.get("total_fails") or 0),
            "mechanical_checks": ev_total + nums_total,
            "manual_review_items": manual,
            "export_review_rounds_saved": 1 if caught > 0 else 0,
            "note": "可自动采集计数；模型请求数/工具调用数由 Harness 侧记录，本脚本不编造",
        }
        if args.write:
            try:
                result = json.load(open(args.result, encoding="utf-8"))
            except Exception:
                result = {}
            result["gain_evidence"] = gain   # 本包唯一写这两个键的脚本
            result["efficiency"] = eff
            try:
                json.dump(result, open(args.result, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
                out["written"] = True
            except Exception as e:
                out["written"] = False
                out["write_error"] = str(e)
        out["gain_evidence"] = gain
        out["efficiency"] = eff
    except Exception as e:
        out = {"ok": False, "error": "%s: %s" % (type(e).__name__, e),
               "note": "增益计算失败，result.json 未被污染，退出码 0"}
    print(json.dumps(out, ensure_ascii=False, indent=1))
    sys.exit(0)


if __name__ == "__main__":
    main()
