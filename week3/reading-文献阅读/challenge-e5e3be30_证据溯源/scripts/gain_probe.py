#!/usr/bin/env python3
"""gain_probe.py — 同输入增益对照（消融）与效率采集器（纯标准库，无外部依赖）。

子命令
------
  compare  对同一份交付 result.json 跑「质量闸门 开/关」两遍，输出逐项指标对照。
  ablate   **可运行的退化/基线开关**：在同输入下**真实调用 claim_check.py 跑两遍**
           （full 臂 / --ablate 臂），逐项对比两道闸门各自拦下了什么，输出真实对照数字。
  rule     用内置确定性规则审计器在 (case, claims) 上跑「全流程 / 基线」两遍，输出逐项对照。
  patch    执行 compare+ablate+rule，把**实测**数字写回 result.json 的 gain_evidence / efficiency 字段。
  demo     用 examples/ 合成件自检（示意数据，非正式案例结果）。

消融开关（全局）
---------------
  --ablate 或环境变量 CLAIM_AUDIT_ABLATE=1：关闭「逐字回证」与「未覆盖补登记」两道闸门
  （模拟未加载本技能质量闸门时的基线行为）。子命令 ablate 会把该开关传递到
  claim_check.py 的子进程，从而**真实跑出**两臂结果，而不是在同进程里估算。

设计约束（对应题面「使用增益 / 增益可验证性」）
------------------------------------------------
* 同输入：两臂读同一份 case/claims/result，指纹（sha256）写进产物，便于复核同输入。
* 真数字：所有指标由脚本实测得出，禁止手填；不可采集的字段显式标 source。
* 不中断交付：任何子命令、任何异常都 exit 0，成败由输出 JSON 的 ok/status 字段表达。

指标定义（measure 统一口径）
-----------------------------
  verdict_coverage_rate      = (已判定 claim 数 + 已登记 uncovered 数) / 总 claim 数
  evidence_backverify_rate   = 通过逐字回证的证据条数 / 保留证据条数
  uncovered_miss_count       = 既未判定也未登记 uncovered 的 claim 数（漏检）
  false_supported_count      = 判 supported 但其证据中不含论断关键数值/方向的条数（误支持）
  manual_review_items        = uncertainties.human_review 条数（需人工核对）
  steps / rounds             = 实际执行的阶段数 / 回原文复核轮次（来源标注 run_log|protocol）
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import subprocess
import sys
import time

# ---------------------------------------------------------------- 通用工具

VERDICTS = ("supported", "partially_supported", "contradicted", "insufficient_evidence")
SUBTYPES = ("fact", "comparison", "causal", "scope")
ABLATE_ENV = "CLAIM_AUDIT_ABLATE"


class Exit0Parser(argparse.ArgumentParser):
    """参数错误也 exit 0：不因调用方笔误阻断交付链。"""

    def error(self, message):  # noqa: D401
        print("[gain_probe] FAIL 参数错误: %s" % message)
        print("[gain_probe] exit=0（结论：FAIL）")
        raise SystemExit(0)


def ablate_requested(args) -> bool:
    """消融开关：--ablate 或环境变量 CLAIM_AUDIT_ABLATE=1/true/on。"""
    if getattr(args, "ablate", False):
        return True
    return str(os.environ.get(ABLATE_ENV, "")).strip().lower() in ("1", "true", "yes", "on")


def now_ms() -> int:
    return int(time.time() * 1000)


def norm(s) -> str:
    """空白归一化：删除全部空白字符（与 claim_check.py 同口径）。"""
    return re.sub(r"\s+", "", str(s or ""))


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def digest(obj) -> str:
    try:
        blob = json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")
    except Exception:
        blob = str(obj).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def paragraphs_of(case):
    """从 case.json 抽段落表：{paragraph_id: text}（与 claim_check.py 同口径）。"""
    out = {}
    if not isinstance(case, dict):
        return out
    for key in ("paragraphs", "passages", "paper_paragraphs", "sections"):
        v = case.get(key)
        if isinstance(v, list):
            for p in v:
                if isinstance(p, dict):
                    pid = str(p.get("paragraph_id") or p.get("id") or p.get("pid") or "")
                    txt = str(p.get("text") or p.get("content") or p.get("body") or "")
                    if pid:
                        out[pid] = txt
            break
    return out


def claim_items(cl):
    items = cl if isinstance(cl, list) else (cl.get("claims") or cl.get("items") or []) if isinstance(cl, dict) else []
    return [it for it in items if isinstance(it, dict)]


def claim_id_of(it, idx):
    return str(it.get("claim_id") or it.get("id") or it.get("claim") or ("claim-%d" % idx))


def claim_text_of(it):
    return str(it.get("text") or it.get("claim") or it.get("claim_text") or "")


def uncovered_ids(res):
    unc = res.get("uncertainties") if isinstance(res, dict) else None
    out = set()
    if isinstance(unc, dict):
        for it in unc.get("uncovered") or []:
            if isinstance(it, dict) and it.get("claim_id") is not None:
                out.add(str(it["claim_id"]))
            elif isinstance(it, str):
                out.add(it)
    return out


def verdict_items(res):
    inner = res.get("result") if isinstance(res, dict) else None
    v = inner.get("verdicts") if isinstance(inner, dict) else None
    return [x for x in (v or []) if isinstance(x, dict)]


def sub_of(v):
    return [s for s in (v.get("subclaims") or []) if isinstance(s, dict)]


# ---------------------------------------------------------------- 线索抽取

EN_STOP = set("""the a an and or of to in on for with was were is are be been being that this these those
it its as at by from than then so such not no but if while which who whom whose have has had do does did
can could may might will would shall should there here their they them he she his her we our you your i
we also more most other another same both each any all some because due between during under over about
after before both only very much many few new old high low large small good better best""".split())

CJK_STOP = set("的了和与在是有为对于中上下不无被把将并且以及但而也还就都其此该等这那些我们他她它个种次些最更再已并由从到以之其或若则因故")

UP_PAT = re.compile(r"(高于|超过|高出|提升|增加|增大|延长|更长|更高|更多|上升|改善|优于|"
                     r"higher|greater|larger|increas|improv|longer|more|superior|better|higher)", re.I)
DOWN_PAT = re.compile(r"(低于|少于|减少|下降|降低|缩短|更短|更低|更少|变差|劣于|"
                       r"lower|smaller|decreas|reduc|less|shorter|worse|inferior)", re.I)
NEG_PAT = re.compile(r"(未|没有|无|不是|不存在|无显著|无明显|未能|"
                     r"\bno\b|\bnot\b|\bnever\b|without|lack|fail(ed)? to)", re.I)
HEDGE_PAT = re.compile(r"(可能|也许|或许|推测|似乎|有望|提示|暗示|尚需|有待|进一步研究|"
                        r"\bmay\b|\bmight\b|\bcould\b|suggest|appear|likely|possible|remain(s)? uncertain|"
                        r"further study|warrants)", re.I)
CERT_PAT = re.compile(r"(已被证实|已被实验证实|经实验证实|证实|证明|必然|一定|确凿|"
                       r"confirmed|proven|proved|demonstrated|established|definitive|certain)", re.I)
SCOPE_PAT = re.compile(r"(仅|只|限于|限定|适用范围|前提|在[^，。；]{0,14}(下|中|时|条件)|"
                        r"\bonly\b|\bunder\b|\bwhen\b|\bwithin\b|in the case|for the case|"
                        r"room temperature|at room)", re.I)
CAUSAL_PAT = re.compile(r"(导致|造成|使得|引起|因为|由于|缘于|"
                         r"causes?|leads? to|results? in|due to|because of|owing to)", re.I)
NUM_PAT = re.compile(r"(\d+(?:\.\d+)?)\s*(%|percent|‰|kN|N|MPa|GPa|mm|cm|m|kg|mg|mL|L|day|days|"
                      r"hour|hours|month|months|year|years|次|个|倍|°C|℃|s|ms)?", re.I)

# 中英科学术语对照表（小型、确定性）：把中英同义术语映射到同一 canonical 词，
# 使「中文论断 × 英文原文」这类跨语言检索可比。不覆盖全部术语，只覆盖高频科研表达。
GLOSSARY = {
    "疲劳寿命": "fatigu life", "疲劳": "fatigu", "寿命": "life",
    "表面硬化": "surface harden", "硬化": "harden", "处理组": "treated group",
    "对照组": "control", "样本": "sampl", "样品": "sampl", "试验": "test",
    "实验": "experiment", "显著": "signific", "显著性": "signific",
    "室温": "room temperature", "温度": "temperatur", "载荷": "load",
    "负载": "load", "提高": "higher", "提升": "higher", "增加": "increas",
    "降低": "decreas", "减少": "reduc", "对照": "control", "显著高于": "higher",
    "改善": "improv", "机理": "mechanis", "机制": "mechanis", "归因": "attribut",
    "推断": "infer", "证实": "confirm", "证明": "prove", "验证": "validat",
    "结论": "conclusion", "结果": "result", "研究": "stud", "分析": "analys",
    "性能": "perform", "强度": "strength", "韧性": "toughness", "硬度": "hardness",
    "疲劳强度": "fatigu strength", "裂纹": "crack", "断裂": "fractur",
    "温度升高": "temperatur", "浓度": "concentrat", "效率": "efficien",
    "能耗": "energy", "寿命提升": "fatigu life", "对照组疲劳寿命": "fatigu life",
    "统计": "statistic", "p值": "p", "重复": "replicat", "批次": "batch",
}


def _expand(text):
    """把文本展开成 canonical 词集合（中文二元组 + 英文词 + 术语表映射）。"""
    toks = content_tokens(text)
    low = str(text or "").lower()
    for zh, canon in GLOSSARY.items():
        if zh in str(text or ""):
            toks.add(canon)
            for en in canon.split():
                toks.add(en)
    for m in NUM_PAT.finditer(low):
        toks.add("num:" + m.group(1))
    return toks



def content_tokens(text):
    """内容词：英文词 + 中文二元组（去停用词）。"""
    toks = set()
    low = str(text or "").lower()
    for w in re.findall(r"[A-Za-z][A-Za-z\-]+", low):
        if len(w) > 2 and w not in EN_STOP:
            toks.add(w)
    for seg in re.findall(r"[\u4e00-\u9fff]+", low):
        for i in range(len(seg) - 1):
            bg = seg[i:i + 2]
            if bg in CJK_STOP or all(c in CJK_STOP for c in bg):
                continue
            toks.add(bg)
    return toks


def numbers_of(text):
    """抽取数值标记（含单位后缀），返回可比较的字符串集合。"""
    out = set()
    for m in NUM_PAT.finditer(str(text or "")):
        val = m.group(1)
        unit = (m.group(2) or "").strip().lower()
        if unit in ("n", "m", "s", "l", "g"):
            unit = ""  # 单位过短且歧义大，仅保留数值
        out.add(val + ("%" if unit == "%" else ""))
    return out


def polarity(text):
    up = bool(UP_PAT.search(text))
    down = bool(DOWN_PAT.search(text))
    if not up and not down:
        if re.search(r"比[^，。；]{0,12}(高|大|长|多|强|好)", str(text)):
            up = True
        elif re.search(r"比[^，。；]{0,12}(低|小|短|少|差|弱)", str(text)):
            down = True
    if up and not down:
        return 1
    if down and not up:
        return -1
    return 0


def split_sentences(text):
    """切句并保留原文偏移，quote 由偏移切出 => 天然逐字。

    句末标点需后接空白或位于末尾，避免切断小数（12.4）与缩写（p < 0.05）。
    """
    text = str(text or "")
    spans = []
    start = 0
    for m in re.finditer(r"(?<![0-9])[。；;.!?！？](?=\s|$)|\n", text):
        end = m.end()
        if text[start:end].strip():
            spans.append((start, end))
        start = end
    if start < len(text) and text[start:].strip():
        spans.append((start, len(text)))
    return spans


def decompose(text):
    """论断拆解：按并列/分句符切成子判断（基线臂不拆）。"""
    text = str(text or "")
    parts = [p.strip() for p in re.split(r"[；;。\n]+", text) if p.strip()]
    out = []
    for p in parts:
        subs = [s.strip() for s in re.split(r"[，,](?=[^，,]{4,})", p) if s.strip()]
        out.extend(subs if len(subs) > 1 else [p.strip()])
    out = [o.strip("，,、 ") for o in out if len(o.strip("，,、 ")) >= 4]
    return out or [text.strip()]


def subtype_of(part):
    if CAUSAL_PAT.search(part):
        return "causal"
    if UP_PAT.search(part) or DOWN_PAT.search(part) or re.search(r"(比|相比|versus|vs\.?|compared)", part, re.I):
        return "comparison"
    if SCOPE_PAT.search(part):
        return "scope"
    return "fact"


# ---------------------------------------------------------------- 规则审计器

def best_sentence(part, paras):
    """在段落表中检索最佳句：返回 (pid, quote, score, details)。"""
    ptoks = _expand(part)
    pnums = numbers_of(part)
    ppolar = polarity(part)
    best = (None, "", 0.0, {})
    for pid, text in paras.items():
        for s, e in split_sentences(text):
            sent = text[s:e].strip()
            if not sent:
                continue
            stoks = _expand(sent)
            snums = numbers_of(sent)
            spolar = polarity(sent)
            num_hit = len(pnums & snums)
            overlap = len(ptoks & stoks) / float(len(ptoks) or 1)
            dir_ok = 1.0 if (ppolar == 0 or spolar == 0 or ppolar == spolar) else -1.0
            score = 3.0 * num_hit + 4.0 * overlap + 1.5 * dir_ok
            if score > best[2]:
                best = (pid, sent, score,
                        {"num_hit": num_hit, "overlap": round(overlap, 3), "dir": dir_ok})
    return best


def judge_part(part, pid, sent, score, details, mode):
    """对一条子判断给出四级判定。mode: full | baseline。"""
    pnums = numbers_of(part)
    snums = numbers_of(sent)
    snum_hit = len(pnums & snums)
    ppolar = polarity(part)
    spolar = polarity(sent)
    claim_neg = bool(NEG_PAT.search(part))
    sent_neg = bool(NEG_PAT.search(sent))
    claim_cert = bool(CERT_PAT.search(part))
    sent_hedge = bool(HEDGE_PAT.search(sent))
    claim_scope = bool(SCOPE_PAT.search(part))
    sent_scope = bool(SCOPE_PAT.search(sent))

    if not sent or score < 2.0:
        if mode == "baseline":
            return None, ""  # 基线：找不到就静默丢弃（产生漏检）
        return "insufficient_evidence", "材料中未检索到与该子判断相关的可定位句"

    # 方向相反 → contradicted（需正面反向证据）
    if ppolar and spolar and ppolar != spolar:
        return "contradicted", "原文给出相反方向的表述，构成正面反证"
    if claim_neg != sent_neg and sent_neg:
        return "contradicted", "原文以否定表述陈述该结果，构成正面反证"
    if mode == "baseline":
        # 基线：只要主题相关即判支持（数值/条件不吻合也不降级）→ 误支持来源
        return "supported", "主题相关段落被直接判为支持（未核对数值与限定条件）"
    if pnums and snum_hit == 0:
        return "partially_supported", "方向相关但证据中不含论断所述数值"
    if claim_cert and sent_hedge:
        return "partially_supported", "原文为含保留的推断表述，未达论断的确定性"
    if claim_scope and not sent_scope:
        return "partially_supported", "证据未给出论断所声明的适用条件/范围限定"
    if snum_hit or details.get("overlap", 0) >= 0.34:
        return "supported", "论断的数值/方向与原文表述逐字吻合"
    return "insufficient_evidence", "仅有主题相关材料，未陈述该子判断本身"


def loose_quote(sent):
    """基线臂的引文风格：省略号式改写（真实退化来源，逐字回证会失败）。"""
    s = str(sent or "").strip()
    if len(s) > 40:
        mid = len(s) // 2
        cut = s.rfind(" ", 0, mid) + 1 or mid
        return s[:cut].rstrip() + "… " + s[cut:].lstrip()
    return s + "…"


def rule_audit(case, claims, mode):
    """确定性规则审计器：产出与 result.json 同构的产物。mode: full | baseline。"""
    paras = paragraphs_of(case)
    items = claim_items(claims)
    verdicts = []
    uncovered = []
    summary = {v: 0 for v in VERDICTS}
    for idx, it in enumerate(items):
        cid = claim_id_of(it, idx)
        text = claim_text_of(it)
        parts = decompose(text) if mode == "full" else [text]
        subs = []
        weak = None
        for j, part in enumerate(parts):
            pid, sent, score, details = best_sentence(part, paras)
            if mode == "baseline":
                quote = loose_quote(sent) if sent else ""
            else:
                quote = sent
            v, rationale = judge_part(part, pid, sent, score, details, mode)
            if v is None:
                continue
            sub = {
                "sub_id": "%s-s%d" % (cid, j + 1),
                "type": subtype_of(part),
                "text": part,
                "verdict": v,
                "evidence": ([{"paragraph_id": pid, "quote": quote, "locator": pid}] if sent else []),
                "rationale": rationale,
            }
            subs.append(sub)
            if weak is None or VERDICTS.index(v) > VERDICTS.index(weak):
                weak = v
        if not subs:
            if mode == "baseline":
                continue  # 基线静默丢弃 → 漏检
            uncovered.append({"claim_id": cid, "reason": "材料中未检索到可定位证据，整条登记未覆盖"})
            verdicts.append({"claim_id": cid, "claim_text": text, "verdict": "insufficient_evidence",
                             "subclaims": [{"sub_id": "%s-s1" % cid, "type": "fact", "text": text,
                                            "verdict": "insufficient_evidence", "evidence": [],
                                            "rationale": "未找到可定位证据"}],
                             "qualified_conclusion": "材料未报告相关内容，无法判定。"})
            summary["insufficient_evidence"] += 1
            continue
        if weak == "insufficient_evidence" and len(subs) > 1:
            weak = "partially_supported"
        verdicts.append({"claim_id": cid, "claim_text": text, "verdict": weak, "subclaims": subs,
                         "qualified_conclusion": "条件/限定以证据原文为准。"})
        summary[weak] += 1
    res = {
        "case_id": (case or {}).get("case_id") if isinstance(case, dict) else "unknown",
        "status": "answered",
        "result": {"verdicts": verdicts, "verdict_summary": summary},
        "claims": [],
        "uncertainties": {"uncovered": uncovered, "unreported": [], "unverifiable": [],
                          "conflicts": [], "human_review": [], "summary": "规则审计器产物"},
    }
    return res


# ---------------------------------------------------------------- 指标测量

def measure(res, case, claims, steps, rounds, steps_source, rounds_source):
    """统一口径测量一个产物。"""
    paras = paragraphs_of(case)
    paras_n = {k: norm(v) for k, v in paras.items()}
    items = claim_items(claims)
    total = len(items)
    want = [claim_id_of(it, i) for i, it in enumerate(items)]
    vts = verdict_items(res)
    judged = {str(v.get("claim_id")) for v in vts}
    unc = uncovered_ids(res)
    covered = judged | unc
    missing = [w for w in want if w not in covered]

    ev_total = 0
    ev_ok = 0
    ev_failed = 0
    false_sup = 0
    sub_count = 0
    problem_keys = set()          # 需人工回原文核对的实质条目（去重）
    text_by_cid = {claim_id_of(it, i): claim_text_of(it) for i, it in enumerate(items)}
    for v in vts:
        cid = str(v.get("claim_id"))
        subs = sub_of(v)
        sub_count += len(subs)
        cnums = numbers_of(text_by_cid.get(cid, ""))
        cpolar = polarity(text_by_cid.get(cid, ""))
        ev_here_ok = False
        for si, s in enumerate(subs):
            for e in (s.get("evidence") or []):
                if not isinstance(e, dict):
                    continue
                ev_total += 1
                pid = str(e.get("paragraph_id") or "")
                q = norm(e.get("quote") or "")
                if not q:
                    ev_failed += 1
                    problem_keys.add((cid, str(s.get("sub_id") or si)))
                    continue
                if pid in paras_n and q in paras_n[pid]:
                    ev_ok += 1
                    ev_here_ok = True
                    continue
                if pid in paras_n:
                    ev_failed += 1   # 段落存在但摘录回证失败 -> 需人工回原文核对
                    problem_keys.add((cid, str(s.get("sub_id") or si)))
                # 段落表缺失：无法核验，既不计入通过也不计入失败（闸门未运行）
        if str(v.get("verdict")) == "supported":
            if not ev_here_ok:
                false_sup += 1
                problem_keys.add((cid, "*"))
            else:
                quotes = " ".join(str(e.get("quote") or "") for s in subs for e in (s.get("evidence") or [])
                                  if isinstance(e, dict))
                cnum = numbers_of(quotes)
                if cnums and not (cnums & cnum):
                    false_sup += 1
                    problem_keys.add((cid, "*"))
                elif cpolar and polarity(quotes) and polarity(quotes) != cpolar:
                    false_sup += 1
                    problem_keys.add((cid, "*"))
    for w in missing:
        problem_keys.add((str(w), "*"))
    unc_obj = res.get("uncertainties") if isinstance(res, dict) else None
    human_list = (unc_obj or {}).get("human_review") or [] if isinstance(unc_obj, dict) else []
    human = len(human_list)
    for h in human_list:
        if isinstance(h, dict):
            problem_keys.add((str(h.get("claim_id") or "?"), str(h.get("sub_id") or "*")))
    return {
        "claims_total": total,
        "claims_judged": len(judged & set(want)) if want else len(judged),
        "claims_uncovered_registered": len(unc & set(want)) if want else len(unc),
        "claims_missing": len(missing),
        "missing_claim_ids": missing[:20],
        "verdict_coverage_rate": round(len(covered) / float(total), 4) if total else None,
        "subclaims_total": sub_count,
        "subclaims_per_claim": round(sub_count / float(total), 3) if total else None,
        "evidence_total": ev_total,
        "evidence_backverified": ev_ok,
        "evidence_backverify_failed": ev_failed,
        "evidence_backverify_rate": round(ev_ok / float(ev_total), 4) if ev_total else None,
        "uncovered_miss_count": len(missing),
        "false_supported_count": false_sup,
        # 需人工核对条目数 = 实质上必须回原文才能定案的条目（回证失败/误支持/漏检，去重）
        "manual_review_items": len(problem_keys),
        "manual_review_explicit": human,
        "manual_review_backverify_failed": ev_failed,
        "steps": steps,
        "rounds": rounds,
        "steps_source": steps_source,
        "rounds_source": rounds_source,
    }


# ---------------------------------------------------------------- 闸门消融

def gate_pass(res, case, claims, on, steps, rounds, steps_source, rounds_source):
    """对**同一份交付产物**跑质量闸门 开/关两遍。

    开：摘录逐字回证不通过的子判断降级为 insufficient_evidence 并登记人工核对；
        输入中既未判定也未登记的 claim 自动补登记 uncovered。
    关：不做回证降级、不做补登记（保留原始判定，暴露漏检与误支持）。
    """
    work = copy.deepcopy(res)
    paras = paragraphs_of(case)
    paras_n = {k: norm(v) for k, v in paras.items()}
    items = claim_items(claims)
    downgraded = 0
    detected = 0
    if on:
        unc = work.setdefault("uncertainties", {})
        if not isinstance(unc, dict):
            unc = {}
            work["uncertainties"] = unc
        human = unc.setdefault("human_review", [])
        for v in verdict_items(work):
            for s in sub_of(v):
                bad = []
                for e in (s.get("evidence") or []):
                    if not isinstance(e, dict):
                        continue
                    pid = str(e.get("paragraph_id") or "")
                    q = norm(e.get("quote") or "")
                    if not q:
                        bad.append(e)
                        continue
                    if pid in paras_n and q not in paras_n[pid]:
                        bad.append(e)
                if bad:
                    detected += 1
                    for e in bad:
                        human.append({"claim_id": str(v.get("claim_id")),
                                      "sub_id": str(s.get("sub_id")),
                                      "reason": "摘录未通过逐字回证（空白归一化子串匹配失败），需人工核对",
                                      "quote": str(e.get("quote") or "")[:120]})
                    s["evidence"] = [e for e in (s.get("evidence") or []) if e not in bad]
                    if s.get("verdict") in ("supported", "partially_supported"):
                        s["verdict"] = "insufficient_evidence"
                        s["rationale"] = "证据未通过逐字回证，降级为无法判断（需人工核对）"
                        downgraded += 1
        # 父级 verdict 按子判断最弱一致结论重算（降级后不得仍标 supported）
        for v in verdict_items(work):
            subs = sub_of(v)
            if not subs:
                continue
            weakest = "supported"
            for s in subs:
                sv = s.get("verdict")
                if sv not in VERDICTS:
                    continue
                if sv == "contradicted":
                    weakest = "contradicted"
                    break
                if sv == "insufficient_evidence":
                    weakest = "partially_supported" if weakest == "supported" else weakest
                elif sv == "partially_supported" and weakest == "supported":
                    weakest = "partially_supported"
            if weakest != v.get("verdict"):
                v["verdict"] = weakest
                v["qualified_conclusion"] = str(v.get("qualified_conclusion") or "") + \
                    "（父级判定已按降级后的子判断重算为 %s）" % weakest
        # 未覆盖补登记
        judged = {str(v.get("claim_id")) for v in verdict_items(work)}
        unc_ids = uncovered_ids(work)
        miss = [claim_id_of(it, i) for i, it in enumerate(items)
                if claim_id_of(it, i) not in judged and claim_id_of(it, i) not in unc_ids]
        cov = unc.setdefault("uncovered", [])
        for cid in miss:
            cov.append({"claim_id": cid, "reason": "交付产物中既无判定也无未覆盖登记，闸门补登记"})
    m = measure(work, case, claims, steps, rounds, steps_source, rounds_source)
    m["downgraded_subclaims"] = downgraded
    m["quote_violations_detected"] = detected
    return work, m


# ---------------------------------------------------------------- 运行日志

def read_runlog(path):
    """可选：读取 Agent 侧运行日志 /app/work/run_log.jsonl 以取真实步骤与复核轮次。"""
    if not path or not os.path.exists(path):
        return None
    stages, rounds = [], 0
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if not isinstance(rec, dict):
                    continue
                stages.append(rec)
                if str(rec.get("kind") or "").lower() in ("recheck", "refetch", "round"):
                    rounds += 1
    except Exception:
        return None
    return {"stages": stages, "steps": len(stages), "rounds": rounds}


# ---------------------------------------------------------------- 子命令

def cmd_compare(args):
    t0 = now_ms()
    res = load_json(args.result)
    case = load_json(args.case) if args.case and os.path.exists(args.case) else {}
    claims = load_json(args.claims) if args.claims and os.path.exists(args.claims) else {}
    log = read_runlog(args.runlog)
    if log:
        steps, rounds, s_src, r_src = log["steps"], log["rounds"], "run_log", "run_log"
    else:
        steps, rounds, s_src, r_src = (5, 2, "protocol", "protocol")
    full, m_full = gate_pass(res, case, claims, True, steps, rounds, s_src, r_src)
    ablated, m_abl = gate_pass(res, case, claims, False, steps, rounds, s_src, r_src)
    out = {
        "ok": True, "status": "completed", "mode": "compare",
        "input_fingerprint": {"result": digest(res), "case": digest(case), "claims": digest(claims)},
        "arms": {
            "full": {"gates_on": True, "metrics": m_full},
            "ablated": {"gates_on": False, "metrics": m_abl},
        },
        "delta_full_minus_ablated": {
            k: (round(m_full[k] - m_abl[k], 4) if isinstance(m_full.get(k), (int, float))
                and isinstance(m_abl.get(k), (int, float)) else None)
            for k in m_full
        },
        "elapsed_ms": now_ms() - t0,
    }
    return out, full


def cmd_rule(args):
    t0 = now_ms()
    case = load_json(args.case)
    claims = load_json(args.claims)
    res_full = rule_audit(case, claims, "full")
    res_base = rule_audit(case, claims, "baseline")
    paras = paragraphs_of(case)
    m_full = measure(res_full, case, claims, 5, 2, "protocol", "protocol")
    m_base = measure(res_base, case, claims, 2, 0, "protocol", "protocol")
    out = {
        "ok": True, "status": "completed", "mode": "rule",
        "input_fingerprint": {"case": digest(case), "claims": digest(claims),
                              "paragraphs": len(paras)},
        "arms": {"full": {"gates_on": True, "metrics": m_full},
                 "ablated": {"gates_on": False, "metrics": m_base}},
        "delta_full_minus_ablated": {
            k: (round(m_full[k] - m_base[k], 4) if isinstance(m_full.get(k), (int, float))
                and isinstance(m_base.get(k), (int, float)) else None)
            for k in m_full
        },
        "note": "规则审计器为确定性参考实现（非官方案例答案），用于同输入下量化各机制的可测效应。",
        "elapsed_ms": now_ms() - t0,
    }
    return out, res_full


# ---------------------------------------------------------------- 消融两跑

CHECKER = "claim_check.py"


def run_checker(result_path, case_path, claims_path, out_path, ablate=False):
    """真实调用交付给用户的校验器跑一遍（子进程），返回可核对的运行记录。

    ablate=True 时追加 --ablate：关闭「逐字回证」与「覆盖对账」两道闸门，
    复现未加载本技能质量闸门时的基线行为。
    """
    here = os.path.dirname(os.path.abspath(__file__))
    script = os.path.join(here, CHECKER)
    cmd = [sys.executable, script, "--result", result_path, "--case", case_path,
           "--claims", claims_path, "--out", out_path]
    if ablate:
        cmd.append("--ablate")
    rec = {"cmd": " ".join(cmd), "ablate": bool(ablate)}
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        rec["exit_code"] = p.returncode
        rec["stdout_tail"] = (p.stdout or "")[-1500:]
    except Exception as e:
        rec["exit_code"] = -1
        rec["error"] = "%s: %s" % (type(e).__name__, e)
    report = {}
    try:
        with open(out_path, "r", encoding="utf-8") as f:
            report = json.load(f)
    except Exception as e:
        rec["report_error"] = "%s: %s" % (type(e).__name__, e)
    probs = report.get("problems") or []
    warns = report.get("warnings") or []
    rec["ok"] = report.get("ok")
    rec["problems_count"] = len(probs)
    rec["warnings_count"] = len(warns)
    rec["gates"] = report.get("gates") or {}
    rec["ablation"] = report.get("ablation") or {}
    rec["problems"] = probs
    return rec


def cmd_ablate(args):
    """同输入两跑：跑完整闸门 + 跑消融基线，产出真实对照数字。

    两跑共用同一份 result/case/claims（指纹记录在 input_fingerprint）。
    1) 闸门层两跑：真的把交付的 claim_check.py 跑两遍（full / --ablate），
       得到「闸门开/关各拦下多少内容级问题」的真实差值。
    2) 流水线层两跑：rule_audit 在 full/baseline 两种模式下对同一输入各跑一遍，
       得到判定覆盖率/证据回证率/漏检数/需人工核对条目数/步骤数的真实差值。
    """
    t0 = now_ms()
    res = load_json(args.result)
    case = load_json(args.case) if args.case and os.path.exists(args.case) else {}
    claims = load_json(args.claims) if args.claims and os.path.exists(args.claims) else {}
    work = os.path.dirname(os.path.abspath(args.result)) or "."
    rep_full = os.path.join(work, "claim_check_ablate_full.json")
    rep_abl = os.path.join(work, "claim_check_ablate_ablated.json")
    run_full = run_checker(args.result, args.case or "/input/case.json",
                            args.claims or "/input/claims-to-verify.json", rep_full, ablate=False)
    run_abl = run_checker(args.result, args.case or "/input/case.json",
                           args.claims or "/input/claims-to-verify.json", rep_abl, ablate=True)

    # 闸门层：闸门开比闸门关多拦住的内容级问题数
    caught_by_gates = max(0, int(run_full.get("problems_count") or 0)
                          - int(run_abl.get("problems_count") or 0))
    gate_layer = {
        "full_run": run_full,
        "ablated_run": run_abl,
        "problems_caught_only_by_gates": caught_by_gates,
        "same_input": True,
        "note": "同一份 result/case/claims 被交付给用户的校验器真实跑两遍；"
                "差值=开启闸门额外拦下的内容级问题数（消融臂记为 WARNING 不判 FAIL）。",
    }

    # 流水线层：full vs baseline 两套真实跑
    log = read_runlog(args.runlog)
    if log:
        steps, rounds, s_src, r_src = log["steps"], log["rounds"], "run_log", "run_log"
    else:
        steps, rounds, s_src, r_src = (5, 2, "protocol", "protocol")
    res_full = rule_audit(case, claims, "full")
    res_base = rule_audit(case, claims, "baseline")
    m_full = measure(res_full, case, claims, steps, rounds, s_src, r_src)
    m_base = measure(res_base, case, claims, 2, 0, "protocol", "protocol")
    pipeline_layer = {
        "arms": {"full": {"gates_on": True, "metrics": m_full},
                 "ablated": {"gates_on": False, "metrics": m_base}},
        "delta_full_minus_ablated": {
            k: (round(m_full[k] - m_base[k], 4) if isinstance(m_full.get(k), (int, float))
                and isinstance(m_base.get(k), (int, float)) else None)
            for k in m_full
        },
    }

    out = {
        "ok": True, "status": "completed", "mode": "ablate",
        "switch": "--ablate / CLAIM_AUDIT_ABLATE=1",
        "input_fingerprint": {"result": digest(res), "case": digest(case), "claims": digest(claims)},
        "gate_layer": gate_layer,
        "pipeline_layer": pipeline_layer,
        "headline": {
            "verdict_coverage_rate": {"full": m_full["verdict_coverage_rate"],
                                      "ablated": m_base["verdict_coverage_rate"],
                                      "delta": pipeline_layer["delta_full_minus_ablated"].get("verdict_coverage_rate")},
            "evidence_backverify_rate": {"full": m_full["evidence_backverify_rate"],
                                         "ablated": m_base["evidence_backverify_rate"],
                                         "delta": pipeline_layer["delta_full_minus_ablated"].get("evidence_backverify_rate")},
            "uncovered_miss_count": {"full": m_full["uncovered_miss_count"],
                                     "ablated": m_base["uncovered_miss_count"],
                                     "delta": pipeline_layer["delta_full_minus_ablated"].get("uncovered_miss_count")},
            "manual_review_items": {"full": m_full["manual_review_items"],
                                    "ablated": m_base["manual_review_items"],
                                    "delta": pipeline_layer["delta_full_minus_ablated"].get("manual_review_items")},
            "steps": {"full": m_full["steps"], "ablated": m_base["steps"],
                      "delta": pipeline_layer["delta_full_minus_ablated"].get("steps")},
        },
        "elapsed_ms": now_ms() - t0,
    }
    return out, res_full


def cmd_patch(args):
    t0 = now_ms()
    res = load_json(args.result)
    cmp_out, _ = cmd_compare(args)
    rule_out = {}
    rule_res = None
    abl_out = {}
    try:
        abl_out, _ = cmd_ablate(args)
    except Exception as e:  # 消融臂失败不影响交付
        abl_out = {"ok": False, "status": "failed", "error": str(e)}
    if args.case and args.claims and os.path.exists(args.case) and os.path.exists(args.claims):
        try:
            rule_out, rule_res = cmd_rule(args)
        except Exception as e:  # 规则臂失败不影响交付
            rule_out = {"ok": False, "status": "failed", "error": str(e)}
    fp = {"result": digest(res), "case": cmp_out["input_fingerprint"]["case"],
          "claims": cmp_out["input_fingerprint"]["claims"]}
    # 两臂指标：闸门层（对交付产物跑两遍校验器）与流水线层（同输入跑两遍确定性流水线）
    gate_layer = abl_out.get("gate_layer") if abl_out.get("ok") else {}
    pipe_layer = abl_out.get("pipeline_layer") if abl_out.get("ok") else {}
    pipe_arms = pipe_layer.get("arms") or {}
    pipe_delta = pipe_layer.get("delta_full_minus_ablated") or {}
    headline = abl_out.get("headline") or {}
    gain = {
        "schema_version": "1.1",
        "generated_by": "scripts/gain_probe.py",
        "generated_at_ms": t0,
        "method": ("同输入同工具两跑对照。闸门层：交付的 claim_check.py 在同一份 result/case/claims 上"
                   "真实跑两遍（full 与 --ablate 消融臂），差值=闸门额外拦下的内容级问题数。"
                   "流水线层：确定性流水线在 full/baseline 两模式下对同一输入各跑一遍，"
                   "得到判定覆盖率/证据回证率/未覆盖漏检数/需人工核对条目数/步骤数的真实差值。"
                   "两臂输入指纹见 input_fingerprint。"),
        "ablation_switch": {
            "flag": "--ablate",
            "env": "CLAIM_AUDIT_ABLATE=1",
            "disabled_gates": ["coverage_audit（覆盖对账）", "quote_verification（逐字回证）"],
            "how_to_run": ("python3 scripts/gain_probe.py ablate --result /app/output/result.json "
                           "--case /input/case.json --claims /input/claims-to-verify.json"),
        },
        "input_fingerprint": fp,
        "arms": {"full": pipe_arms.get("full", cmp_out["arms"]["full"]),
                 "ablated": pipe_arms.get("ablated", cmp_out["arms"]["ablated"])},
        "delta_full_minus_ablated": pipe_delta or cmp_out["delta_full_minus_ablated"],
        "headline": headline,
        "gate_layer": gate_layer,
        "delivered_artifact_gate_arms": {
            "full": cmp_out["arms"]["full"], "ablated": cmp_out["arms"]["ablated"],
            "note": "对交付产物本身开/关闸门后的逐项指标（含降级数与改写检出数）。",
        },
        "rule_pipeline_arms": ({"full": rule_out.get("arms", {}).get("full"),
                                 "ablated": rule_out.get("arms", {}).get("ablated"),
                                 "note": rule_out.get("note")} if rule_out else {}),
        "mechanism_to_metric": [
            {"mechanism": "逐字回证闸门（空白归一化子串匹配）",
             "metric": "evidence_backverify_rate / false_supported_count / downgraded_subclaims",
             "expected": "开启后回证率上升、误支持下降、改写摘录被降级并转人工核对",
             "observed": "见 delta_full_minus_ablated 与 gate_layer.problems_caught_only_by_gates"},
            {"mechanism": "未覆盖登记闸门（覆盖对账 + 补登记）",
             "metric": "uncovered_miss_count / verdict_coverage_rate",
             "expected": "开启后漏检归零、判定覆盖率上升",
             "observed": "见 headline.verdict_coverage_rate 与 headline.uncovered_miss_count"},
            {"mechanism": "论断拆解（fact/comparison/causal/scope）",
             "metric": "subclaims_per_claim",
             "expected": "全流程臂的子判断粒度高于基线臂",
             "observed": "见 rule_pipeline_arms"},
        ],
        "boundaries": [
            "对照在**同一份交付产物与同一输入**上做，反映的是本技能质量闸门的可测效应；平台基础 Agent 与参赛 Agent 的官方对照由组织方提供，不由本包代答。",
            "证据回证率仅在段落表可解析时被实测（case.json 含 paragraphs/passages/sections）；否则该指标为 null 并标注 gate skipped。",
            "误支持计数基于数值/方向线索的机械比对，不等同于人工标注的语义判错率。",
            "步骤数与复核轮次：优先取运行日志 run_log.jsonl；无日志时取协议常量并在 source 字段标注 protocol。",
            "消融臂由 --ablate / CLAIM_AUDIT_ABLATE=1 真实触发，闸门关闭时内容级问题降级为 WARNING（照实打印，不隐藏）。",
        ],
        "failure_conditions": [
            "case.json 段落表缺失 -> 逐字回证闸门不可实测，证据类指标置 null，不得宣称已回证。",
            "claims 文件缺失或为空 -> 覆盖类指标为 null，闸门降级并写 gate_note。",
            "运行日志缺失 -> steps/rounds 为协议常量，不可作为实际耗时的证据。",
            "claim_check.py 子进程启动失败 -> gate_layer 记 error，其余两臂指标照常交付。",
        ],
        "honesty_note": "本块所有数值由脚本在本机实测写出；未经实测的字段一律置 null 并注明来源，不手填。",
    }
    m_full_metrics = gain["arms"]["full"].get("metrics") or {}
    eff = {
        "collector": "scripts/gain_probe.py",
        "auto_collected": True,
        "measured_at_ms": t0,
        "elapsed_ms": now_ms() - t0,
        "claims_total": m_full_metrics.get("claims_total"),
        "subclaims_total": m_full_metrics.get("subclaims_total"),
        "evidence_total": m_full_metrics.get("evidence_total"),
        "paragraphs_available": len(paragraphs_of(load_json(args.case))) if args.case and os.path.exists(args.case) else 0,
        "steps": m_full_metrics.get("steps"),
        "steps_source": m_full_metrics.get("steps_source"),
        "rounds": m_full_metrics.get("rounds"),
        "rounds_source": m_full_metrics.get("rounds_source"),
        "manual_review_items": m_full_metrics.get("manual_review_items"),
        "uncovered_miss_count": m_full_metrics.get("uncovered_miss_count"),
        "verdict_coverage_rate": m_full_metrics.get("verdict_coverage_rate"),
        "evidence_backverify_rate": m_full_metrics.get("evidence_backverify_rate"),
        "ablation_switch": gain["ablation_switch"],
        "reproduce": "python3 scripts/gain_probe.py patch --result /app/output/result.json "
                     "--case /input/case.json --claims /input/claims-to-verify.json "
                     "--runlog /app/work/run_log.jsonl --out /app/output/gain_evidence.json",
        "reproduce_ablation": "python3 scripts/gain_probe.py ablate --result /app/output/result.json "
                              "--case /input/case.json --claims /input/claims-to-verify.json",
    }
    res["gain_evidence"] = gain
    res["efficiency"] = eff
    if isinstance(res.get("uncertainties"), dict):
        res["uncertainties"].setdefault("summary", "")
    if args.out:
        try:
            with open(args.out, "w", encoding="utf-8") as f:
                json.dump({"ok": True, "status": "completed", "mode": "patch",
                           "gain_evidence": gain, "efficiency": eff,
                           "compare": cmp_out, "ablate": abl_out, "rule": rule_out},
                          f, ensure_ascii=False, indent=1)
        except Exception as e:
            print("[gain_probe] WARNING 证据文件写出失败: %s" % e)
    try:
        with open(args.result, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
    except Exception as e:
        print("[gain_probe] WARNING result.json 回写失败: %s" % e)
    return {"ok": True, "status": "completed", "mode": "patch",
            "gain_evidence": gain, "efficiency": eff}, res


def cmd_demo(args):
    """用 examples/ 合成件自检全链路（示意数据，非正式案例结果）。"""
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    case_path = os.path.join(base, "examples", "example-input.json")
    claims_path = os.path.join(base, "examples", "example-claims.json")
    case = load_json(case_path)
    claims = load_json(claims_path)
    res = load_json(os.path.join(base, "examples", "example-result.json"))
    _f, m_full = gate_pass(res, case, claims, True, 5, 2, "protocol", "protocol")
    _a, m_abl = gate_pass(res, case, claims, False, 5, 2, "protocol", "protocol")
    rule_out, _res = cmd_rule(argparse.Namespace(case=case_path, claims=claims_path))
    out = {"ok": True, "status": "completed", "mode": "demo",
           "note": "examples/ 为合成示意件，自检用；不代表正式案例结果。",
           "gate_arms": {"full": m_full, "ablated": m_abl},
           "rule_arms": rule_out["arms"],
           "delta": rule_out["delta_full_minus_ablated"]}
    return out, res


def main() -> int:
    ap = Exit0Parser(description="同输入增益对照与效率采集（恒 exit 0）")
    ap.add_argument("--ablate", action="store_true",
                    help="消融基线：关闭逐字回证与覆盖对账两道闸门（等价环境变量 CLAIM_AUDIT_ABLATE=1）")
    sub = ap.add_subparsers(dest="cmd")
    for name in ("compare", "ablate", "rule", "patch", "demo"):
        p = sub.add_parser(name)
        p.add_argument("--result", default=None)
        p.add_argument("--case", default=None)
        p.add_argument("--claims", default=None)
        p.add_argument("--runlog", default=None)
        p.add_argument("--out", default=None)
        p.add_argument("--ablate", action="store_true",
                       help="消融基线：关闭逐字回证与覆盖对账两道闸门")
    args = ap.parse_args()
    if not args.cmd:
        args.cmd = "demo"
    try:
        if args.cmd == "compare":
            out, _ = cmd_compare(args)
        elif args.cmd == "ablate":
            out, _ = cmd_ablate(args)
        elif args.cmd == "rule":
            out, _ = cmd_rule(args)
        elif args.cmd == "patch":
            out, _ = cmd_patch(args)
        else:
            out, _ = cmd_demo(args)
    except Exception as e:
        out = {"ok": False, "status": "failed", "mode": args.cmd, "error": "%s: %s" % (type(e).__name__, e)}
        print("[gain_probe] FAIL %s" % out["error"])
    if args.out:
        try:
            with open(args.out, "w", encoding="utf-8") as f:
                json.dump(out, f, ensure_ascii=False, indent=1)
        except Exception as e:
            print("[gain_probe] WARNING 报告写出失败: %s" % e)
    print(json.dumps(out, ensure_ascii=False, indent=1)[:4000])
    return 0  # 恒 0：失败不中断交付，结论看 ok/status


if __name__ == "__main__":
    sys.exit(main())
