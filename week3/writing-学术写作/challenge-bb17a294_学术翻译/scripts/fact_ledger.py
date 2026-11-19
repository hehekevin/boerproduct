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
"""
import argparse, json, os, re, sys, glob, hashlib

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

def _norm_value(v):
    """数值归一化：去千分位；统一全角等号/减号；支持 万/亿 ↔ thousand/million/billion 跨语向量级换算。"""
    v = (v or "").strip()
    v = v.replace(",", "").replace("＝", "=").replace("−", "-").replace("～", "~")
    v = re.sub(r"[（(].*?[)）]", "", v).strip()
    v = re.sub(r"\s*~\s*", "~", v)
    v = v.replace("（", "(").replace("）", ")")
    return v


def _scale_of(tok):
    """返回 (数值, 乘数, 量级词)；无量级词则乘数 1。"""
    t = _norm_value(tok)
    m = re.match(r"^([+-]?\d+(?:\.\d+)?)\s*(万人|亿元|万|亿|千|百万|千万|thousand|million|billion)?", t, re.I)
    if not m:
        return None, 1.0, None
    val = float(m.group(1))
    word = (m.group(2) or "").lower()
    mult = {"万": 1e4, "万人": 1e4, "亿": 1e8, "亿元": 1e8, "千": 1e3, "百万": 1e6,
            "千万": 1e7, "thousand": 1e3, "million": 1e6, "billion": 1e9}.get(word, 1.0)
    return val, mult, word


def _numeric_forms(v):
    """一个数值的所有可接受写法（含量级换算后的等价值），用于宽松匹配。"""
    val, mult, word = _scale_of(v)
    if val is None:
        return set()
    forms = set()
    for k in (1.0, 1e3, 1e4, 1e6, 1e7, 1e8, 1e9):
        scaled = val * mult / k
        if scaled and abs(scaled) >= 1:
            forms.add(("%.10g" % scaled))
            forms.add(("%.10g" % round(scaled, 6)))
    forms.add(("%.10g" % val))
    return forms


def cmd_check(args):
    draft = open(args.draft, encoding="utf-8").read()
    ledger = _load_ledger(args.ledger)

    # 台账索引：数值归一化 + 量级换算后的等价写法集合
    num_index = {}
    for r in ledger:
        if r["type"] in ("number", "statistic"):
            norm = _norm_value(r["value"])
            num_index.setdefault(norm, []).append(r)
            for f in _numeric_forms(r["value"]):
                num_index.setdefault(f, []).append(r)
    doi_set = {r["value"] for r in ledger if r["type"] == "doi"}

    fails, checked = [], 0
    # 逐行校验草稿中的数字
    for ln, line in enumerate(draft.splitlines(), 1):
        if line.strip().startswith("```"):
            continue
        for m in NUM_PAT.finditer(line):
            v = m.group(0).strip()
            if not re.search(r"\d", v) or len(v) < 1:
                continue
            checked += 1
            norm = _norm_value(v)
            if norm in num_index:
                continue
            # 宽松重试：等价量级写法
            hit = any(f in num_index for f in _numeric_forms(v))
            if not hit:
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

    report = {"draft": args.draft, "checked_numbers": checked, "unmatched": len(fails),
              "verdict": "pass" if not fails else "fail",
              "unmatched_detail": fails[:200],
              "ledger_facts": len(ledger),
              "note": "FAIL 条目须回材料核对或在稿件中标注[待核]；禁止凭印象保留来源不明的数值。"
                      "本脚本失败路径 exit 0，verdict 照实记录，不中断交付。"}
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        json.dump(report, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({k: report[k] for k in ("checked_numbers", "unmatched", "verdict")}, ensure_ascii=False))
    return 0

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--sources", required=True)
    b.add_argument("--out", required=True)
    c = sub.add_parser("check")
    c.add_argument("--draft", required=True)
    c.add_argument("--ledger", required=True)
    c.add_argument("--refs", default=None)
    c.add_argument("--out", default=None)
    args = ap.parse_args()
    if args.cmd == "build":
        return cmd_build(args)
    return cmd_check(args)

if __name__ == "__main__":
    sys.exit(main())
