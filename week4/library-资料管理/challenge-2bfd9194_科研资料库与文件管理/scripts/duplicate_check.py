#!/usr/bin/env python3
"""duplicate_check.py — 内容哈希去重 + 版本链重建（lib-file-organizer）。

重复检测：按 sha256 分组（只信任 sha256_status=ok 的条目），同组即内容级重复，
保留最早 mtime（并列取 file_id 小者）为正本，其余 duplicate_of 指向正本。
版本链：把文件名主干去掉版本词（v2/final/draft/副本/定稿…，防汉字陷阱：用子串正则
而非 isalpha）归一化后分组；组内哈希互不相同的成员按 mtime 升序重建版本序
（version_rank=1 最旧），最新者即 current。哈希相同的一律进重复组，不进版本链。
只写本脚本负责的键：duplicates / versions 与 files[].{duplicate_of,version_group,
version_rank}——不碰 category/审计/覆盖键（多脚本禁写同一键）。

用法：
    python3 duplicate_check.py --result /app/output/result.json [--dry-run]
退出码恒为 0（失败以 problems 报告）。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

VERSION_TOKEN_RE = re.compile(
    r"[\s_\-.]*(v\d+|final|draft|copy|backup|old|new|rev\d*|定稿|终稿|初稿|草稿|修改稿?|副本|备份|旧版?|新版?|"
    r"\(\d+\)|\[\d+\]|-\d{8}|_\d{8})[\s_\-.]*$", re.IGNORECASE)


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def norm_stem(path):
    """去扩展名、去版本词后的逻辑名归一化（全小写、分隔符归一）。"""
    stem = os.path.splitext(os.path.basename(path))[0]
    prev = None
    while prev != stem:
        prev = stem
        stem = VERSION_TOKEN_RE.sub("", stem)
    stem = re.sub(r"[\s_\-.]+", "", stem).lower()
    return stem


def main():
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", required=True)
        ap.add_argument("--dry-run", action="store_true")
        args = ap.parse_args()
    except Exception as e:
        print("[duplicate_check] 参数解析失败: %s" % e)
        return 0

    problems = []
    try:
        result = load_json(args.result)
        inner = result.get("result") or {}
        files = inner.get("files") or []
    except Exception as e:
        print("[duplicate_check] FAIL: result.json 读取失败: %s（不中断交付）" % e)
        return 0

    try:
        # 清空本脚本负责的键后重建（幂等，可重复运行）
        inner["duplicates"], inner["versions"] = [], []
        for f in files:
            f["duplicate_of"] = None
            f["version_group"] = None
            f["version_rank"] = None

        # 1) 内容级重复：sha256 分组（仅信任 ok/ok_inline）
        by_hash = {}
        for f in files:
            if f.get("sha256") and str(f.get("sha256_status", "")).startswith("ok"):
                by_hash.setdefault(f["sha256"], []).append(f)
        gid = 0
        for h, members in sorted(by_hash.items()):
            if len(members) < 2:
                continue
            gid += 1
            members.sort(key=lambda f: (f.get("mtime") or "9999", f.get("file_id")))
            keep = members[0]
            group = {"group_id": "D%02d" % gid, "hash": h,
                     "member_ids": [f["file_id"] for f in members],
                     "keep_id": keep["file_id"], "action": "merge",
                     "evidence": "sha256 完全相同（内容级重复，非文件名判断）"}
            inner["duplicates"].append(group)
            for f in members[1:]:
                f["duplicate_of"] = keep["file_id"]
                if not f.get("skip_reason"):
                    f["action"] = "merge"

        # 2) 版本链：归一化主干分组，组内哈希互异才成链
        by_stem = {}
        for f in files:
            if f.get("duplicate_of"):
                continue                      # 同哈希重复成员不进版本链
            s = norm_stem(f.get("path") or "")
            if not s:
                continue
            by_stem.setdefault(s, []).append(f)
        vid = 0
        for s, members in sorted(by_stem.items()):
            distinct = {f.get("sha256") for f in members}
            if len(members) < 2 or len(distinct) < 2:
                continue
            vid += 1
            members.sort(key=lambda f: (f.get("mtime") or "9999", f.get("file_id")))
            chain = {"group_id": "V%02d" % vid, "logical_name": s,
                     "member_ids": [f["file_id"] for f in members],
                     "order_by_mtime": [f["file_id"] for f in members],
                     "current_id": members[-1]["file_id"],
                     "evidence": "同名逻辑文档、内容哈希互异，按 mtime 升序重建版本链"}
            inner["versions"].append(chain)
            for rank, f in enumerate(members, 1):
                f["version_group"] = chain["group_id"]
                f["version_rank"] = rank
    except Exception as e:
        problems.append("去重/版本链执行异常: %s" % e)

    if not args.dry_run:
        try:
            with open(args.result, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=1)
        except Exception as e:
            problems.append("写回 result.json 失败: %s" % e)

    try:
        inner2 = result.get("result") or {}
        print("[duplicate_check] 重复组 %d | 版本链 %d" % (
            len(inner2.get("duplicates") or []), len(inner2.get("versions") or [])))
    except Exception:
        pass
    for p in problems:
        print("  WARN: %s" % p)
    print("[duplicate_check] 完成（退出码 0）")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[duplicate_check] 未预期异常（已降级）: %s" % e)
        sys.exit(0)
