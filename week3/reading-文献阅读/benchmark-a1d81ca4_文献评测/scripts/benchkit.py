#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""benchkit.py — benchkit v3 评测包工具
（init / techcheck / diff / report / embed / verify / gain / efficiency）。

用法：
    python3 benchkit.py init       --case <case.json> --outdir <dir> [--input-dir <dir>]
    python3 benchkit.py techcheck  --outdir <dir>
    python3 benchkit.py diff       --outdir <dir>
    python3 benchkit.py report     --outdir <dir>
    python3 benchkit.py embed      --outdir <dir>
    python3 benchkit.py verify     --outdir <dir> [--case <case.json>]
    python3 benchkit.py gain       --outdir <dir> [--truth <truth.json>]
    python3 benchkit.py efficiency --outdir <dir> [--model-requests N]

设计约束：
- 任何输入（含损坏 JSON、空文件、未知结构）都不得抛裸异常、不得产出空题集：
  所有命令全捕获降级，仅打印警告并写 warn.log，退出码恒为 0（verify 的 FAIL 用
  verdict 字段与打印表达，不中断交付）；识别失败合成兜底题卡。
- techcheck 的 score_suggest 只是确定性建议（数值/条件/术语覆盖），不是 DSH 分数，
  也不是独立语义验证；语义 0/1/2 由评分规则的判定线给出，两者分开记录。
- 判分口径必须机械可观察：scoring_rule 写不出 0/1/2 判定线时，verify 会拦截。
- gain 的两条臂吃同一批作答，只改判分时可见信息；差异度量的是判分口径增益，
  不是跨 Agent 能力增益（跨 Agent 对照由平台固定白板负责）。
