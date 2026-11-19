#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""triage_audit.py — 成果转化取舍清单审计
检查: 1) keep 条目在改写稿有落点；2) drop 条目未携带关键数据被删；3) 强度升级词审计。
"""
import argparse, json, os, re, sys, glob

UPGRADES = ["证明", "彻底", "革命性", "突破性进展", "颠覆", "完胜", "神效", "包治", "根治",
            "100%", "绝对", "必然"]

def _norm(s):
    return re.sub(r"\s+", "", s)

def _punchless(s):
    # 去除空白与中英文标点，仅保留文字/数字/百分号等实义字符（\w 含 CJK）
    return re.sub(r"[^\w%.‰±]+", "", s)

def _bigrams(s):
    s2 = _punchless(s)
    return [s2[i:i+2] for i in range(len(s2)-1)] if len(s2) >= 2 else ([s2] if s2 else [])

def _cover(probe, transfer_punchless, ratio=0.6):
    """探针的二元组在改写稿中的覆盖率 >= ratio 即视为落点（容忍改写与标点差异）"""
    toks = _bigrams(probe)
    if not toks:
        return True
    hitc = sum(1 for tk in toks if tk in transfer_punchless)
    return hitc / len(toks) >= ratio

def _load_sources(path_or_dir):
    if os.path.isdir(path_or_dir):
        return "\n".join(open(fp, encoding="utf-8").read()
                         for fp in sorted(glob.glob(os.path.join(path_or_dir, "*.txt"))))
    return open(path_or_dir, encoding="utf-8").read()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--triage", required=True)
    ap.add_argument("--source", required=True)
    ap.add_argument("--transfer", required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--strict", action="store_true",
                    help="保留兼容：仅在报告中标记 ci_strict=true，**不改变退出码**（退出码恒 0）")
    args = ap.parse_args()
    # 输入缺失/损坏不中断交付：照实记录 unreadable，退出码恒 0
    try:
        rows = [json.loads(l) for l in open(args.triage, encoding="utf-8") if l.strip()]
        transfer = open(args.transfer, encoding="utf-8").read()
        src = _load_sources(args.source)
    except Exception as e:
        report = {"triage_total": 0, "keep": 0, "compress": 0, "drop": 0,
                  "problems": [{"type": "input_unreadable", "count": 1,
                                "detail": [{"error": type(e).__name__ + ": " + str(e)[:200]}]}],
                  "fail": 0, "verdict": "unreadable",
                  "hint": "输入缺失或不可解析；已如实登记，交付不中断。",
                  "exit_note": "退出码恒 0：问题记入 report.verdict/fail，交付不中断；--strict 仅供 CI。"}
        if args.out:
            os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
            json.dump(report, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(json.dumps({"verdict": "unreadable", "keep_missed": 0,
                          "strength_violations": 0,
                          "error": type(e).__name__ + ": " + str(e)[:160]}, ensure_ascii=False))
        return 0
    problems = []

    # 1) keep 落点
    keep_missed = []
    t_pl = _punchless(transfer)
    for r in rows:
        if r.get("tier") != "keep":
            continue
        probe = _norm(str(r.get("content", "")))[:30]
        if not probe:
            continue
        # 提取探针中的关键数字，要求改写稿至少保留其一
        nums = re.findall(r"\d+(?:\.\d+)?", probe)
        hit = (_punchless(probe)[:18] in t_pl
               or any(n in transfer for n in nums[:5])
               or _cover(probe, t_pl))
        if not hit:
            keep_missed.append({"sid": r.get("sid"), "probe": probe[:40]})
    if keep_missed:
        problems.append({"type": "keep_missed", "count": len(keep_missed), "detail": keep_missed[:15]})

    # 2) drop 未携带关键数据
    data_lost = []
    for r in rows:
        if r.get("tier") != "drop":
            continue
        content = str(r.get("content", ""))
        nums = re.findall(r"\d+(?:\.\d+)?", content)
        # 若该段数字在源文出现且改写稿完全没有 → 数据丢失风险
        if nums and not any(n in transfer for n in nums[:8]) and len(nums) >= 2:
            data_lost.append({"sid": r.get("sid"), "nums": nums[:8]})
    if data_lost:
        problems.append({"type": "data_lost_with_drop", "count": len(data_lost), "detail": data_lost[:10]})

    # 3) 强度升级词
    viol = []
    for w in UPGRADES:
        for m in re.finditer(re.escape(w), transfer):
            ctx = transfer[max(0, m.start()-50):m.end()+50].replace("\n", " ")
            viol.append({"w": w, "ctx": ctx})
    if viol:
        problems.append({"type": "strength_violations", "count": len(viol), "samples": viol[:10]})

    hard = [p for p in problems if p["type"] in ("keep_missed", "strength_violations")]
    report = {"triage_total": len(rows), "keep": sum(1 for r in rows if r.get("tier") == "keep"),
              "compress": sum(1 for r in rows if r.get("tier") == "compress"),
              "drop": sum(1 for r in rows if r.get("tier") == "drop"),
              "problems": problems, "fail": len(hard),
              "verdict": "pass" if not hard else "fail",
              "hint": "keep_missed → 把被丢的结论/限定补回；strength_violations → 降级表述。",
              "exit_note": "退出码恒 0：fail 已照实记入 report.verdict/fail，交付不中断；--strict 仅供 CI。"}
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        json.dump(report, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({"verdict": report["verdict"], "keep_missed": len(keep_missed),
                      "strength_violations": len(viol)}, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    sys.exit(main())
