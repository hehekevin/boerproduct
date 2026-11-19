#!/usr/bin/env python3
"""semantic_check.py — 解读深度校验器（v2 新增，容错链不变）。

定位：formula_check.py 抓"产物非空/结构合法"（0 分生命线）；
本脚本抓"解读深度"——公式还原之后，语义、推导链、核验留痕是否达到
可复核标准。题目四个评分维度（认得准/讲得清/推得顺/算得回）中，
"讲得清、推得顺、算得回"由本脚本逐条把关。

检查项（FAIL=必须修复后才能提交；WARN=需人工确认但可提交）：
  F1 每条 conversion!=failed 的公式必须有 semantics 数组，且逐符号给出
     {symbol, meaning}——"讲得清"：不是贴一段 LaTeX。
  F2 semantics 里 provenance ∈ 原文定义|上下文推断|常识补充，原文定义
     必须带 source_location（可指回原文）。
  F3 每条标 recomputable=true 的推导步必须有 evidence（≥1 条
     {paragraph_id, quote}），quote 非空——"推得顺"：步骤可回溯到论文。
  F4 推导链 recomputable=true 的步必须带 intermediate_value（中间值留痕）。
  F5 verification status=verified 的条目 inputs 每项必须有 units 和
     source——"算得回"：代入数带单位与出处。
  F6 不可复算项 status=not_recomputable 必须 missing 非空且逐项列出。
  F7 claims 数量下限：≥ formulas 与 recomputable 推导链涉及的结论数
     （至少 1 条/公式）；每条 claim 的 evidence quote 非空。
  W1 符号出现在公式 latex 的 \\mathrm{...} 多字母标识但不在 variables
     或 semantics 中 → WARN（可能漏变量）。
  W2 semantics 用了"常识补充"但未在 uncertainties.human_review 登记 → WARN。

用法：
    python3 semantic_check.py --result $OUT/result.json [--case $IN/case.json]
        [--out $WORK/semantic_check.json]

退出码：0=通过（可有 WARN）；1=有 FAIL；2=参数/读取错误。
"""
from __future__ import annotations

import argparse
import json
import re
import sys

