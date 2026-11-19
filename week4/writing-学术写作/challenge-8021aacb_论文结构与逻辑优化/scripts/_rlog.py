#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_rlog.py — 运行日志：自动记录各脚本调用，供 efficiency 计数（不写 result.json）"""
import json, os, time


def _log_path():
    for p in ("/app/work/run_log.jsonl",
              os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "run_log.local.jsonl")):
        try:
            d = os.path.dirname(p)
            if d:
                os.makedirs(d, exist_ok=True)
            return p
        except Exception:
            continue
    return "run_log.local.jsonl"


def log_call(tool, argv=None, seconds=None, extra=None):
    try:
        row = {"ts": round(time.time(), 3), "tool": tool, "argv": argv or [],
               "seconds": round(seconds, 3) if seconds is not None else None,
               "extra": extra or {}}
        with open(_log_path(), "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass


def read_log(path=None):
    p = path or _log_path()
    rows = []
    try:
        for line in open(p, encoding="utf-8"):
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
    except Exception:
        pass
    return rows
