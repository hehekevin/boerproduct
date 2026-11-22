#!/usr/bin/env python3
"""param_check.py — 关键参数可行域/耦合约束数值校验器（exp-param-domain 核心工具）。

对 result.json 做真实算术校验（finite domains + real arithmetic）：
  1. 域校验：parameters[].current 是否落在 range[下限,上限] 内（硬违规）；
     step 给定时做步进对齐检查（警告级）。
  2. 耦合约束算术求值：constraints[].expression 用受限 AST 求值器
     （白名单：数字/名称/四则运算/一元负号/比较/and-or，函数调用与属性访问一律
     拒绝）在当前值映射下求值；求值为假或不可求值（未知参数名/非法语法/黑名单
     节点）记为违规并给出明细。
  3. 步进建议：每个参数若声明 step，核对 range 下限与当前值是否符合步进栅格。

参数变量名以 parameters[].name 整串精确匹配。参数名允许中文（如「反应温度」）、
连字符（如「P-01」）：求值前把参数名按长度降序整串替换为安全占位符 v0/v1/…，
变量名匹配不使用 str.isalpha()（汉字 isalpha=True、连字符被拆词是已知陷阱）。

**键归属**：本脚本只写 result.feasibility_check；其余键一律不碰。
本工具做的是「方案声明口径下的算术自洽性校验」：变量映射来自 result.json 内
登记的当前值，属前瞻性规划场景，不代表实测实验室数据、不冒充设备供应商报价
或安全认证。

用法：
    python3 param_check.py --result /app/output/result.json [--out 报告路径] [--emit-into]
退出码恒为 0（结论记在 feasibility_check 与 stdout，不中断交付）。
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import sys

ALLOWED_NODES = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.Name,
                 ast.Compare, ast.BoolOp, ast.Load,
                 ast.Add, ast.Sub, ast.Mult, ast.Div, ast.USub, ast.UAdd,
                 ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Eq, ast.NotEq,
                 ast.And, ast.Or)
BIN_OPS = {ast.Add, ast.Sub, ast.Mult, ast.Div}
CMP_OPS = {ast.Lt: lambda a, b: a < b, ast.LtE: lambda a, b: a <= b,
           ast.Gt: lambda a, b: a > b, ast.GtE: lambda a, b: a >= b,
           ast.Eq: lambda a, b: a == b, ast.NotEq: lambda a, b: a != b}


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_json(path, obj):
    try:
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)
        return True
    except Exception as e:
        print("[param_check] 写盘失败 %s: %s" % (path, e))
        return False


def is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _eval_node(node, variables):
    """受限 AST 递归求值。返回 (ok, value_or_error)。"""
    if not isinstance(node, ALLOWED_NODES):
        return False, "黑名单节点: %s" % type(node).__name__
    if isinstance(node, ast.Expression):
        return _eval_node(node.body, variables)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return True, float(node.value)
        return False, "常量须为数字: %r" % node.value
    if isinstance(node, ast.Name):
        if node.id in variables:
            return True, float(variables[node.id])
        return False, "未知参数名: %r" % node.id
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        ok, v = _eval_node(node.operand, variables)
        if not ok:
            return ok, v
        return True, -v if isinstance(node.op, ast.USub) else v
    if isinstance(node, ast.BinOp) and type(node.op) in BIN_OPS:
        ok1, a = _eval_node(node.left, variables)
        ok2, b = _eval_node(node.right, variables)
        if not ok1:
            return ok1, a
        if not ok2:
            return ok2, b
        op = type(node.op)
        try:
            if op is ast.Add:
                return True, a + b
            if op is ast.Sub:
                return True, a - b
            if op is ast.Mult:
                return True, a * b
            if b == 0:
                return False, "除零"
            return True, a / b
        except Exception as e:
            return False, "算术异常: %s" % e
    if isinstance(node, ast.Compare) and len(node.ops) >= 1 and type(node.ops[0]) in CMP_OPS:
        ok1, a = _eval_node(node.left, variables)
        ok2, b = _eval_node(node.comparators[0], variables)
        if not ok1:
            return ok1, a
        if not ok2:
            return ok2, b
        return True, bool(CMP_OPS[type(node.ops[0])](a, b))
    if isinstance(node, ast.BoolOp) and isinstance(node.op, (ast.And, ast.Or)):
        vals = []
        for sub in node.values:
            ok, v = _eval_node(sub, variables)
            if not ok:
                return ok, v
            vals.append(bool(v))
        return True, all(vals) if isinstance(node.op, ast.And) else any(vals)
    return False, "不支持的语法: %s" % type(node).__name__


def eval_expr(expression, variables):
    """安全求值入口：任何异常都转为 (False, 错误说明)，绝不抛出。"""
    try:
        tree = ast.parse(str(expression), mode="eval")
    except Exception as e:
        return False, "语法错误: %s" % e
    return _eval_node(tree, variables)


def rewrite_expr(expression, names):
    """把表达式中出现的参数名整串替换为合法占位符 v0/v1/…。

    参数名可含连字符（P-01）、中文（反应温度）等非标识符字符，直接进
    ast.parse 会把 `P-01` 拆成 `P` 减 `01` 触发语法错误/leading zeros 错误；
    此处按名字长度降序做整串替换（避免短名前缀吞掉长名），不使用 isalpha 类
    启发式判断。
    """
    expr = str(expression)
    ids = sorted((str(i) for i in names if str(i)), key=len, reverse=True)
    ph_map = {}
    for i, nm in enumerate(ids):
        ph = "v%d" % i
        if nm and nm in expr:
            ph_map[nm] = ph
            expr = expr.replace(nm, ph)
    return expr, ph_map


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", required=True)
        ap.add_argument("--out", default=None, help="校验报告落盘路径")
        ap.add_argument("--emit-into", action="store_true",
                        help="把 feasibility_check 回写 result.feasibility_check")
        args = ap.parse_args()
    except Exception as e:
        print("[param_check] 参数解析失败（已降级）: %s" % e)
        return 0

    res = load_json(args.result)
    if not isinstance(res, dict) or not isinstance(res.get("result"), dict):
        print("[param_check] FAIL: result.json 不存在/不可解析: %s（不中断交付）" % args.result)
        return 0
    inner = res["result"]
    params = [p for p in (inner.get("parameters") or []) if isinstance(p, dict)]
    cons = [c for c in (inner.get("constraints") or []) if isinstance(c, dict)]

    violations, warnings = [], []
    domain_bad = 0
    cur_map = {str(p.get("name")): p.get("current")
               for p in params if is_num(p.get("current"))}

    # 1. 参数域校验（当前值落 range）
    for i, p in enumerate(params):
        nm = str(p.get("name") or "parameters[%d]" % i)
        rng = p.get("range") if isinstance(p.get("range"), (list, tuple)) else None
        if not rng or len(rng) < 2 or not (is_num(rng[0]) and is_num(rng[1])):
            warnings.append("参数 %s 可行域 range 缺失或非法，跳过域校验" % nm)
        else:
            lo, hi = float(rng[0]), float(rng[1])
            if lo > hi:
                warnings.append("参数 %s range 下限>上限 (%s>%s)，视为声明错误" % (nm, lo, hi))
            cv = p.get("current")
            if is_num(cv) and not (lo <= float(cv) <= hi):
                domain_bad += 1
                violations.append({"type": "current_out_of_domain", "target": nm,
                                   "detail": "当前值 %s 超出可行域 [%s, %s]" % (cv, lo, hi)})
        step = p.get("step")
        if is_num(step) and float(step) > 0 and rng and len(rng) >= 2 \
                and is_num(rng[0]) and is_num(p.get("current")):
            off = abs(float(p["current"]) - float(rng[0])) % float(step)
            if off > 1e-9 and abs(off - float(step)) > 1e-9:
                warnings.append("参数 %s 当前值 %s 与步进 %s 不对齐（可执行性提示）"
                                % (nm, p.get("current"), step))

    # 2. 耦合约束算术求值（当前值映射）
    n_eval = 0
    n_declared = 0
    for i, c in enumerate(cons):
        cid = c.get("cid") or "constraints[%d]" % i
        if c.get("kind") == "none_declared":
            continue
        n_declared += 1
        expr_raw = str(c.get("expression") or "").strip()
        if not expr_raw:
            warnings.append("%s expression 为空，跳过求值" % cid)
            continue
        expr, ph_map = rewrite_expr(expr_raw, cur_map.keys())
        variables = {ph_map.get(k, k): v for k, v in cur_map.items()}
        ok, val = eval_expr(expr, variables)
        if not ok:
            violations.append({"type": "constraint_unevaluable", "target": cid,
                               "detail": str(val)})
            continue
        n_eval += 1
        if val is False:
            violations.append({"type": "constraint_violated", "target": cid,
                               "detail": "当前值映射下不成立: %s" % expr_raw})

    all_in_domain = domain_bad == 0
    hard_viol = [v for v in violations if v["type"] in ("current_out_of_domain",
                                                        "constraint_violated",
                                                        "constraint_unevaluable")]
    feas = {
        "tool": "scripts/param_check.py",
        "scenario_note": "算术校验基于 result.json 内登记的可行域/当前值，"
                         "属前瞻性规划口径，不代表实测实验室数据或供应商确认",
        "parameters_checked": len(params),
        "constraints_declared": n_declared,
        "constraint_evaluations": n_eval,
        "checked_count": len(params) + n_eval,
        "all_within_domain": all_in_domain,
        "all_constraints_satisfied": not any(v["type"] in ("constraint_violated",
                                                           "constraint_unevaluable")
                                             for v in violations),
        "violations": violations,
        "warnings": warnings,
        "verdict": "PASS" if not hard_viol else "FAIL",
        "summary": "域越界 %d，违规 %d 条，警告 %d 条"
                   % (domain_bad, len(hard_viol), len(warnings)),
    }

    out_path = args.out or os.path.join(os.path.dirname(os.path.abspath(args.result)) or ".",
                                        "..", "work", "param_check.json")
    save_json(out_path, feas)
    if args.emit_into:
        try:
            cur = load_json(args.result)
            if isinstance(cur, dict) and isinstance(cur.get("result"), dict):
                cur["result"]["feasibility_check"] = feas
                save_json(args.result, cur)
        except Exception as e:
            print("[param_check] 回写 result.json 失败: %s" % e)

    print("[param_check] %s：%s" % (feas["verdict"], feas["summary"]))
    for v in violations[:20]:
        print("  VIOLATION[%s] %s: %s" % (v["type"], v["target"], v["detail"]))
    for w in warnings[:20]:
        print("  WARN: %s" % w)
    print("[param_check] 报告落盘: %s" % os.path.abspath(out_path))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[param_check] 未预期异常（已降级，不中断交付）: %s" % e)
        sys.exit(0)