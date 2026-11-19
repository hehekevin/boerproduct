#!/usr/bin/env python3
"""gain.py — 同输入双跑对照：把"机制→指标"增益证据嵌入 result.json。

做三件事（全部为真实运行，无预置数字）：
1. 在同一份输入上跑两遍抽取：full（全部机制开）与 ablated（关闭五源检索/逐字
   回证/冲突检测/逐行 claim/条件绑定），两遍都用同一抽取器 extract.py、同一输入。
2. 用同一套指标函数分别度量两遍，并额外度量**实际交付的 result.json**（Agent
   真实产出），得到三列对照。
3. 把对照表、机制→指标映射、边界与失效条件写进 result.json 的 gain_evidence；
   同时把可自动采集的效率计数写进 efficiency（含复现命令）。

用法：
    python3 gain.py --case /input/case.json --fields /input/target-fields.json \
        --paras /app/work/paragraphs.json --result /app/output/result.json \
        --out /app/work/gain-evidence.json

退出码恒 0；任何异常降级为报告项，绝不裸崩，绝不中断交付。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import extract as EX  # noqa: E402  同目录模块，纯标准库

ABLATED_SET = ["sweep", "verbatim", "conflict", "claim", "condition"]

MECH_MAP = [
    {"mechanism": "五源检索（正文/表格/图注/摘要/补充材料分别登记 search_log）",
     "ablation": "sweep",
     "expected_metric": "field_coverage_rate↑、conflicts_found↑（正文外的表格/图注值不再被发现）",
     "why": "只查正文时，仅出现在表格行或图注中的字段退化为 not_reported，跨源数值冲突也因只见到一侧而漏报。"},
    {"mechanism": "逐字回证（verbatim_number 必须逐字出现在引文内，且与 scalar 数值一致）",
     "ablation": "verbatim",
     "expected_metric": "numeric_verbatim_rate↑",
     "why": "关闭后允许值与引文脱钩（换算成小数、换用邻近他数），字面一致但语义/数值对应关系丢失。"},
    {"mechanism": "跨源冲突检测（同字段多来源不一致 → source_conflict 双方并列）",
     "ablation": "conflict",
     "expected_metric": "conflicts_found↑",
     "why": "关闭后静默取首个命中，把材料内部矛盾写成单一确定结论。"},
    {"mechanism": "逐行 claim 绑定（每 field_id 一条 claim-<field_id>）",
     "ablation": "claim",
     "expected_metric": "claim_coverage↑",
     "why": "关闭后结论与字段行脱钩，读者无法逐行回指证据。"},
    {"mechanism": "条件同源绑定（value 与成立条件同行同行抽取）",
     "ablation": "condition",
     "expected_metric": "condition_coverage↑",
     "why": "关闭后数值脱离样本/时间点/电压窗口语境，读者可能把条件性结论误读为普适结论。"},
]

BOUNDARIES = [
    "对照为**同一输入、同一抽取器的机制消融**，不是平台给出的『基础 Agent vs 加载 Skill』官方对照；"
    "官方对照由平台在 3 个固定案例上生成，本文件不替代、不预置其分数。",
    "两遍都由确定性抽取器执行，不含模型采样，因此指标衡量的是**协议机制本身**的贡献，"
    "不包含模型能力差异；模型带来的差异在 delivered 列体现。",
    "delivered 列的 numeric_verbatim_rate 需要段落库可用；PDF 场景若段落库缺失，该项记 null 并写明原因，不臆造。",
    "指标对字段集合规模与材料版式敏感：字段少、材料短时绝对差值小，判读以相对差与方向为准。",
]

FAILURE_CONDITIONS = [
    "输入缺 target-fields.json 或 case.json → 两遍都退化为空结果，对照表只有 0 值；此时该对照无判读意义，"
    "已在 evidence 中标记 degraded=true。",
    "材料无可抽取文本层（扫描件未 OCR）→ full 与 ablated 同为 extraction_failed，"
    "覆盖率差值趋零是真实反映，不得把差值解读为方法优势。",
    "材料极短（仅 1-2 段）→ 五源检索的额外收益无法体现；此时以 conflicts_found 与 claim_coverage 为主要判读项。",
    "抽取器词表未覆盖领域专有表述 → 该字段两遍都 not_reported，属口径问题不是机制问题。",
]


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def norm(s):
    return re.sub(r"\s+", "", s or "")


def nums_of(s):
    try:
        return re.findall(r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?", str(s or ""))
    except Exception:
        return []


def num_eq(a, b):
    try:
        fa, fb = float(a), float(b)
    except Exception:
        return False
    return abs(fa - fb) <= 1e-9 * max(1.0, abs(fa), abs(fb))


def para_library(case, paras_path):
    texts = {}
    try:
        for p in EX.harvest(case, paras_path):
            if p.get("pid") and p.get("text"):
                texts[str(p["pid"])] = str(p["text"])
    except Exception:
        pass
    return texts


def row_numeric(row):
    val = row.get("value") if isinstance(row.get("value"), dict) else {}
    return val.get("scalar") is not None or val.get("range") is not None


def metrics_of(doc, paras):
    """对一份 result 形状的文档计算机制指标（两遍与交付版共用同一函数）。"""
    fields = doc.get("fields") if isinstance(doc.get("fields"), list) else \
        (doc.get("result", {}).get("fields") if isinstance(doc.get("result"), dict) else [])
    fields = fields or []
    claims = doc.get("claims") if isinstance(doc.get("claims"), list) else []
    unc = doc.get("uncertainties") if isinstance(doc.get("uncertainties"), dict) else {}
    trace = doc.get("_trace") if isinstance(doc.get("_trace"), dict) else {}

    total = len(fields)
    cnt = {"reported": 0, "not_reported": 0, "source_conflict": 0, "extraction_failed": 0}
    numeric_rows = 0
    verbatim_ok = 0
    verbatim_checkable = 0
    cond_ok = 0
    for r in fields:
        if not isinstance(r, dict):
            continue
        st = r.get("status")
        cnt[st] = cnt.get(st, 0) + 1
        conds = r.get("conditions")
        if st == "reported" and isinstance(conds, list) and conds:
            cond_ok += 1
        if st == "reported" and row_numeric(r):
            numeric_rows += 1
            vn = str(r.get("verbatim_number") or "").strip()
            ev = r.get("evidence") if isinstance(r.get("evidence"), list) else []
            in_quote = False
            in_para = None
            for e in ev:
                if not isinstance(e, dict):
                    continue
                q = str(e.get("quote") or "")
                if vn and vn in q:
                    in_quote = True
                pid = str(e.get("paragraph_id") or "")
                if paras and pid in paras and q:
                    if norm(q) not in norm(paras[pid]):
                        in_para = False
                    else:
                        in_para = True
                        break
            ok = bool(vn) and in_quote
            if ok and row_numeric(r):
                val = r.get("value", {})
                sc = val.get("scalar")
                if sc is not None:
                    vn_nums = nums_of(vn)
                    if vn_nums and not num_eq(sc, vn_nums[0]):
                        ok = False
            verbatim_checkable += 1
            if ok:
                verbatim_ok += 1

    claim_ids = set()
    for c in claims:
        if isinstance(c, dict) and c.get("claim_id"):
            claim_ids.add(str(c["claim_id"]))
    claim_cov = 0
    for r in fields:
        if isinstance(r, dict) and ("claim-%s" % r.get("field_id")) in claim_ids:
            claim_cov += 1

    human_review = len(unc.get("human_review") or []) if isinstance(unc.get("human_review"), list) else 0

    return {
        "fields_total": total,
        "status_counts": cnt,
        "field_coverage_rate": round(cnt.get("reported", 0) / total, 4) if total else None,
        "numeric_rows": numeric_rows,
        "numeric_verbatim_rate": round(verbatim_ok / numeric_rows, 4) if numeric_rows else None,
        "verbatim_checkable_rows": verbatim_checkable,
        "quote_literal_check_available": bool(paras),
        "conflicts_found": cnt.get("source_conflict", 0),
        "claim_coverage": round(claim_cov / total, 4) if total else None,
        "condition_coverage": round(cond_ok / cnt.get("reported", 0), 4) if cnt.get("reported") else None,
        "human_review_items": human_review,
        "steps": trace.get("steps"),
        "requests": trace.get("probes"),
        "wall_clock_ms": trace.get("wall_clock_ms"),
    }


METRIC_KEYS = ["field_coverage_rate", "numeric_verbatim_rate", "conflicts_found",
               "claim_coverage", "condition_coverage", "human_review_items",
               "steps", "requests"]


def delta(full, abl):
    out = {}
    for k in METRIC_KEYS:
        a, b = full.get(k), abl.get(k)
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            out[k] = {"full": a, "ablated": b, "delta": round(a - b, 4)}
        else:
            out[k] = {"full": a, "ablated": b, "delta": None,
                      "note": "该列不可比（分母为 0 或数据不可得）"}
    return out


def input_fingerprint(case, fields, paras):
    """同输入指纹：证明两遍跑的是同一份输入。"""
    fp = {}
    try:
        if isinstance(case, dict):
            fp["case_id"] = case.get("case_id")
            src = case.get("source") if isinstance(case.get("source"), dict) else {}
            fp["source_title"] = src.get("title")
            fp["source_doi"] = src.get("doi")
            fp["material_keys"] = sorted([k for k in case.keys()
                                          if isinstance(case.get(k), (list, dict))])
    except Exception:
        pass
    fp["field_ids"] = [f[0] for f in fields]
    fp["field_count"] = len(fields)
    fp["paragraph_count"] = len(paras)
    fp["paragraph_digest"] = str(abs(hash(tuple(sorted(paras.items())))))[:12] if paras else "none"
    return fp


def auto_efficiency(delivered_metrics, paras, case):
    """可自动采集的效率计数（从已落盘的真实产物统计，不臆造）。"""
    eff = {
        "collection": "由 gain.py 从已落盘产物机械统计（可复现，无模型采样参与）",
        "fields_total": delivered_metrics.get("fields_total"),
        "reported_fields": (delivered_metrics.get("status_counts") or {}).get("reported"),
        "claims_total": (delivered_metrics.get("status_counts") or {}).get("reported", 0)
        + len((delivered_metrics.get("status_counts") or {}).get("not_reported", []) or []),
        "numeric_rows_verified": delivered_metrics.get("numeric_rows"),
        "verbatim_verified_rows": round((delivered_metrics.get("numeric_verbatim_rate") or 0)
                                         * (delivered_metrics.get("numeric_rows") or 0), 4)
        if delivered_metrics.get("numeric_verbatim_rate") is not None else None,
        "paragraphs_indexed": len(paras),
        "quote_literal_check_available": bool(paras),
        "human_review_items": delivered_metrics.get("human_review_items"),
        "conflicts_found": delivered_metrics.get("conflicts_found"),
    }
    eff["reproduce"] = {
        "gain_evidence": "python3 /skills/weekly-skill/scripts/gain.py --case /input/case.json "
                         "--fields /input/target-fields.json --paras /app/work/paragraphs.json "
                         "--result /app/output/result.json --out /app/work/gain-evidence.json",
        "ablation_full": "python3 /skills/weekly-skill/scripts/extract.py --case /input/case.json "
                         "--fields /input/target-fields.json --out /app/work/run-full.json",
        "ablation_degraded": "python3 /skills/weekly-skill/scripts/extract.py --case /input/case.json "
                              "--fields /input/target-fields.json --ablate sweep,verbatim,conflict,claim,condition "
                              "--out /app/work/run-ablated.json",
        "note": "命令路径按平台实际挂载位置（/skills/weekly-skill）书写；参数可原样复跑。",
    }
    eff["budget_note"] = ("模型请求数与墙钟由平台记录，不由本 Skill 自行声明；"
                          "此处仅列脚本侧可机械复算的计数。")
    return eff


def run(args):
    case = {}
    try:
        case = load_json(args.case)
    except Exception as e:
        print("[gain] case.json 读取失败: %s" % e)
    tf = None
    try:
        tf = load_json(args.fields)
    except Exception as e:
        print("[gain] target-fields.json 读取失败: %s" % e)
    fids, defs = EX.pick_fields(tf) if tf is not None else ([], {})
    fields = [(f, defs.get(f, {})) for f in fids]
    paras = para_library(case, args.paras)

    degraded = (not fields) or (not paras)

    t0 = time.time()
    full_doc = EX.extract(fields, case, args.paras, [])
    abl_doc = EX.extract(fields, case, args.paras, ABLATED_SET)
    arms_ms = int((time.time() - t0) * 1000)

    full_m = metrics_of(full_doc, paras)
    abl_m = metrics_of(abl_doc, paras)

    delivered_m = None
    delivered_doc = None
    try:
        delivered_doc = load_json(args.result)
        delivered_m = metrics_of(delivered_doc, paras)
    except Exception as e:
        print("[gain] 交付版 result.json 读取失败（delivered 列留空）: %s" % e)

    evidence = {
        "comparison_type": "same_input_mechanism_ablation",
        "what_this_is": ("在同一份输入、同一抽取器上跑两遍：full=全部机制开启，ablated=同时关闭五源检索/"
                         "逐字回证/跨源冲突检测/逐行 claim/条件绑定；两遍数字均为脚本真实运行所得。"),
        "what_this_is_not": ("这不是平台『基础 Agent vs 加载 Skill』的官方对照（该对照由平台在 3 个固定案例上"
                             "生成），也不预置任何官方分数；此处只度量本 Skill 协议机制自身的贡献。"),
        "input_fingerprint": input_fingerprint(case, fields, paras),
        "degraded": degraded,
        "degraded_reason": ("输入缺字段表或段落库为空，双跑无判读意义" if degraded else None),
        "arms": {
            "full": {"label": "全部机制开启", "metrics": full_m,
                     "trace": full_doc.get("_trace", {})},
            "ablated": {"label": "关闭 %s" % ",".join(ABLATED_SET), "metrics": abl_m,
                        "trace": abl_doc.get("_trace", {})},
            "delivered": {"label": "本次实际交付的 result.json（Agent 真实产出）",
                          "metrics": delivered_m,
                          "note": "与两遍同源同输入，用于观察模型执行协议后的实际落点"},
        },
        "delta_full_minus_ablated": delta(full_m, abl_m),
        "mechanism_to_metric": MECH_MAP,
        "boundaries": BOUNDARIES,
        "failure_conditions": FAILURE_CONDITIONS,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "both_arms_wall_clock_ms": arms_ms,
    }

    if delivered_doc is not None:
        try:
            delivered_doc["gain_evidence"] = evidence
            delivered_doc["efficiency"] = auto_efficiency(delivered_m or {}, paras, case)
            d = os.path.dirname(args.result)
            if d:
                os.makedirs(d, exist_ok=True)
            with open(args.result, "w", encoding="utf-8") as f:
                json.dump(delivered_doc, f, ensure_ascii=False, indent=1)
        except Exception as e:
            print("[gain] 写回 result.json 失败: %s" % e)

    try:
        d = os.path.dirname(args.out)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(evidence, f, ensure_ascii=False, indent=1)
    except Exception as e:
        print("[gain] 证据文件写盘失败: %s" % e)

    print("[gain] 对照完成（full vs ablated）：")
    for k in METRIC_KEYS:
        dd = evidence["delta_full_minus_ablated"][k]
        print("  %-26s full=%s ablated=%s delta=%s" % (
            k, dd["full"], dd["ablated"], dd["delta"]))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--fields", default="/input/target-fields.json")
    ap.add_argument("--paras", default=None)
    ap.add_argument("--result", default="/app/output/result.json")
    ap.add_argument("--out", default="/app/work/gain-evidence.json")
    args = ap.parse_args()
    try:
        return run(args)
    except Exception as e:
        print("[gain] 未捕获异常已兜底: %s" % e)
        return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[gain] 未捕获异常已兜底: %s" % e)
        sys.exit(0)
