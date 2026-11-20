#!/usr/bin/env python3
"""result_scaffold.py — result.json 生命线守卫（骨架生成 + 非空兜底修补）。

模式：
    scaffold  依据 case.json 生成骨架 result.json（Stage 0 立即执行，先落盘再逐段回填）
    ensure    读取已有 result.json，修补空缺：result 永不为空串/null、
              verification 数组不为空（自动补 status=not_recomputable+missing 占位）、
              claims 不为空、status 落在合法四级枚举内

用法：
    python result_scaffold.py scaffold --case /input/case.json --out $WORK/result.json
    python result_scaffold.py ensure   --result $WORK/result.json \
        [--case /input/case.json] [--out /app/output/result.json]

原则：修补只补结构不造内容——占位条目全部显式声明"待回填/缺失"，不编造数值。
退出码：0=成功；2=参数错误；1=无法写入输出。
"""
from __future__ import annotations

import argparse
import json
import sys

STATUSES = {"answered", "partial", "insufficient_evidence", "input_error"}
CONTRACT = ["case_id", "status", "result", "claims", "uncertainties", "changelog"]
RESULT_INNER = ["formulas", "variables", "derivations", "verification", "coverage"]
UNC_KEYS = ["unreported", "unverifiable", "conflicts", "human_review", "summary"]


def _load(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f), None
    except Exception as e:
        return {}, "读取失败（%s），按空骨架重建" % e


def _dump(obj, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def _case_info(case_path):
    case, _ = _load(case_path) if case_path else ({}, None)
    cid = case.get("case_id") or case.get("id") or "unknown-case"
    fields = []
    oc = case.get("output_contract")
    if isinstance(oc, dict):
        for key in ("fields", "required_fields", "result.json", "result"):
            if isinstance(oc.get(key), list):
                fields = [str(x) for x in oc[key]]
                break
        else:
            fields = [str(k) for k in oc.keys()]
    elif isinstance(oc, list):
        fields = [str(x) for x in oc]
    return cid, fields


def _placeholder_verification(reason):
    return {"formula_id": "n/a", "status": "not_recomputable",
            "missing": [reason], "notes": "占位条目：%s。后续阶段必须替换为"
            "真实核验（expected+computed）或真实缺失登记，不得保留占位提交。" % reason}


def _placeholder_claim(cid, text):
    return {"claim_id": "k-00", "text": text, "kind": "reported",
            "source_id": cid, "location": "result.json",
            "evidence": [{"paragraph_id": "n/a", "quote": text}]}


def scaffold(case_path, out_path):
    cid, fields = _case_info(case_path)
    res = {k: None for k in dict.fromkeys(CONTRACT + fields) if k}
    res["case_id"] = cid
    res["status"] = "partial"
    res["result"] = {k: ([] if k != "coverage" else
                         {"formulas_total": 0, "converted_full": 0,
                          "variables_defined": 0, "derivation_steps": 0,
                          "verified": 0, "not_recomputable": False})
                     for k in RESULT_INNER}
    res["result"]["verification"] = [_placeholder_verification(
        "骨架阶段：尚未盘点可计算公式与输入")]
    res["claims"] = [_placeholder_claim(cid, "骨架已生成，各阶段将逐段回填真实结果")]
    res["uncertainties"] = {k: ([] if k != "summary" else
                               "骨架阶段：尚未开始，全部内容待回填")
                            for k in UNC_KEYS}
    res["changelog"] = [{"step": "scaffold", "change": "生成骨架 result.json"}]
    _dump(res, out_path)
    print("[result_scaffold] 骨架已写入 %s（case_id=%s，契约字段=%d）"
          % (out_path, cid, len(res)))
    return 0


def ensure(result_path, case_path, out_path):
    res, err = _load(result_path)
    fixes = []
    if err:
        fixes.append(err)

    cid, fields = _case_info(case_path) if case_path else ("unknown-case", [])
    for k in dict.fromkeys(CONTRACT + fields):
        if k not in res:
            res[k] = None
            fixes.append("补缺失字段 %s" % k)

    if not res.get("case_id"):
        res["case_id"] = cid
        fixes.append("补 case_id=%s" % cid)

    if res.get("status") not in STATUSES:
        res["status"] = "partial"
        fixes.append("status 非法/缺失 → partial（请人工复核后改为诚实四级之一）")

    inner = res.get("result")
    if not isinstance(inner, dict) or not inner:
        inner = {k: ([] if k != "coverage" else
                     {"formulas_total": 0, "converted_full": 0,
                      "variables_defined": 0, "derivation_steps": 0,
                      "verified": 0, "not_recomputable": False})
                 for k in RESULT_INNER}
        res["result"] = inner
        fixes.append("result 为空/非对象 → 重建空结构")
    for k in RESULT_INNER:
        if k not in inner:
            inner[k] = {"formulas_total": 0, "converted_full": 0,
                        "variables_defined": 0, "derivation_steps": 0,
                        "verified": 0, "not_recomputable": False} if k == "coverage" else []
            fixes.append("result.%s 缺失 → 置空容器" % k)

    verifs = inner.get("verification")
    if not isinstance(verifs, list) or not verifs:
        inner["verification"] = [_placeholder_verification(
            "运行结束时 verification 仍为空，按缺失登记")]
        fixes.append("verification 为空 → 补 not_recomputable 占位（含 missing 清单）")

    claims = res.get("claims")
    if not isinstance(claims, list) or not claims:
        res["claims"] = [_placeholder_claim(
            res["case_id"],
            "运行结束但未产出任何论断：主结果见 result 字段，状态 %s" % res["status"])]
        fixes.append("claims 为空 → 补说明性 claim")

    unc = res.get("uncertainties")
    if not isinstance(unc, dict) or not unc:
        res["uncertainties"] = {k: ([] if k != "summary" else "未提供")
                                for k in UNC_KEYS}
        fixes.append("uncertainties 缺失/非对象 → 重建")

    _dump(res, out_path)
    if fixes:
        print("[result_scaffold] ensure 修补 %d 处：" % len(fixes))
        for f_ in fixes:
            print("  - %s" % f_)
    else:
        print("[result_scaffold] ensure：结构完整，无需修补")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="mode", required=True)
    s1 = sub.add_parser("scaffold")
    s1.add_argument("--case", required=True)
    s1.add_argument("--out", required=True)
    s2 = sub.add_parser("ensure")
    s2.add_argument("--result", required=True)
    s2.add_argument("--case", default=None)
    s2.add_argument("--out", required=True)
    args = ap.parse_args()
    try:
        if args.mode == "scaffold":
            return scaffold(args.case, args.out)
        return ensure(args.result, args.case, args.out)
    except OSError as e:
        print("[result_scaffold] 输出写入失败: %s" % e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
