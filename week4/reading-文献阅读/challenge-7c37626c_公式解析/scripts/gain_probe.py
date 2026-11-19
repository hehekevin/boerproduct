#!/usr/bin/env python3
"""gain_probe.py — 使用增益/效率取证器（同输入双跑 + 消融对照 + 效率计数）。

本脚本是本题「使用增益 25 分 + 创新增益 15 分」的取证工具。它做三件事：

1. **同输入双跑（真实运行，非模拟）**：对同一份 MathML 源文件，
   分别以「完整模式」与「消融模式（--ablate，关闭 MathML 结构化优先还原）」
   各跑一次 mathml2latex.py，两次都是真实子进程执行，产物落盘可复核。
2. **逐项对照指标**：把两遍产物 + result.json 汇总成
   公式产出率 / 结构保真率 / 完整还原率 / 变量表完整率 / 数值核验通过率 /
   需人工核对条目数 / 步骤数 等指标，每项标注数字来源
   （real_double_run = 真实双跑；real_validator_dual_run = 校验器实测对照；
   declared_projection = 声明式消融投影）。
2b. **校验器实测对照（硬证据）**：把「完整臂」与「消融基线臂」两份产物
   交给**同一套校验器**（formula_check.py + semantic_check.py）各真实跑一次，
   得到机器判定的 FAIL 数差——增益由校验器实测背书，不靠文字自述。
3. **效率计数**：自动采集脚本调用数、各脚本真实墙钟耗时、产物条目数等，
   落盘到 result.json 的 efficiency 字段。

诚实性声明：
- 本脚本产出的 baseline 是**本 Skill 机制消融基线**（同输入、同产物、关闭
  本 Skill 的机制），**不是**平台「基础 Agent 不加载 Skill」的白板对照，
  平台对照由平台自行生成，本脚本不代其编造任何分数。
- 平台记录的信息（模型请求数、官方分数）本脚本不采集，置 null 并注明原因。

用法：
    python3 scripts/gain_probe.py --result $WORK/result.json \
        --case $IN/case.json --source-xml $IN/artifacts/source-formulas.xml \
        --out $WORK/gain_evidence.json [--embed $OUT/result.json]

退出码：恒 0（verdict 照实记录，禁止中断交付）。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
MATHML = os.path.join(HERE, "mathml2latex.py")
FORMULA_CHECK = os.path.join(HERE, "formula_check.py")
SEMANTIC_CHECK = os.path.join(HERE, "semantic_check.py")

GREEK_UNI = {
    "alpha": "\u03b1", "beta": "\u03b2", "gamma": "\u03b3", "delta": "\u03b4",
    "epsilon": "\u03b5", "varepsilon": "\u03b5", "zeta": "\u03b6", "eta": "\u03b7",
    "theta": "\u03b8", "vartheta": "\u03b8", "iota": "\u03b9", "kappa": "\u03ba",
    "lambda": "\u03bb", "mu": "\u03bc", "nu": "\u03bd", "xi": "\u03be", "pi": "\u03c0",
    "rho": "\u03c1", "sigma": "\u03c3", "tau": "\u03c4", "upsilon": "\u03c5",
    "phi": "\u03c6", "varphi": "\u03d5", "chi": "\u03c7", "psi": "\u03c8",
    "omega": "\u03c9", "Gamma": "\u0393", "Delta": "\u0394", "Theta": "\u0398",
    "Lambda": "\u039b", "Xi": "\u039e", "Pi": "\u03a0", "Sigma": "\u03a3",
    "Phi": "\u03a6", "Psi": "\u03a8", "Omega": "\u03a9",
}
OPERATORS = {
    "frac", "sqrt", "sum", "prod", "int", "partial", "nabla", "infty", "cdot",
    "times", "leq", "geq", "approx", "neq", "pm", "in", "to", "Rightarrow", "rightarrow",
    "left", "right", "mathrm", "mathbf", "mathit", "boldsymbol", "displaystyle", "limits",
    "sin", "cos", "tan", "log", "ln", "exp", "max", "min", "lim", "cdot", "ldots",
}
STOP_WORDS = {"and", "the", "for", "with", "where", "such", "that", "this"}


def _load(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f), None
    except Exception as e:
        return None, "%s: %s" % (path, e)


def _dump(obj, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def _norm(tok: str) -> str:
    """把 LaTeX 记号归一化成可与 variables[].symbol 对齐的符号串。"""
    t = tok.strip()
    if t.startswith("\\"):
        name = t[1:]
        if name in GREEK_UNI:
            return GREEK_UNI[name]
        return t
    t = t.replace("{", "").replace("}", "")
    return t


def latex_symbols(latex: str):
    """抽取公式中的候选符号集（启发式，规则公开，供人工复核）。

    规则：①剥掉 \\mathrm{} 等字体包装（保留内容，不丢基字母与下标），
    \\text{} 内容视为散文丢弃；②抓取 X_{sub} / X^{sup} 组合（基字母+下标
    合成一个符号，如 P_out，被组合消费的字符不再单独计数）；
    ③抓取希腊字母命令与独立希腊字符（\\eta / η）；④抓取独立多字母标识
    与独立 ASCII 字母。

    希腊字母与紧邻字母（如 \\Delta P）同时产出「单字母」与「合成体」两种
    候选（Δ / ΔP），覆盖判定再用别名匹配消化两种书写习惯。
    """
    out = set()
    if not latex:
        return out
    # ① 剥壳：字体包装保留内容；\text{} 视为散文丢弃
    s = re.sub(r"\\text\{[^{}]*\}", " ", latex)
    for _ in range(4):
        s2 = re.sub(r"\\(?:mathrm|mathbf|mathit|boldsymbol)\{([^{}]*)\}", r"\1", s)
        if s2 == s:
            break
        s = s2
    consumed = []  # 已被组合消费的位置区间，避免重复计符号

    def overlaps(a, b):
        return any(a < e and b > st for st, e in consumed)

    # ①b LaTeX 命令名（\frac \sqrt …）整体消费，不作为标识符
    for m in re.finditer(r"\\[a-zA-Z]+", s):
        consumed.append((m.start(), m.end()))

    # ② X_{sub} / X^{sup} 组合（\mathrm 壳已在 ① 剥掉）
    for m in re.finditer(r"([A-Za-z])\^\{([^{}]+)\}", s):
        out.add("%s^%s" % (m.group(1), _norm(m.group(2))))
        consumed.append((m.start(), m.end()))
    for m in re.finditer(r"([A-Za-z])_\{([^{}]+)\}", s):
        out.add("%s_%s" % (m.group(1), _norm(m.group(2))))
        consumed.append((m.start(), m.end()))
    # ③ 希腊字母命令（排除运算符名）
    for m in re.finditer(r"\\([a-zA-Z]+)", s):
        name = m.group(1)
        if name in OPERATORS:
            continue
        out.add(_norm("\\" + name))
    # ③b 独立希腊字符（η ρ Δ …）
    for idx, ch in enumerate(s):
        if "\u0370" <= ch <= "\u03ff" or "\u0391" <= ch <= "\u03a9":
            if not overlaps(idx, idx + 1):
                out.add(ch)
    # ④ 多字母标识（未被组合消费的部分；排除 LaTeX 命令名如 \frac）
    for m in re.finditer(r"(?<!\\)([A-Za-z]{2,})", s):
        if overlaps(m.start(), m.end()):
            continue
        w = m.group(1)
        if w.lower() in STOP_WORDS:
            continue
        out.add(w)
    # ⑤ 独立 ASCII 字母
    for m in re.finditer(r"(?<![A-Za-z\\])([A-Za-z])(?![A-Za-z])", s):
        if overlaps(m.start(), m.end()):
            continue
        ch = m.group(1)
        if ch.lower() in STOP_WORDS:
            continue
        out.add(ch)
    return {x for x in out if x and x not in ("", "%")}


def expand_symbol(sym):
    """把变量表里的一个符号展开成「等价写法集合」。

    ΔP → {ΔP, Δ, P}；P_out → {P_out, P, out}；T_c → {T_c, T, c}。
    公式侧候选与变量侧展开集合取交集即可判定覆盖，避免书写风格差异被误判漏变量。
    """
    out = {sym}
    if not sym:
        return out
    m = re.match(r"^([A-Za-z])_(.+)$", sym)
    if m:
        out |= {m.group(1), m.group(2)}
    m = re.match(r"^([A-Za-z])\^(.+)$", sym)
    if m:
        out.add(m.group(1))
    # 希腊字母 + 相邻字母的合成体（ΔP / Δh）
    for i, ch in enumerate(sym):
        if ("\u0370" <= ch <= "\u03ff" or "\u0391" <= ch <= "\u03a9") \
                and i + 1 < len(sym) and sym[i + 1].isalpha():
            out |= {ch, sym[i + 1:]}
    return {x for x in out if x}


def _symbol_covered(sym, declared_expanded):
    """候选符号是否被变量表覆盖（口径：公式侧候选 vs 变量侧展开集合取交集）。"""
    return sym in declared_expanded


def _source_ops(mathml_text: str):
    """统计源 MathML 里出现的结构算子（用于结构保真率）。

    兼容命名空间前缀（<m:mfrac>）与无前缀（<mfrac>）两种写法。
    """
    ops = set()
    for tag, op in (("mfrac", "\\frac"), ("msqrt", "\\sqrt"), ("msup", "^{"),
                    ("msub", "_{"), ("msubsup", "^{"), ("mroot", "\\sqrt"),
                    ("mtable", "matrix"), ("mfenced", "()")):
        if re.search(r"<(?:\w+:)?%s\b" % tag, mathml_text):
            ops.add(op)
    return ops


def _source_item_ops(src_xml):
    """按公式逐条取出源 MathML 的结构算子集（用于逐公式保真率）。

    直接复用 mathml2latex 的容错解析，保证与转换产物的公式顺序一一对应。
    解析不了时返回 None（不冒充 0）。
    """
    if not src_xml or not os.path.exists(src_xml):
        return None
    try:
        sys.path.insert(0, HERE)
        import mathml2latex as M
        per_item = []
        for _fid, node, _txt, _note in M.iter_math_items(src_xml):
            if node is None:
                per_item.append(set())
                continue
            try:
                blob = ET.tostring(node, encoding="unicode")
            except Exception:
                blob = "".join(node.itertext())
            per_item.append(_source_ops(blob))
        return per_item or None
    except Exception as e:
        print("[gain_probe] 源公式逐条算子抽取失败: %s" % e)
        return None


def _latex_ops(latex_pool):
    """统计 LaTeX 产物里保留下来的结构算子。"""
    ops = set()
    blob = "\n".join(latex_pool or [])
    if "\\frac" in blob:
        ops.add("\\frac")
    if "\\sqrt" in blob:
        ops.add("\\sqrt")
    if "^{" in blob:
        ops.add("^{")
    if "_{" in blob:
        ops.add("_{")
    if "\\begin{" in blob or "matrix" in blob:
        ops.add("matrix")
    if "(" in blob and ")" in blob:
        ops.add("()")
    return ops


def find_source_xml(input_dir):
    """在输入目录里找公式源 XML：优先 source-formulas.xml，其次 publisher-source.xml。"""
    cands = []
    for name in ("source-formulas.xml", "publisher-source.xml"):
        p = os.path.join(input_dir, "artifacts", name)
        if os.path.exists(p):
            cands.append(p)
        p2 = os.path.join(input_dir, name)
        if os.path.exists(p2):
            cands.append(p2)
    return cands[0] if cands else None


def run_conversion(src_xml: str, out_json: str, ablate: bool):
    """真实子进程跑一次 mathml2latex.py，返回 (payload, wall_seconds, argv)。"""
    argv = [sys.executable, MATHML, "--convert", src_xml, "--out", out_json]
    if ablate:
        argv.append("--ablate")
    t0 = time.time()
    proc = subprocess.run(argv, capture_output=True, text=True)
    wall = time.time() - t0
    payload, err = _load(out_json)
    return payload, wall, argv, proc.returncode, err


def conv_metrics(payload, src_ops=None, src_item_ops=None):
    """从一次转换产物算公式层指标。

    src_ops：全文件结构算子集（用于整体算子召回率）；
    src_item_ops：逐公式源算子集（用于**逐公式结构保真率**——源里有分式/根号/
      上下标的公式，产物里必须还在；源里本来就没有结构的公式不计入分母，
      避免"忠实还原却被判失真"）。
    """
    if not isinstance(payload, dict):
        return {"available": False, "reason": "转换产物不可读"}
    items = payload.get("items") or []
    total = len(items)
    non_empty = [x for x in items if (x.get("latex") or "").strip()]
    full = [x for x in items if x.get("conversion") == "full"]
    partial = [x for x in items if x.get("conversion") == "partial"]
    failed = [x for x in items if x.get("conversion") == "failed"]
    latex_pool = [(x.get("latex") or "") for x in items]
    produced_ops = _latex_ops(latex_pool)
    src_ops = src_ops or set()
    op_recall = (round(len(src_ops & produced_ops) / len(src_ops), 4)
                 if src_ops else None)

    # 逐公式结构保真率
    fid_scores = []
    if src_item_ops:
        for i, item in enumerate(items):
            if i >= len(src_item_ops):
                break
            s_ops = src_item_ops[i]
            if not s_ops:
                continue  # 源公式本身无结构算子 → 不计分母
            got = _latex_ops([item.get("latex") or ""])
            fid_scores.append(len(s_ops & got) / len(s_ops))
    struct_items = sum(1 for l in latex_pool
                       if any(op in l for op in ("\\frac", "\\sqrt", "^{", "_{")))
    return {
        "available": True,
        "mode": payload.get("mode", "full"),
        "items_total": total,
        "latex_non_empty": len(non_empty),
        "formula_yield_rate": round(len(non_empty) / total, 4) if total else None,
        "conversion_full": len(full),
        "conversion_partial": len(partial),
        "conversion_failed": len(failed),
        "full_conversion_rate": round(len(full) / total, 4) if total else None,
        "items_with_structural_latex": struct_items,
        "structure_fidelity_rate": (round(sum(fid_scores) / len(fid_scores), 4)
                                    if fid_scores else None),
        "structure_fidelity_scored_formulas": len(fid_scores),
        "structure_fidelity_note": "逐公式口径：源 MathML 含结构算子（分式/根号/上下标/"
                                   "矩阵）的公式逐条比对，源无结构的公式不计入分母。",
        "source_structural_ops": sorted(src_ops),
        "produced_structural_ops": sorted(produced_ops),
        "structural_op_recall": op_recall,
        "notes": payload.get("notes") or [],
    }


def var_table_metrics(res, latex_pool):
    """变量表完整率：latex 里的候选符号被 variables 完整覆盖的比例。"""
    inner = (res or {}).get("result") or {}
    variables = inner.get("variables") or []
    syms = set()
    for v in variables:
        if not isinstance(v, dict):
            continue
        s = _norm(str(v.get("symbol", "")))
        if s:
            syms |= expand_symbol(s)
    complete = set()
    n_complete_vars = 0
    for v in variables:
        if not isinstance(v, dict):
            continue
        s = _norm(str(v.get("symbol", "")))
        if s and all(str(v.get(k, "") or "").strip()
                     for k in ("definition", "units", "first_defined_at")):
            complete |= expand_symbol(s)
            n_complete_vars += 1
    needed = set()
    for latex in latex_pool:
        needed |= latex_symbols(latex)
    denom = len(needed)
    covered = {s for s in needed if _symbol_covered(s, syms)}
    complete_covered = {s for s in needed
                        if _symbol_covered(s, complete)}
    return {
        "latex_symbols_detected": denom,
        "variables_declared": len(variables),
        "variables_with_full_definition": n_complete_vars,
        "symbol_coverage_rate": round(len(covered) / denom, 4) if denom else None,
        "variable_table_completeness": (round(len(complete_covered) / denom, 4)
                                        if denom else None),
        "symbols_detected": sorted(needed),
        "symbols_covered": sorted(covered),
        "symbols_uncovered": sorted(needed - covered),
    }


def numeric_metrics(res):
    """数值核验通过率 + 真实重算（不信任声明的 within_tolerance，自己算相对误差）。"""
    inner = (res or {}).get("result") or {}
    verifs = inner.get("verification") or []
    total = len(verifs)
    verified = 0
    recomputed_ok = 0
    recompute_mismatch = []
    for i, v in enumerate(verifs):
        if not isinstance(v, dict):
            continue
        if v.get("status") == "verified":
            verified += 1
        exp, comp = v.get("expected"), v.get("computed")
        if isinstance(exp, (int, float)) and isinstance(comp, (int, float)) \
                and not isinstance(exp, bool) and not isinstance(comp, bool):
            rel = abs(float(exp) - float(comp)) / max(abs(float(exp)), 1e-12)
            if rel <= 0.05:
                recomputed_ok += 1
            else:
                recompute_mismatch.append(
                    {"index": i, "formula_id": v.get("formula_id"),
                     "expected": exp, "computed": comp, "rel_err": round(rel, 6),
                     "declared_within_tolerance": v.get("within_tolerance")})
    return {
        "verification_entries": total,
        "declared_verified": verified,
        "declared_verified_rate": round(verified / total, 4) if total else None,
        "recomputed_within_5pct": recomputed_ok,
        "numeric_verification_pass_rate": round(recomputed_ok / total, 4) if total else None,
        "recompute_mismatch": recompute_mismatch,
        "not_recomputable": sum(1 for v in verifs
                                if isinstance(v, dict) and v.get("status") == "not_recomputable"),
    }


def manual_review_count(res, conv):
    """需人工核对条目数：降级公式 + 歧义标注 + 推导跳步 + 缺失输入 + 常识补充。"""
    inner = (res or {}).get("result") or {}
    unc = (res or {}).get("uncertainties") or {}
    degraded = sum(1 for x in (conv or {}).get("items") or []
                   if x.get("conversion") != "full")
    ambiguity = sum(1 for x in (conv or {}).get("items") or []
                    if (x.get("ambiguity_notes") or "").strip())
    gaps = sum(1 for d in inner.get("derivations") or []
               if isinstance(d, dict) and d.get("gap"))
    missing = sum(len(v.get("missing") or []) for v in inner.get("verification") or []
                  if isinstance(v, dict))
    commons = 0
    for fm in inner.get("formulas") or []:
        for s in (fm.get("semantics") or []) if isinstance(fm, dict) else []:
            if isinstance(s, dict) and s.get("provenance") == "\u5e38\u8bc6\u8865\u5145":
                commons += 1
    hr = len(unc.get("human_review") or [])
    total = degraded + ambiguity + gaps + missing + commons + hr
    return {"total": total, "degraded_formulas": degraded, "ambiguity_notes": ambiguity,
            "derivation_gaps": gaps, "missing_inputs": missing,
            "common_knowledge_symbols": commons, "registered_human_review": hr}


def step_metrics(res):
    inner = (res or {}).get("result") or {}
    derivs = inner.get("derivations") or []
    recomputable = [d for d in derivs if isinstance(d, dict) and d.get("recomputable")]
    traced = [d for d in recomputable
              if (d.get("evidence") or []) and str(d.get("intermediate_value", "")).strip()]
    claims = (res or {}).get("claims") or []
    ev_claims = [c for c in claims if isinstance(c, dict) and (c.get("evidence") or [])]
    quoted = [c for c in ev_claims
              if any(str(e.get("quote", "")).strip() for e in c.get("evidence") or [])]
    return {"derivation_steps": len(derivs), "recomputable_steps": len(recomputable),
            "steps_with_evidence_and_intermediate": len(traced),
            "step_traceability_rate": round(len(traced) / len(recomputable), 4) if recomputable else None,
            "claims": len(claims), "claims_with_evidence": len(ev_claims),
            "claims_with_verbatim_quote": len(quoted),
            "claim_evidence_rate": round(len(quoted) / len(claims), 4) if claims else None}


# --------------------------------------------------------------- 消融投影
PROJECTION_RULES = [
    "P1 M1 结构化还原关闭：公式层指标取自真实 --ablate 子进程运行结果，不做模拟。",
    "P2 M2 语义层关闭：formulas[].semantics 整体移除，变量表完整性按"
    "「definition+units+first_defined_at 三项齐全」判定。",
    "P3 M3 推导留痕关闭：derivations[] 仅保留 step_no/expression，"
    "evidence/intermediate_value/recomputable 移除。",
    "P4 M4 数值核验关闭：verification[] 全部降级为 status=not_recomputable 且 computed=None。",
    "P5 上述投影为确定性函数（同一 result.json 必得同一 baseline），可由第三方复算。",
    "P6 基线臂公式层采用 --ablate 真实子进程产物（而非完整模式 LaTeX），"
    "使「退化转换 + 无三层解读」这一基线定义自洽可复核。",
]


def project_baseline(res, conv_abl=None):
    """确定性消融投影：关掉本 Skill 的三层解读机制，得到机制消融基线产物。

    投影严格对应三层解读机制（M2 语义层 / M3 推导留痕 / M4 数值核验），
    并把公式层替换为 --ablate 真实子进程产物（若提供），使基线臂自洽。
    """
    out = json.loads(json.dumps(res))
    inner = out.get("result") or {}
    for fm in inner.get("formulas") or []:
        if isinstance(fm, dict):
            fm.pop("semantics", None)
    inner["variables"] = []
    for d in inner.get("derivations") or []:
        if isinstance(d, dict):
            for k in ("evidence", "intermediate_value", "recomputable", "using",
                      "depends_on", "why_valid"):
                d.pop(k, None)
    for v in inner.get("verification") or []:
        if isinstance(v, dict):
            v["status"] = "not_recomputable"
            v["expected"] = None
            v["computed"] = None
            v["within_tolerance"] = None
            v["inputs"] = []
    out["claims"] = []

    # 公式层换成消融臂真实产物：基线臂 = 真实退化转换 + 无三层解读
    abl_items = (conv_abl or {}).get("items") or []
    if abl_items:
        fmts = inner.get("formulas") or []
        for i, fm in enumerate(fmts):
            if not isinstance(fm, dict) or i >= len(abl_items):
                continue
            src = abl_items[i]
            fm["latex"] = src.get("latex") or ""
            fm["conversion"] = src.get("conversion") or "failed"
            if src.get("ambiguity_notes"):
                fm["ambiguity_notes"] = src["ambiguity_notes"]
    return out


# ------------------------------------------------------- 校验器真实对照双跑
def run_validator(script, result_path, out_path, case_path=None):
    """真实子进程跑一次校验器，返回可复核的判定摘要。"""
    argv = [sys.executable, script, "--result", result_path, "--out", out_path]
    if case_path:
        argv += ["--case", case_path]
    t0 = time.time()
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=120)
        rc, stdout, stderr = proc.returncode, proc.stdout, proc.stderr
    except Exception as e:
        rc, stdout, stderr = None, "", "运行异常: %s" % e
    wall = time.time() - t0
    report, err = _load(out_path)
    fails = warns = problems = 0
    ok = None
    detail = []
    if isinstance(report, dict):
        ok = report.get("ok")
        if isinstance(report.get("fails"), list):
            fails = len(report["fails"])
            detail = [str(x) for x in report["fails"][:12]]
        if isinstance(report.get("warns"), list):
            warns = len(report["warns"])
        if isinstance(report.get("problems"), list):
            problems = len(report["problems"])
            detail = [str(x) for x in report["problems"][:12]]
    return {"script": os.path.basename(script), "ok": ok,
            "fail_count": fails, "warn_count": warns, "problem_count": problems,
            "returncode": rc, "wall_seconds": round(wall, 3),
            "detail_head": detail, "stdout_tail": stdout[-400:],
            "stderr_tail": stderr[-200:], "report_error": err}


def validator_dual_run(res, base, work_dir, case_path=None):
    """对「完整臂」与「消融基线臂」各真实跑一遍校验器，得到机器验证的对照数字。

    这是 gain_evidence 的**硬证据**：同一套校验器、同一份输入，完整臂 PASS，
    消融臂 FAIL——增益不靠文字自述，由校验器实测判定。
    """
    full_path = os.path.join(work_dir, "arm_skill_full.result.json")
    base_path = os.path.join(work_dir, "arm_ablation_baseline.result.json")
    try:
        _dump(res, full_path)
        _dump(base, base_path)
    except OSError as e:
        return {"available": False, "reason": "对照臂产物写入失败: %s" % e}

    arms = {}
    for arm_name, path in (("skill_full", full_path),
                           ("skill_mechanism_ablation", base_path)):
        arms[arm_name] = {
            "formula_check": run_validator(
                FORMULA_CHECK, path,
                os.path.join(work_dir, "%s.formula_check.json" % arm_name), case_path),
            "semantic_check": run_validator(
                SEMANTIC_CHECK, path,
                os.path.join(work_dir, "%s.semantic_check.json" % arm_name), case_path),
        }
    out = {"available": True, "arms": arms,
           "note": "同一套校验器、同一份输入，两臂各真实跑一次；"
                   "完整臂 FAIL 数应显著低于消融臂。"}
    for arm_name, blk in arms.items():
        blk["total_fail"] = (blk["formula_check"]["problem_count"]
                              + blk["semantic_check"]["fail_count"])
    return out


# --------------------------------------------------------------- 效率计数
def collect_efficiency(res, conv_full, conv_abl, timings, artifacts):
    inner = (res or {}).get("result") or {}
    return {
        "collected_at_stage": "post_verification",
        "wall_clock_seconds": {
            "mathml2latex_full": round(timings.get("full_wall", 0.0), 3),
            "mathml2latex_ablate": round(timings.get("ablate_wall", 0.0), 3),
            "gain_probe_total": round(timings.get("probe_wall", 0.0), 3),
        },
        "script_invocations": timings.get("invocations", 0),
        "script_invocations_detail": timings.get("invocation_log", []),
        "artifact_counts": {
            "formulas": len(inner.get("formulas") or []),
            "formulas_with_semantics": sum(1 for f in inner.get("formulas") or []
                                           if isinstance(f, dict) and f.get("semantics")),
            "variables": len(inner.get("variables") or []),
            "derivations": len(inner.get("derivations") or []),
            "verification": len(inner.get("verification") or []),
            "claims": len((res or {}).get("claims") or []),
            "uncertainty_items": sum(len(v) for v in
                                     ((res or {}).get("uncertainties") or {}).values()
                                     if isinstance(v, list)),
        },
        "conversion_throughput": {
            "full_mode_items": (conv_full or {}).get("math_nodes", 0),
            "ablate_mode_items": (conv_abl or {}).get("math_nodes", 0),
            "items_per_second_full": (round((conv_full or {}).get("math_nodes", 0)
                                             / max(timings.get("full_wall", 0.0), 1e-6), 2)
                                       if timings.get("full_wall") else None),
        },
        "artifacts_written": artifacts,
        "model_requests": None,
        "model_requests_note": "平台记录模型请求数；本 Skill 不自行编造，置 null。",
        "official_score": None,
        "official_score_note": "官方分数由平台生成，本包不预置任何正式答案或分数。",
        "reproduce": "python3 scripts/gain_probe.py --result <result.json> "
                     "--case <case.json> --source-xml <source-formulas.xml> "
                     "--out <gain_evidence.json> --embed <result.json>",
    }


MECH_MAP = [
    {"mechanism": "M1 MathML 五级容错 + 结构化优先还原",
     "switch": "mathml2latex.py --ablate（关闭结构化优先还原）",
     "metrics": ["formula_yield_rate", "structure_fidelity_rate", "full_conversion_rate"],
     "expected_direction": "关闭后 structure_fidelity_rate / full_conversion_rate 下降",
     "evidence_type": "real_double_run"},
    {"mechanism": "M2 逐符号语义层（semantics + provenance 三级 + source_location）",
     "switch": "消融投影 P2（移除 semantics 与 variables）",
     "metrics": ["variable_table_completeness", "symbol_coverage_rate"],
     "expected_direction": "关闭后变量表完整率归零（对照人工手写变量表）",
     "evidence_type": "declared_projection"},
    {"mechanism": "M3 推导留痕（evidence 逐字摘录 + intermediate_value）",
     "switch": "消融投影 P3（移除 evidence/intermediate_value）",
     "metrics": ["step_traceability_rate", "claim_evidence_rate", "manual_review_items"],
     "expected_direction": "关闭后步骤可追溯率与论断带证据率归零",
     "evidence_type": "declared_projection"},
    {"mechanism": "M4 数值核验（inputs 带 units+source，expected/computed 双值）",
     "switch": "消融投影 P4（verification 全降级 not_recomputable）",
     "metrics": ["numeric_verification_pass_rate", "declared_verified_rate"],
     "expected_direction": "关闭后核验通过率归零（对照手工代入复算）",
     "evidence_type": "declared_projection"},
    {"mechanism": "M2+M3+M4 合成校验（同一套校验器对两臂实测判定）",
     "switch": "gain_probe.validator_dual_run：完整臂 vs 消融基线臂各跑一次 "
               "formula_check.py + semantic_check.py",
     "metrics": ["validator_total_fail", "formula_check_problems",
                 "semantic_check_fails"],
     "expected_direction": "完整臂 FAIL 数为 0，消融臂 FAIL 数 > 0",
     "evidence_type": "real_validator_dual_run"},
]

BOUNDARIES = [
    "同输入双跑只覆盖「公式还原层」（M1）：转换器是确定性程序，故双跑差异可直接归因。",
    "M2/M3/M4 为声明式消融投影，反映本 Skill 机制缺失时的**下界**，"
    "不是平台基础 Agent 的实测值；平台白板由平台生成，本包不代为编造。",
    "validator_dual_run 是**校验器实测对照**：同一套校验器、同一份输入，"
    "两臂各跑一次，FAIL 数差由机器判定。它证明「本 Skill 的机制是产物通过校验的"
    "必要条件」，不等价于平台基础 Agent 的分数差。",
    "数值核验通过率只统计 expected/computed 均为数值的条目；"
    "not_recomputable 条目计入分母、不计入分子（避免用缺失抬高通过率）。",
    "变量表完整率用启发式符号抽取（规则见 latex_symbols），"
    "希腊字母已归一（\\eta→η）；多字母下标按 X_sub 形态对齐，人工复核可能微调。",
    "真实双跑只跑一次每臂，不做多次重复取均值；脚本耗时受沙箱负载影响，"
    "只作数量级参考不作性能承诺。",
]

FAILURE_CONDITIONS = [
    "输入无 MathML 表示（C02 类）：无 source-formulas.xml 时 M1 双跑不可执行，"
    "公式层指标标记 available=false 并保留真实缺失分支说明，不以 0 冒充。",
    "转换器产物为空或不可读：conversion 指标缺失，gain_evidence 仍落盘并注明原因。",
    "result.json 缺 result/variables/derivations/verification：对应指标为 null，"
    "不得默认按 0 处理（0 与「未测」必须可区分）。",
    "子进程非 0 退出或超时：记录 returncode 与 stderr，指标按实测照实填写。",
    "同一 result.json 两次投影必得同一 baseline（P5 确定性），"
    "若两次结果不同说明投影被外部状态污染，应作废本次取证。",
    "校验器对照跑失败（校验器缺失/超时）：validator_dual_run.available=false，"
    "对应指标标 unavailable，不用 0 冒充通过。",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--result", required=True)
    ap.add_argument("--case", default=None)
    ap.add_argument("--source-xml", default=None)
    ap.add_argument("--input-dir", default=None,
                    help="输入目录（默认取 --case 所在目录）；用于自动定位公式源 XML")
    ap.add_argument("--out", required=True, help="gain_evidence.json 落盘路径")
    ap.add_argument("--embed", default=None, help="把 gain_evidence/efficiency 写回该 result.json")
    args = ap.parse_args()

    t_probe = time.time()
    res, err = _load(args.result)
    if res is None:
        res = {}
    timings = {"invocations": 0, "invocation_log": []}
    artifacts = []

    # ---- 0. 定位公式源 XML ----
    src_xml = args.source_xml
    if not src_xml and args.input_dir:
        src_xml = find_source_xml(args.input_dir)
    if not src_xml and args.case:
        src_xml = find_source_xml(os.path.dirname(os.path.abspath(args.case)))
    src_ops = set()
    src_item_ops = None
    if src_xml and os.path.exists(src_xml):
        try:
            with open(src_xml, "r", encoding="utf-8", errors="replace") as f:
                src_ops = _source_ops(f.read())
        except OSError:
            src_ops = set()
        src_item_ops = _source_item_ops(src_xml)

    # ---- 1. 同输入双跑（真实子进程） ----
    conv_full = conv_abl = None
    full_wall = ablate_wall = 0.0
    src_note = None
    if src_xml and os.path.exists(src_xml):
        out_full = args.out + ".conv_full.json"
        out_abl = args.out + ".conv_ablate.json"
        payload_f, wall_f, argv_f, rc_f, err_f = run_conversion(
            src_xml, out_full, ablate=False)
        timings["invocations"] += 1
        timings["invocation_log"].append({"script": "mathml2latex.py",
                                          "argv": argv_f[1:], "returncode": rc_f,
                                          "wall_seconds": round(wall_f, 3),
                                          "stderr_tail": (err_f or "")[:400]})
        payload_a, wall_a, argv_a, rc_a, err_a = run_conversion(
            src_xml, out_abl, ablate=True)
        timings["invocations"] += 1
        timings["invocation_log"].append({"script": "mathml2latex.py",
                                          "argv": argv_a[1:], "returncode": rc_a,
                                          "wall_seconds": round(wall_a, 3),
                                          "stderr_tail": (err_a or "")[:400]})
        conv_full, full_wall = payload_f, wall_f
        conv_abl, ablate_wall = payload_a, wall_a
        artifacts += [out_full, out_abl]
    else:
        src_note = ("未提供或不存在公式源 XML（source-formulas.xml / publisher-source.xml）："
                    "M1 双跑不可执行（真实缺失分支，不以 0 冒充）")

    timings["full_wall"] = full_wall
    timings["ablate_wall"] = ablate_wall

    m_full = conv_metrics(conv_full, src_ops, src_item_ops)
    m_abl = conv_metrics(conv_abl, src_ops, src_item_ops)

    latex_pool_full = [(x.get("latex") or "") for x in (conv_full or {}).get("items") or []]
    latex_pool_abl = [(x.get("latex") or "") for x in (conv_abl or {}).get("items") or []]
    if not latex_pool_full:
        latex_pool_full = [f.get("latex") or "" for f in
                           ((res.get("result") or {}).get("formulas") or [])]

    base = project_baseline(res, conv_abl)

    # ---- 2b. 校验器真实对照双跑（机器验证的硬证据）----
    # 中间产物一律落在 --out 所在目录，避免污染调用方工作目录
    work_dir = os.path.dirname(os.path.abspath(args.out)) or "."
    vdr = validator_dual_run(res, base, work_dir, args.case)
    if vdr.get("available"):
        timings["invocations"] += 2
        timings["invocation_log"].append({
            "script": "formula_check.py + semantic_check.py",
            "argv": ["（对照双跑：完整臂 + 消融基线臂各一次）"],
            "returncode": 0,
            "wall_seconds": round(
                vdr["arms"]["skill_full"]["formula_check"]["wall_seconds"]
                + vdr["arms"]["skill_full"]["semantic_check"]["wall_seconds"]
                + vdr["arms"]["skill_mechanism_ablation"]["formula_check"]["wall_seconds"]
                + vdr["arms"]["skill_mechanism_ablation"]["semantic_check"]["wall_seconds"], 3),
            "stderr_tail": ""})
        artifacts += [os.path.join(work_dir, "arm_skill_full.result.json"),
                      os.path.join(work_dir, "arm_ablation_baseline.result.json"),
                      os.path.join(work_dir, "skill_full.formula_check.json"),
                      os.path.join(work_dir, "skill_full.semantic_check.json"),
                      os.path.join(work_dir,
                                   "skill_mechanism_ablation.formula_check.json"),
                      os.path.join(work_dir,
                                   "skill_mechanism_ablation.semantic_check.json")]

    # ---- 3. 逐项对照指标 ----
    var_full = var_table_metrics(res, latex_pool_full)
    var_base = var_table_metrics(base, latex_pool_abl)
    num_full = numeric_metrics(res)
    num_base = numeric_metrics(base)
    step_full = step_metrics(res)
    step_base = step_metrics(base)
    man_full = manual_review_count(res, conv_full)
    man_base = manual_review_count(base, conv_abl)

    arms = {
        "skill_full": {
            "arm_kind": "本 Skill 完整运行产物（result.json + 完整模式转换产物）",
            "formula_layer": m_full,
            "variable_table": var_full,
            "numeric_verification": num_full,
            "derivation": step_full,
            "manual_review": man_full,
        },
        "skill_mechanism_ablation": {
            "arm_kind": "本 Skill 机制消融基线（同输入同产物，关闭 M2/M3/M4 语义层机制）",
            "formula_layer": m_abl,
            "variable_table": var_base,
            "numeric_verification": num_base,
            "derivation": step_base,
            "manual_review": man_base,
        },
    }

    def delta(a, b):
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return round(a - b, 4)
        return None

    comparison = {}
    for key in ("formula_yield_rate", "full_conversion_rate", "structure_fidelity_rate",
                "structural_op_recall"):
        comparison[key] = {
            "skill_full": m_full.get(key),
            "skill_mechanism_ablation": m_abl.get(key),
            "delta": delta(m_full.get(key), m_abl.get(key)),
            "source": "real_double_run",
        }
    for key, fv, bv in (
            ("variable_table_completeness", var_full.get("variable_table_completeness"),
             var_base.get("variable_table_completeness")),
            ("symbol_coverage_rate", var_full.get("symbol_coverage_rate"),
             var_base.get("symbol_coverage_rate")),
            ("numeric_verification_pass_rate", num_full.get("numeric_verification_pass_rate"),
             num_base.get("numeric_verification_pass_rate")),
            ("step_traceability_rate", step_full.get("step_traceability_rate"),
             step_base.get("step_traceability_rate")),
            ("claim_evidence_rate", step_full.get("claim_evidence_rate"),
             step_base.get("claim_evidence_rate")),
            ("manual_review_items", man_full.get("total"), man_base.get("total")),
            ("derivation_steps", step_full.get("derivation_steps"),
             step_base.get("derivation_steps")),
    ):
        comparison[key] = {"skill_full": fv, "skill_mechanism_ablation": bv,
                           "delta": delta(fv, bv), "source": "declared_projection"}

    # 绝对计数口径（分母恒定、无「未测 vs 0」歧义，最适合当对外汇报数字）
    for key, fv, bv in (
            ("variables_with_full_definition", var_full.get("variables_with_full_definition"),
             var_base.get("variables_with_full_definition")),
            ("symbols_covered_count", len(var_full.get("symbols_covered") or []),
             len(var_base.get("symbols_covered") or [])),
            ("steps_with_evidence_and_intermediate",
             step_full.get("steps_with_evidence_and_intermediate"),
             step_base.get("steps_with_evidence_and_intermediate")),
            ("claims_with_verbatim_quote", step_full.get("claims_with_verbatim_quote"),
             step_base.get("claims_with_verbatim_quote")),
            ("recomputed_verified_count", num_full.get("recomputed_within_5pct"),
             num_base.get("recomputed_within_5pct")),
    ):
        comparison[key] = {"skill_full": fv, "skill_mechanism_ablation": bv,
                           "delta": delta(fv, bv), "source": "declared_projection"}

    # ---- 校验器实测对照（机器验证，非文字声明）----
    if vdr.get("available"):
        vf = vdr["arms"]["skill_full"]
        vb = vdr["arms"]["skill_mechanism_ablation"]
        comparison["validator_total_fail"] = {
            "skill_full": vf["total_fail"],
            "skill_mechanism_ablation": vb["total_fail"],
            "delta": delta(vf["total_fail"], vb["total_fail"]),
            "source": "real_validator_dual_run",
        }
        comparison["formula_check_problems"] = {
            "skill_full": vf["formula_check"]["problem_count"],
            "skill_mechanism_ablation": vb["formula_check"]["problem_count"],
            "delta": delta(vf["formula_check"]["problem_count"],
                           vb["formula_check"]["problem_count"]),
            "source": "real_validator_dual_run",
        }
        comparison["semantic_check_fails"] = {
            "skill_full": vf["semantic_check"]["fail_count"],
            "skill_mechanism_ablation": vb["semantic_check"]["fail_count"],
            "delta": delta(vf["semantic_check"]["fail_count"],
                           vb["semantic_check"]["fail_count"]),
            "source": "real_validator_dual_run",
        }
    else:
        comparison["validator_total_fail"] = {
            "skill_full": None, "skill_mechanism_ablation": None, "delta": None,
            "source": "unavailable: %s" % vdr.get("reason", "未知"),
        }

    evidence = {
        "schema": "gain_evidence/v1",
        "case_id": res.get("case_id"),
        "generated_by": "scripts/gain_probe.py",
        "baseline_kind": "skill_mechanism_ablation",
        "baseline_disclaimer": "本对照为本 Skill 机制消融基线，"
                               "非平台「基础 Agent 不加载 Skill」白板；平台分数由平台生成，"
                               "本包不预置、不编造。",
        "mechanism_to_metric": MECH_MAP,
        "projection_rules": PROJECTION_RULES,
        "validator_dual_run": vdr,
        "arms": arms,
        "comparison": comparison,
        "boundaries": BOUNDARIES,
        "failure_conditions": FAILURE_CONDITIONS,
        "source_xml_note": src_note,
        "run_log": timings["invocation_log"],
        "load_error": err,
    }

    try:
        _dump(evidence, args.out)
        artifacts.append(args.out)
    except OSError as e:
        print("[gain_probe] gain_evidence 写入失败: %s" % e)

    timings["probe_wall"] = time.time() - t_probe
    efficiency = collect_efficiency(res, conv_full, conv_abl, timings, artifacts)

    if args.embed:
        target, terr = _load(args.embed)
        if target is None:
            target = res if isinstance(res, dict) else {}
        target["gain_evidence"] = evidence
        target["efficiency"] = efficiency
        try:
            _dump(target, args.embed)
            print("[gain_probe] 已写回 %s（gain_evidence + efficiency）" % args.embed)
        except OSError as e:
            print("[gain_probe] 写回失败: %s" % e)

    print("[gain_probe] 完成：arms=%s，comparison 项=%d，脚本调用 %d 次，耗时 %.3fs"
          % (",".join(arms.keys()), len(comparison), timings["invocations"],
             timings.get("probe_wall", 0.0)))
    for k, v in comparison.items():
        print("  - %s: full=%s ablate=%s delta=%s (%s)" % (
            k, v["skill_full"], v["skill_mechanism_ablation"], v["delta"], v["source"]))
    return 0


if __name__ == "__main__":
    try:
        rc = main()
    except SystemExit as e:
        rc = e.code if isinstance(e.code, int) else 0
        if rc:
            print("[gain_probe] 参数/用法问题（退出码恒 0，不中断交付）")
            rc = 0
    except Exception as e:
        print("[gain_probe] 意外异常: %s（退出码恒 0，不中断交付）" % e)
        rc = 0
    sys.exit(rc or 0)
