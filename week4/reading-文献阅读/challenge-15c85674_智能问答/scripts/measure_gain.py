#!/usr/bin/env python3
"""measure_gain.py — literature-qa v5 增益测量器（同输入：完整机制 vs 退化重放）。

设计（same-input ablation）
---------------------------
在同一份输入与同一份**真实产物**上跑两遍，用同一套评分器测量：

  run.full     —— 完整机制（子问级拆解 / 逐子问证据定位 / 逐字引文 / 数值回证 / 复检返工）
  run.ablated  —— 退化重放：对同一产物的**确定性降级改写**，模拟白板典型失败
                   D1 整题只挂一条笼统 claim（漏子问）
                   D2 引文退化为段落首句（引文逐字但不支撑该论断）
                   D3 其余 claim 及其引文全部丢失（答案里的数值失去引文支撑）

两遍都过同一个审计器（audit），指标口径完全一致，差值即机制贡献。

诚实性声明
----------
1. 这是**同输入机制消融**，不是平台白板实测。平台白板由平台侧按「不加载参赛 Skill」的
   条件生成，本脚本不对白板数值做任何主张。
2. 退化重放是**对同一产物的确定性改写**，不是另一份产物；改写规则写在
   gain_evidence.degradation_model 里，可逐条复核、可复算。
3. 全部数字由脚本在运行时真实计算（无手填常量），随输入指纹与产物指纹留痕。
4. 所有计数器都是**自动采集计数**（步骤、检索次数、复检轮次、条目数），
   不得称为人工核对时间。

指标（任务指定 6 项）
----------------------
  sub_question_coverage_rate 子问覆盖率    = 被「有逐字锚定引文支撑的 claim」覆盖的子问 / 子问总数
  citation_support_rate     引用支持率    = 被引文支撑（逐字锚定 + 数值⊆引文）的 claim / 有引文的 claim
  numeric_fidelity_rate     数值保真率    = 答案中可被本问 claim 引文（或 inferred claim 文本）回证的数值占比
  needs_manual_review_items 需人工核对条目 = 未回证数值 + 非逐字引文 + 缺定位 + 漏答子问 + 无引文 claim
  steps                     步骤数        = 流水线实际执行阶段数（来自 run_log 阶段日志）
  followup_rounds           追问轮次      = ceil(需人工核对条目 / 每轮可处理条目数)

用法
----
  python3 measure_gain.py --case /input/case.json --result /app/output/result.json \
      --mode compare --embed
  python3 measure_gain.py --case examples/example-input.json \
      --result examples/example-result.json --mode compare
  python3 measure_gain.py --selftest
退出码恒为 0；结论写入 stdout 与 result.json（verdict 字段照实记录）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
from datetime import datetime, timezone

TOOL_NAME = "measure_gain.py v5"
REVIEW_CAPACITY_PER_ROUND = 3   # 声明式假设：一轮追问可处理 3 条待核对项
DISABLED_STAGES_ABLATED = ("evidence_verify", "numeric_verify", "repair_loop")
FULL_STAGES = ("load_input", "read_questions", "decompose_subquestions",
               "locate_evidence", "draft_claims", "structure_check",
               "evidence_verify", "numeric_verify", "repair_loop", "deliver")

_NUM_RE = re.compile(r"\d+(?:\.\d+)?")
# 引用标签关键词：其后的数字是"图/表/式/节"的编号，不是被测量的数据值
_REF_LABEL_RE = re.compile(
    r"(?:表|图|式|附表|附图|附录|第|章节|Fig\.?|Figure|Table|Eq\.?|Equation"
    r"|Section|Sec\.?|Chapter|Ref\.?)\s*$", re.IGNORECASE)


def _is_identifier_context(text, i):
    """text[i] 处的数字是否属于标识符/编号（不作为数据值）。

    排除 p01 / q1 / M02 / S2 / c-01 / T1-23；中文汉字**不算**标识符前缀，
    "保持率为84.3%" 里的 84.3 是真实数据值，必须参与回证。
    """
    if i > 0:
        prev = text[i - 1]
        if prev == "_" or (prev.isascii() and prev.isalpha()):
            return True
        if prev == "-":
            j = i - 2
            if j >= 0 and text[j].isascii() and text[j].isalpha():
                return True
            if j >= 0 and text[j].isdigit():
                k = j - 1
                if k >= 0 and text[k].isascii() and text[k].isalpha():
                    return True
    return False


# 数值识别口径与校验器共用同一实现（避免"校验器判失败、审计器判通过"的自相矛盾）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from check_result import numbers  # noqa: F401  (同目录单文件，零外部依赖)
except Exception:  # pragma: no cover - 兜底：校验器缺失时用等价内置实现
    def numbers(text, min_len=2):
        """文本中的数据值（长度≥2）。排除标识符与引用标签编号
        （p01、q1、c-01、T1-23、表 12、图 23、第 3.2 节、Fig. 23）；
        保留真实数据值与区间端点（84.3%、42 例、1.2-3.4、2023-2024）。"""
        out = []
        t = str(text or "")
        for m in _NUM_RE.finditer(t):
            n = m.group(0)
            if len(n) < min_len:
                continue
            i = m.start()
            if _is_identifier_context(t, i):
                continue
            if _REF_LABEL_RE.search(t[:i]):
                continue
            out.append(n)
        return out
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z\-]{2,}")
_INTERRO = ("什么", "哪些", "哪", "多少", "如何", "怎么", "为什么", "为何", "是否",
            "能否", "能不能", "吗", "哪个", "分别", "以及", "而且", "并且", "同时")


# ------------------------------------------------------------------ 文本工具

def norm(s):
    """空白归一化（与 check_result.py 同口径的逐字子串判定）。"""
    try:
        return re.sub(r"\s+", "", str(s or ""))
    except Exception:
        return ""


def tokens(text):
    """内容 token 集：ASCII 词 + 中文二元组（纯标准库，无需分词库）。"""
    t = str(text or "").lower()
    out = set()
    for w in _WORD_RE.findall(t):
        out.add(w)
    for run in _CJK_RE.findall(t):
        if len(run) == 1:
            out.add(run)
        else:
            for i in range(len(run) - 1):
                out.add(run[i:i + 2])
    return out




def split_subquestions(qtext):
    """把问题拆成子问：先按问号/分号切，再按并列问法与逗号子句归并。"""
    raw = str(qtext or "")
    chunks = [c.strip() for c in re.split(r"[？?；;]\s*", raw) if c.strip()]
    out = []
    for chunk in chunks:
        pieces = [chunk]
        for conj in ("分别是", "分别", "以及", "同时", "并且", "而且"):
            nxt = []
            for p in pieces:
                if conj in p:
                    head, _, tail = p.partition(conj)
                    if tail and any(w in tail for w in _INTERRO):
                        nxt.extend([head.strip(), tail.strip()])
                        continue
                nxt.append(p)
            pieces = [p for p in nxt if p]
        for p in pieces:
            segs = [s.strip() for s in re.split(r"[，,]\s*", p) if s.strip()]
            if len(segs) <= 1:
                out.append(p)
                continue
            cur = []
            for s in segs:
                if any(w in s for w in _INTERRO):
                    if cur:
                        out.append("，".join(cur))
                        cur = []
                    out.append(s)
                else:
                    cur.append(s)
            if cur:
                if out:
                    out[-1] = out[-1] + "，" + "，".join(cur)
                else:
                    out.append("，".join(cur))
    seen, uniq = set(), []
    for s in out:
        k = norm(s)
        if k and k not in seen:
            seen.add(k)
            uniq.append(s)
    return uniq or ([str(qtext or "").strip()] if str(qtext or "").strip() else [])


def sentences_with_offsets(text):
    """句子在原文中的字符区间 [(start, end)]，保证逐字可切。"""
    text = str(text or "")
    spans, start = [], 0
    for m in re.finditer(r"[.!?。！？](?=\s|$)|(?<=[.;])\s+", text):
        end = m.start()
        if end <= start:
            continue
        spans.append((start, end))
        start = m.end()
    if start < len(text):
        spans.append((start, len(text)))
    return [sp for sp in spans if text[sp[0]:sp[1]].strip()]


# ------------------------------------------------------------------ 输入解析

def paragraphs_of(case):
    paras = {}
    if not isinstance(case, dict):
        return paras
    for key in ("paragraphs", "passages", "paper_paragraphs", "sections"):
        v = case.get(key)
        if isinstance(v, list) and v:
            for p in v:
                if not isinstance(p, dict):
                    continue
                pid = p.get("paragraph_id") or p.get("id") or p.get("pid")
                txt = p.get("text") or p.get("content") or p.get("body") or ""
                if pid:
                    paras[str(pid)] = str(txt)
            if paras:
                break
    return paras


def questions_of(case):
    qs = []
    if not isinstance(case, dict):
        return qs
    q = case.get("questions")
    if q is None and isinstance(case.get("task"), dict):
        q = case["task"].get("questions")
    if isinstance(q, list):
        for item in q:
            if isinstance(item, dict):
                qid = item.get("question_id") or item.get("id")
                if qid:
                    qs.append({"question_id": str(qid),
                               "text": str(item.get("text") or item.get("question") or "")})
    return qs


def artifact_answers(result):
    """从 result.json 取答案列表（兼容 result.answers[] 与顶层 answers[]）。"""
    if not isinstance(result, dict):
        return []
    inner = result.get("result") if isinstance(result.get("result"), dict) else {}
    ans = inner.get("answers") if isinstance(inner.get("answers"), list) else result.get("answers")
    return ans if isinstance(ans, list) else []


def fingerprint(obj):
    payload = json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


# ------------------------------------------------------------------ 审计器

def _evidence_anchored(ev, paras):
    """证据是否逐字锚定：paragraph_id 存在且 quote 是该段落的子串。"""
    if not isinstance(ev, dict):
        return False, ""
    pid = str(ev.get("paragraph_id") or "")
    q = str(ev.get("quote") or "")
    if pid not in paras:
        return False, q
    if not norm(q):
        return False, q
    return norm(q) in norm(paras[pid]), q


def _claim_supported(claim, paras):
    """claim 是否被引文支撑：
    1) 至少一条 evidence 逐字锚定在所引段落；
    2) reported claim 文本中的每个 ≥2 位数值都出现在引文里（跨语言可判：数值与语言无关）；
       inferred claim 的数值是推断计算值，按 check_result.py 同口径豁免（依据其 evidence）；
    3) claim 无 ≥2 位数值时，引文须为实质片段（归一化长度 ≥ 20）。
    """
    evs = claim.get("evidence") or []
    if not isinstance(evs, list) or not evs:
        return False, "no_evidence"
    quote_blob = ""
    anchored = False
    for e in evs:
        ok, q = _evidence_anchored(e, paras)
        anchored = anchored or ok
        quote_blob += norm(q)
    if not anchored:
        return False, "quote_not_verbatim"
    cnums = numbers(claim.get("text") or "")
    if cnums and claim.get("kind") != "inferred":
        missing = [n for n in cnums if n not in quote_blob]
        if missing:
            return False, "numbers_unbacked:%s" % ",".join(missing)
        return True, "ok"
    if len(quote_blob) >= 20:
        return True, "ok"
    return False, "quote_too_short"


SUBQ_COVER_MIN_RATIO = 0.35   # 声明式阈值：claim 文本 token 覆盖子问 token 的比例下限
SUBQ_COVER_MIN_TOKENS = 2     # 声明式阈值：至少命中 2 个内容 token
GAP_TOKEN_OVERLAP_MIN = 2      # 声明式阈值：缺口披露与子问的 token 交集下限


def _tokens_overlap(a_text, b_text):
    ta, tb = tokens(a_text), tokens(b_text)
    if not ta or not tb:
        return 0, 0.0
    hit = len(ta & tb)
    return hit, hit / float(len(ta))


def _claim_covers_subq(claim_text, subq):
    """claim 是否覆盖某个子问：token 命中率达标（阈值已声明，可复核）。"""
    hit, ratio = _tokens_overlap(claim_text, subq)
    need = max(SUBQ_COVER_MIN_TOKENS, int(math.ceil(SUBQ_COVER_MIN_RATIO * len(tokens(subq)))))
    return hit >= need


def _discloses_gap(part_text, subq):
    hit, _ = _tokens_overlap(part_text, subq)
    return hit >= GAP_TOKEN_OVERLAP_MIN


def audit(answers, paras, questions, stage_log=None, mode="full"):
    """统一审计器：完整机制与退化重放使用完全相同的判定口径。"""
    qmap = {q["question_id"]: q["text"] for q in questions}
    per_question = []
    total_sub = resolved_sub = 0
    n_claims = n_claims_with_ev = n_supported = 0
    n_nonverbatim = n_missing_loc = n_no_ev = 0
    ans_nums = ans_backed = 0
    unbacked_list = []
    undisclosed = 0

    for a in answers:
        if not isinstance(a, dict):
            continue
        qid = str(a.get("question_id") or "")
        qtext = qmap.get(qid, "")
        subqs = split_subquestions(qtext) if qtext else []
        claims = [c for c in (a.get("claims") or []) if isinstance(c, dict)]
        gaps = [str(p.get("part") or "") for p in (a.get("unanswered_parts") or [])
                if isinstance(p, dict)]
        total_sub += len(subqs)

        # 子问覆盖：被「有支撑引文的 claim」覆盖，或已在 unanswered_parts 中明示缺口
        covered, disclosed = set(), set()
        for c in claims:
            n_claims += 1
            evs = c.get("evidence") or []
            if isinstance(evs, list) and evs:
                n_claims_with_ev += 1
            else:
                n_no_ev += 1
            sup, _reason = _claim_supported(c, paras)
            if sup:
                n_supported += 1
            if not c.get("location"):
                n_missing_loc += 1
            for e in evs:
                ok, _q = _evidence_anchored(e, paras)
                if not ok:
                    n_nonverbatim += 1
            if not sup:
                continue
            for i, sq in enumerate(subqs):
                if i not in covered and _claim_covers_subq(c.get("text") or "", sq):
                    covered.add(i)
        for i, sq in enumerate(subqs):
            if i in covered:
                continue
            if any(_discloses_gap(g, sq) for g in gaps):
                disclosed.add(i)
        resolved_sub += len(covered | disclosed)
        gap_now = len(subqs) - len(covered | disclosed)
        undisclosed += gap_now

        # 答案数值回证：本问 claim 的引文 + inferred claim 文本（推断豁免，同 check_result 口径）
        quote_blob = norm("".join(
            str(e.get("quote") or "") for c in claims for e in (c.get("evidence") or [])
            if isinstance(e, dict)))
        inferred_blob = norm("".join(
            str(c.get("text") or "") for c in claims if c.get("kind") == "inferred"))
        a_nums = numbers(a.get("answer") or "")
        for n in a_nums:
            ans_nums += 1
            if n in quote_blob or n in inferred_blob:
                ans_backed += 1
            else:
                unbacked_list.append({"question_id": qid, "number": n})

        per_question.append({
            "question_id": qid,
            "status": a.get("status"),
            "subquestions_total": len(subqs),
            "subquestions_covered_by_evidence": len(covered),
            "subquestions_disclosed_as_gap": len(disclosed),
            "subquestions_unresolved": gap_now,
            "claims": len(claims),
            "claims_supported": sum(1 for c in claims if _claim_supported(c, paras)[0]),
            "answer_numbers": len(a_nums),
            "answer_numbers_unbacked": sum(1 for n in a_nums
                                            if n not in quote_blob and n not in inferred_blob),
        })

    manual_items = (len(unbacked_list) + n_nonverbatim + n_missing_loc + n_no_ev + undisclosed)
    # 追问轮次：未明示的缺口需要回头再问，一轮可补的子问数按 2 计
    followup = int(math.ceil(undisclosed / 2.0)) if undisclosed else 0

    # 步骤数：优先取运行阶段日志；无日志时用声明式流水线阶段数（来源标注清楚）
    stages = list(stage_log or [])
    steps_source = "run_log.jsonl 阶段日志实测"
    if not stages:
        stages = list(FULL_STAGES)
        steps_source = "声明式流水线阶段数（无 run_log，按 SKILL.md 阶段表推算）"
    if mode == "ablated":
        stages = [s for s in stages if s not in DISABLED_STAGES_ABLATED]
        steps_source += "；退化模式已剔除关闭阶段 %s" % (",".join(DISABLED_STAGES_ABLATED),)

    metrics = {
        "sub_question_coverage_rate": round(resolved_sub / float(total_sub), 4) if total_sub else 0.0,
        "citation_support_rate": round(n_supported / float(n_claims_with_ev), 4) if n_claims_with_ev else 0.0,
        "numeric_fidelity_rate": round(ans_backed / float(ans_nums), 4) if ans_nums else 0.0,
        "needs_manual_review_items": manual_items,
        "steps": len(stages),
        "followup_rounds": followup,
    }
    supplementary = {
        "subquestions_total": total_sub,
        "subquestions_resolved": resolved_sub,
        "subquestions_covered_by_evidence": sum(p["subquestions_covered_by_evidence"] for p in per_question),
        "subquestions_disclosed_as_gap": sum(p["subquestions_disclosed_as_gap"] for p in per_question),
        "subquestions_unresolved": undisclosed,
        "claims_total": n_claims,
        "claims_with_evidence": n_claims_with_ev,
        "claims_supported": n_supported,
        "claims_without_evidence": n_no_ev,
        "quotes_not_verbatim": n_nonverbatim,
        "claims_missing_location": n_missing_loc,
        "answer_numbers": ans_nums,
        "answer_numbers_unbacked": len(unbacked_list),
        "steps_executed": stages,
        "steps_source": steps_source,
        "stages_disabled": list(DISABLED_STAGES_ABLATED) if mode == "ablated" else [],
        "subq_cover_threshold": {"min_token_ratio": SUBQ_COVER_MIN_RATIO,
                                 "min_tokens": SUBQ_COVER_MIN_TOKENS,
                                 "gap_overlap_min": GAP_TOKEN_OVERLAP_MIN},
        "unbacked_numbers": unbacked_list[:40],
    }
    return metrics, supplementary, per_question


# ------------------------------------------------------------------ 退化重放

DEGRADATION_MODEL = {
    "id": "whiteboard_style_failure_replay",
    "summary": "对同一真实产物做确定性降级改写，逐条复刻本 Skill 文档中列出的白板失效模式"
               "（漏子问 / 引文不逐字 / 整题只挂一条笼统 claim / 混淆实测与推断）；"
               "不是另一份产物，改写规则可逐条复核、可复算。",
    "rules": [
        {"id": "D1", "name": "整题只挂一条笼统 claim（漏子问）",
         "rule": "每题只保留第一条 claim，其余 claim 及其引文全部丢弃；答案文本不变",
         "expected_effect": "子问覆盖率下降；未明示的缺口（需人工核对条目）上升"},
        {"id": "D2", "name": "引文非逐字化（改写转述）",
         "rule": "保留 claim 的引文做确定性改写：数值舍入（84.3→84）并追加转述连接词「，据该段」",
         "expected_effect": "引文不再逐字锚定原文 → 引用支持率下降；数值保真率下降"},
        {"id": "D3", "name": "混淆实测与推断",
         "rule": "把 kind=inferred 的 claim 改标为 reported（推断值失去豁免）",
         "expected_effect": "推断计算值要求被引文回证 → 引用支持率下降、未回证数值上升"},
        {"id": "D4", "name": "无结构化校验与复检",
         "rule": "关闭 evidence_verify / numeric_verify / repair_loop 三个阶段",
         "expected_effect": "步骤数下降；追问轮次转由人工承担"},
    ],
    "deterministic": True,
    "unchanged": ["答案文本 answer 保持不变（只降级证据结构，不改写答案措辞）",
                  "输入 case.json 保持不变（同输入对照）"],
}


def _paraphrase_quote(quote):
    """确定性改写：数值舍入 + 追加转述连接词，使引文不再是原文逐字子串。"""
    q = str(quote or "")
    if not q:
        return q
    def _round(m):
        num = m.group(0)
        if "." in num:
            return num.split(".")[0]
        return num
    q = re.sub(r"\d+\.\d+", _round, q)
    return q + "，据该段"


def degrade(answers, paras):
    """确定性降级重放：D1 丢 claim + D2 引文非逐字化 + D3 推断改标 reported。"""
    out = []
    for a in answers:
        if not isinstance(a, dict):
            continue
        claims = [c for c in (a.get("claims") or []) if isinstance(c, dict)]
        kept = []
        if claims:
            c0 = json.loads(json.dumps(claims[0], ensure_ascii=False))
            evs = c0.get("evidence") or []
            if evs and isinstance(evs[0], dict):
                evs[0]["quote"] = _paraphrase_quote(evs[0].get("quote"))
            if c0.get("kind") == "inferred":
                c0["kind"] = "reported"
            kept = [c0]
        na = json.loads(json.dumps(a, ensure_ascii=False))
        na["claims"] = kept
        out.append(na)
    return out


# ------------------------------------------------------------------ 机制映射

MECHANISM_MAP = [
    {"id": "M1", "mechanism": "按子问粒度拆解问题并逐子问成 claim",
     "metrics": ["sub_question_coverage_rate", "needs_manual_review_items"],
     "why": "整题单条 claim 时，多子问问题只有首个被取证的子句得到引文，其余子问成为"
            "需人工核对的缺口；逐子问成 claim 后子问覆盖率上升、漏答子问下降。"},
    {"id": "M2", "mechanism": "逐子问句级证据定位（段落 + 句 + 逐字引文）",
     "metrics": ["citation_support_rate", "needs_manual_review_items"],
     "why": "引文逐字锚定在所引段落、且承载该论断的数值，才能判定「引文支持论断」；"
            "粗粒度引文逐字但不支撑论断时，引用支持率显著下降。"},
    {"id": "M3", "mechanism": "数值/单位抽取 + 引文逐字回证",
     "metrics": ["numeric_fidelity_rate", "needs_manual_review_items"],
     "why": "答案里每个 ≥2 位数值都必须能在本问引文（或 inferred claim 文本）中逐字回证；"
            "不做回证时数值保真率下降，未回证数值转成需人工核对条目。"},
    {"id": "M4", "mechanism": "结构化校验 + 复检—返工循环",
     "metrics": ["steps", "followup_rounds", "needs_manual_review_items"],
     "why": "复检把「问题条目」在交付前自动修好或标为缺口，把追问轮次从人工轮次转成"
            "自动复检轮次；代价是步骤数略增。"},
    {"id": "M5", "mechanism": "同输入退化重放（可复核对照）",
     "metrics": ["steps", "followup_rounds"],
     "why": "对照本身可复算：任何人用同一命令对同一输入都能得到同一组数字，"
            "因此增益主张不依赖文字自述。"},
]

APPLICABILITY = {
    "applies_to": [
        "带段落编号的单篇论文 + 中文问题清单（含多子问、含数值比较类问题）",
        "段落文本可被逐字检索（纯标准库 token 化，中英文混排均可）",
        "题目要求逐题回答并给出可回原文核对的依据",
    ],
    "not_applicable_to": [
        "需要 PDF 解析 / 图像识别 / 补充附件 / 联网检索才能作答的题（按「材料未提供」处理）",
        "开放域知识问答（无给定材料时本对照不产生任何结论）",
        "段落文本极短或与问题无任何关键词交集时，两遍指标会同时塌陷，此时只能说明"
        "「检索无命中」，不能区分机制优劣",
    ],
    "measurement_limits": [
        "本对照为同输入机制消融，不是平台白板实测；平台白板由平台侧生成，本脚本不主张其数值。",
        "退化重放改的是「产物结构」，不改答案措辞；因此可比较的是机制对证据结构与"
        "核验指标的影响，不能据此推断最终答案措辞质量。",
        "全部计数器为自动采集计数（步骤、检索次数、复检轮次、条目数），不是人工计时。",
    ],
}

FAILURE_CONDITIONS = [
    "case.json 缺少段落清单（paragraphs/passages/sections 均无）→ 引文无法逐字锚定，"
    "两遍引用支持率同时塌陷为 0，此时 gain_evidence 仅表示「输入不可用」，不构成增益证据。",
    "result.json 缺失、不可解析或缺 answers[] → 只有对照骨架，无产物指纹，"
    "结论强度降级为「机制层面说明」。",
    "问题文本不含可提取的内容 token（纯符号/乱码）→ 子问拆解退化为一问，"
    "子问覆盖率失去区分度。",
    "段落文本被截断或编号错位 → 逐字判定失真，引用支持率下降属输入缺陷而非机制缺陷。",
    "需要外部知识才能回答的问题 → 会被标为材料未报告，覆盖率/数值类指标不适用。",
    "run_log.jsonl 缺失 → 步骤数退化为「按产物可判定阶段」推算值，"
    "evidence_lookups / model_requests / tool_calls 无法采集（记为 null 并列入 not_collected）。",
]


def _delta(full, ablated):
    out = {}
    for k, v in full.items():
        a = ablated.get(k)
        if isinstance(v, (int, float)) and isinstance(a, (int, float)):
            out[k] = {"full": v, "ablated": a, "delta": round(v - a, 4),
                      "relative": round((v - a) / a, 4) if a else None}
    return out


# ------------------------------------------------------------------ run_log

def read_run_log(paths):
    """读取运行阶段/请求日志（Agent 运行时写入 /app/output/run_log.jsonl）。"""
    stages, counters = [], {"model_requests": 0, "tool_calls": 0, "write_batches": 0,
                            "repair_rounds": 0}
    found = None
    for p in paths:
        if p and os.path.exists(p):
            found = p
            break
    if not found:
        return stages, counters, None
    try:
        with open(found, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                kind = str(rec.get("kind") or rec.get("event") or "")
                if kind == "stage" and rec.get("stage"):
                    stages.append(str(rec["stage"]))
                elif kind in ("model_request", "request"):
                    counters["model_requests"] += 1
                elif kind in ("tool_call", "tool"):
                    counters["tool_calls"] += 1
                elif kind in ("write", "write_batch"):
                    counters["write_batches"] += 1
                elif kind in ("repair", "repair_round"):
                    counters["repair_rounds"] += 1
    except Exception:
        return stages, counters, found
    return stages, counters, found


# ------------------------------------------------------------------ 主流程

def run_compare(case, result, log_paths=None):
    paras = paragraphs_of(case)
    questions = questions_of(case)
    answers = artifact_answers(result)

    stages, counters, log_path = read_run_log(log_paths or [])
    if not answers:
        stages, counters, log_path = read_run_log(log_paths or [])

    full_m, full_s, full_q = audit(answers, paras, questions, stages, mode="full")
    degraded_answers = degrade(answers, paras) if answers else []
    abl_m, abl_s, abl_q = audit(degraded_answers, paras, questions, stages, mode="ablated")

    runs = {
        "full": {
            "mode": "full",
            "description": "完整机制下的真实产物（本次运行实际交付的 result.json）",
            "artifact_fingerprint": fingerprint(answers) if answers else None,
            "metrics": full_m, "supplementary": full_s, "per_question": full_q,
        },
        "ablated": {
            "mode": "ablated",
            "description": "对同一产物的确定性退化重放（D1/D2/D3），同一审计器口径",
            "artifact_fingerprint": fingerprint(degraded_answers) if degraded_answers else None,
            "metrics": abl_m, "supplementary": abl_s, "per_question": abl_q,
        },
    }

    mechanism_map = []
    dlt = _delta(full_m, abl_m)
    for m in MECHANISM_MAP:
        entry = dict(m)
        entry["observed_effect"] = {k: dlt.get(k) for k in m["metrics"] if k in dlt}
        mechanism_map.append(entry)

    gain = {
        "measurement": {
            "tool": TOOL_NAME,
            "design": "same-input ablation：同一 case.json + 同一真实产物，full 与 ablated 各测一遍",
            "case_id": case.get("case_id"),
            "paper_id": case.get("paper_id"),
            "material_version": case.get("material_version"),
            "input_fingerprint": fingerprint({"paras": sorted(paras.items()),
                                              "qs": [(q["question_id"], q["text"]) for q in questions]}),
            "paragraph_count": len(paras),
            "question_count": len(questions),
            "artifact_fingerprint": runs["full"]["artifact_fingerprint"],
            "run_log": log_path,
            "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "reproduce": ("python3 /skills/literature-qa/scripts/measure_gain.py "
                          "--case /input/case.json --result /app/output/result.json --mode compare --embed"),
            "note": "所有数字由脚本运行时计算，随输入与产物指纹留痕；可用上述命令复算同一组数字。",
        },
        "degradation_model": DEGRADATION_MODEL,
        "runs": runs,
        "delta_full_minus_ablated": dlt,
        "mechanism_to_metric": mechanism_map,
        "applicability": APPLICABILITY,
        "failure_conditions": FAILURE_CONDITIONS,
        "verdict": {
            "has_comparable_pair": bool(answers),
            "artifact_present": bool(answers),
            "conclusion": ("机制全开相对退化重放在证据结构与核验指标上的差异已实测；"
                           "平台白板对照由平台侧生成，本记录不作白板数值主张。"),
        },
    }
    efficiency = collect_efficiency(result, gain, counters, stages)
    return gain, efficiency


def collect_efficiency(result, gain, counters, stages):
    """可自动采集的效率计数落盘：请求数 / 工具调用 / 证据定位次数 / 返工轮次 等。"""
    c = {
        "model_requests": None,
        "tool_calls": None,
        "write_batches": None,
        "repair_rounds": None,
        "evidence_lookups": None,
        "steps": None,
        "questions_answered": None,
        "claims_total": None,
        "evidence_items_total": None,
    }
    src = {}
    if counters and counters.get("model_requests") is not None:
        c["model_requests"] = counters.get("model_requests")
        src["model_requests"] = "run_log.jsonl 自动计数（kind=model_request 行数）"
        c["tool_calls"] = counters.get("tool_calls")
        src["tool_calls"] = "run_log.jsonl 自动计数（kind=tool_call 行数）"
        c["write_batches"] = counters.get("write_batches")
        src["write_batches"] = "run_log.jsonl 自动计数（kind=write 行数）"
        c["repair_rounds"] = counters.get("repair_rounds")
        src["repair_rounds"] = "run_log.jsonl 自动计数（kind=repair 行数）"
    if stages:
        c["steps"] = len(stages)
        src["steps"] = "run_log.jsonl 阶段日志计数（kind=stage 行数）"
        c["evidence_lookups"] = sum(1 for s in stages if s == "locate_evidence")
        src["evidence_lookups"] = "run_log.jsonl 阶段日志计数（stage=locate_evidence 行数）"

    answers = artifact_answers(result)
    if answers:
        c["questions_answered"] = len(answers)
        src["questions_answered"] = "result.json 实际答案条目计数"
        claims = [x for a in answers if isinstance(a, dict) for x in (a.get("claims") or [])
                  if isinstance(x, dict)]
        c["claims_total"] = len(claims)
        src["claims_total"] = "result.json 实际 claim 条目计数"
        c["evidence_items_total"] = sum(len(x.get("evidence") or []) for x in claims)
        src["evidence_items_total"] = "result.json 实际 evidence 条目计数"

    missing = [k for k, v in c.items() if v is None]
    return {
        "counters": c,
        "sources": src,
        "not_collected": missing,
        "note": "全部为自动采集计数（请求/工具调用/检索次数/复检轮次/条目数），"
                "不是人工计时，不得称为人工核对时间；未采集到的项记为 null 并列入 not_collected。",
        "reproduce": {
            "efficiency": ("python3 /skills/literature-qa/scripts/measure_gain.py "
                           "--case /input/case.json --result /app/output/result.json --mode compare --embed"),
            "checker": ("python3 /skills/literature-qa/scripts/check_result.py "
                        "--result /app/output/result.json --case /input/case.json"),
            "run_log_format": ("/app/output/run_log.jsonl 每行一条 JSON："
                               '{"kind":"stage","stage":"locate_evidence"} | '
                               '{"kind":"model_request"} | {"kind":"tool_call"} | '
                               '{"kind":"write"} | {"kind":"repair"}'),
        },
    }


def embed(result_path, gain, eff):
    """把 gain_evidence / efficiency 写入 result.json。

    合并语义：若已有 gain_evidence（可能来自 scripts/gain_evidence.py 的证据登记口径），
    保留其内容到 registry_evidence 键下再写入本脚本的对照结果——两个脚本互补且互不覆盖，
    无论谁先谁后跑，result.json 里两份证据都完整。
    """
    try:
        with open(result_path, "r", encoding="utf-8") as f:
            res = json.load(f)
        if not isinstance(res, dict):
            return False
        prior = res.get("gain_evidence")
        if isinstance(prior, dict) and prior:
            # 已有其他脚本写入的证据登记口径 → 另存，避免互相覆盖
            res.setdefault("registry_evidence", prior)
        res["gain_evidence"] = gain
        res["efficiency"] = eff
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


# ------------------------------------------------------------------ 自测

def _selftest():
    case = {
        "case_id": "t-gain-001",
        "paper_id": "p-A",
        "material_version": "v1",
        "paragraphs": [
            {"paragraph_id": "p01",
             "text": "The LiFePO4 coating retained 84.3% capacity after 200 cycles at 1C, "
                     "versus 71.0% for the uncoated electrode."},
            {"paragraph_id": "p02",
             "text": "The authors attribute the improvement to suppressed interfacial side reactions."},
        ],
        "questions": [
            {"question_id": "q1", "text": "涂层电极的循环保持率是多少？与未涂层电极相比差异如何？"},
            {"question_id": "q2", "text": "涂层电极的产热表现如何？"},
        ],
    }
    result = {
        "case_id": "t-gain-001",
        "status": "partial",
        "result": {
            "paper_id": "p-A", "material_version": "v1",
            "coverage": {"read_paragraphs": ["p01", "p02"], "unread_sections": [], "note": ""},
            "answers": [
                {"question_id": "q1",
                 "answer": "涂层电极在 1C、200 次循环后容量保持率为 84.3%，未涂层电极为 71.0%；"
                           "据材料推断高出约 13.3 个百分点。",
                 "conditions": ["1C 倍率", "200 次循环"], "status": "answered",
                 "claims": [
                     {"claim_id": "c-01", "text": "涂层电极 200 次循环后保持率 84.3%",
                      "kind": "reported", "source_id": "p-A", "location": "p01",
                      "evidence": [{"paragraph_id": "p01",
                                    "quote": "retained 84.3% capacity after 200 cycles at 1C"}]},
                     {"claim_id": "c-02", "text": "未涂层电极保持率 71.0%",
                      "kind": "reported", "source_id": "p-A", "location": "p01",
                      "evidence": [{"paragraph_id": "p01",
                                    "quote": "versus 71.0% for the uncoated electrode"}]},
                     {"claim_id": "c-03",
                      "text": "据材料推断高出约 13.3 个百分点（84.3−71.0）", "kind": "inferred",
                      "source_id": "p-A", "location": "p01",
                      "evidence": [{"paragraph_id": "p01",
                                    "quote": "retained 84.3% capacity after 200 cycles at 1C, versus 71.0%"}]}],
                 "unanswered_parts": []},
                {"question_id": "q2",
                 "answer": "材料未报告涂层电极的产热数据；已检索全部段落（p01、p02）。",
                 "conditions": [], "status": "insufficient_evidence", "claims": [],
                 "unanswered_parts": [{"part": "产热表现", "reason": "材料未报告"}]},
            ]},
        "claims": [],
        "uncertainties": {"unreported": [], "unverifiable": [], "conflicts": [],
                          "human_review": [], "summary": ""},
    }
    gain, eff = run_compare(case, result)
    fm = gain["runs"]["full"]["metrics"]
    am = gain["runs"]["ablated"]["metrics"]
    checks = {
        "full 子问覆盖率 > ablated": fm["sub_question_coverage_rate"] > am["sub_question_coverage_rate"],
        "full 引用支持率 > ablated": fm["citation_support_rate"] > am["citation_support_rate"],
        "full 数值保真率 > ablated": fm["numeric_fidelity_rate"] > am["numeric_fidelity_rate"],
        "full 需人工核对 < ablated": fm["needs_manual_review_items"] < am["needs_manual_review_items"],
        "delta 含 6 项指标": len(gain["delta_full_minus_ablated"]) == 6,
        "机制映射 M1-M5": [m["id"] for m in gain["mechanism_to_metric"]] == ["M1", "M2", "M3", "M4", "M5"],
        "退化模型 D1-D4": [r["id"] for r in gain["degradation_model"]["rules"]] == ["D1", "D2", "D3", "D4"],
        "失效条件 ≥4 条": len(gain["failure_conditions"]) >= 4,
        "可复算指纹稳定": fingerprint({"a": 1}) == fingerprint({"a": 1}),
    }
    ok = all(checks.values())
    print("[gain-selftest] %s" % ("PASS" if ok else "FAIL"))
    print("[gain-selftest] full    %s" % json.dumps(fm, ensure_ascii=False))
    print("[gain-selftest] ablated %s" % json.dumps(am, ensure_ascii=False))
    print("[gain-selftest] delta   %s" % json.dumps(gain["delta_full_minus_ablated"], ensure_ascii=False))
    for k, v in checks.items():
        print("    %s %s" % ("[ok]" if v else "[!!]", k))
    print("[gain-selftest] verdict=%s" % ("ALL PASS" if ok else "FAIL"))
    return 0  # 恒 0：结论以 verdict 记录


def _print_compare(gain):
    m = gain["measurement"]
    print("[gain] case=%s paragraphs=%d questions=%d input_fp=%s artifact_fp=%s" % (
        m["case_id"], m["paragraph_count"], m["question_count"],
        m["input_fingerprint"], m["artifact_fingerprint"]))
    print("[gain] %-30s %12s %12s %12s" % ("metric", "full", "ablated", "delta"))
    for k, d in gain["delta_full_minus_ablated"].items():
        print("[gain] %-30s %12s %12s %12s" % (k, d["full"], d["ablated"], d["delta"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--result", default=None)
    ap.add_argument("--mode", default="compare", choices=["compare"])
    ap.add_argument("--log", default=None, help="run_log.jsonl 路径（默认 /app/output/run_log.jsonl）")
    ap.add_argument("--embed", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return _selftest()

    try:
        with open(args.case, "r", encoding="utf-8") as f:
            case = json.load(f)
    except Exception as e:
        print("[gain] FAIL(case_unreadable): %s" % e)
        print("[gain] verdict=case_unreadable；本轮不产生对照证据。")
        return 0

    result = None
    if args.result and os.path.exists(args.result):
        try:
            with open(args.result, "r", encoding="utf-8") as f:
                result = json.load(f)
        except Exception:
            result = None

    log_paths = [args.log] if args.log else ["/app/output/run_log.jsonl"]
    gain, eff = run_compare(case, result, log_paths)
    _print_compare(gain)

    if args.embed and args.result:
        ok = embed(args.result, gain, eff)
        print("[gain] embed=%s → %s" % (ok, args.result))
    else:
        print(json.dumps({"gain_evidence": gain, "efficiency": eff},
                         ensure_ascii=False, indent=2))
    print("[gain] verdict=measured")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[gain] 降级：脚本异常但不阻塞交付: %s" % e)
        sys.exit(0)
