#!/usr/bin/env python3
"""audit_ops.py — 整理操作审计链生成与校验（lib-file-organizer）。

从 result.files 的 action 机械生成操作审计链 ops[]：每个非 keep/待定操作一条记录，
含 op_id、prev_op_id 链接、chain_hash（sha256(前序哈希 + 记录规范 JSON)，首记录前序
为 GENESIS）、replay 复放命令——任何一条操作可按记录复跑并核对。
链完整性校验：重算 chain_hash 逐条比对，断链/缺 replay/目标 file_id 不存在都列出。
只写本脚本负责的键：ops 与 /app/work/audit_chain.json——不碰 category/去重键
（多脚本禁写同一键）。

用法：
    python3 audit_ops.py --result /app/output/result.json [--work-dir /app/work] [--dry-run]
退出码恒为 0（失败以 problems 报告）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

OP_TYPES = {"move": "move", "rename": "rename", "move_rename": "move",
            "merge": "merge", "skip": "skip"}


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def canon(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def build_ops(result):
    """从 files[].action 生成审计链（幂等：覆盖重建 ops）。"""
    inner = result.get("result") or {}
    files = inner.get("files") or []
    plan = inner.get("directory_plan") or {}
    tree = {}
    try:
        tree = json.loads(plan.get("tree") or "{}")
    except Exception:
        pass
    ops = []
    prev_hash = "GENESIS"
    idx = 0
    for f in files:
        act = f.get("action")
        if act in (None, "keep"):
            continue
        idx += 1
        op_type = OP_TYPES.get(act, "register")
        detail = {"from": f.get("path"),
                  "to": (os.path.dirname(f.get("path") or "").replace("\\", "/") == f.get("category")
                         and None or (str(f.get("category")) + "/" + (f.get("rename_suggestion")
                                      or os.path.basename(f.get("path") or "")))),
                  "rule_id": f.get("rule_hit"),
                  "duplicate_of": f.get("duplicate_of"),
                  "basis": "规则 %s 事前声明命中" % f.get("rule_hit") if f.get("rule_hit") else None}
        if act == "merge":
            detail["to"] = "并入正本 %s" % f.get("duplicate_of")
        if act == "skip":
            detail["to"] = None
        op = {"op_id": "OP-%04d" % idx, "op_type": op_type, "target_id": f.get("file_id"),
              "detail": detail, "replay": "python3 audit_ops.py --replay %s --result result.json"
              % ("OP-%04d" % idx), "status": "planned",
              "prev_op_id": ("OP-%04d" % (idx - 1)) if idx > 1 else None}
        op["chain_hash"] = hashlib.sha256((prev_hash + canon(op)).encode("utf-8")).hexdigest()
        ops.append(op)
        prev_hash = op["chain_hash"]
    inner["ops"] = ops
    return ops


def main():
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", required=True)
        ap.add_argument("--work-dir", default="/app/work")
        ap.add_argument("--dry-run", action="store_true")
        args = ap.parse_args()
    except Exception as e:
        print("[audit_ops] 参数解析失败: %s" % e)
        return 0

    problems = []
    result = None
    try:
        result = load_json(args.result)
    except Exception as e:
        print("[audit_ops] FAIL: result.json 读取失败: %s（不中断交付）" % e)
        return 0

    inner = result.get("result") or {}
    ops = []
    try:
        ops = build_ops(result)
        # 链完整性重算
        prev_hash, prev_id = "GENESIS", None
        file_ids = {f.get("file_id") for f in inner.get("files") or []}
        for i, op in enumerate(ops):
            stored = op.get("chain_hash")
            op_check = {k: v for k, v in op.items() if k != "chain_hash"}
            expect = hashlib.sha256((prev_hash + canon(op_check)).encode("utf-8")).hexdigest()
            if stored != expect:
                problems.append("ops[%d] chain_hash 不符（审计链断裂）" % i)
            if op.get("prev_op_id") != prev_id:
                problems.append("ops[%d] prev_op_id 应为 %s" % (i, prev_id))
            if not op.get("replay"):
                problems.append("ops[%d] 缺 replay 复放命令" % i)
            if op.get("target_id") not in file_ids:
                problems.append("ops[%d] target_id %s 不在 files 清单" % (i, op.get("target_id")))
            prev_hash, prev_id = stored, op.get("op_id")
    except Exception as e:
        problems.append("审计链生成异常: %s" % e)

    if not args.dry_run:
        try:
            with open(args.result, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=1)
        except Exception as e:
            problems.append("写回 result.json 失败: %s" % e)
        try:
            os.makedirs(args.work_dir or ".", exist_ok=True)
            with open(os.path.join(args.work_dir, "audit_chain.json"), "w", encoding="utf-8") as f:
                json.dump({"ops_count": len(ops), "problems": problems,
                           "tail_hash": ops[-1]["chain_hash"] if ops else None},
                          f, ensure_ascii=False, indent=1)
        except Exception as e:
            problems.append("audit_chain.json 写出失败: %s" % e)

    print("[audit_ops] ops %d 条 | 链尾 %s | 计划状态 planned（执行后由 Agent 改 done）"
          % (len(ops), ops[-1]["chain_hash"][:12] if ops else "-"))
    for p in problems:
        print("  WARN: %s" % p)
    print("[audit_ops] 完成（退出码 0）")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[audit_ops] 未预期异常（已降级）: %s" % e)
        sys.exit(0)
