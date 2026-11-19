#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""译文核验脚本：段落对齐、术语一致性、数字单位保留、占位符残留、result.json 完整性。

纯 Python 标准库，无第三方依赖。用法：

  python verify_alignment.py --bilingual OUT/bilingual.md --glossary OUT/glossary.csv --result OUT/result.json [--json]

各模式（也可单独运行）：
  --mode segment      仅检查双语文件段落对齐
  --mode glossary     仅检查术语一致性
  --mode numbers      仅检查数字单位保留
  --mode placeholders 仅检查占位符残留
  --mode result       仅检查 result.json 必填字段
不带 --mode 时运行全部核验。

退出码：0 全部通过；1 存在未通过项。
"""
import argparse
import csv
import json
import re
import sys
import os

BILINGUAL_UNIT_RE = re.compile(r"^###\s+(\S+)\s+\|\s+(\S+)\s+\|\s*(.*)$")
SRC_RE = re.compile(r"^SRC:\s?(.*)$")
TGT_RE = re.compile(r"^TGT:\s?(.*)$")
NOTE_RE = re.compile(r"^NOTE:\s?(.*)$")
PLACEHOLDER_RE = re.compile(r"⟪[^⟫]*⟫")
NUMBER_RE = re.compile(r"\d+(?:\.\d+)?%?")

REQUIRED_RESULT_FIELDS = [
    "case_id", "task_type", "status", "status_reason", "source_info",
    "outputs", "stats", "verification", "uncertainty", "change_log", "notes",
]

UNTRANSLATED_TAG = "[!UNTRANSLATED"
UNCLEAR_TAG = "[!UNCLEAR"


def parse_bilingual(path):
    """解析双语对照文件，返回单元列表 [{id, location, kind, src, tgt}]。"""
    units = []
    cur = None
    field = None
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            m = BILINGUAL_UNIT_RE.match(line)
            if m:
                if cur:
                    units.append(cur)
                cur = {"id": m.group(1), "location": m.group(2),
                       "kind": m.group(3).strip(), "src": "", "tgt": "", "note": ""}
                field = None
                continue
            if cur is None:
                continue
            ms = SRC_RE.match(line)
            mt = TGT_RE.match(line)
            mn = NOTE_RE.match(line)
            if ms:
                cur["src"] += ms.group(1) + "\n"
                field = "src"
            elif mt:
                cur["tgt"] += mt.group(1) + "\n"
                field = "tgt"
            elif mn:
                cur["note"] += mn.group(1) + "\n"
                field = "note"
            elif field and line:
                cur[field] += line + "\n"
    if cur:
        units.append(cur)
    for u in units:
        u["src"] = u["src"].strip()
        u["tgt"] = u["tgt"].strip()
        u["note"] = u["note"].strip()
    return units


def check_alignment(units):
    issues = []
    ids = [u["id"] for u in units]
    if len(set(ids)) != len(ids):
        issues.append("存在重复段号: %s" % sorted({i for i in ids if ids.count(i) > 1}))
    empty_tgt = [u["id"] for u in units if not u["tgt"]]
    if empty_tgt:
        issues.append("以下单元译文为空且未标 [!UNTRANSLATED]: %s"
                      % ",".join(i for i in empty_tgt
                                 if i not in {u["id"] for u in units if UNTRANSLATED_TAG in u["tgt"]}))
    body = [u for u in units if re.match(r"^P\d+$", u["id"])]
    seq = [int(u["id"][1:]) for u in body]
    missing = sorted(set(range(1, max(seq) + 1)) - set(seq)) if seq else []
    if missing:
        issues.append("正文段号缺号: P%s" % ",P".join(str(n) for n in missing))
    return issues


def load_glossary(path):
    rows = []
    with open(path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if row.get("term_en"):
                rows.append(row)
    return rows


def check_glossary(units, glossary):
    issues = []
    locked = [g for g in glossary if g.get("status", "").strip() == "locked"]
    for g in locked:
        term = g["term_en"].strip()
        zh = g["term_zh"].strip()
        variants = [v.strip() for v in (g.get("variant") or "").split(";") if v.strip()]
        hit_units = [u for u in units if term.lower() in u["src"].lower()]
        for u in hit_units:
            if zh and zh not in u["tgt"] and UNTRANSLATED_TAG not in u["tgt"]:
                issues.append("术语不一致 [%s] 段 %s: 应含译名 '%s'" % (term, u["id"], zh))
            for v in variants:
                if v and v in u["tgt"]:
                    issues.append("禁用变体 [%s] 段 %s: 出现 '%s'" % (term, u["id"], v))
    return issues


def check_numbers(units):
    issues = []
    pure_id_ph = re.compile(r"⟪[^⟫\s]*⟫")  # 纯编号占位符如 ⟪E01⟫、⟪R12⟫，其内部数字不参与核对
    for u in units:
        if UNTRANSLATED_TAG in u["tgt"] or not u["src"] or not u["tgt"]:
            continue
        src_clean = pure_id_ph.sub(" ", u["src"])
        src_nums = set(NUMBER_RE.findall(src_clean))
        tgt_text = u["tgt"]
        # 数字核对时忽略占位符内的数字（占位符整体回填即可）
        for n in sorted(src_nums):
            # 占位符回填后数字应原样出现在译文中；千分位差异允许
            if n.replace(",", "") not in tgt_text.replace(",", ""):
                issues.append("数字缺失 段 %s: 原文 '%s' 未出现在译文" % (u["id"], n))
    return issues


def check_placeholders(units):
    issues = []
    for u in units:
        # 仅译文残留占位符视为问题（原文占位是正常保护标记）
        for ph in PLACEHOLDER_RE.findall(u["tgt"]):
            if ph not in u["src"]:
                issues.append("占位符残留 段 %s: %s（原文中不存在，回填失败）" % (u["id"], ph))
    return issues


def check_result(path):
    issues = []
    if not os.path.exists(path):
        return ["result.json 不存在: %s" % path]
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return ["result.json 解析失败: %s" % e]
    for k in REQUIRED_RESULT_FIELDS:
        if k not in data:
            issues.append("result.json 缺少必填字段: %s" % k)
    if data.get("case_id") in (None, "", "REPLACE_WITH_ACTUAL_CASE_ID"):
        issues.append("case_id 未填入实际值")
    if data.get("status") not in ("success", "partial", "failed", "blocked"):
        issues.append("status 取值非法: %r（应为 success/partial/failed/blocked）" % data.get("status"))
    if data.get("status") == "partial" and not data.get("status_reason"):
        issues.append("status 为 partial 但未填写 status_reason 与未完成清单")
    return issues


def main():
    ap = argparse.ArgumentParser(description="文献翻译译文核验")
    ap.add_argument("--bilingual", default="/app/output/bilingual.md")
    ap.add_argument("--glossary", default="/app/work/glossary.csv")
    ap.add_argument("--result", default="/app/output/result.json")
    ap.add_argument("--mode", choices=["segment", "glossary", "numbers",
                                       "placeholders", "result"], default=None)
    ap.add_argument("--json", action="store_true", help="以 JSON 输出报告")
    args = ap.parse_args()

    report = {}
    need_units = args.mode in (None, "segment", "glossary", "numbers", "placeholders")
    units = parse_bilingual(args.bilingual) if need_units else []
    if args.mode in (None, "segment"):
        report["alignment"] = check_alignment(units)
    if args.mode in (None, "glossary"):
        if os.path.exists(args.glossary):
            report["terminology"] = check_glossary(units, load_glossary(args.glossary))
        else:
            report["terminology"] = ["术语表不存在: %s" % args.glossary]
    if args.mode in (None, "numbers"):
        report["numbers"] = check_numbers(units)
    if args.mode in (None, "placeholders"):
        report["placeholders"] = check_placeholders(units)
    if args.mode in (None, "result"):
        report["result_json"] = check_result(args.result)

    report["flagged_counts"] = {
        "unclear": sum(u["tgt"].count(UNCLEAR_TAG) for u in units),
        "untranslated": sum(u["tgt"].count(UNTRANSLATED_TAG) for u in units),
    }
    report["unit_total"] = len(units)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        ok = True
        print("双语核验报告")
        print("单元总数: %d" % report["unit_total"])
        print("[!UNCLEAR] 共 %d 处, [!UNTRANSLATED] 共 %d 处" % (
            report["flagged_counts"]["unclear"], report["flagged_counts"]["untranslated"]))
        for name, issues in report.items():
            if not isinstance(issues, list):
                continue
            if issues:
                ok = False
                print("\n[%s] 未通过, %d 项问题:" % (name, len(issues)))
                for it in issues:
                    print("  - %s" % it)
            else:
                print("\n[%s] 通过" % name)
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
