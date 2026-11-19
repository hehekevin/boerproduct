#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gain_evidence.py — 论文转 PPT：增益证据层（同输入对照 + 效率计数）

skill 模式：以本次产物实测——页数、含证据页数、逐条证据数、引用可核验率
          （quote 逐字出现在论文文本的比例）、数值有据率、需人工核对条目数。
baseline 模式：模拟「不做证据映射/不做引用逐字回证」的基础路径——论文中的
          标题、要点与数值落到页面上但无法逐条回证，按不可核对项计数。
退出码恒 0：结论写进 JSON，不以退出码表达成败。
"""
import argparse, json, os, re, sys


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--result", default="/app/output/result.json")
    ap.add_argument("--paper", default=None, help="论文文本/目录，用于 quote 逐字回证")
    ap.add_argument("--baseline", action="store_true")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    result = load(args.result)
    if not isinstance(result, dict):
        print(json.dumps({"ok": False, "note": "result.json 不可解析，跳过增益计算"}, ensure_ascii=False))
        return 0
    paper = read_text(args.paper)
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
            if paper and re.sub(r"\s+", "", q) in paper:
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
    if args.baseline:
        out = {
            "mode": "baseline_no_evidence_mapping",
            "slides": total,
            "pages_without_traceable_evidence": total,
            "manual_review_items": total * 3,
            "note": "基础路径不做证据映射与逐字回证：每页标题/要点/引用都需人工回论文逐条核对",
        }
    else:
        out = {
            "mode": "skill",
            "metrics": {
                "slides_total": total,
                "pages_with_evidence": pages_with_ev,
                "page_evidence_coverage_rate": round(pages_with_ev / total, 3) if total else None,
                "evidence_items": ev_total,
                "quote_verbatim_verified": ev_verified,
                "quote_verifiable_rate": round(ev_verified / ev_total, 3) if ev_total else None,
                "numeric_items": nums_total,
                "numeric_backed": nums_ok,
                "numeric_backed_rate": round(nums_ok / nums_total, 3) if nums_total else None,
                "manual_review_items": manual,
            },
            "efficiency": {
                "slides_built": total,
                "mechanical_checks": ev_total + nums_total,
                "manual_review_items": manual,
                "note": "本次运行可自动采集的计数；模型请求数与工具调用数由 Harness 侧记录",
            },
        }
        base_manual = total * 3
        out["baseline_comparison"] = {
            "baseline_manual_review_items": base_manual,
            "skill_manual_review_items": manual,
            "reduction": base_manual - manual,
            "reduction_rate": round((base_manual - manual) / base_manual, 3) if base_manual else None,
        }
    if args.write:
        result["registry_evidence"] = out  # 独立键，避免覆盖其它脚本写的 gain_evidence
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
