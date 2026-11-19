#!/usr/bin/env python3
"""classify_files.py — 按事前声明的规则机械归类 + 重命名建议（lib-file-organizer）。

读取 result.json 与 /app/work/classification_rules.json（必须已 declared_at 事前声明），
按 priority 升序对每个文件做规则匹配（ext / path_contains / name_contains 任一命中，
取首个命中；全不中归 fallback_category），机械写出 category 与 rule_hit；
按命名规范生成 rename_suggestion（正则校验，不合规范则留空并登记）。
中文匹配一律用子串包含（防 str.isalpha 对汉字返回 True 的陷阱）。
只写本脚本负责的键：files[].{category,rule_hit,rename_suggestion,action} 与
directory_plan——不碰哈希/去重/版本/审计键（多脚本禁写同一键）。

用法：
    python3 classify_files.py --result /app/output/result.json \
        --rules /app/work/classification_rules.json [--dry-run]
退出码恒为 0（失败以 problems 报告）。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def rule_matches(rule, path, name, ext):
    """三类条件任一命中即算命中；全部用子串/集合比较，不用 isalpha。"""
    m = rule.get("match") or {}
    e = (m.get("ext") or [])
    if e and (("." + ext.lower()) in {x.lower() if x.startswith(".") else "." + x.lower() for x in e}):
        return True
    for sub in (m.get("path_contains") or []):
        if sub and sub in path:
            return True
    for sub in (m.get("name_contains") or []):
        if sub and sub in name:
            return True
    return False


def suggest_name(path, category, conv):
    """按命名规范生成建议名：清洗非法字符 + 规范化版本词 + 模板/正则校验。"""
    name = os.path.basename(path)
    stem, ext = os.path.splitext(name)
    ext = ext.lower()
    stem = re.sub(r"\s+", "_", stem.strip())
    stem = re.sub(r'[\\/:*?"<>|]', "_", stem)          # 非法字符替换
    stem = re.sub(r"_+", "_", stem).strip("_")
    pat = conv.get("pattern") if isinstance(conv, dict) else None
    regex = conv.get("regex") if isinstance(conv, dict) else None
    if pat and "{stem}" in pat:
        cand = pat.replace("{category}", str(category or "")).replace("{stem}", stem).replace("{ext}", ext)
    else:
        cand = "%s_%s%s" % (category, stem, ext) if category else stem + ext
    ok = True
    if regex:
        try:
            ok = re.search(regex, cand) is not None
        except re.error:
            ok = False
    return (cand if ok else None)


def main():
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", required=True)
        ap.add_argument("--rules", default="/app/work/classification_rules.json")
        ap.add_argument("--dry-run", action="store_true")
        args = ap.parse_args()
    except Exception as e:
        print("[classify_files] 参数解析失败: %s" % e)
        return 0

    problems, applied = [], False
    result, rules = None, None
    try:
        result = load_json(args.result)
    except Exception as e:
        print("[classify_files] FAIL: result.json 读取失败: %s（不中断交付）" % e)
        return 0
    try:
        if os.path.exists(args.rules):
            rules = load_json(args.rules)
        else:
            problems.append("规则文件不存在: %s（归类暂停，须先事前声明）" % args.rules)
    except Exception as e:
        problems.append("规则文件读取失败: %s" % e)

    try:
        inner = result.get("result") or {}
        files = inner.get("files") or []
        decl = inner.get("classification_rules") or {}
        # 事前声明闸门：result 与规则文件必须一致且已声明
        if not rules:
            pass
        elif not rules.get("declared_at"):
            problems.append("classification_rules.declared_at 为空：规则未事前声明，禁止归类")
        elif decl and decl.get("declared_at") and rules.get("declared_at") != decl.get("declared_at"):
            problems.append("规则文件与 result.classification_rules 的 declared_at 不一致，禁止归类")
        else:
            rlist = sorted(rules.get("rules") or [], key=lambda r: (r.get("priority") or 999, str(r.get("rule_id"))))
            if not rlist:
                problems.append("规则列表为空，禁止归类")
            else:
                ids = {str(r.get("rule_id")) for r in rlist}
                if len(ids) != len(rlist):
                    problems.append("rule_id 重复，先修复规则再归类")
                else:
                    fallback = rules.get("fallback_category") or "unsorted"
                    conv = rules.get("naming_convention") or {}
                    tree = {}
                    for f in files:
                        if f.get("skip_reason"):
                            f["action"] = f.get("action") or "skip"
                            f["judged"] = True
                            continue
                        name = os.path.basename(f.get("path") or "")
                        ext = f.get("file_type") or ""
                        hit = None
                        for r in rlist:
                            if rule_matches(r, f.get("path") or "", name, ext):
                                hit = r
                                break
                        f["category"] = str(hit["category"]) if hit else fallback
                        f["rule_hit"] = str(hit["rule_id"]) if hit else "fallback"
                        sug = suggest_name(f.get("path") or "", f["category"], conv)
                        cur = name
                        f["rename_suggestion"] = sug if (sug and sug != cur) else None
                        target_dir = f["category"]
                        parent = os.path.dirname(f.get("path") or "").replace("\\", "/")
                        moves = (parent != target_dir)
                        renames = bool(f["rename_suggestion"])
                        f["action"] = ("move_rename" if (moves and renames) else
                                       "move" if moves else "rename" if renames else "keep")
                        f["judged"] = True
                        tree[f["category"]] = tree.get(f["category"], 0) + 1
                    inner["directory_plan"] = {
                        "target_root": conv.get("pattern") and conv.get("target_root") or None,
                        "tree": json.dumps(tree, ensure_ascii=False, sort_keys=True),
                        "note": "按分类规则事前声明生成的目标目录树（category/ 两级）",
                    }
                    applied = True
    except Exception as e:
        problems.append("归类执行异常: %s" % e)

    if not args.dry_run and applied:
        try:
            with open(args.result, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=1)
        except Exception as e:
            problems.append("写回 result.json 失败: %s" % e)

    n_cat = sum(1 for f in (result.get("result") or {}).get("files") or [] if f.get("category"))
    print("[classify_files] applied=%s | 已归类 %d/%d | 规则 %s" % (
        applied, n_cat, len((result.get("result") or {}).get("files") or []),
        (rules or {}).get("declared_at")))
    for p in problems:
        print("  WARN: %s" % p)
    print("[classify_files] 完成（退出码 0，结论见上方 WARN/applied）")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[classify_files] 未预期异常（已降级）: %s" % e)
        sys.exit(0)
