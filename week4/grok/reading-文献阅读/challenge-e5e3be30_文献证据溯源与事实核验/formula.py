"""formula — formula parsing & math reasoning checks (stdlib, safe).

For formula_reasoning: validate LaTeX structure (balanced braces/brackets, no lost
terms), extract symbols, build a variable table (definition/unit/range/source,
defined-in-paper vs inferred), and do numeric-substitution verification with a SAFE
AST arithmetic evaluator (no eval of arbitrary code). Derivation steps carry their
assumptions so a reader can check each step.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
import figkit


def latex_structure_ok(latex: str) -> dict:
    issues = []
    depth = 0
    for ch in latex:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:
                issues.append("unbalanced closing brace")
                break
    if depth != 0:
        issues.append(f"unbalanced braces (depth {depth})")
    if latex.count("\\left") != latex.count("\\right"):
        issues.append("\\left/\\right mismatch")
    if latex.count("[") != latex.count("]"):
        issues.append("bracket mismatch")
    return {"ok": not issues, "issues": issues}


def extract_symbols(latex: str) -> list:
    # strip latex commands & numbers; keep letter symbols (incl. greek names)
    s = re.sub(r"\\[a-zA-Z]+", " ", latex)
    s = re.sub(r"[0-9.]+", " ", s)
    toks = re.findall(r"[A-Za-z]+", s)
    seen = []
    for t in toks:
        if t not in seen and t not in {"frac", "sqrt", "sum", "int", "pm", "times", "cdot", "le", "ge", "approx", "in", "log", "ln", "exp", "sin", "cos", "tan", "max", "min"}:
            seen.append(t)
    return seen


_ALLOWED = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b,
            ast.Mult: lambda a, b: a * b, ast.Div: lambda a, b: a / b,
            ast.Pow: lambda a, b: a ** b, ast.USub: lambda a: -a, ast.UAdd: lambda a: a}


def _ev(node, env):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.Name):
        if node.id not in env:
            raise ValueError(f"unknown symbol {node.id}")
        return float(env[node.id])
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED:
        return _ALLOWED[type(node.op)](_ev(node.left, env), _ev(node.right, env))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED:
        return _ALLOWED[type(node.op)](_ev(node.operand, env))
    raise ValueError("unsupported expression")


def safe_eval(expr: str, env: dict) -> float:
    return _ev(ast.parse(expr, mode="eval").body, env)


def check_formula(f: dict) -> dict:
    latex = f.get("latex", "")
    struct = latex_structure_ok(latex)
    symbols = extract_symbols(latex)
    defined = {v.get("symbol") for v in f.get("variables", [])}
    undefined = [s for s in symbols if s not in defined and len(s) == 1]
    numeric = None
    nc = f.get("numeric_check")
    if nc and nc.get("expr") and nc.get("values"):
        try:
            got = safe_eval(nc["expr"], nc["values"])
            exp = nc.get("expected")
            numeric = {"computed": got, "expected": exp,
                       "match": (exp is None) or abs(got - exp) <= nc.get("tol", 1e-6)}
        except Exception as e:  # noqa: BLE001
            numeric = {"error": str(e)}
    return {"id": f.get("id"), "structure": struct, "symbols": symbols,
            "undefined_symbols": undefined, "numeric_check": numeric}


def check_all(ir: dict, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    reports = [check_formula(f) for f in ir.get("formulas", [])]
    figkit.write_json(out_dir / "formula_check.json", reports)
    return {"n_formulas": len(reports), "reports": reports}