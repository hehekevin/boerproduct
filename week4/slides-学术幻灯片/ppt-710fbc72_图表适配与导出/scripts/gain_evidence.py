#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gain_evidence.py — 增益证据层：同输入对照 + 效率计数 + --ablate 消融双臂。

四种模式（可组合）：
  （默认）skill 模式   以本次 result.json 实测——页数、含证据页数、quote 逐字可回证率、
                      数值有据率、需人工核对条目数。
  --baseline           模拟「不做证据映射/不做引用逐字回证」的基础路径计数。
  --ablate             消融实验：同一校验器对两臂各跑一遍——
                      臂A(full)=原始 deck+evidence；臂B(polluted)=注入污染反例的副本
                      （每 2 条 quote 改写 1 条、每 3 页删 1 页全部证据行、抽掉模板值）。
                      FAIL 数差是机器判定，写入 gain_evidence.ablation。
  --write              把结果写进 result.json 的 gain_evidence 与 efficiency 两个键
                      （其余脚本不写这两个键，防多脚本互踩）。

机制→指标映射、边界与失效条件随消融结果一并输出。退出码恒 0。
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pptx_verify import run_gates, _norm  # noqa: E402


def load(p):
    if not p or not os.path.exists(p):
        return None
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None


def read_text(p):
    if not p or not os.path.exists(p):
        return ""
    if os.path.isdir(p):
        buf = []
        for root, _, fs in os.walk(p):
            for f in sorted(fs):
                if f.lower().endswith((".txt", ".md", ".json", ".csv")):
                    try:
                        buf.append(open(os.path.join(root, f), encoding="utf-8", errors="ignore").read())
                    except Exception:
                        pass
        return re.sub(r"\s+", "", "".join(buf))
    try:
        return re.sub(r"\s+", "", open(p, encoding="utf-8", errors="ignore").read())
    except Exception:
        return ""


def slides_of(result):
    for k in ("deliverable", "slides", "slide_plan", "pages"):
        v = result.get(k)
        if isinstance(v, dict) and isinstance(v.get("slides"), list):
            return v["slides"]
        if isinstance(v, list):
            return v
    return []


def measure(result, paper):
    slides = slides_of(result)
    total = len(slides)
    ev_total = ev_verified = pages_with_ev = nums_total = nums_ok = 0
    for s in slides:
        if not isinstance(s, dict):
            continue
        evs = s.get("evidence") or []
        if isinstance(evs, list) and evs:
            pages_with_ev += 1
        for e in evs:
            if not isinstance(e, dict):
                continue
            q = str(e.get("quote") or "")
            if not q:
                continue
            ev_total += 1
            if paper and _norm(q).lower() in paper.lower():
                ev_verified += 1
        txt = " ".join(str(x) for x in (s.get("bullets") or [])) + " " + str(s.get("title") or "")
        for n in re.findall(r"\d+(?:\.\d+)?%?", txt):
            nums_total += 1
            if paper and n in paper:
                nums_ok += 1
    gates = result.get("gates") or {}
    mism = 0
    if isinstance(gates, dict):
        for v in gates.values():
            if isinstance(v, dict) and isinstance(v.get("fail"), int):
                mism += v["fail"]
    manual = (ev_total - ev_verified) + max(0, nums_total - nums_ok) + mism
    return {"slides_total": total, "pages_with_evidence": pages_with_ev,
            "page_evidence_coverage_rate": round(pages_with_ev / total, 3) if total else None,
            "evidence_items": ev_total, "quote_verbatim_verified": ev_verified,
            "quote_verifiable_rate": round(ev_verified / ev_total, 3) if ev_total else None,
            "numeric_items": nums_total, "numeric_backed": nums_ok,
            "numeric_backed_rate": round(nums_ok / nums_total, 3) if nums_total else None,
            "manual_review_items": manual}


