#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""benchkit.py — benchkit v3 评测包工具（init / techcheck / diff / embed / verify）。

用法：
    python benchkit.py init     --case <case.json> --outdir <dir> [--input-dir <dir>]
    python benchkit.py techcheck --outdir <dir>
    python benchkit.py diff     --outdir <dir>
    python benchkit.py embed    --outdir <dir>
    python benchkit.py verify   --outdir <dir> [--case <case.json>]

设计约束：
- 任何输入（含损坏 JSON、空文件、未知结构）都不得抛裸异常、不得产出空结果：
  所有命令全捕获降级，仅打印警告并写 warn.log，退出码恒为 0（verify 的 FAIL 用报告文件与打印表达）。
- 技术检查只是确定性校验，不是 DSH 分数，也不是独立语义验证。
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

SCORE_FIELDS = ("item_id", "score", "rationale", "disputed", "failure_type", "answer_raw_excerpt")
TOP_KEYS = ("case_id", "status", "result", "claims", "uncertainties")
STATUSES = ("answered", "partial", "insufficient_evidence", "input_error")
RULE_ONLY = "仅规则评分"

TASK_KEYS = ("task", "question", "prompt", "instruction", "query", "requirement",
             "problem", "title", "ask")
ID_KEYS = ("item_id", "id", "qid", "question_id", "number", "index", "key")
REF_KEYS = ("reference_answer", "gold_answer", "gold", "expected_answer", "expected",
            "answer", "reference")
SRC_KEYS = ("source_text", "text", "source", "passage", "paragraph", "table_text",
            "evidence", "context", "material", "excerpt", "quote")
COND_KEYS = ("conditioning", "conditions", "constraints", "givens", "assumptions")
RULE_KEYS = ("scoring_rule", "grading_rule", "grading", "score_rule", "scoring",
             "rubric", "criteria")
INPUTREF_KEYS = ("input_ref", "source_ref", "source_id", "location", "page", "section")
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
    if not isinstance(w, dict):
        w = {"task": str(w)}
    task = first_key(w, TASK_KEYS)
    if isinstance(task, (dict, list)):
        task = json.dumps(task, ensure_ascii=False)
    src = first_key(w, SRC_KEYS)
    if isinstance(src, (dict, list)):
        src = json.dumps(src, ensure_ascii=False)
    cond = first_key(w, COND_KEYS)
    if isinstance(cond, str):
        cond = [cond]
    if not isinstance(cond, list):
        cond = []
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
        "conditioning": [str(c) for c in cond if str(c).strip()],
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
        "scoring_rule": "2=结论正确且带原文定位；1=部分正确；0=错误或未答",
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


def tech_check(item, answer):
    """确定性校验——不是 DSH 分数，也不是独立语义验证。"""
    src = str(item.get("source_text_snapshot") or "")
    ref = str(item.get("reference_answer") or "")
    ans = str(answer or "")
    checks = {"answer_empty": not ans.strip()}
    if ref and ref != RULE_ONLY:
        nums = re.findall(r"[-+]?\d+(?:\.\d+)?", ref)
        if nums:
            checks["ref_numbers_in_source"] = all(n in src for n in nums)
            checks["answer_covers_ref_numbers"] = all(n in ans for n in nums)
    cond = item.get("conditioning") or []
    if cond:
        cov = [{"condition": str(c)[:120], "ratio": token_cover(c, ans)} for c in cond if str(c)]
        checks["condition_coverage"] = cov
        checks["answer_covers_conditions"] = all(
            (str(c) in ans) or token_cover(c, ans) >= 0.6 for c in cond if str(c))
    return checks


def check_digest(results):
    return sha16([{"i": r.get("item_id"), "t": r.get("technical_check")}
                  for r in results])


