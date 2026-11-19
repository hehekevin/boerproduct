#!/usr/bin/env python3
"""skeleton.py — field2table-r3 骨架生成器 + 段落收割器。

一次调用完成两件事：
1. 为 output_contract 全部键 + 全部 field_id 生成一版全覆盖 result.json 骨架
   （每 field_id 一行 status=extraction_failed），保证任何时刻 result.json 存在
   且 JSON 可解析。
2. 从 case.json 收割段落文本（paragraphs/passages/sections 等）写入 --paras 指定
   的段落库文件，供 check.py 做逐字校验。

任何异常都降级写盘，绝不裸崩，退出码恒为 0。

用法：
    python3 skeleton.py --fields /input/target-fields.json --case /input/case.json \
        --out /app/output/result.json --paras /app/work/paragraphs.json
"""
from __future__ import annotations

import argparse
import json
import sys

UNIVERSAL = ["case_id", "status", "result", "claims", "uncertainties"]
DEFAULT_SUMMARY = "骨架：全部字段待抽取"


def read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print("[skeleton] 读取失败 %s: %s" % (path, e))
        return None


def pick_fields(tf):
    """兼容 fields/targets/items 列表或纯数组；返回 (field_ids, definitions)。"""
    ids, defs = [], {}
    try:
        if isinstance(tf, list):
            items = tf
        elif isinstance(tf, dict):
            items = tf.get("fields") or tf.get("targets") or tf.get("items") or []
        else:
            items = []
        for it in items:
            if isinstance(it, dict):
                fid = it.get("field_id") or it.get("id") or it.get("name")
                if fid is None:
                    continue
                fid = str(fid)
                ids.append(fid)
                defs[fid] = {k: v for k, v in it.items() if k not in ("field_id", "id", "name")}
            elif isinstance(it, (str, int)):
                ids.append(str(it))
    except Exception as e:
        print("[skeleton] 字段清单解析失败: %s" % e)
    seen, out = set(), []
    for i in ids:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out, defs


def contract_keys(case):
    """output_contract 声明的键 + 通用五键，返回保序去重列表。"""
    keys = list(UNIVERSAL)
    extra = []
    try:
        oc = case.get("output_contract") if isinstance(case, dict) else None
        if isinstance(oc, dict):
            for key in ("fields", "required_fields", "result.json", "result"):
                v = oc.get(key)
                if isinstance(v, list):
                    extra = [str(x) for x in v]
                    break
            if not extra:
                extra = [str(k) for k in oc.keys()]
        elif isinstance(oc, list):
            extra = [str(x) for x in oc]
    except Exception as e:
        print("[skeleton] output_contract 解析失败: %s" % e)
    for k in extra:
        if k not in keys:
            keys.append(k)
    return keys


def default_for(key, case):
    """契约键的最小合法占位：绝不省略键，未知值填 unknown 或空数组。"""
    if key == "case_id":
        try:
            return case.get("case_id") if isinstance(case, dict) else None
        except Exception:
            return None
    if key == "status":
        return "partial"
    if key == "result":
        return None  # 由调用方填充
    if key == "claims":
        return []
    if key == "uncertainties":
        return {"unreported": [], "unverifiable": [], "conflicts": [],
                "human_review": [], "summary": DEFAULT_SUMMARY}
    if key == "changelog":
        return [{"step": "skeleton", "change": "生成全字段骨架+段落库"}]
    return "unknown"


def empty_row(fid, fdef):
    row = {
        "field_id": fid,
        "status": "extraction_failed",
        "value": {"scalar": None, "range": None, "text": None},
        "units": None,
        "statistic": None,
        "conditions": [],
        "comparator": None,
        "evidence": [],
        "verbatim_number": None,
        "claim_layer": None,
        "search_log": [],
        "evidence_note": None,
        "conflicts": [],
        "failure_reason": "not yet processed (skeleton)",
    }
    if fdef:
        row["field_definition"] = fdef
    return row


