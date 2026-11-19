#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fact_ledger.py — 事实台账构建与稿件交叉校验（开题版）
两个子命令:
  build : 从 extracted/*.txt 源文本提取"硬事实"（数值+单位、统计量、DOI、年份），
          生成 fact_ledger.jsonl，每条含 id/值/来源 locator/逐字原文。
  check : 校验稿件中的数字与 DOI 是否可回溯到来源或计划声明；
          --allow 传入 plan.jsonl/milestones.jsonl/risk_table.jsonl 等
          计划类文件，其中声明的数字（周期/样本/指标）计入白名单——
          开题报告里的计划数字不是幻觉，不能误报。

诚实原则: check 只报告不修改；FAIL 条目须回材料核对或稿件标 [待核]。
容错: 任何脏行/缺文件/空台账都不崩溃——verdict 分别为 pass/fail/skipped/error。
"""
import argparse, glob, json, os, re, sys

NUM_PAT = re.compile(
    r"(?<![.\w])(?:(?:\d+[\d,]*(?:\.\d+)?)\s*(?:%|‰|±\s*\d+(?:\.\d+)?)?"
    r"(?:\s*(?:n\s*=\s*\d+|p\s*[=<]\s*0?\.\d+|P\s*[=<]\s*0?\.\d+|CI[：: ]?\s*[-\d.,\s至to]+|"
    r"mg|ml|mmol|μmol|kg|g/L|ng/mL|pg/mL|μmol/L|mmHg|kPa|°C|K\b|Hz|kHz|MHz|nm|μm|µm|cm|mm|m\b|"
    r"s\b|ms|μs|min|h\b|d\b|wk|month|yr|year|bp|kb|Mb|Gb|TB|GB|MB|KB|km|ppm|ppb|IU|U/L|"
    r"cells|倍|年|月|天|日|小时|分钟|秒|万|亿|元|美元|万元|人|例|只|株|次|篇|页|名|个|台|辆|度))?)"
)
DOI_PAT = re.compile(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+")
STAT_PAT = re.compile(r"\b(?:t|F|r|χ2|chi2|Z|OR|HR|RR|β|beta|d|Cohen's d)\s*[=＝]\s*[-−]?\d+(?:\.\d+)?", re.I)


def _norm(s):
    return str(s).replace(",", "").replace("＝", "=").replace("−", "-").strip()


def _core(s):
    return re.sub(r"[^\d.=/%±]", "", _norm(s))


def _iter_source_lines(sources_dir):
    for fp in sorted(glob.glob(os.path.join(sources_dir, "M*.txt"))):
        mid = os.path.splitext(os.path.basename(fp))[0]
        try:
            with open(fp, encoding="utf-8", errors="ignore") as f:
                for ln, line in enumerate(f, 1):
                    m = re.match(r"\[SRC:(M\d+):([^\]]+)\]\s?(.*)", line.rstrip("\n"))
                    if m:
                        yield m.group(1), m.group(2), m.group(3)
                    elif line.startswith("====="):
                        continue
                    else:
                        yield mid, "line%d" % ln, line.strip()
        except Exception:
            continue


def cmd_build(args):
    ledger, seen = [], set()
    try:
        rows = list(_iter_source_lines(args.sources))
    except Exception as e:
        rows = []
        print(json.dumps({"ok": False, "note": "sources 不可读: %s" % str(e)[:150]}, ensure_ascii=False))
    for mid, loc, text in rows:
        if not text:
            continue
        for pat, typ in ((NUM_PAT, "number"), (DOI_PAT, "doi"), (STAT_PAT, "statistic")):
            for m in pat.finditer(text):
                v = m.group(0).strip().rstrip(".,;)")
                if typ == "number" and not re.search(r"\d", v):
                    continue
                key = (mid, loc, typ, v)
                if key in seen:
                    continue
                seen.add(key)
                ledger.append({"id": "F%04d" % (len(ledger) + 1), "type": typ, "value": v,
                               "source": mid, "locator": loc, "quote": text[:300]})
    try:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            for row in ledger:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)[:200]}, ensure_ascii=False))
        return 0
    print(json.dumps({"ok": True, "ledger": args.out, "facts": len(ledger),
                      "by_type": {t: sum(1 for r in ledger if r["type"] == t)
                                  for t in {r["type"] for r in ledger}}}, ensure_ascii=False))
    return 0


def _load_ledger(path):
    rows = []
    if not path or not os.path.exists(path):
        return rows
    with open(path, encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows


def _allow_numbers(allow_files):
    """计划类文件中声明的数字白名单（周期/样本/指标/经费不是幻觉）。"""
    allowed = set()
    for fp in allow_files or []:
        if not fp or not os.path.exists(fp):
            continue
        try:
            raw = open(fp, encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        for m in re.finditer(r"\d+[\d,]*(?:\.\d+)?", raw):
            allowed.add(_norm(m.group(0)))
    return allowed


def cmd_check(args):
    report = {"draft": args.draft, "ledger": args.ledger, "checked_numbers": 0,
              "unmatched": 0, "verdict": "error", "unmatched_detail": [],
              "note": "FAIL 条目须回材料核对或稿件标注[待核]；计划数字经 --allow 白名单放行。"}
    try:
        if not os.path.exists(args.draft):
            report["verdict"] = "skipped"
            report["note"] = "draft 不存在: %s" % args.draft
        elif not args.ledger or not os.path.exists(args.ledger) or os.path.getsize(args.ledger) == 0:
            report["verdict"] = "skipped"
            report["note"] = "台账缺失或为空——无来源可对照，不判 fail，如实登记 skipped"
        else:
            ledger = _load_ledger(args.ledger)
            num_index, doi_set = {}, set()
            for r in ledger:
                if r.get("type") in ("number", "statistic"):
                    num_index.setdefault(_norm(r.get("value")), []).append(r)
                elif r.get("type") == "doi":
                    doi_set.add(r.get("value"))
            allowed = _allow_numbers(args.allow)
            draft = open(args.draft, encoding="utf-8", errors="ignore").read()
            fails, checked, refs_skipped = [], 0, 0
            for ln, line in enumerate(draft.splitlines(), 1):
                s = line.strip()
                if s.startswith(("|", "#", "```", ">")):
                    continue
                if re.match(r"^\[\d+\]", s) or s.startswith(("- [", "* [")):
                    refs_skipped += 1  # 参考文献条目：年份/页码来自文献本身，不入数值校验
                    continue
                for m in NUM_PAT.finditer(line):
                    v = m.group(0).strip()
                    if not re.search(r"\d", v):
                        continue
                    checked += 1
                    n = _norm(v)
                    if n in num_index or n in allowed:
                        continue
                    core = _core(v)
                    if core and any(core in k for k in list(num_index) + list(allowed)):
                        continue
                    fails.append({"line": ln, "value": v, "context": s[:160],
                                  "reason": "draft number not found in sources or plan declarations"})
            for m in DOI_PAT.finditer(draft):
                v = m.group(0).rstrip(".,;)")
                if v not in doi_set:
                    fails.append({"line": None, "value": v, "context": "",
                                  "reason": "DOI not present in sources"})
            report.update(checked_numbers=checked, unmatched=len(fails),
                          unmatched_detail=fails[:200],
                          references_skipped=refs_skipped,
                          verdict="pass" if not fails else "fail",
                          ledger_facts=len(ledger), plan_allowlist=len(allowed))
    except Exception as e:
        report["verdict"] = "error"
        report["error"] = str(e)[:300]
    if args.out:
        try:
            os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
            json.dump(report, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        except Exception:
            pass
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
    c.add_argument("--allow", nargs="*", default=[], help="计划类文件（plan/milestones/risk jsonl），数字进白名单")
    c.add_argument("--out", default=None)
    args = ap.parse_args()
    return cmd_build(args) if args.cmd == "build" else cmd_check(args)


if __name__ == "__main__":
    sys.exit(main())