def inject_pollution(deck, ev_rows, outdir):
    """污染反例注入副本：改写 quote / 删证据行 / 制造悬空图号引用。

    每种污染各对应一个闸门，用于证明「闸门真的在抓」而不是恒过。
    """
    os.makedirs(outdir, exist_ok=True)
    polluted = []
    quote_reworded = 0
    dropped_slides = []
    for i, r in enumerate(ev_rows):
        # 每 3 行删 1 行证据（模拟基础路径无证据映射），对应页失去覆盖
        if i % 3 == 0 and r.get("slide_no") is not None and r["slide_no"] not in dropped_slides:
            dropped_slides.append(r["slide_no"])
            continue
        r2 = dict(r)
        # 只对存活行改写——保证「改写数=改写且仍在臂B中的条数」不虚报
        if r2.get("quote") and i % 2 == 1:
            q = r2["quote"]
            # 改写手法：数字取整/换尾符——模拟"改写事实再上页"
            r2["quote"] = re.sub(r"\d+\.\d+", lambda m: m.group(0).split(".")[0], q, count=1)
            if r2["quote"] == q:
                r2["quote"] = q[:-1] + ("。" if not q.endswith("。") else "；")
            quote_reworded += 1
        polluted.append(r2)
    # 悬空图号引用：正文加一条引用 Fig.99 的要点（图注不存在）；
    # 由 render_export.figure_ref_alignment 判定（不在 run_gates 内，见 mechanisms 边界说明）
    if deck.get("slides"):
        deck["slides"][0].setdefault("bullets", []).append("与 Fig.99 的趋势一致（污染注入）")
    p_deck = os.path.join(outdir, "deck.polluted.json")
    p_ev = os.path.join(outdir, "evidence_map.polluted.jsonl")
    with open(p_deck, "w", encoding="utf-8") as f:
        json.dump(deck, f, ensure_ascii=False, indent=1)
    with open(p_ev, "w", encoding="utf-8") as f:
        for r in polluted:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return p_deck, p_ev, {"quotes_reworded": quote_reworded,
                          "evidence_rows_dropped_slides": dropped_slides,
                          "dangling_figure_ref": "Fig.99 -> slide 1"}


def ablate(deck_path, ev_path, paper_path, workdir):
    """消融双臂：同一校验器（pptx_verify.run_gates）各跑一遍，FAIL 数差即增益。"""
    deck = load(deck_path)
    if not isinstance(deck, dict) or not deck.get("slides"):
        return {"ok": False, "error": "deck 不可解析或无 slides，消融未执行",
                "boundary": "消融需要 /app/work/deck.json 与 evidence_map.jsonl；缺失时本项如实登记为未执行"}
    ev_rows = []
    if ev_path and os.path.exists(ev_path):
        ev_rows = load_ev_rows_safe(ev_path)
    ablate_dir = os.path.join(workdir, "ablate")
    injection = inject_pollution(deck, ev_rows, ablate_dir)
    p_deck, p_ev, inj = injection[0], injection[1], injection[2]

    arm_full = run_gates(deck, ev_rows, paper_path if paper_path and os.path.exists(paper_path) else None)
    deck_p = load(p_deck)
    ev_p = load_ev_rows_safe(p_ev)
    arm_poll = run_gates(deck_p, ev_p, paper_path if paper_path and os.path.exists(paper_path) else None)

    # 动态统计：被删证据后真正失去覆盖的页（deck 有页而臂B无任何证据行）
    kept_slides = {r.get("slide_no") for r in ev_p}
    all_slides = {s.get("no") for s in (deck.get("slides") or [])}
    lost_slides = sorted(all_slides - kept_slides)

    qf_full = arm_full["quote_gate"].get("fail", 0)
    qf_poll = arm_poll["quote_gate"].get("fail", 0)
    cf_full = arm_full["coverage_gate"].get("fail_slides", 0)
    cf_poll = arm_poll["coverage_gate"].get("fail_slides", 0)
    unbacked_full = sum(len(c.get("numeric_unbacked") or []) for c in arm_full["slide_coverage"])
    unbacked_poll = sum(len(c.get("numeric_unbacked") or []) for c in arm_poll["slide_coverage"])

    return {
        "ok": True,
        "design": "同输入两臂：A=原始 deck+evidence；B=注入污染反例的副本（quote 改写/证据行删除/悬空图号）。同一校验器 run_gates 各跑一遍，FAIL 数差为机器判定。",
        "injection": inj,
        "arms": {
            "full": {"quote_gate_fail": qf_full, "coverage_fail_slides": cf_full,
                     "numeric_unbacked": unbacked_full, "total_fail": arm_full["fail"]},
            "polluted": {"quote_gate_fail": qf_poll, "coverage_fail_slides": cf_poll,
                         "numeric_unbacked": unbacked_poll, "total_fail": arm_poll["fail"]},
        },
        "mechanisms": [
            {"mechanism": "quote 逐字回证闸门", "metric": "quote_gate_fail(臂B-臂A)",
             "observed_diff": qf_poll - qf_full,
             "expected": "改写 %d 条存活 quote 应全部被抓（差值≥%d）" % (inj["quotes_reworded"], inj["quotes_reworded"]),
             "boundary": "只抓空白归一化后的逐字不匹配；同义改写若保持逐字子串则抓不到（本就不该逐字匹配）",
             "failure_condition": "论文文本不可读时 quote_gate 四态降级 unreadable，差值记 0 并如实登记"},
            {"mechanism": "证据覆盖闸门", "metric": "coverage_fail_slides(臂B-臂A)",
             "observed_diff": cf_poll - cf_full,
             "expected": "证据行删除导致 %d 页失去覆盖，应全部被抓" % len(lost_slides),
             "boundary": "按页判 fail（页内无任何证据行才 fail），不校验证据条数下限",
             "failure_condition": "deck 无 slides 时消融整体未执行"},
            {"mechanism": "数字回证闸门", "metric": "numeric_unbacked(臂B-臂A)",
             "observed_diff": unbacked_poll - unbacked_full,
             "expected": "改写/删证后数字失去回证来源，差值≥0 且随污染增加",
             "boundary": "只抓百分数/小数/带单位数（纯整数误报太高不抓）",
             "failure_condition": "无论文文本时数字回证未执行，差值记 0"},
        ],
        "verdict": {
            "gates_catch_pollution": (qf_poll > qf_full) and (cf_poll > cf_full),
            "note": "quote 与覆盖两闸门差值均 >0 才可宣称闸门在真实抓错；任一为 0 须在 worklog 如实登记边界（图号错位由 render_export.figure_ref_alignment 另行判定，不计入 run_gates）",
        },
    }