def harvest_paras(case):
    """从 case.json 收割段落文本，返回 {pid: text}。"""
    texts = {}
    if not isinstance(case, dict):
        return texts
    for key in ("paragraphs", "passages", "paper_paragraphs", "sections", "material"):
        v = case.get(key)
        if isinstance(v, list):
            for p in v:
                if isinstance(p, dict):
                    pid = str(p.get("paragraph_id") or p.get("id") or p.get("pid") or "")
                    txt = str(p.get("text") or p.get("content") or p.get("body") or "")
                    if pid and txt:
                        texts[pid] = txt
            if texts:
                break
        elif isinstance(v, dict):
            for k, t in v.items():
                if isinstance(t, str) and t.strip():
                    texts[str(k)] = t
            if texts:
                break
    # 兜底：嵌套在 material/paper 下
    if not texts:
        for holder in ("material", "paper", "source", "document"):
            sub = case.get(holder)
            if isinstance(sub, dict):
                for key in ("paragraphs", "passages", "sections"):
                    v = sub.get(key)
                    if isinstance(v, list):
                        for p in v:
                            if isinstance(p, dict):
                                pid = str(p.get("paragraph_id") or p.get("id") or p.get("pid") or "")
                                txt = str(p.get("text") or p.get("content") or p.get("body") or "")
                                if pid and txt:
                                    texts[pid] = txt
                        if texts:
                            break
    return texts


def build(args):
    tf = read_json(args.fields)
    case = read_json(args.case) or {}
    if not isinstance(case, dict):
        case = {}

    fids, fdefs = pick_fields(tf)
    if not fids:
        fids, fdefs = ["unknown"], {}
        print("[skeleton] target-fields 无可用 field_id，写入单条 unknown 行")

    rows = [empty_row(fid, fdefs.get(fid)) for fid in fids]
    result_body = {
        "field_schema_version": "r3",
        "fields": rows,
        "coverage": {"fields_total": len(rows), "reported": 0, "not_reported": 0,
                     "source_conflict": 0, "extraction_failed": len(rows)},
        "field_dictionary": {fid: fdefs[fid] for fid in fids if fid in fdefs},
        "extraction_criteria": {
            "source_priority": ["表格", "结果段", "图注", "摘要/结论", "补充材料"],
            "unit_policy": "保留原单位不换算",
            "verbatim_rule": "verbatim_number ∈ quote 且与 scalar 数值一致",
            "hedge_rule": "限定词原样进 conditions 并标推断性",
            "absent_rule": "未报告≠0",
            "coverage_rule": "每个 field_id 一行 + 每行一条 claim-<field_id>",
        },
    }

    out = {}
    for key in contract_keys(case):
        val = default_for(key, case)
        out[key] = result_body if key == "result" and val is None else val
    if "result" not in out:
        out["result"] = result_body
    if not out.get("case_id"):
        out["case_id"] = case.get("case_id")
        if not out["case_id"]:
            print("[skeleton] case_id 缺失，置 null 并记入 uncertainties")
            try:
                out["uncertainties"]["unverifiable"].append("case_id 缺失：case.json 未提供")
            except Exception:
                pass
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fields", default="/input/target-fields.json")
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--out", default="/app/output/result.json")
    ap.add_argument("--paras", default="/app/work/paragraphs.json")
    args = ap.parse_args()

    try:
        doc = build(args)
    except Exception as e:
        print("[skeleton] 构建失败，降级为最小骨架: %s" % e)
        doc = {
            "case_id": None, "status": "partial",
            "result": {"field_schema_version": "r3",
                       "fields": [empty_row("unknown", None)],
                       "coverage": {"fields_total": 1, "reported": 0, "not_reported": 0,
                                    "source_conflict": 0, "extraction_failed": 1},
                       "field_dictionary": {}, "extraction_criteria": {}},
            "claims": [],
            "uncertainties": {"unreported": [], "unverifiable": ["骨架构建异常: %s" % e],
                              "conflicts": [], "human_review": [], "summary": DEFAULT_SUMMARY},
            "changelog": [{"step": "skeleton", "change": "降级骨架（构建异常）"}],
        }

    try:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=1)
        n = 0
        try:
            n = len(doc.get("result", {}).get("fields", []))
        except Exception:
            pass
        print("[skeleton] 骨架已写入 %s（%d 行 field）" % (args.out, n))
    except Exception as e:
        print("[skeleton] 写盘失败（请手工创建 result.json）: %s" % e)

    # 段落收割（第二职责，失败不影响骨架交付）
    try:
        case = read_json(args.case) or {}
        texts = harvest_paras(case)
        if texts:
            import os
            d = os.path.dirname(args.paras)
            if d:
                os.makedirs(d, exist_ok=True)
            with open(args.paras, "w", encoding="utf-8") as f:
                json.dump(texts, f, ensure_ascii=False, indent=1)
            print("[skeleton] 段落库已写入 %s（%d 段）" % (args.paras, len(texts)))
        else:
            print("[skeleton] case.json 未收割到段落（PDF 或异形材料，check 将降级跳过逐字校验）")
    except Exception as e:
        print("[skeleton] 段落收割失败（不影响骨架）: %s" % e)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[skeleton] 未捕获异常已兜底: %s" % e)
        sys.exit(0)
