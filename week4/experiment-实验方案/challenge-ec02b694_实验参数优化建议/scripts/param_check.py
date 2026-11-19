#!/usr/bin/env python3
"""param_check.py — 约束感知数值可行性校验器（exp-param-optimize 核心工具）。

对 result.json 做真实算术校验（finite domains + real arithmetic）：
  1. 参数域校验：parameters[].current_value 与建议值是否落在声明域
     [domain.min, domain.max] 内（硬违规）；step 给定时做步进对齐检查（警告级）。
  2. 耦合约束算术求值：coupling_constraints[].expression 用受限 AST 求值器
     （白名单：数字/名称/四则运算/一元负号/比较/and-or，函数调用与属性访问一律
     拒绝）分别在「当前值」与「建议执行值」两套变量映射下求值；建议执行值 = 
     set_to→suggested_value；up/down→current_value±magnitude；hold/缺省→current_value。
     求值为假或不可求值（未知参数名/非法语法/黑名单节点）记为违规并给出明细。
  3. 建议值一致性：direction=hold 但 suggested_value 与 current_value 不符等
     口径冲突记警告。

注意：参数 id 允许中文（如「反应温度」），标识符解析走 ast.Name 节点，
**不使用 str.isalpha() 判断**（isalpha 对汉字返回 True 但对「温度-1」这类
含连字符/数字的 id 会误判，混淆变量名与词干），变量名一律整串精确匹配。

**键归属**：本脚本只写 result.feasibility_check；其余键一律不碰。
本工具做的是「方案声明口径下的算术自洽性校验」：变量映射来自 result.json
内登记的当前值与建议值，属于前瞻性规划场景，不代表实测实验室数据、不冒充
设备供应商报价或安全认证。

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
        # 变量名整串精确匹配（参数 id 可含中文/连字符，不用 isalpha 类启发式）
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


def rewrite_expr(expression, param_ids):
    """把表达式中出现的参数 id 整串替换为合法占位符 v0/v1/…。

    参数 id 可含连字符（P-01）、中文（反应温度）等非标识符字符，直接进
    ast.parse 会把 `P-01` 拆成 `P` 减 `01` 触发语法错误；此处按 id 长度
    降序做整串替换（避免 P-0 吞掉 P-01 的前缀），变量名匹配不使用
    str.isalpha() 类启发式判断。
    """
    expr = str(expression)
    ids = sorted((str(i) for i in param_ids if str(i)), key=len, reverse=True)
    ph_map = {}
    for i, pid in enumerate(ids):
        ph = "v%d" % i
        if pid and pid in expr:
            ph_map[pid] = ph
            expr = expr.replace(pid, ph)
    return expr, ph_map


def suggested_map(params, suggs):
    """按建议构造「建议执行值」映射。"""
    cur = {str(p.get("param_id")): p.get("current_value")
           for p in params if is_num(p.get("current_value"))}
    out = dict(cur)
    for s in suggs:
        if not isinstance(s, dict):
            continue
        pid = str(s.get("param_id") or "")
        if pid not in cur:
            continue
        d = s.get("direction")
        if d == "set_to" and is_num(s.get("suggested_value")):
            out[pid] = float(s["suggested_value"])
        elif d in ("up", "down") and is_num(s.get("magnitude")):
            sign = 1.0 if d == "up" else -1.0
            out[pid] = float(cur[pid]) + sign * float(s["magnitude"])
    return out


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", required=True)
        ap.add_argument("--out", default=None, help="校验报告落盘路径")
        ap.add_argument("--emit-into", action="store_true",
                        help="把 feasibility_check 回写 result.json 的 result.feasibility_check")
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
    suggs = [s for s in (inner.get("optimization_suggestions") or []) if isinstance(s, dict)]
    cons = [c for c in (inner.get("coupling_constraints") or []) if isinstance(c, dict)]

    violations, warnings = [], []
    domain_bad_cur = domain_bad_sug = 0
    cur_map = suggested_map(params, suggs)

    # 1. 参数域校验（当前值 + 建议执行值）
    for i, p in enumerate(params):
        pid = str(p.get("param_id") or "parameters[%d]" % i)
        dom = p.get("domain") if isinstance(p.get("domain"), dict) else {}
        lo, hi = dom.get("min"), dom.get("max")
        if not (is_num(lo) and is_num(hi)):
            warnings.append("参数 %s 域声明缺失或非法，跳过域校验" % pid)
            continue
        cv = p.get("current_value")
        if is_num(cv) and not (float(lo) <= float(cv) <= float(hi)):
            domain_bad_cur += 1
            violations.append({"type": "current_out_of_domain", "target": pid,
                               "detail": "当前值 %s 超出声明域 [%s, %s]" % (cv, lo, hi)})
        sv = cur_map.get(pid)
        if is_num(sv) and not (float(lo) <= float(sv) <= float(hi)):
            domain_bad_sug += 1
            violations.append({"type": "suggested_out_of_domain", "target": pid,
                               "detail": "建议执行值 %s 超出声明域 [%s, %s]" % (sv, lo, hi)})
        step = dom.get("step")
        if is_num(step) and float(step) > 0 and is_num(sv):
            off = abs(float(sv) - float(lo)) % float(step)
            if off > 1e-9 and abs(off - float(step)) > 1e-9:
                warnings.append("参数 %s 建议执行值 %s 与步进 %s 不对齐（可执行性提示）"
                                % (pid, sv, step))

    # 2. 耦合约束算术求值（当前值 / 建议执行值 两套映射）
    n_eval = 0
    cur_only = {str(p.get("param_id")): p.get("current_value")
                for p in params if is_num(p.get("current_value"))}
    for i, c in enumerate(cons):
        cid = c.get("cid") or "constraints[%d]" % i
        if c.get("kind") == "none_declared":
            continue
        expr_raw = str(c.get("expression") or "").strip()
        if not expr_raw:
            warnings.append("%s expression 为空，跳过求值" % cid)
            continue
        expr, ph_map = rewrite_expr(expr_raw, cur_only.keys())
        for mode, vmap in (("current", cur_only), ("suggested", cur_map)):
            variables = {ph_map.get(k, k): v for k, v in vmap.items()}
            ok, val = eval_expr(expr, variables)
            if not ok:
                violations.append({"type": "constraint_unevaluable", "target": "%s@%s" % (cid, mode),
                                   "detail": str(val)})
                continue
            n_eval += 1
            if val is False:
                violations.append({"type": "constraint_violated", "target": "%s@%s" % (cid, mode),
                                   "detail": "在%s值映射下不成立: %s" % ("当前" if mode == "current" else "建议", expr_raw)})

    # 3. 口径一致性（警告级）
    for i, s in enumerate(suggs):
        sid = s.get("sugg_id") or "suggestions[%d]" % i
        pid = str(s.get("param_id") or "")
        if s.get("direction") == "hold" and is_num(s.get("suggested_value")) \
                and pid in cur_map and float(s["suggested_value"]) != float(cur_map[pid]):
            warnings.append("%s direction=hold 但 suggested_value 与当前值不同" % sid)

    all_in_domain = domain_bad_cur == 0 and domain_bad_sug == 0
    hard_viol = [v for v in violations if v["type"] in ("current_out_of_domain",
                                                        "suggested_out_of_domain",
                                                        "constraint_violated",
                                                        "constraint_unevaluable")]
    feas = {
        "tool": "scripts/param_check.py",
        "scenario_note": "算术校验基于 result.json 内登记的声明域/当前值/建议值，"
                         "属前瞻性规划口径，不代表实测实验室数据或供应商确认",
        "parameters_checked": len(params),
        "constraints_declared": len(cons),
        "constraint_evaluations": n_eval,
        "checked_count": len(params) + n_eval,
        "all_within_domain": all_in_domain,
        "all_constraints_satisfied": not any(v["type"] in ("constraint_violated",
                                                           "constraint_unevaluable")
                                             for v in violations),
        "variable_maps": {"current": {k: v for k, v in cur_map.items()},
                          "suggested": cur_map},
        "violations": violations,
        "warnings": warnings,
        "verdict": "PASS" if not hard_viol else "FAIL",
        "summary": "域越界 %d（当前）/ %d（建议），违规 %d 条，警告 %d 条"
                   % (domain_bad_cur, domain_bad_sug, len(hard_viol), len(warnings)),
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
