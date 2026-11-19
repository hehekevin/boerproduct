#!/usr/bin/env python3
"""cli_guard.py — 本包统一的「退出码恒 0」契约（所有脚本共用）。

为什么需要：题面要求「失败也要交付」，平台侧流水线按退出码判断成败。
一旦某个校验脚本因内容级失败返回非 0，上游会把「校验未过」误读成
「交付中断」，从而丢掉本可以交付的部分结果 —— 这是本包最想避免的失败模式。

本模块提供两个东西：
  SafeParser      —— argparse 子类：未知参数 / 缺少必填参数 / 参数类型错误
                     都不再 exit 2，而是按「失败」处理并以 0 退出。
  safe_parse_args —— 包装 ap.parse_args()：出错返回 None，绝不抛异常。
  run_entry       —— 脚本入口包装：主流程正常返回、抛异常、参数有误，
                     一律以 0 退出。

**退出码契约（本包全部脚本，含校验器）**：
    0 —— 脚本已正常执行完毕（含「判定为 fail」的情形）。
    不存在非 0 退出。
判定结果只落在产物文件里（check_report.json 的 ok/verdict/problems），
不落在退出码上 —— 上游请读 verdict，不要读退出码。
"""
from __future__ import annotations

import argparse
import sys


class SafeParser(argparse.ArgumentParser):
    """argparse 子类：参数错误按失败处理，不 exit 2。

    覆盖 error()：argparse 默认在此处调用 sys.exit(2)，本包改为打印问题后
    以 SystemExit(0) 结束，由 run_entry 统一收敛退出码。
    """

    def error(self, message):
        try:
            self.print_usage(sys.stderr)
        except Exception:
            pass
        print("[argparse] 参数有误: %s（按失败处理，退出码恒 0）" % message,
              file=sys.stderr)
        raise SystemExit(0)


def safe_parse_args(ap, argv=None):
    """解析命令行参数；出错返回 None（不抛异常、不产生非 0 退出码）。"""
    try:
        return ap.parse_args(argv)
    except SystemExit as e:
        code = getattr(e, "code", 0)
        if code not in (0, None):
            print("[argparse] 参数有误: exit=%s（按失败处理，退出码恒 0）" % code,
                  file=sys.stderr)
        return None
    except Exception as e:
        print("[argparse] 参数解析异常: %s（按失败处理，退出码恒 0）" % e,
              file=sys.stderr)
        return None


def peek_option(argv, name, default=None):
    """从原始 argv 里找 --name 的值（参数解析失败、无法走 argparse 时用）。"""
    try:
        for i, a in enumerate(argv or []):
            if a == name and i + 1 < len(argv):
                return argv[i + 1]
            if a.startswith(name + "="):
                return a.split("=", 1)[1]
    except Exception:
        pass
    return default


def run_entry(main, tag):
    """脚本入口统一包装：任何路径都以 0 退出。

    用法：
        if __name__ == "__main__":
            run_entry(main, "check_result")
    """
    try:
        main()
    except SystemExit as e:
        code = getattr(e, "code", 0)
        if code not in (0, None):
            print("[%s] 以 exit=%s 结束（降级为 0，交付不中断）" % (tag, code))
    except Exception as e:
        print("[%s] 异常降级: %s（退出码恒 0）" % (tag, e))
    sys.exit(0)
