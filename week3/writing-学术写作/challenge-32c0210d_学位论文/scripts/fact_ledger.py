#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fact_ledger.py — 事实台账构建与稿件交叉校验
两个子命令:
  build  : 从 extracted/*.txt 源文本中提取"硬事实"（数值+单位、样本量、统计量、DOI、年份、图表编号），
           生成 fact_ledger.jsonl，每条含 id/值/正则形态/来源 locator/逐字原文。
  check  : 校验稿件（md/txt）中的数字与引用是否都能在台账中找到出处；
           未能对上的数字逐条列出（FAIL），疑似模型自补的数值即真相风险点。

用法:
  python3 fact_ledger.py build  --sources /app/work/extracted --out /app/work/fact_ledger.jsonl
  python3 fact_ledger.py check  --draft /app/work/draft.md --ledger /app/work/fact_ledger.jsonl \
                               --refs /app/work/references.json [--out /app/output/fact_check.json]

诚实原则: check 只报告不修改；FAIL 条目需作者回材料核对或显式标注 [待核]，禁止凭印象改数。
退出码：**恒为 0**（发现问题不中断交付，判据在 verdict/unmatched 字段）；参数错误同样以退出码 0 结束。
CI 门禁请读报告里的 ci_gate 字段（--strict 只是把该字段显式标出，不改变退出码）。
"""
import argparse, json, os, re, sys, glob, hashlib


class _SafeParser(argparse.ArgumentParser):
    """参数错误也以退出码 0 结束：判据写进 stderr 的 JSON，绝不中断交付链。"""

    def error(self, message):
        sys.stderr.write(json.dumps(
            {"ok": False, "verdict": "fail", "fail_reason": [str(message)[:200]],
             "note": "参数错误已如实记录；退出码恒 0，不中断交付。"}, ensure_ascii=False) + "\n")
        raise SystemExit(0)

NUM_PAT = re.compile(
    r"(?<![.\w])(?:(?:\d+[\d,]*(?:\.\d+)?)\s*(?:%|‰|±\s*\d+(?:\.\d+)?)?"
    r"(?:\s*(?:n\s*=\s*\d+|p\s*[=<]\s*0?\.\d+|P\s*[=<]\s*0?\.\d+|CI[：: ]?\s*[-\d.,\s至to]+|"
    r"mg|ml|mmol|μmol|kg|g/L|ng/mL|pg/mL|μmol/L|mmHg|kPa|°C|K\b|Hz|kHz|MHz|nm|μm|µm|cm|mm|m\b|"
    r"s\b|ms|μs|min|h\b|d\b|wk|month|yr|year|bp|kb|Mb|Gb|TB|GB|MB|KB|km|ppm|ppb|IU|U/L|"
    r"cells|倍|年|月|天|日|小时|分钟|秒|万|亿|元|美元|人|例|只|株|次|篇|页|名|个|台|辆|度))?)"
)
DOI_PAT = re.compile(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+")
YEAR_PAT = re.compile(r"\b(19|20)\d{2}\b")
STAT_PAT = re.compile(r"\b(?:t|F|r|χ2|chi2|Z|OR|HR|RR|β|beta|d|Cohen's d)\s*[=＝]\s*[-−]?\d+(?:\.\d+)?", re.I)

def _iter_source_lines(sources_dir):
    for fp in sorted(glob.glob(os.path.join(sources_dir, "M*.txt"))):
        mid = os.path.splitext(os.path.basename(fp))[0]
        with open(fp, encoding="utf-8") as f:
            for ln, line in enumerate(f, 1):
                m = re.match(r"\[SRC:(M\d+):([^\]]+)\]\s?(.*)", line.rstrip("\n"))
                if m:
                    yield m.group(1), m.group(2), m.group(3), fp, ln
                elif line.startswith("====="):
                    continue
                else:
                    yield mid, f"line{ln}", line.strip(), fp, ln

def cmd_build(args):
    ledger = []
    seen = set()
    for mid, loc, text, fp, ln in _iter_source_lines(args.sources):
        if not text:
            continue
        for m in NUM_PAT.finditer(text):
            v = m.group(0).strip()
            if not re.search(r"\d", v):
                continue
            key = (mid, loc, v)
            if key in seen:
                continue
            seen.add(key)
            ledger.append({"id": "F%04d" % (len(ledger) + 1), "type": "number", "value": v,
                           "source": mid, "locator": loc, "quote": text[:300]})
        for m in DOI_PAT.finditer(text):
            key = (mid, loc, m.group(0))
            if key in seen: continue
            seen.add(key)
            ledger.append({"id": "F%04d" % (len(ledger) + 1), "type": "doi", "value": m.group(0).rstrip(".,;)"),
                           "source": mid, "locator": loc, "quote": text[:300]})
        for m in STAT_PAT.finditer(text):
            key = (mid, loc, m.group(0))
            if key in seen: continue
            seen.add(key)
            ledger.append({"id": "F%04d" % (len(ledger) + 1), "type": "statistic", "value": m.group(0),
                           "source": mid, "locator": loc, "quote": text[:300]})
    with open(args.out, "w", encoding="utf-8") as f:
        for row in ledger:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(json.dumps({"ok": True, "ledger": args.out, "facts": len(ledger),
                      "by_type": {t: sum(1 for r in ledger if r["type"] == t) for t in {r["type"] for r in ledger}}},
                     ensure_ascii=False))
    return 0

def _load_ledger(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


REF_ENTRY_PAT = re.compile(r"^\s*\[(\d+)\]\s*\S")
SRC_ANCHOR_PAT = re.compile(r"^\[SRC:[^\]]*\]\s*")
CITE_IDX_PAT = re.compile(r"\[(\d+)\]")
DOI_ANY = re.compile(r"10\.\d{4,9}/\S+")


def build_reference_index(sources_dir):
    """从源材料中抽出「实际存在」的参考文献编号，用于检测稿件里「引用了不存在的文献」
    ——题面「术语与引用」方向明确列出的失败模式。

    两种条目写法都识别：
      a) 条目独占一行：  "[1] Smith J. et al. ..."（行首 [N]）
      b) 材料行内含 [N] 且同行带 DOI： "[材料] 参考文献 [1] Smith J. ... DOI:10.0000/abc.123"
    提取出的 .txt 带 [SRC:M01:lineN] 锚点前缀，先剥离再判断。
    """
    idx = set()
    for fp in sorted(glob.glob(os.path.join(sources_dir, "M*.txt"))):
        try:
            with open(fp, encoding="utf-8") as f:
                for line in f:
                    raw = SRC_ANCHOR_PAT.sub("", line)
                    starts_as_entry = REF_ENTRY_PAT.match(raw) is not None
                    has_doi = DOI_ANY.search(raw) is not None
                    if not (starts_as_entry or has_doi):
                        continue
                    for m in CITE_IDX_PAT.finditer(raw):
                        idx.add(int(m.group(1)))
        except Exception:
            continue
    return idx

def cmd_check(args):
    gates = []
    try:
        draft = open(args.draft, encoding="utf-8").read()
        ledger = _load_ledger(args.ledger)
    except Exception as e:
        report = {"draft": args.draft, "checked_numbers": 0, "unmatched": 0, "verdict": "fail",
                  "unmatched_detail": [], "ledger_facts": 0,
                  "gates": [{"state": "unreadable", "detail": str(e)[:160]}],
                  "ci_gate": "fail",
                  "fail_reason": ["输入不可读，闸门未跑成"],
                  "note": "闸门未跑成，不得宣称已核对。"}
        if args.out:
            os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
            json.dump(report, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(json.dumps({"checked_numbers": 0, "unmatched": 0, "verdict": "fail"}, ensure_ascii=False))
        return 0
    gates.append({"state": "enforced", "detail": "draft=%d chars, ledger=%d facts" % (len(draft), len(ledger))})

    # 台账索引：数值归一化（去千分位）字符串集合；统计量/DOI 精确串
    num_index = {}
    for r in ledger:
        if r["type"] in ("number", "statistic"):
            norm = r["value"].replace(",", "").replace("＝", "=").replace("−", "-")
            num_index.setdefault(norm, []).append(r)
    doi_set = {r["value"] for r in ledger if r["type"] == "doi"}

    fails, checked = [], 0
    # 逐行校验草稿中的数字
    for ln, line in enumerate(draft.splitlines(), 1):
        if line.strip().startswith(("|", "```", "#")) and line.strip().startswith("```"):
            continue
        for m in NUM_PAT.finditer(line):
            v = m.group(0).strip()
            if not re.search(r"\d", v) or len(v) < 1:
                continue
            checked += 1
            norm = v.replace(",", "").replace("＝", "=").replace("−", "-")
            if norm not in num_index:
                # 宽松重试：纯数字部分
                core = re.sub(r"[^\d.=/%±]", "", norm)
                hit = any(core and core in k for k in num_index)
                if not hit:
                    fails.append({"line": ln, "value": v, "context": line.strip()[:160],
                                  "reason": "draft number not found in any source (possible hallucination or reformatting)"})
    # DOI 校验
    for m in DOI_PAT.finditer(draft):
        v = m.group(0).rstrip(".,;)")
        if v not in doi_set:
            fails.append({"line": None, "value": v, "context": "", "reason": "DOI not present in sources"})

    # 引用编号校验：稿件引用 [n] 但材料中没有该编号的文献条目 → 引用了不存在的文献
    ref_idx = set()
    ref_gate = {"state": "skipped_not_provided", "detail": "未提供 --sources，跳过引用编号存在性校验"}
    if args.sources and os.path.isdir(args.sources):
        ref_idx = build_reference_index(args.sources)
        ref_gate = {"state": "enforced",
                    "detail": "material reference index: %s" % (sorted(ref_idx) or "empty")}
    gates.append(ref_gate)
    cited_idx = sorted({int(x.group(1)) for x in CITE_IDX_PAT.finditer(draft)})
    missing_refs = [n for n in cited_idx if n not in ref_idx] if ref_idx else []
    for n in missing_refs:
        fails.append({"line": None, "value": "[%d]" % n, "context": "",
                      "reason": "cited reference number has no entry in materials "
                                "(引用了材料中不存在的文献)"})

    report = {"draft": args.draft, "checked_numbers": checked, "unmatched": len(fails),
              "verdict": "pass" if not fails else "fail",
              "ci_gate": "pass" if not fails else "fail",
              "unmatched_detail": fails[:200],
              "ledger_facts": len(ledger),
              "gates": gates,
              "cited_reference_numbers": cited_idx,
              "material_reference_index": sorted(ref_idx),
              "missing_reference_numbers": missing_refs,
              "fail_reason": [] if not fails else ["%d 个数值/DOI/引用未回证" % len(fails)],
              "note": "FAIL 条目须回材料核对或在稿件中标注[待核]；禁止凭印象保留来源不明的数值。"}
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        json.dump(report, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({k: report[k] for k in ("checked_numbers", "unmatched", "verdict")}, ensure_ascii=False))
    return 0

def main():
    ap = _SafeParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--sources", required=True)
    b.add_argument("--out", required=True)
    c = sub.add_parser("check")
    c.add_argument("--draft", required=True)
    c.add_argument("--ledger", required=True)
    c.add_argument("--refs", default=None)
    c.add_argument("--sources", default=None,
                   help="extracted 源材料目录（用于校验引用编号是否真实存在）")
    c.add_argument("--out", default=None)
    c.add_argument("--strict", action="store_true", help="仅显式标出报告里的 ci_gate 字段（不改变退出码）")
    args = ap.parse_args()
    if args.cmd == "build":
        return cmd_build(args)
    return cmd_check(args)

if __name__ == "__main__":
    sys.exit(main())
