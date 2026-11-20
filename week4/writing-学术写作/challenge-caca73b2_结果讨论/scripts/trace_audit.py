#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""trace_audit.py — 数值-来源核对表 + 图表交叉引用 + 讨论结论溯源审计（三项合一）
补强项:
 A) 数字-来源逐条核对表: 草稿中每个数值 → 溯源到 readings.jsonl 的图表登记值（status=matched）
    或 fact_ledger.jsonl 的源文事实（status=ledger）；都对不上 → status=unmatched（FAIL 风险点）。
    核对表整表输出，可直接嵌入 result.json 的 number_source_table 字段。
 B) 结果段交叉引用完整性: readings.jsonl 登记的每张图/表都必须在结果段被正文引用；
    结果段引用的每个图/表编号都必须在 readings 登记过。缺一边 fail。
 C) 讨论结论溯源: 讨论段中每条含结论动词的句子必须带【依据：…】内联标注（指向本研究图/表
    或文献+locator）；输出 discussion_claims 逐条表。缺标注 → fail。

用法:
  python trace_audit.py --draft /app/output/results_discussion.md \
      --readings /app/work/readings.jsonl --ledger /app/work/fact_ledger.jsonl \
      [--dclaims /app/work/dclaims.jsonl] \
      --out-table /app/work/number_source_table.json --out /app/output/trace_audit.json

