#!/usr/bin/env python3
"""extraction_guard.py — 数据提取结构化与逐字回证守卫（sysrev-review-synthesis）。

对 result.extraction 做机械审计（与题面"提取项回证"机检点对应）：
  1. 每条纳入（非重复）记录必须有结构化提取项 item；
  2. 每个提取项必须含 study_design / sample / effect 三个结构化块，且每块的
     evidence.quote + evidence.location 非空；
  3. **提取项回证**：每个 evidence.quote 必须在来源文本中逐字命中（空白归一化
     子串匹配）——来源为 case.json 全 corpus（题录各字段拼接）或该记录在
     result.claims 的证据链，二者命中其一即可；
  4. 数值字段缺失（effect.value / sample.size 为 null）时必须有 extraction_notes
     说明（材料缺失登记，不脑补）。
纯函数 analyze_extraction(inner, case=None) 供 verify_check.py 复用；CLI 只读
审计不改写 result.json。退出码恒为 0。
用法：
    python3 extraction_guard.py --result /app/output/result.json --case /input/case.json \
        [--out /app/work/extraction_audit.json]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

RECORD_KEYS = ("records", "papers", "candidates", "items", "documents",
               "literature", "search_results", "results", "exports")


def norm(s):
    return re.sub(r"\s+", "", str(s or ""))


def case_corpus(case):
    """把 case.json 里全部题录文本拼成归一化语料（含数组元素逐条文本）。"""
    texts = []

    def walk(o):
        if isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                if isinstance(v, (dict, list)):
                    walk(v)
                elif isinstance(v, str):
                    texts.append(v)
        elif isinstance(o, str):
            texts.append(o)

    for key in RECORD_KEYS:
        v = case.get(key) if isinstance(case, dict) else None
        if isinstance(v, list) and v:
            for e in v:
                if isinstance(e, dict):
                    for sv in e.values():
                        if isinstance(sv, str):
                            texts.append(sv)
                elif isinstance(e, str):
                    texts.append(e)
    walk(case.get("fulltexts") if isinstance(case, dict) else None)
    return norm("".join(texts))


def claims_index(res_claims):
    idx = {}
    for c in res_claims or []:
        if isinstance(c, dict):
            idx.setdefault(str(c.get("source_id") or ""), []).append(c)
    return idx


def quote_backed(quote, corpus, claim_entries):
    q = norm(quote)
    if not q:
        return False
    if q in corpus:
        return True
    for c in claim_entries:
        for e in (c.get("evidence") or []):
            if isinstance(e, dict) and q and q in norm(e.get("quote")):
                return True
    return False


def _block_ok(block):
    ev = block.get("evidence") if isinstance(block, dict) else None
    ok = bool(str((ev or {}).get("quote") or "").strip()) and bool(str((ev or {}).get("location") or "").strip())
    return ok, (ev or {}).get("quote")


def analyze_extraction(inner, case=None):
    """纯函数审计（不写盘）。返回 {problems, self_check, missing, quotes_unbacked}。"""
    problems, self_check, missing, unbacked = [], [], [], []
    corpus = case_corpus(case if isinstance(case, dict) else {})
    cidx = claims_index(inner.get("_claims") or [])
    records = [r for r in (inner.get("records") or []) if isinstance(r, dict)]
    included = [r for r in records if r.get("decision") == "included" and not r.get("duplicate_of")]
    ext = inner.get("extraction") if isinstance(inner, dict) else None
    ext = ext if isinstance(ext, dict) else {}
    items = [it for it in (ext.get("items") or []) if isinstance(it, dict)]
    iidx = {str(it.get("record_id")): it for it in items}
    known_ids = {str(r.get("record_id")) for r in records}

    for it in items:
        rid = str(it.get("record_id") or "")
        if rid not in known_ids:
            problems.append("提取项 record_id=%r 不在 result.records 中（提取项须回链到真实题录）" % rid)
        elif str(next(r.get("decision") for r in records if str(r.get("record_id")) == rid)) != "included":
            problems.append("提取项 record_id=%r 指向非 included 记录（只提取纳入研究）" % rid)

    for r in included:
        rid = str(r.get("record_id") or "")
        it = iidx.get(rid)
        ok_present = it is not None
        self_check.append({"item": "extraction[%s].present" % rid,
                           "template_value": "included ⇒ 结构化提取项存在", "applied": True,
                           "match": ok_present})
        if not ok_present:
            missing.append(rid)
            problems.append("纳入记录 %s 缺结构化提取项（study_design/sample/effect）" % rid)
            continue
        entries = cidx.get(rid) or []
        for blk, label in (("study_design", "study_design"), ("sample", "sample"),
                           ("effect", "effect")):
            b = it.get(blk)
            if not isinstance(b, dict) or not b:
                problems.append("%s 提取项缺结构化块 %s" % (rid, label))
                self_check.append({"item": "extraction[%s].%s" % (rid, label),
                                   "template_value": "结构化块存在且证据回证", "applied": True, "match": False})
                continue
            ok, q = _block_ok(b)
            backed = quote_backed(q, corpus, entries) if ok else False
            self_check.append({"item": "extraction[%s].%s_backed" % (rid, label),
                               "template_value": "evidence.quote 在来源文本逐字回证",
                               "applied": True, "match": ok and backed})
            if not ok:
                problems.append("%s 提取块 %s 缺 evidence.quote/location（提取项无据）" % (rid, label))
            elif not backed:
                unbacked.append("%s.%s" % (rid, label))
                problems.append("%s 提取块 %s 的 evidence.quote 在来源语料与 claims 中均无逐字回证" % (rid, label))
        # 数值缺失须说明（不脑补）
        eff_val = ((it.get("effect") or {}).get("value")) if isinstance(it.get("effect"), dict) else None
        smp = it.get("sample") if isinstance(it.get("sample"), dict) else {}
        size = smp.get("size")
        note = str(it.get("extraction_notes") or "").strip()
        if (eff_val is None or size is None) and not note:
            problems.append("%s 提取项 effect.value/sample.size 缺失且 extraction_notes 未说明"
                            "（材料缺失须登记，不得留空且不说明）" % rid)
    return {"problems": problems, "self_check": self_check, "missing": missing,
            "quotes_unbacked": unbacked, "n_included": len(included), "n_items": len(items)}


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", required=True)
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--out", default="/app/work/extraction_audit.json")
        args = ap.parse_args()
    except Exception as e:
        print("[extraction_guard] 参数解析失败（已降级）: %s" % e)
        return 0
    try:
        with open(args.result, "r", encoding="utf-8") as f:
            res = json.load(f)
        inner = res.get("result") if isinstance(res, dict) else None
        if not isinstance(inner, dict):
            raise ValueError("result 非对象")
        inner = dict(inner)
        inner["_claims"] = res.get("claims") or []
    except Exception as e:
        print("[extraction_guard] FAIL: result.json 不可读: %s（不中断交付）" % e)
        _dump(args.out, {"verdict": "FAIL", "problems": ["读取失败: %s" % e]})
        return 0
    case = {}
    try:
        if os.path.exists(args.case):
            with open(args.case, "r", encoding="utf-8") as f:
                case = json.load(f)
    except Exception as e:
        print("[extraction_guard] case.json 不可读（语料回证降级为仅 claims 回证）: %s" % e)
    rep = analyze_extraction(inner, case)
    verdict = "FAIL" if rep["problems"] else "PASS"
    _dump(args.out, {"verdict": verdict, **rep})
    print("[extraction_guard] %s: 纳入 %d 条 / 提取项 %d 个 / 缺项 %d / 无回证 %d"
          % (verdict, rep["n_included"], rep["n_items"], len(rep["missing"]), len(rep["quotes_unbacked"])))
    for p in rep["problems"][:20]:
        print("  - %s" % p)
    return 0


def _dump(path, obj):
    if not path:
        return
    try:
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[extraction_guard] 未预期异常（已降级，不中断交付）: %s" % e)
        sys.exit(0)
