#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gain_probe.py — 增益对照：同一校验器（verify_check.analyze）对同一输入跑
normal（五组全开）与 degraded（--ablate 关闭五组）两遍，得真实漏检差；
--inject-pollution 在副本上注入污染（聚合篡改/行数篡改/条件遗漏/删日志/删边界登记/
删复算/悬空映射），对照两模式捕获差。键归属：gain_evidence / efficiency 归本脚本。
退出码恒 0。
"""
import argparse, copy, json, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify_check import analyze, ABLATE_GROUPS, marker_hit

POLLUTIONS = ["agg_tamper", "row_count_tamper", "filter_drop", "log_drop", "boundary_drop", "recompute_drop", "dangling_mapping"]


def inject_pollution(result):
    """在副本上注入客观违规；返回 (副本, 注入明细)。"""
    p = copy.deepcopy(result)
    r = p.setdefault("result", {})
    notes = []
    qrs = r.get("query_results") or []
    if qrs:
        x = qrs[0]
        for alias in (x.get("aggregates") or {}):
            v = x["aggregates"][alias]
            if isinstance(v, (int, float)):
                x["aggregates"][alias] = round(float(v) + 0.5, 6)
                notes.append("agg_tamper: %s.%s %s -> %s" % (x.get("query_id"), alias, v, x["aggregates"][alias]))
                break
        if x.get("row_count"):
            x["row_count"] = int(x["row_count"]) + 3
            notes.append("row_count_tamper: %s row_count+3" % x.get("query_id"))
        if x.get("groups"):
            x["groups"][0]["count"] = int(x["groups"][0].get("count", 0)) + 2
            notes.append("group_count_tamper: %s groups[0].count+2" % x.get("query_id"))
    queries = r.get("queries") or []
    for q in queries:
        if q.get("filters"):
            dropped = q["filters"].pop()
            notes.append("filter_drop: %s 移除过滤条件 %s（条件遗漏）" % (q.get("query_id"), dropped))
            break
    if r.get("query_log"):
        removed = r["query_log"].pop()
        notes.append("log_drop: 移除日志 seq=%s（留痕缺失）" % removed.get("seq"))
    if r.get("boundary_registry"):
        removed = r["boundary_registry"].pop()
        notes.append("boundary_drop: 移除边界登记 %s" % removed.get("ref"))
    if r.get("recompute"):
        r["recompute"]["computed_by"] = "agent-manual"
        notes.append("recompute_drop: computed_by 改为 agent-manual（绕开机械复算）")
    if queries:
        q = queries[0]
        old = q.get("question_id")
        q["question_id"] = "GHOST-XX"
        notes.append("dangling_mapping: %s question_id %s -> GHOST-XX" % (q.get("query_id"), old))
    return p, notes


def catch_by_group(problems):
    out = {}
    for p in problems:
        tag = p.split("]", 1)[0].lstrip("[") if p.startswith("[") else "structure"
        out[tag] = out.get(tag, 0) + 1
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--result", required=True)
    ap.add_argument("--case", required=True)
    ap.add_argument("--work-dir", default="/app/work")
    ap.add_argument("--ablate", default="all")
    ap.add_argument("--emit-into", action="store_true")
    ap.add_argument("--inject-pollution", action="store_true")
    a = ap.parse_args()
    info = {"script": "gain_probe", "marker_hit": marker_hit(), "exit": 0}
    t0 = time.time()
    try:
        with open(a.result, "r", encoding="utf-8") as f:
            result = json.load(f)
        with open(a.case, "r", encoding="utf-8") as f:
            case = json.load(f)
        os.makedirs(a.work_dir, exist_ok=True)
        groups = set(ABLATE_GROUPS) if a.ablate == "all" else set(x for x in a.ablate.split(",") if x in ABLATE_GROUPS)
        clean_n = analyze(result, case, ablate=frozenset())
        clean_d = analyze(result, case, ablate=groups)
        cn, cd = catch_by_group(clean_n), catch_by_group(clean_d)
        pollution_notes, pol = [], {}
        if a.inject_pollution:
            p_copy, pollution_notes = inject_pollution(result)
            pol["normal"] = catch_by_group(analyze(p_copy, case, ablate=frozenset()))
            pol["degraded"] = catch_by_group(analyze(p_copy, case, ablate=groups))
            with open(os.path.join(a.work_dir, "gain_probe_polluted.json"), "w", encoding="utf-8") as f:
                json.dump(p_copy, f, ensure_ascii=False, indent=2)
        delta = {}
        for g in ABLATE_GROUPS:
            delta[g] = {"clean_normal": cn.get(g, 0), "clean_degraded": cd.get(g, 0),
                        "polluted_normal_caught": pol.get("normal", {}).get(g, 0),
                        "polluted_degraded_caught": pol.get("degraded", {}).get(g, 0)}
        n_norm = sum(pol.get("normal", {}).values())
        n_deg = sum(pol.get("degraded", {}).values())
        gain = {
            "available": True,
            "runs": [
                {"run": "clean_normal", "ablate": [], "problems": len(clean_n), "by_group": cn},
                {"run": "clean_degraded", "ablate": sorted(groups), "problems": len(clean_d), "by_group": cd},
                {"run": "polluted_normal", "ablate": [], "problems": n_norm, "by_group": pol.get("normal", {})},
                {"run": "polluted_degraded", "ablate": sorted(groups), "problems": n_deg, "by_group": pol.get("degraded", {})},
            ],
            "delta_normal_minus_degraded": {
                "polluted_problems_caught_diff": n_norm - n_deg,
                "per_group": delta,
                "pollutions_injected": len(pollution_notes),
                "caught_by_normal_mode": n_norm > 0,
            },
            "mechanism_to_metric_map": [
                {"mechanism": "mapping", "metric": "悬空映射/缺 question_id/越界列", "group": "mapping"},
                {"mechanism": "stat_recompute", "metric": "聚合值与行数机械复算一致", "group": "recompute"},
                {"mechanism": "boundary_registry", "metric": "空结果/缺失值必登记", "group": "boundary"},
                {"mechanism": "query_log", "metric": "issued+executed+时间戳留痕", "group": "log"},
                {"mechanism": "conservation", "metric": "组计数和=总行数", "group": "conservation"},
            ],
            "boundaries": ["本校验层 normal vs degraded 两模式对照，不等于平台基础 Agent 白板对照",
                           "退化模式只用于增益对照，不得当作交付自检结论"],
            "failure_conditions": ["case.json 无 datasets 键时 mapping 组降级为仅查 question_id 回溯",
                                   "数据集行以非 dict/矩阵提供时列名核对跳过（登记于 material_gaps）"],
        }
        wall = round(time.time() - t0, 3)
        eff = {"wall_clock_seconds_total": wall, "checker_runs": 6, "model_requests": None,
               "steps_count": len(analyze(result, case)) + len(clean_d) + n_norm + n_deg + len(pollution_notes),
               "reproduce": "python3 /skills/weekly-skill/scripts/gain_probe.py --result /app/output/result.json --case /input/case.json --work-dir /app/work --emit-into --inject-pollution"}
        if a.emit_into:
            r = result.setdefault("result", {})
            r["gain_evidence"], r["efficiency"] = gain, eff
            with open(a.result, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
        with open(os.path.join(a.work_dir, "gain_evidence.json"), "w", encoding="utf-8") as f:
            json.dump({"gain_evidence": gain, "efficiency": eff, "pollution_notes": pollution_notes}, f, ensure_ascii=False, indent=2)
        info.update({"clean_normal": len(clean_n), "clean_degraded": len(clean_d),
                     "polluted_normal": n_norm, "polluted_degraded": n_deg,
                     "pollutions": len(pollution_notes), "wall": wall})
    except Exception as e:
        info["error"] = str(e)
    print(json.dumps(info, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
