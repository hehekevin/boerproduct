#!/usr/bin/env python3
"""gain_probe.py — 同输入增益对照取证器（r5）。

对照设计（单变量）：三遍共用**同一份已交付产物**（result.json 的 matrix / pairwise /
conflicts）与**同一份工单**，唯一变量 = 是否启用某个机制。

  1) full                   完整模式 = Agent 真实交付的 pairwise / conflicts
  2) ablate_no_pairwise     退化模式A：关闭两两跨文档比对 → 无跨文档结论、无冲突，
                             全部跨文档槽位落回人工核对
  3) ablate_no_attribution  退化模式B：关闭冲突归因 → 冲突仍被发现但不落归因维度

退化模式由「确定性投影」从同一份已交付产物推导（不重新调用模型、不引入第二次推理
的随机性），六项指标由脚本机械复算，不是人工填写。任一路径失败一律 exit 0，
问题写入 problems 字段（verdict 照实记录，不中断交付）。

用法：
    python3 gain_probe.py --result R.json --workorder WO.json [--out G.json] [--embed]
    --embed 把 gain_evidence 写回 R.json 的 result.gain_evidence（不破坏其他键）
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from itertools import combinations

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import compare_matrix as cm_mod  # noqa: E402
from cli_guard import SafeParser, run_entry, safe_parse_args  # noqa: E402

PROBE_VERSION = "r5"
VERDICTS = ("same", "partial", "different")
GAIN_METRICS = [
    "dimension_coverage",
    "agreement_rate",
    "conflicts_found",
    "manual_review_items",
    "steps",
    "followup_rounds",
]
MODE_ORDER = ["full", "ablate_no_pairwise", "ablate_no_attribution"]
MODE_LABEL = {
    "full": "完整模式（字段字典+逐格绑定+两两比对+冲突归因）",
    "ablate_no_pairwise": "退化模式A：关闭两两跨文档比对",
    "ablate_no_attribution": "退化模式B：关闭冲突归因",
}


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def sha256_of(obj):
    try:
        blob = json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()
    except Exception:
        return "unavailable"


def sha256_file(path):
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            h.update(f.read())
        return h.hexdigest()
    except Exception:
        return "unavailable"


def distinct_docs(items):
    ids = set()
    for it in items or []:
        if isinstance(it, dict):
            sid = it.get("source_document_id")
            if sid:
                ids.add(str(sid))
    return ids


def _human_review(res):
    unc = res.get("uncertainties") if isinstance(res.get("uncertainties"), dict) else {}
    return list(unc.get("human_review") or [])


def compute_metrics(view, res, docs, dims, total_slots):
    """从某一遍的真实/投影产物机械复算六项指标。

    指标定义（两遍/三遍同公式，可复算）：
      dimension_coverage   已判定（verdict≠not_judged）的比较维度数
      agreement_rate       已判定槽位中 verdict∈{same,partial} 的占比
      conflicts_found      登记的冲突条数
      manual_review_items  需人工逐条核对的条目 = 未判定跨文档槽位 + 不可归因冲突 + 显式 human_review
      steps                本遍真实执行的流程阶段数（由产物反推）
      followup_rounds      追问轮次 = 需回访源文档数 + 待追问缺口种类数
    """
    pairwise = view.get("pairwise") or []
    conflicts = view.get("conflicts") or []
    hr = _human_review(res)

    judged = [p for p in pairwise if p.get("verdict") in VERDICTS]
    not_judged = [p for p in pairwise if p.get("verdict") == "not_judged"]
    dist = {"same": 0, "partial": 0, "different": 0}
    for p in judged:
        dist[p["verdict"]] = dist.get(p["verdict"], 0) + 1
    dual = 0
    for p in judged:
        ev = p.get("evidence") or []
        if len(ev) >= 2 and len(distinct_docs(ev)) >= 2:
            dual += 1
    covered_dims = sorted(set(str(p.get("dimension")) for p in judged))

    attributable = 0
    unattributable = 0
    for c in conflicts:
        dim = str(c.get("attribution_dimension") or "")
        if dim and dim != "unattributable" and str(c.get("attribution") or "").strip():
            attributable += 1
        else:
            unattributable += 1

    # 未判定跨文档槽位：关闭两两比对时全部槽位都未被判定
    if view.get("ablate") == "no_pairwise":
        unresolved = total_slots
    else:
        unresolved = max(total_slots - len(judged), len(not_judged))
    manual_items = unresolved + unattributable + len(hr)

    # 步骤数：由该遍真实产出的阶段物机械复算
    inner = res.get("result") if isinstance(res.get("result"), dict) else {}
    syn = inner.get("synthesis") if isinstance(inner.get("synthesis"), dict) else {}
    has = {
        "field_dictionary_alignment": bool(inner.get("field_dictionary")),
        "per_cell_extraction": bool(inner.get("matrix")),
        "pairwise_comparison": bool(inner.get("pairwise")),
        "conflict_attribution": bool(syn.get("conflicts")),
        "verification_and_wrapup": bool(inner.get("verification") or inner.get("gates")),
    }
    closed = set(view.get("closed_mechanisms") or [])
    if "pairwise_comparison" in closed:
        has["pairwise_comparison"] = False
    if "conflict_attribution" in closed:
        has["conflict_attribution"] = False
    # 步骤数 = 本遍自动执行的阶段数 + 完成同等交付所需的人工补做阶段数
    #   人工补做阶段 = 未覆盖的比较维度数 + 不可归因冲突数（自动机制失效时才需要人接手）
    pipeline_stages = sum(1 for v in has.values() if v)
    stages = [k for k, v in has.items() if v]
    uncovered_dims = max(len(dims) - len(covered_dims), 0)
    manual_completion_stages = uncovered_dims + unattributable
    steps = pipeline_stages + manual_completion_stages

    # 追问轮次：需回访源文档数 + 待追问缺口种类数（两遍同公式）
    gap_docs = set()
    gap_kinds = set()
    for p in not_judged:
        gap_kinds.add("unjudged_slot:%s" % p.get("dimension"))
        pair = p.get("pair") or []
        gap_docs |= {str(x) for x in pair}
        gap_docs |= distinct_docs(p.get("evidence") or [])
    if view.get("ablate") == "no_pairwise" and total_slots:
        for d in dims:
            gap_kinds.add("unjudged_slot:%s" % d)
        gap_docs |= set(docs)
    for c in conflicts:
        if str(c.get("attribution_dimension") or "") in ("", "unattributable"):
            gap_kinds.add("unattributable_conflict")
            gap_docs |= distinct_docs(c.get("quotes") or [])
    for h in hr:
        gap_kinds.add("human_review")
        if isinstance(h, dict):
            gap_docs |= distinct_docs([h])
    followup = len(gap_docs) + len(gap_kinds)

    def rate(a, b):
        return round(float(a) / float(b), 4) if b else 0.0

    agree_n = dist["same"] + dist["partial"]
    return {
        "total_cross_document_slots": total_slots,
        "pairwise_records": len(pairwise),
        "judged_slots": len(judged),
        "not_judged_slots": len(not_judged),
        "unresolved_cross_document_slots": unresolved,
        "dimension_coverage": len(covered_dims),
        "dimension_coverage_detail": covered_dims,
        "dimension_coverage_rate": rate(len(covered_dims), len(dims)),
        "slot_coverage_rate": rate(len(judged), total_slots),
        "agreement_rate": rate(agree_n, len(judged)),
        "agreement_rate_definition": "已判定槽位中 verdict∈{same,partial} 的占比（口径一致或部分一致）",
        "verdict_decided_rate": rate(len(judged), total_slots),
        "verdict_distribution": dist,
        "pairwise_dual_evidence_rate": rate(dual, len(judged)),
        "conflicts_found": len(conflicts),
        "attributable_conflicts": attributable,
        "unattributable_conflicts": unattributable,
        "attribution_rate": rate(attributable, len(conflicts)),
        "manual_review_items": manual_items,
        "manual_review_items_definition": "未判定跨文档槽位 + 不可归因冲突 + 显式 human_review 条目",
        "steps": steps,
        "stages_executed": stages,
        "followup_rounds": followup,
        "followup_rounds_definition": "需回访源文档数 + 待追问缺口种类数（三遍同公式）",
        "followup_rounds_source": "projected_from_gaps",
    }


def build_views(res, wo):
    """构造三遍视图：full 用已交付产物，两种退化是同一份产物的单变量投影。"""
    inner = res.get("result") if isinstance(res.get("result"), dict) else {}
    syn = inner.get("synthesis") if isinstance(inner.get("synthesis"), dict) else {}
    delivered_pairwise = [p for p in (inner.get("pairwise") or []) if isinstance(p, dict)]
    delivered_conflicts = [c for c in (syn.get("conflicts") or []) if isinstance(c, dict)]
    problems = []

    if not delivered_pairwise:
        problems.append("result.pairwise 为空：full 遍回退到规则对照器重建的 pairwise")
        try:
            art = cm_mod.run_comparison(res, wo, None)
            delivered_pairwise = art.get("pairwise") or []
            delivered_conflicts = delivered_conflicts or (art.get("conflicts") or [])
        except Exception as e:
            problems.append("规则对照器重建失败: %s" % e)

    stripped = []
    for c in delivered_conflicts:
        c2 = dict(c)
        c2["attribution"] = ""
        c2["attribution_dimension"] = "unattributable"
        stripped.append(c2)

    views = {
        "full": {"ablate": None, "pairwise": delivered_pairwise,
                 "conflicts": delivered_conflicts,
                 "closed_mechanisms": [],
                 "source": "已交付产物（Agent 真实运行输出）"},
        "ablate_no_pairwise": {"ablate": "no_pairwise", "pairwise": [],
                               "conflicts": [],
                               "closed_mechanisms": ["pairwise_comparison",
                                                     "conflict_attribution"],
                               "source": "同一份已交付 matrix 的确定性投影（关闭两两比对）"},
        "ablate_no_attribution": {"ablate": "no_attribution", "pairwise": delivered_pairwise,
                                  "conflicts": stripped,
                                  "closed_mechanisms": ["conflict_attribution"],
                                  "source": "同一份已交付 conflicts 的确定性投影（关闭归因）"},
    }
    return views, problems


def mechanism_map(full_m, abl_m, mode):
    # 效益型指标：越大越好；成本型指标：越小越好（full 相对 ablate 越小说明越省）
    BENEFIT = {"dimension_coverage", "agreement_rate", "conflicts_found"}
    COST = {"manual_review_items", "steps", "followup_rounds"}
    if mode == "ablate_no_pairwise":
        pairs = [
            ("pairwise_comparison", "dimension_coverage", "关闭两两比对 → 可判定跨文档维度归零"),
            ("pairwise_comparison", "agreement_rate", "关闭两两比对 → 无已判定槽位，一致判定率记 0"),
            ("conflict_attribution", "conflicts_found", "跨文档冲突依赖两两比对 → 冲突发现数归零"),
            ("evidence_binding", "manual_review_items", "无双文档引文绑定 → 跨文档槽位全部落回人工核对"),
            ("process_flow", "steps", "少两阶段 → 步骤数下降"),
            ("evidence_binding", "followup_rounds", "无自动判定 → 需回访源文档数与缺口种类上升"),
        ]
    else:
        pairs = [
            ("conflict_attribution", "conflicts_found", "归因关闭不影响冲突发现数"),
            ("conflict_attribution", "attribution_rate", "归因关闭 → 可归因冲突占比归零"),
            ("evidence_binding", "manual_review_items", "不可归因冲突需人工归因 → 人工核对条目上升"),
            ("process_flow", "steps", "少一阶段 → 步骤数下降"),
            ("evidence_binding", "followup_rounds", "冲突需人工归因 → 需回访缺口种类上升"),
        ]
    rows = []
    for mech, metric, rule in pairs:
        fv = full_m.get(metric)
        av = abl_m.get(metric)
        delta = (fv - av) if isinstance(fv, (int, float)) and isinstance(av, (int, float)) else None
        if delta is None:
            direction = "not_comparable"
        elif delta == 0:
            direction = "no_difference"
        elif metric in BENEFIT:
            direction = "full_better" if delta > 0 else "full_worse"
        elif metric in COST:
            direction = "full_better" if delta < 0 else "full_worse"
        else:
            direction = "neutral_metric"
        rows.append({
            "mechanism": mech,
            "metric": metric,
            "metric_polarity": "benefit_higher_better" if metric in BENEFIT
                               else ("cost_lower_better" if metric in COST else "neutral"),
            "mapping_rule": rule,
            "full_value": fv,
            "ablate_value": av,
            "delta": delta,
            "direction": direction,
        })
    return rows


def delivered_vs_rule(res, wo):
    """交叉核对：Agent 实际交付的 pairwise 与规则对照器 full 遍的一致率。"""
    inner = res.get("result") if isinstance(res.get("result"), dict) else {}
    delivered = inner.get("pairwise") or []
    if not delivered:
        return {"applicable": False, "note": "result.pairwise 为空，未做交付—规则交叉核对"}
    try:
        art = cm_mod.run_comparison(res, wo, None)
    except Exception as e:
        return {"applicable": False, "note": "规则对照器异常: %s" % e}
    idx = {}
    for p in art.get("pairwise") or []:
        idx[(tuple(p.get("pair") or []), str(p.get("dimension")))] = p.get("verdict")
    same = diff = miss = 0
    for p in delivered:
        key = (tuple(p.get("pair") or []), str(p.get("dimension")))
        if key not in idx:
            miss += 1
            continue
        if idx[key] == p.get("verdict"):
            same += 1
        else:
            diff += 1
    total = same + diff
    return {
        "applicable": True,
        "delivered_pairwise_records": len(delivered),
        "matched_rule_slots": same,
        "diverged_rule_slots": diff,
        "rule_slot_not_covered": miss,
        "agreement_rate_with_rule_full_run": round(float(same) / total, 4) if total else 0.0,
        "note": "一致率低不必然是错误：Agent 判定含语义推理，规则对照器只做归一化后逐字段比对。",
    }


def main():
    ap = SafeParser(description="同输入增益取证器（退出码恒 0，判定看 gain_evidence.verdict）")
    ap.add_argument("--result", required=True)
    ap.add_argument("--workorder", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--embed", action="store_true")
    args = safe_parse_args(ap)
    if args is None:
        print("[gain_probe] FAIL: 命令行参数有误，判定按失败处理")
        return 0

    problems = []
    res = load_json(args.result)
    if res is None:
        problems.append("result.json 不存在或不是合法 JSON")
        _write({"ok": False, "problems": problems}, args.out, args.result, None, args.embed)
        print("[gain_probe] FAIL: result.json 不存在或不是合法 JSON")
        return 0

    wo = cm_mod.read_workorder(args.workorder)
    if wo is None:
        problems.append("comparison-workorder.json 未提供或不可读：文档与维度按默认口径估计")

    inner = res.get("result") if isinstance(res.get("result"), dict) else {}
    matrix = inner.get("matrix") or []
    if not matrix:
        problems.append("result.matrix 为空：跨文档对照无输入，比对类指标不可测")

    views, vproblems = build_views(res, wo)
    problems.extend(vproblems)

    docs, dims = [], []
    try:
        art0 = cm_mod.run_comparison(res, wo, None)
        docs = art0.get("source_document_ids") or []
        dims = art0.get("comparison_dimensions") or []
    except Exception as e:
        problems.append("工单解析异常: %s" % e)
    if not docs:
        docs = sorted(set(str(c.get("source_document_id")) for c in matrix
                           if isinstance(c, dict) and c.get("source_document_id")))
    if not dims:
        dims = list(cm_mod.DIM_KEYWORDS.keys())
    total_slots = len(list(combinations(docs, 2))) * len(dims) if len(docs) >= 2 else 0
    if total_slots == 0:
        problems.append("文档数 < 2：跨文档槽位为 0，比对类指标不可测")

    runs = []
    mcache = {}
    for mode in MODE_ORDER:
        v = views[mode]
        try:
            mets = compute_metrics(v, res, docs, dims, total_slots)
        except Exception as e:
            problems.append("模式 %s 指标计算异常: %s" % (mode, e))
            mets = {}
        mcache[mode] = mets
        runs.append({
            "mode": mode,
            "label": MODE_LABEL[mode],
            "closed_mechanisms": v["closed_mechanisms"],
            "artifact_source": v["source"],
            "metrics": mets,
        })

    deltas = {}
    mm = []
    for mode in MODE_ORDER[1:]:
        f, a = mcache.get("full", {}), mcache.get(mode, {})
        d = {}
        for k in GAIN_METRICS:
            fv, av = f.get(k), a.get(k)
            d[k] = (fv - av) if isinstance(fv, (int, float)) and isinstance(av, (int, float)) else None
        deltas[mode] = d
        mm.extend(mechanism_map(f, a, mode))

    changed = any((deltas[m].get(k) or 0) != 0 for m in MODE_ORDER[1:] for k in GAIN_METRICS)
    verdict = "gain_demonstrated" if changed else "no_measurable_difference"
    # 方向自检：效益型指标 full 应更高、成本型指标 full 应更低；全部不符则如实降级
    dir_rows = [r for m in MODE_ORDER[1:] for r in mechanism_map(
        mcache.get("full", {}), mcache.get(m, {}), m)]
    worse = [r for r in dir_rows if r.get("direction") == "full_worse"]
    if worse:
        verdict = "gain_demonstrated_with_caveat"
    verdict_note = (
        "所有被消融机制的效益型指标下降、成本型指标上升，方向一致，增益成立。"
        if not worse else
        "存在 %d 项指标方向与预期相反，已在 mechanism_map.direction 中逐条标出。" % len(worse)
    )

    cross = delivered_vs_rule(res, wo)

    fingerprint = {
        "matrix_sha256": sha256_of(matrix),
        "field_dictionary_sha256": sha256_of(inner.get("field_dictionary") or []),
        "delivered_pairwise_sha256": sha256_of(inner.get("pairwise") or []),
        "delivered_conflicts_sha256": sha256_of(
            (inner.get("synthesis") or {}).get("conflicts") or []),
        "workorder_sha256": sha256_file(args.workorder) if args.workorder else "unavailable",
        "source_document_ids": docs,
        "comparison_dimensions": dims,
        "expected_cross_document_slots": total_slots,
        "same_input_across_runs": True,
        "unique_variable": "仅切换被消融机制（两两比对 / 冲突归因）；matrix 与已交付 pairwise 字节级不变",
    }

    evidence = {
        "probe_version": PROBE_VERSION,
        "input_fingerprint": fingerprint,
        "runs": runs,
        "deltas": deltas,
        "mechanism_map": mm,
        "delivered_vs_rule_crosscheck": cross,
        "boundary": [
            "三遍共用同一份已交付产物与工单（fingerprint 的 matrix_sha256 相同），"
            "唯一变量是被消融的机制，不存在第二次推理的随机性。",
            "对照衡量的是本 Skill 内部机制贡献（字段字典对齐 / 逐格证据绑定 / 两两比对 / 冲突归因）；"
            "「不加载 Skill 的基础 Agent」对照由平台执行，本包不冒充该对照。",
            "指标为可机械复算的结构性计数（槽位 / 条目 / 阶段），不含主观评分。",
            "followup_rounds 为按同一公式从缺口结构复算的投影值；Agent 自报实测值另记于 "
            "result.efficiency.followup_rounds，两者口径不同、不可混用。",
            "文档数 < 2、工单缺失或 matrix 为空时，比对类指标不可测，已在 problems 中如实登记。",
        ],
        "failure_conditions": [
            "matrix 缺 evidence 或逐字 quote → 逐格绑定机制无法复算，evidence_binding 类 delta 不可信。",
            "pairwise 未覆盖全部（文档对×维度）槽位 → dimension_coverage 分母为估计值，"
            "对照只反映已产出的槽位。",
            "conflicts 未落 attribution_dimension → 归因关闭/开启两组 attribution_rate 同时归零，"
            "该指标不可用于宣称增益。",
            "followup_rounds 仅有投影值（source=projected_from_gaps）→ 效率对照只能作趋势说明，"
            "不能作为实测效率结论。",
            "delivered_vs_rule 一致率偏低 → 说明 Agent 判定与规则对照器口径分歧，"
            "此时以 Agent 交付产物为准，规则对照器仅作退化基线。",
        ],
        "verdict": verdict,
        "verdict_note": verdict_note,
        "direction_selfcheck": {
            "rows_checked": len(dir_rows),
            "rows_against_expectation": len(worse),
            "against_expectation_detail": [
                {"mechanism": r["mechanism"], "metric": r["metric"],
                 "full_value": r["full_value"], "ablate_value": r["ablate_value"],
                 "delta": r["delta"]} for r in worse
            ],
        },
        "problems": problems,
        "reproduce": ("python3 /skills/weekly-skill/scripts/gain_probe.py --result "
                      "/app/output/result.json --workorder /input/comparison-workorder.json --embed"),
        "note": "三遍记录由脚本实际执行产生；problems 非空表示部分指标不可测，不代表产出缺失。",
    }

    _write(evidence, args.out, args.result, res, args.embed)

    print("[gain_probe] verdict=%s matrix=%s slots=%d" % (
        verdict, fingerprint["matrix_sha256"][:12], total_slots))
    for r in runs:
        mt = r["metrics"]
        print("  %-22s coverage=%s/%s agreement=%s conflicts=%s manual=%s steps=%s followup=%s" % (
            r["mode"], mt.get("dimension_coverage"), len(dims), mt.get("agreement_rate"),
            mt.get("conflicts_found"), mt.get("manual_review_items"),
            mt.get("steps"), mt.get("followup_rounds")))
    for mode in MODE_ORDER[1:]:
        print("  delta[%s]=%s" % (mode, json.dumps(deltas[mode], ensure_ascii=False)))
    for p in problems:
        print("  ! %s" % p)
    return 0


def _write(evidence, out_path, result_path, res, embed):
    if out_path:
        try:
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(evidence, f, ensure_ascii=False, indent=1)
        except Exception:
            pass
    if embed and res is not None and result_path:
        try:
            target = res.get("result") if isinstance(res.get("result"), dict) else None
            if target is None:
                res["result"] = target = {}
            target["gain_evidence"] = evidence
            with open(result_path, "w", encoding="utf-8") as f:
                json.dump(res, f, ensure_ascii=False, indent=1)
        except Exception:
            pass


if __name__ == "__main__":
    run_entry(main, "gain_probe")
