#!/usr/bin/env python3
"""gain_probe.py — 增益对照探针（lit-classify）。

同一输入跑两遍：正常模式（四组机械校验全部开启）与退化模式（--ablate all，
关闭体系命中 / 引用回证 / 同键同类 / 边界待复核登记四组检查），逐项对照
可观测指标（全部实测，不臆造）：

  1. taxonomy_missed      体系外路径/未声明体系漏检数
  2. evidence_missed      引用回证缺失漏检数（quote 不在原文 / claims 无对应）
  3. consistency_missed   同键同类违规漏检数
  4. pending_missed       未判定/边界条目待复核漏登记数
  5. manual_review_items  需人工核对条目数；clarification_rounds 按每轮 3 条折算

另采集 efficiency 效率计数，并支持 --inject-pollution 生成污染副本做反例自测
（正常模式须抓到污染项，退出码恒 0）。污染注入四类：体系外路径、依据缺失、
同键不同判、待复核登记丢失。

**本脚本只产出对照证据；退化模式仅用于增益对照，不得用于交付自检。**
用法：
    python3 gain_probe.py --result /app/output/result.json --case /input/case.json \
        --work-dir /app/work --emit-into [--inject-pollution]
退出码：恒为 0（结论记在 verdict 字段与 stdout，不中断交付）。
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from verify_check import analyze, norm, node_ids, source_text, REG_BOUNDARY  # noqa: E402
except Exception as e:  # pragma: no cover
    print("[gain_probe] 无法导入 verify_check: %s" % e)
    sys.exit(0)

ROUND_BATCH = 3  # 追问轮次折算：每轮最多消化 3 条人工条目


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_json(path, obj):
    try:
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)
        return True
    except Exception as e:
        print("[gain_probe] 写盘失败 %s: %s" % (path, e))
        return False


def check_index(report):
    out = {}
    for s in report.get("self_check") or []:
        if isinstance(s, dict) and s.get("item"):
            out[s["item"]] = s
    return out


def caught(idx, key):
    e = idx.get(key)
    return bool(e and e.get("applied") and e.get("match") is False)


def objective_violations(res, case_state="enforced", case=None):
    """独立复算四类客观违规（与校验层分开实现，作为漏检真值）。"""
    inner = (res or {}).get("result") or {}
    items = [it for it in (inner.get("items") or []) if isinstance(it, dict)]
    claims = [c for c in (res.get("claims") or []) if isinstance(c, dict)]
    pending_reg = [p for p in (inner.get("pending_review") or []) if isinstance(p, dict)]
    conflicts = inner.get("conflicts") or []
    ids = node_ids(inner.get("taxonomy") or {})
    tax, evid, cons, pend = [], [], [], []

    claim_ids = {str(c.get("source_id") or "") for c in claims}
    for i, it in enumerate(items):
        iid = str(it.get("item_id") or i)
        pp = it.get("primary_path")
        if pp and ids and str(pp) not in ids:
            tax.append(iid)
        if pp:
            quote = norm(it.get("evidence_quote"))
            src = norm(source_text(case or {}, it.get("source_ref"), iid)) \
                if (case_state == "enforced" and case) else ""
            if not quote or not src or quote not in src or iid not in claim_ids:
                evid.append(iid)
        if it.get("judged") is not True:
            if not str(it.get("pending_reason") or "").strip() or \
               not any(str(p.get("item_id")) == iid for p in pending_reg):
                pend.append(iid)
        elif it.get("boundary") in REG_BOUNDARY:
            if not any(str(p.get("item_id")) == iid for p in pending_reg):
                pend.append(iid)

    # 同键同类真值（独立重算，不读 result.consistency）
    groups = {}
    for it in items:
        key = str(it.get("key_signature") or "").strip()
        pp = it.get("primary_path")
        if key and pp:
            groups.setdefault(key, []).append((str(it.get("item_id") or ""), str(pp)))
    for key, members in sorted(groups.items()):
        paths = sorted({p for _iid, p in members})
        if len(paths) <= 1:
            continue
        member_ids = [iid for iid, _p in members]
        rec = [c for c in conflicts if isinstance(c, dict)
               and set(str(x) for x in (c.get("item_ids") or [])) >= set(member_ids)]
        resolved = bool(rec) and any(str(c.get("resolution")) in ("merged", "escalated") for c in rec)
        if not resolved:
            cons.append("%s:%s" % (key, ",".join(member_ids)))
    return {"taxonomy": tax, "evidence": evid, "consistency": cons, "pending": pend}


def count_caught(items, idx):
    """按 self_check 三元组统计被校验层捕获的违规数。"""
    t = sum(1 for i in range(len(items)) if caught(idx, "items[%d].taxonomy_path_hit" % i))
    e = sum(1 for i in range(len(items)) if caught(idx, "items[%d].evidence_verbatim" % i)
            or caught(idx, "items[%d].claims_backed" % i))
    c = sum(1 for i in range(len(items)) if caught(idx, "items[%d].consistency_same_key" % i))
    p = sum(1 for i in range(len(items)) if caught(idx, "items[%d].pending_registered" % i))
    return t, e, c, p


def mode_metrics(res, report, label, case_state="enforced", case=None):
    idx = check_index(report)
    inner = (res or {}).get("result") or {}
    items = [it for it in (inner.get("items") or []) if isinstance(it, dict)]
    gt = objective_violations(res, case_state=case_state, case=case)
    t_c, e_c, c_c, p_c = count_caught(items, idx)

    disabled = set(report.get("disabled_checks") or [])
    tax_missed = len(gt["taxonomy"]) if "taxonomy" in disabled else max(len(gt["taxonomy"]) - t_c, 0)
    evid_missed = len(gt["evidence"]) if "evidence" in disabled else max(len(gt["evidence"]) - e_c, 0)
    cons_missed = len(gt["consistency"]) if "consistency" in disabled else max(len(gt["consistency"]) - c_c, 0)
    pend_missed = len(gt["pending"]) if "pending" in disabled else max(len(gt["pending"]) - p_c, 0)

    unjudged = sum(1 for it in items if it.get("judged") is not True)
    manual_items = unjudged + tax_missed + evid_missed + cons_missed + pend_missed

    checks_executed = sum(1 for s in (report.get("self_check") or [])
                          if isinstance(s, dict) and s.get("applied"))
    steps_field = inner.get("steps") or []
    steps_done = sum(1 for s in steps_field if isinstance(s, dict)
                     and str(s.get("status") or "done").lower() in ("done", "ok", "completed"))
    rounds = int(math.ceil(manual_items / float(ROUND_BATCH))) if manual_items else 0

    return {
        "mode": label,
        "ablate": report.get("ablate"),
        "verdict": report.get("verdict"),
        "problems": len(report.get("problems") or []),
        "metrics": {
            "taxonomy_violations_objective": len(gt["taxonomy"]),
            "taxonomy_caught": t_c,
            "taxonomy_missed": tax_missed,
            "evidence_violations_objective": len(gt["evidence"]),
            "evidence_caught": e_c,
            "evidence_missed": evid_missed,
            "consistency_violations_objective": len(gt["consistency"]),
            "consistency_caught": c_c,
            "consistency_missed": cons_missed,
            "pending_violations_objective": len(gt["pending"]),
            "pending_caught": p_c,
            "pending_missed": pend_missed,
            "manual_review_items": manual_items,
            "manual_review_breakdown": {"unjudged": unjudged,
                                        "taxonomy_missed": tax_missed,
                                        "evidence_missed": evid_missed,
                                        "consistency_missed": cons_missed,
                                        "pending_missed": pend_missed},
            "steps_count": checks_executed + steps_done,
            "steps_detail": {"checks_executed": checks_executed,
                             "checks_disabled": len(report.get("disabled_checks") or []),
                             "flow_steps_total": len(steps_field),
                             "flow_steps_done": steps_done},
            "clarification_rounds": rounds,
        },
    }


def inject_pollution(res):
    """在副本上注入四类污染（不触碰交付文件本身）。返回 (polluted, plan)。"""
    p = copy.deepcopy(res or {})
    inner = p.setdefault("result", {})
    plan = []
    items = [it for it in (inner.get("items") or []) if isinstance(it, dict)]
    classified = [it for it in items if it.get("primary_path")]
    if classified:
        it0 = classified[0]
        it0["evidence_quote"] = None
        it0["primary_path"] = "T-FAKE-99"
        plan.append("%s 清空 evidence_quote 并改为体系外路径 T-FAKE-99（体系外类目+依据缺失）"
                    % it0.get("item_id"))
        same_key = [x for x in classified[1:]
                    if x.get("key_signature") and x.get("key_signature") == it0.get("key_signature")]
        if same_key:
            it1 = same_key[0]
            it1["primary_path"] = "T-OTHER-01"
            plan.append("%s 与 %s 同键但改判不同路径（同类不同判）" % (it1.get("item_id"), it0.get("item_id")))
        elif len(classified) > 1:
            it1 = classified[1]
            it1["primary_path"] = "T-OTHER-01"
            plan.append("%s 改为另一体系外路径（不同键亦属体系外）" % it1.get("item_id"))
    if inner.get("pending_review"):
        inner["pending_review"] = []
        plan.append("清空 pending_review（待复核登记丢失）")
    if inner.get("conflicts"):
        inner["conflicts"] = []
        plan.append("清空 conflicts（同键同类处置记录丢失）")
    p["claims"] = []
    plan.append("清空 claims（证据链缺失）")
    if not plan:
        plan.append("（无可注入位置：items 为空）")
    return p, plan


def count_files(root):
    n = 0
    try:
        for _dirpath, _dirnames, filenames in os.walk(root):
            n += len(filenames)
    except Exception:
        pass
    return n


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", default="/app/output/result.json")
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--work-dir", default="/app/work")
        ap.add_argument("--out", default=None)
        ap.add_argument("--emit-into", action="store_true",
                        help="把 gain_evidence 写入 result.json 的 result.gain_evidence")
        ap.add_argument("--inject-pollution", action="store_true",
                        help="额外生成污染副本做反例自测")
        args = ap.parse_args()
    except Exception as e:
        print("[gain_probe] 参数解析失败（已降级）: %s" % e)
        return 0

    t0 = time.time()
    res = load_json(args.result)
    if not isinstance(res, dict):
        print("[gain_probe] FAIL: result.json 不存在或不可解析: %s（不中断交付）" % args.result)
        return 0
    case = load_json(args.case)
    case_state = "enforced" if isinstance(case, dict) else "skipped_not_provided"
    rub = load_json(os.path.join(args.work_dir or ".", "taxonomy.json")) \
        if os.path.exists(os.path.join(args.work_dir or ".", "taxonomy.json")) else None
    taxonomy_state = "enforced" if isinstance(rub, dict) else "not_found"

    # --- 两遍真实运行：同一输入、同一份文件内容 ---
    t1 = time.time()
    rep_normal = analyze(copy.deepcopy(res), copy.deepcopy(case) if case else {},
                         ablate="none", case_state=case_state, taxonomy_state=taxonomy_state)
    t_normal = time.time() - t1
    t2 = time.time()
    rep_degraded = analyze(copy.deepcopy(res), copy.deepcopy(case) if case else {},
                           ablate="all", case_state=case_state, taxonomy_state=taxonomy_state)
    t_degraded = time.time() - t2

    m_normal = mode_metrics(res, rep_normal, "normal", case_state, case if isinstance(case, dict) else {})
    m_normal["wall_clock_seconds"] = round(t_normal, 4)
    m_degraded = mode_metrics(res, rep_degraded, "degraded", case_state, case if isinstance(case, dict) else {})
    m_degraded["wall_clock_seconds"] = round(t_degraded, 4)

    delta_keys = ("taxonomy_missed", "evidence_missed", "consistency_missed",
                  "pending_missed", "manual_review_items", "steps_count",
                  "clarification_rounds")
    delta = {}
    for k in delta_keys:
        a, b = m_normal["metrics"].get(k), m_degraded["metrics"].get(k)
        delta[k] = (round(a - b, 6) if isinstance(a, (int, float))
                    and isinstance(b, (int, float)) else None)

    mechanism_map = [
        {"metric": "taxonomy_missed", "mechanism": "体系事前声明检查（declared_at + "
         "dimensions.nodes）+ primary_path/tags 命中体系 node_id",
         "formula": "客观违规数 − 被校验层捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后体系外类目（凭空造类）不再被判 FAIL"},
        {"metric": "evidence_missed", "mechanism": "引用回证（evidence_quote 逐字出现在 "
         "case.json 该条目原文 + claims 证据链对应条目）",
         "formula": "无回证的已归类条目数", "higher_is_better": False,
         "degrade_effect": "关闭后依据缺失/标签与原文对不上不再判 FAIL，判定退化为关键词猜类"},
        {"metric": "consistency_missed", "mechanism": "同键同类复算（key_signature 独立重算"
         "分组，同键不同判须 conflicts 登记 merged/escalated）",
         "formula": "客观违规数 − 被校验层捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后同类不同判、重复下载改判不一致不再可检出"},
        {"metric": "pending_missed", "mechanism": "待复核登记检查（未判定/边界情形 ⇒ "
         "pending_review 含 reason+needed_action；escalated 冲突须进入）",
         "formula": "客观违规数 − 被校验层捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后边界情形可静默漏登记，人工复核入口丢失"},
        {"metric": "manual_review_items", "mechanism": "漏检 + 未判定条目合计",
         "formula": "unjudged + 四类漏检", "higher_is_better": False,
         "degrade_effect": "机器判定面缩小后，需人工逐条核对的条目增加"},
        {"metric": "steps_count", "mechanism": "线性流程 + 机械校验三元组自检",
         "formula": "校验层已执行检查项数 + 流程层已完成步骤数", "higher_is_better": None,
         "degrade_effect": "关闭检查项会减少执行计数，但换来漏检——步骤少不等于质量高"},
        {"metric": "clarification_rounds", "mechanism": "把人工核对条目按每轮 %d 条打包"
         "（公式随记录落盘）" % ROUND_BATCH,
         "formula": "ceil(manual_review_items / %d)" % ROUND_BATCH,
         "higher_is_better": False,
         "degrade_effect": "人工条目越多，回原文/回问所需的轮次越多"},
    ]

    boundaries = [
        "对照对象是本校验层自身的正常模式与退化模式，不是平台基础 Agent 与参赛 Agent 的"
        "平台白板对照；平台对照结论由平台生成，本探针不代替、不冒充。",
        "退化模式关闭四组检查（taxonomy/evidence/consistency/pending），枚举、结构守卫、"
        "coverage 汇总一致性等基础检查仍开启，因此退化侧漏检数是下界而非最坏情形。",
        "四类违规的客观真值由探针独立复算（与 verify_check 分开实现），口径一致时漏检数才可信。",
        "wall_clock_seconds 为本机两次 analyze 调用耗时，受机器负载影响，仅作同次对照参考。",
        "追问轮次是按约定批量（每轮 3 条）折算的估计量，不是实测交互次数。",
    ]

    failure_conditions = [
        "result.json 不存在或不可解析 → 探针输出 FAIL 并以退出码 0 结束，不改交付物。",
        "case.json 缺失 → case_contract 闸门记 skipped_not_provided，原文回证校验跳过。",
        "taxonomy 未事前声明时体系命中真值不可得，taxonomy_missed 记 0 但属『无法判定』而非『无违规』。",
        "把 --ablate 的退化结果当作交付自检结论即为误用。",
        "污染反例自测只在副本上注入，原 result.json 不被修改。",
    ]

    gain_evidence = {
        "probe_version": "1.0",
        "probe_tool": "scripts/gain_probe.py",
        "case_id": res.get("case_id"),
        "input": {"result_path": os.path.abspath(args.result),
                  "case_path": os.path.abspath(args.case),
                  "case_contract_state": case_state,
                  "same_input_for_both_runs": True,
                  "run_order": ["normal", "degraded"],
                  "note": "两遍均读取同一份 result.json 内容（深拷贝传入校验函数，不做原地修改）"},
        "runs": [m_normal, m_degraded],
        "delta_normal_minus_degraded": delta,
        "mechanism_to_metric_map": mechanism_map,
        "boundaries": boundaries,
        "failure_conditions": failure_conditions,
        "interpretation_rule": "delta>0 且指标为 lower_is_better 时表示机制带来增益"
                               "（漏检减少）；delta=0 表示该指标在本输入上无区分度。",
    }

    if args.inject_pollution:
        polluted, plan = inject_pollution(res)
        p_path = os.path.join(args.work_dir or ".", "gain_probe_polluted.json")
        save_json(p_path, polluted)
        p_normal = analyze(copy.deepcopy(polluted), copy.deepcopy(case) if case else {},
                           ablate="none", case_state=case_state, taxonomy_state=taxonomy_state)
        p_deg = analyze(copy.deepcopy(polluted), copy.deepcopy(case) if case else {},
                        ablate="all", case_state=case_state, taxonomy_state=taxonomy_state)
        pm_n = mode_metrics(polluted, p_normal, "polluted_normal", case_state,
                            case if isinstance(case, dict) else {})
        pm_d = mode_metrics(polluted, p_deg, "polluted_degraded", case_state,
                            case if isinstance(case, dict) else {})
        gain_evidence["pollution_selftest"] = {
            "polluted_copy": os.path.abspath(p_path),
            "injected": plan,
            "normal_mode": {"verdict": p_normal.get("verdict"),
                            "problems": len(p_normal.get("problems") or []),
                            "taxonomy_missed": pm_n["metrics"]["taxonomy_missed"],
                            "evidence_missed": pm_n["metrics"]["evidence_missed"],
                            "consistency_missed": pm_n["metrics"]["consistency_missed"],
                            "pending_missed": pm_n["metrics"]["pending_missed"],
                            "problem_sample": (p_normal.get("problems") or [])[:8]},
            "degraded_mode": {"verdict": p_deg.get("verdict"),
                              "problems": len(p_deg.get("problems") or []),
                              "taxonomy_missed": pm_d["metrics"]["taxonomy_missed"],
                              "evidence_missed": pm_d["metrics"]["evidence_missed"],
                              "consistency_missed": pm_d["metrics"]["consistency_missed"],
                              "pending_missed": pm_d["metrics"]["pending_missed"],
                              "problem_sample": (p_deg.get("problems") or [])[:8]},
            "missed_detection_delta": {
                "taxonomy_missed": pm_d["metrics"]["taxonomy_missed"]
                                   - pm_n["metrics"]["taxonomy_missed"],
                "evidence_missed": pm_d["metrics"]["evidence_missed"]
                                   - pm_n["metrics"]["evidence_missed"],
                "consistency_missed": pm_d["metrics"]["consistency_missed"]
                                      - pm_n["metrics"]["consistency_missed"],
                "pending_missed": pm_d["metrics"]["pending_missed"]
                                  - pm_n["metrics"]["pending_missed"],
                "problems": (len(p_deg.get("problems") or [])
                             - len(p_normal.get("problems") or [])),
            },
            "caught_by_normal_mode": bool(p_normal.get("problems")),
            "note": "污染仅注入副本；正常模式须抓到污染项，退化模式漏检属预期。",
        }

    elapsed = round(time.time() - t0, 4)
    try:
        size_bytes = os.path.getsize(args.result)
    except Exception:
        size_bytes = None
    efficiency = {
        "collected_by": "scripts/gain_probe.py（自动采集）",
        "wall_clock_seconds_total": elapsed,
        "result_bytes": size_bytes,
        "input_files_scanned": count_files(os.path.dirname(os.path.abspath(args.case))),
        "checker_runs": 2,
        "checker_checks_executed_normal": m_normal["metrics"]["steps_detail"]["checks_executed"],
        "checker_checks_executed_degraded": m_degraded["metrics"]["steps_detail"]["checks_executed"],
        "checker_checks_disabled_degraded": m_degraded["metrics"]["steps_detail"]["checks_disabled"],
        "items_total": len([it for it in ((res.get("result") or {}).get("items") or [])
                            if isinstance(it, dict)]),
        "manual_review_items_normal": m_normal["metrics"]["manual_review_items"],
        "manual_review_items_degraded": m_degraded["metrics"]["manual_review_items"],
        "clarification_rounds_normal": m_normal["metrics"]["clarification_rounds"],
        "clarification_rounds_degraded": m_degraded["metrics"]["clarification_rounds"],
        "model_requests": None,
        "model_requests_note": "模型请求数由 Agent 侧记录（不可由本脚本采集），"
                               "交付前按实际请求次数回填；缺失时保持 null，不得臆造。",
        "reproduce": "python3 /skills/weekly-skill/scripts/gain_probe.py "
                     "--result /app/output/result.json --case /input/case.json "
                     "--work-dir /app/work --emit-into --inject-pollution",
    }

    out_path = args.out or os.path.join(args.work_dir or ".", "gain_evidence.json")
    save_json(out_path, {"gain_evidence": gain_evidence, "efficiency": efficiency})

    if args.emit_into:
        try:
            cur = load_json(args.result)
            if isinstance(cur, dict) and isinstance(cur.get("result"), dict):
                cur["result"]["gain_evidence"] = gain_evidence
                cur["result"]["efficiency"] = efficiency
                save_json(args.result, cur)
        except Exception as e:
            print("[gain_probe] 回写 result.json 失败: %s" % e)

    print("[gain_probe] 正常模式 verdict=%s ｜ 退化模式 verdict=%s"
          % (m_normal["verdict"], m_degraded["verdict"]))
    for name in delta_keys:
        a, b = m_normal["metrics"].get(name), m_degraded["metrics"].get(name)
        print("  %-22s normal=%s  degraded=%s  delta=%s" % (name, a, b, delta.get(name)))
    if "pollution_selftest" in gain_evidence:
        ps = gain_evidence["pollution_selftest"]
        print("  污染反例: caught_by_normal_mode=%s（注入 %d 项）"
              % (ps["caught_by_normal_mode"], len(ps["injected"])))
    print("[gain_probe] 证据落盘: %s" % os.path.abspath(out_path))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[gain_probe] 未预期异常（已降级，不中断交付）: %s" % e)
        sys.exit(0)
