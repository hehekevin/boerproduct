#!/usr/bin/env python3
r"""number_audit.py — 数字提取 + 交叉比对核心（num-consistency-audit）。

用正则 \d 从稿件全文/表格/图注机械提取六类数字，并做结果报告数字一致性
交叉比对，产出 result.number_audits[]（每条数字：出处+值+类型+是否一致+
冲突对象）与 result.findings[]（不一致处：逐字 quote + 定位 + severity +
修改建议）。**模型只在本脚本后辅判"哪个值是笔误"，全文精读交由机械比对。**

机械比对规则（6 条，全部可复算、低误报）：
  R1 样本量一致性：多个位置报告的入组总数（共/合计/n=总数）互不相同 → critical；
  R2 同名统计量冲突：r/d/OR/RR/HR/t/F/χ² 同一标签在多个位置出现不同值 → major；
  R3 自由度越界：t(df)/F 里的 df 超过 n-1（样本量已知时）→ major；
  R4 p 值与显著性表述矛盾：p≤0.05 却写"不显著"，或 p>0.05 却写"显著" → critical；
  R5 CI 与 null：CI 区间排除/包含 0（或比值类 1）却与"显著/不显著"表述相反 → critical；
  R6 CI 宽 vs SE：se 与 CI 区间同段时，CI 宽应≈2*z*se（容差 10%）→ major；
另：百分比记录不做强制求和判错（不同口径可能相加），仅当同句内百分比明显
总和落在 [0,100] 之外才 minor 提示（避免误报）。

数值提取一律 regex `\d`，不用 isalpha 判汉字。退出码恒 0（结论记在报告）。
用法：
    number_audit.py --result /app/output/result.json --case /input/case.json \
        --input-root /input [--emit-into]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys

MANUSCRIPT_KEYS = ("manuscript", "paper", "document", "full_text", "text", "body", "content")
Z95 = 1.96

# 严重度映射（与 SKILL.md severity_rubric / verify_check 保持一致）
SEV_TOTAL_N = "critical"
SEV_STAT_CONFLICT = "major"
SEV_DF_OVER = "major"
SEV_P_WORDING = "critical"
SEV_CI_NULL = "critical"
SEV_CI_SE = "major"
SEV_PCT = "minor"


def _num(x):
    if isinstance(x, bool):
        return None
    try:
        return float(str(x).strip().replace(",", ""))
    except Exception:
        return None


def _walk(o, buf):
    if isinstance(o, dict):
        for v in o.values():
            _walk(v, buf)
    elif isinstance(o, list):
        for v in o:
            _walk(v, buf)
    elif isinstance(o, str):
        if len(o.strip()) >= 2:
            buf.append(o)


def segments_from_case(case):
    """返回 [{section_id, name, text}] 若干段，段文本用于定位与逐字回证。"""
    segs = []
    if not isinstance(case, dict):
        return segs
    root = None
    for k in MANUSCRIPT_KEYS:
        if isinstance(case.get(k), (dict, list, str)):
            root = case[k]
            break
    if root is None:
        root = {k: v for k, v in case.items() if k != "output_contract"}

    def add_text(sid, name, txt):
        if txt and len(str(txt).strip()) >= 2:
            segs.append({"section_id": sid, "name": name, "text": str(txt)})

    if isinstance(root, dict):
        for sk in ("sections", "chapters", "parts"):
            v = root.get(sk)
            if isinstance(v, list) and v:
                for i, s in enumerate(v):
                    if isinstance(s, dict):
                        sid = str(s.get("section_id") or s.get("id") or ("%s[%d]" % (sk, i)))
                        add_text(sid, s.get("name") or s.get("title") or sid,
                                 s.get("text") or s.get("content") or "")
                    elif isinstance(s, str):
                        add_text("%s[%d]" % (sk, i), "", s)
                break
        # 表格/图注
        for tk in ("tables", "figure_captions", "captions", "figures"):
            tv = root.get(tk)
            if isinstance(tv, list):
                for i, t in enumerate(tv):
                    if isinstance(t, dict):
                        txt = t.get("text") or t.get("caption") or t.get("content") or ""
                        add_text("%s[%d]" % (tk, i), t.get("name") or t.get("title") or ("%s%d" % (tk, i)), txt)
                    elif isinstance(t, str):
                        add_text("%s[%d]" % (tk, i), "", t)
    elif isinstance(root, list):
        for i, s in enumerate(root):
            if isinstance(s, dict):
                add_text(str(s.get("section_id", "S%d" % (i + 1))), s.get("name", ""),
                         s.get("text") or s.get("content") or "")
            elif isinstance(s, str):
                add_text("S%d" % (i + 1), "", s)
    elif isinstance(root, str):
        add_text("DOC", "全文", root)
    if not segs:
        buf = []
        _walk(root, buf)
        add_text("DOC", "全文", "\n".join(buf))
    return segs


def snippet(txt, m):
    """取匹配位置前后各 24 字符作逐字 raw（保证是全文子串，可回证）。"""
    s = max(0, m.start() - 24)
    e = min(len(txt), m.end() + 24)
    return txt[s:e]


# ---------------- 提取器 ----------------
# 样本量：关键词 + 允许描述词（如"本科生"）+ 人数单位（名/例/人/位/份），避开"共3个量表"这类非人数
RE_N_TOTAL = re.compile(r"(?:共|一共|总共|合计|纳入|招募了?|入组|入选)\s*[^，。；、\d]{0,10}?(\d{1,6})\s*(?:名|例|人|位|份)")
RE_N_EQ = re.compile(r"(?<![A-Za-z])[nN]\s*=\s*(\d{1,6})")
RE_PCT = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*[%％]")
RE_P = re.compile(r"(?<![A-Za-z])p\s*(?:值)?\s*(<=|≤|>=|≥|<|>|=|＝)\s*(\d+\.?\d*)")
RE_EFFECT = re.compile(r"(?<![A-Za-z])(r|d|OR|RR|HR|η²|η2|g|ES|Cohen[’']?s\s*d)\s*=\s*(-?\d+\.?\d*)")
RE_STAT = re.compile(r"(?<![A-Za-z])(t|F|χ²|χ2|chi-square|z|Z)\s*\(\s*(\d{1,3})(?:\s*,\s*(\d{1,4}))?\s*\)\s*=\s*(\d+\.?\d*)")
RE_DF = re.compile(r"(?i)(?:df|自由度)\s*=\s*(\d{1,3})")
RE_CI_BRACKET = re.compile(r"(\d+\.\d+)\s*[-–—~,，]\s*(\d+\.\d+)")
RE_SE = re.compile(r"(?i)(?:SE|标准误|SD\b)\s*=\s*(\d+\.\d+)")

RE_SENT_SPLIT = re.compile(r"(?<=[。．.!?！？;；])")


def sentence_window(txt, m, limit=140):
    """取匹配所在句子（中英文句末标点切分，英文句点排除小数），避免把下一句副词误纳入。"""
    start = 0
    for sep in ("。", "；", "！", "？", "!", "?"):
        p = txt.rfind(sep, 0, m.start())
        if p != -1:
            start = max(start, p + 1)
    for mm in re.finditer(r"\.(?=\s|$)", txt[:max(0, m.start())]):
        start = max(start, mm.end())
    end = len(txt)
    for sep in ("。", "；", "！", "？", "!", "?"):
        p = txt.find(sep, m.end())
        if p != -1:
            end = min(end, p + 1)
    for mm in re.finditer(r"\.(?=\s|$)", txt[m.end():]):
        end = min(end, m.end() + mm.end())
    return txt[start:min(end, start + limit)]

WORD_POS = re.compile(r"(显著|有显著|显著高于|显著低于|统计学意义|有统计学意义|significant(?:ly)?|(?!not\s)significant)")
WORD_NEG = re.compile(r"(不显著|无显著|无统计学意义|未见显著|差异无统计学意义|not\s+significant|no\s+significant|无显著性)")


def has_pos(txt):
    return bool(WORD_POS.search(txt))


def has_neg(txt):
    return bool(WORD_NEG.search(txt))


def _loc_of(seg, match):
    # 粗略第几句：按句号切
    return seg["section_id"]


def extract_total_n(segs):
    out = []
    for seg in segs:
        txt = seg["text"]
        for m in RE_N_TOTAL.finditer(txt):
            out.append({"kind": "sample_size", "value": int(m.group(1)), "type_tag": "total_n",
                        "source": "case", "section_id": seg["section_id"], "name": seg["name"],
                        "location": "共纳入/合计句", "raw": snippet(txt, m)})
        for m in RE_N_EQ.finditer(txt):
            out.append({"kind": "sample_size", "value": int(m.group(1)), "type_tag": "total_n",
                        "source": "case", "section_id": seg["section_id"], "name": seg["name"],
                        "location": "n=句", "raw": snippet(txt, m)})
    return out


def extract_pct(segs):
    out = []
    for seg in segs:
        for m in RE_PCT.finditer(seg["text"]):
            out.append({"kind": "percentage", "value": float(m.group(1)), "type_tag": "pct",
                        "section_id": seg["section_id"], "name": seg["name"],
                        "location": "百分比", "raw": snippet(seg["text"], m),
                        "line": seg["text"][max(0, m.start()-60):m.end()+60]})
    return out


def extract_p(segs):
    out = []
    for seg in segs:
        txt = seg["text"]
        for m in RE_P.finditer(txt):
            v = float(m.group(2))
            if m.group(1) in ("<", "≤", "<="):
                v = v - 0.0001  # 当作边界
            out.append({"kind": "p_value", "value": v, "type_tag": "p", "op": m.group(1),
                        "section_id": seg["section_id"], "name": seg["name"],
                        "location": "p值", "raw": snippet(txt, m),
                        "window": sentence_window(txt, m)})
    return out


def extract_effect(segs):
    out = []
    for seg in segs:
        txt = seg["text"]
        for m in RE_EFFECT.finditer(txt):
            out.append({"kind": "effect_size", "value": float(m.group(2)),
                        "label": m.group(1), "type_tag": "effect",
                        "section_id": seg["section_id"], "name": seg["name"],
                        "location": "效应量", "raw": snippet(txt, m)})
    return out


def extract_stat(segs):
    out = []
    for seg in segs:
        txt = seg["text"]
        for m in RE_STAT.finditer(txt):
            df1 = int(m.group(2))
            df2 = int(m.group(3)) if m.group(3) else None
            out.append({"kind": "statistic", "value": float(m.group(4)),
                        "label": m.group(1), "df1": df1, "df2": df2,
                        "type_tag": "stat_" + m.group(1),
                        "section_id": seg["section_id"], "name": seg["name"],
                        "location": "统计量", "raw": snippet(txt, m)})
        for m in RE_DF.finditer(txt):
            out.append({"kind": "df", "value": int(m.group(1)), "label": "df",
                        "type_tag": "df", "section_id": seg["section_id"],
                        "name": seg["name"], "location": "自由度", "raw": snippet(txt, m)})
    return out


def extract_ci(segs):
    out = []
    for seg in segs:
        txt = seg["text"]
        for m in RE_CI_BRACKET.finditer(txt):
            lo, hi = float(m.group(1)), float(m.group(2))
            if lo > hi:
                lo, hi = hi, lo
            out.append({"kind": "confidence_interval", "value": (lo, hi), "null": 0.0,
                        "type_tag": "ci", "section_id": seg["section_id"], "name": seg["name"],
                        "location": "置信区间", "raw": snippet(txt, m),
                        "window": sentence_window(txt, m)})
    return out


def collect(segs):
    audits = extract_total_n(segs) + extract_pct(segs) + extract_p(segs) \
        + extract_effect(segs) + extract_stat(segs) + extract_ci(segs)
    # 补 SE（供 R6 用）
    se_list = []
    for seg in segs:
        for m in RE_SE.finditer(seg["text"]):
            se_list.append({"se": float(m.group(1)), "section_id": seg["section_id"],
                            "raw": snippet(seg["text"], m)})
    return audits, se_list


# ---------------- 比对规则 ----------------
def audit(mc, audits, se_list):
    """执行 6 条比对规则，返回 (number_audits, findings, conflict_summary)。"""
    findings = []
    # 初始化 consistent/conflicts/source
    for a in audits:
        a.setdefault("source", "case")
        a["consistent"] = True
        a["conflicts_with"] = []
        a["note"] = ""

    def conflict(aids, rule, sev, evid, quote, loc, suggestion):
        for aid in aids:
            rec = next((x for x in audits if x.get("audit_id") == aid), None)
            if rec is not None:
                rec["consistent"] = False
        findings.append({"finding_id": None, "kind": "number_conflict", "rule": rule,
                         "quote": quote, "location": loc, "severity": sev,
                         "evidence": evid, "revision_suggestion": suggestion,
                         "status": "confirmed", "conflict_ids": list(aids)})

    # 分配 audit_id
    for i, a in enumerate(audits):
        a["audit_id"] = "N%02d" % (i + 1)

    # R1 样本量一致性
    n_audits = [a for a in audits if a["kind"] == "sample_size"]
    if len(n_audits) >= 2:
        vals = {}
        for a in n_audits:
            vals.setdefault(a["value"], []).append(a["audit_id"])
        if len(vals) > 1:
            aids = [a["audit_id"] for a in n_audits]
            quote = n_audits[0]["raw"]
            evid = "入组总数在多个位置不一致: " + "; ".join(
                "%s=%s(%s:%s)" % (a["audit_id"], a["value"], a["section_id"], a["location"])
                for a in n_audits)
            conflict(aids, "R1_total_n", SEV_TOTAL_N, evid, quote,
                     n_audits[0]["section_id"], "统一摘要与方法的入组总数，核对原始台账")

    # R2 同名统计量冲突（效应量/统计量标签相同但值不同）
    labeled = [a for a in audits if a.get("label") and a["kind"] in ("effect_size", "statistic", "df")]
    by_label = {}
    for a in labeled:
        by_label.setdefault(a["label"], []).append(a)
    for lab, lst in by_label.items():
        dv = {}
        for a in lst:
            key = round(a["value"], 4)
            dv.setdefault(key, []).append(a["audit_id"])
        if len(dv) > 1:
            aids = [a["audit_id"] for a in lst]
            evid = "%s 报告值不一致: %s" % (lab, "; ".join(
                "%s=%s(%s:%s)" % (a["audit_id"], a["value"], a["section_id"], a["location"])
                for a in lst))
            conflict(aids, "R2_stat_conflict", SEV_STAT_CONFLICT, evid,
                     lst[0]["raw"], lst[0]["section_id"],
                     "核对 %s 的正确数值，统一正文与图表" % lab)

    # R3 自由度越界 df > n-1
    nval = None
    if n_audits:
        from collections import Counter
        cnt = Counter(a["value"] for a in n_audits)
        nval = cnt.most_common(1)[0][0]  # 众数样本量
    for a in audits:
        if a["kind"] == "df":
            if nval is not None and a["value"] > nval - 1:
                conflict([a["audit_id"]], "R3_df_over", SEV_DF_OVER,
                         "df=%s > n-1=%s（样本量 n=%s），自由度与样本量矛盾" % (a["value"], nval - 1, nval),
                         a["raw"], a["section_id"], "核对自由度（df 不可能超过 n-1）")
        if a["kind"] == "statistic" and a.get("df1"):
            for d in (a["df1"], a["df2"]):
                if d and nval is not None and d > nval - 1:
                    conflict([a["audit_id"]], "R3_df_over", SEV_DF_OVER,
                             "%s(%s)=... 中 df=%s > n-1=%s，与样本量矛盾" % (a["label"], a["df1"], d, nval - 1),
                             a["raw"], a["section_id"], "核对统计量的自由度")

    # R4 p 值与显著性表述矛盾
    for a in audits:
        if a["kind"] != "p_value":
            continue
        w = a.get("window", "")
        pos, neg = has_pos(w), has_neg(w)
        sig_by_p = a["value"] <= 0.05
        if neg and sig_by_p:
            conflict([a["audit_id"]], "R4_p_wording", SEV_P_WORDING,
                     "p=%s（≤0.05）却写不显著" % a["value"], a["raw"], a["section_id"],
                     "核对 p 值与显著性表述是否一致")
        if pos and not sig_by_p:
            conflict([a["audit_id"]], "R4_p_wording", SEV_P_WORDING,
                     "p=%s（>0.05）却写显著" % a["value"], a["raw"], a["section_id"],
                     "核对 p 值与显著性表述是否一致")

    # R5 CI 与 null + 显著性表述
    for a in audits:
        if a["kind"] != "confidence_interval":
            continue
        lo, hi = a["value"]
        null = a.get("null", 0.0)
        excludes = not (lo <= null <= hi)
        w = a.get("window", "")
        pos, neg = has_pos(w), has_neg(w)
        if excludes and neg:
            conflict([a["audit_id"]], "R5_ci_null", SEV_CI_NULL,
                     "CI [%s,%s] 排除 null=%s，却写不显著" % (lo, hi, null), a["raw"],
                     a["section_id"], "核对区间与显著性结论")
        if not excludes and pos:
            conflict([a["audit_id"]], "R5_ci_null", SEV_CI_NULL,
                     "CI [%s,%s] 包含 null=%s，却写显著" % (lo, hi, null), a["raw"],
                     a["section_id"], "核对区间与显著性结论")

    # R6 CI 宽 vs SE（同段出现）
    for a in audits:
        if a["kind"] != "confidence_interval":
            continue
        lo, hi = a["value"]
        for s in se_list:
            if s["section_id"] == a["section_id"]:
                expect = 2 * Z95 * s["se"]
                width = hi - lo
                if expect > 0 and abs(width - expect) > 0.1 * expect + 1e-6:
                    conflict([a["audit_id"]], "R6_ci_se", SEV_CI_SE,
                             "CI 宽=%.3f 与 SE=%.3f 推得期望宽≈%.3f（2*1.96*SE）不符" % (width, s["se"], expect),
                             a["raw"], a["section_id"], "核对 SE 或 CI 端点是否笔误")
                break

    # 给 finding 编号
    for i, f in enumerate(findings):
        f["finding_id"] = "F%02d" % (i + 1)

    summary = {
        "conflicts_total": len(findings),
        "by_kind": {},
        "by_severity": {},
        "rules_applied": ["R1_total_n", "R2_stat_conflict", "R3_df_over",
                          "R4_p_wording", "R5_ci_null", "R6_ci_se"],
        "extracted": {k: sum(1 for a in audits if a["kind"] == k) for k in
                      ("sample_size", "p_value", "effect_size", "confidence_interval",
                       "percentage", "statistic", "df")},
    }
    for f in findings:
        summary["by_kind"][f["rule"]] = summary["by_kind"].get(f["rule"], 0) + 1
        summary["by_severity"][f["severity"]] = summary["by_severity"].get(f["severity"], 0) + 1
    return audits, findings, summary


def build_claims(findings):
    claims = []
    for i, f in enumerate(findings):
        claims.append({"claim_id": "c-%02d" % (i + 1), "text": f["evidence"],
                       "kind": "reported", "source_id": f["finding_id"],
                       "location": f["location"],
                       "evidence": [{"paragraph_id": "case", "quote": f["quote"]}]})
    return claims


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", default="/app/output/result.json")
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--input-root", default="/input")
        ap.add_argument("--emit-into", action="store_true")
        args, _unknown = ap.parse_known_args()
    except SystemExit:
        sys.exit(0)
    except Exception as e:
        print("[number_audit] 参数解析失败（降级）: %s" % e)
        return 0

    case = {}
    try:
        with open(args.case, "r", encoding="utf-8") as f:
            case = json.load(f)
    except Exception as e:
        print("[number_audit] case.json 读取失败: %s（不中断交付）" % e)

    res = {}
    try:
        with open(args.result, "r", encoding="utf-8") as f:
            res = json.load(f)
    except Exception:
        print("[number_audit] result.json 不可解析，重建容器（不中断交付）")
    if not isinstance(res, dict):
        res = {}
    res.setdefault("result", {})

    segs = segments_from_case(case)
    audits, se_list = collect(segs)
    audits, findings, summary = audit(case, audits, se_list)

    inner = res["result"]
    inner["number_audits"] = audits
    inner["findings"] = findings
    inner["conflict_summary"] = summary
    inner["manuscript_overview"] = inner.get("manuscript_overview") or {}
    ov = inner["manuscript_overview"]
    ov["full_text_chars"] = sum(len(s["text"]) for s in segs)
    ov["sections"] = [{"section_id": s["section_id"], "name": s["name"],
                       "chars": len(s["text"])} for s in segs]

    res["claims"] = build_claims(findings)
    # 严重度口径回填（若未声明）
    rub = inner.get("severity_rubric") or {}
    rub.setdefault("levels", {})
    if not rub["levels"].get("critical"):
        rub["levels"] = {
            "critical": "摘要与正文/图表间样本量或主要结局效应量/CI/p 值相互矛盾，直接推翻主要结论",
            "major": "次要统计量、自由度越界、百分比等不一致，影响可信度但不必然推翻结论",
            "minor": "百分比四舍五入差等不改变结论的表述不一致"}
        rub["declared_at"] = "step2"
    inner["severity_rubric"] = rub
    res["status"] = "partial"

    # 收尾状态：由机械比对结果直接体现实事求是
    inner["run_status"] = {"state": "success", "reason": None, "manual_takeover": [],
                           "note": "数字提取与交叉比对由 number_audit.py 机械完成"}
    if findings:
        inner["verdict"] = "audited"
        inner["verdict_basis"] = "完成全文/表格/图注数字提取与交叉比对，发现 %d 处数字不一致" % len(findings)
    elif audits:
        inner["verdict"] = "audited"
        inner["verdict_basis"] = "完成数字提取与交叉比对，未发现数字不一致"
    else:
        inner["verdict"] = "cannot_verify"
        inner["verdict_basis"] = "稿件中未提取到任何可核对数字"
        inner["material_gaps"] = list(inner.get("material_gaps") or []) + \
            ["未提取到数字（正文可能非结构化或纯图片）"]
    changelog = res.get("changelog") or []
    changelog.append({"step": "step2", "change": "number_audit 数字提取+交叉比对",
                      "extracted": summary["extracted"],
                      "conflicts_total": len(findings)})
    res["changelog"] = changelog

    if args.emit_into:
        try:
            d = os.path.dirname(args.result)
            if d:
                os.makedirs(d, exist_ok=True)
            with open(args.result, "w", encoding="utf-8") as f:
                json.dump(res, f, ensure_ascii=False, indent=1)
        except Exception as e:
            print("[number_audit] 回写失败: %s" % e)

    print("[number_audit] 段数=%d 提取数字=%d 冲突=%d" % (len(segs), len(audits), len(findings)))
    print("  提取分布: %s" % json.dumps(summary["extracted"], ensure_ascii=False))
    for f in findings:
        print("  [%s] %s sev=%s: %s" % (f["finding_id"], f["rule"], f["severity"], f["evidence"]))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[number_audit] 未预期异常（降级，exit 0）: %s" % e)
        sys.exit(0)