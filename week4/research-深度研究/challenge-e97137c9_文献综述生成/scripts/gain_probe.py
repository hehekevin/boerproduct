#!/usr/bin/env python3
"""gain_probe.py — 增益对照探针（lit-review-bind）。

同一输入跑两遍：正常模式（四组机械校验全部开启）与退化模式（--ablate all，
关闭段落-来源绑定 / 引用逐字回证 / 分歧对照与强度不越界 / 主题覆盖四组检查），
逐项对照可观测指标（全部实测，不臆造）：

  1. binding_missed      段落无来源漏检数（客观违规但校验层未捕获）
  2. quote_missed        编造/未回证引用漏检数
  3. dispute_missed      分歧登记/强度越界漏检数
  4. coverage_missed     主题归属/覆盖遗漏漏检数
  5. manual_review_items 需人工核对条目数；clarification_rounds 按每轮 3 条折算

另采集 efficiency 效率计数，并支持 --inject-pollution 生成污染副本做反例自测
（注入：无来源论断 / 编造引用 / 清空 omissions / 拆散分歧对照；正常模式须抓到，
退出码恒 0）。

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
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from verify_check import analyze  # noqa: E402
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


def group_bucket(item_name):
    """把 self_check 条目归入四组之一（按条目名前缀）。"""
    if ".source_bound" in item_name or item_name.endswith(".quote_backed") \
            or item_name.startswith("theme.items"):
        pass
    if item_name.endswith(".source_bound"):
        return "binding"
    if item_name.endswith(".quote_backed"):
        return "quote"
    if item_name.endswith(".two_sides") or item_name.endswith(".consensus_backed") \
            or item_name.endswith(".strength_bounded"):
        return "dispute"
    if item_name.startswith("theme."):
        return "coverage"
    return "other"


def objective_violations(res, case):
    """独立复算四类客观违规（与校验层分开实现，作为漏检真值）。"""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from draft_bind import analyze_binding, extract_texts
    from dispute_table import analyze_disputes
    from theme_group import analyze as analyze_theme
    b = analyze_binding(res, case if isinstance(case, dict) else {}, ablate="none")
    con = [p for p in (b.get("problems") or []) if "未绑定任何来源" in p or "不在输入文献集" in p
           or "不在 claims[]" in p or "无可用底本" in p]
    quo = [p for p in (b.get("problems") or []) if "无任何来源（无来源论断）" in p
           or "无 evidence 回证条目" in p]
    quo += ["unbacked_quote:%s" % u.get("claim") for u in (b.get("unbacked_quotes") or [])]
    d = analyze_disputes(res, ablate="none")
    dis = [p for p in (d.get("problems") or [])]
    t = analyze_theme(res, ablate="none")
    cov = [p for p in (t.get("problems") or [])]
    return {"binding": con, "quote": quo, "dispute": dis, "coverage": cov}


def mode_metrics(res, case, report, label):
    idx = check_index(report)
    inner = (res or {}).get("result") or {}
    gt = objective_violations(res, case)
    disabled = set(report.get("disabled_checks") or [])

    per_group_caught = {}
    for s in (report.get("self_check") or []):
        g = group_bucket(str(s.get("item")))
        per_group_caught.setdefault(g, 0)
        if s.get("applied") and s.get("match") is False:
            per_group_caught[g] += 1

    def missed(group, gt_key):
        obj = len(gt.get(gt_key) or [])
        c = per_group_caught.get(group, 0)
        if group in disabled:
            return obj  # 该组已关闭：客观违规全部漏检
        return max(obj - c, 0)

    binding_missed = missed("binding", "binding")
    quote_missed = missed("quote", "quote")
    dispute_missed = missed("dispute", "dispute")
    coverage_missed = missed("coverage", "coverage")

    unjudged = sum(1 for it in (inner.get("items") or [])
                   if isinstance(it, dict) and it.get("judged") is not True)
    manual_items = unjudged + binding_missed + quote_missed + dispute_missed + coverage_missed
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
            "binding_violations_objective": len(gt["binding"]),
            "binding_missed": binding_missed,
            "quote_violations_objective": len(gt["quote"]),
            "quote_missed": quote_missed,
            "dispute_violations_objective": len(gt["dispute"]),
            "dispute_missed": dispute_missed,
            "coverage_violations_objective": len(gt["coverage"]),
            "coverage_missed": coverage_missed,
            "manual_review_items": manual_items,
            "manual_review_breakdown": {"unjudged": unjudged,
                                        "binding_missed": binding_missed,
                                        "quote_missed": quote_missed,
                                        "dispute_missed": dispute_missed,
                                        "coverage_missed": coverage_missed},
            "steps_count": checks_executed + steps_done,
            "steps_detail": {"checks_executed": checks_executed,
                             "checks_disabled": len(report.get("disabled_checks") or []),
                             "flow_steps_total": len(steps_field),
                             "flow_steps_done": steps_done},
            "clarification_rounds": rounds,
        },
    }


def inject_pollution(res):
    """在副本上注入污染（不触碰交付文件本身）。返回 (polluted, plan)。"""
    p = copy.deepcopy(res or {})
    inner = p.setdefault("result", {})
    plan = []
    outline = inner.setdefault("outline", {})
    sections = outline.get("sections") or []
    # 污染1：无来源论断（段落清空 source_ids）
    for s in sections:
        for para in (s.get("paragraphs") or []):
            if isinstance(para, dict) and para.get("source_ids"):
                para["source_ids"] = []
                plan.append("%s 清空 source_ids（无来源论断）" % para.get("para_id"))
                break
        if plan:
            break
    # 污染2：编造引用（claims 里第一条的 quote 换成虚构文本）
    for c in (p.get("claims") or []):
        if isinstance(c, dict) and (c.get("evidence") or []):
            pid = str(c["evidence"][0].get("paragraph_id") or "")
            old = str(c["evidence"][0].get("quote") or "")[:40]
            c["evidence"][0]["quote"] = "This fabricated sentence never appears in any source text."
            plan.append("%s 编造引用（原 quote 前 40 字: %s…）" % (c.get("claim_id"), old))
            break
    # 污染3：清空 omissions（覆盖遗漏丢失）
    if inner.get("omissions"):
        inner["omissions"] = []
        plan.append("清空 omissions（引用遗漏登记丢失）")
    # 污染4：拆散分歧对照（把首个 disputed 的立场砍到 1 个）
    for d in (inner.get("disputes") or []):
        if isinstance(d, dict) and d.get("status") == "disputed":
            if d.get("positions") and len(d["positions"]) > 1:
                d["positions"] = d["positions"][:1]
                plan.append("%s 拆散分歧对照（立场砍到 1 方）" % d.get("dispute_id"))
            break
    if not plan:
        plan.append("（无可注入位置）")
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

    # --- 两遍真实运行：同一输入、同一份文件内容 ---
    t1 = time.time()
    rep_normal = analyze(copy.deepcopy(res), copy.deepcopy(case) if case else {},
                         ablate="none", case_state=case_state, outline_state="not_found")
    t_normal = time.time() - t1
    t2 = time.time()
    rep_degraded = analyze(copy.deepcopy(res), copy.deepcopy(case) if case else {},
                           ablate="all", case_state=case_state, outline_state="not_found")
    t_degraded = time.time() - t2

    m_normal = mode_metrics(res, case, rep_normal, "normal")
    m_normal["wall_clock_seconds"] = round(t_normal, 4)
    m_degraded = mode_metrics(res, case, rep_degraded, "degraded")
    m_degraded["wall_clock_seconds"] = round(t_degraded, 4)

    delta_keys = ("binding_missed", "quote_missed", "dispute_missed", "coverage_missed",
                  "manual_review_items", "steps_count", "clarification_rounds")
    delta = {}
    for k in delta_keys:
        a, b = m_normal["metrics"].get(k), m_degraded["metrics"].get(k)
        delta[k] = (round(a - b, 6) if isinstance(a, (int, float))
                    and isinstance(b, (int, float)) else None)

    mechanism_map = [
        {"metric": "binding_missed", "mechanism": "段落-来源绑定检查（非空段落 ⇒ source_ids 非空、"
         "来源必须在输入文献集内、claim_ids 不断链）",
         "formula": "客观违规数 − 被校验层捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后无来源论断不再判 FAIL，草稿句子可脱离文献自由发挥"},
        {"metric": "quote_missed", "mechanism": "引用逐字回证（claim 的 evidence.quote 须在来源"
         "正文/摘要中空白归一化后逐字命中）",
         "formula": "unbacked_quotes 数 + 无回证条目数", "higher_is_better": False,
         "degrade_effect": "关闭后编造引用不再被判 FAIL，读起来通顺但引文是假的"},
        {"metric": "dispute_missed", "mechanism": "分歧对照登记（disputed ⇒ ≥2 立场且双方文献不重叠；"
         "established ⇒ ≥2 来源；disputed claim ⇒ dispute_id 有效）",
         "formula": "客观违规数 − 被校验层捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后反面证据可被抹平成单线叙事，结论强度可越界"},
        {"metric": "coverage_missed", "mechanism": "主题归属与覆盖检查（keep ⇒ 归属≥1主题或登记"
         "遗漏；uncited 未登记 omissions；coverage 手填与机械重算不符）",
         "formula": "客观违规数 − 被校验层捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后文献可被静默丢弃，综述覆盖面不可核"},
        {"metric": "manual_review_items", "mechanism": "漏检 + 未判定条目合计",
         "formula": "unjudged + 四类漏检", "higher_is_better": False,
         "degrade_effect": "机器判定面缩小后，需人工逐条核对的条目增加"},
        {"metric": "steps_count", "mechanism": "四步线性流程 + 机械校验三元组自检",
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
        "退化模式关闭四组检查（binding/quote/dispute/coverage），枚举、结构守卫、verdict "
        "一致性等基础检查仍开启，因此退化侧漏检数是下界而非最坏情形。",
        "四类违规的客观真值由探针独立复算（与 verify_check 分开实现），口径一致时漏检数才可信。",
        "wall_clock_seconds 为本机两次 analyze 调用耗时，受机器负载影响，仅作同次对照参考。",
        "追问轮次是按约定批量（每轮 3 条）折算的估计量，不是实测交互次数。",
        "case.json 未提供文献正文时逐字回证退化为 evidence_table 摘录底本并登记 "
        "unverifiable_text，此时 quote 组的判据强度受限。",
    ]

    failure_conditions = [
        "result.json 不存在或不可解析 → 探针输出 FAIL 并以退出码 0 结束，不改交付物。",
        "case.json 缺失 → case_contract 闸门记 skipped_not_provided，契约字段校验跳过。",
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
                           ablate="none", case_state=case_state, outline_state="not_found")
        p_deg = analyze(copy.deepcopy(polluted), copy.deepcopy(case) if case else {},
                        ablate="all", case_state=case_state, outline_state="not_found")
        pm_n = mode_metrics(polluted, case, p_normal, "polluted_normal")
        pm_d = mode_metrics(polluted, case, p_deg, "polluted_degraded")
        gain_evidence["pollution_selftest"] = {
            "polluted_copy": os.path.abspath(p_path),
            "injected": plan,
            "normal_mode": {"verdict": p_normal.get("verdict"),
                            "problems": len(p_normal.get("problems") or []),
                            "binding_missed": pm_n["metrics"]["binding_missed"],
                            "quote_missed": pm_n["metrics"]["quote_missed"],
                            "dispute_missed": pm_n["metrics"]["dispute_missed"],
                            "coverage_missed": pm_n["metrics"]["coverage_missed"],
                            "problem_sample": (p_normal.get("problems") or [])[:8]},
            "degraded_mode": {"verdict": p_deg.get("verdict"),
                              "problems": len(p_deg.get("problems") or []),
                              "binding_missed": pm_d["metrics"]["binding_missed"],
                              "quote_missed": pm_d["metrics"]["quote_missed"],
                              "dispute_missed": pm_d["metrics"]["dispute_missed"],
                              "coverage_missed": pm_d["metrics"]["coverage_missed"],
                              "problem_sample": (p_deg.get("problems") or [])[:8]},
            "missed_detection_delta": {
                "binding_missed": pm_d["metrics"]["binding_missed"] - pm_n["metrics"]["binding_missed"],
                "quote_missed": pm_d["metrics"]["quote_missed"] - pm_n["metrics"]["quote_missed"],
                "dispute_missed": pm_d["metrics"]["dispute_missed"] - pm_n["metrics"]["dispute_missed"],
                "coverage_missed": pm_d["metrics"]["coverage_missed"] - pm_n["metrics"]["coverage_missed"],
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
        "papers_total": len([it for it in ((res.get("result") or {}).get("items") or [])
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
