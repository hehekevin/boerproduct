#!/usr/bin/env python3
"""run_trace.py — 执行留痕包装器（sci-code-exec）。

用 subprocess 以 `python3 <script>` 运行一次分析脚本，捕获 stdout/stderr 落盘
到 /app/work/logs/run_NNN.log，并把执行痕迹（命令、python 版本、退出码、日志
路径、墙钟、开始时间）追加进 result.json 的 `execution_traces` 键（仅此键，
多脚本禁写同一键）。运行失败（非零退出 / 超时 / 无法启动）照实记录 exit_code
并保留日志——留痕的目的正是保住失败现场，失败不重写不掩盖。

定位标志：脚本校验自身与 SKILL.md 同包（../SKILL.md 存在）才视为挂载命中。

用法：
    python3 run_trace.py --script /app/work/analysis_01.py \
        --result /app/output/result.json --work-dir /app/work --timeout 120
退出码恒为 0（结论记在 execution_traces 与 stdout，不中断交付）。
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import time


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_json(path, obj):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def next_trace_id(traces):
    n = 1
    for t in traces or []:
        tid = str((t or {}).get("trace_id") or "")
        if tid.startswith("run_"):
            try:
                n = max(n, int(tid[4:]) + 1)
            except Exception:
                pass
    return "run_%03d" % n


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--script", required=True, help="待执行的分析脚本路径")
        ap.add_argument("--args", default="", help="传给脚本的附加参数（原样拆分）")
        ap.add_argument("--result", default="/app/output/result.json")
        ap.add_argument("--work-dir", default="/app/work")
        ap.add_argument("--timeout", type=int, default=120)
        args = ap.parse_args()
    except Exception as e:
        print("[run_trace] 参数解析失败（已降级）: %s" % e)
        return 0

    problems = []
    marker = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "SKILL.md")
    marker_hit = os.path.exists(marker)
    if not marker_hit:
        problems.append("定位标志未命中（脚本未与 SKILL.md 同包），仍继续执行")

    script = args.script
    script_exists = os.path.exists(script)
    if not script_exists:
        problems.append("脚本不存在: %s（仍按契约落一条失败痕迹）" % script)

    logs_dir = os.path.join(args.work_dir or ".", "logs")
    try:
        os.makedirs(logs_dir, exist_ok=True)
    except Exception as e:
        problems.append("日志目录创建失败: %s" % e)

    res = load_json(args.result)
    if not isinstance(res, dict):
        problems.append("result.json 不存在或不可解析: %s（痕迹先落到 work 侧文件）" % args.result)

    cmd_list = ["python3", script] + ([a for a in args.args.split() if a] if args.args else [])
    command = " ".join(cmd_list)
    trace_id = next_trace_id((res or {}).get("result", {}).get("execution_traces")) if res else "run_001"
    log_path = os.path.join(logs_dir, "%s.log" % trace_id)
    started_at = time.strftime("%Y-%m-%dT%H:%M:%S")

    exit_code, wall = "spawn_error", None
    tail = ""
    if script_exists:
        t0 = time.time()
        try:
            proc = subprocess.run(cmd_list, capture_output=True, timeout=args.timeout)
            wall = round(time.time() - t0, 3)
            exit_code = int(proc.returncode)
            tail = (proc.stdout or b"").decode("utf-8", "replace") + \
                   (proc.stderr or b"").decode("utf-8", "replace")
        except subprocess.TimeoutExpired:
            wall = round(time.time() - t0, 3)
            exit_code = "timeout"
            tail = "TIMEOUT after %ss" % args.timeout
            problems.append("脚本超时被终止（%ss）: %s" % (args.timeout, script))
        except FileNotFoundError as e:
            wall = round(time.time() - t0, 3)
            exit_code = "spawn_error"
            tail = "SPAWN_ERROR: %s" % e
            problems.append("无法启动 python3（%s）；请在有 python3 的环境运行" % e)
        except Exception as e:
            wall = round(time.time() - t0, 3)
            exit_code = "spawn_error"
            tail = "SPAWN_ERROR: %s" % e
            problems.append("执行异常: %s" % e)
    else:
        tail = "SCRIPT_NOT_FOUND: %s" % script

    # 日志落盘（失败现场保留）
    try:
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("# command: %s\n# started_at: %s\n# exit_code: %s\n\n%s"
                    % (command, started_at, exit_code, tail))
        log_bytes = os.path.getsize(log_path)
    except Exception as e:
        log_bytes, log_path = None, None
        problems.append("日志写盘失败: %s" % e)

    trace = {"trace_id": trace_id, "command": command, "script": script,
             "exit_code": exit_code, "log_ref": log_path, "log_bytes": log_bytes,
             "wall_seconds": wall, "started_at": started_at,
             "python_version": platform.python_version(),
             "status": "done" if exit_code == 0 else "failed"}

    wrote_result = False
    if isinstance(res, dict):
        try:
            inner = res.setdefault("result", {})
            traces = inner.setdefault("execution_traces", [])
            traces.append(trace)
            save_json(args.result, res)
            wrote_result = True
        except Exception as e:
            problems.append("回写 result.json 失败: %s" % e)

    # work 侧镜像（result.json 不可写时痕迹不丢失）
    try:
        mirror = os.path.join(args.work_dir or ".", "execution_traces.json")
        m = load_json(mirror)
        if not isinstance(m, list):
            m = []
        m.append(trace)
        save_json(mirror, m)
    except Exception as e:
        problems.append("work 镜像写盘失败: %s" % e)

    print("[run_trace] %s | exit_code=%s | wall=%ss | marker_hit=%s | 回写result=%s"
          % (trace_id, exit_code, wall if wall is not None else "n/a", marker_hit, wrote_result))
    print("  command : %s" % command)
    print("  log_ref : %s" % log_path)
    for pr in problems:
        print("  WARN: %s" % pr)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[run_trace] 未预期异常（已降级，不中断交付）: %s" % e)
        sys.exit(0)