容错: 任一输入缺失/损坏 → 对应检查项降级为 skipped 并如实记录，其余项照常执行，不崩溃。
诚实原则: 只报告不修改；unmatched 数值须回材料核对或标[待核]，禁止凭印象改数。
"""
import argparse, json, os, re, sys

NUM_RE = re.compile(r"(?<![\w.])(?:(?:\d+[\d,]*(?:\.\d+)?)\s*(?:%|‰|±\s*\d+(?:\.\d+)?)?(?:\s*(?:p\s*[=<]\s*0?\.\d+|n\s*=\s*\d+|CI\s*[-\d.,]+|(?:mg|ml|mmol|kg|mmHg|kPa|°C|nm|μm|cm|mm|ppm|IU|U/L|ng/mL|pg/mL|g/L|倍|年|月|天|小时|分钟|例|人|株))))?", re.I)
REF_RE = re.compile(r"(图|表|Figure|Fig\.?|Table)\s*(\d+)", re.I)
CLAIM_WORDS = ["表明", "提示", "说明", "支持", "证实", "意味着", "推测", "归因", "可能与",
               "原因", "机制", "一致", "不一致", "优于", "高于", "低于", "相关", "反映了", "归结于"]
MARK_RE = re.compile(r"【依据[：:]([^】]+)】")


def _load_jsonl(path):
    if not path or not os.path.exists(path):
        return None
    rows = []
    try:
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line:
                rows.append(json.loads(line))
        return rows
    except Exception:
        return None


def _norm(s):
    return re.sub(r"[\s,，]", "", str(s))


def _ref_key(m):
    kind = m.group(1)
    kind = "表" if kind in ("表", "Table") or kind.lower().startswith("table") else "图"
    return f"{kind}{int(m.group(2))}"


def _zones(draft):
    def find(pat):
        m = re.search(pat, draft, re.I)
        return m.start() if m else None
    r0 = find(r"#+\s*结\s*果|#+\s*Results")
    d0 = find(r"#+\s*讨\s*论|#+\s*Discussion")
    rz = draft[r0:d0] if (r0 is not None and d0 is not None and d0 > r0) else ""
    dz = draft[d0:] if d0 is not None else ""
    return rz, dz


# ---- A) 数字-来源逐条核对表 ----
def build_table(draft, readings, ledger):
    # 图表登记值索引: 归一化值 -> {"ref":…, "locator":…, "verbatim":…}
    reg, led = {}, {}
    for r in readings or []:
        loc = r.get("locator", "")
        for v in r.get("values", []):
            val = _norm(v.get("value", ""))
            if val:
                reg.setdefault(val, {"ref": r.get("ref", ""), "locator": loc,
                                     "verbatim": str(v.get("value", ""))[:80]})
    for f in ledger or []:
        val = _norm(f.get("value", ""))
        if val:
            led.setdefault(val, {"ref": f.get("source", ""), "locator": f.get("locator", ""),
                                 "verbatim": str(f.get("value", ""))[:80]})
    table, unmatched, checked = [], [], 0
    for ln, line in enumerate(draft.splitlines(), 1):
        s = line.strip()
        if s.startswith(("|", "```", "#")) and not s.startswith("#"):
            continue
        for m in NUM_RE.finditer(line):
            v = m.group(0).strip()
            if not re.search(r"\d", v):
                continue
            checked += 1
            norm = _norm(v)
            src = reg.get(norm)
            status = "matched"
            if not src:
                # 宽松重试: 去符号取数字核心做包含匹配
                core = re.sub(r"[^\d.=/%±]", "", norm)
                hit = None
                if core:
                    for k, meta in reg.items():
                        if core in k:
                            hit = meta
                            break
                if hit:
                    src = hit
                else:
                    src = led.get(norm)
                    status = "ledger" if src else "unmatched"
            row = {"line": ln, "value": v, "context": line.strip()[:100],
                   "source_ref": (src or {}).get("ref", ""), "source_locator": (src or {}).get("locator", ""),
                   "verbatim": (src or {}).get("verbatim", ""), "status": status}
            table.append(row)
            if status == "unmatched":
                unmatched.append(row)
    return {"table": table, "checked": checked, "unmatched": len(unmatched),
            "unmatched_detail": unmatched[:60]}


# ---- B) 结果段图表交叉引用完整性 ----
def crossref(results_zone, readings):
    registered = set()
    for r in readings or []:
        ref = str(r.get("ref", "")).strip()
        if ref:
            registered.add(_ref_key(re.match(REF_RE, ref) if REF_RE.search(ref) else None) if REF_RE.search(ref) else ref)
    cited = {_ref_key(m) for m in REF_RE.finditer(results_zone)}
    reg_disp = sorted(registered)
    missing_in_text = sorted(registered - cited)   # 登记了但结果段没引用
    unknown_in_text = sorted(cited - registered)   # 引用了但没登记
    return {"registered": reg_disp, "cited_in_results": sorted(cited),
            "missing_in_text": missing_in_text, "unknown_in_text": unknown_in_text,
            "verdict": "pass" if not (missing_in_text or unknown_in_text) else "fail",
            "hint": "登记的每张图/表都要在结果段被引用；引用编号须与 readings 登记一致（多面板引用如 图2A-C 视为引用图2）。"}


# ---- C) 讨论结论溯源 ----
def disc_claims(disc_zone, dclaims):
    claims, missing = [], []
    cid = 0
    for raw in re.split(r"(?<=[。！？])", disc_zone.replace("\n", " ")):
        s = raw.strip()
        if not s or len(s) < 8:
            continue
        if not any(w in s for w in CLAIM_WORDS):
            continue
        cid += 1
        mark = MARK_RE.search(s)
        support = mark.group(1).strip() if mark else ""
        strength = "推测" if any(k in s for k in ("可能", "提示", "推测", "有待")) else "数据/文献支持"
        row = {"cid": "D%02d" % cid, "claim": s[:160], "support": support,
               "strength": strength, "annotated": bool(mark)}
        claims.append(row)
        if not mark:
            missing.append(row)
    bound = len(claims) - len(missing)
    return {"claims": claims, "total": len(claims), "annotated": bound, "missing": missing,
            "verdict": "pass" if (claims and not missing) or not claims else "fail",
            "dclaims_file_bound": len(dclaims or []),
            "hint": "每条结论句末加【依据：图2A；文献[4] M05:p12】；推测句须带'可能/提示'限定语。"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--draft", required=True)
    ap.add_argument("--readings", default=None)
    ap.add_argument("--ledger", default=None)
    ap.add_argument("--dclaims", default=None)
    ap.add_argument("--out-table", default=None, help="number_source_table.json 输出路径（供 build_result.py 嵌入）")
    ap.add_argument("--out", default=None, help="trace_audit.json 报告路径")
    args = ap.parse_args()

    try:
        draft = open(args.draft, encoding="utf-8").read()
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"draft unreadable: {e}"}, ensure_ascii=False))
        return 1
    readings = _load_jsonl(args.readings)
    ledger = _load_jsonl(args.ledger)
    dclaims = _load_jsonl(args.dclaims)

    degraded = []
    if readings is None:
        degraded.append("readings.jsonl 缺失或不可解析——A/C 项降级，仅用 ledger 溯源")
    if ledger is None:
        degraded.append("fact_ledger.jsonl 缺失——A 项仅用 readings 溯源")

    tab = build_table(draft, readings, ledger)
    rz, dz = _zones(draft)
    if readings is not None and rz:
        xr = crossref(rz, readings)
    else:
        xr = {"verdict": "skipped", "hint": "readings 缺失或未定位到 Results 区段，交叉引用检查跳过"}
    if dz:
        dc = disc_claims(dz, dclaims)
    else:
        dc = {"verdict": "skipped", "hint": "未定位到 Discussion 区段，讨论溯源检查跳过"}

    hard_fail = (tab["unmatched"] > 0 and readings is not None) or \
                xr.get("verdict") == "fail" or dc.get("verdict") == "fail"
    report = {"draft": args.draft,
              "number_source_summary": {"checked": tab["checked"], "matched":
                                        sum(1 for r in tab["table"] if r["status"] == "matched"),
                                        "ledger": sum(1 for r in tab["table"] if r["status"] == "ledger"),
                                        "unmatched": tab["unmatched"]},
              "crossref": xr, "discussion_claims": dc,
              "degraded": degraded, "verdict": "fail" if hard_fail else "pass",
              "hint": "unmatched 数值回材料核对或标[待核]；missing_in_text 补引用；讨论句补【依据：…】标注。"}
    if args.out_table:
        os.makedirs(os.path.dirname(args.out_table) or ".", exist_ok=True)
        json.dump(tab["table"], open(args.out_table, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        json.dump(report, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({"verdict": report["verdict"], "checked": tab["checked"],
                      "unmatched": tab["unmatched"],
                      "crossref": xr.get("verdict"), "claims": f"{dc.get('annotated', 0)}/{dc.get('total', 0)}"},
                     ensure_ascii=False))
    return 1 if hard_fail else 0


if __name__ == "__main__":
    sys.exit(main())
