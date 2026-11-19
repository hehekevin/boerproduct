#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_gate.py — 统一校验器（构建前闸门 + 消融双臂共用）。

对 deck 计划逐页做 6 项机械检查，全部结论写进 JSON（verdict/fails/metrics），
退出码恒 0——失败经由 verdict 传递，不用退出码表达。
闸门四态：enforced / skipped_not_provided / not_found / unreadable。
函数 evaluate(plan, source_text) 供 ablate.py 复用，保证两臂用同一校验器。
"""
import argparse, json, os, re, sys

NUM_RE = re.compile(r"\d+(?:\.\d+)?%?")


def norm(s):
    return re.sub(r"\s+", "", str(s or ""))


def _state(path):
    if path is None:
        return "skipped_not_provided"
    if not os.path.exists(path):
        return "not_found"
    return "ok"


def evaluate(plan, source_text, constraints=None):
    """对计划做全部闸门检查，返回报告 dict（纯函数，不落盘）。"""
    if not isinstance(plan, dict) or not isinstance(plan.get("slides"), list):
        return {"verdict": "fail", "gates": {}, "metrics": {},
                "fatal": "plan 缺 slides 数组，无法校验"}
    slides = [s for s in plan["slides"] if isinstance(s, dict)]
    src = norm(source_text) if source_text else ""
    gates, fails, warns = {}, [], []

    # ---- quote 闸门：每条证据 quote 空白归一化后逐字出现在源文本 ----
    q_total = q_ok = 0
    bad_quotes = []
    for s in slides:
        for e in (s.get("evidence") or []):
            if not isinstance(e, dict):
                continue
            q = str(e.get("quote") or "")
            if not q:
                continue
            q_total += 1
            if src and norm(q) in src:
                q_ok += 1
            else:
                bad_quotes.append({"slide": s.get("no"), "quote": q[:60]})
    gates["quote_gate"] = {
        "state": "enforced" if src else "skipped_not_provided",
        "total": q_total, "pass": q_ok, "fail": len(bad_quotes),
        "note": "" if src else "源文本未提供，下游不得宣称已核对"}
    if bad_quotes:
        fails.append({"gate": "quote_gate", "items": bad_quotes})

    # ---- 数字闸门：页面数字必须在该页 quote 里逐字出现 ----
    n_total = n_ok = 0
    unbacked = []
    for s in slides:
        page_q = norm(" ".join(str(e.get("quote") or "") for e in (s.get("evidence") or [])
                               if isinstance(e, dict)))
        txt = " ".join(str(x) for x in (s.get("bullets") or [])) + " " + str(s.get("claim") or "")
        for n in NUM_RE.findall(txt):
            n_total += 1
            if page_q and n in page_q:
                n_ok += 1
            else:
                unbacked.append({"slide": s.get("no"), "num": n})
    gates["numeric_gate"] = {"state": "enforced", "total": n_total,
                             "pass": n_ok, "fail": len(unbacked)}
    if unbacked:
        fails.append({"gate": "numeric_gate", "items": unbacked[:20]})

    # ---- 主张闸门：每内容页恰一个 claim（≤40字）、要点 ≤5 条 ----
    claim_ok = 0
    content = 0
    claim_bad = []
    for s in slides:
        role = str(s.get("role") or "")
        if role in ("title", "section", "closing", "backup"):
            continue
        content += 1
        c = str(s.get("claim") or "")
        b = s.get("bullets") or []
        if c and len(c) <= 40 and len(b) <= 5:
            claim_ok += 1
        else:
            claim_bad.append({"slide": s.get("no"), "claim_len": len(c),
                              "bullets": len(b)})
    gates["claim_gate"] = {"state": "enforced", "content_pages": content,
                           "pass": claim_ok, "fail": len(claim_bad)}
    if claim_bad:
        fails.append({"gate": "claim_gate", "items": claim_bad[:20]})

    # ---- 备注闸门：40-800 字，内容页备注含 Q: 预判问题（问答准备） ----
    notes_ok = 0
    notes_bad = []
    for s in slides:
        role = str(s.get("role") or "")
        if role in ("title", "section", "backup"):
            continue
        n = str(s.get("notes") or "")
        if 40 <= len(n) <= 800 and "Q:" in n:
            notes_ok += 1
        else:
            notes_bad.append({"slide": s.get("no"), "len": len(n), "has_q": "Q:" in n})
    gates["notes_gate"] = {"state": "enforced", "pass": notes_ok,
                           "fail": len(notes_bad),
                           "rule": "40-800字 且含 Q: 预判问题（问答准备机制）"}
    if notes_bad:
        fails.append({"gate": "notes_gate", "items": notes_bad[:20]})

    # ---- 叙事闸门：title 开头、conclusion/closing 收尾、结论不得先于结果 ----
    roles = [str(s.get("role") or "") for s in slides]
    narrative_bad = []
    if not roles or roles[0] != "title":
        narrative_bad.append("首页 role 必须为 title")
    if "conclusion" in roles and "result" in roles and \
            roles.index("conclusion") < roles.index("result"):
        narrative_bad.append("conclusion 出现在 result 之前")
    if roles and roles[-1] not in ("conclusion", "closing"):
        narrative_bad.append("末页必须为 conclusion/closing")
    gates["narrative_gate"] = {"state": "enforced", "pass": 0 if narrative_bad else 1,
                               "fail": len(narrative_bad), "items": narrative_bad}
    if narrative_bad:
        fails.append({"gate": "narrative_gate", "items": narrative_bad})

    # ---- 证据覆盖闸门：每个内容页 ≥1 条 evidence ----
    cov_ok = 0
    cov_bad = []
    for s in slides:
        role = str(s.get("role") or "")
        if role in ("title", "section", "closing"):
            continue
        ev = s.get("evidence") or []
        if isinstance(ev, list) and ev:
            cov_ok += 1
        else:
            cov_bad.append({"slide": s.get("no")})
    gates["coverage_gate"] = {"state": "enforced", "pass": cov_ok,
                              "fail": len(cov_bad)}
    if cov_bad:
        fails.append({"gate": "coverage_gate", "items": cov_bad[:20]})

    # ---- 时长预算（软检查，仅 warn） ----
    dur = None
    if isinstance(constraints, dict):
        dur = constraints.get("duration_min")
    if dur:
        est = sum(len(str(s.get("notes") or "")) for s in slides) / 240.0
        if est > dur:
            warns.append("预计讲稿时长 %.1f 分钟超过约束 %s 分钟" % (est, dur))

    total_checks = q_total + n_total + content * 2 + len(slides)
    metrics = {
        "quote_verifiable_rate": round(q_ok / q_total, 3) if q_total else None,
        "numeric_backed_rate": round(n_ok / n_total, 3) if n_total else None,
        "evidence_coverage_rate": round(cov_ok / content, 3) if content else None,
        "notes_qa_rate": round(notes_ok / max(1, len(slides) - roles.count("title")
                                              - roles.count("section")), 3),
        "claim_single_rate": round(claim_ok / content, 3) if content else None,
        "narrative_ok": 0 if narrative_bad else 1,
        "fails_total": sum(len(f["items"]) if isinstance(f.get("items"), list) else 1
                           for f in fails),
        "checks_total": total_checks,
    }
    verdict = "pass" if not fails else "fail"
    return {"verdict": verdict, "gates": gates, "metrics": metrics,
            "fails": fails, "warns": warns}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--source", default="/app/work/source_text.txt")
    ap.add_argument("--constraints", default="/app/work/constraints.json")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    plan = None
    try:
        plan = json.load(open(args.plan, encoding="utf-8"))
    except Exception as e:
        report = {"verdict": "fail", "fatal": "plan 不可解析: %s" % e,
                  "gates": {}, "metrics": {}}
    else:
        src = ""
        st = _state(args.source)
        if st == "ok":
            src = open(args.source, encoding="utf-8", errors="ignore").read()
        cons = None
        if _state(args.constraints) == "ok":
            try:
                cons = json.load(open(args.constraints, encoding="utf-8"))
            except Exception:
                cons = None
        report = evaluate(plan, src, cons)
        report["source_state"] = st
    if args.out:
        try:
            os.makedirs(os.path.dirname(args.out), exist_ok=True)
            json.dump(report, open(args.out, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)
        except Exception:
            pass
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        sys.exit(0)  # 所有失败路径（含 argparse error）一律退出码 0

