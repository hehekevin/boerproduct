#!/usr/bin/env python3
"""numeric_audit.py — 数值/单位/年份/显著性机械复算（cite-fact-verify 数值一致性）。

对稿件正文做三类确定性数值复算，回写 result.numeric_audit：
  inventory_per_section  各节数字+单位+前置语义标签清单（复算底账）
  label_conflicts        同一前置标签+单位在不同节出现不同数值（数值漂移候选）
  p_claims / p_violations 显著性表述复算：正文宣称 p<阈值 与他节报告 p=值
                         逐条复算，p=值不满足阈值即候选违规（如摘要 p<0.01、
                         结果 p=0.04 → 0.04 不满足 <0.01）
统计口径：前置标签取数字前紧邻的中文/字母串末尾 3 字符（≥2 字符才参与分组），
英文词数用正则统计——不用 str.isalpha()（汉字 "字".isalpha()==True 会把中文
全部误计为英文词，isalpha 汉字陷阱）。
扫描结果是机械候选清单，供 Agent 复核；不直接下"数值矛盾"结论，也不改动
findings。verify_check.py 会把 numeric_consistency 发现的 numeric_claims 逐字
回证于稿件原文，防止冒充数值证据。

**键归属**：本脚本只写 result.numeric_audit 一个键。
退出码恒为 0（结论记在 stdout 与报告，不中断交付）。
用法：
    python3 numeric_audit.py --result /app/output/result.json --case /input/case.json --emit-into
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

MANU_KEYS = ("manuscript", "paper", "document", "full_text", "text", "body", "content")
SECTION_KEYS = ("sections", "chapters", "parts")

NUM_RE = re.compile(r"([\u4e00-\u9fffA-Za-z]{2,})\s*(\d+(?:\.\d+)?)\s*"
                    r"(个百分点|%|‰|个月|小时|分钟|毫克|毫升|微克|名|人|例|岁|年|月|周|天|日|次|个|种|篇|项|条|批|倍|度|分|秒|"
                    r"mg|ml|kg|mm|cm|km|min|μg|ng|pg|mmol|nmol|h|g|l|s)?")
P_RE = re.compile(r"[pP]\s*(<=|>=|<|>|≤|≥|=)\s*(0?\.\d+|[01](?:\.\d+)?)")


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_json(path, obj):
    try:
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)
        return True
    except Exception as e:
        print("[numeric_audit] 写盘失败 %s: %s" % (path, e))
        return False


def sections_of(case):
    """返回 [(section_id, text)]：常见稿件键下的分段文本；无分段则整体一段。"""
    root = None
    if isinstance(case, dict):
        for k in MANU_KEYS:
            if isinstance(case.get(k), (dict, list, str)):
                root = case[k]
                break
    if root is None:
        root = case if isinstance(case, dict) else {}
    out = []
    if isinstance(root, dict):
        for sk in SECTION_KEYS:
            v = root.get(sk)
            if isinstance(v, list) and v:
                for i, s in enumerate(v):
                    sid = str(s.get("section_id") or s.get("id") or ("S%d" % (i + 1))) if isinstance(s, dict) else "S%d" % (i + 1)
                    txt = str(s.get("text") or s.get("content") or "") if isinstance(s, dict) else str(s)
                    out.append((sid, txt))
                return out
        if isinstance(root.get("text"), str):
            out.append(("FULL", root["text"]))
    elif isinstance(root, str):
        out.append(("FULL", root))
    if not out:
        buf = []

        def walk(o):
            if isinstance(o, dict):
                for v in o.values():
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)
            elif isinstance(o, str):
                buf.append(o)
        walk({k: v for k, v in (case.items() if isinstance(case, dict) else []) if k != "output_contract"})
        out.append(("FULL", "".join(buf)))
    return out


def en_words(s):
    """英文词数：正则统计，规避 isalpha 的汉字误计陷阱。"""
    return len(re.findall(r"[A-Za-z]+", str(s or "")))


def scan_section(text):
    """扫描一节文本 → (numeric entries, p_claims)。"""
    entries, pclaims = [], []
    for m in NUM_RE.finditer(text or ""):
        label, value, unit = m.group(1), m.group(2), (m.group(3) or "")
        label = label[-3:]
        ctx = text[max(0, m.start(2) - 10):min(len(text), m.end(2) + 14)].replace("\n", " ")
        entries.append({"value": value, "unit": unit, "label": label, "context": ctx})
    for m in P_RE.finditer(text or ""):
        op, val = m.group(1), m.group(2)
        pclaims.append({"token": "p%s%s" % (op, val), "op": op, "value": float(val)})
    return entries, pclaims


def audit(res, case):
    secs = sections_of(case)
    inventory, p_by_sec = {}, {}
    for sid, text in secs:
        entries, pclaims = scan_section(text)
        inventory[sid] = entries
        p_by_sec[sid] = pclaims

    # 同标签+单位跨节数值漂移候选
    groups = {}
    for sid, entries in inventory.items():
        for e in entries:
            key = (e["label"], e["unit"])
            groups.setdefault(key, {}).setdefault(e["value"], []).append(sid)
    conflicts = []
    for (label, unit), vals in sorted(groups.items()):
        if len(vals) > 1:
            conflicts.append({"label": label, "unit": unit,
                              "values": sorted(vals.keys(), key=lambda x: float(x) if x.replace(".", "", 1).isdigit() else 0),
                              "sections": {v: vals[v] for v in sorted(vals)},
                              "note": "同一前置标签+单位出现不同数值，须人工复核是否指同一量"})

    # 显著性复算：p=值 不满足他节宣称的 p<阈值 → 候选违规
    thresholds, values = [], []
    for sid, claims in p_by_sec.items():
        for c in claims:
            (thresholds if c["op"] in ("<", "<=", "≤") else values).append(dict(c, section=sid))
    p_violations = []
    for v in values:
        for t in thresholds:
            if v["value"] > t["value"]:
                p_violations.append({"claimed": t["token"], "claimed_section": t["section"],
                                     "actual": v["token"], "actual_section": v["section"],
                                     "recompute": "%.2f 不满足 %s%.2f，显著性表述自相矛盾（候选，须复核）"
                                                  % (v["value"], t["op"], t["value"])})

    total_nums = sum(len(v) for v in inventory.values())
    return {
        "inventory_per_section": inventory,
        "label_conflicts": conflicts,
        "p_claims": {k: [c["token"] for c in v] for k, v in p_by_sec.items() if v},
        "p_violations": p_violations,
        "stats": {"numbers_scanned": total_nums, "en_words": en_words("".join(t for _s, t in secs)),
                  "note": "前置标签取数字前紧邻中文/字母串末 3 字符；英文词数用正则统计（规避 isalpha 汉字陷阱）"},
        "scan_note": "机械复算候选清单：label_conflicts 与 p_violations 须由 Agent 逐条复核后才能写入"
                     " findings（facet=numeric_consistency，numeric_claims 须逐字回证于稿件原文）。",
    }


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", default="/app/output/result.json")
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--out", default=None)
        ap.add_argument("--emit-into", action="store_true",
                        help="把 numeric_audit 回写 result.json 的 result.numeric_audit")
        args = ap.parse_args()
    except Exception as e:
        print("[numeric_audit] 参数解析失败（已降级）: %s" % e)
        return 0

    res = load_json(args.result)
    if not isinstance(res, dict):
        print("[numeric_audit] FAIL: result.json 不存在或不可解析: %s（不中断交付）" % args.result)
        return 0
    case = load_json(args.case)
    result = audit(res, case if isinstance(case, dict) else {})

    if args.out:
        save_json(args.out, {"numeric_audit": result})
    if args.emit_into:
        cur = load_json(args.result)
        if isinstance(cur, dict) and isinstance(cur.get("result"), dict):
            cur["result"]["numeric_audit"] = result
            save_json(args.result, cur)

    print("[numeric_audit] 扫描数字 %d 个 | 标签冲突候选 %d | p 表述违规候选 %d"
          % (result["stats"]["numbers_scanned"], len(result["label_conflicts"]),
             len(result["p_violations"])))
    for c in result["label_conflicts"]:
        print("  conflict: %s%s → %s" % (c["label"], c["unit"], c["sections"]))
    for v in result["p_violations"]:
        print("  p-violation: %s(%s) vs %s(%s)" % (v["claimed"], v["claimed_section"],
                                                   v["actual"], v["actual_section"]))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[numeric_audit] 未预期异常（已降级，不中断交付）: %s" % e)
        sys.exit(0)
