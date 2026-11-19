#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gain_eval.py — 使用增益取证（同输入双跑对照 · 真实运行证据）

目的: 为 result.json 的 gain_evidence 字段产出**真实跑出来的数字**，而不是文字自述。
两个实验, 全部基于同一批输入文件:

  实验 A 同输入双跑 (same_input_ablation)
    arm=full      : 全部机检开启 (seven_check + plan_check)
    arm=degraded  : 同一输入, 机检关闭 (--ablate all), 模拟"不加载本 Skill 的基础 Agent"
    记录: 每臂的真实 verdict / checks 数 / 通过率 / 需人工核对条目数 / 步骤数。

  实验 B 污染反例 (defect_detection_probe)
    在同一输入的**确定性污染副本**上双跑:
    full 能抓到缺陷 (verdict=fail, 逐条 problem), degraded 抓不到 (机检已关),
    两臂的 defects_caught 差值 = 本 Skill 机检层的**检测力证据**。

机制→指标映射 (mechanism_to_metric): 每条 Skill 机制对应它实际影响的对照指标与取证位置。
边界 (boundaries): 明确本对照**不能**证明什么 (不替代平台官方 base-vs-skill 对照;
不衡量 LLM 文笔质量; 只衡量机检层的可核验覆盖与人工返工量)。

纯标准库, 零外部依赖, 不调模型, 恒 exit 0。
用法:
  python3 gain_eval.py --draft /app/output/proposal.md --route /app/work/route.jsonl \
    --milestones /app/work/milestones.jsonl --constraints /app/work/constraints.json \
    --plan /app/work/plan.jsonl --risks /app/work/risk_table.jsonl \
    --out /app/output/gain_evidence.json
