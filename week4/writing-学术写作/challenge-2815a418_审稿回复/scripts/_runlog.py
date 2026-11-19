#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_runlog.py — 运行事件采集（零依赖，失败静默）

每个脚本在 main() 结束时调用 log_event()，把「脚本名 / 事件 / 耗时 / 结果」追加到
run_log.jsonl。build_result.py finalize 据此汇总真实 efficiency 计数
（脚本调用次数、按脚本分组、墙钟耗时、阶段数），不靠模型自述。

- 路径：环境变量 REBUTTAL_RUNLOG，默认 /app/work/run_log.jsonl
- 写不了（目录不存在/只读）时静默跳过，绝不因此让脚本失败
"""
import json
import os
import time


def _log_path():
    p = os.environ.get("REBUTTAL_RUNLOG") or "/app/work/run_log.jsonl"
    if os.name == "nt" and p.startswith("/app/"):
        p = os.path.join(os.getcwd(), "run_log.jsonl")
    return p


def log_event(script, event, seconds=None, ok=True, **extra):
    """追加一条运行事件。任何异常都被吞掉——采集失败不影响主流程。"""
    try:
        rec = {"script": script, "event": event, "ok": bool(ok),
               "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
        if seconds is not None:
            try:
                rec["seconds"] = round(float(seconds), 3)
            except Exception:
                pass
        if extra:
            rec["detail"] = extra
        p = _log_path()
        d = os.path.dirname(p)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass
    return rec


def read_events(path=None):
    """读取运行事件；文件不存在返回空列表。"""
    p = path or _log_path()
    out = []
    try:
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        return []
    return out
