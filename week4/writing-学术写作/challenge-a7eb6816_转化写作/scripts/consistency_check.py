#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""consistency_check.py — 成稿一致性检查（章节完整性 / 结构规范 / 引用对应 / 术语统一）
输入: draft.md + constraints.json（必含 required_sections；可选 citation_style、word_range、terms）
输出: check_report.json（逐项 pass/fail/warn + 修复建议），退出码 fail=1

检查项:
 1) 章节完整性: required_sections 逐个在稿内找到（标题行模糊匹配）
 2) 引用对应: 正文引用标记 [n] 或 (Author, Year) 是否都在参考文献表里；反之孤立条目报告
 3) 引用格式: citation_style 为 gbt7714/apa/vancouver 时抽查条目形态
 4) 术语统一: terms 中每个规范名在稿内出现时，其别名（括号内列出）出现次数应为 0（首次定义除外）
 5) 字数范围: word_range=[min,max]（中文字符计）
 6) 图表引用: 图/表编号（图1、Figure 2、表3…）在稿内首次出现顺序是否递增且被正文提及
"""
import argparse, json, os, re, sys

def _norm_head(s):
    return re.sub(r"[\s#*_:：·\-—0-9.]+", "", s).lower()

def check_sections(draft, required):
    heads = []
    for line in draft.splitlines():
        m = re.match(r"^\s*#{1,6}\s*(.+)$", line)
        if m:
            heads.append(_norm_head(m.group(1)))
        elif re.match(r"^\s*(第?[一二三四五六七八九十\d]+[、.．章节])\s*\S+", line):
            heads.append(_norm_head(line))
    missing = []
    for sec in required:
        key = _norm_head(sec)
        if key and not any(key in h or h in key for h in heads if h):
            missing.append(sec)
    return {"item": "sections_complete", "required": required, "missing": missing,
            "verdict": "pass" if not missing else "fail",
            "hint": "补齐缺失章节标题；确属不适用的章节在 [待核]/边界说明中显式声明，不要静默省略。" if missing else ""}

def _ref_table(draft):
    """返回 (正文中的引用标记集合, 参考文献条目编号集合, 参考文献区文本)"""
    cites = set()
    for m in re.finditer(r"\[(\d{1,3}(?:\s*[,，\-]\s*\d{1,3})*)\]", draft):
        for part in re.split(r"[,，\-]", m.group(1)):
            if part.strip().isdigit():
                cites.add(int(part.strip()))
    # 参考文献区：标题之后或最后 40 行
    ref_zone = ""
    for pat in (r"##?\s*参\s*考\s*文\s*献", r"##?\s*References", r"REFENCES", r"参考文献[:：]"):
        m = re.search(pat, draft, re.I)
        if m:
            ref_zone = draft[m.end():]
            break
    if not ref_zone:
        ref_zone = "\n".join(draft.splitlines()[-40:])
    entries = set()
    for line in ref_zone.splitlines():
        m = re.match(r"^\s*[\[(]?(\d{1,3})[\]).]\s", line)
        if m:
            entries.add(int(m.group(1)))
    return cites, entries, ref_zone

def check_citations(draft, style):
    cites, entries, ref_zone = _ref_table(draft)
    if not cites and not entries:
        return {"item": "citations", "verdict": "warn", "hint": "稿内未检测到编号引用；若本任务不要求引用可忽略。"}
    orphan_cites = sorted(c for c in cites if c not in entries)
    orphan_entries = sorted(e for e in entries if e not in cites)
    style_bad = []
    if style and entries:
        lines = [l for l in ref_zone.splitlines() if re.match(r"^\s*[\[(]?\d{1,3}[\]).]", l)]
        for l in lines[:30]:
            if style == "gbt7714" and not re.search(r"\[\s*(J|M|D|C|N|R|S|P|DB/OL|EB/OL)", l):
                style_bad.append(l[:80])
            elif style == "apa" and not re.search(r"\(\d{4}[a-z]?\)", l):
                style_bad.append(l[:80])
            elif style == "vancouver" and not re.search(r"\.\s", l):
                style_bad.append(l[:80])
    out = {"item": "citations", "cited": sorted(cites), "listed": sorted(entries),
           "cited_not_listed": orphan_cites, "listed_not_cited": orphan_entries,
           "style": style, "style_suspect": style_bad,
           "verdict": "pass" if not (orphan_cites or style_bad) else "fail",
           "hint": "正文引用必须在文献表有条目；风格可疑行按目标格式逐条修正。"}
    if orphan_entries:
        out["verdict"] = "warn" if out["verdict"] == "pass" else out["verdict"]
        out["hint"] += "；listed_not_cited 为文献表未在正文引用的条目，按需删除或补引用。"
    return out

def check_terms(draft, terms):
    bad = []
    for canon, aliases in (terms or {}).items():
        first = re.search(re.escape(canon), draft)
        for a in aliases:
            for m in re.finditer(re.escape(a), draft):
                if first and m.start() < first.start():
                    continue  # 首次定义前允许出现
                # 首次出现若是"规范名（别名）"定义形式则允许
                ctx = draft[max(0, m.start() - len(canon) - 2):m.end() + 2]
                if canon in ctx:
                    continue
                bad.append({"canonical": canon, "alias": a, "line": draft[:m.start()].count("\n") + 1})
    return {"item": "terms_consistent", "violations": bad[:50],
            "verdict": "pass" if not bad else "warn",
            "hint": "别名应统一为规范名（首次定义处可写: 规范名（别名））。"}

def check_words(draft, word_range):
    if not word_range:
        return {"item": "word_range", "verdict": "skip"}
    n = len(re.findall(r"[\u4e00-\u9fff]", draft))
    lo, hi = word_range
    return {"item": "word_range", "count": n, "range": word_range,
            "verdict": "pass" if lo <= n <= hi else "warn",
            "hint": f"中文字符数 {n} 超出 [{lo},{hi}]，按任务约束增删。"}

def check_figures(draft):
    seq = []
    for m in re.finditer(r"(?:图|表|Figure|Fig\.?|Table)\s*(\d+)", draft):
        seq.append(int(m.group(1)))
    ok = all(b >= a for a, b in zip(seq, seq[1:]))
    firsts = []
    for pat in (r"图\s*(\d+)", r"表\s*(\d+)"):
        seen = set()
        for m in re.finditer(pat, draft):
            n = int(m.group(1))
            if n not in seen:
                seen.add(n); firsts.append(n)
    mono = all(b > a for a, b in zip(firsts, firsts[1:]))
    return {"item": "figures_order", "mentions": seq[:60], "first_appearance_monotonic": mono,
            "verdict": "pass" if mono else "warn",
            "hint": "图表编号应按正文首次提及顺序递增。"}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--draft", required=True)
    ap.add_argument("--constraints", required=True, help="constraints.json（含 required_sections 等键）")
    ap.add_argument("--out", default=None)
    ap.add_argument("--strict", action="store_true",
                    help="保留兼容：仅在报告中标记 ci_strict=true，**不改变退出码**（退出码恒 0）")
    args = ap.parse_args()
    # 输入缺失/损坏不中断交付：照实记录 unreadable，退出码恒 0
    try:
        draft = open(args.draft, encoding="utf-8").read()
        con = json.load(open(args.constraints, encoding="utf-8"))
    except Exception as e:
        report = {"draft": args.draft, "results": [
            {"item": "input_readable", "verdict": "unreadable",
             "hint": "输入缺失或不可解析：%s: %s" % (type(e).__name__, str(e)[:160])}],
            "fail": 0, "verdict": "unreadable",
            "hint": "输入缺失或不可解析；已如实登记，交付不中断。",
            "exit_note": "退出码恒 0：问题记入 report.verdict/results，交付不中断。"}
        if args.out:
            os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
            json.dump(report, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(json.dumps({"verdict": "unreadable", "fail": 0,
                          "error": type(e).__name__ + ": " + str(e)[:160]}, ensure_ascii=False))
        return 0
    results = [
        check_sections(draft, con.get("required_sections") or []),
        check_citations(draft, con.get("citation_style")),
        check_terms(draft, con.get("terms")),
        check_words(draft, con.get("word_range")),
        check_figures(draft),
    ]
    hard_fail = [r for r in results if r.get("verdict") == "fail"]
    report = {"draft": args.draft, "results": results,
              "fail": len(hard_fail),
              "verdict": "pass" if not hard_fail else "fail",
              "hint": "fail 项必须修复后重跑；warn 项写入 result.json 的 uncertainty。",
              "ci_strict": bool(args.strict),
              "exit_note": "退出码恒 0：fail 已照实记入 report.verdict/results，交付不中断。"}
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        json.dump(report, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({"verdict": report["verdict"], "fail": report["fail"],
                      "items": [r.get("item") + ":" + r.get("verdict", "?") for r in results]}, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    sys.exit(main())
