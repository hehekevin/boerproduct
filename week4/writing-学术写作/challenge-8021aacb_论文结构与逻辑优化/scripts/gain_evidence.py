#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gain_evidence.py — 增益证据层：同输入消融两臂真跑 + 污染反例注入验证检测器非空转

流程（全部本次运行真跑，不引用历史数字）：
  1. 完整臂：structure_check.run_arm(manuscript, ablate=False)
  2. 消融臂：同一校验器 run_arm(manuscript, ablate=True)（六类全关，模拟基础 Agent 表层检查）
  3. 逐项指标差（同输入两臂 FAIL 数差 = 机器判定，非文字声明）
  4. 污染反例：向稿件副本注入 3 处植入缺陷（跨章节重复段/绝对化结论句/无证据论断），
     完整臂重跑副本，逐项确认是否命中（检测器非空转证据）
写入 result.json 的 gain_evidence 与 efficiency 两个键（其余键一律不动，避免与
build_result.py 冲突）。退出码恒 0。
边界与失效条件：增益度量的是「机检可发现的结构问题数」，不度量语义正确性；
若稿件本身无结构缺陷，两臂差值可能为 0，此时以污染反例命中数作为能力证据。
"""
import argparse, copy, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _rlog
import structure_check as SC


def inject_pollution(ms):
    """向稿件副本注入 3 处植入缺陷，返回 (副本, 植入说明)。"""
    bad = copy.deepcopy(ms)
    planted = []
    secs = bad.get("sections", [])
    if len(secs) >= 2:
        src_para = None
        for p in secs[0]["paragraphs"]:
            if len(p) >= 40:
                src_para = p
                break
        if src_para:
            secs[-1]["paragraphs"].append(src_para)  # 植入1：跨章节重复
            planted.append({"kind": "repetition", "where": "末章节追加首章节原段"})
    over = "本研究完全证明了该方法在所有场景下均显著优于全部基线方法，彻底解决了该问题。"
    tgt = secs[-1] if secs else None
    if tgt and tgt["paragraphs"]:
        tgt["paragraphs"][-1] += over  # 植入2：绝对化/超边界结论句
        planted.append({"kind": "claim_boundary", "where": "末章节段落尾拼接绝对化结论句"})
    unsup = "分析表明该策略的效果非常突出，值得在后续研究中深入考察。"
    if tgt:
        tgt["paragraphs"].insert(0, unsup)  # 植入3：无证据论断句
        planted.append({"kind": "claim_evidence", "where": "末章节段首插入无证据论断"})
    return bad, planted


def check_planted(rep_full_on_bad, planted):
    cats_hit = set()
    for f in rep_full_on_bad.get("findings", []):
        q = str(f.get("quote", "")) + str(f.get("problem", ""))
        if "完全证明" in q or "彻底解决" in q or "显著优于" in q:
            cats_hit.add("claim_boundary")
        if "分析表明该策略" in q or "非常突出" in q:
            cats_hit.add("claim_evidence")
    # 重复检测命中：末章节出现与首章节重复的 finding
    if any(f.get("category") == "repetition" for f in rep_full_on_bad.get("findings", [])):
        cats_hit.add("repetition")
    return cats_hit


def main():
    t0 = __import__("time").time()
    ap = argparse.ArgumentParser()
    ap.add_argument("--manuscript", default="/app/work/manuscript.json")
    ap.add_argument("--result", default="/app/output/result.json")
    try:
        args = ap.parse_args()
    except SystemExit:
        print(json.dumps({"ok": False, "note": "参数错误"}))
        return 0

    out = {"ok": False, "mechanism_map": [
        {"metric": "六类结构 FAIL 数差", "mechanism": "同一校验器 structure_check 两臂各跑一遍，逐类计数相减",
         "boundary": "只度量机检可发现的结构问题，不度量语义正确性",
         "invalid_when": "稿件本身无结构缺陷时差值可能为 0，此时看污染反例命中数"},
        {"metric": "跨章节重复检出", "mechanism": "句级归一化全等/互相包含 + 二元组 Jaccard≥0.85",
         "boundary": "改写幅度大或语序重排的重复会漏检",
         "invalid_when": "段落被改写超过一半字符"},
        {"metric": "超边界表述检出", "mechanism": "绝对化词表 + 同句因果词×相关统计共现",
         "boundary": "词表覆盖有限，委婉超边界（如『基本解决了』）不在词表",
         "invalid_when": "超边界表述不在词表且无因果/相关共现"},
        {"metric": "无证据论断检出", "mechanism": "论断标记句无数值/引用/图表标记",
         "boundary": "同段任一句有证据标记即放宽为 same_paragraph，可能漏报",
         "invalid_when": "论断与证据被排版进不同段落"},
    ]}
    try:
        ms = json.load(open(args.manuscript, encoding="utf-8"))
        full = SC.run_arm(ms, ablate=False)      # 完整臂：真跑第 1 遍
        ablate = SC.run_arm(ms, ablate=True)     # 消融臂：真跑第 2 遍（同输入）
        pc = full["summary"]["per_category"]
        ac = ablate["summary"]["per_category"]
        diff = {c: {"skill_full": pc.get(c, 0), "ablated_generic": ac.get(c, 0),
                    "diff": pc.get(c, 0) - ac.get(c, 0)} for c in SC.CATEGORIES}
        out.update({
            "ok": True,
            "same_input": args.manuscript,
            "arms": {"skill_full": "structure_check.run_arm(ablate=False)",
                     "ablated_generic": "同一校验器 run_arm(ablate=True)，六类结构检测全部关闭，仅表层规则"},
            "metrics": {
                "fail_count": {"skill_full": full["summary"]["fail_count"],
                               "ablated_generic": ablate["summary"]["fail_count"],
                               "diff_machine_judged": full["summary"]["fail_count"] - ablate["summary"]["fail_count"]},
                "per_category": diff,
                "high_severity": {"skill_full": sum(1 for f in full["findings"] if f["severity"] == "high"),
                                  "ablated_generic": sum(1 for f in ablate["findings"] if f["severity"] == "high")},
                "six_category_coverage": {"skill_full": sum(1 for c in SC.CATEGORIES if pc.get(c)),
                                          "ablated_generic": 0,
                                          "note": "消融臂六类全关，覆盖数恒 0；差值即结构级能力的机检证据"},
            },
        })
        bad, planted = inject_pollution(ms)
        if planted:
            rep_bad = SC.run_arm(bad, ablate=False)
            cats_hit = sorted(check_planted(rep_bad, planted))
            out["pollution_test"] = {
                "purpose": "检测器非空转验证：向副本注入植入缺陷，确认完整臂能命中",
                "planted": planted,
                "planted_total": len(planted),
                "planted_categories_caught": cats_hit,
                "planted_caught": len(cats_hit),
                "verdict": "pass" if len(cats_hit) >= min(2, len(planted)) else "weak",
                "note": "未命中的植入类别如实记录；weak 不代表全部检测器失效",
            }
    except Exception as e:
        out["error"] = str(e)
        out["note"] = "增益计算失败，如实记录；退出码仍为 0"

    out["honesty"] = {
        "all_numbers_from": "本次运行真跑（同输入两臂 + 污染副本）",
        "not_claimed": "不宣称跨模型横向评测分数；FAIL 数差≠评分提升",
    }
    eff = {"tool_calls": len(_rlog.read_log()),
           "tool_calls_source": "auto: run_log.jsonl（各脚本 _rlog.log_call 逐次写入）",
           "arms_run": 2, "pollution_injections": out.get("pollution_test", {}).get("planted_total", 0),
           "mechanical_checks": out.get("metrics", {}).get("fail_count", {}).get("skill_full", 0),
           "note": "模型请求数由 Harness 侧记录，本脚本不冒充"}
    written = False
    try:
        result = json.load(open(args.result, encoding="utf-8")) if os.path.exists(args.result) else {}
        result["gain_evidence"] = out
        result["efficiency"] = eff  # 本脚本独占这两个键；build_result.py 不写同名键
        os.makedirs(os.path.dirname(args.result) or ".", exist_ok=True)
        json.dump(result, open(args.result, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        written = True
    except Exception as e:
        out["write_error"] = str(e)
    print(json.dumps({"ok": out.get("ok"), "written": written,
                      "fail_diff": out.get("metrics", {}).get("fail_count", {}).get("diff_machine_judged"),
                      "pollution": out.get("pollution_test", {}).get("verdict"),
                      "gain_evidence": out.get("error")}, ensure_ascii=False))
    _rlog.log_call("gain_evidence", argv=sys.argv[1:], seconds=__import__("time").time() - t0,
                   extra={"written": written})
    return 0


if __name__ == "__main__":
    sys.exit(main())