def build_summary(items, score_rows):
    scored = [r for r in score_rows if r.get("score") in (0, 1, 2)]
    dist = {"0": 0, "1": 0, "2": 0}
    for r in scored:
        dist[str(int(r["score"]))] += 1
    return {
        "items_total": len(items),
        "items_with_reference": sum(1 for it in items if it.get("reference_answer") != RULE_ONLY),
        "items_rule_only": sum(1 for it in items if it.get("reference_answer") == RULE_ONLY),
        "score_dist": dist,
        "avg": (round(sum(int(r["score"]) for r in scored) / float(len(scored)), 3)
                if scored else None),
        "note": ("技术合成检查日志不是 DSH 分数也不是独立语义验证；来源是段落/表格文本，"
                 "不是 PDF 像素金标。六方面：任务定义=items 题卡；数据与答案管理=source_text_"
                 "snapshot+reference+version；评分维度=0/1/2 rubric+scores；原始输出留存="
                 "run_results 全量嵌入；误差分析=failure_samples；版本迭代=version+diff。"),
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
        r["technical_check_note"] = "确定性校验，不是 DSH 分数也不是独立语义验证"
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
        return any(v is False for k, v in c.items()
                   if isinstance(v, bool) and (k.startswith("answer_covers")
                                               or k == "ref_numbers_in_source"))
    passed = sum(1 for r in results if not check_fail(r.get("technical_check")))
    print("[benchkit] techcheck：ran=%d 全过=%d check_sha=%s（≠DSH 分数≠语义验证）"
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

    result = {}
    try:
        result = load_json(os.path.join(outdir, "result.json")) or {}
    except Exception as e:
        log(outdir, "embed: result.json 读取失败（%s），重建" % e)
    if not result.get("case_id"):
        result["case_id"] = str((pack or {}).get("case_id") or "unknown")
    if result.get("status") not in STATUSES:
        result["status"] = "partial"
    result["result"] = {"items": items, "run_results": run_list, "scores": score_rows,
                        "failures": fail_summ, "version": version, "materials": mats,
                        "diff": diff, "summary": build_summary(items, score_rows)}
    result.setdefault("claims", [])
    result.setdefault("uncertainties", {"unreported": [], "unverifiable": [], "conflicts": [],
                                        "human_review": [], "summary": ""})
    save_json(os.path.join(outdir, "result.json"), result)
    print("[benchkit] embed 完成：items=%d run_results=%d scores=%d failures=%d 已全量嵌入"
          % (len(items), len(run_list), len(score_rows), len(fail_summ)))
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
        for fld in ("item_id", "task", "scoring_rule", "difficulty"):
            if not str(it.get(fld) or "").strip():
                problems.append("题卡 %s 缺字段 %s" % (it.get("item_id"), fld))
        if "conditioning" not in it:
            problems.append("题卡 %s 缺 conditioning（source-conditioned 条件逐条保留）"
                            % it.get("item_id"))
        if not str(it.get("reference_answer") or "").strip():
            problems.append("题卡 %s 缺 reference_answer（无参考答案须填『%s』）"
                            % (it.get("item_id"), RULE_ONLY))

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
        for key in ("items", "run_results", "scores", "failures", "version", "summary"):
            if key not in emb:
                problems.append("result.result 缺嵌入字段 %s（关键内容必须完整嵌入）" % key)
        if "items" in emb and len(emb.get("items") or []) != len(items):
            problems.append("result.result.items 与 items.json 数量不一致（题卡未完整嵌入）")
        if "scores" in emb and len(emb.get("scores") or []) != len(item_ids):
            problems.append("result.result.scores 与题卡数量不一致（逐题分数未完整嵌入）")
        if "run_results" in emb and len(emb.get("run_results") or []) != len(run_map):
            problems.append("result.result.run_results 与 run_results.json 数量不一致（原始输出未全量嵌入）")
        ev = emb.get("version") if isinstance(emb.get("version"), dict) else {}
        if ev.get("items_sha") and items and ev.get("items_sha") != sha16(items):
            problems.append("result.result.version.items_sha 与 items.json 不一致")

    report = {"ok": not problems, "problems": problems, "items": len(items),
              "ran": len(run_map), "scored": len(rows), "failures": len(failures)}
    save_json(os.path.join(outdir, "benchkit_verify.json"), report)
    if problems:
        print("[benchkit] verify FAIL（%d 处）" % len(problems))
        for p in problems[:60]:
            print("  - %s" % p)
        return 0
    print("[benchkit] verify PASS（items=%d ran=%d scored=%d）"
          % (len(items), len(run_map), len(rows)))
    return 0


def main():
    ap = argparse.ArgumentParser(description="benchkit v3 评测包工具")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("init", help="抄契约+落骨架：六件落盘 + result.json 全键骨架")
    p.add_argument("--case", required=True)
    p.add_argument("--outdir", required=True)
    p.add_argument("--input-dir", default=None, help="材料目录（默认取 case.json 所在目录）")
    p = sub.add_parser("techcheck", help="确定性技术检查 + 复跑稳定性记录")
    p.add_argument("--outdir", required=True)
    p = sub.add_parser("diff", help="item 级版本对比：定向重算 + 可比性标记")
    p.add_argument("--outdir", required=True)
    p = sub.add_parser("embed", help="评测包全量嵌入 result.json")
    p.add_argument("--outdir", required=True)
    p = sub.add_parser("verify", help="机械校验：字段/漏分/分值域/原始输出/快照/嵌入/claims")
    p.add_argument("--outdir", required=True)
    p.add_argument("--case", default=None)
    args = ap.parse_args()
    fn = {"init": cmd_init, "techcheck": cmd_techcheck, "diff": cmd_diff,
          "embed": cmd_embed, "verify": cmd_verify}.get(args.cmd)
    if fn is None:
        ap.print_help()
        return 0
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