"""
import argparse, json, os, shutil, sys, tempfile, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import seven_check  # noqa: E402
import plan_check  # noqa: E402


def read_lines(path):
    rows = []
    if not path or not os.path.exists(path):
        return rows
    with open(path, encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows


def run_arm(draft, route, milestones, constraints, plan, risks, ablate):
    """跑一臂: seven_check + plan_check, 返回真实报告。"""
    t0 = time.time()
    seven = seven_check.run_checks(draft=draft, route=route, milestones=milestones,
                                   constraints=constraints, ablate=ablate)
    t1 = time.time()
    plan_rows = read_lines(plan)
    ms_rows = read_lines(milestones)
    risk_rows = read_lines(risks)
    con = {}
    if constraints and os.path.exists(constraints):
        try:
            con = json.load(open(constraints, encoding="utf-8"))
        except Exception:
            con = {}
    pc = plan_check.evaluate(plan_rows, ms_rows, risk_rows, con, ablate=ablate,
                             ok_p=bool(plan_rows), ok_m=bool(ms_rows), ok_r=bool(risk_rows))
    t2 = time.time()
    sm = seven.get("metrics", {})
    pm = pc.get("metrics", {})
    metrics = {
        "section_completeness_rate": sm.get("section_completeness_rate"),
        "route_executability_pass_rate": sm.get("route_executability_pass_rate"),
        "timeline_consistency_rate": sm.get("timeline_consistency_rate"),
        "manual_check_items": (sm.get("manual_check_items") or 0) + (pm.get("manual_check_items") or 0),
        "steps": {
            "automated_check_steps": (sm.get("checks_total") or 0) + (pm.get("checks_total") or 0),
            "seven_check_steps": sm.get("checks_total"),
            "plan_check_steps": pm.get("checks_total"),
            "model_requests": 0,
        },
        "checks_total": (sm.get("checks_total") or 0) + (pm.get("checks_total") or 0),
        "checks_verified": (sm.get("checks_verified") or 0),
        "checks_failed": (sm.get("checks_failed") or 0) + (pm.get("checks_failed") or 0),
        "checks_unverified": (sm.get("checks_unverified") or 0) + (pm.get("checks_unverified") or 0),
        "machine_verified_ratio": None,
        "defects_caught": (seven.get("fail") or 0) + (pc.get("fail") or 0),
    }
    if metrics["checks_total"]:
        metrics["machine_verified_ratio"] = round(
            metrics["checks_verified"] / float(metrics["checks_total"]), 4)
    return {
        "label": "Skill 全量机检" if not ablate else "退化对照（机检关闭）",
        "ablate": sorted(set(ablate or [])),
        "seven_check": {"verdict": seven.get("verdict"), "fail": seven.get("fail"),
                        "gates": seven.get("gates"),
                        "failures": (seven.get("failures") or [])[:50],
                        "checks_total": seven.get("checks_total"),
                        "checks_matched": seven.get("checks_matched"),
                        "notes": seven.get("notes")},
        "plan_check": {"verdict": pc.get("verdict"), "fail": pc.get("fail"),
                       "problems": (pc.get("problems") or [])[:50],
                       "goals": pc.get("goals"), "milestones": pc.get("milestones"),
                       "risks": pc.get("risks"), "notes": pc.get("notes")},
        "metrics": metrics,
        "wall_seconds": round((t2 - t0), 3),
        "script_invocations": 2,
    }


def make_polluted_copy(draft, route, milestones, workdir):
    """确定性污染副本: 删 route 一步的 output 字段 + 里程碑周期越界。注入点固定可复现。"""
    os.makedirs(workdir, exist_ok=True)
    out = {}

    # 污染 route: 最后一步去掉 output (B 机检字段缺失)
    rows = read_lines(route)
    if rows:
        p = os.path.join(workdir, "route.jsonl")
        with open(p, "w", encoding="utf-8") as f:
            for i, r in enumerate(rows):
                if i == len(rows) - 1 and isinstance(r, dict):
                    r = dict(r)
                    r.pop("output", None)
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        out["route"] = p

    # 污染 milestones: 最后一条周期改为超出上限 (C 机检超期)
    ms = read_lines(milestones)
    if ms:
        p = os.path.join(workdir, "milestones.jsonl")
        with open(p, "w", encoding="utf-8") as f:
            for i, m in enumerate(ms):
                if i == len(ms) - 1 and isinstance(m, dict):
                    m = dict(m)
                    m["period"] = "第37-48月"
                f.write(json.dumps(m, ensure_ascii=False) + "\n")
        out["milestones"] = p
    return out


def rate_delta(a, b):
    if a is None or b is None:
        return None
    return round(float(a) - float(b), 4)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--draft", default=None)
    ap.add_argument("--route", default=None)
    ap.add_argument("--milestones", default=None)
    ap.add_argument("--constraints", default=None)
    ap.add_argument("--plan", default=None)
    ap.add_argument("--risks", default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    notes = []
    full = run_arm(args.draft, args.route, args.milestones, args.constraints,
                   args.plan, args.risks, None)
    degraded = run_arm(args.draft, args.route, args.milestones, args.constraints,
                       args.plan, args.risks, "all")

    # 实验 B: 污染副本双跑
    probe = {"enabled": False, "note": "缺少 route/milestones 输入，未做污染反例"}
    tmp = None
    try:
        tmp = tempfile.mkdtemp(prefix="gain_probe_")
        pol = make_polluted_copy(args.draft, args.route, args.milestones, tmp)
        if pol:
            probe = {
                "enabled": True,
                "injection": "route 末步删除 output 字段；milestones 末条周期改为第37-48月",
                "same_input_for_both_arms": True,
                "full": run_arm(args.draft, pol.get("route"), pol.get("milestones"),
                                args.constraints, args.plan, args.risks, None),
                "degraded": run_arm(args.draft, pol.get("route"), pol.get("milestones"),
                                    args.constraints, args.plan, args.risks, "all"),
            }
            probe["defects_caught_full"] = probe["full"]["metrics"]["defects_caught"]
            probe["defects_caught_degraded"] = probe["degraded"]["metrics"]["defects_caught"]
            probe["detection_margin"] = (probe["defects_caught_full"]
                                         - probe["defects_caught_degraded"])
            probe["note"] = ("full 抓到 %d 条缺陷，degraded 因机检关闭抓到 %d 条；"
                             "差额即机检层检测力。" % (probe["defects_caught_full"],
                                                   probe["defects_caught_degraded"]))
    except Exception as e:
        probe = {"enabled": False, "note": "污染反例执行异常: %s" % str(e)[:160]}
    finally:
        if tmp and os.path.isdir(tmp):
            try:
                shutil.rmtree(tmp, ignore_errors=True)
            except Exception:
                pass

    fm, dm = full["metrics"], degraded["metrics"]
    comparison = []
    for key, label, unit, definition in (
        ("section_completeness_rate", "章节完整率", "ratio",
         "七要素必备章节中经机检逐条命中并回证到正文的比例（分母固定 9 项）"),
        ("route_executability_pass_rate", "路线可执行性通过率", "ratio",
         "技术路线步骤中 input/output/depends/resources 齐全、依赖真实、归属有效里程碑的比例"),
        ("timeline_consistency_rate", "时间表一致率", "ratio",
         "里程碑条目中周期能在正文逐字回证、交付物齐全且不超给定周期的比例"),
        ("manual_check_items", "需人工核对条目数", "count",
         "失败项 + 未核验项：交付前仍需人工逐条确认的条目数量（越低越好）"),
        ("steps", "步骤数", "count",
         "达成同一交付所需的人工步骤量：机检步骤数 + 残留人工核对条目"),
    ):
        fv = fm.get(key)
        dv = dm.get(key)
        if key == "steps":
            fv = (fm["steps"]["automated_check_steps"] or 0) + (fm["manual_check_items"] or 0)
            dv = (dm["steps"]["automated_check_steps"] or 0) + (dm["manual_check_items"] or 0)
        comparison.append({
            "metric": key, "label": label, "unit": unit, "definition": definition,
            "full": fv, "degraded": dv, "delta": rate_delta(fv, dv),
            "better_when": "higher" if key.endswith("rate") else "lower",
        })

    mechanism_to_metric = [
        {"mechanism": "七要素章节完整性机检 (seven_check §A)",
         "metric": "section_completeness_rate",
         "how": "对正文逐条关键词命中并给出行号定位，缺项计 fail",
         "evidence": "arms.full.seven_check.checks 中 check=A_section_completeness"},
        {"mechanism": "技术路线可执行性机检 (seven_check §B)",
         "metric": "route_executability_pass_rate",
         "how": "route.jsonl 每步五字段齐全 + 依赖 sid 真实 + 归属有效里程碑",
         "evidence": "arms.full.seven_check.checks 中 check=B_route_*"},
        {"mechanism": "时间表-内容一致性机检 (seven_check §C)",
         "metric": "timeline_consistency_rate",
         "how": "里程碑周期在正文逐字回证 + 正文区间必有里程碑 + 不超 constraints.total_months",
         "evidence": "arms.full.seven_check.checks 中 check=C_timeline_*"},
        {"mechanism": "闸门状态显式枚举 (enforced/skipped/not_found/unreadable/ablation)",
         "metric": "machine_verified_ratio",
         "how": "未运行的检查输出 applied=false 占位，不计入通过率，强制人工接管",
         "evidence": "arms.degraded.seven_check.checks 中 applied=false 的条目数"},
        {"mechanism": "问题-目标-周期-风险四表机检 (plan_check)",
         "metric": "manual_check_items",
         "how": "孤儿目标/不可考核标准/超期/风险四件套缺失逐条报出并给出 gid/rid",
         "evidence": "arms.full.plan_check.problems"},
        {"mechanism": "分片写作 + 全文内嵌 + 骨架先行 (SKILL.md 强制协议)",
         "metric": "steps",
         "how": "把整稿拆成 3 次分片响应写入，脚本侧合并内嵌，取代一次性长稿反复重写",
         "evidence": "SKILL.md §强制执行协议 2/4/5 条；arms.*.metrics.steps.model_requests=0"},
    ]

    boundaries = [
        "本对照的 degraded 臂是**本 Skill 机检层的退化**，不是官方基础 Agent 的真实产出；"
        "官方 base-vs-skill 对照由平台固定案例统一生成，本包不预置、不替代。",
        "同输入双跑证明的是「机检层把多少条目从人工核对转为机器核验」，"
        "不衡量 LLM 文笔、立论深度或学科正确性。",
        "章节/路线/时间表三率的分母在两臂完全一致（同一批输入文件），"
        "因此差值只可能来自机检开关，不含输入差异。",
        "实验 B 的污染副本使用确定性注入（route 末步删 output、里程碑末条改周期），"
        "缺陷位置固定、可复跑；注入细节写入 injection 字段，不隐藏。",
        "requires_human 计数是机检视角的下界：真实人工核对量还包含内容判断与学科规范判断。",
        "本对照不产生任何 benchmark 分数；平台记录的对照与白板以平台为准。",
    ]

    efficiency = {
        "gain_eval_model_requests": 0,
        "gain_eval_script_invocations": 4,
        "gain_eval_wall_seconds": round(full["wall_seconds"] + degraded["wall_seconds"], 3),
        "external_dependencies": 0,
        "notes": [
            "gain_evidence 全流程纯标准库本地计算，不消耗任何模型请求，不影响 64 请求预算。",
            "同输入双跑共 4 次脚本调用（2 臂 × (seven_check + plan_check)），"
            "退化臂通过 --ablate 复用同一份输入，不复制模型产出。",
        ],
    }

    report = {
        "schema": "acwrite.gain_evidence/v1",
        "purpose": "同输入对照的真实运行证据（不依赖文字自述）",
        "input_files": {"draft": args.draft, "route": args.route,
                        "milestones": args.milestones, "constraints": args.constraints,
                        "plan": args.plan, "risks": args.risks},
        "arms": {"full": full, "degraded": degraded},
        "comparison": comparison,
        "mechanism_to_metric": mechanism_to_metric,
        "defect_detection_probe": probe,
        "boundaries": boundaries,
        "efficiency": efficiency,
        "reproduce": [
            "python3 $SD/gain_eval.py --draft /app/output/proposal.md "
            "--route /app/work/route.jsonl --milestones /app/work/milestones.jsonl "
            "--constraints /app/work/constraints.json --plan /app/work/plan.jsonl "
            "--risks /app/work/risk_table.jsonl --out /app/output/gain_evidence.json",
            "# 单臂复现: python3 $SD/seven_check.py --draft ... --out /app/output/seven_check.json",
            "# 单臂退化复现: python3 $SD/seven_check.py --draft ... --ablate all --out /app/output/seven_check_ablated.json",
        ],
        "notes": notes,
    }

    if args.out:
        try:
            os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
            json.dump(report, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        except Exception as e:
            notes.append("gain_evidence 写盘失败: %s" % str(e)[:160])
    summary = {"arms": ["full", "degraded"],
               "full_verdict": full["seven_check"]["verdict"],
               "degraded_verdict": degraded["seven_check"]["verdict"],
               "manual_check_items": {"full": fm["manual_check_items"],
                                      "degraded": dm["manual_check_items"]},
               "probe_defects": {k: probe.get(k) for k in
                                 ("defects_caught_full", "defects_caught_degraded",
                                  "detection_margin")},
               "out": args.out}
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
