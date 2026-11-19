#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""trace_audit.py — 数值-来源核对表 + 图表交叉引用 + 讨论结论溯源 + 描述/解释分离审计
补强项:
 A) 数字-来源逐条核对表: 草稿中每个数值 → 溯源到 readings.jsonl 的图表登记值（status=matched）
    或 fact_ledger.jsonl 的源文事实（status=ledger）；都对不上 → status=unmatched（FAIL 风险点）。
    核对表整表输出，可直接嵌入 result.json 的 number_source_table 字段。
 B) 结果段交叉引用完整性: readings.jsonl 登记的每张图/表都必须在结果段被正文引用；
    结果段引用的每个图/表编号都必须在 readings 登记过。缺一边 fail。
 C) 讨论结论溯源: 讨论段中每条含结论动词的句子必须带【依据：…】内联标注（指向本研究图/表
    或文献+locator）；输出 discussion_claims 逐条表。缺标注 → fail。
 D) 描述/解释分离: 结果段中把「观察数值」与「推断解释」写在同一句 → 推断-实测混淆数（fail）。
 E) 限定强度机检: 强断言词（证明/证实/表明/导致/归因于）的依据必须定位到本研究图/表；
    推测句（可能/提示/有待）不得配强断言词。逐条输出 {item, template_value, applied, match}。

本轮新增（增益可验证性）:
 * --ablate <mech,mech> 退化/基线模式：关闭指定护栏机制，同一输入再跑一遍做对照。
   关闭机制 ≠ 通过：报告仍诚实记录「本应检出但未检出」的量（detection_coverage 下降）。
 * gain_metrics 块 = 固定评估器(恒定, 不随机制开关变化) + 本模式检出能力 + 流程步骤数
   + 输入指纹(sha1)，供 build_result.py 合成 result.json 的 gain_evidence。
 * --strict-exit：显式要求校验失败时退出码非 0（CI 用）。默认退出码恒为 0，
   失败以 verdict / fail 计数落在报告与 stdout 中，不中断交付链。

用法:
  python3 trace_audit.py --draft /app/output/results_discussion.md \
      --readings /app/work/readings.jsonl --ledger /app/work/fact_ledger.jsonl \
      [--dclaims /app/work/dclaims.jsonl] \
      --out-table /app/work/number_source_table.json --out /app/output/trace_audit.json