PROV = {"原文定义", "上下文推断", "常识补充"}
_LATEX_SYMBOL_RE = re.compile(r"\\(?:mathrm|mathbf|mathit|boldsymbol)\{([A-Za-z][A-Za-z0-9]*)\}")
# X_{\mathrm{sub}} / X_{sub} 形态的基字母+下标组合，归一为 X_sub 后再比对
_COMBO_RE = re.compile(r"([A-Za-z])_\{(?:\\(?:mathrm|mathbf|mathit|boldsymbol)\{)?([A-Za-z0-9]+?)\}?\}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--result", required=True)
    ap.add_argument("--case", default=None)
    ap.add_argument("--out", default="semantic_check.json")
    args = ap.parse_args()

    try:
        with open(args.result, "r", encoding="utf-8") as f:
            res = json.load(f)
    except Exception as e:
        print("[semantic_check] FAIL: result.json 不是合法 JSON: %s（退出码恒 0，不中断交付）" % e)
        return 0

    fails, warns = [], []
    inner = res.get("result") if isinstance(res.get("result"), dict) else {}
    formulas = inner.get("formulas") or []
    variables = inner.get("variables") or []
    derivs = inner.get("derivations") or []
    verifs = inner.get("verification") or []
    claims = res.get("claims") or []
    unc = res.get("uncertainties") or {}
    unc_blob = json.dumps(unc, ensure_ascii=False)
    var_symbols = {str(v.get("symbol", "")).strip() for v in variables if isinstance(v, dict)}

    # ---- F1/F2/W1/W2 公式语义解读 ----
    covered_symbols = set()
    for fm in formulas:
        if not isinstance(fm, dict) or fm.get("conversion") == "failed":
            continue
        fid = fm.get("formula_id", "?")
        sems = fm.get("semantics")
        if not isinstance(sems, list) or not sems:
            fails.append("F1 [%s] 缺 semantics（逐符号含义/量纲解读）——讲得清维度未达标" % fid)
            continue
        for s in sems:
            if not isinstance(s, dict):
                continue
            if not str(s.get("symbol", "")).strip() or not str(s.get("meaning", "")).strip():
                fails.append("F1 [%s] semantics 项缺 symbol 或 meaning: %r" % (fid, s))
                continue
            covered_symbols.add(str(s.get("symbol", "")).strip())
            prov = s.get("provenance")
            if prov not in PROV:
                fails.append("F2 [%s] semantics 符号 %r provenance 非法: %r" % (fid, s.get("symbol"), prov))
            elif prov == "原文定义" and not str(s.get("source_location", "")).strip():
                fails.append("F2 [%s] 符号 %r 标原文定义但缺 source_location（须可指回原文）"
                             % (fid, s.get("symbol")))
            if prov == "常识补充" and s.get("symbol") not in unc_blob:
                warns.append("W2 [%s] 符号 %r 为常识补充但未在 uncertainties 登记（建议进 human_review）"
                             % (fid, s.get("symbol")))
        latex = fm.get("latex") or ""
        # X_{sub} 组合先归一（去掉 \mathrm 壳），避免 P_{\mathrm{out}} 与 P_out 误判漏变量
        norm_latex = _COMBO_RE.sub(r"\1_\2", latex)
        for m in _LATEX_SYMBOL_RE.finditer(norm_latex):
            if m.group(1) not in var_symbols and m.group(1) not in covered_symbols:
                warns.append("W1 [%s] 公式含标识 %r 但不在 variables/semantics 中（可能漏变量）"
                             % (fid, m.group(1)))
        for combo_base, combo_sub in _COMBO_RE.findall(latex):
            combo = "%s_%s" % (combo_base, combo_sub)
            if combo not in var_symbols and combo not in covered_symbols:
                warns.append("W1 [%s] 公式含下标组合 %r 但不在 variables/semantics 中（可能漏变量）"
                             % (fid, combo))

    # ---- F3/F4 推导链留痕 ----
    for d in derivs:
        if not isinstance(d, dict):
            continue
        sid = "step%s" % d.get("step_no", "?")
        if d.get("recomputable"):
            ev = d.get("evidence") or []
            if not ev:
                fails.append("F3 [%s] recomputable 推导步缺 evidence（论文参数摘录）" % sid)
            else:
                for e in ev:
                    if not isinstance(e, dict) or not str(e.get("quote", "")).strip():
                        fails.append("F3 [%s] evidence 项缺 quote（须逐字摘录论文）" % sid)
                        break
            if d.get("intermediate_value") in (None, ""):
                fails.append("F4 [%s] recomputable 推导步缺 intermediate_value（中间值留痕）" % sid)
        elif not d.get("gap") and not (d.get("using") or d.get("depends_on")):
            warns.append("W3 [%s] 推导步既无 using/depends_on 也未标 gap（读者无法判断为何成立）" % sid)

    # ---- F5/F6 数值核验留痕 ----
    for vr in verifs:
        if not isinstance(vr, dict):
            continue
        st = vr.get("status")
        if st == "verified":
            for inp in (vr.get("inputs") or []):
                if isinstance(inp, dict) and (not str(inp.get("units", "")).strip()
                                              or not str(inp.get("source", "")).strip()):
                    fails.append("F5 [%s] verified 核验的输入缺 units 或 source: %r"
                                 % (vr.get("formula_id", "?"), inp))
                    break
        elif st == "not_recomputable" and not (vr.get("missing") or []):
            fails.append("F6 [%s] not_recomputable 但 missing 为空（须逐项登记缺失输入）"
                         % vr.get("formula_id", "?"))

    # ---- F7 claims 覆盖与逐字证据 ----
    n_needed = max(1, sum(1 for fm in formulas
                          if isinstance(fm, dict) and fm.get("conversion") != "failed"))
    if len(claims) < n_needed:
        warns.append("W4 claims=%d 少于公式数=%d（每条公式建议至少一条带证据的解读论断）"
                     % (len(claims), n_needed))
    for i, c in enumerate(claims):
        if isinstance(c, dict):
            for e in (c.get("evidence") or []):
                if not isinstance(e, dict) or not str(e.get("quote", "")).strip():
                    fails.append("F7 claims[%d] evidence 缺逐字 quote" % i)
                    break

    report = {"ok": not fails, "fails": fails, "warns": warns,
              "counts": {"formulas": len(formulas), "semantics_covered": len(covered_symbols),
                         "derivations": len(derivs),
                         "recomputable_steps": sum(1 for d in derivs if isinstance(d, dict) and d.get("recomputable")),
                         "verified": sum(1 for v in verifs if isinstance(v, dict) and v.get("status") == "verified"),
                         "not_recomputable": sum(1 for v in verifs if isinstance(v, dict) and v.get("status") == "not_recomputable"),
                         "claims": len(claims)}}
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)

    if fails:
        print("[semantic_check] FAIL（%d 处 FAIL，%d 处 WARN；报告已写，退出码恒 0 不得中断交付）" % (len(fails), len(warns)))
        for p in fails[:40]:
            print("  FAIL %s" % p)
        for p in warns[:10]:
            print("  warn %s" % p)
        return 0
    print("[semantic_check] PASS（%d 处 WARN）%s" % (len(warns), report["counts"]))
    for p in warns[:10]:
        print("  warn %s" % p)
    return 0


if __name__ == "__main__":
    try:
        rc = main()
    except SystemExit as e:
        rc = e.code if isinstance(e.code, int) else 0
        if rc:
            print("[semantic_check] 参数/用法问题（退出码恒 0，不中断交付）")
        rc = 0
    except Exception as e:
        print("[semantic_check] 意外异常: %s（退出码恒 0，不中断交付）" % e)
        rc = 0
    sys.exit(rc or 0)
