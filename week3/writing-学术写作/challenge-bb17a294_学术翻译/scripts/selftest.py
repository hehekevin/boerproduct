#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""selftest.py — 一键自测：正常模式 + 退化模式 同输入对照 + 污染数据反例

产出 selftest_report.json（含**真实跑出来的数字**），供 worklog / README 引用。
所有断言失败**只记录不抛异常**，脚本 exit 0（不阻断交付）。

用例来源：**本地构造的合成材料**，非平台正式案例、非预置答案。
正式案例由评测平台在 /input/case.json 提供，本脚本不接触、不预置其答案。

A/B 设计（诚实说明）：
  同一份「带漂移的译稿」输入，两遍管线：
    full    = 全部机制开启（术语锁定 + 数字回证 + 引用锚定 + 覆盖度），会检测并**保守自动修复**确定性问题
    ablated = 关闭上述机制，既不检测也不修复
  两份产物用**同一个独立评估器**（evaluate_artifact，全强度）度量，差值即机制的可归因贡献。

用法:
  python3 scripts/selftest.py --out /app/output/selftest_report.json
"""
import argparse, json, os, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from align_check import analyze, evaluate_artifact, scan_numbers  # noqa: E402

SEGS = [
    {"seg": "S001", "locator": "M01:p1|para1", "role": "body",
     "src_text": "A cohort of 12,345 patients was analysed across 32 hospitals between 2019 and 2021. "
                 "The tumor microenvironment (TME) was associated with poor prognosis (HR = 1.62, "
                 "95% CI 1.31-2.01) [1]."},
    {"seg": "S002", "locator": "M01:p1|para2", "role": "body",
     "src_text": "A least absolute shrinkage and selection operator (LASSO) model was fitted to "
                 "1.2 million features using 320 samples."},
    {"seg": "S003", "locator": "M01:p2|para1", "role": "figure_caption",
     "src_text": "Fig. 1. Overall survival was 67.8% at 5 years, and the treatment dose was 12.4 mg/kg [2]."},
    {"seg": "S004", "locator": "M01:p2|para2", "role": "body",
     "src_text": "The study suggests a possible mechanism rather than a definitive cause, and may "
                 "explain part of the association [3]."},
]
TERMS = [
    {"src": "tumor microenvironment", "tgt": "肿瘤微环境", "status": "locked",
     "forbidden": ["肿瘤环境", "瘤周微环境"], "first_locator": "M01:p1|para1"},
    {"src": "least absolute shrinkage and selection operator (LASSO)",
     "tgt": "最小绝对收缩与选择算子（LASSO）", "status": "locked",
     "forbidden": ["拉索回归"], "first_locator": "M01:p1|para2"},
    {"src": "overall survival", "tgt": "总生存期", "status": "locked",
     "forbidden": ["总体生存率", "总存活率"], "first_locator": "M01:p2|para1"},
]
# 「模型初译」：含真实漂移（禁用变体 / 四舍五入 / 漏引 / 漏译）——这是真实工作流里最常见的输入
DRAFT = [
    {"seg": "S001", "tgt_text": "研究分析了 2019 至 2021 年间 32 家医院的 12,345 例患者。"
                                "肿瘤环境（TME）与不良预后相关（HR = 1.62）[1]。"},
    {"seg": "S002", "tgt_text": "拉索回归模型在 320 个样本上拟合了 120 万个特征。"},
    {"seg": "S003", "tgt_text": "图 1. 5 年总生存期为 68%，治疗剂量为 12.4 毫克/千克 [2]。"},
    {"seg": "S004", "tgt_text": ""},
]
# 完全干净的对照：证明校验器**不误报**
CLEAN = [
    {"seg": "S001", "tgt_text": "研究分析了 2019 至 2021 年间 32 家医院的 12,345 例患者。"
                                "肿瘤微环境（TME）与不良预后相关（HR = 1.62，95% CI 1.31-2.01）[1]。"},
    {"seg": "S002", "tgt_text": "最小绝对收缩与选择算子（LASSO）模型在 320 个样本上拟合了 120 万个特征。"},
    {"seg": "S003", "tgt_text": "图 1. 5 年总生存期为 67.8%，治疗剂量为 12.4 毫克/千克 [2]。"},
    {"seg": "S004", "tgt_text": "该研究提示可能的机制而非确定性因果，且或可解释该关联的一部分 [3]。"},
]
ABLATE = ["term_lock", "num_verify", "cite_anchor", "coverage"]


def _run(segs, rows, terms, ablate):
    rep, fixed_rows, changes, per_seg = analyze(segs, rows, terms, ablate=ablate, fix=True)
    ev = evaluate_artifact(fixed_rows, segs, terms)
    det = rep.get("detected_by_pipeline", {})
    m = dict(ev["metrics"])
    m.update({"detected_by_pipeline": det, "detected_total": rep.get("detected_total", 0),
              "detection_recall": rep.get("detection_recall"),
              "auto_fixed_items": len(changes), "verdict": rep.get("verdict"),
              "fail_count": rep.get("fail", 0),
              "pre_fix_metrics": rep.get("pre_fix_artifact_metrics")})
    return {"report": rep, "rows": fixed_rows, "changes": changes, "metrics": m, "per_seg": per_seg}


def case_normal_vs_degraded():
    """同输入两遍：full（全部机制 + 自动修复） vs ablated（退化，既不查也不修）。"""
    t0 = time.time()
    full = _run(SEGS, DRAFT, TERMS, [])
    abl = _run(SEGS, DRAFT, TERMS, ABLATE)
    per_seg_rows = []
    for seg in sorted(full["per_seg"]):
        f = full["per_seg"][seg]
        a = abl["per_seg"].get(seg, {})
        per_seg_rows.append({"seg": seg,
                              "full": {k: f[k] for k in ("term_ok", "num_ok", "cite_ok", "omitted")},
                              "ablated": {k: a.get(k) for k in ("term_ok", "num_ok", "cite_ok", "omitted")},
                              "differs": any(f[k] != a.get(k) for k in ("term_ok", "num_ok", "cite_ok", "omitted"))})
    fm, am = full["metrics"], abl["metrics"]
    return {
        "input": {"segments": len(SEGS), "identical_input_for_both_runs": True,
                  "draft_description": "同一份含漂移的初译稿（禁用变体 / 四舍五入 / 漏引 / 漏译）",
                  "note": "两遍使用完全相同的 segments/terminology/translation 输入"},
        "full": {"config": "全部机制开启 + 确定性自动修复", "metrics": fm,
                 "auto_fix_changes": full["changes"]},
        "ablated": {"config": "退化：" + ",".join(ABLATE), "metrics": am,
                    "auto_fix_changes": abl["changes"]},
        "deltas": {k: {"full": fm.get(k), "ablated": am.get(k),
                       "delta": round(fm[k] - am[k], 4)
                       if isinstance(fm.get(k), (int, float)) and isinstance(am.get(k), (int, float))
                       else None}
                   for k in ("term_consistency_rate", "number_unit_fidelity_rate",
                             "citation_alignment_rate", "omission_rate", "needs_human_items",
                             "detected_total", "detection_recall", "auto_fixed_items")},
        "per_segment_comparison": per_seg_rows,
        "segments_changed_by_mechanism": [r["seg"] for r in per_seg_rows if r["differs"]],
        "elapsed_sec": round(time.time() - t0, 3),
    }


def case_clean_no_false_positive():
    """干净稿：校验器必须 verdict=pass（证明不误报）。"""
    r = _run(SEGS, CLEAN, TERMS, [])
    return {"verdict": r["report"]["verdict"], "detected_total": r["report"]["detected_total"],
            "metrics": r["metrics"], "problem_types": sorted({p["type"] for p in r["report"]["problems"]}),
            "passed": r["report"]["verdict"] == "pass"}


def case_contamination():
    """污染数据反例：校验器必须抓到；退出码必须为 0。"""
    rep, _rows, _ch, _ps = analyze(SEGS, DRAFT, TERMS, ablate=[], fix=False)
    ev = evaluate_artifact(DRAFT, SEGS, TERMS)
    caught_types = sorted({p["type"] for p in rep.get("problems", [])})
    cli = {"exit_code": None, "stdout": "", "verdict": None}
    with tempfile.TemporaryDirectory() as td:
        sp, tp, gp = (os.path.join(td, n) for n in ("segments.jsonl", "translation.jsonl", "terminology.jsonl"))
        with open(sp, "w", encoding="utf-8") as f:
            for s in SEGS:
                f.write(json.dumps(s, ensure_ascii=False) + "\n")
        with open(tp, "w", encoding="utf-8") as f:
            for t in DRAFT:
                f.write(json.dumps(t, ensure_ascii=False) + "\n")
        with open(gp, "w", encoding="utf-8") as f:
            for t in TERMS:
                f.write(json.dumps(t, ensure_ascii=False) + "\n")
        p = subprocess.run([sys.executable, os.path.join(HERE, "align_check.py"),
                            "--segments", sp, "--translation", tp, "--terminology", gp,
                            "--out", os.path.join(td, "align_check.json")],
                           capture_output=True, text=True)
        cli["exit_code"] = p.returncode
        cli["stdout"] = p.stdout.strip()[:400]
        try:
            cli["verdict"] = json.load(open(os.path.join(td, "align_check.json"), encoding="utf-8"))["verdict"]
        except Exception:
            cli["verdict"] = None
    return {
        "expectation": "verdict=fail 且 exit_code=0（抓到问题但不中断交付）",
        "verdict": rep["verdict"], "fail_count": rep["fail"],
        "detected_total": rep["detected_total"],
        "problem_types": caught_types,
        "artifact_metrics": ev["metrics"],
        "cli_check": cli,
        "passed": rep["verdict"] == "fail" and cli["exit_code"] == 0,
    }


def case_numeric_units():
    """量级换算单元测试：万/亿 ↔ million/billion 必须等价；错量级必须不等。"""
    probes = [
        ("1.2 million features", "120 万个特征", True),
        ("2.5 billion cells", "25 亿个细胞", True),
        ("1.2 million features", "1200 万个特征", False),
        ("12,345 patients", "12,345 例", True),
        ("12,345 patients", "12,300 例", False),
        ("67.8% survival", "67.8%", True),
        ("67.8% survival", "68%", False),
        ("12.4 mg/kg", "12.4 毫克/千克", True),
        ("12.4 mg/kg", "12.4 毫克/升", False),
    ]
    rows = []
    for src, tgt, expect_eq in probes:
        s, t = scan_numbers(src), scan_numbers(tgt)
        vals_eq = len(s) == len(t) and all(
            abs(a["value"] - b["value"]) <= max(1e-9, abs(a["value"]) * 1e-9) for a, b in zip(s, t))
        rows.append({"src": src, "tgt": tgt, "values_equal": vals_eq, "expect_equal": expect_eq,
                     "ok": vals_eq == expect_eq,
                     "src_values": [a["value"] for a in s], "tgt_values": [b["value"] for b in t]})
    return {"probes": rows, "passed": all(r["ok"] for r in rows)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/app/output/selftest_report.json")
    args = ap.parse_args()

    rep = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "case_source": "本地构造的合成材料（biomedical 风格），非平台正式案例、非预置答案",
        "normal_vs_degraded": case_normal_vs_degraded(),
        "clean_no_false_positive": case_clean_no_false_positive(),
        "contamination_counterexample": case_contamination(),
        "numeric_scale_units": case_numeric_units(),
    }
    rep["all_passed"] = bool(rep["contamination_counterexample"]["passed"]
                             and rep["numeric_scale_units"]["passed"]
                             and rep["clean_no_false_positive"]["passed"])
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        json.dump(rep, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    nd = rep["normal_vs_degraded"]
    keys = ("term_consistency_rate", "number_unit_fidelity_rate", "citation_alignment_rate",
            "omission_rate", "needs_human_items", "detected_total", "detection_recall",
            "auto_fixed_items")
    print(json.dumps({
        "all_passed": rep["all_passed"],
        "full": {k: nd["full"]["metrics"].get(k) for k in keys},
        "ablated": {k: nd["ablated"]["metrics"].get(k) for k in keys},
        "deltas": nd["deltas"],
        "clean_case_verdict": rep["clean_no_false_positive"]["verdict"],
        "contamination": {"verdict": rep["contamination_counterexample"]["verdict"],
                          "exit_code": rep["contamination_counterexample"]["cli_check"]["exit_code"],
                          "types": rep["contamination_counterexample"]["problem_types"]},
        "numeric_units_passed": rep["numeric_scale_units"]["passed"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