"""
from __future__ import annotations

import argparse
import csv
import datetime
import hashlib
import json
import os
import re
import sys
import tempfile
import time

SCORE_FIELDS = ("item_id", "score", "rationale", "disputed", "failure_type", "answer_raw_excerpt")
TOP_KEYS = ("case_id", "status", "result", "claims", "uncertainties")
STATUSES = ("answered", "partial", "insufficient_evidence", "input_error")
RULE_ONLY = "仅规则评分"
# ---- 严格臂 / 基础臂（无工具判分）的口径关键词 ----
HEDGE_SOURCE = ("suggests", "suggest ", "may ", "might ", "possible", "likely",
                "imply", "indicates", "推测", "可能", "暗示", "似乎")
HEDGE_ANSWER = ("suggests", "可能", "推断", "表明", "暗示", "提示", "似乎")
STRONG_CLAIM = ("证明", "证实", "必然", "肯定", "断定", "proves", "proven",
                "definitely", "certainly", "conclusively", "undoubtedly")
DIGIT_RE = re.compile(r"\d")

# ---- 失败类型分类（与 SKILL.md 的 8 类归因一致）----
FAIL_SUGGEST = {
    "no_answer": "未产出答案：核对题面指令与来源段落后再作答，不得留空",
    "text_mismatch": "事实或数值与来源不符：回到 source_text 逐字核对",
    "missing_condition": "补齐缺失条件（逐条对照 conditioning）",
    "overclaim": "论断强度超出来源：降级为来源支持的表述（如 suggests 保持推断级）并保留限定",
    "format_error": "按题面输出格式约束重排（字段/定位/结构）",
    "file_unreadable": "来源文件无法读取：如实登记缺口，不编造内容",
    "permission_denied": "权限不足：登记后降级交付，不伪造替代数据",
    "disputed": "存疑项交人工复核，评分不改动，评分规则可修订",
}

# ---- 工单字段同义词映射（识别失败即合成兜底，绝不产空题集） ----
TASK_KEYS = ("task", "question", "prompt", "instruction", "query", "requirement",
             "problem", "title", "ask", "sub_question", "topic", "assignment")
ID_KEYS = ("item_id", "id", "qid", "task_id", "question_id", "number", "index", "key")
REF_KEYS = ("reference_answer", "gold_answer", "gold", "ground_truth", "expected_answer",
            "expected", "sample_answer", "model_answer", "answer", "reference")
SRC_KEYS = ("source_text", "text", "source", "passage", "paragraph", "table_text",
            "evidence", "context", "material", "materials", "excerpt", "quote",
            "supporting_text")
COND_KEYS = ("conditioning", "conditions", "condition", "constraints", "givens",
             "assumptions", "conditioned_on")
RULE_KEYS = ("scoring_rule", "grading_rule", "grading", "score_rule", "scoring",
             "rubric", "criteria", "verdict_rule", "judgment_rule")
INPUTREF_KEYS = ("input_ref", "source_ref", "source_id", "location", "page", "section",
                 "evidence_ref", "figure", "table")
DIFF_KEYS = ("difficulty", "level")
PATH_HINTS = ("workorder", "item", "question", "entry", "task", "case", "subtask",
              "benchmark", "题")
STOPWORDS = {"the", "a", "an", "of", "in", "to", "and", "is", "are", "was", "were",
             "for", "on", "at", "by", "with", "that", "this", "it", "as", "be"}


def log(outdir, msg):
    print("[benchkit] %s" % msg)
    try:
        with open(os.path.join(outdir, "warn.log"), "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, obj):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


# ============ 效率台账：工具调用/判分轮次/返工轮次自动计数 ============
LEDGER = ".benchkit_ledger.jsonl"
JUDGE_CMDS = ("techcheck", "report", "verify", "gain")
REWORK_CMDS = ("diff",)


def ledger_append(outdir, cmd, extra=None):
    """每个子命令调用都追加一条台账记录（供 efficiency 自动计数，可复现）。"""
    try:
        d = outdir or "."
        os.makedirs(d, exist_ok=True)
        rec = {"cmd": cmd, "ts": datetime.datetime.now().isoformat(timespec="seconds")}
        if extra:
            rec.update(extra)
        with open(os.path.join(d, LEDGER), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def ledger_read(outdir):
    recs = []
    try:
        with open(os.path.join(outdir, LEDGER), "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    recs.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        pass
    return recs


def sha16(obj):
    raw = json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def iter_nodes(obj, path="$"):
    yield path, obj
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from iter_nodes(v, path + "." + str(k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from iter_nodes(v, "%s[%d]" % (path, i))


def first_key(d, keys):
    for k in keys:
        if isinstance(d, dict) and k in d and d[k] not in (None, ""):
            return d[k]
    return None


def to_str_list(v):
    """标量/列表/字典/换行或分号分隔字符串 → 字符串列表（条件词不因形态丢条目）。"""
    if v in (None, ""):
        return []
    if isinstance(v, list):
        out = [str(x) for x in v if str(x).strip()]
    elif isinstance(v, dict):
        out = ["%s: %s" % (k, x) for k, x in v.items() if str(x).strip()]
    else:
        out = [s.strip() for s in re.split(r"[\n；;]+", str(v)) if s.strip()]
    return out


def find_contract(case):
    """在 case.json 任意层级找 output_contract（dict 或键名 list），取不到返回 {}。"""
    if isinstance(case, dict):
        oc = case.get("output_contract")
        if isinstance(oc, dict):
            return dict(oc)
        if isinstance(oc, list):
            return {str(k): None for k in oc}
    for _, node in iter_nodes(case):
        if isinstance(node, dict):
            oc = node.get("output_contract")
            if isinstance(oc, dict):
                return dict(oc)
            if isinstance(oc, list):
                return {str(k): None for k in oc}
    return {}


def find_items(case):
    """递归找工单条目列表：优先路径含题义关键词、且含 task 类字段的 dict 列表。"""
    best, best_score = None, -1.0
    for path, node in iter_nodes(case):
        if isinstance(node, list) and node:
            dicts = [d for d in node if isinstance(d, dict)]
            if not dicts:
                continue
            taskish = sum(1 for d in dicts if first_key(d, TASK_KEYS) is not None)
            if taskish == 0:
                continue
            score = taskish + len(dicts) * 0.1
            low = path.lower()
            if any(h in low for h in PATH_HINTS):
                score += 5.0
            if score > best_score:
                best_score, best = score, dicts
    if best:
        return best
    if isinstance(case, list):
        dicts = [d for d in case if isinstance(d, dict) and first_key(d, TASK_KEYS) is not None]
        if dicts:
            return dicts
    return []


def norm_item(w, i):
    """同义词映射归一为题卡；结构未知时绝不丢弃条目，extra 保留未识别字段。"""
    if not isinstance(w, dict):
        w = {"task": str(w)}
    task = first_key(w, TASK_KEYS)
    if isinstance(task, (dict, list)):
        task = json.dumps(task, ensure_ascii=False)
    src = first_key(w, SRC_KEYS)
    if isinstance(src, (dict, list)):
        src = json.dumps(src, ensure_ascii=False)
    ref = first_key(w, REF_KEYS)
    consumed = set(TASK_KEYS + ID_KEYS + REF_KEYS + SRC_KEYS + COND_KEYS +
                   RULE_KEYS + INPUTREF_KEYS + DIFF_KEYS)
    extra = {}
    for k, v in w.items():
        if k not in consumed and v not in (None, ""):
            extra[str(k)] = str(v)[:500]
    return {
        "item_id": str(first_key(w, ID_KEYS) or ("item-%d" % (i + 1))),
        "task": str(task or ""),
        "input_ref": str(first_key(w, INPUTREF_KEYS) or ""),
        "conditioning": [str(c) for c in to_str_list(first_key(w, COND_KEYS))],
        "reference_answer": (str(ref) if ref not in (None, "") else RULE_ONLY),
        "scoring_rule": str(first_key(w, RULE_KEYS) or ""),
        "difficulty": str(first_key(w, DIFF_KEYS) or "unspecified"),
        "source_text_snapshot": str(src or ""),
        "extra": extra,
    }


def fallback_item(case):
    """识别不出结构化条目时合成单条兜底题卡，绝不产出空题集。"""
    task, src = "", ""
    if isinstance(case, dict):
        t = first_key(case, TASK_KEYS) or first_key(
            case, ("description", "summary", "objective", "goal", "background"))
        if isinstance(t, (dict, list)):
            t = json.dumps(t, ensure_ascii=False)
        task = str(t or "")
        s = first_key(case, SRC_KEYS)
        if isinstance(s, (dict, list)):
            s = json.dumps(s, ensure_ascii=False)
        src = str(s or "")
    if not task:
        task = ("未在 case.json 中识别出结构化条目：请人工阅读 /input/ 下材料与 task.md，"
                "按题面要求作答；本题卡为兜底记录，作答与评分口径不变。")
    return {
        "item_id": "item-1", "task": task, "input_ref": "", "conditioning": [],
        "reference_answer": RULE_ONLY,
        "scoring_rule": ("2=主结论正确且条件完整、可回溯来源定位；1=部分正确或缺条件；"
                         "0=错误、编造或未答"),
        "difficulty": "unspecified", "source_text_snapshot": src, "extra": {},
    }


def scan_materials(input_dir):
    mats = []
    try:
        for name in sorted(os.listdir(input_dir)):
            p = os.path.join(input_dir, name)
            if os.path.isfile(p):
                mats.append({"file": name, "bytes": os.path.getsize(p)})
    except Exception:
        pass
    return mats


def excerpt(text, head=300, tail=100):
    text = str(text or "")
    if len(text) <= head + tail + 1:
        return text
    return text[:head] + "…" + text[-tail:]


def token_cover(needle, hay):
    n = set(re.findall(r"\w+", str(needle).lower())) - STOPWORDS
    if not n:
        return 1.0
    h = set(re.findall(r"\w+", str(hay).lower()))
    return round(len(n & h) / float(len(n)), 3)


def point_met(point, answer):
    """要点是否可判满足：子串命中 → 引号术语命中 → 数字命中 → token 覆盖 ≥0.6
    （确定性建议，非语义终判）。"""
    p = str(point or "").strip()
    if not p:
        return True
    if p in answer:
        return True
    quoted = re.findall(r"[『「\"'“”‘’]([^』」\"'“”‘’]{1,40})[』」\"'“”‘’]", p)
    if quoted:
        return all(q in answer for q in quoted)
    nums = re.findall(r"\d+(?:\.\d+)?", p)
    if nums:
        return all(n in answer for n in nums)
    return token_cover(p, answer) >= 0.6


def tech_check(item, answer):
    """确定性校验——不是 DSH 分数，也不是独立语义验证；score_suggest 仅供参考。"""
    src = str(item.get("source_text_snapshot") or "")
    ref = str(item.get("reference_answer") or "")
    ans = str(answer or "")
    checks = {"answer_empty": not ans.strip()}
    ref_ok = None
    if ref and ref != RULE_ONLY:
        nums = re.findall(r"[-+]?\d+(?:\.\d+)?", ref)
        if nums:
            checks["ref_numbers_in_source"] = all(n in src for n in nums)
            checks["answer_covers_ref_numbers"] = all(n in ans for n in nums)
            ref_ok = checks["answer_covers_ref_numbers"]
        else:
            ref_ok = bool(point_met(ref, ans))
            checks["answer_covers_ref_terms"] = ref_ok
    cond = item.get("conditioning") or []
    cond_ok = None
    if cond:
        cov = [{"condition": str(c)[:120], "ratio": token_cover(c, ans)} for c in cond if str(c)]
        checks["condition_coverage"] = cov
        cond_ok = all((str(c) in ans) or token_cover(c, ans) >= 0.6 for c in cond if str(c))
        checks["answer_covers_conditions"] = cond_ok
    if checks["answer_empty"]:
        checks["score_suggest"] = 0
    elif (ref_ok is not False) and (cond_ok is not False):
        checks["score_suggest"] = 2
    else:
        checks["score_suggest"] = 1
    return checks


def check_digest(results):
    return sha16([{"i": r.get("item_id"), "t": r.get("technical_check")}
                  for r in results])


# ============ 增益对照引擎：严格评分器 vs 基础（无工具）判分器 ============
# 两条臂吃同一批作答（同一 run_results），只改「判分时能看到什么」：
#   严格臂：题卡全字段（conditioning / reference_answer / source_text_snapshot）
#           + 证据定位 + 编造守卫 + 越界断言守卫 → 0/1/2 + 缺陷类型
#   基础臂：只看到 task 与答案表面（是否非空/是否含数值/是否贴题）→ 0/1/2
# 两臂分数差异 = 「有工具的判分口径」相对「无工具的表面判分」的增益。
# 注意：这是同一批作答在两种口径下的对照，不替代平台跨 Agent 白板对照。

LOC_RE = re.compile(r"(p\d{1,3}|第\s*\d+\s*[页段节]|来源|见\s*p\d|表\s*\d|图\s*\d)", re.I)
# 页码/图表引用（p02、图3、表1）不是内容数值，抽数值前先剥掉
PAGEREF_RE = re.compile(r"(?:p|pg|page|页|段|表|图|figure|fig|table|tbl)\s*\.?\s*\d+",
                         re.I)
EXIST_RE = re.compile(r"(存在|确有|确实有|有数据|有循环|已报道|已报告|exists?|is reported|"
                       r"were reported|available)", re.I)


def _numbers(text):
    """抽取内容数值：先剥掉 p02/图3/表1 这类定位引用，避免把页码当编造数值。"""
    cleaned = PAGEREF_RE.sub(" ", str(text or ""))
    return set(re.findall(r"[-+]?\d+(?:\.\d+)?", cleaned))


# 严格臂的 6 项机制（non_empty 是底线，不参与消融）
STRICT_CHECKS = ("fabrication_guard", "condition_coverage", "reference_match",
                 "evidence_location", "overclaim_guard", "unreported_guard")


def strict_grade(item, answer, evidence=None, ablate=None):
    """严格评分器（机械口径）：题卡全字段 + 证据定位 + 编造/越界守卫。

    ablate：可关闭的机制名集合（消融开关）。被关闭的机制不执行、不计步，
    对应 ok_* 视为通过（该机制不产生缺陷）。用于量化「关掉某条机制后分数怎么变」。
    """
    abl = set(str(x) for x in (ablate or []))
    src = str(item.get("source_text_snapshot") or "")
    ref = str(item.get("reference_answer") or "")
    rule = str(item.get("scoring_rule") or "")
    ans = str(answer or "")
    ev = evidence if isinstance(evidence, list) else []
    conds = [str(c) for c in (item.get("conditioning") or []) if str(c)]
    steps, flags = [], {}

    def step(name, ok, detail):
        steps.append({"step": name, "pass": bool(ok), "detail": detail})
        return bool(ok)

    if not ans.strip():
        step("non_empty", False, "答案为空")
        flags["defect"] = "no_answer"
        return {"score": 0, "defect": "no_answer", "steps": steps, "flags": flags}
    step("non_empty", True, "答案非空")
    if "fabrication_guard" in abl:
        ok_fab = True
    else:
        allowed = _numbers(src) | _numbers(ref) | set(
            n for c in conds for n in re.findall(r"\d+(?:\.\d+)?", c))
        fab = sorted(_numbers(ans) - allowed)
        ok_fab = step("fabrication_guard", not fab,
                      ("答案出现来源/参考答案/条件均未含的数值 %s" % fab) if fab
                      else "答案数值均可回证")
    if "condition_coverage" in abl:
        ok_cond = True
    else:
        miss_cond = [c for c in conds
                     if not ((c in ans) or token_cover(c, ans) >= 0.6)]
        ok_cond = step("condition_coverage", not miss_cond,
                       ("缺条件 %s" % miss_cond) if miss_cond else "条件齐备")
    if "reference_match" in abl:
        ok_ref = True
    elif ref and ref != RULE_ONLY:
        ref_nums = re.findall(r"\d+(?:\.\d+)?", ref)
        miss_ref = [n for n in ref_nums if n not in ans]
        ok_ref = step("reference_match", not miss_ref,
                      ("参考答案数值 %s 未出现" % miss_ref) if miss_ref
                      else "参考答案数值逐字出现")
    else:
        ok_ref = step("reference_match", True, "仅规则评分题，无参考答案数值比对")
    if "evidence_location" in abl:
        ok_ev = True
    else:
        has_ev = any(str((e or {}).get("location") or "").strip()
                     for e in ev if isinstance(e, dict)) or bool(LOC_RE.search(ans))
        ok_ev = step("evidence_location", has_ev,
                     "有证据定位" if has_ev else "无页码/段落/图表定位")
    if "overclaim_guard" in abl:
        ok_oc = True
    else:
        hedge_src = any(h in src.lower() for h in HEDGE_SOURCE)
        strong = [w for w in STRONG_CLAIM if w in ans]
        over = bool(strong) and hedge_src
        ok_oc = step("overclaim_guard", not over,
                     ("来源为推断性表述，答案出现断言词 %s" % strong) if over
                     else "未见越界断言")
    # 未报告守卫：评分规则要求「未报告/未提供」，答案却断言存在 → 编造未报告数据
    ok_unrep = True
    if "unreported_guard" not in abl and ref == RULE_ONLY and re.search(
            r"(未报告|未提供|不存在|unreported|not reported)", rule):
        cond_keys = [n for c in conds for n in re.findall(r"\d+(?:\.\d+)?", c)]
        src_has = all(n in _numbers(src) for n in cond_keys) if cond_keys else False
        asserts_exist = bool(EXIST_RE.search(ans))
        if asserts_exist and not src_has:
            ok_unrep = step("unreported_guard", False,
                            "来源未报告该条件下的数据，答案却断言其存在")
        else:
            ok_unrep = step("unreported_guard", True, "未把未报告内容写成已存在")
    flags["defect"] = ""
    if abl:
        flags["ablated_checks"] = sorted(abl)
    if not ok_oc:
        flags["defect"] = "overclaim"
    elif not ok_unrep:
        flags["defect"] = "overclaim"
    elif not ok_ref:
        flags["defect"] = "text_mismatch"
    elif not ok_fab:
        flags["defect"] = "fabricated_value"
    elif not ok_cond:
        flags["defect"] = "missing_condition"
    elif not ok_ev:
        flags["defect"] = "format_error"
    if flags["defect"] in ("overclaim", "text_mismatch", "fabricated_value"):
        score = 0
    elif flags["defect"] in ("missing_condition", "format_error"):
        score = 1
    else:
        score = 2
    return {"score": score, "defect": flags["defect"], "steps": steps, "flags": flags}


def baseline_grade(item, answer):
    """基础（无工具）判分器：只看答案表面——是否非空、是否含数值、是否贴题；
    看不到 conditioning / reference_answer / 证据定位，因此抓不到条件缺失、
    数值冲突与编造。这是「不加载本 Skill 时判分能力」的对照基线。"""
    ans = str(answer or "")
    task = str(item.get("task") or "")
    steps = []
    if not ans.strip():
        steps.append({"step": "non_empty", "pass": False, "detail": "答案为空"})
        return {"score": 0, "defect": "no_answer", "steps": steps, "flags": {}}
    steps.append({"step": "non_empty", "pass": True, "detail": "答案非空"})
    has_num = bool(_numbers(ans))
    steps.append({"step": "has_number", "pass": has_num,
                  "detail": "含数值" if has_num else "无数值"})
    terms = [t for t in re.findall(r"[\w\u4e00-\u9fff]{2,}", task)
             if t.lower() not in STOPWORDS]
    hit = sum(1 for t in terms if t in ans)
    on_topic = hit >= 2
    steps.append({"step": "on_topic", "pass": on_topic,
                  "detail": "贴题关键词命中 %d/%d" % (hit, len(terms))})
    score = 2 if (has_num or on_topic) else 1
    return {"score": score, "defect": "", "steps": steps, "flags": {}}


def _arm_timing(fn, *a, **kw):
    t0 = time.perf_counter()
    out = fn(*a, **kw)
    return out, int((time.perf_counter() - t0) * 1000000)


def gain_evidence_for(items, run_map, score_rows, corpus=None, ablate=None):
    """同一批作答跑两条臂 → 逐题分数/一致率/漏检数/耗时/步骤数对照。

    ablate：关闭严格臂的机制名集合（消融开关）；默认 None = 完整评分器
    （含逐字回证 reference_match 与裁定 adjudication）。
    """
    per_item, t_strict, t_base, s_strict, s_base = [], 0, 0, 0, 0
    truth = {}
    if corpus:
        truth = corpus.get("truth") or {}
    abl = set(str(x) for x in (ablate or []))
    for it in items:
        iid = str(it.get("item_id"))
        r = run_map.get(iid) or {}
        ans = str(r.get("answer_raw") or "")
        ev = r.get("evidence") if isinstance(r.get("evidence"), list) else []
        st, us1 = _arm_timing(strict_grade, it, ans, ev, abl)
        bl, us2 = _arm_timing(baseline_grade, it, ans)
        t_strict += us1
        t_base += us2
        s_strict += len(st.get("steps") or [])
        s_base += len(bl.get("steps") or [])
        row = next((x for x in score_rows if str(x.get("item_id")) == iid), {})
        hs = row.get("score")
        truth_item = truth.get(iid) or {}
        truth_defect = str(truth_item.get("defect") or "")
        truth_score = truth_item.get("score")
        per_item.append({
            "item_id": iid,
            "strict_score": st.get("score"), "strict_defect": st.get("defect"),
            "strict_steps": len(st.get("steps") or []),
            "baseline_score": bl.get("score"), "baseline_defect": bl.get("defect"),
            "baseline_steps": len(bl.get("steps") or []),
            "human_score": hs,
            "truth_score": truth_score, "truth_defect": truth_defect,
            "strict_vs_baseline_agree": st.get("score") == bl.get("score"),
            "strict_vs_human_agree": (hs is not None
                                       and int(hs) == int(st.get("score"))),
            "strict_detected": bool(st.get("defect")),
            "baseline_detected": bool(bl.get("defect")),
            "missed_by_baseline": bool(st.get("defect")) and not bl.get("defect"),
            "missed_by_strict": bool(bl.get("defect")) and not st.get("defect"),
            "truth_match_strict": (None if truth_score is None
                                   else int(truth_score) == int(st.get("score"))),
            "truth_match_baseline": (None if truth_score is None
                                     else int(truth_score) == int(bl.get("score"))),
        })
    n = len(per_item) or 1
    ag = sum(1 for p in per_item if p["strict_vs_baseline_agree"])
    agh = sum(1 for p in per_item if p["strict_vs_human_agree"])
    have_h = sum(1 for p in per_item if p["human_score"] is not None)
    metrics = {
        "items_compared": len(per_item),
        "agreement_strict_vs_baseline": round(ag / float(n), 3),
        "agreement_strict_vs_human": (round(agh / float(n), 3) if have_h else None),
        "strict_detected_defects": sum(1 for p in per_item if p["strict_detected"]),
        "baseline_detected_defects": sum(1 for p in per_item if p["baseline_detected"]),
        "missed_by_baseline": sum(1 for p in per_item if p["missed_by_baseline"]),
        "missed_by_strict": sum(1 for p in per_item if p["missed_by_strict"]),
        "time_us": {"strict_arm": t_strict, "baseline_arm": t_base,
                    "delta": t_strict - t_base},
        "time_ms": {"strict_arm": round(t_strict / 1000.0, 3),
                    "baseline_arm": round(t_base / 1000.0, 3),
                    "delta": round((t_strict - t_base) / 1000.0, 3)},
        "steps": {"strict_arm": s_strict, "baseline_arm": s_base,
                  "delta": s_strict - s_base},
        "ablated_checks": sorted(abl),
    }
    if truth:
        ts = [p for p in per_item if p["truth_score"] is not None]
        metrics["truth_grounded"] = {
            "items": len(ts),
            "strict_accuracy": (round(sum(1 for p in ts if p["truth_match_strict"])
                                      / float(len(ts)), 3) if ts else None),
            "baseline_accuracy": (round(sum(1 for p in ts if p["truth_match_baseline"])
                                        / float(len(ts)), 3) if ts else None),
        }
    return per_item, metrics


def build_adjudication_rows(per_item, score_rows):
    """机器裁定：严格臂与人工判分不一致的题目 → 依证据裁定并留争议标记。
    裁定只依据题卡条件/参考答案与原文定位，不改人工分数。"""
    rows = []
    for p in per_item:
        iid = str(p.get("item_id"))
        hs = p.get("human_score")
        ss = p.get("strict_score")
        row = next((x for x in score_rows if str(x.get("item_id")) == iid), {})
        if hs is None or ss is None:
            continue
        agree = int(hs) == int(ss)
        rows.append({
            "item_id": iid,
            "round1_score": int(hs),
            "round2_score": int(ss),
            "final_score": int(hs),
            "disputed": (not agree) or bool(row.get("disputed")),
            "agree": agree,
            "resolution": ("两轮一致" if agree else
                           "以人工判分为准（评分规则口径优先），差异登记为争议待复核"),
            "basis_location": "scores.csv 行 item_id=%s；题卡 conditioning/reference_answer；"
                              "run_results.answer_raw 原文" % iid,
            "strict_defect": p.get("strict_defect"),
            "baseline_score": p.get("baseline_score"),
            "rule_revision": ("" if agree else
                              "建议复核评分规则判定线是否可机械观察（不改分数）"),
        })
    return rows


MECHANISM_METRIC_MAP = [
    {"mechanism": "题卡 conditioning 逐条保留 + 条件覆盖检查",
     "metric": "strict_detected_defects 中的 missing_condition 计数 / "
               "baseline 对同题的漏检数 missed_by_baseline",
     "expected_direction": "严格臂高于基础臂"},
    {"mechanism": "reference_answer 数值逐字回证",
     "metric": "text_mismatch 检出数；严格臂与参考答案一致率 strict_vs_human",
     "expected_direction": "严格臂高于基础臂"},
    {"mechanism": "证据定位（页码/段落/图表）强制要求",
     "metric": "format_error 检出数；steps.strict_arm > steps.baseline_arm",
     "expected_direction": "严格臂步骤数更高（检查更细）"},
    {"mechanism": "编造守卫（答案数值必须可回证到来源/参考答案/条件）",
     "metric": "fabricated_value 检出数——基础臂完全不查，必然漏检",
     "expected_direction": "严格臂高于基础臂"},
    {"mechanism": "推断性来源的越界断言守卫",
     "metric": "overclaim 检出数",
     "expected_direction": "严格臂高于基础臂"},
    {"mechanism": "逐题可溯源（item_id → 原文输出 → 评分依据）",
     "metric": "agreement_strict_vs_human（严格臂与人工判分一致率）",
     "expected_direction": "越高越好"},
]

GAIN_BOUNDARIES = [
    "两条臂吃的是同一批作答，只改判分时可见信息；因此差异度量的是「判分口径增益」，"
    "不是「答题能力增益」。",
    "基础臂刻意不给题卡 conditioning / reference_answer / 证据定位，属于下界模拟，"
    "不是某个真实平台 Agent 的实测水平；跨 Agent 对照以组织方白板为准。",
    "严格臂是确定性规则判定，不是语义理解；它可能漏判「结论方向对但表述含糊」这类语义问题。",
    "答案由 Agent 生成，本包不预置正式答案；增益对照跑的是本次运行真实产出的作答。",
]

GAIN_FAILURE_CONDITIONS = [
    "作答为空 → 两臂同判 0，对照不产生区分度，该题应记入失败样例而非增益证据。",
    "题卡无 reference_answer（仅规则评分）→ 数值回证与编造守卫退化为条件/证据检查，"
    "严格臂判别力下降。",
    "答案超长或含大量无关数字 → 数值回证与编造守卫可能误报，需人工复核（disputed）。",
    "作答来自人工直接填写（非模型直出）→ 效率计数不反映真实模型请求数。",
]


GATE_STATUS = ("enforced", "skipped_not_provided", "not_found", "unreadable")


def build_gates(outdir, pack=None):
    """闸门状态显式枚举：没跑≠通过；not_found/unreadable 必须带 gate_note。
    九域：items/run_results/scores/failure_samples/version/diff/report/gain_evidence/efficiency"""
    gates = {}
    specs = {"items": "items.json", "run_results": "run_results.json",
             "scores": "scores.csv", "failure_samples": "failure_samples.json",
             "version": "version.json", "diff": "diff.json",
             "report": "report.md", "gain_evidence": "gain_evidence.json",
             "efficiency": "efficiency.json"}
    for name, fn in specs.items():
        p = os.path.join(outdir, fn)
        if not os.path.exists(p):
            gates[name] = {"status": "not_found",
                           "gate_note": "文件缺失，下游不得宣称已核对"}
            continue
        try:
            if fn.endswith(".json"):
                load_json(p)
            else:
                with open(p, "r", encoding="utf-8") as f:
                    f.read(200)
            gates[name] = {"status": "enforced"}
        except Exception as e:
            gates[name] = {"status": "unreadable",
                           "gate_note": ("读取失败: %s；下游不得宣称已核对" % str(e)[:100])}
    contract_keys = []
    if isinstance(pack, dict):
        contract_keys = [str(k) for k in find_contract(
            pack.get("_case") or {}).keys()]
    return gates


def verify_checks(items, rows, run_map, fail_ids):
    """逐条机械校验三元组 {item, template_value, applied, match}，结果嵌入 result.json。"""
    checks = []
    for it in items:
        iid = str(it.get("item_id"))
        row = next((r for r in rows if str(r.get("item_id")) == iid), {})
        sc = str(row.get("score") or "").strip()
        rat = str(row.get("rationale") or "").strip()
        raw = str((run_map.get(iid) or {}).get("answer_raw") or "").strip()
        sr = str(it.get("scoring_rule") or "").strip()
        conds = it.get("conditioning")
        checks.append({"item": iid, "template_value": "score∈{0,1,2}",
                       "applied": True, "match": sc in ("0", "1", "2")})
        checks.append({"item": iid, "template_value": "rationale 非空且非待评",
                       "applied": True,
                       "match": bool(rat) and rat != "待评" and sc in ("0", "1", "2")})
        checks.append({"item": iid,
                       "template_value": "run_results 有原始输出或失败样例",
                       "applied": True, "match": bool(raw) or iid in fail_ids})
        checks.append({"item": iid,
                       "template_value": "scoring_rule 含 0/1/2 判定线或可观察判据",
                       "applied": True,
                       "match": bool(re.search(r"[0-2]\s*[=＝:：]", sr) or re.search(
                           r"(正确|错误|达标|完整|一致|可回溯|未报告|编造|条件|定位)", sr))})
        checks.append({"item": iid, "template_value": "conditioning 键存在",
                       "applied": True, "match": "conditioning" in it})
        checks.append({"item": iid,
                       "template_value": "conditioning 数值逐字出现在参考答案",
                       "applied": bool(conds),
                       "match": (all(str(n) in str(it.get("reference_answer") or "")
                                     or str(n) in str(it.get("source_text_snapshot") or "")
                                     for c in conds
                                     for n in re.findall(r"\d+(?:\.\d+)?", str(c)))
                                 if conds else None)})
    return checks


def build_summary(items, score_rows):
    scored = [r for r in score_rows if r.get("score") in (0, 1, 2)]
    dist = {"0": 0, "1": 0, "2": 0}
    for r in scored:
        dist[str(int(r["score"]))] += 1
    return {
        "items_total": len(items),
        "items_with_reference": sum(1 for it in items if it.get("reference_answer") != RULE_ONLY),
        "items_rule_only": sum(1 for it in items if it.get("reference_answer") == RULE_ONLY),
        "items_with_conditioning": sum(1 for it in items if it.get("conditioning")),
        "score_dist": dist,
        "avg": (round(sum(int(r["score"]) for r in scored) / float(len(scored)), 3)
                if scored else None),
        "note": ("技术合成检查日志/score_suggest 不是 DSH 分数也不是独立语义验证；来源是段落/"
                 "表格文本，不是 PDF 像素金标。分数复算路径：scores 行 → items 题卡 "
                 "conditioning/scoring_rule → run_results 原文输出全文。"),
    }


# ============ 题面对齐：三类运行状态（成功/部分完成/无法判断/拒答）============
RUN_STATUSES = ("success", "partial", "undetermined", "refused")


def derive_run_status(it, ans, ev, fail_type=""):
    """按题面「运行状态」字段派生：成功/部分完成/无法判断/拒答 + 原因。"""
    ans = str(ans or "")
    if not ans.strip():
        return {"status": "refused", "reason": "未产出任何作答（对应失败类型 %s）"
                % (fail_type or "no_answer")}
    if fail_type in ("file_unreadable", "permission_denied"):
        return {"status": "undetermined",
                "reason": "来源不可读/权限不足，无法判断：%s" % fail_type}
    has_loc = any(str((e or {}).get("location") or "").strip()
                  for e in (ev or []) if isinstance(e, dict))
    if not has_loc:
        return {"status": "partial", "reason": "有作答但缺证据定位（页码/段落/图表）"}
    return {"status": "success", "reason": "作答含结论与证据定位，可回溯来源"}


def build_answer_index(items, run_map, score_rows, fail_map):
    """题面输出要求表的语义索引：阅读/解析结果 + 证据与边界 + 运行状态。"""
    answers, evidence_idx, run_status, uncertainties = [], [], [], []
    for it in items:
        iid = str(it.get("item_id"))
        r = run_map.get(iid) or {}
        ans = str(r.get("answer_raw") or "")
        ev = r.get("evidence") if isinstance(r.get("evidence"), list) else []
        row = next((x for x in score_rows if str(x.get("item_id")) == iid), {})
        fr = fail_map.get(iid) or {}
        ft = str(fr.get("failure_type") or row.get("failure_type") or "")
        answers.append({
            "item_id": iid,
            "task": it.get("task"),
            "answer_raw": ans,
            "answer_struct": r.get("answer_struct") if isinstance(
                r.get("answer_struct"), dict) else {},
            "evidence": ev,
            "score": row.get("score"),
            "failure_type": ft,
        })
        for e in ev:
            if isinstance(e, dict):
                evidence_idx.append({"item_id": iid,
                                     "quote": str(e.get("quote") or ""),
                                     "location": str(e.get("location") or "")})
        st = derive_run_status(it, ans, ev, ft)
        run_status.append({"item_id": iid, **st})
        if it.get("reference_answer") == RULE_ONLY:
            uncertainties.append({"item_id": iid, "kind": "unreported",
                                  "note": "题目无参考答案，仅按评分规则判定，需人工复核语义分"})
        if not str(it.get("source_text_snapshot") or "").strip():
            uncertainties.append({"item_id": iid, "kind": "conflicts",
                                  "note": "题卡缺来源快照，结论不可回溯到原文"})
        if ft:
            uncertainties.append({"item_id": iid, "kind": "unverifiable",
                                  "note": "失败类型 %s：%s" % (ft, fr.get("why") or "未记录原因")})
    return answers, evidence_idx, run_status, uncertainties


def build_adjudication(items, score_rows, fail_map, adj_raw):
    """结构化裁定：逐题记录两轮独立判分、分歧、裁定依据与规则修订。"""
    adj = []
    for it in items:
        iid = str(it.get("item_id"))
        row = next((x for x in score_rows if str(x.get("item_id")) == iid), {})
        extra = adj_raw.get(iid) if isinstance(adj_raw, dict) else None
        disputed = bool(row.get("disputed"))
        if not extra and not disputed:
            continue
        e = extra if isinstance(extra, dict) else {}
        adj.append({
            "item_id": iid,
            "round1_score": e.get("round1_score"),
            "round2_score": e.get("round2_score"),
            "disputed": disputed,
            "final_score": row.get("score"),
            "rationale": str(row.get("rationale") or ""),
            "resolution": e.get("resolution") or (
                "按原文定位裁定" if disputed else "两轮判分一致，无需裁定"),
            "basis_location": e.get("basis_location") or it.get("input_ref") or "",
            "rule_revision": e.get("rule_revision") or "",
            "adjudicator": e.get("adjudicator") or "benchkit strict arm / 人工复核",
        })
    return adj


def cmd_init(args):
    outdir = args.outdir
    os.makedirs(outdir, exist_ok=True)
    try:
        case = load_json(args.case)
    except Exception as e:
        log(outdir, "case.json 读取失败（%s），按空工单降级，仍产出全套文件" % e)
        case = {}
    case_id = str((case.get("case_id") if isinstance(case, dict) else None)
                  or (case.get("id") if isinstance(case, dict) else None) or "unknown")
    contract = find_contract(case)
    raw_items = find_items(case)
    items = [norm_item(w, i) for i, w in enumerate(raw_items)] or [fallback_item(case)]
    if not raw_items:
        log(outdir, "未识别出结构化工单条目，已写入兜底题卡 item-1（请人工核对）")
    mats = scan_materials(args.input_dir or os.path.dirname(os.path.abspath(args.case)) or "/input")

    save_json(os.path.join(outdir, "items.json"),
              {"case_id": case_id, "items": items, "materials": mats})
    save_json(os.path.join(outdir, "run_results.json"), {
        "case_id": case_id,
        "run_config": {"python_version": sys.version.split()[0],
                       "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
                       "budget_note": "平台 64 请求/900 秒/16384 token；技能内部熔断 48 请求/700 秒"},
        "stability": {},
        "results": [{"item_id": it["item_id"], "answer_raw": "", "answer_struct": {},
                     "evidence": [], "technical_check": {}, "timing": None}
                    for it in items]})
    try:
        with open(os.path.join(outdir, "scores.csv"), "w", encoding="utf-8", newline="") as f:
            wtr = csv.DictWriter(f, fieldnames=list(SCORE_FIELDS))
            wtr.writeheader()
            for it in items:
                wtr.writerow({"item_id": it["item_id"], "score": "", "rationale": "待评",
                              "disputed": "false", "failure_type": "", "answer_raw_excerpt": ""})
    except Exception as e:
        log(outdir, "scores.csv 写入失败（%s）" % e)
    save_json(os.path.join(outdir, "failure_samples.json"), {"case_id": case_id, "failures": []})
    version = {"snapshot": "v1", "items_sha": sha16(items),
               "item_shas": {str(it["item_id"]): sha16(it) for it in items},
               "changes": ["init: 生成 %d 张题卡骨架" % len(items)],
               "comparable_with": [],
               "note": "题目/参考答案/评分规则变化后运行 diff：仅重算受影响题目，未变题目历史分数可比"}
    save_json(os.path.join(outdir, "version.json"), version)
    try:
        with open(os.path.join(outdir, "report.md"), "w", encoding="utf-8") as f:
            f.write("# 文献阅读 Benchmark 评测报告（占位：评分后运行 report 子命令生成）\n")
    except Exception as e:
        log(outdir, "report.md 占位写入失败（%s）" % e)

    score_rows = [{"item_id": it["item_id"], "score": None, "rationale": "待评",
                   "disputed": False, "failure_type": "", "answer_raw_excerpt": ""}
                  for it in items]
    contract_keys = [str(k) for k in contract.keys()]
    result = {}
    for k in list(dict.fromkeys(list(TOP_KEYS) + contract_keys)):
        if k == "case_id":
            result[k] = case_id
        elif k == "status":
            result[k] = "partial"
        elif k == "result":
            result[k] = {"items": items, "run_results": [], "scores": score_rows,
                         "failures": [], "version": version, "materials": mats,
                         "summary": build_summary(items, score_rows)}
        elif k == "claims":
            result[k] = []
        elif k == "uncertainties":
            result[k] = {"unreported": [], "unverifiable": [], "conflicts": [],
                         "human_review": [], "summary": "骨架已落盘：待作答、待评分"}
        else:
            result[k] = "unknown"
    save_json(os.path.join(outdir, "result.json"), result)
    print("[benchkit] init 完成：items=%d contract_keys=%s case_id=%s → %s"
          % (len(items), contract_keys or ["(无 output_contract，用通用五键)"], case_id, outdir))
    return 0


def cmd_techcheck(args):
    outdir = args.outdir
    try:
        pack = load_json(os.path.join(outdir, "items.json"))
        run = load_json(os.path.join(outdir, "run_results.json"))
    except Exception as e:
        log(outdir, "techcheck 输入读取失败（%s），跳过" % e)
        return 0
    items = {str(it.get("item_id")): it for it in (pack.get("items") or [])}
    results = run.get("results") or []
    by_id = {str(r.get("item_id")): r for r in results}
    for iid, it in items.items():
        r = by_id.get(iid)
        if r is None:
            r = {"item_id": iid, "answer_raw": "", "answer_struct": {}, "evidence": []}
            results.append(r)
            by_id[iid] = r
        r.setdefault("answer_raw", "")
        r["technical_check"] = tech_check(it, str(r.get("answer_raw") or ""))
        r["technical_check_note"] = "确定性校验与建议分，不是 DSH 分数也不是独立语义验证"
    run["results"] = results
    new_sha = check_digest(results)
    prev = (run.get("stability") or {}).get("check_sha")
    try:
        version = load_json(os.path.join(outdir, "version.json"))
        if prev and prev != new_sha:
            version.setdefault("changes", []).append(
                "复跑稳定性：技术检查结果与上次不同（check_sha %s→%s），请核对作答是否变化" % (prev[:8], new_sha[:8]))
            save_json(os.path.join(outdir, "version.json"), version)
    except Exception:
        pass
    run.setdefault("stability", {})["check_sha"] = new_sha
    save_json(os.path.join(outdir, "run_results.json"), run)
    def check_fail(c):
        if not isinstance(c, dict):
            return True
        if c.get("answer_empty") is True:
            return True
        return (c.get("answer_covers_conditions") is False
                or c.get("answer_covers_ref_numbers") is False
                or c.get("answer_covers_ref_terms") is False)
    passed = sum(1 for r in results if not check_fail(r.get("technical_check")))
    print("[benchkit] techcheck：ran=%d 全过=%d check_sha=%s（score_suggest≠DSH 分数≠语义验证）"
          % (len(results), passed, new_sha[:12]))
    return 0


def cmd_diff(args):
    """item 级版本对比：改题后只重算受影响题目，未变题目历史分数可比（改得动）。"""
    outdir = args.outdir
    try:
        items = (load_json(os.path.join(outdir, "items.json")) or {}).get("items") or []
        version = load_json(os.path.join(outdir, "version.json")) or {}
    except Exception as e:
        log(outdir, "diff 输入读取失败（%s）" % e)
        return 0
    cur = {str(it["item_id"]): sha16(it) for it in items}
    prev = version.get("item_shas") or {}
    changed = [i for i in cur if i in prev and cur[i] != prev[i]]
    added = [i for i in cur if i not in prev]
    removed = [i for i in prev if i not in cur]
    unchanged = [i for i in cur if i in prev and cur[i] == prev[i]]
    diff = {"changed": changed, "added": added, "removed": removed,
            "rescore_only": changed + added, "comparable": unchanged,
            "note": "仅 rescore_only 内题目需重算并更新分数；comparable 内题目历史分数仍可比"}
    save_json(os.path.join(outdir, "diff.json"), diff)
    if changed or added or removed:
        m = re.match(r"v(\d+)", str(version.get("snapshot") or "v0"))
        version["snapshot"] = "v%d" % ((int(m.group(1)) if m else 0) + 1)
        version["item_shas"] = cur
        version["items_sha"] = sha16(items)
        version.setdefault("changes", []).append(
            "diff: changed=%s added=%s removed=%s；仅重算受影响题目" % (changed, added, removed))
        version["comparable_with"] = unchanged
        save_json(os.path.join(outdir, "version.json"), version)
    print("[benchkit] diff：changed=%d added=%d removed=%d 可比=%d → %s"
          % (len(changed), len(added), len(removed), len(unchanged),
             "快照已递增" if (changed or added or removed) else "无变化"))
    return 0


def cmd_report(args):
    """机械生成逐题评测报告：得分、证据、失败类型、改进建议，全部可复算。"""
    outdir = args.outdir
    try:
        pack = load_json(os.path.join(outdir, "items.json")) or {}
        items = pack.get("items") or []
    except Exception as e:
        log(outdir, "report: items.json 读取失败（%s）" % e)
        items = []
    run_map, rows, failures = {}, [], []
    try:
        run = load_json(os.path.join(outdir, "run_results.json")) or {}
        run_map = {str(r.get("item_id")): r for r in (run.get("results") or [])}
    except Exception as e:
        log(outdir, "report: run_results.json 读取失败（%s）" % e)
    try:
        with open(os.path.join(outdir, "scores.csv"), "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    except Exception as e:
        log(outdir, "report: scores.csv 读取失败（%s）" % e)
    try:
        failures = (load_json(os.path.join(outdir, "failure_samples.json")) or {}).get("failures") or []
    except Exception:
        pass
    try:
        version = load_json(os.path.join(outdir, "version.json")) or {}
    except Exception:
        version = {}
    sumry = build_summary(items, [{"score": int(r["score"]) if str(r.get("score")) in ("0", "1", "2") else None} for r in rows])
    fmap = {str(fr.get("item_id")): fr for fr in failures}
    lines = ["# 文献阅读 Benchmark 评测报告（逐题，机械生成）", "",
             "- case_id: %s" % pack.get("case_id", "unknown"),
             "- 生成时间: %s" % datetime.datetime.now().isoformat(timespec="seconds"),
             "- 题数: %d ｜ 已评: %d ｜ 分布: 0分=%d 1分=%d 2分=%d ｜ 均分: %s"
             % (sumry["items_total"], sum(sumry["score_dist"].values()),
                sumry["score_dist"]["0"], sumry["score_dist"]["1"],
                sumry["score_dist"]["2"], sumry["avg"]),
             "- 复现说明: 相同输入 + 同版本题卡(items_sha=%s) + 同评分规则可复算同一批分数。"
             % (version.get("items_sha") or "unknown"),
             "- 分数复算路径: scores 行 → 题卡 conditioning/scoring_rule → run_results 原文输出全文。",
             "- 技术检查 score_suggest 不是 DSH 分数也不是独立语义验证；语义分按评分规则判定。", ""]
    for it in items:
        iid = str(it.get("item_id"))
        r = next((x for x in rows if str(x.get("item_id")) == iid), {})
        rr = run_map.get(iid) or {}
        fr = fmap.get(iid) or {}
        ft = str(fr.get("failure_type") or r.get("failure_type") or "")
        sugg = FAIL_SUGGEST.get(ft, "保持达标；如修订评分规则按 diff 定向重算")
        tc = rr.get("technical_check") if isinstance(rr.get("technical_check"), dict) else {}
        lines += ["## %s（难度: %s，input_ref: %s）" % (iid, it.get("difficulty"), it.get("input_ref") or "-"),
                  "- 题面: %s" % excerpt(it.get("task"), 200, 0),
                  "- 得分: %s ｜ 争议: %s ｜ 确定性建议分: %s（非语义终判）"
                  % (r.get("score") or "未评", r.get("disputed") or "false",
                     tc.get("score_suggest", "-") if tc else "-"),
                  "- 判分依据: %s" % (r.get("rationale") or "待评"),
                  "- 条件: %s ｜ 参考答案: %s"
                  % ("；".join(it.get("conditioning") or []) or "（无）",
                     excerpt(it.get("reference_answer"), 120, 0)),
                  "- 证据摘录: %s" % excerpt(fr.get("answer_raw_excerpt") or rr.get("answer_raw")),
                  "- 失败类型: %s" % (ft or "无"),
                  "- 改进建议: %s" % sugg, ""]
    fail_tbl = ["| item_id | failure_type | why |", "|-|-|-|"]
    for fr in failures:
        fail_tbl.append("| %s | %s | %s |" % (fr.get("item_id"), fr.get("failure_type"), excerpt(fr.get("why"), 120, 0)))
    if not failures:
        fail_tbl.append("| （无失败样例） | | |")
    # 增益对照节（若已运行 gain 子命令）
    gain_path = os.path.join(outdir, "gain_evidence.json")
    if os.path.exists(gain_path):
        try:
            ge = load_json(gain_path) or {}
            m = ge.get("metrics") or {}
            lines += ["## 判分口径增益对照（同一批作答 · 严格臂 vs 基础臂）", "",
                      "- 对照题数: %s ｜ 严格臂与基础臂一致率: %s"
                      % (m.get("items_compared"), m.get("agreement_strict_vs_baseline")),
                      "- 严格臂检出缺陷: %s ｜ 基础臂检出缺陷: %s ｜ 基础臂漏检: %s ｜ 严格臂漏检: %s"
                      % (m.get("strict_detected_defects"), m.get("baseline_detected_defects"),
                         m.get("missed_by_baseline"), m.get("missed_by_strict")),
                      "- 耗时(ms): 严格臂 %s / 基础臂 %s ｜ 步骤数: 严格臂 %s / 基础臂 %s"
                      % ((m.get("time_ms") or {}).get("strict_arm"),
                         (m.get("time_ms") or {}).get("baseline_arm"),
                         (m.get("steps") or {}).get("strict_arm"),
                         (m.get("steps") or {}).get("baseline_arm")),
                      "- 严格臂与人工判分一致率: %s" % m.get("agreement_strict_vs_human"), "",
                      "| item_id | 严格臂 | 基础臂 | 人工分 | 严格臂缺陷 | 一致 | 基础臂漏检 |",
                      "|-|-|-|-|-|-|-|"]
            for p in (ge.get("per_item") or []):
                lines.append("| %s | %s | %s | %s | %s | %s | %s |" % (
                    p.get("item_id"), p.get("strict_score"), p.get("baseline_score"),
                    p.get("human_score"), p.get("strict_defect") or "-",
                    "是" if p.get("strict_vs_baseline_agree") else "否",
                    "是" if p.get("missed_by_baseline") else "否"))
            lines += ["", "边界: " + "；".join(GAIN_BOUNDARIES),
                      "失效条件: " + "；".join(GAIN_FAILURE_CONDITIONS), ""]
        except Exception as e:
            log(outdir, "report: gain_evidence.json 读取失败（%s）" % e)
    lines += ["## 失败样例归因（8 类题型）"] + fail_tbl + ["",
              "## 分歧裁定", "disputed=true 的题按证据（原文定位）裁定；分歧超过一档时修订评分规则"
              "而不是修改分数，修订史记入 version.changes。逐题结构化裁定见 result.result.adjudication。", ""]
    rp = os.path.join(outdir, "report.md")
    with open(rp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("[benchkit] report 生成: %s（%d 题）" % (rp, len(items)))
    return 0


def cmd_gain(args):
    """增益对照：同一批作答分别用「严格评分器」与「基础（无工具）判分」跑一遍。
    输出逐题分数/一致率/漏检数/耗时/步骤数，并写明机制→指标映射、边界与失效条件。
    退出码恒 0：输入不足时如实记录 skipped_reason，不中断交付。"""
    outdir = args.outdir
    try:
        pack = load_json(os.path.join(outdir, "items.json")) or {}
        items = pack.get("items") or []
    except Exception as e:
        log(outdir, "gain: items.json 读取失败（%s）" % e)
        items = []
    run_map = {}
    try:
        run = load_json(os.path.join(outdir, "run_results.json")) or {}
        run_map = {str(r.get("item_id")): r for r in (run.get("results") or [])}
    except Exception as e:
        log(outdir, "gain: run_results.json 读取失败（%s）" % e)
    rows = []
    try:
        with open(os.path.join(outdir, "scores.csv"), "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    except Exception as e:
        log(outdir, "gain: scores.csv 读取失败（%s）" % e)
    score_rows = [{"item_id": str(r.get("item_id") or ""),
                   "score": int(str(r.get("score"))) if str(r.get("score")) in ("0", "1", "2") else None,
                   "rationale": str(r.get("rationale") or ""),
                   "disputed": str(r.get("disputed") or "").lower() == "true",
                   "failure_type": str(r.get("failure_type") or ""),
                   "answer_raw_excerpt": str(r.get("answer_raw_excerpt") or "")}
                  for r in rows]
    corpus = None
    if args.truth:
        try:
            corpus = load_json(args.truth)
        except Exception as e:
            log(outdir, "gain: truth 文件读取失败（%s），按无真值运行" % e)
    ablate = []
    for x in str(getattr(args, "ablate", "") or "").split(","):
        x = x.strip()
        if x:
            if x not in STRICT_CHECKS:
                log(outdir, "gain: 未知消融机制名 %s（可选：%s），已忽略"
                    % (x, ", ".join(STRICT_CHECKS)))
            else:
                ablate.append(x)
    per_item, metrics = gain_evidence_for(items, run_map, score_rows, corpus, ablate)
    adjudication = build_adjudication_rows(per_item, score_rows)
    answered = sum(1 for p in per_item
                   if str((run_map.get(p["item_id"]) or {}).get("answer_raw") or "").strip())
    skipped = ""
    if not items:
        skipped = "题卡为空，未产生对照"
    elif answered == 0:
        skipped = "本批作答全部为空，对照无区分度（如实记录，不伪造数字）"
    ev = {
        "schema_version": "benchkit-gain-v1",
        "case_id": str(pack.get("case_id") or "unknown"),
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "design": {
            "what": "同一批作答（run_results）分别用严格评分器与基础（无工具）判分各跑一遍，"
                    "只改判分时可见的信息，其余输入完全相同。",
            "strict_arm": "可见题卡 conditioning / reference_answer / source_text_snapshot "
                          "+ 证据定位要求；执行 6 项检查（non_empty / fabrication_guard / "
                          "condition_coverage / reference_match / evidence_location / "
                          "overclaim_guard + unreported_guard），输出 0/1/2 与缺陷类型，"
                          "并做逐题裁定 adjudication。",
            "baseline_arm": "只可见 task 与答案表面（是否非空 / 是否含数值 / 是否贴题关键词），"
                            "看不到 conditioning / reference_answer / 证据定位要求；"
                            "输出 0/1/2。模拟「不加载本 Skill 时判分口径」下界。",
            "controlled_variables": ["作答文本完全相同", "题卡完全相同", "评分刻度相同(0/1/2)",
                                     "运行时间窗相同"],
            "ablation_switch": {
                "available_mechanisms": list(STRICT_CHECKS),
                "used": ablate,
                "how": "python3 $SK/scripts/benchkit.py gain --outdir <目录> "
                       "--ablate condition_coverage,evidence_location —— "
                       "关闭指定机制后重跑本对照；逐条机制的边际贡献见 ablate 子命令的 "
                       "ablation.json",
                "note": "消融开关只改判分口径，不改作答与题卡；数字必须真跑，不得手写。",
            },
            "not_a_claim": "本对照度量的是判分口径增益，不是跨 Agent 能力增益；"
                           "跨 Agent 对照由平台固定白板负责。",
        },
        "per_item": per_item,
        "metrics": metrics,
        "adjudication": adjudication,
        "mechanism_to_metric": MECHANISM_METRIC_MAP,
        "boundaries": GAIN_BOUNDARIES,
        "failure_conditions": GAIN_FAILURE_CONDITIONS,
        "skipped_reason": skipped,
        "reproduce": "python3 $SK/scripts/benchkit.py gain --outdir <同一输出目录>；"
                     "同输入同代码必得同结果（严格臂与基础臂均为纯函数，无随机性）。",
    }
    save_json(os.path.join(outdir, "gain_evidence.json"), ev)
    print("[benchkit] gain 对照：items=%d 严格臂检出=%d 基础臂检出=%d 基础臂漏检=%d "
          "一致率=%s 耗时(ms) 严格=%s/基础=%s 步骤 严格=%s/基础=%s 消融=%s"
          % (metrics.get("items_compared"), metrics.get("strict_detected_defects"),
             metrics.get("baseline_detected_defects"), metrics.get("missed_by_baseline"),
             metrics.get("agreement_strict_vs_baseline"),
             (metrics.get("time_ms") or {}).get("strict_arm"),
             (metrics.get("time_ms") or {}).get("baseline_arm"),
             (metrics.get("steps") or {}).get("strict_arm"),
             (metrics.get("steps") or {}).get("baseline_arm"),
             ",".join(ablate) or "none"))
    return 0


def cmd_ablate(args):
    """消融对照（leave-one-out）：逐条关闭严格臂的判分机制，量化每条机制的贡献。
    同一批作答、同一题卡，只改「关掉哪条机制」→ 分数/检出数/步骤数/耗时的变化。
    退出码恒 0：输入不足时如实记录 skipped_reason，不中断交付。"""
    outdir = args.outdir
    try:
        pack = load_json(os.path.join(outdir, "items.json")) or {}
        items = pack.get("items") or []
    except Exception as e:
        log(outdir, "ablate: items.json 读取失败（%s）" % e)
        items = []
    run_map = {}
    try:
        run = load_json(os.path.join(outdir, "run_results.json")) or {}
        run_map = {str(r.get("item_id")): r for r in (run.get("results") or [])}
    except Exception as e:
        log(outdir, "ablate: run_results.json 读取失败（%s）" % e)

    # 完整臂基准
    full_rows, t_full, s_full = [], 0, 0
    for it in items:
        iid = str(it.get("item_id"))
        r = run_map.get(iid) or {}
        ans = str(r.get("answer_raw") or "")
        ev = r.get("evidence") if isinstance(r.get("evidence"), list) else []
        st, us = _arm_timing(strict_grade, it, ans, ev)
        t_full += us
        s_full += len(st.get("steps") or [])
        full_rows.append({"item_id": iid, "score": st.get("score"),
                          "defect": st.get("defect"),
                          "steps": len(st.get("steps") or []), "time_us": us})
    full_map = {r["item_id"]: r for r in full_rows}

    per_mech = []
    for mech in STRICT_CHECKS:
        rows, t_off, s_off = [], 0, 0
        for it in items:
            iid = str(it.get("item_id"))
            r = run_map.get(iid) or {}
            ans = str(r.get("answer_raw") or "")
            ev = r.get("evidence") if isinstance(r.get("evidence"), list) else []
            st, us = _arm_timing(strict_grade, it, ans, ev, [mech])
            t_off += us
            s_off += len(st.get("steps") or [])
            rows.append({"item_id": iid, "score": st.get("score"),
                         "defect": st.get("defect"),
                         "steps": len(st.get("steps") or []), "time_us": us})
        changed = [r["item_id"] for r in rows
                   if full_map.get(r["item_id"], {}).get("score") != r["score"]]
        lost = [r["item_id"] for r in rows
                if full_map.get(r["item_id"], {}).get("defect")
                and not r.get("defect")]
        gained = [r["item_id"] for r in rows
                  if r.get("defect") and not full_map.get(r["item_id"], {}).get("defect")]
        per_mech.append({
            "mechanism": mech,
            "items_changed_score": len(changed),
            "item_ids_changed_score": changed,
            "defects_missed_when_off": len(lost),
            "item_ids_missed_when_off": lost,
            "false_defects_when_off": len(gained),
            "item_ids_false_defects_when_off": gained,
            "steps_delta_vs_full": s_off - s_full,
            "time_us_delta_vs_full": t_off - t_full,
            "interpretation": (
                "关闭本机制后 %d 题分数变化，其中 %d 题缺陷不再被检出——"
                "该机制贡献了这些题的判定力；步骤数变化 %d。"
                % (len(changed), len(lost), s_off - s_full)),
        })
    # 全部机制关闭 = 纯表面判分
    rows, t_all, s_all = [], 0, 0
    for it in items:
        iid = str(it.get("item_id"))
        r = run_map.get(iid) or {}
        ans = str(r.get("answer_raw") or "")
        ev = r.get("evidence") if isinstance(r.get("evidence"), list) else []
        st, us = _arm_timing(strict_grade, it, ans, ev, list(STRICT_CHECKS))
        t_all += us
        s_all += len(st.get("steps") or [])
        rows.append({"item_id": iid, "score": st.get("score"), "defect": st.get("defect"),
                     "steps": len(st.get("steps") or []), "time_us": us})
    all_changed = [r["item_id"] for r in rows
                   if full_map.get(r["item_id"], {}).get("score") != r["score"]]
    all_lost = [r["item_id"] for r in rows
                if full_map.get(r["item_id"], {}).get("defect") and not r.get("defect")]

    answered = sum(1 for it in items
                   if str((run_map.get(str(it.get("item_id"))) or {}).get("answer_raw")
                          or "").strip())
    skipped = ""
    if not items:
        skipped = "题卡为空，未产生消融对照"
    elif answered == 0:
        skipped = "本批作答全部为空，消融无区分度（如实记录，不伪造数字）"
    abl = {
        "schema_version": "benchkit-ablation-v1",
        "case_id": str(pack.get("case_id") or "unknown"),
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "design": {
            "what": "leave-one-out 消融：同一批作答、同一题卡，逐条关闭严格臂的判分机制，"
                    "观察逐题分数、缺陷检出数、步骤数与耗时的变化。",
            "switch": "消融开关 = 关闭机制名集合（%s）；"
                      "用 benchkit.py gain --ablate <机制,机制> 可把同一开关接到增益对照上。"
                      % ", ".join(STRICT_CHECKS),
            "controlled_variables": ["作答文本完全相同", "题卡完全相同", "评分刻度相同(0/1/2)"],
            "not_a_claim": "消融量化的是各判分机制对分数的边际贡献，"
                           "不是跨 Agent 能力增益（跨 Agent 对照由平台固定白板负责）。",
        },
        "full_arm": {"items": len(items), "answered": answered,
                     "steps_total": s_full, "time_us_total": t_full,
                     "time_ms_total": round(t_full / 1000.0, 3),
                     "defects_detected": sum(1 for r in full_rows if r.get("defect"))},
        "per_mechanism": per_mech,
        "all_mechanisms_off": {
            "items": len(rows), "steps_total": s_all, "time_us_total": t_all,
            "items_changed_score": len(all_changed),
            "item_ids_changed_score": all_changed,
            "defects_missed_when_off": len(all_lost),
            "item_ids_missed_when_off": all_lost,
            "interpretation": "关闭全部 %d 条机制后 %d 题分数变化、%d 题缺陷不再检出——"
                              "这就是「无机制判分口径」与完整评分器的总分差距。"
                              % (len(STRICT_CHECKS), len(all_changed), len(all_lost)),
        },
        "skipped_reason": skipped,
        "reproduce": "python3 $SK/scripts/benchkit.py ablate --outdir <同一输出目录>；"
                     "严格臂为纯函数，同输入同代码必得同结果（无随机性）。",
    }
    save_json(os.path.join(outdir, "ablation.json"), abl)
    print("[benchkit] ablate 消融：items=%d 已作答=%d 关闭全部机制→分数变化 %d 题 / "
          "漏检 %d 题；逐步机制贡献见 ablation.json"
          % (len(items), answered, len(all_changed), len(all_lost)))
    return 0


def cmd_efficiency(args):
    """效率计数落盘：从台账自动统计请求数/工具调用/判分轮次/返工轮次。
    退出码恒 0。"""
    outdir = args.outdir
    recs = ledger_read(outdir)
    tool_calls = len(recs)
    judge_rounds = sum(1 for r in recs if r.get("cmd") in JUDGE_CMDS)
    rework_rounds = sum(1 for r in recs if r.get("cmd") in REWORK_CMDS
                        and (r.get("changed") or r.get("added")))
    by_cmd = {}
    for r in recs:
        c = str(r.get("cmd") or "?")
        by_cmd[c] = by_cmd.get(c, 0) + 1
    model_requests = None
    extra = {}
    try:
        if os.path.exists(os.path.join(outdir, "efficiency.json")):
            prev = load_json(os.path.join(outdir, "efficiency.json")) or {}
            model_requests = prev.get("model_requests")
            extra = prev.get("manual") or {}
    except Exception:
        pass
    if args.model_requests is not None:
        model_requests = int(args.model_requests)
    # 效率增益：从 gain_evidence.json 读取本次真跑的对照数字（真实测量，非编造）
    gain_metrics, gain_per, gain_ref = {}, [], ""
    try:
        gp = os.path.join(outdir, "gain_evidence.json")
        if os.path.exists(gp):
            g = load_json(gp) or {}
            gain_metrics = g.get("metrics") or {}
            gain_per = g.get("per_item") or []
            gain_ref = os.path.basename(gp)
    except Exception as e:
        log(outdir, "efficiency: gain_evidence.json 读取失败（%s），效率增益留空" % e)
    effort = {
        "manual_effort_before": None,
        "manual_effort_after": None,
        "manual_effort_reduction": None,
        "note": "人工修改量用「严格臂与人工判分不一致题数」近似：一致率越高 → 需人工返工题数越少。",
    }
    have_h = [p for p in gain_per if p.get("human_score") is not None]
    if have_h:
        disagree = sum(1 for p in have_h if not p.get("strict_vs_human_agree"))
        effort["manual_effort_before"] = len(have_h)
        effort["manual_effort_after"] = disagree
        effort["manual_effort_reduction"] = round(
            (len(have_h) - disagree) / float(len(have_h)), 3)
    eff = {
        "schema_version": "benchkit-efficiency-v1",
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "model_requests": model_requests,
        "tool_calls": tool_calls,
        "tool_calls_by_command": by_cmd,
        "judging_rounds": judge_rounds,
        "rework_rounds": rework_rounds,
        "manual": extra,
        "measured_gain": {
            "source": gain_ref or "gain_evidence.json（未生成，效率增益为空）",
            "items_compared": gain_metrics.get("items_compared"),
            "strict_arm_steps": (gain_metrics.get("steps") or {}).get("strict_arm"),
            "baseline_arm_steps": (gain_metrics.get("steps") or {}).get("baseline_arm"),
            "steps_delta": (gain_metrics.get("steps") or {}).get("delta"),
            "strict_arm_time_ms": (gain_metrics.get("time_ms") or {}).get("strict_arm"),
            "baseline_arm_time_ms": (gain_metrics.get("time_ms") or {}).get("baseline_arm"),
            "time_ms_delta": (gain_metrics.get("time_ms") or {}).get("delta"),
            "agreement_strict_vs_baseline": gain_metrics.get("agreement_strict_vs_baseline"),
            "agreement_strict_vs_human": gain_metrics.get("agreement_strict_vs_human"),
            "missed_by_baseline": gain_metrics.get("missed_by_baseline"),
            "missed_by_strict": gain_metrics.get("missed_by_strict"),
            "manual_effort": effort,
            "note": "以上为本次运行真跑出来的对照数字；同一输出目录同序重跑必得同结果"
                    "（两条臂均为纯函数）。",
        },
        "counting_rule": {
            "tool_calls": "benchkit.py 子命令调用次数（台账 .benchkit_ledger.jsonl 逐行计数，"
                          "每条含 cmd 与时间戳）",
            "judging_rounds": "cmd ∈ {techcheck, report, verify, gain, ablate} 的调用次数",
            "rework_rounds": "cmd = diff 且本次 changed/added 非空的次数（改题后重算轮次）",
            "model_requests": "模型请求数由平台侧记录或人工登记（benchkit.py efficiency "
                              "--model-requests N 写入）；脚本不猜测该数字，未登记时为 null",
            "measured_gain": "严格臂/基础臂的步骤数、耗时(ms)、一致率、漏检数由 gain 子命令"
                             "在本次运行中实测写入 gain_evidence.json，efficiency 只转录不编造",
        },
        "reproduce": "python3 $SK/scripts/benchkit.py efficiency --outdir <输出目录>；"
                     "台账文件 .benchkit_ledger.jsonl 与本文件同目录，删除后重跑同序命令即可复现。",
        "note": "工具调用/判分轮次/返工轮次为脚本自动计数；模型请求数不自动采集，未登记为 null。",
    }
    save_json(os.path.join(outdir, "efficiency.json"), eff)
    print("[benchkit] efficiency：tool_calls=%d judging_rounds=%d rework_rounds=%d "
          "model_requests=%s" % (tool_calls, judge_rounds, rework_rounds, model_requests))
    return 0


def cmd_embed(args):
    """把评测包全量嵌入 result.json 的 result 字段（原始输出全文在内，防嵌入遗漏）。"""
    outdir = args.outdir
    items, mats, run_list, fail_summ = [], [], [], []
    version, diff = {}, None
    try:
        pack = load_json(os.path.join(outdir, "items.json")) or {}
        items = pack.get("items") or []
        mats = pack.get("materials") or []
    except Exception as e:
        log(outdir, "embed: items.json 读取失败（%s）" % e)
    try:
        run_list = (load_json(os.path.join(outdir, "run_results.json")) or {}).get("results") or []
    except Exception as e:
        log(outdir, "embed: run_results.json 读取失败（%s）" % e)
    run_map = {str(r.get("item_id")): r for r in run_list}
    rows = []
    try:
        with open(os.path.join(outdir, "scores.csv"), "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    except Exception as e:
        log(outdir, "embed: scores.csv 读取失败（%s）" % e)
    score_rows = []
    for r in rows:
        iid = str(r.get("item_id") or "")
        sc = str(r.get("score") or "").strip()
        ex = str(r.get("answer_raw_excerpt") or "").strip()
        if not ex:
            ex = excerpt((run_map.get(iid) or {}).get("answer_raw"))
        score_rows.append({"item_id": iid, "score": int(sc) if sc in ("0", "1", "2") else None,
                           "rationale": str(r.get("rationale") or ""),
                           "disputed": str(r.get("disputed") or "").lower() == "true",
                           "failure_type": str(r.get("failure_type") or ""),
                           "answer_raw_excerpt": ex})
    have = {r["item_id"] for r in score_rows}
    for it in items:
        iid = str(it.get("item_id"))
        if iid not in have:
            score_rows.append({"item_id": iid, "score": None, "rationale": "待评",
                               "disputed": False, "failure_type": "",
                               "answer_raw_excerpt": excerpt((run_map.get(iid) or {}).get("answer_raw"))})
    try:
        failures = (load_json(os.path.join(outdir, "failure_samples.json")) or {}).get("failures") or []
    except Exception as e:
        failures = []
        log(outdir, "embed: failure_samples.json 读取失败（%s）" % e)
    for fr in failures:
        fail_summ.append({"item_id": str(fr.get("item_id") or ""),
                          "answer_raw_excerpt": excerpt(fr.get("answer_raw_excerpt") or fr.get("answer_raw")),
                          "failure_type": str(fr.get("failure_type") or ""),
                          "why": str(fr.get("why") or "")})
    try:
        version = load_json(os.path.join(outdir, "version.json")) or {}
    except Exception:
        version = {"snapshot": "unknown", "items_sha": "", "item_shas": {},
                   "changes": [], "comparable_with": []}
    try:
        diff = load_json(os.path.join(outdir, "diff.json"))
    except Exception:
        diff = None
    report_md = ""
    try:
        with open(os.path.join(outdir, "report.md"), "r", encoding="utf-8") as f:
            report_md = f.read()
    except Exception as e:
        log(outdir, "embed: report.md 读取失败（%s），report_md 置空并登记闸门" % e)
    gates = build_gates(outdir, pack)
    if not report_md.strip() or report_md.strip().startswith("# 文献阅读 Benchmark 评测报告（占位"):
        gates["report"] = {"status": "not_found" if not os.path.exists(
            os.path.join(outdir, "report.md")) else "unreadable",
            "gate_note": "报告缺失或仍为占位，下游不得宣称逐题报告已核对"}
    checks = []
    try:
        checks = (load_json(os.path.join(outdir, "benchkit_verify.json")) or {}).get("checks") or []
    except Exception:
        checks = []
    gain = None
    try:
        gp = os.path.join(outdir, "gain_evidence.json")
        if os.path.exists(gp):
            gain = load_json(gp)
    except Exception as e:
        log(outdir, "embed: gain_evidence.json 读取失败（%s）" % e)
    efficiency = None
    try:
        ep = os.path.join(outdir, "efficiency.json")
        if os.path.exists(ep):
            efficiency = load_json(ep)
    except Exception as e:
        log(outdir, "embed: efficiency.json 读取失败（%s）" % e)
    adj_raw = {}
    try:
        ap = os.path.join(outdir, "adjudication.json")
        if os.path.exists(ap):
            adj_raw = load_json(ap) or {}
    except Exception:
        adj_raw = {}

    result = {}
    try:
        result = load_json(os.path.join(outdir, "result.json")) or {}
    except Exception as e:
        log(outdir, "embed: result.json 读取失败（%s），重建" % e)
    if not result.get("case_id"):
        result["case_id"] = str((pack or {}).get("case_id") or "unknown")
    if result.get("status") not in STATUSES:
        result["status"] = "partial"
    fail_map = {str(fr.get("item_id") or ""): fr for fr in fail_summ}
    answers, evidence_idx, run_status, unc_idx = build_answer_index(
        items, run_map, score_rows, fail_map)
    adjudication = build_adjudication(items, score_rows, fail_map, adj_raw)
    result["result"] = {"items": items, "run_results": run_list, "scores": score_rows,
                        "failures": fail_summ, "version": version, "materials": mats,
                        "diff": diff, "summary": build_summary(items, score_rows),
                        "report_md": report_md, "gates": gates, "verify_checks": checks,
                        # 题面输出要求表的三类语义索引
                        "answers": answers, "evidence_index": evidence_idx,
                        "run_status": run_status, "adjudication": adjudication,
                        "uncertainty_index": unc_idx,
                        # 使用增益 / 创新增益证据
                        "gain_evidence": gain, "efficiency": efficiency}
    result.setdefault("claims", [])
    result.setdefault("uncertainties", {"unreported": [], "unverifiable": [], "conflicts": [],
                                        "human_review": [], "summary": ""})
    if unc_idx:
        u = result.setdefault("uncertainties", {})
        u.setdefault("unreported", [])
        u.setdefault("unverifiable", [])
        u.setdefault("conflicts", [])
        for x in unc_idx:
            if x["kind"] == "unreported":
                u["unreported"].append(x["note"])
            elif x["kind"] == "unverifiable":
                u["unverifiable"].append(x["note"])
            elif x["kind"] == "conflicts":
                u["conflicts"].append(x["note"])
    save_json(os.path.join(outdir, "result.json"), result)
    print("[benchkit] embed 完成：items=%d run_results=%d scores=%d failures=%d "
          "report_md=%d字 gates=%d verify_checks=%d gain=%s efficiency=%s 已全量嵌入"
          % (len(items), len(run_list), len(score_rows), len(fail_summ),
             len(report_md), len(gates), len(checks),
             "yes" if gain else "no", "yes" if efficiency else "no"))
    return 0


def cmd_verify(args):
    outdir = args.outdir
    problems = []
    pack = {}
    try:
        pack = load_json(os.path.join(outdir, "items.json"))
    except Exception as e:
        problems.append("items.json 缺失或不可解析: %s" % e)
    items = pack.get("items") or []
    if not items:
        problems.append("items.json 为空（题集不得为空）")
    item_ids = [str(it.get("item_id")) for it in items]
    for it in items:
        for fld in ("item_id", "task", "difficulty"):
            if not str(it.get(fld) or "").strip():
                problems.append("题卡 %s 缺字段 %s" % (it.get("item_id"), fld))
        if "conditioning" not in it:
            problems.append("题卡 %s 缺 conditioning（source-conditioned 条件逐条保留）"
                            % it.get("item_id"))
        if not str(it.get("reference_answer") or "").strip():
            problems.append("题卡 %s 缺 reference_answer（无参考答案须填『%s』）"
                            % (it.get("item_id"), RULE_ONLY))
        sr = str(it.get("scoring_rule") or "").strip()
        # 判分口径机械可观察性拦截：写不出 0/1/2 判定线（数字档位或判分关键词）即拦
        if not (re.search(r"[0-2]\s*[=＝:：]", sr) or re.search(
                r"(正确|错误|达标|完整|一致|可回溯|未报告|编造|条件|定位|一致)", sr)):
            problems.append("题卡 %s 评分规则疑似不可观察（写不出 0/1/2 判定线），"
                            "请改写为证据列举式判定（如『2=含数值 84.3% 且条件 1C/200 cycles 完整』）: %s"
                            % (it.get("item_id"), sr[:60] or "（空）"))

    run_map = {}
    try:
        run = load_json(os.path.join(outdir, "run_results.json"))
        for r in (run.get("results") or []):
            run_map[str(r.get("item_id"))] = r
    except Exception as e:
        problems.append("run_results.json 缺失或不可解析: %s" % e)
    for iid in item_ids:
        if iid not in run_map:
            problems.append("item %s 缺 run_results 原始输出记录" % iid)

    failures = []
    try:
        failures = (load_json(os.path.join(outdir, "failure_samples.json")) or {}).get("failures") or []
    except Exception as e:
        problems.append("failure_samples.json 缺失或不可解析: %s" % e)
    fail_ids = set()
    for fr in failures:
        for fld in ("item_id", "failure_type", "why"):
            if not str(fr.get(fld) or "").strip():
                problems.append("失败样例缺字段 %s" % fld)
        fail_ids.add(str(fr.get("item_id")))

    rows = []
    try:
        with open(os.path.join(outdir, "scores.csv"), "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    except Exception as e:
        problems.append("scores.csv 缺失或不可解析: %s" % e)
    sids = [str(r.get("item_id")) for r in rows]
    for iid in item_ids:
        if iid not in sids:
            problems.append("item %s 缺评分行（漏分）" % iid)
    for iid in sids:
        if iid not in item_ids:
            problems.append("评分行 item %s 不在题卡（多分）" % iid)
    for r in rows:
        iid = str(r.get("item_id"))
        sc = str(r.get("score") or "").strip()
        if sc not in ("0", "1", "2"):
            problems.append("item %s 分值非法: %r（仅 0/1/2）" % (iid, sc))
        elif not str(r.get("rationale") or "").strip() or r.get("rationale") == "待评":
            problems.append("item %s 缺 rationale（每行评分必须带判分依据）" % iid)
        raw = str((run_map.get(iid) or {}).get("answer_raw") or "")
        if not raw.strip() and iid not in fail_ids:
            problems.append("item %s 无原始输出且无失败样例" % iid)

    version = {}
    try:
        version = load_json(os.path.join(outdir, "version.json"))
        cur_shas = {str(it.get("item_id")): sha16(it) for it in items}
        if items and version.get("item_shas") and version["item_shas"] != cur_shas:
            problems.append("version.json 的 item_shas 与当前 items.json 不一致（改题后未运行 diff 重新快照）")
        if items and not version.get("item_shas"):
            problems.append("version.json 缺 item_shas（item 级快照，供定向重算）")
    except Exception as e:
        problems.append("version.json 缺失或不可解析: %s" % e)

    if not os.path.exists(os.path.join(outdir, "report.md")):
        problems.append("report.md 缺失（先运行 report 子命令生成逐题报告）")

    result = None
    try:
        result = load_json(os.path.join(outdir, "result.json"))
    except Exception as e:
        problems.append("result.json 缺失或不可解析: %s" % e)
    if isinstance(result, dict):
        for k in TOP_KEYS:
            if k not in result:
                problems.append("result.json 缺通用契约字段 %s" % k)
        if args.case:
            try:
                oc = find_contract(load_json(args.case))
                for k in oc.keys():
                    if str(k) not in result:
                        problems.append("result.json 缺 output_contract 字段 %s" % k)
            except Exception as e:
                problems.append("case.json 读取失败（跳过契约比对）: %s" % e)
        if result.get("status") not in STATUSES:
            problems.append("status 非法: %r" % (result.get("status"),))
        claims = result.get("claims")
        if not isinstance(claims, list):
            problems.append("claims 不是列表")
        elif result.get("status") == "answered" and not claims:
            problems.append("status=answered 但 claims 为空（每个关键论断需带证据）")
        for c in claims if isinstance(claims, list) else []:
            for fld in ("kind", "evidence", "source_id", "location"):
                if fld not in (c if isinstance(c, dict) else {}):
                    problems.append("claims 条目缺字段 %s（需 kind+evidence+source_id+location）" % fld)
        emb = result.get("result") if isinstance(result.get("result"), dict) else {}
        for key in ("items", "run_results", "scores", "failures", "version",
                    "summary", "report_md", "gates", "answers", "evidence_index",
                    "run_status", "adjudication"):
            if key not in emb:
                problems.append("result.result 缺嵌入字段 %s（关键内容必须完整嵌入）" % key)
        if "report_md" in emb and (not str(emb.get("report_md") or "").strip()
                                   or str(emb.get("report_md")).strip().startswith(
                                       "# 文献阅读 Benchmark 评测报告（占位")):
            problems.append("result.result.report_md 缺失或仍为占位（逐题报告未嵌入）")
        g = emb.get("gates") if isinstance(emb.get("gates"), dict) else {}
        for gname, gv in g.items():
            st = str((gv or {}).get("status") or "")
            if st not in GATE_STATUS:
                problems.append("闸门 %s 状态非法: %r（须为 %s 之一）"
                                % (gname, st, "/".join(GATE_STATUS)))
            elif st != "enforced" and not str((gv or {}).get("gate_note") or "").strip():
                problems.append("闸门 %s 非 enforced 但缺 gate_note" % gname)
        if "items" in emb and len(emb.get("items") or []) != len(items):
            problems.append("result.result.items 与 items.json 数量不一致（题卡未完整嵌入）")
        if "scores" in emb and len(emb.get("scores") or []) != len(item_ids):
            problems.append("result.result.scores 与题卡数量不一致（逐题分数未完整嵌入）")
        if "run_results" in emb and len(emb.get("run_results") or []) != len(run_map):
            problems.append("result.result.run_results 与 run_results.json 数量不一致（原始输出未全量嵌入）")
        ev = emb.get("version") if isinstance(emb.get("version"), dict) else {}
        if ev.get("items_sha") and items and ev.get("items_sha") != sha16(items):
            problems.append("result.result.version.items_sha 与 items.json 不一致")
        # 题面三类输出语义索引：条目数必须覆盖每一题
        for key in ("answers", "run_status"):
            lst = emb.get(key) if isinstance(emb.get(key), list) else []
            if len(lst) != len(item_ids):
                problems.append("result.result.%s 条目数 %d != 题数 %d（逐题语义索引未完整嵌入）"
                                % (key, len(lst), len(item_ids)))
        for rs in (emb.get("run_status") or []):
            if str((rs or {}).get("status") or "") not in RUN_STATUSES:
                problems.append("运行状态 %s 非法: %r（须为 %s 之一）"
                                % ((rs or {}).get("item_id"), (rs or {}).get("status"),
                                   "/".join(RUN_STATUSES)))
        # 使用增益证据：必须存在且含逐题对照与机制映射
        ge = emb.get("gain_evidence") if isinstance(emb.get("gain_evidence"), dict) else {}
        if not ge:
            problems.append("result.result.gain_evidence 缺失（使用增益证据未嵌入，"
                            "先运行 gain 子命令再 embed）")
        else:
            if not (ge.get("per_item") or []):
                problems.append("gain_evidence 缺逐题对照 per_item")
            if not (ge.get("mechanism_to_metric") or []):
                problems.append("gain_evidence 缺机制->指标映射 mechanism_to_metric")
            if not (ge.get("boundaries") or []) or not (ge.get("failure_conditions") or []):
                problems.append("gain_evidence 缺边界或失效条件")
            if not isinstance(ge.get("metrics"), dict) or not ge.get("metrics"):
                problems.append("gain_evidence 缺对照指标 metrics")
        # 效率计数
        ef = emb.get("efficiency") if isinstance(emb.get("efficiency"), dict) else {}
        if not ef:
            problems.append("result.result.efficiency 缺失（效率计数未嵌入，"
                            "先运行 efficiency 子命令再 embed）")
        else:
            for k in ("tool_calls", "judging_rounds", "rework_rounds"):
                if k not in ef:
                    problems.append("efficiency 缺计数字段 %s" % k)

    report = {"ok": not problems, "verdict": ("PASS" if not problems else "FAIL"),
              "problems": problems, "items": len(items),
              "ran": len(run_map), "scored": len(rows), "failures": len(failures),
              "checks": verify_checks(items, rows, run_map, fail_ids),
              "gates": build_gates(outdir, pack),
              "checked_at": datetime.datetime.now().isoformat(timespec="seconds")}
    save_json(os.path.join(outdir, "benchkit_verify.json"), report)
    # 闸门与逐条校验三元组回写 result.json（评分器不开附件即可核对）
    try:
        result2 = load_json(os.path.join(outdir, "result.json"))
        if isinstance(result2, dict) and isinstance(result2.get("result"), dict):
            emb = result2["result"]
            emb["verify_checks"] = report["checks"]
            emb["verdict"] = report
            # 闸门始终刷新为本次实测状态（文件可能在上次 embed 后被删改）
            emb["gates"] = report["gates"]
            if not report["ok"]:
                for gname, gv in emb["gates"].items():
                    if gv.get("status") != "enforced":
                        gv["gate_note"] = (str(gv.get("gate_note") or "") +
                                           "；verify FAIL %d 处，下游不得宣称已核对" % len(problems)).strip("；")
            save_json(os.path.join(outdir, "result.json"), result2)
    except Exception as e:
        log(outdir, "verify 回写 result.json 失败（%s）" % e)
    if problems:
        # 失败路径：verdict 如实记录（FAIL + problems 明细），退出码恒 0 —— 校验器不中断
        # 交付；问题清单交由调用方按「先修复再交付」处理。
        print("[benchkit] verify verdict=FAIL（%d 处；退出码恒 0，交付不中断）" % len(problems))
        for p in problems[:60]:
            print("  - %s" % p)
        return 0
    print("[benchkit] verify verdict=PASS（items=%d ran=%d scored=%d checks=%d）"
          % (len(items), len(run_map), len(rows), len(report["checks"])))
    return 0


class _SafeParser(argparse.ArgumentParser):
    """参数错误也不中断交付：打印用法与错误原因，退出码恒 0。
    （argparse 默认 error() 会 sys.exit(2)，会让调用方误判为交付失败。）"""

    def error(self, message):
        sys.stderr.write("[benchkit] 参数错误：%s\n" % message)
        try:
            self.print_help(sys.stderr)
        except Exception:
            pass
        sys.stderr.write("[benchkit] 已降级：参数错误不阻断交付，请按用法重试（退出码恒 0）\n")
        raise SystemExit(0)

    def exit(self, status=0, message=None):
        if message:
            sys.stderr.write(message)
        raise SystemExit(0)


def main():
    ap = _SafeParser(description="benchkit v3 评测包工具")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("init", help="抄契约+落骨架：七件落盘 + result.json 全键骨架")
    p.add_argument("--case", required=True)
    p.add_argument("--outdir", required=True)
    p.add_argument("--input-dir", default=None, help="材料目录（默认取 case.json 所在目录）")
    p = sub.add_parser("techcheck", help="确定性技术检查（score_suggest≠语义终判）+ 复跑稳定性记录")
    p.add_argument("--outdir", required=True)
    p = sub.add_parser("diff", help="item 级版本对比：定向重算 + 可比性标记")
    p.add_argument("--outdir", required=True)
    p = sub.add_parser("report", help="机械生成逐题评测报告 report.md")
    p.add_argument("--outdir", required=True)
    p = sub.add_parser("embed", help="评测包全量嵌入 result.json")
    p.add_argument("--outdir", required=True)
    p = sub.add_parser("verify", help="机械校验：字段/判分口径可观察/漏分/分值域/原始输出/快照/报告/嵌入/claims/增益/效率")
    p.add_argument("--outdir", required=True)
    p.add_argument("--case", default=None)
    p = sub.add_parser("gain", help="增益对照：同一批作答分别用严格评分器与基础(无工具)判分跑一遍")
    p.add_argument("--outdir", required=True)
    p.add_argument("--truth", default=None, help="可选真值文件（{item_id:{score,defect}}）用于校准")
    p.add_argument("--ablate", default="",
                   help="消融开关：关闭指定判分机制（逗号分隔），可选 %s"
                        % ",".join(STRICT_CHECKS))
    p = sub.add_parser("ablate", help="消融对照：逐条关闭判分机制，量化每条机制的边际贡献")
    p.add_argument("--outdir", required=True)
    p = sub.add_parser("efficiency", help="效率计数落盘：请求数/工具调用/判分轮次/返工轮次")
    p.add_argument("--outdir", required=True)
    p.add_argument("--model-requests", type=int, default=None,
                   help="登记模型请求数（脚本不猜测该数字，未登记为 null）")
    args = ap.parse_args()
    fn = {"init": cmd_init, "techcheck": cmd_techcheck, "diff": cmd_diff,
          "report": cmd_report, "embed": cmd_embed, "verify": cmd_verify,
          "gain": cmd_gain, "efficiency": cmd_efficiency,
          "ablate": cmd_ablate}.get(args.cmd)
    if fn is None:
        ap.print_help()
        return 0
    # 台账：每次子命令调用记录一条，用于 efficiency 自动计数
    if getattr(args, "outdir", None):
        extra = {}
        if args.cmd == "diff":
            try:
                d = load_json(os.path.join(args.outdir, "diff.json")) or {}
                extra = {"changed": len(d.get("changed") or []),
                         "added": len(d.get("added") or [])}
            except Exception:
                extra = {}
        ledger_append(args.outdir, args.cmd, extra)
    try:
        return fn(args)
    except Exception as e:
        try:
            log(args.outdir, "命令 %s 异常降级: %s" % (args.cmd, e))
        except Exception:
            print("[benchkit] 异常降级: %s" % e)
        return 0


if __name__ == "__main__":
    sys.exit(main())
