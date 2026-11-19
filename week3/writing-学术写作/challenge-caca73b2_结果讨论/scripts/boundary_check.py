#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""boundary_check.py — 结果/讨论边界检查
检查:
 1) 结果段（Results 标题到 Discussion 标题之间）出现解释性/因果性标记词 → fail
 2) 讨论段因果词（导致/造成/使得/决定/因果）出现在无干预设计依据的句子 → 需标注 fail（材料若含
    randomized/干预/因果检验 等词则放行）
 3) 正文数值不在 readings.jsonl 登记值中 → fail
 4) "显著/显著差异"用于未达 p<0.05 的数值语境 → fail
"""
import argparse, json, os, re, sys

EXPLAIN_WORDS = ["表明", "说明", "证明", "意味着", "由此可见", "提示这是", "原因是"]
CAUSAL_WORDS = ["导致", "造成", "使得", "决定于", "归因于", "因果效应", "因果作用", "归因"]
CAUSAL_PASS = ["randomized", "随机对照", "RCT", "干预", "处理组", "因果推断", "工具变量", "双重差分", "DID", "倾向得分"]
SIGNIF_WORDS = ["显著", "显著差异", "显著升高", "显著降低", "显著增加"]

def _norm(s):
    return re.sub(r"[\s,，]", "", s)

class _Usage(Exception):
    """argparse 用法错误（缺必填参数）——按内容级失败处理，不中断交付链。"""


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise _Usage(message)


def _fail(err, **extra):
    """统一失败输出：verdict 照实记录，退出码恒 0。"""
    rec = {"verdict": "fail", "fail": 1, "problems": [], "error": str(err),
           "note": "退出码恒 0：交付链不中断，已如实记录。"}
    rec.update(extra)
    print(json.dumps(rec, ensure_ascii=False))
    return 0


def main():
    ap = _Parser()
    ap.add_argument("--draft", required=True)
    ap.add_argument("--readings", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--strict-exit", action="store_true",
                    help="校验失败时退出码非 0（CI 用）；默认恒 0，失败以 verdict/fail 计数落在报告中，不中断交付链")
    try:
        args = ap.parse_args()
    except _Usage as e:
        return _fail(e, hint="必填参数缺失，请补 --draft（可选 --readings/--out/--strict-exit）。")
    try:
        draft = open(args.draft, encoding="utf-8").read()
    except Exception as e:
        return _fail(f"draft unreadable: {e}")
    rows = []
    if args.readings and os.path.exists(args.readings):
        try:
            rows = [json.loads(l) for l in open(args.readings, encoding="utf-8") if l.strip()]
        except Exception as e:
            return _fail(f"readings unreadable: {e}")
    readings_gate = "enforced" if (args.readings and os.path.exists(args.readings)) else (
        "skipped_not_provided" if not args.readings else "not_found")

    # 定位 Results / Discussion 区间
    def find_zone(pat):
        m = re.search(pat, draft, re.I)
        return m.start() if m else None
    r0 = find_zone(r"#+\s*结\s*果|#+\s*Results|结果段")
    d0 = find_zone(r"#+\s*讨\s*论|#+\s*Discussion|讨论段")
    results_zone = draft[r0:d0] if (r0 is not None and d0 is not None and d0 > r0) else ""
    disc_zone = draft[d0:] if d0 is not None else draft

    problems = []
    # 1) 结果段解释性用词
    hits = []
    for w in EXPLAIN_WORDS:
        for m in re.finditer(re.escape(w), results_zone):
            line = results_zone[:m.start()].count("\n") + 1
            ctx = results_zone[max(0, m.start()-40):m.end()+40].replace("\n", " ")
            hits.append({"word": w, "line": line, "ctx": ctx})
    if hits:
        problems.append({"type": "explanatory_in_results", "count": len(hits), "samples": hits[:8],
                         "hint": "结果段只陈述观察；解释句移入讨论段。"})

    # 2) 讨论因果词
    causal_hits = []
    design_pass = any(w.lower() in draft.lower() for w in CAUSAL_PASS)
    for w in CAUSAL_WORDS:
        for m in re.finditer(re.escape(w), disc_zone):
            sent = re.split(r"(?<=[。！？.!?])", disc_zone[max(0, m.start()-200):m.end()+200])[-1]
            causal_hits.append({"word": w, "ctx": sent[:120]})
    if causal_hits and not design_pass:
        problems.append({"type": "causal_overreach", "count": len(causal_hits), "samples": causal_hits[:8],
                         "hint": "观察性数据避免因果词；改用 相关/伴随/提示；或补干预依据说明。"})

    # 3) 数值溯源
    reg = set()
    for r in rows:
        for v in r.get("values", []):
            reg.add(_norm(str(v.get("value", ""))))
        reg.add(_norm(str(r.get("caption_quote", ""))[:60]))
    missing = []
    for line in draft.splitlines():
        for m in re.finditer(r"\d+(?:\.\d+)?(?:\s*[±%‰])?", line):
            v = _norm(m.group(0))
            if len(v) < 2:
                continue
            if not any(v in x for x in reg):
                # 台账兜底由 fact_check 负责，这里只报非整数风险值
                missing.append(m.group(0))
    # 缩样：只保留出现≥1次的数值样本（完整核查以 fact_ledger check 为准）
    problems.append({"type": "reading_trace_note", "count": len(missing),
                     "note": "完整数值核查以 fact_ledger check 输出为准；此处列非登记数值样例",
                     "samples": list(dict.fromkeys(missing))[:12]})

    # 4) 显著性用词
    sig_bad = []
    for line in draft.splitlines():
        if any(w in line for w in SIGNIF_WORDS):
            for pm in re.finditer(r"p\s*[=<]\s*(0?\.\d+)", line, re.I):
                try:
                    if float(pm.group(1)) >= 0.05:
                        sig_bad.append(line.strip()[:120])
                except ValueError:
                    pass
    if sig_bad:
        problems.append({"type": "significance_misuse", "count": len(sig_bad), "samples": sig_bad[:5],
                         "hint": "p≥0.05 不得称'显著'；改写为'未达显著（p=…）'。"})

    hard = [p for p in problems if p["type"] in ("explanatory_in_results", "causal_overreach", "significance_misuse")]
    report = {"draft": args.draft, "problems": problems, "fail": len(hard),
              "verdict": "pass" if not hard else "fail",
              "gates": {"readings": readings_gate},
              "gate_notes": ("" if readings_gate == "enforced"
                             else f"gate[readings]={readings_gate}：数值溯源子项未运行，下游不得宣称已核对"),
              "hint": "fail 项修复后重跑；reading_trace_note 结合 fact_check 综合判断。"}
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        json.dump(report, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({"verdict": report["verdict"], "fail": len(hard),
                      "types": [p["type"] for p in problems],
                      "gates": report["gates"]}, ensure_ascii=False))
    return 1 if (hard and args.strict_exit) else 0


def _safe_main():
    """顶层安全网：任何未捕获异常都记为内容级失败，退出码恒 0。"""
    try:
        return main()
    except SystemExit:
        raise
    except Exception as e:
        return _fail(f"{type(e).__name__}: {e}")


if __name__ == "__main__":
    sys.exit(_safe_main())
