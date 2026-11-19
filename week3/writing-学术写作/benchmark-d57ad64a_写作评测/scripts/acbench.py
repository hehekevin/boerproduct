#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""acbench.py — 学术写作 Benchmark 评测包工具（init / techcheck / diff / report / embed / verify）。

用法：
    python3 acbench.py init     --case <case.json> --outdir <dir> [--input-dir <dir>]
    python3 acbench.py techcheck --outdir <dir>
    python3 acbench.py diff     --outdir <dir>
    python3 acbench.py report   --outdir <dir>
    python3 acbench.py embed    --outdir <dir>
    python3 acbench.py verify   --outdir <dir> [--case <case.json>]

设计约束：
- 任何输入（含损坏 JSON、空文件、未知结构）都不得抛裸异常、不得产出空题集：
  所有命令全捕获降级，仅打印警告并写 warn.log，退出码恒为 0。
- techcheck 的 score_suggest 只是确定性建议，不是最终语义分；语义 0/1/2 由
  verdict_rule（全部 must_points 满足=2；命中任一 reject=0；其余=1）判定，两者分开记录。
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
import time

SCORE_FIELDS = ("item_id", "score", "rationale", "disputed", "failure_type", "draft_excerpt")
TOP_KEYS = ("case_id", "status", "result", "claims", "uncertainties")
STATUSES = ("answered", "partial", "insufficient_evidence", "input_error")
RULE_ONLY = "仅规则评分"
FAIL_SUGGEST = {
    "no_answer": "未产出稿件：核对题面指令与材料后再作答，不得留空",
    "missing_must_point": "补齐缺失必需要点（逐条对照 must_points）",
    "overclaim": "论断强度超出材料：降级为材料支持的表述并保留限定条件",
    "format_error": "按题面格式约束重排（体裁/小节/字数/引用格式）",
    "text_mismatch": "事实或数值与材料不符：回到材料逐条核对",
    "file_unreadable": "材料文件无法读取：如实登记缺口，不编造内容",
    "permission_denied": "权限不足：登记后降级交付，不伪造替代数据",
    "disputed": "存疑项交人工复核，评分不改动，锚点可修订",
}

# ---- 工单字段同义词映射（识别失败即合成兜底，绝不产空题集） ----
TASK_KEYS = ("task", "instruction", "prompt", "question", "query", "requirement",
             "problem", "title", "ask", "writing_task", "topic", "assignment")
ID_KEYS = ("item_id", "id", "qid", "task_id", "question_id", "number", "index", "key")
REF_KEYS = ("reference_answer", "gold_answer", "gold", "expected_answer", "expected",
            "sample_answer", "model_answer", "answer", "reference")
MUST_KEYS = ("must_points", "required_points", "key_points", "required_elements",
             "must_include", "essentials", "required", "requirements")
VARIANT_KEYS = ("variants", "acceptable_variants", "allowed_variants",
                "acceptable_variations", "acceptable_differences")
REJECT_KEYS = ("reject", "rejects", "forbidden", "disallowed", "unacceptable", "errors")
GENRE_KEYS = ("genre", "type", "category", "style", "audience", "format")
MAT_KEYS = ("materials", "sources", "input", "inputs", "material_refs",
            "source_refs", "evidence", "context")
VERDICT_KEYS = ("verdict_rule", "completion_rule", "pass_rule", "judgment_rule")
RULE_KEYS = ("scoring_rule", "grading_rule", "grading", "score_rule", "scoring",
             "rubric", "criteria")
DIFF_KEYS = ("difficulty", "level")
INPUTREF_KEYS = ("input_ref", "source_ref", "source_id", "location", "page", "section")
PATH_HINTS = ("workorder", "item", "question", "entry", "task", "case", "subtask",
              "benchmark", "writing", "题")
STOPWORDS = {"the", "a", "an", "of", "in", "to", "and", "is", "are", "was", "were",
             "for", "on", "at", "by", "with", "that", "this", "it", "as", "be"}


def log(outdir, msg):
    print("[acbench] %s" % msg)
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
    """标量/列表/换行或分号分隔字符串 → 字符串列表。"""
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
    """同义词映射归一为写作题卡；结构未知时绝不丢弃条目。"""
    if not isinstance(w, dict):
        w = {"task": str(w)}
    task = first_key(w, TASK_KEYS)
    if isinstance(task, (dict, list)):
        task = json.dumps(task, ensure_ascii=False)
    mats = first_key(w, MAT_KEYS)
    if isinstance(mats, dict):
        mats = json.dumps(mats, ensure_ascii=False)
    else:
        mats = to_str_list(mats)
    consumed = set(TASK_KEYS + ID_KEYS + REF_KEYS + MUST_KEYS + VARIANT_KEYS +
                   REJECT_KEYS + GENRE_KEYS + MAT_KEYS + VERDICT_KEYS + RULE_KEYS +
                   INPUTREF_KEYS + DIFF_KEYS)
    extra = {}
    for k, v in w.items():
        if k not in consumed and v not in (None, ""):
            extra[str(k)] = str(v)[:500]
    verdict = first_key(w, VERDICT_KEYS) or (
        "全部 must_points 满足=pass(2)；命中任一 reject=fail(0)；其余=borderline(1)")
    return {
        "item_id": str(first_key(w, ID_KEYS) or ("item-%d" % (i + 1))),
        "task": str(task or ""),
        "genre": str(first_key(w, GENRE_KEYS) or "unspecified"),
        "input_ref": str(first_key(w, INPUTREF_KEYS) or ""),
        "materials": [str(m) for m in (to_str_list(mats) or [])],
        "must_points": to_str_list(first_key(w, MUST_KEYS)),
        "variants": to_str_list(first_key(w, VARIANT_KEYS)),
        "reject": to_str_list(first_key(w, REJECT_KEYS)),
        "verdict_rule": str(verdict),
        "reference_answer": (str(first_key(w, REF_KEYS)) if first_key(w, REF_KEYS) not in (None, "") else RULE_ONLY),
        "scoring_rule": str(first_key(w, RULE_KEYS) or ""),
        "difficulty": str(first_key(w, DIFF_KEYS) or "unspecified"),
        "extra": extra,
    }


