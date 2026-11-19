#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""strength_gate.py — 证据强度分级与措辞相称性审计（说得准）

强度分级口径（写入 report 的 rubric，评分器可核对）：
  A：多篇一致 / 指南或共识文件支撑
  B：单项原始研究（样本量、设计在 support_scope 注明）
  C：综述转述 / 二手证据
  D：预印本、仅摘要、证据缺失或 match=none
措辞相称规则（机械可判定）：
  R1 强断言词（证实/证明/显著…）× 证据等级 C/D → overclaim
  R2 相关性表述 × 因果词（导致/因此/由于/使得）→ causal_overreach
  R3 全称词（所有/总是/必然…）→ overgeneralization
  R4 无限定语的解释性论断 → needs_hedge
  R5 强证据(A/B)却过度弱化（可能与/或许）× 数值结论 → underclaim（双向把关）
输出 strength_report.json：逐条 grade/flags/suggestion + 汇总计数 + verdict。
退出码恒为 0；verdict 照实写 JSON，不以退出码表达成败。
"""
import argparse
import json
import os
import sys

STRONG_WORDS = ["证实", "证明", "确立", "首次发现", "显著", "明确表明", "毫无疑问"]
CAUSAL_WORDS = ["导致", "因此", "由于", "使得", "造成", "归因于", "证明其"]
UNIVERSAL_WORDS = ["所有", "总是", "必然", "唯一", "从未", "永远"]
HEDGE_WORDS = ["可能", "或许", "提示", "似乎", "倾向于", "推测"]
TYPE_GRADE = {"指南": "A", "共识": "A", "原始研究": "B", "综述": "C",
              "预印本": "D", "review": "C", "guideline": "A", "preprint": "D"}

RUBRIC = {
    "A": "多篇一致/指南共识支撑；可用『证实/确立』级措辞",
    "B": "单项原始研究；可用『表明/显示』，不得写『证实』",
    "C": "综述转述/二手证据；应写『有综述提示/已有总结认为』",
    "D": "预印本/仅摘要/证据缺失；必须带限定语，禁强断言",
}


def load_jsonl(p):
    rows = []
    if p and os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            rows.append(json.loads(line))
                        except Exception:
                            pass
        except Exception:
            pass
    return rows



class _ArgParser(argparse.ArgumentParser):
    """参数错误也退出码 0：结论写 JSON，不以退出码表达成败（硬约束）。"""
    def error(self, message):
        print(json.dumps({"ok": False, "error": "argparse: %s" % message,
                          "note": "参数错误照实记录，退出码 0"}, ensure_ascii=False))
        self.exit(0)

def grade_of(ev):
    if not ev or ev.get("match") != "exact":
        return "D"
    return TYPE_GRADE.get(str(ev.get("source_type") or ""), "B")


def audit_claim(claim, ev):
    text = str(claim.get("text") or "")
    grade = grade_of(ev)
    flags = []
    strong = any(w in text for w in STRONG_WORDS)
    causal = any(w in text for w in CAUSAL_WORDS)
    universal = any(w in text for w in UNIVERSAL_WORDS)
    hedged = any(w in text for w in HEDGE_WORDS) or bool(claim.get("hedged"))
    correlational = any(w in text for w in ["相关", "关联", "伴随", "association"])

    if strong and grade in ("C", "D"):
        flags.append("overclaim")
    if correlational and causal:
        flags.append("causal_overreach")
    if universal:
        flags.append("overgeneralization")
    if grade == "D" and not hedged:
        flags.append("needs_hedge")
    if claim.get("type") == "interpretive" and not hedged:
        flags.append("needs_hedge")
    if grade in ("A", "B") and hedged and claim.get("type") == "numeric":
        flags.append("underclaim")
    suggestion = {
        "overclaim": "改为与等级相称的措辞（B→『结果表明』；C/D→『有研究提示』）",
        "causal_overreach": "相关性证据不得写因果：改为『与…相关/可能介导』",
        "overgeneralization": "限定适用范围：『在本次队列中/在 XX 条件下』",
        "needs_hedge": "加限定语：样本/人群/机制未明处用『可能/提示/有待』",
        "underclaim": "强证据不必过度弱化，可直接『结果表明』并保留边界说明",
    }
    return {"claim_id": claim.get("claim_id"), "grade": grade,
            "flags": flags, "suggestions": [suggestion[f] for f in flags]}


def main():
    ap = _ArgParser()
    ap.add_argument("--claims", default="/app/work/claims.jsonl")
    ap.add_argument("--evidence-table", default="/app/work/evidence_table.jsonl")
    ap.add_argument("--out", default="/app/output/strength_report.json")
    args = ap.parse_args()

    try:
        claims = load_jsonl(args.claims)
        evs = {r.get("claim_id"): r for r in load_jsonl(args.evidence_table)
               if isinstance(r, dict)}
        if not claims:
            print(json.dumps({"ok": False, "violations": 0,
                              "note": "claims 为空，跳过强度审计"}, ensure_ascii=False))
            return 0
        rows = [audit_claim(c, evs.get(c.get("claim_id"))) for c in claims]
        violations = sum(1 for r in rows if r["flags"])
        report = {
            "ok": True,
            "rubric": RUBRIC,
            "rules": ["R1 强断言×C/D证据=overclaim", "R2 相关×因果词=causal_overreach",
                      "R3 全称词=overgeneralization", "R4 D级/解释性未加限定=needs_hedge",
                      "R5 强证据过度弱化=underclaim"],
            "claims_total": len(claims),
            "grade_counts": {g: sum(1 for r in rows if r["grade"] == g)
                             for g in ("A", "B", "C", "D")},
            "violation_counts": {f: sum(1 for r in rows if f in r["flags"])
                                 for f in ("overclaim", "causal_overreach",
                                           "overgeneralization", "needs_hedge",
                                           "underclaim")},
            "violations": violations,
            "verdict": "fail" if violations else "pass",
            "results": rows,
        }
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        json.dump(report, open(args.out, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print(json.dumps({"ok": True, "violations": violations,
                          "verdict": report["verdict"],
                          "grade_counts": report["grade_counts"],
                          "out": args.out}, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e),
                          "note": "强度审计失败不阻断，退出码 0"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
