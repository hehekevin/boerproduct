#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_rlog.py — 运行日志（效率计数的自动采集源）

每个脚本在入口/出口调用 log_call()，向 $ACWRITE_RUNLOG（默认 /app/work/run_log.jsonl）
追加一行 JSON：工具名、参数、耗时、模式（full/ablate）、附加计数。
build_result.py 与 gain_evidence.py 读取该日志自动统计工具调用数/步骤数/耗时，
使「效率增益」有真实运行计数而非自述数字。

设计原则：
- 零外部依赖（仅标准库）。
- 写日志失败绝不抛异常（不得阻断交付）；写不进去时下游效率字段按 gate=not_provided 如实留空。
"""
import json
import os
import time

DEFAULT_LOG = "/app/work/run_log.jsonl"


def log_path():
    return os.environ.get("ACWRITE_RUNLOG") or DEFAULT_LOG


def log_call(tool, argv=None, seconds=None, mode=None, extra=None):
    """追加一条工具调用记录。返回记录 dict；任何异常都被吞掉（返回 None）。"""
    try:
        rec = {
            "tool": tool,
            "ts": time.time(),
            "mode": mode or os.environ.get("ACWRITE_MODE") or "full",
        }
        if argv is not None:
            rec["argv"] = [str(a) for a in argv][:24]
        if seconds is not None:
            rec["seconds"] = round(float(seconds), 3)
        if extra:
            rec["extra"] = extra
        p = log_path()
        d = os.path.dirname(p)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return rec
    except Exception:
        return None


def read_log(path=None):
    """读取日志为 list；文件不存在或损坏时返回 []（不抛异常）。"""
    p = path or log_path()
    rows = []
    try:
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        return []
    return rows