def load_ev_rows_safe(path):
    rows = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except Exception:
                        rows.append({"_parse_error": line[:120]})
    except Exception:
        pass
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--result", default="/app/output/result.json")
    ap.add_argument("--paper", default=None, help="论文文本/目录，用于 quote 逐字回证")
    ap.add_argument("--deck", default="/app/work/deck.json", help="消融用页计划")
    ap.add_argument("--evidence", default="/app/work/evidence_map.jsonl", help="消融用证据映射")
    ap.add_argument("--work", default="/app/work", help="消融副本输出目录")
    ap.add_argument("--baseline", action="store_true")
    ap.add_argument("--ablate", action="store_true")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    result = load(args.result)
    if not isinstance(result, dict):
        print(json.dumps({"ok": False, "note": "result.json 不可解析，跳过增益计算"}, ensure_ascii=False))
        return 0
    paper = read_text(args.paper)
    m = measure(result, paper)

    if args.baseline:
        out = {"mode": "baseline_no_evidence_mapping", "slides": m["slides_total"],
               "pages_without_traceable_evidence": m["slides_total"],
               "manual_review_items": m["slides_total"] * 3,
               "note": "基础路径不做证据映射与逐字回证：每页标题/要点/引用都需人工回论文逐条核对"}
    else:
        out = {"mode": "skill", "metrics": m,
               "efficiency": {"slides_built": m["slides_total"],
                              "mechanical_checks": m["evidence_items"] + m["numeric_items"],
                              "manual_review_items": m["manual_review_items"],
                              "note": "本次运行自动采集计数；模型请求数与工具调用数由 Harness 侧记录"}}
        base_manual = m["slides_total"] * 3
        out["baseline_comparison"] = {
            "baseline_manual_review_items": base_manual,
            "skill_manual_review_items": m["manual_review_items"],
            "reduction": base_manual - m["manual_review_items"],
            "reduction_rate": round((base_manual - m["manual_review_items"]) / base_manual, 3)
            if base_manual else None}

    if args.ablate:
        out["ablation"] = ablate(args.deck, args.evidence, args.paper, args.work)
        # 消融差值计入 efficiency（机器判定，非文字声明）
        abl = out["ablation"]
        if abl.get("ok"):
            out["efficiency"]["ablation_gate_fail_diff"] = \
                abl["arms"]["polluted"]["total_fail"] - abl["arms"]["full"]["total_fail"]

    if args.write:
        result["gain_evidence"] = out  # 本包只有本脚本写 gain_evidence/efficiency 两键
        result["efficiency"] = out.get("efficiency")
        try:
            with open(args.result, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=1)
            out["written"] = True
        except Exception as e:
            out["written"] = False
            out["write_error"] = str(e)
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
