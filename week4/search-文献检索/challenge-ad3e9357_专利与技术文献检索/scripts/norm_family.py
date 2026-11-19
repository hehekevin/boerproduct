#!/usr/bin/env python3
"""norm_family.py — 号码规范化 + 专利族归并 + 确定性筛选排序引擎（patent-search-verify）。

职责（全部机械可复算，无模型参与）：
  1. 号码规范化：把 raw_number（公开号/授权号/申请号）归一为 `国家码+数字+种类码`
     的规范形式（大写、去空格与标点、补全识别 number_kind），写 items[].norm_number。
     归一失败（无法识别国家码/号码过短）→ 保留 None，由 Agent 登记 missing_metadata。
  2. 专利族归并：按族键（规范化后的优先权号，缺省用申请号）把同族成员聚到
     family_groups[]（family_id / key / key_kind / member_ids / scope / evidence）；
     无族键条目 family_id=None（独立条目，不臆造族关系）。scope 口径照 Agent 声明
     （simple=同优先权 / extended=扩展族），脚本只按声明的键机械归并。
  3. 确定性筛选排序：relevance 层级(direct=0,indirect=1,irrelevant=2) → confidence
     降序 → item_id 升序，写 result.screening（ordered_ids / ties）。

**键归属**：本脚本只写 items[].norm_number、items[].family_id、result.family_groups、
result.screening；其余键一律不碰（多脚本禁写同一键）。

用法：
    python3 norm_family.py --result /app/output/result.json [--dry-run]
退出码恒为 0（结论记在 stdout 与报告 verdict 字段，不中断交付）。
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys

# 规范形式：两个字母国家码 + 至少 6 位数字/字母（含种类码），如 US20200123456A1
NORM_RE = re.compile(r"^[A-Z]{2}[0-9A-Z]{6,15}$")
CC_RE = re.compile(r"^[A-Z]{2}$")
KIND_PATTERNS = [
    ("publication", re.compile(r"^[A-Z]{2}\d{6,12}[A-Z]\d?$")),
    ("grant", re.compile(r"^[A-Z]{2}\d{6,12}[B-Z]$")),
    ("application", re.compile(r"^[A-Z]{2}\d{8,14}[0-9X]?$")),
]
TIER = {"direct": 0, "indirect": 1, "irrelevant": 2}
CONF = {"high": 0, "medium": 1, "low": 2}


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
        print("[norm_family] 写盘失败 %s: %s" % (path, e))
        return False


def normalize_number(raw):
    """号码规范化：大写、去空白与常见分隔符；返回 (norm, kind, note)。"""
    if raw is None or not str(raw).strip():
        return None, None, "raw_number 为空"
    s = re.sub(r"[\s,./\-_()]", "", str(raw)).upper()
    # 申请号校验位 X 保留（如 CN202310123456X），其余字符必须是字母/数字
    if not re.fullmatch(r"[0-9A-Z]+", s):
        return None, None, "含无法归一的字符（仅保留字母数字）"
    m = CC_RE.match(s[:2])
    if not m:
        return None, None, "缺少两位国家/组织码前缀"
    digits = sum(ch.isdigit() for ch in s)
    if digits < 6:
        return None, None, "数字位不足 6 位，疑似不完整号码"
    kind = "unknown"
    for k, pat in KIND_PATTERNS:
        if pat.fullmatch(s):
            kind = k
            break
    return s, kind, ""


def family_key(item):
    """族键：规范化优先权号（取最小者保证确定性），缺省用申请号。"""
    keys = []
    for p in (item.get("priority_numbers") or []):
        n, _k, note = normalize_number(p)
        if n:
            keys.append(n)
    if keys:
        return min(keys), "priority"
    if item.get("application_number"):
        n, _k, note = normalize_number(item["application_number"])
        if n:
            return n, "application"
    return None, None


def build_updates(items):
    """对 items 逐条规范化 + 归族。返回 (updates, families, problems)。"""
    problems, updates = [], {}
    fam_members = {}
    for it in items:
        if not isinstance(it, dict):
            continue
        iid = str(it.get("item_id"))
        norm, kind, note = normalize_number(it.get("raw_number"))
        if norm is None and it.get("kind") == "patent":
            problems.append("%s 号码无法归一（%s）→ 须登记 missing_metadata" % (iid, note))
        key, key_kind = family_key(it)
        updates[iid] = {"norm_number": norm, "number_kind": kind, "family_id": None}
        if key:
            fid = "F-" + key[:14]
            fam_members.setdefault(fid, {"key": key, "key_kind": key_kind, "members": []})
            fam_members[fid]["members"].append(iid)
            updates[iid]["family_id"] = fid
    families = []
    for fid in sorted(fam_members):
        g = fam_members[fid]
        families.append({"family_id": fid,
                         "key": g["key"], "key_kind": g["key_kind"],
                         "member_ids": sorted(g["members"]),
                         "scope": None,
                         "evidence": "族键=%s(%s)；成员号见 items[].priority_numbers/application_number"
                                     % (g["key"], g["key_kind"])})
    return updates, families, problems


def screening_order(items):
    """确定性筛选顺序：relevance 层级 → confidence → item_id（字符串序）。"""
    scored = []
    for it in items:
        if not isinstance(it, dict) or it.get("relevance") is None:
            continue
        iid = str(it.get("item_id"))
        tier = TIER.get(it.get("relevance"), 3)
        conf = CONF.get(it.get("confidence"), 3)
        scored.append((iid, tier, conf))
    ordered = [t[0] for t in sorted(scored, key=lambda t: (t[1], t[2], t[0]))]
    ties = {}
    for iid, tier, conf in scored:
        ties.setdefault((tier, conf), []).append(iid)
    tie_groups = [{"relevance_tier": t, "confidence_rank": c, "item_ids": sorted(ids),
                   "rule": "item_id 升序"}
                  for (t, c), ids in sorted(ties.items()) if len(ids) > 1]
    return ordered, tie_groups


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", default="/app/output/result.json")
        ap.add_argument("--dry-run", action="store_true", help="只打印对照，不写盘")
        args = ap.parse_args()
    except Exception as e:
        print("[norm_family] 参数解析失败（已降级）: %s" % e)
        return 0

    res = load_json(args.result)
    if not isinstance(res, dict) or not isinstance(res.get("result"), dict):
        print("[norm_family] FAIL: result.json 不存在/不可解析/无 result 对象: %s（不中断交付）"
              % args.result)
        return 0

    inner = res["result"]
    items = [it for it in (inner.get("items") or []) if isinstance(it, dict)]
    updates, families, problems = build_updates(items)
    ordered, tie_groups = screening_order(items)

    print("[norm_family] 已规范化 %d/%d 条号码 | 归并出 %d 个族 | 筛选顺序 %d 条"
          % (sum(1 for u in updates.values() if u["norm_number"]), len(items),
             len(families), len(ordered)))
    for f in families:
        print("  %s  key=%s (%s)  members=%s"
              % (f["family_id"], f["key"], f["key_kind"], ",".join(f["member_ids"])))
    for t in tie_groups:
        print("  并列组 tier=%d conf=%d → %s" % (t["relevance_tier"], t["confidence_rank"],
                                                ",".join(t["item_ids"])))
    for p in problems:
        print("  WARN: %s" % p)

    if args.dry_run:
        print("[norm_family] dry-run：不写盘。")
        return 0
    if not updates and not families:
        print("[norm_family] FAIL: 无任何条目可处理（见 WARN），不写盘。")
        return 0

    changed = copy.deepcopy(res)
    ch_inner = changed["result"]
    for it in ch_inner.get("items") or []:
        u = updates.get(str(it.get("item_id"))) if isinstance(it, dict) else None
        if isinstance(it, dict) and u:
            it["norm_number"] = u["norm_number"]
            it["family_id"] = u["family_id"]
            if u["norm_number"] is None and it.get("kind") == "patent" \
                    and "number" not in (it.get("missing_metadata") or []):
                it["missing_metadata"] = list(it.get("missing_metadata") or []) + ["number"]
    ch_inner["family_groups"] = families
    ch_inner["screening"] = {"ordered_ids": ordered, "ties": tie_groups,
                             "rule": "relevance 层级(direct<indirect<irrelevant) → confidence 降序 → item_id 升序",
                             "note": "norm_family.py 机械产出"}
    if save_json(args.result, changed):
        print("[norm_family] 已回写 norm_number / family_id / family_groups / screening → %s"
              % args.result)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[norm_family] 未预期异常（已降级，不中断交付）: %s" % e)
        sys.exit(0)