容错: 任一输入缺失/损坏 → 对应检查项降级为 skipped 并如实记录，其余项照常执行，不崩溃。
诚实原则: 只报告不修改；unmatched 数值须回材料核对或标[待核]，禁止凭印象改数。
"""
import argparse, hashlib, json, os, re, sys

UNITS = r"(?:mg|ml|mmol|kg|mmHg|kPa|°C|nm|μm|cm|mm|ppm|IU|U/L|ng/mL|pg/mL|g/L|倍|年|月|天|小时|分钟|例|人|株)"
# 统计量 token 必选替代: p= / n= / CI / 数值±误差 / 数值+单位；裸数字(24h/图1编号)不误捕不漏检
NUM_RE = re.compile(r"(?<![\dA-Za-z_.])(?:p\s*[=<]\s*0?\.\d+|n\s*=\s*\d+|CI\s*[-\d.,]+|(?:\d+[\d,]*(?:\.\d+)?\s*(?:%|‰|±\s*\d+(?:\.\d+)?)|(?:\d+[\d,]*(?:\.\d+)?)\s*" + UNITS + r"))", re.I)
REF_RE = re.compile(r"(图|表|Figure|Fig\.?|Table)\s*(\d+)", re.I)
CLAIM_WORDS = ["表明", "提示", "说明", "支持", "证实", "意味着", "推测", "归因", "可能与",
               "原因", "机制", "一致", "不一致", "优于", "高于", "低于", "相关", "反映了", "归结于"]
MARK_RE = re.compile(r"【依据[：:]([^】]+)】")
# 限定强度机检词表: 强断言词要求依据为本研究数据(图表+统计量); 推测词须配限定语
STRONG_WORDS = ["证明", "证实", "表明", "确立了", "决定", "导致", "归因于", "足以说明"]
HEDGE_WORDS = ["可能", "提示", "推测", "有待", "或许", "倾向于", "在一定程度上"]
DATA_MARK = re.compile(r"(本研究|本实验|本试验)?[（(]?(图|表|Figure|Fig\.?|Table)\s*(\d+)")
# 推断/解释类用词（结果段出现即与「只陈述观察」冲突）
INFER_WORDS = ["表明", "说明", "意味着", "由此可见", "提示", "可见", "因此", "所以",
               "原因是", "原因在于", "机制", "导致", "造成", "使得", "归因", "由于",
               "推测", "预期", "反映", "反映出", "证明", "证实", "源于", "得益于",
               "是因为", "系由", "受.*影响"]

# ---- 可退化机制（消融基线）：关闭后对应护栏不再生效，但「本应检出量」如实记录 ----
ABLATABLE = {
    "stat_verify": "统计量逐条回证（数值→图表/台账逐字核对）",
    "strength_audit": "限定强度机检（强断言须本研究数据、推测句须带限定语）",
    "claim_evidence": "讨论结论【依据：…】标注与逐条溯源",
    "crossref": "图表交叉引用双向完整性核对",
    "separation": "结果段描述与解释分离检测",
}

# ---- 流程步骤清单（步骤数计量的真实来源；随机制开关增减）----
WORKFLOW_STEPS = [
    {"stage": 1, "action": "抄写 output_contract 全部字段名与 case_id", "produces": "constraints.json", "mechanism": None},
    {"stage": 1, "action": "落骨架 result.json（字段齐全、status=partial）", "produces": "result.json(skeleton)", "mechanism": None},
    {"stage": 1, "action": "抽取材料文本（PDF/表/图注）", "produces": "extracted/*.txt", "mechanism": None},
    {"stage": 2, "action": "构建事实台账（数值/统计量/DOI 逐字+定位）", "produces": "fact_ledger.jsonl", "mechanism": None},
    {"stage": 2, "action": "图表读数登记（数值/单位/误差棒含义/图注逐字）", "produces": "readings.jsonl", "mechanism": None},
    {"stage": 3, "action": "撰写结果段（按图序、只陈述观察、每段带图表引用）", "produces": "draft.md#结果", "mechanism": None},
    {"stage": 3, "action": "撰写讨论段（结论句末内联【依据：…】）", "produces": "draft.md#讨论", "mechanism": None},
    {"stage": 3, "action": "回填讨论结论溯源表（逐条 claim→来源）", "produces": "dclaims.jsonl", "mechanism": "claim_evidence"},
    {"stage": 4, "action": "数值逐条回证，产出数字-来源核对表", "produces": "number_source_table.json", "mechanism": "stat_verify"},
    {"stage": 4, "action": "事实台账交叉校验（fact_check）", "produces": "fact_check.json", "mechanism": None},
    {"stage": 4, "action": "边界检查（因果/显著性/结果段解释词）", "produces": "boundary_check.json", "mechanism": "separation"},
    {"stage": 4, "action": "图表交叉引用双向核对", "produces": "trace_audit.crossref", "mechanism": "crossref"},
    {"stage": 4, "action": "限定强度机检（强断言↔本研究数据）", "produces": "trace_audit.strength_check", "mechanism": "strength_audit"},
    {"stage": 5, "action": "构建可编辑 docx + md 双版本", "produces": "results_discussion.docx/.md", "mechanism": None},
    {"stage": 5, "action": "渲染预览 PDF/PNG（无渲染器则如实记状态）", "produces": "previews/", "mechanism": None},
    {"stage": 5, "action": "组装 result.json（全文与证据嵌入、字段齐全）", "produces": "result.json", "mechanism": None},
]


def _load_jsonl(path):
    if not path or not os.path.exists(path):
        return None
    rows = []
    try:
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line:
                rows.append(json.loads(line))
        return rows
    except Exception:
        return None


def _norm(s):
    return re.sub(r"[\s,，]", "", str(s))


def _ref_key(m):
    kind = m.group(1)
    kind = "表" if kind in ("表", "Table") or kind.lower().startswith("table") else "图"
    return f"{kind}{int(m.group(2))}"


def _zones(draft):
    def find(pat):
        m = re.search(pat, draft, re.I)
        return m.start() if m else None
    r0 = find(r"#+\s*结\s*果|#+\s*Results")
    d0 = find(r"#+\s*讨\s*论|#+\s*Discussion")
    rz = draft[r0:d0] if (r0 is not None and d0 is not None and d0 > r0) else ""
    dz = draft[d0:] if d0 is not None else ""
    return rz, dz


def _sha1(path):
    if not path or not os.path.exists(path):
        return None
    try:
        return hashlib.sha1(open(path, "rb").read()).hexdigest()[:16]
    except Exception:
        return None


# ---- A) 数字-来源逐条核对表 ----
def build_table(draft, readings, ledger):
    # 图表登记值索引: 归一化值 -> {"ref":…, "locator":…, "verbatim":…}
    reg, led = {}, {}
    for r in readings or []:
        loc = r.get("locator", "")
        for v in r.get("values", []):
            val = _norm(v.get("value", ""))
            if val:
                reg.setdefault(val, {"ref": r.get("ref", ""), "locator": loc,
                                     "verbatim": str(v.get("value", ""))[:80]})
    for f in ledger or []:
        val = _norm(f.get("value", ""))
        if val:
            led.setdefault(val, {"ref": f.get("source", ""), "locator": f.get("locator", ""),
                                 "verbatim": str(f.get("value", ""))[:80]})
    table, unmatched, checked = [], [], 0
    for ln, line in enumerate(draft.splitlines(), 1):
        s = line.strip()
        if s.startswith(("|", "```", "#")) and not s.startswith("#"):
            continue
        for m in NUM_RE.finditer(line):
            v = m.group(0).strip()
            if not re.search(r"\d", v):
                continue
            checked += 1
            norm = _norm(v)
            src = reg.get(norm)
            status = "matched"
            if not src:
                # 宽松重试: 去符号取数字核心做包含匹配
                core = re.sub(r"[^\d.%±/]", "", norm)
                hit = None
                if core:
                    for k, meta in reg.items():
                        if core in k:
                            hit = meta
                            break
                if hit:
                    src = hit
                else:
                    src = led.get(norm)
                    status = "ledger" if src else "unmatched"
            row = {"line": ln, "value": v, "context": line.strip()[:100],
                   "source_ref": (src or {}).get("ref", ""), "source_locator": (src or {}).get("locator", ""),
                   "verbatim": (src or {}).get("verbatim", ""), "status": status}
            table.append(row)
            if status == "unmatched":
                unmatched.append(row)
    return {"table": table, "checked": checked, "unmatched": len(unmatched),
            "unmatched_detail": unmatched[:60]}


# ---- B) 结果段图表交叉引用完整性 ----
def crossref(results_zone, readings):
    registered = set()
    for r in readings or []:
        ref = str(r.get("ref", "")).strip()
        if not ref:
            continue
        m = REF_RE.search(ref)
        registered.add(_ref_key(m) if m else ref)
    cited = {_ref_key(m) for m in REF_RE.finditer(results_zone)}
    reg_disp = sorted(registered)
    missing_in_text = sorted(registered - cited)   # 登记了但结果段没引用
    unknown_in_text = sorted(cited - registered)   # 引用了但没登记
    return {"registered": reg_disp, "cited_in_results": sorted(cited),
            "missing_in_text": missing_in_text, "unknown_in_text": unknown_in_text,
            "verdict": "pass" if not (missing_in_text or unknown_in_text) else "fail",
            "hint": "登记的每张图/表都要在结果段被引用；引用编号须与 readings 登记一致（多面板引用如 图2A-C 视为引用图2）。"}


# ---- C) 讨论结论溯源 + 限定强度机检 ----
def _evidence_quote(mark_txt, readings, ledger):
    """从【依据】内容定位来源，摘录 ≤40 字逐字证据。返回 (kind, evidence, source_id, location)。"""
    m = DATA_MARK.search(mark_txt)
    if m:
        kind_n = m.group(2)
        kind_n = "表" if kind_n in ("表", "Table") or kind_n.lower().startswith("table") else "图"
        ref = f"{kind_n}{int(m.group(3))}"
        for r in readings or []:
            if str(r.get("ref", "")).replace(" ", "") == ref:
                q = str(r.get("caption_quote", "")) or str(
                    (r.get("values") or [{}])[0].get("value", ""))
                return ("本研究数据", q[:40], ref, r.get("locator", ""))
    lit = re.search(r"文献\s*\[?(\w+)\]?", mark_txt)
    if lit:
        sid = f"文献[{lit.group(1)}]"
        loc = re.search(r"[A-Z]\d+[:：]p\d+", mark_txt)
        return ("文献", mark_txt[:40], sid, loc.group(0) if loc else "")
    if any(k in mark_txt for k in ("推测", "待补", "待核")):
        return ("推测", mark_txt[:40], "", "")
    return ("未定位", mark_txt[:40], "", "")


def _strength_check(sent, mark_txt, evidence_kind):
    """限定强度机检: 返回 {item, check_type, template_value, applied, match} 三元组列表。
    check_type=strength → 受 strength_audit 机制管辖；check_type=annotation → 受 claim_evidence 管辖。"""
    out = []
    is_strong = any(w in sent for w in STRONG_WORDS)
    is_hedge = any(w in sent for w in HEDGE_WORDS)
    has_data = evidence_kind == "本研究数据"
    if is_strong:
        out.append({"item": "strong_claim_backed_by_data", "check_type": "strength", "cid_sent": sent[:60],
                    "template_value": "强断言词(证明/证实/表明/导致/归因于)的依据须为本研究数据(图表)",
                    "applied": evidence_kind, "match": has_data})
    if is_hedge and not is_strong:
        out.append({"item": "hedged_claim_consistent", "check_type": "strength", "cid_sent": sent[:60],
                    "template_value": "推测句须带限定语且依据标注为推测/文献，不得直接给本研究数据强结论",
                    "applied": evidence_kind, "match": evidence_kind in ("推测", "文献", "未定位") or bool(mark_txt)})
    if not is_strong and not is_hedge and mark_txt:
        out.append({"item": "claim_has_support_annotation", "check_type": "annotation", "cid_sent": sent[:60],
                    "template_value": "结论句句末带【依据：…】且 kind 可定位", "applied": evidence_kind,
                    "match": evidence_kind in ("本研究数据", "文献")})
    return out


def disc_claims(disc_zone, dclaims, readings=None, ledger=None):
    """enforce=False 时仍计算全部 claim 与强度信息（供固定评估器），但不计入 fail。"""
    claims, missing, strength_fails = [], [], []
    cid = 0
    for raw in re.split(r"(?<=[。！？])", disc_zone.replace("\n", " ")):
        s = raw.strip()
        if not s or len(s) < 8:
            continue
        if not any(w in s for w in CLAIM_WORDS):
            continue
        cid += 1
        mark = MARK_RE.search(s)
        mark_txt = mark.group(1).strip() if mark else ""
        kind, ev, sid, loc = _evidence_quote(mark_txt, readings, ledger) if mark else ("", "", "", "")
        row = {"cid": "D%02d" % cid, "claim": s[:160],
               "kind": kind, "evidence": ev, "source_id": sid, "location": loc,
               "support": mark_txt, "strength": "推测" if any(k in s for k in ("可能", "提示", "推测", "有待")) else "数据/文献支持",
               "annotated": bool(mark)}
        row["strength_checks"] = _strength_check(s, mark_txt, kind)
        for sc in row["strength_checks"]:
            if not sc["match"]:
                strength_fails.append(sc)
        claims.append(row)
        if not mark:
            missing.append(row)
    bound = len(claims) - len(missing)
    strength_fail = [sc for sc in strength_fails if sc.get("check_type") == "strength"]
    annot_fail = [sc for sc in strength_fails if sc.get("check_type") == "annotation"]
    return {"claims": claims, "total": len(claims), "annotated": bound, "missing": missing,
            "strength_check": {"checked": sum(len(c["strength_checks"]) for c in claims),
                               "fail": len(strength_fails),
                               "strength_fail": len(strength_fail), "strength_fail_detail": strength_fail[:12],
                               "annotation_fail": len(annot_fail), "annotation_fail_detail": annot_fail[:12],
                               "fail_detail": strength_fails[:12]},
            "verdict": "pass" if (claims and not missing and not strength_fails) or not claims else "fail",
            "dclaims_file_bound": len(dclaims or []),
            "hint": "每条结论句末加【依据：图2A；文献[4] M05:p12】；强断言词须配本研究数据依据；推测句须带限定语。"}


# ---- D) 描述/解释分离 + 结果表述抽取（题面「读得准/分得清/核得了」语义层）----
def extract_result_statements(results_zone, readings):
    """逐句抽取结果段陈述：数值、图表引用、是否只陈述观察、是否带统计量。
    输出 result_statements：{sid, text, numbers[], refs[], stat_expressions[], observation_only, issues[]}"""
    reg = {}
    for r in readings or []:
        ref = str(r.get("ref", "")).strip()
        m = REF_RE.search(ref)
        if m:
            reg.setdefault(_ref_key(m), {"locator": r.get("locator", ""),
                                          "caption_quote": str(r.get("caption_quote", ""))[:40]})
    out = []
    for i, raw in enumerate(re.split(r"(?<=[。！？])", results_zone.replace("\n", " ")), 1):
        s = raw.strip()
        if len(s) < 6:
            continue
        nums = [m.group(0).strip() for m in NUM_RE.finditer(s) if re.search(r"\d", m.group(0))]
        refs = [_ref_key(m) for m in REF_RE.finditer(s)]
        infer_hit = [w for w in INFER_WORDS if re.search(w, s)]
        issues = []
        if infer_hit:
            issues.append("inference_in_results")
        if nums and not refs:
            issues.append("numeric_without_figure_ref")
        for rf in refs:
            if reg and rf not in reg:
                issues.append(f"ref_not_registered:{rf}")
        out.append({"sid": "R%02d" % i, "text": s[:200], "numbers": nums, "refs": refs,
                    "stat_expressions": [n for n in nums if re.search(r"p\s*[=<]|n\s*=|CI|±", n)],
                    "observation_only": not infer_hit, "issues": issues,
                    "locators": [reg[rf]["locator"] for rf in refs if rf in reg]})
    return out


def separation_check(results_zone):
    """结果段中同一句既含实测数值又含推断/解释用词 → 推断-实测混淆。"""
    confusions, pure_observe, total_sent = [], 0, 0
    for raw in re.split(r"(?<=[。！？])", results_zone.replace("\n", " ")):
        s = raw.strip()
        if len(s) < 6:
            continue
        total_sent += 1
        has_num = bool(NUM_RE.search(s))
        infer_hit = [w for w in INFER_WORDS if re.search(w, s)]
        if has_num and infer_hit:
            confusions.append({"sentence": s[:140], "inference_words": infer_hit,
                               "numbers": [m.group(0) for m in NUM_RE.finditer(s)][:6],
                               "hint": "结果段只陈述观察；把「这表明/源于…」等解释句整体移入讨论段。"})
        elif has_num and not infer_hit:
            pure_observe += 1
    return {"sentences": total_sent, "pure_observation_sentences": pure_observe,
            "inference_measurement_confusion": len(confusions), "confusions": confusions[:20],
            "verdict": "pass" if not confusions else "fail",
            "hint": "结果段句子同时出现实测数值与推断词即判混淆；解释统一放讨论段。"}


# ---- E) 增益计量：固定评估器 + 本模式检出能力 + 步骤数 ----
def evaluate_fixed(tab, xr, dc, sep):
    """固定评估器：对同一草稿恒定计算，不随机制开关变化（两遍跑必须完全一致）。"""
    rows = tab["table"]
    stat_total = len(rows)
    stat_backed = sum(1 for r in rows if r["status"] in ("matched", "ledger"))
    stat_unverified = sum(1 for r in rows if r["status"] == "unmatched")
    sc = dc.get("strength_check", {})
    strong_bad = sc.get("strength_fail", 0)
    annot_bad = sc.get("annotation_fail", 0)
    confusion = sep.get("inference_measurement_confusion", 0)
    claim_missing = len(dc.get("missing", []))
    xref_gap = len(xr.get("missing_in_text", [])) + len(xr.get("unknown_in_text", []))
    defects = {
        "stat_unverified": stat_unverified,
        "strong_claim_without_data_basis": strong_bad,
        "inference_measurement_confusion": confusion,
        "claim_missing_evidence": claim_missing + annot_bad,
        "crossref_gap": xref_gap,
    }
    return {
        "stat_statements_total": stat_total,
        "stat_statements_backed": stat_backed,
        "stat_evidence_rate": round(stat_backed / stat_total, 4) if stat_total else None,
        "strong_claim_violations": strong_bad,
        "inference_measurement_confusion": confusion,
        "manual_review_items": sum(defects.values()),
        "defects": defects,
        "total_defects": sum(defects.values()),
        "note": "固定评估器：同一草稿下恒定，与护栏开关无关，用于证明两遍跑输入一致。",
    }


def build_gain_metrics(ablate, tab, xr, dc, sep, fixed, fingerprint):
    """本模式检出能力 + 流程步骤数 + 输入指纹。"""
    on = {k: (k not in ablate) for k in ABLATABLE}
    sc = dc.get("strength_check", {})
    detected = {
        "stat_unverified": tab["unmatched"] if on["stat_verify"] else 0,
        "strong_claim_without_data_basis": sc.get("strength_fail", 0) if on["strength_audit"] else 0,
        "inference_measurement_confusion": sep.get("inference_measurement_confusion", 0) if on["separation"] else 0,
        "claim_missing_evidence": (len(dc.get("missing", [])) + sc.get("annotation_fail", 0)) if on["claim_evidence"] else 0,
        "crossref_gap": (len(xr.get("missing_in_text", [])) + len(xr.get("unknown_in_text", []))) if on["crossref"] else 0,
    }
    detected_total = sum(detected.values())
    total = fixed["total_defects"]
    skipped_steps = [s for s in WORKFLOW_STEPS if s["mechanism"] and s["mechanism"] in ablate]
    executed_steps = [s for s in WORKFLOW_STEPS if s not in skipped_steps]
    # 交付口径（随模式变化）：本模式实际交付给下游的可核验量与人工负担
    auto_verified = (sum(1 for r in tab["table"] if r["status"] in ("matched", "ledger"))
                     if on["stat_verify"] else 0)
    stat_total = fixed.get("stat_statements_total", 0)
    delivered = {
        "auto_verified_statements": auto_verified,
        "statements_requiring_manual_source_check": max(stat_total - auto_verified, 0),
        # 交付口径的有据率：本模式实际完成逐字回证的统计表述占比（固定评估器口径恒定，交付口径随模式变化）
        "delivered_evidence_rate": round(auto_verified / stat_total, 4) if stat_total else None,
        # 残留缺陷率：本模式未暴露、因而会带着进入交付的缺陷占真实缺陷总数的比例
        "residual_defects": max(total - detected_total, 0),
        "residual_defect_rate": round(max(total - detected_total, 0) / total, 4) if total else None,
        "defects_visible_to_reviewer": detected_total,
        "defects_hidden_from_reviewer": max(total - detected_total, 0),
        "reviewer_manual_burden": max(stat_total - auto_verified, 0) + max(total - detected_total, 0),
        "note": "reviewer_manual_burden = 需人工回材料核对的统计表述数 + 本模式未暴露给复核者的缺陷数。"
                "退化模式不是「负担更小」，而是缺陷对复核者不可见（假象）。",
    }
    return {
        "mode": "ablate_baseline" if ablate else "full",
        "ablate_requested": sorted(ablate),
        "ablate_legend": {k: ABLATABLE[k] for k in sorted(ablate)},
        "mechanism_enabled": on,
        "fixed_evaluator": fixed,
        "detected_defects": detected,
        "detected_total": detected_total,
        "detection_coverage": round(detected_total / total, 4) if total else None,
        "detection_coverage_note": "关闭机制 ≠ 通过：未检出的缺陷不等于不存在，缺口须回材料人工核对。",
        "delivered": delivered,
        "steps_total": len(WORKFLOW_STEPS),
        "steps_executed": len(executed_steps),
        "steps_skipped": [{"stage": s["stage"], "action": s["action"], "skipped_mechanism": s["mechanism"]} for s in skipped_steps],
        "step_list": [{"stage": s["stage"], "action": s["action"], "produces": s["produces"],
                       "mechanism": s["mechanism"], "executed": s not in skipped_steps} for s in WORKFLOW_STEPS],
        "input_fingerprint": fingerprint,
    }


def main():
    """顶层安全网：任何异常都不得中断交付链；如实记录后返回 0。"""
    try:
        return _run()
    except Exception as e:
        print(json.dumps({"ok": False, "verdict": "fail", "error": str(e)[:400],
                          "note": "审计脚本内部异常，已如实记录；交付链不中断，收尾仍继续。"},
                         ensure_ascii=False))
        return 0


class _Usage(Exception):
    """argparse 用法错误（缺必填参数）——按内容级失败处理，不中断交付链。"""


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise _Usage(message)


def _run():
    ap = _Parser()
    ap.add_argument("--draft", required=True)
    ap.add_argument("--readings", default=None)
    ap.add_argument("--ledger", default=None)
    ap.add_argument("--dclaims", default=None)
    ap.add_argument("--out-table", default=None, help="number_source_table.json 输出路径（供 build_result.py 嵌入）")
    ap.add_argument("--out", default=None, help="trace_audit.json 报告路径")
    ap.add_argument("--ablate", default=None,
                    help="退化/基线模式：逗号分隔机制名，可选 " + "/".join(sorted(ABLATABLE)))
    ap.add_argument("--strict-exit", action="store_true",
                    help="校验失败时退出码非 0（CI 用）；默认恒 0，不中断交付链")
    try:
        args = ap.parse_args()
    except _Usage as e:
        print(json.dumps({"ok": False, "verdict": "fail", "fail_count": 1,
                          "error": f"用法错误: {e}",
                          "hint": "必填参数缺失，请补 --draft（可选 --readings/--ledger/--dclaims/--out/--out-table/--ablate/--strict-exit）。",
                          "note": "退出码恒 0：交付链不中断，已如实记录。"}, ensure_ascii=False))
        return 0

    warnings = []
    ablate = set()
    for a in (args.ablate or "").split(","):
        a = a.strip()
        if not a:
            continue
        if a in ABLATABLE:
            ablate.add(a)
        else:
            warnings.append(f"unknown_ablate_mechanism:{a}")

    try:
        draft = open(args.draft, encoding="utf-8").read()
    except Exception as e:
        # 草稿不可读也要枚举闸门：下游据此知道哪些检查项根本没跑
        pre_gates = {}
        for key, path in (("readings", args.readings), ("ledger", args.ledger), ("dclaims", args.dclaims)):
            pre_gates[key] = ("skipped_not_provided" if not path else
                              "not_found" if not os.path.exists(path) else "unreadable")
        pre_notes = "; ".join(f"gate[{k}]={v}：未运行，下游不得宣称该项已核对" for k, v in pre_gates.items())
        print(json.dumps({"ok": False, "error": f"draft unreadable: {e}",
                          "verdict": "fail", "fail_count": 1, "gates": pre_gates,
                          "gate_notes": pre_notes,
                          "note": "交付链不中断：如实记录后继续收尾。"},
                         ensure_ascii=False))
        return 0
    readings = _load_jsonl(args.readings)
    ledger = _load_jsonl(args.ledger)
    dclaims = _load_jsonl(args.dclaims)

    # 闸门状态显式枚举: enforced / skipped_not_provided / not_found / unreadable
    gates = {}

    def gate_state(path, loaded, name):
        if not path:
            return "skipped_not_provided"
        if not os.path.exists(path):
            return "not_found"
        if loaded is None:
            return "unreadable"
        return "enforced"
    gates["readings"] = gate_state(args.readings, readings, "readings")
    gates["ledger"] = gate_state(args.ledger, ledger, "ledger")
    gates["dclaims"] = gate_state(args.dclaims, dclaims, "dclaims")
    gate_notes = {k: {"enforced": "",
                      "skipped_not_provided": f"gate[{k}]=skipped_not_provided：未运行，下游不得宣称该项已核对",
                      "not_found": f"gate[{k}]=not_found：文件不存在，下游不得宣称该项已核对",
                      "unreadable": f"gate[{k}]=unreadable：解析失败，下游不得宣称该项已核对"}[v]
                  for k, v in gates.items() if v != "enforced"}
    gate_notes_str = "; ".join(gate_notes.values()) if gate_notes else "全部闸门 enforced"

    # 全量计算（固定评估器与模式判定共用同一份计算结果，保证两遍跑可比）
    tab = build_table(draft, readings, ledger)
    rz, dz = _zones(draft)
    if readings is not None and rz:
        xr = crossref(rz, readings)
    else:
        xr = {"verdict": "skipped", "gate": gates["readings"],
              "hint": "readings 缺失或未定位到 Results 区段，交叉引用检查跳过（gate 状态见 gates）"}
    if dz:
        dc = disc_claims(dz, dclaims, readings, ledger)
    else:
        dc = {"verdict": "skipped", "gate": "no_discussion_zone",
              "hint": "未定位到 Discussion 区段，讨论溯源检查跳过"}
    if rz:
        sep = separation_check(rz)
    else:
        sep = {"verdict": "skipped", "gate": "no_results_zone", "inference_measurement_confusion": 0,
               "confusions": [], "sentences": 0, "pure_observation_sentences": 0,
               "hint": "未定位到 Results 区段，描述/解释分离检查跳过"}
    rstat = extract_result_statements(rz, readings) if rz else []

    fixed = evaluate_fixed(tab, xr, dc, sep)
    fixed["result_statements"] = {
        "total": len(rstat),
        "observation_only": sum(1 for s in rstat if s["observation_only"]),
        "with_numeric_without_ref": sum(1 for s in rstat if "numeric_without_figure_ref" in s["issues"]),
        "with_unregistered_ref": sum(1 for s in rstat if any(i.startswith("ref_not_registered") for i in s["issues"])),
    }
    fingerprint = {"draft": _sha1(args.draft), "readings": _sha1(args.readings),
                   "ledger": _sha1(args.ledger), "dclaims": _sha1(args.dclaims)}
    gain = build_gain_metrics(ablate, tab, xr, dc, sep, fixed, fingerprint)

    # 生效判定：被关闭的机制不计入 fail，但如实记录「本应检出未检出」
    stat_on = "stat_verify" not in ablate
    strength_on = "strength_audit" not in ablate
    claim_on = "claim_evidence" not in ablate
    xref_on = "crossref" not in ablate
    sep_on = "separation" not in ablate

    sc = dc.get("strength_check", {})
    n_stat = tab["unmatched"] if stat_on else 0
    n_strength = sc.get("strength_fail", 0) if strength_on else 0
    n_annot = (len(dc.get("missing", [])) + sc.get("annotation_fail", 0)) if claim_on else 0
    n_xref = (len(xr.get("missing_in_text", [])) + len(xr.get("unknown_in_text", []))) if xref_on else 0
    n_sep = sep.get("inference_measurement_confusion", 0) if sep_on else 0

    hard_fail = bool(n_stat or n_strength or n_annot or n_xref or n_sep)
    fail_detail = {
        "stat_unverified": n_stat, "strong_claim_without_data_basis": n_strength,
        "claim_missing_evidence": n_annot, "crossref_gap": n_xref,
        "inference_measurement_confusion": n_sep,
    }

    if not stat_on:
        gates["stat_verify"] = "not_enforced_ablate"
        gate_notes_str += "; gate[stat_verify]=not_enforced_ablate：本轮为退化对照运行，该护栏未生效，下游不得宣称已回证"
    if not strength_on:
        gates["strength_audit"] = "not_enforced_ablate"
        gate_notes_str += "; gate[strength_audit]=not_enforced_ablate：本轮为退化对照运行，该护栏未生效"
    if not claim_on:
        gates["claim_evidence"] = "not_enforced_ablate"
        gate_notes_str += "; gate[claim_evidence]=not_enforced_ablate：本轮为退化对照运行，该护栏未生效"
    if not xref_on:
        gates["crossref"] = "not_enforced_ablate"
        gate_notes_str += "; gate[crossref]=not_enforced_ablate：本轮为退化对照运行，该护栏未生效"
    if not sep_on:
        gates["separation"] = "not_enforced_ablate"
        gate_notes_str += "; gate[separation]=not_enforced_ablate：本轮为退化对照运行，该护栏未生效"

    report = {"draft": args.draft,
              "gates": gates, "gate_notes": gate_notes_str,
              "number_source_summary": {"checked": tab["checked"], "matched":
                                        sum(1 for r in tab["table"] if r["status"] == "matched"),
                                        "ledger": sum(1 for r in tab["table"] if r["status"] == "ledger"),
                                        "unmatched": tab["unmatched"]},
              "crossref": xr, "discussion_claims": dc, "separation": sep,
              "result_statements": rstat,
              "gain_metrics": gain,
              "warnings": warnings,
              "degraded": ([gate_notes_str] if gate_notes else []) + warnings,
              "verdict": "fail" if hard_fail else "pass",
              "fail_count": sum(fail_detail.values()),
              "fail_by_item": fail_detail,
              "hint": "unmatched 数值回材料核对或标[待核]；missing_in_text 补引用；讨论句补【依据：…】标注；strength_check fail 句降语气或补数据依据。"}
    if args.out_table:
        if stat_on:
            os.makedirs(os.path.dirname(args.out_table) or ".", exist_ok=True)
            json.dump(tab["table"], open(args.out_table, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        else:
            # 机制关闭 → 不产出核对表（无回证即无核对表），如实说明
            report["number_source_table_note"] = "stat_verify 机制已关闭，本轮未产出数字-来源核对表。"
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        json.dump(report, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({"verdict": report["verdict"], "checked": tab["checked"],
                      "unmatched": tab["unmatched"],
                      "crossref": xr.get("verdict"), "claims": f"{dc.get('annotated', 0)}/{dc.get('total', 0)}",
                      "strength_fail": sc.get("strength_fail", 0),
                      "annotation_fail": sc.get("annotation_fail", 0),
                      "separation_confusion": sep.get("inference_measurement_confusion", 0),
                      "fail_count": report["fail_count"],
                      "mode": gain["mode"], "detection_coverage": gain["detection_coverage"],
                      "steps_executed": gain["steps_executed"], "steps_total": gain["steps_total"],
                      "gates": gates}, ensure_ascii=False))
    return 1 if (hard_fail and args.strict_exit) else 0


if __name__ == "__main__":
    sys.exit(main())