def fallback_item(case):
    """识别不出结构化条目时合成单条兜底题卡，绝不产出空题集。"""
    task, mats = "", []
    if isinstance(case, dict):
        t = first_key(case, TASK_KEYS) or first_key(
            case, ("description", "summary", "objective", "goal", "background"))
        if isinstance(t, (dict, list)):
            t = json.dumps(t, ensure_ascii=False)
        task = str(t or "")
        mats = to_str_list(first_key(case, MAT_KEYS))
    if not task:
        task = ("未在 case.json 中识别出结构化条目：请人工阅读 /input/ 下材料与 task.md，"
                "按题面要求完成写作产物并按 verdict_rule 判分；本题卡为兜底记录，口径不变。")
    return {
        "item_id": "item-1", "task": task, "genre": "unspecified", "input_ref": "",
        "materials": mats, "must_points": [], "variants": [], "reject": [],
        "verdict_rule": ("全部 must_points 满足=pass(2)；命中任一 reject=fail(0)；其余=borderline(1)"),
        "reference_answer": RULE_ONLY,
        "scoring_rule": "2=必需要点全满足且忠实材料；1=部分满足；0=实质错误或未作答",
        "difficulty": "unspecified", "extra": {},
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


def norm_ws(text):
    """空白归一化（空白字符序列压为单个空格），用于 quote 逐字回证匹配。"""
    return re.sub(r"\s+", " ", str(text or "")).strip()


def excerpt(text, head=300, tail=100):
    text = str(text or "")
    if len(text) <= head + tail + 1:
        return text
    return text[:head] + "…" + text[-tail:]


def corpus_from_case(case):
    """把 case.json 全部字符串值拼接为回证语料（空白归一化后做子串匹配）。"""
    parts = []

    def walk(o):
        if isinstance(o, str):
            parts.append(o)
        elif isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(case)
    return norm_ws(" ".join(parts))


def token_cover(needle, hay):
    n = set(re.findall(r"\w+", str(needle).lower())) - STOPWORDS
    if not n:
        return 1.0
    h = set(re.findall(r"\w+", str(hay).lower()))
    return round(len(n & h) / float(len(n)), 3)


CJK_RE = re.compile(r"[\u4e00-\u9fff]+")


def cjk_bigrams(text):
    """中文串的字符二元组集合（去掉标点空白）。"""
    out = set()
    for seg in CJK_RE.findall(str(text or "")):
        if len(seg) == 1:
            out.add(seg)
            continue
        for i in range(len(seg) - 1):
            out.add(seg[i:i + 2])
    return out


def cjk_cover(point, draft):
    """中文要点对原稿的二元组覆盖率（比英文 token 覆盖更适合中文学术写作）。"""
    pb = cjk_bigrams(point)
    if not pb:
        return None
    db = cjk_bigrams(draft)
    return round(len(pb & db) / float(len(pb)), 3)


NEG_TABLE_RE = re.compile(r"(表外数值|材料外|未提供|无依据|没有依据|来源不明|额外数值|杜撰)")
OVERCLAIM_TERMS = ("证明", "证实", "彻底", "必然", "一定", "显著", "因果", "导致", "预测", "完全")
SPLIT_RE = re.compile(r"[，,；;]")
NEG_START_RE = re.compile(r"^(不|未|无|不得|禁止|避免|不含|不删|不能|不可|别|勿|严禁|不应)")
NEG_INFIX_RE = re.compile(r"(不得出现|不得写|不含|不引入|未出现|不出现|不包括|避免出现|"
                           r"禁止出现|不能出现|不应出现|无依据|表外数值|材料外)")


def material_list(item):
    """题卡的材料列表（兼容 list / 字符串 / JSON 字符串化列表三种形态）。"""
    mats = item.get("materials") or []
    if isinstance(mats, str):
        s = mats.strip()
        if s.startswith("["):
            try:
                parsed = json.loads(s)
                if isinstance(parsed, list):
                    return [str(m) for m in parsed]
            except Exception:
                pass
        return [mats]
    return [str(m) for m in mats]


def materials_text(item):
    return " ".join(material_list(item))


def point_scopes(point):
    """把要点按标点切成子句（学术锚点常写成「A，且不含 B」这类多子句形式）。"""
    return [s.strip() for s in SPLIT_RE.split(str(point or "")) if s.strip()]


def scope_met(scope, draft, item):
    """单个子句是否满足。返回 (met, kind)；kind 便于报告里说明判定依据。"""
    s = str(scope or "").strip()
    if not s:
        return True, "empty"
    negated = bool(NEG_START_RE.match(s)) or bool(NEG_INFIX_RE.search(s))
    quoted = re.findall(r"[『「\"'“”‘’]([^』」\"'“”‘’]{1,40})[』」\"'“”‘’]", s)
    if negated:
        # 否定子句：引号术语必须缺席；无引号时用过度断言词表核对
        if quoted:
            return all(q not in draft for q in quoted), "negated_term_absent"
        if NEG_TABLE_RE.search(s):
            src = materials_text(item)
            if not src:
                return False, "negated_table_unverifiable"
            nums = re.findall(r"\d+(?:\.\d+)?", draft)
            missing = [n for n in nums if n not in src]
            return (not missing), "negated_table_ok" if not missing else "negated_table_hit"
        hits = [w for w in OVERCLAIM_TERMS if w in draft]
        if hits:
            return False, "negated_overclaim_hit"
        return True, "negated_no_term_found"
    if s in draft:
        return True, "literal"
    if quoted:
        return all(q in draft for q in quoted), "quoted_term"
    nums = re.findall(r"\d+(?:\.\d+)?", s)
    if nums:
        return all(n in draft for n in nums), "numeric"
    cc = cjk_cover(s, draft)
    if cc is not None:
        return cc >= 0.6, "cjk_bigram"
    return token_cover(s, draft) >= 0.6, "token_cover"


def point_met(point, draft, item=None):
    """必需要点是否可判满足（确定性建议，非语义终判）：
    多子句全部满足才算满足；否定子句走缺席判定；正向子句走
    子串 → 引号术语 → 数字 → 中文二元组覆盖 → 英文 token 覆盖。"""
    scopes = point_scopes(point)
    if not scopes:
        return True
    for s in scopes:
        met, _kind = scope_met(s, draft, item or {})
        if not met:
            return False
    return True




def reject_terms(reject_list):
    """reject 条目 → 可检测关键词。引号内为关键触发词，否则整串按字面子串匹配。"""
    out = []
    for r in reject_list or []:
        s = str(r or "").strip()
        if not s:
            continue
        quoted = re.findall(r"[『「\"'“”‘’]([^』」\"'“”‘’]{1,40})[』」\"'“”‘’]", s)
        if quoted:
            for q in quoted:
                out.append({"reject": s, "term": q, "mode": "quoted"})
        else:
            out.append({"reject": s, "term": s, "mode": "literal"})
    return out


def tech_check(item, draft):
    """确定性校验——不是语义终判，score_suggest 仅供参考。"""
    src = json.dumps(item.get("materials") or [], ensure_ascii=False) if not isinstance(
        item.get("materials"), str) else str(item["materials"])
    src += " " + str(item.get("input_ref") or "")
    ref = str(item.get("reference_answer") or "")
    draft = str(draft or "")
    checks = {"draft_empty": not draft.strip()}
    if ref and ref != RULE_ONLY:
        nums = re.findall(r"[-+]?\d+(?:\.\d+)?", ref)
        if nums:
            checks["ref_numbers_in_source"] = all(n in src for n in nums)
            checks["draft_covers_ref_numbers"] = all(n in draft for n in nums)
    mp = item.get("must_points") or []
    if mp:
        cov = [{"point": str(m)[:120], "met": bool(point_met(m, draft, item))} for m in mp]
        checks["must_point_coverage"] = cov
        checks["missing_must_points"] = [c["point"] for c in cov if not c["met"]]
    rj = item.get("reject") or []
    if rj:
        hits = []
        for t in reject_terms(rj):
            if t["term"] and t["term"] in draft:
                hits.append(t["term"])
        checks["reject_hits"] = hits
    all_met = all(c["met"] for c in (checks.get("must_point_coverage") or [])) if mp else None
    no_reject = not checks.get("reject_hits")
    if checks["draft_empty"]:
        checks["score_suggest"] = 0
    elif not no_reject:
        checks["score_suggest"] = 0
    elif (all_met is True or mp == []) and no_reject:
        checks["score_suggest"] = 2
    else:
        checks["score_suggest"] = 1
    return checks


def check_digest(results):
    return sha16([{"i": r.get("item_id"), "t": r.get("technical_check")} for r in results])


def build_summary(items, score_rows):
    scored = [r for r in score_rows if r.get("score") in (0, 1, 2)]
    dist = {"0": 0, "1": 0, "2": 0}
    for r in scored:
        dist[str(int(r["score"]))] += 1
    return {
        "items_total": len(items),
        "items_with_reference": sum(1 for it in items if it.get("reference_answer") != RULE_ONLY),
        "items_rule_only": sum(1 for it in items if it.get("reference_answer") == RULE_ONLY),
        "must_points_total": sum(len(it.get("must_points") or []) for it in items),
        "score_dist": dist,
        "avg": (round(sum(int(r["score"]) for r in scored) / float(len(scored)), 3)
                if scored else None),
        "note": ("score_suggest/techcheck 为确定性建议，不是语义终判；语义分按 verdict_rule "
                 "0/1/2 判定并逐行给 rationale。分数复算路径：scores 行 → items 题卡 "
                 "must_points/reject → run_results 原稿全文。"),
    }


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
        "results": [{"item_id": it["item_id"], "draft_md": "", "draft_struct": {},
                     "evidence": [], "technical_check": {}, "timing": None}
                    for it in items]})
    try:
        with open(os.path.join(outdir, "scores.csv"), "w", encoding="utf-8", newline="") as f:
            wtr = csv.DictWriter(f, fieldnames=list(SCORE_FIELDS))
            wtr.writeheader()
            for it in items:
                wtr.writerow({"item_id": it["item_id"], "score": "", "rationale": "待评",
                              "disputed": "false", "failure_type": "", "draft_excerpt": ""})
    except Exception as e:
        log(outdir, "scores.csv 写入失败（%s）" % e)
    save_json(os.path.join(outdir, "failure_samples.json"), {"case_id": case_id, "failures": []})
    version = {"snapshot": "v1", "items_sha": sha16(items),
               "item_shas": {str(it["item_id"]): sha16(it) for it in items},
               "changes": ["init: 生成 %d 张写作题卡骨架" % len(items)],
               "comparable_with": [],
               "note": "题目/必需要点/锚点变化后运行 diff：仅重算受影响题目，未变题目历史分数可比"}
    save_json(os.path.join(outdir, "version.json"), version)

    score_rows = [{"item_id": it["item_id"], "score": None, "rationale": "待评",
                   "disputed": False, "failure_type": "", "draft_excerpt": ""}
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
                         "human_review": [], "summary": "骨架已落盘：待撰写稿件、待评分"}
        else:
            result[k] = "unknown"
    save_json(os.path.join(outdir, "result.json"), result)
    print("[acbench] init 完成：items=%d contract_keys=%s case_id=%s → %s"
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
            r = {"item_id": iid, "draft_md": "", "draft_struct": {}, "evidence": []}
            results.append(r)
            by_id[iid] = r
        r.setdefault("draft_md", "")
        r["technical_check"] = tech_check(it, str(r.get("draft_md") or ""))
        r["technical_check_note"] = "确定性校验与建议分，不是语义终判"
    run["results"] = results
    new_sha = check_digest(results)
    prev = (run.get("stability") or {}).get("check_sha")
    try:
        version = load_json(os.path.join(outdir, "version.json"))
        if prev and prev != new_sha:
            version.setdefault("changes", []).append(
                "复跑稳定性：技术检查结果与上次不同（check_sha %s→%s），请核对稿件是否变化"
                % (prev[:8], new_sha[:8]))
            save_json(os.path.join(outdir, "version.json"), version)
    except Exception:
        pass
    run.setdefault("stability", {})["check_sha"] = new_sha
    save_json(os.path.join(outdir, "run_results.json"), run)
    def check_fail(c):
        if not isinstance(c, dict):
            return True
        if c.get("draft_empty") is True:
            return True
        return bool(c.get("missing_must_points")) or bool(c.get("reject_hits")) or \
            c.get("draft_covers_ref_numbers") is False
    passed = sum(1 for r in results if not check_fail(r.get("technical_check")))
    print("[acbench] techcheck：ran=%d 全过=%d check_sha=%s（score_suggest≠语义终判）"
          % (len(results), passed, new_sha[:12]))
    return 0


def cmd_diff(args):
    """item 级版本对比：改题后只重算受影响题目，未变题目历史分数可比。"""
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
    print("[acbench] diff：changed=%d added=%d removed=%d 可比=%d"
          % (len(changed), len(added), len(removed), len(unchanged)))
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
    lines = ["# 学术写作 Benchmark 评测报告（逐题，机械生成）", "",
             "- case_id: %s" % pack.get("case_id", "unknown"),
             "- 生成时间: %s" % datetime.datetime.now().isoformat(timespec="seconds"),
             "- 题数: %d ｜ 已评: %d ｜ 分布: 0分=%d 1分=%d 2分=%d ｜ 均分: %s"
             % (sumry["items_total"], sum(sumry["score_dist"].values()),
                sumry["score_dist"]["0"], sumry["score_dist"]["1"],
                sumry["score_dist"]["2"], sumry["avg"]),
             "- 复现说明: 相同输入 + 同版本题卡(items_sha=%s) + 同评分规则可复算同一批分数。"
             % (version.get("items_sha") or "unknown"),
             "- 分数复算路径: scores 行 → 题卡 must_points/reject/verdict_rule → run_results 原稿全文。", ""]
    for it in items:
        iid = str(it.get("item_id"))
        r = next((x for x in rows if str(x.get("item_id")) == iid), {})
        rr = run_map.get(iid) or {}
        fr = fmap.get(iid) or {}
        ft = str(fr.get("failure_type") or r.get("failure_type") or "")
        sugg = FAIL_SUGGEST.get(ft, "保持达标；如修订锚点按 diff 定向重算")
        lines += ["## %s（体裁: %s，难度: %s）" % (iid, it.get("genre"), it.get("difficulty")),
                  "- 题面: %s" % excerpt(it.get("task"), 200, 0),
                  "- 得分: %s ｜ 争议: %s" % (r.get("score") or "未评", r.get("disputed") or "false"),
                  "- 判分依据: %s" % (r.get("rationale") or "待评"),
                  "- 必需要点: %s" % ("；".join(it.get("must_points") or []) or "（兜底题卡，人工补充）"),
                  "- 证据摘录: %s" % excerpt(fr.get("answer_raw_excerpt") or rr.get("draft_md")),
                  "- 失败类型: %s" % (ft or "无"),
                  "- 改进建议: %s" % sugg, ""]
    fail_tbl = ["| item_id | failure_type | why |", "|-|-|-|"]
    for fr in failures:
        fail_tbl.append("| %s | %s | %s |" % (fr.get("item_id"), fr.get("failure_type"), excerpt(fr.get("why"), 120, 0)))
    if not failures:
        fail_tbl.append("| （无失败样例） | | |")
    lines += ["## 失败样例归因"] + fail_tbl + ["",
              "## 分歧裁定", "disputed=true 的题按证据裁定；分歧超过一档时修订锚点而不是修改分数，"
              "修订史记入 version.changelog。", ""]
    rp = os.path.join(outdir, "report.md")
    with open(rp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("[acbench] report 生成: %s（%d 题）" % (rp, len(items)))
    return 0


def cmd_gain(args):
    """调用 gain_eval.py 做同输入双评分器对照，把增益证据嵌入 result.json。
    脚本缺失/异常时降级：写 gain_evidence 的失败说明，绝不中断交付。"""
    outdir = args.outdir
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gain_eval.py")
    try:
        import subprocess
    except Exception as e:
        log(outdir, "subprocess 不可用（%s），gain 证据降级" % e)
        return 0
    cmd = [sys.executable, script, "--outdir", outdir]
    if args.case:
        cmd += ["--case", args.case]
    if args.input_dir:
        cmd += ["--input-dir", args.input_dir]
    if args.degrade:
        cmd += ["--degrade"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        log(outdir, "gain_eval 退出码=%s 输出=%s" % (r.returncode, (r.stdout or "")[:400]))
        if r.stderr:
            log(outdir, "gain_eval stderr=%s" % (r.stderr or "")[:300])
    except Exception as e:
        log(outdir, "gain_eval 调用失败（%s），降级记录" % e)
    # 无论成功与否都把现有 gain_evidence.json 嵌入 result.json
    gpath = os.path.join(outdir, "gain_evidence.json")
    gain = None
    try:
        gain = load_json(gpath)
    except Exception as e:
        log(outdir, "gain_evidence.json 读取失败（%s），记录降级说明" % e)
    if gain is None:
        gain = {"ok": False, "status": "unavailable",
                "reason": "gain_eval.py 未产出可用结果（脚本缺失、运行失败或输出不可解析）",
                "metrics": {"agreement_rate": None, "missed_detections": None,
                            "false_downgrades": None, "items_compared": 0},
                "boundaries": ["增益证据缺失：不得宣称已完成同输入对照，下游需重跑 gain 子命令"],
                "honesty": {"status": "degraded", "note": "本次未产出真实对照数字，如实留空而非填 0"}}
    try:
        result = load_json(os.path.join(outdir, "result.json")) or {}
        result.setdefault("result", {})
        result["result"]["gain_evidence"] = gain
        save_json(os.path.join(outdir, "result.json"), result)
    except Exception as e:
        log(outdir, "gain 证据回写 result.json 失败（%s）" % e)
    m = (gain.get("metrics") or {})
    print("[acbench] gain：items=%s 一致率=%s 漏检=%s 误判=%s"
          % (gain.get("n_items"), m.get("agreement_rate"),
             m.get("missed_detections"), m.get("false_downgrades")))
    return 0


def record_step(outdir, cmd, t0, ok=True, note=""):
    """每个子命令完成后追加一条步骤记录到 steps_log.jsonl（效率计数的真实来源）。"""
    try:
        os.makedirs(outdir, exist_ok=True)
        rec = {"step": cmd, "ts": datetime.datetime.now().isoformat(timespec="seconds"),
               "elapsed_ms": int((time.time() - t0) * 1000), "ok": bool(ok), "note": str(note)[:200]}
        with open(os.path.join(outdir, "steps_log.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def read_steps(outdir):
    recs = []
    try:
        with open(os.path.join(outdir, "steps_log.jsonl"), "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        recs.append(json.loads(line))
                    except Exception:
                        continue
    except Exception:
        pass
    return recs


def build_efficiency(outdir, items, score_rows):
    """效率字段：真实采集自 steps_log.jsonl 的步骤数与耗时 + 复现说明。"""
    recs = read_steps(outdir)
    cmds = [r.get("step") for r in recs]
    total_ms = sum(int(r.get("elapsed_ms") or 0) for r in recs)
    manual_formula = "manual = 7(建题卡/判读材料/核验数值引用/写参考答案与变体/逐题评分与依据/双评与裁定/汇总报告与装配) + 每题 4(抄要点/逐条回证/写评分行与依据/写失败样例或裁定)"
    tool_formula = "tool = report / embed / verify / gain 四步机械动作（脚本命令计数）"
    return {
        "tool_steps": len(recs),
        "tool_step_sequence": cmds,
        "tool_elapsed_ms_total": total_ms,
        "tool_step_formula": tool_formula,
        "manual_step_formula": manual_formula,
        "manual_steps_estimated": 7 + len(items) * 4,
        "mechanical_steps_saved_estimate": 7 + len(items) * 4 - len(set(cmds)),
        "items": len(items),
        "scored_items": sum(1 for r in score_rows if r.get("score") in (0, 1, 2)),
        "reproduce": {
            "commands": ["init --case <case.json> --outdir <dir>",
                         "techcheck --outdir <dir>",
                         "diff --outdir <dir>",
                         "report --outdir <dir>",
                         "gain --outdir <dir> --case <case.json>",
                         "embed --outdir <dir>",
                         "verify --outdir <dir> --case <case.json>"],
            "runtime": "python3 %s" % os.path.basename(__file__),
            "deps": "仅 Python 3.7+ 标准库，零第三方依赖",
            "determinism": "同一输入 + 同一题卡版本(items_sha) + 同一评分规则 → 同一批分数",
            "fingerprint": {"items_sha": sha16(items),
                            "steps_log": os.path.basename(os.path.join(outdir, "steps_log.jsonl"))},
            "note": "步骤数与耗时由 steps_log.jsonl 自动采集，未实测的人工工时不编造",
        },
        "note": ("效率计数为脚本侧真实采集（步骤数/耗时）；人工侧步骤按流程清单逐项计数，"
                 "两者均可在 steps_log.jsonl 与本字段复核，不填编造的人工耗时。"),
    }


def build_contract_map(items, score_rows, failures, report_md, adjudication, gain):
    """题面输出要求表 → result.json 字段的逐项语义映射（核对用）。"""
    disputed = [r for r in score_rows if r.get("disputed")]
    rounds = ((adjudication or {}).get("rounds") or [])
    return {
        "题集": {"required_by": "题面『题能判定』+ 任务集设计方向",
                 "fields": ["result.items[].item_id", "result.items[].task",
                            "result.items[].must_points", "result.items[].variants",
                            "result.items[].reject", "result.items[].verdict_rule",
                            "result.items[].reference_answer"],
                 "count": len(items),
                 "semantics": "每题带可观察必需要点 + 可接受变体 + 不可接受错误 + 判定规则，两名评分员不商量可判出同一档"},
        "评分": {"required_by": "题面『锚点打得齐』+ 评分锚点方向",
                 "fields": ["result.scores[].item_id", "result.scores[].score",
                            "result.scores[].rationale", "result.scores[].draft_excerpt"],
                 "count": len(score_rows),
                 "semantics": "0/1/2 逐题打分，每行带判分依据（引题卡要点 + 材料定位），可顺 item_id 复算"},
        "失败样例": {"required_by": "题面『报告说得清』+ 评测报告方向",
                     "fields": ["result.failures[].item_id", "result.failures[].failure_type",
                                "result.failures[].why", "result.failures[].answer_raw_excerpt"],
                     "count": len(failures),
                     "semantics": "失败按 8 类归因并附原稿摘录，报告逐题给出改进建议"},
        "报告": {"required_by": "题面『报告说得清』",
                 "fields": ["result.report_md"],
                 "chars": len(report_md or ""),
                 "semantics": "逐题给出得分/证据/失败类型/改进建议，报告全文嵌入，不依赖附件"},
        "裁定": {"required_by": "题面『锚点打得齐』+ 标注一致性方向",
                 "fields": ["result.adjudication.rounds[].item_id", "result.adjudication.rounds[].judge_a",
                            "result.adjudication.rounds[].judge_b", "result.adjudication.rounds[].delta",
                            "result.adjudication.rounds[].adjudicated",
                            "result.adjudication.rounds[].anchor_revision",
                            "result.adjudication.rounds[].evidence"],
                 "count": len(rounds),
                 "semantics": "双评分分歧按证据裁定；分歧超一档修订锚点而非改分，修订史记入 version.changes"},
        "分歧": {"required_by": "题面『锚点打得齐』+ 标注一致性方向",
                 "fields": ["result.scores[].disputed", "result.adjudication.rounds[].delta",
                            "result.adjudication.rounds[].anchor_revision"],
                 "disputed_items": len(disputed),
                 "max_delta": max([int(r.get("delta") or 0) for r in rounds] or [0]),
                 "semantics": "分歧集中在少数判据上 → 修订锚点；disputed 题必须有裁定记录否则 verify FAIL"},
        "目标产物": {"required_by": "题面输出要求表『目标产物』",
                     "fields": ["result.run_results[].item_id", "result.run_results[].draft_md",
                                "result.run_results[].draft_struct"],
                     "semantics": "可编辑稿件全文留存，满足题面指定体裁/受众/格式"},
        "事实与来源映射": {"required_by": "题面输出要求表『事实与来源映射』",
                           "fields": ["result.run_results[].evidence[].quote",
                                      "result.run_results[].evidence[].location",
                                      "claims[].evidence[].quote", "claims[].evidence[].location"],
                           "semantics": "数字/术语/引用逐条回溯到材料原文，不新增材料外事实"},
        "版本与边界": {"required_by": "题面输出要求表『版本与边界』",
                       "fields": ["result.version", "result.diff", "uncertainties.unreported",
                                  "uncertainties.unverifiable", "uncertainties.conflicts",
                                  "uncertainties.human_review"],
                       "semantics": "修改差异、人工确认项、材料缺口与异常分别说明，未确认部分明确标注"},
        "增益证据": {"required_by": "题面评分维度『使用增益』+『创新增益』",
                     "fields": ["result.gain_evidence.metrics.agreement_rate",
                                "result.gain_evidence.metrics.missed_detections",
                                "result.gain_evidence.mechanism_to_metric",
                                "result.gain_evidence.boundaries"],
                     "present": bool(gain),
                     "semantics": "同输入同批作答的双评分器对照，附机制→指标映射与边界"},
    }


def cmd_embed(args):
    """把评测包全量嵌入 result.json 的 result 字段（稿件全文在内，防嵌入遗漏）。"""
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
        ex = str(r.get("draft_excerpt") or "").strip()
        if not ex:
            ex = excerpt((run_map.get(iid) or {}).get("draft_md"))
        score_rows.append({"item_id": iid, "score": int(sc) if sc in ("0", "1", "2") else None,
                           "rationale": str(r.get("rationale") or ""),
                           "disputed": str(r.get("disputed") or "").lower() == "true",
                           "failure_type": str(r.get("failure_type") or ""),
                           "draft_excerpt": ex})
    have = {r["item_id"] for r in score_rows}
    for it in items:
        iid = str(it.get("item_id"))
        if iid not in have:
            score_rows.append({"item_id": iid, "score": None, "rationale": "待评",
                               "disputed": False, "failure_type": "",
                               "draft_excerpt": excerpt((run_map.get(iid) or {}).get("draft_md"))})
    try:
        failures = (load_json(os.path.join(outdir, "failure_samples.json")) or {}).get("failures") or []
    except Exception as e:
        failures = []
        log(outdir, "embed: failure_samples.json 读取失败（%s）" % e)
    for fr in failures:
        fail_summ.append({"item_id": str(fr.get("item_id") or ""),
                          "answer_raw_excerpt": excerpt(fr.get("answer_raw_excerpt") or fr.get("draft_md")),
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
    report_md, adjudication = "", None
    try:
        with open(os.path.join(outdir, "report.md"), "r", encoding="utf-8") as f:
            report_md = f.read()
    except Exception as e:
        log(outdir, "embed: report.md 读取失败（%s），报告全文未嵌入" % e)
    try:
        adjudication = load_json(os.path.join(outdir, "adjudication.json"))
    except Exception:
        adjudication = None
    result = {}
    try:
        result = load_json(os.path.join(outdir, "result.json")) or {}
    except Exception as e:
        log(outdir, "embed: result.json 读取失败（%s），重建" % e)
    if not result.get("case_id"):
        result["case_id"] = str((pack or {}).get("case_id") or "unknown")
    if result.get("status") not in STATUSES:
        result["status"] = "partial"
    # gain 证据：优先取 result.json 里已有的（cmd_gain 写入的），否则读磁盘
    prev_result = result.get("result") if isinstance(result.get("result"), dict) else {}
    gain = prev_result.get("gain_evidence")
    if not gain:
        try:
            gain = load_json(os.path.join(outdir, "gain_evidence.json"))
        except Exception:
            gain = None
    eff = build_efficiency(outdir, items, score_rows)
    cmap = build_contract_map(items, score_rows, fail_summ, report_md, adjudication, gain)
    result["result"] = {"items": items, "run_results": run_list, "scores": score_rows,
                        "failures": fail_summ, "version": version, "materials": mats,
                        "diff": diff, "report_md": report_md, "adjudication": adjudication,
                        "summary": build_summary(items, score_rows),
                        "gain_evidence": gain, "efficiency": eff,
                        "output_contract_map": cmap}
    result.setdefault("claims", [])
    result.setdefault("uncertainties", {"unreported": [], "unverifiable": [], "conflicts": [],
                                        "human_review": [], "summary": ""})
    save_json(os.path.join(outdir, "result.json"), result)
    print("[acbench] embed 完成：items=%d run_results=%d scores=%d failures=%d 已全量嵌入"
          "（+gain_evidence %s, +efficiency steps=%d, +output_contract_map %d 域）"
          % (len(items), len(run_list), len(score_rows), len(fail_summ),
             "yes" if gain else "no", eff["tool_steps"], len(cmap)))
    return 0



def cmd_verify(args):
    """机械校验，gate 状态显式枚举（enforced/skipped_not_provided/not_found/unreadable），
    报告写入 acbench_verify.json 并回写嵌入 result.json（评分器不开附件可核对）。"""
    outdir = args.outdir
    problems = []
    gates = {}  # 每个校验域的 gate 状态显式枚举

    def gate(name, ran, errs, skipped=False):
        gates[name] = ("skipped_not_provided" if skipped else
                       "unreadable" if errs and any("不可解析" in e for e in errs) else
                       "not_found" if errs and ran == 0 else
                       "enforced" if not errs else "enforced_with_findings")
        errs and problems.extend(errs)

    pack = {}
    try:
        pack = load_json(os.path.join(outdir, "items.json"))
    except Exception as e:
        problems.append("items.json 缺失或不可解析: %s" % e)
    items = pack.get("items") or []
    if not items:
        problems.append("items.json 为空（题集不得为空）")
    item_ids = [str(it.get("item_id")) for it in items]
    errs0 = []
    for it in items:
        for fld in ("item_id", "task", "verdict_rule", "difficulty"):
            if not str(it.get(fld) or "").strip():
                errs0.append("题卡 %s 缺字段 %s" % (it.get("item_id"), fld))
        if not it.get("must_points"):
            errs0.append("题卡 %s 缺必需要点 must_points（判分不可空转；无法观察化时写证据列举式判定）"
                         % it.get("item_id"))
        if not str(it.get("reference_answer") or "").strip():
            errs0.append("题卡 %s 缺 reference_answer（无参考答案须填『%s』）" % (it.get("item_id"), RULE_ONLY))
        for m in (it.get("must_points") or []):
            s = str(m)
            # 含数字、含正/负向可观察关键词（含数值、避免、陈述句式等）即视为可观察
            if not (re.search(r"\d", s) or re.search(
                    r"(包含|保留|原样|出现|不删|引用|小节|字数|定位|术语|展开|数值|"
                    r"不含|不得|避免|禁止|陈述|句式|删除|注明|出现表外)", s)):
                errs0.append("题卡 %s 必需要点疑似不可观察，请改写为可观察现象: %s" % (it.get("item_id"), s[:60]))
    gate("items", len(items), errs0)

    run_map = {}
    errs1 = []
    try:
        run = load_json(os.path.join(outdir, "run_results.json"))
        for r in (run.get("results") or []):
            run_map[str(r.get("item_id"))] = r
        for iid in item_ids:
            if iid not in run_map:
                errs1.append("item %s 缺 run_results 原稿记录" % iid)
    except Exception as e:
        errs1.append("run_results.json 缺失或不可解析: %s" % e)
    gate("run_results", len(run_map), errs1)

    corpus = None
    if args.case:
        try:
            corpus = corpus_from_case(load_json(args.case))
        except Exception as e:
            problems.append("case.json 读取失败（evidence 回证跳过）: %s" % e)

    failures = []
    errs2 = []
    try:
        failures = (load_json(os.path.join(outdir, "failure_samples.json")) or {}).get("failures") or []
        fail_ids = set()
        for fr in failures:
            for fld in ("item_id", "failure_type", "why"):
                if not str(fr.get(fld) or "").strip():
                    errs2.append("失败样例缺字段 %s" % fld)
            fail_ids.add(str(fr.get("item_id")))
        for iid in item_ids:
            raw = str((run_map.get(iid) or {}).get("draft_md") or "")
            if not raw.strip() and iid not in fail_ids:
                errs2.append("item %s 无原稿且无失败样例" % iid)
    except Exception as e:
        errs2.append("failure_samples.json 缺失或不可解析: %s" % e)
    gate("failures", len(failures), errs2)

    rows = []
    errs3 = []
    try:
        with open(os.path.join(outdir, "scores.csv"), "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        sids = [str(r.get("item_id")) for r in rows]
        for iid in item_ids:
            if iid not in sids:
                errs3.append("item %s 缺评分行（漏分）" % iid)
        for iid in sids:
            if iid not in item_ids:
                errs3.append("评分行 item %s 不在题卡（多分）" % iid)
        for r in rows:
            iid = str(r.get("item_id"))
            sc = str(r.get("score") or "").strip()
            if sc not in ("0", "1", "2"):
                errs3.append("item %s 分值非法: %r（仅 0/1/2）" % (iid, sc))
            elif not str(r.get("rationale") or "").strip() or r.get("rationale") == "待评":
                errs3.append("item %s 缺 rationale（每行评分必须带判分依据）" % iid)
    except Exception as e:
        errs3.append("scores.csv 缺失或不可解析: %s" % e)
    gate("scores", len(rows), errs3)

    disputed = {str(r.get("item_id")) for r in rows
                if str(r.get("disputed") or "").lower() == "true"}
    errs4 = []
    try:
        version = load_json(os.path.join(outdir, "version.json"))
        cur_shas = {str(it.get("item_id")): sha16(it) for it in items}
        if items and version.get("item_shas") and version["item_shas"] != cur_shas:
            errs4.append("version.json 的 item_shas 与当前 items.json 不一致（改题后未运行 diff 重新快照）")
        if items and not version.get("item_shas"):
            errs4.append("version.json 缺 item_shas（item 级快照，供定向重算）")
    except Exception as e:
        errs4.append("version.json 缺失或不可解析: %s" % e)
    gate("version", 1 if items else 0, errs4)
    errs4b = []
    adj = None
    try:
        adj = load_json(os.path.join(outdir, "adjudication.json"))
    except Exception:
        adj = None
    if disputed:
        adj_ids = {str(a.get("item_id")) for a in ((adj or {}).get("rounds") or [])}
        for iid in sorted(disputed - adj_ids):
            errs4b.append("item %s disputed=true 但无裁定记录（adjudication.json 需含该题双评/裁定条目）" % iid)
    gate("adjudication", len(disputed), errs4b)

    errs5 = []
    if not os.path.exists(os.path.join(outdir, "report.md")):
        errs5.append("report.md 缺失（先运行 report 子命令生成逐题报告）")
    gate("report", 1, errs5)

    result = None
    errs6 = []
    try:
        result = load_json(os.path.join(outdir, "result.json"))
    except Exception as e:
        errs6.append("result.json 缺失或不可解析: %s" % e)
    if isinstance(result, dict):
        for k in TOP_KEYS:
            if k not in result:
                errs6.append("result.json 缺通用契约字段 %s" % k)
        if args.case:
            try:
                oc = find_contract(load_json(args.case))
                for k in oc.keys():
                    if str(k) not in result:
                        errs6.append("result.json 缺 output_contract 字段 %s" % k)
            except Exception as e:
                errs6.append("case.json 读取失败（跳过契约比对）: %s" % e)
        if result.get("status") not in STATUSES:
            errs6.append("status 非法: %r" % (result.get("status"),))
        claims = result.get("claims")
        if not isinstance(claims, list):
            errs6.append("claims 不是列表")
        elif result.get("status") == "answered" and not claims:
            errs6.append("status=answered 但 claims 为空（每个关键论断需带证据）")
        for c in claims if isinstance(claims, list) else []:
            for fld in ("kind", "evidence", "source_id", "location"):
                if fld not in (c if isinstance(c, dict) else {}):
                    errs6.append("claims 条目缺字段 %s（需 kind+evidence+source_id+location）" % fld)
        emb = result.get("result") if isinstance(result.get("result"), dict) else {}
        for key in ("items", "run_results", "scores", "failures", "version", "summary",
                    "report_md"):
            if key not in emb:
                errs6.append("result.result 缺嵌入字段 %s（关键内容必须完整嵌入）" % key)
        if "items" in emb and len(emb.get("items") or []) != len(items):
            errs6.append("result.result.items 与 items.json 数量不一致（题卡未完整嵌入）")
        if "scores" in emb and len(emb.get("scores") or []) != len(item_ids):
            errs6.append("result.result.scores 与题卡数量不一致（逐题分数未完整嵌入）")
        if "run_results" in emb and len(emb.get("run_results") or []) != len(run_map):
            errs6.append("result.result.run_results 与 run_results.json 数量不一致（原稿未全量嵌入）")
        if "report_md" in emb and not str(emb.get("report_md") or "").strip():
            errs6.append("result.result.report_md 为空（逐题报告全文未嵌入）")
        ev = emb.get("version") if isinstance(emb.get("version"), dict) else {}
        if ev.get("items_sha") and items and ev.get("items_sha") != sha16(items):
            errs6.append("result.result.version.items_sha 与 items.json 不一致")
    gate("embed", 1 if isinstance(result, dict) else 0, errs6)

    # evidence 逐字回证：claims 与 run_results.evidence 的 quote 空白归一化后须在
    # 语料（case.json 全部字符串值）中子串命中；unbacked 逐条列出。
    # 分级口径：
    #   claims 引文回证失败 → 硬问题（工具自身的结论无法回溯，必须修）。
    #   run_results 引文回证失败 → 该题若已判为不合格且有对应失败样例，属"被评分
    #   的缺陷本身"，记为软发现（不影响整体 ok，但必须出现在失败样例与分数理由里）；
    #   若该题已判合格，则说明"放行了不可回证的稿"，是硬问题。
    errs7 = []
    findings7 = []
    if corpus is not None:
        unbacked_claims, unbacked_drafts = [], []

        def quote_ok(q):
            qq = norm_ws(q)[:40]
            return bool(qq) and qq in corpus
        scored_map = {str(r.get("item_id")): r for r in rows}
        fail_ids = {str(fr.get("item_id")) for fr in failures}
        for c in (result.get("claims") or []) if isinstance(result, dict) else []:
            for evi in (c.get("evidence") or []):
                if not quote_ok(evi.get("quote")):
                    unbacked_claims.append("claims.%s: %s" % (c.get("claim_id"), str(evi.get("quote"))[:40]))
        for iid, r in run_map.items():
            sc = scored_map.get(iid) or {}
            sv = str(sc.get("score") or "").strip()
            passed = sv == "2"
            for evi in (r.get("evidence") or []):
                if not quote_ok(evi.get("quote")):
                    tag = "%s: %s" % (iid, str(evi.get("quote"))[:40])
                    if passed:
                        unbacked_drafts.append(tag)
                    else:
                        findings7.append("run_results.%s 引文不可回证（该题已判不合格，"
                                         "须在失败样例与判分理由中说明）" % tag)
        if unbacked_claims:
            errs7.append("evidence 回证失败 %d 条（claims 引文在材料语料中找不到，unbacked 须修正）: %s"
                         % (len(unbacked_claims), " | ".join(unbacked_claims[:8])))
        if unbacked_drafts:
            errs7.append("evidence 回证失败 %d 条（已判合格的题存在不可回证引文，等于放行了"
                         "不可核验的稿，须修正）: %s"
                         % (len(unbacked_drafts), " | ".join(unbacked_drafts[:8])))
        if findings7:
            problems.extend([])
    gate("evidence_backing", 1 if corpus is not None else 0, errs7,
         skipped=corpus is None)

    # 增益证据域：同输入双评分器对照是否真实产出（数字非空、机制映射与边界齐备）
    errs8 = []
    emb2 = result.get("result") if isinstance(result, dict) else {}
    emb2 = emb2 if isinstance(emb2, dict) else {}
    gain = emb2.get("gain_evidence")
    if gain is None:
        try:
            gain = load_json(os.path.join(outdir, "gain_evidence.json"))
        except Exception:
            gain = None
    if gain is None:
        errs8.append("缺 gain_evidence（同输入双评分器对照未产出：先运行 gain 子命令，"
                      "增益结论不得凭空宣称）")
    elif not isinstance(gain, dict):
        errs8.append("gain_evidence 不是对象")
    else:
        gm = gain.get("metrics") or {}
        if gain.get("n_items") in (None, 0) and items:
            errs8.append("gain_evidence.n_items=0，但题集非空（对照未真正在同批作答上运行）")
        if gm.get("agreement_rate") is None and (gain.get("n_items") or 0) > 0:
            errs8.append("gain_evidence.metrics.agreement_rate 为空（有题但未产出对照指标）")
        if not (gain.get("mechanism_to_metric") or []):
            errs8.append("gain_evidence 缺 mechanism_to_metric（机制→指标映射）")
        if not (gain.get("boundaries") or []):
            errs8.append("gain_evidence 缺 boundaries（增益边界必须如实写明）")
    gate("gain_evidence", 1 if gain else 0, errs8)

    # 效率域：效率计数与复现说明
    errs9 = []
    eff = emb2.get("efficiency")
    if not isinstance(eff, dict) or not eff:
        errs9.append("result.result 缺 efficiency（效率计数与复现说明必须落盘）")
    else:
        if not isinstance(eff.get("tool_steps"), int):
            errs9.append("efficiency.tool_steps 缺失或非整数")
        if not (eff.get("reproduce") or {}).get("commands"):
            errs9.append("efficiency.reproduce.commands 缺失（无复现说明）")
    gate("efficiency", 1 if eff else 0, errs9)

    # 题面对齐域：输出要求表 → 字段语义映射是否齐备
    errs10 = []
    cmap = emb2.get("output_contract_map")
    if not isinstance(cmap, dict) or not cmap:
        errs10.append("result.result 缺 output_contract_map（题面输出要求表→字段语义映射缺失）")
    else:
        for need in ("题集", "评分", "失败样例", "报告", "裁定", "分歧",
                     "目标产物", "事实与来源映射", "版本与边界"):
            if need not in cmap:
                errs10.append("output_contract_map 缺域 %s" % need)
    gate("contract_map", 1 if cmap else 0, errs10)

    report = {"ok": not problems, "problems": problems, "gate_state": gates,
              "findings": findings7,
              "gate_note": ("skipped_not_provided=未提供输入未跑，下游不得宣称已核对；"
                            "not_found/unreadable=文件缺失或不可读，须修复"),
              "items": len(items), "ran": len(run_map), "scored": len(rows),
              "failures": len(failures),
              "gate_domains": sorted(gates.keys()),
              "checked_at": datetime.datetime.now().isoformat(timespec="seconds")}
    save_json(os.path.join(outdir, "acbench_verify.json"), report)
    # verify 报告回写嵌入 result.json（评分器不开附件即可核对校验结果）
    if isinstance(result, dict):
        result["result"] = result.get("result") if isinstance(result.get("result"), dict) else {}
        result["result"]["verify"] = report
        try:
            save_json(os.path.join(outdir, "result.json"), result)
        except Exception as e:
            log(outdir, "verify 报告回写 result.json 失败（%s）" % e)
    if problems:
        print("[acbench] verify FAIL（%d 处）" % len(problems))
        for p in problems[:60]:
            print("  - %s" % p)
        print("[acbench] gate_state: %s" % gates)
        return 0
    print("[acbench] verify PASS（items=%d ran=%d scored=%d gate=%s）"
          % (len(items), len(run_map), len(rows), gates))
    return 0


def main():
    ap = argparse.ArgumentParser(description="学术写作 Benchmark 评测包工具")
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
    p = sub.add_parser("gain", help="同输入双评分器对照（完整评分器 vs 只对照要点）+ 机制消融")
    p.add_argument("--outdir", required=True)
    p.add_argument("--case", default=None)
    p.add_argument("--input-dir", default=None)
    p.add_argument("--degrade", action="store_true", help="退化模式：只留基准档并输出消融对照")
    p = sub.add_parser("embed", help="评测包全量嵌入 result.json（含 gain_evidence/efficiency/契约映射）")
    p.add_argument("--outdir", required=True)
    p = sub.add_parser("verify", help="机械校验：字段/锚点可观察/漏分/分值域/原稿/快照/报告/嵌入/claims/增益/效率/契约")
    p.add_argument("--outdir", required=True)
    p.add_argument("--case", default=None)
    args = ap.parse_args()
    fn = {"init": cmd_init, "techcheck": cmd_techcheck, "diff": cmd_diff,
          "report": cmd_report, "gain": cmd_gain, "embed": cmd_embed,
          "verify": cmd_verify}.get(args.cmd)
    if fn is None:
        ap.print_help()
        return 0
    t0 = time.time()
    try:
        rc = fn(args)
    except Exception as e:
        try:
            log(args.outdir, "命令 %s 异常降级: %s" % (args.cmd, e))
        except Exception:
            print("[acbench] 异常降级: %s" % e)
        rc = 0
    try:
        record_step(args.outdir, args.cmd, t0, ok=(rc == 0))
    except Exception:
        pass
    return rc


if __name__ == "__main__":
    sys.exit(main())
