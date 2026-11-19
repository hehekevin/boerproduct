#!/usr/bin/env python3
"""schema_guard.py — 输出契约守卫（结构 + 题面输出要求表语义 + 引文逐字回证）。

用途：在 Skill 运行的最后阶段，校验 /app/output/result.json 是否满足
case.json 的 output_contract（全部字段名）+ 本题业务 schema，并在失败时
打印缺失字段清单，供 Agent 回填后重跑。绝不改写业务内容，只做结构校验。

题面输出要求表语义核对（对应题面「Skill 运行后的输出要求」三行）：
  阅读/解析结果  → result 存在且含 objects[]；每个对象覆盖工单要求；
  证据与边界    → claims[].evidence/source_id/location 齐备；uncertainties 四类可空但键齐；
  运行状态      → status 取值合法（answered|partial|insufficient_evidence|input_error），
                  非 answered 时必须有 status_reason 说明原因与人工接管位置。

逐字回证：claims 每条 evidence.quote ≤40 字（空白归一化后），且必须能在
材料文件（--input-root 下 json/md/txt）或 result 自身表格转录中找到归一化子串；
找不到的 quote 逐条列出计 FAIL（不编造）。

退出码：恒为 0（禁止中断交付）；成败看 stdout 的 verdict 与 problems 明细。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

STATUS_ENUM = {"answered", "partial", "insufficient_evidence", "input_error"}


def norm(s) -> str:
    return re.sub(r"\s+", "", str(s or "")).lower()


def load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def contract_fields(case: dict) -> list:
    """从 case.json 提取 output_contract 字段名（兼容多种排布）。"""
    oc = case.get("output_contract") if isinstance(case, dict) else None
    if oc is None:
        return []
    if isinstance(oc, dict):
        # 通用契约：键=字段名，值=说明文字。全部键视为必填字段。
        # 兼容 {"fields":[...]} 显式列表排布。
        for key in ("fields", "required_fields", "result.json", "result"):
            v = oc.get(key)
            if isinstance(v, list):
                return [str(x) for x in v]
        return [str(k) for k in oc.keys()]
    if isinstance(oc, list):
        return [str(x) for x in oc]
    return []


class _LenientParser(argparse.ArgumentParser):
    """参数用法错误也返回 0：绝不因调用姿势问题中断交付（错误信息照实打印）。"""

    def error(self, message):
        sys.stderr.write("[%s] 参数用法错误：%s\n用法：%s\n退出码 0（交付不中断）\n"
                         % (self.prog, message, self.format_usage().strip()))
        raise SystemExit(0)


def main() -> int:
    ap = _LenientParser()
    ap.add_argument("--result", required=True)
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--extra-schema", default=None,
                    help="题目业务 schema：{\"required\":[...], \"arrays\":{\"answers\":[...子字段]}}")
    ap.add_argument("--root-array", default=None,
                    help="若 result.json 顶层是数组且每个元素都需满足同一 schema，给出元素内必需字段（逗号分隔）")
    ap.add_argument("--input-root", default=None,
                    help="材料目录（json/md/txt），用于 claims 逐字引文回证")
    ap.add_argument("--out", default=None, help="可选：把判定明细写到该 JSON 文件")
    args = ap.parse_args()

    problems = []
    if not os.path.exists(args.result):
        print("[schema_guard] verdict=fail：result.json 不存在：%s —— 已记录，退出码 0" % args.result)
        if args.out:
            with open(args.out, "w", encoding="utf-8") as f:
                json.dump({"verdict": "fail", "problems": ["result.json 不存在"]},
                          f, ensure_ascii=False, indent=1)
        return 0

    try:
        result = load_json(args.result)
    except Exception as e:
        print("[schema_guard] verdict=fail：result.json 不是合法 JSON：%s —— 已记录，退出码 0" % e)
        if args.out:
            with open(args.out, "w", encoding="utf-8") as f:
                json.dump({"verdict": "fail", "problems": ["JSON 解析失败: %s" % e]},
                          f, ensure_ascii=False, indent=1)
        return 0

    # 1) case_id 必须存在
    if isinstance(result, dict):
        if not result.get("case_id"):
            problems.append("缺少 case_id")
        # 2) output_contract 全字段
        if os.path.exists(args.case):
            try:
                case = load_json(args.case)
                for f in contract_fields(case):
                    if f not in result:
                        problems.append("缺少 output_contract 字段: %s" % f)
            except Exception as e:
                problems.append("case.json 读取失败（跳过契约校验）: %s" % e)

    # 2b) 题面输出要求表语义：运行状态合法 + 非 answered 必须说明原因
    if isinstance(result, dict):
        st = result.get("status")
        if st not in STATUS_ENUM:
            problems.append("status 取值非法: %r（应属 %s）" % (st, sorted(STATUS_ENUM)))
        elif st != "answered" and not str(result.get("status_reason") or "").strip():
            problems.append("status=%s 但缺 status_reason（题面要求说明异常原因与人工接管位置）" % st)
        inner = result.get("result")
        if not isinstance(inner, dict):
            problems.append("result 不是对象（题面「阅读/解析结果」要求结构化结果）")
        elif not isinstance(inner.get("objects"), list):
            problems.append("result.objects 缺失或不是数组（题面「阅读/解析结果」要求结构化结果）")
        unc = result.get("uncertainties")
        if isinstance(unc, dict):
            for k in ("unreported", "unverifiable", "conflicts", "human_review"):
                if k not in unc:
                    problems.append("uncertainties 缺子类: %s（题面「证据与边界」要求）" % k)
        for i, c in enumerate(result.get("claims") or []):
            if not isinstance(c, dict):
                continue
            for f in ("claim_id", "text", "kind", "source_id", "location"):
                if not str(c.get(f) or "").strip():
                    problems.append("claims[%d] 缺字段: %s（题面要求 kind/evidence/source_id/location）"
                                    % (i, f))
            if not (c.get("evidence") or []):
                problems.append("claims[%d] 缺 evidence（题面「证据与边界」要求可回证）" % i)

    # 3) 题目业务 schema
    if args.extra_schema and os.path.exists(args.extra_schema):
        sch = load_json(args.extra_schema)
        for f in sch.get("required", []):
            if isinstance(result, dict) and f not in result:
                problems.append("缺少业务字段: %s" % f)
        for arr, sub in (sch.get("arrays") or {}).items():
            v = result.get(arr) if isinstance(result, dict) else None
            if v is None:
                problems.append("缺少数组字段: %s" % arr)
                continue
            if not isinstance(v, list):
                problems.append("%s 应为数组，实际: %s" % (arr, type(v).__name__))
                continue
            for i, item in enumerate(v):
                if not isinstance(item, dict):
                    problems.append("%s[%d] 不是对象" % (arr, i))
                    continue
                for sf in sub:
                    if sf not in item:
                        problems.append("%s[%d] 缺少子字段: %s" % (arr, i, sf))

    # 4) 顶层数组模式（逐案例的题）
    if args.root_array and isinstance(result, list):
        need = [x for x in args.root_array.split(",") if x]
        for i, item in enumerate(result):
            if not isinstance(item, dict):
                problems.append("result[%d] 不是对象" % i)
                continue
            for f in need:
                if f not in item:
                    problems.append("result[%d] 缺少字段: %s" % (i, f))

    # 5) claims 逐字引文回证（quote ≤40 字 + 归一化子串匹配）
    if isinstance(result, dict):
        blob_parts = []
        inner = result.get("result") or {}
        for o in (inner.get("objects") or []) if isinstance(inner, dict) else []:
            tb = (o.get("table") or {}) if isinstance(o, dict) else {}
            for row in tb.get("rows") or []:
                blob_parts.extend(str(c) for c in row)
        if args.input_root and os.path.isdir(args.input_root):
            for root, _d, files in os.walk(args.input_root):
                for fn in files:
                    if fn.lower().endswith((".json", ".md", ".txt")):
                        try:
                            with open(os.path.join(root, fn), "r", encoding="utf-8",
                                      errors="replace") as f:
                                blob_parts.append(f.read())
                        except Exception:
                            pass
        blob = norm(" ".join(blob_parts))
        for i, c in enumerate(result.get("claims") or []):
            if not isinstance(c, dict):
                continue
            cid = c.get("claim_id") or i
            for j, ev in enumerate(c.get("evidence") or []):
                q = ev.get("quote") if isinstance(ev, dict) else ev
                qn = norm(q)
                if not qn:
                    problems.append("claims[%s].evidence[%d] quote 为空" % (cid, j))
                    continue
                if len(qn) > 40:
                    problems.append("claims[%s].evidence[%d] quote 超过 40 字（实际 %d）" % (cid, j, len(qn)))
                if blob and qn not in blob:
                    problems.append("claims[%s].evidence[%d] quote 无法在材料/表格中逐字回证: %r"
                                    % (cid, j, str(q)[:40]))

    verdict = "pass" if not problems else "fail"
    if args.out:
        try:
            with open(args.out, "w", encoding="utf-8") as f:
                json.dump({"verdict": verdict, "problems": problems},
                          f, ensure_ascii=False, indent=1)
        except Exception:
            pass

    if problems:
        print("[schema_guard] verdict=fail（%d 处）——已记录，退出码 0，交付不中断:" % len(problems))
        for p in problems[:40]:
            print("  - %s" % p)
        if len(problems) > 40:
            print("  ... 共 %d 处" % len(problems))
    else:
        print("[schema_guard] verdict=pass: 结构完整（case_id=%s）" % (
            result.get("case_id") if isinstance(result, dict) else "(array)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
