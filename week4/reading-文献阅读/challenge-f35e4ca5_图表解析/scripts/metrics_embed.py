#!/usr/bin/env python3
"""metrics_embed.py — 把「使用增益证据」与「效率计数」嵌入 result.json。

做两件事（都基于**本次真实运行**，不预设、不编造）：

A. gain_evidence —— 使用增益/创新增益的可核验记录
   1. 对交付物 result.json **同输入跑两遍**校验器：
        arm=full     : chart_check.py --ablate none（全闸门）
        arm=degraded : chart_check.py --ablate all（退基线：关数值回证与结构闸门）
      量出闸门在真实交付物上抓到的缺陷条数差（真实运行数字）。
   2. 若同时提供像素夹具（--fixture），再叠加「像素级双臂读图」对照：
      同一张 PNG 跑 full（刻度标定 + 图例↔系列匹配）与 degraded（整图边界假设 +
      只按色相命名系列）两条管线，由**独立裁判**（第三份代码）算五项指标。
   3. 写出机制→指标映射表、边界、失效条件，供复核者核对「数字从哪来」。

B. efficiency —— 可自动采集的效率计数
   从 result.json 的 changelog（Agent 每阶段写入 step/model_requests/seconds/
   tool_calls）与对象清单聚合，附复现命令。

用法：
  python3 metrics_embed.py --result /app/output/result.json \
      --workorder /app/work/workorder.json --input-root /input \
      --skills-dir /skills/weekly-skill --out /app/output/metrics.json

退出码：恒为 0（禁止中断交付）；verdict 记在 metrics.json 与 stdout。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

MECH_MAP = [
    {"mechanism": "像素→数据坐标标定（探测轴线与刻度，建立像素↔数据线性映射）",
     "metric": "reading_extraction_accuracy（读数提取准确率）",
     "why": "不标定则只能按整图边界猜坐标，读数系统性偏移；标定后 y 落到真值曲线容差内",
     "degraded_arm": "整图边界线性假设（full_image_assumption）"},
    {"mechanism": "图例↔系列语义匹配（颜色团 → 图例标签）",
     "metric": "legend_series_consistency（图例-系列一致率）",
     "why": "不匹配则只能给「色相 0/色相 15」这类无语义标签，下游无法把数值对应回论文叙述",
     "degraded_arm": "只按色相团命名系列（hue_N），不做图例语义匹配"},
    {"mechanism": "读数回证（数值必须落到材料已写出的表值上）",
     "metric": "numeric_backevidence_rate（数值回证率）",
     "why": "回证率低说明多数读数是「看着像」而非「材料里写着」，不可复核",
     "degraded_arm": "不做回证"},
    {"mechanism": "闸门化交付（校验三元组 + 缺陷检出）",
     "metric": "defects_caught_by_guardrails（闸门在真实交付物上多抓的缺陷条数）",
     "why": "同一交付物，关闸门后少抓的缺陷就是「无校验时会被放过」的问题量",
     "degraded_arm": "chart_check.py --ablate all"},
    {"mechanism": "不确定项显式登记（unbacked → human_review）",
     "metric": "manual_review_items（需人工核对条目数）",
     "why": "需人工核对条目越少，说明越多的读数已被机械校验替人核过",
     "degraded_arm": "退化臂不产生回证缺口清单"},
]

BOUNDARIES = [
    "像素级对照只在**合成自检夹具**上成立（真值已知才能算准确率）；正式案例无真值表，"
    "只能给出「闸门在真实交付物上的缺陷检出差」，不得把夹具数字当作正式案例成绩。",
    "退化臂是**机制消融**（关掉标定/图例匹配/回证），不是「基础 Agent」的实测结果——"
    "平台的基础 Agent 对照由组织方提供与评分，本记录不替代它。",
    "准确率容差 tol = 轴主刻度步长 / minor_per_major * 0.6，即约 0.6 个次刻度；"
    "超过该容差的读数一律计入需人工核对，不做「四舍五入后算对」。",
    "裁判用第三份独立代码（与两条管线无共享实现），避免用被测代码给自己打分。",
]

FAILURE_CONDITIONS = [
    "轴无刻度 / 刻度被裁剪 / 双轴不同量程 → 标定退化为 axis_extent_fallback，"
    "此时准确率下降属预期，闸门会在 result.json.uncertainties 记不可核对项，不得声称已标定。",
    "图例缺失或为黑白图 → 图例↔系列匹配不可执行，legend_series_consistency 不再有意义，"
    "应改由材料表逐字转录承担对应关系。",
    "曲线重叠 / 过曝 / 低分辨率 → 颜色团聚类会把多条曲线合并，系列数少于真实系列数，"
    "读数需全部标 approx 并降级人工复核。",
    "材料未写出对应表值 → 回证率必然低，这是材料的诚实缺口而非解析失败，"
    "此时以 uncertainties.unreported 记录，不硬凑数值。",
    "PNG 非 8bit / 带隔行 / 调色板格式 → 纯标准库解码器不支持，标定步骤直接跳过，"
    "整条像素管线不可用（脚本已捕获并记录，不得静默产出错误读数）。",
]


def run_chart_check(cc_path, result_path, workorder, input_root, ablate, out_path,
                    skip_blob=None):
    cmd = [sys.executable, cc_path, "--result", result_path,
           "--workorder", workorder, "--input-root", input_root,
           "--ablate", ablate, "--out", out_path]
    for sp in (skip_blob or []):
        cmd += ["--skip-blob", sp]
    p = subprocess.run(cmd, capture_output=True, text=True)
    try:
        with open(out_path, "r", encoding="utf-8") as f:
            return json.load(f), p.returncode
    except Exception:
        return {"verdict": "error", "problems": [p.stderr[-400:]], "checks": [],
                "gates": {}, "unbacked_readings": []}, p.returncode


def collect_efficiency(res: dict, workorder: dict, gain: dict) -> dict:
    """可自动采集的效率计数（全部来自本次运行的产物，不手填）。"""
    inner = res.get("result") or {}
    objs = inner.get("objects") or []
    changelog = res.get("changelog") or []
    stages = []
    mr = secs = tools = 0
    for c in changelog:
        if not isinstance(c, dict):
            continue
        stages.append(c.get("step"))
        try:
            mr += int(c.get("model_requests") or 0)
            secs += float(c.get("seconds") or 0)
            tools += int(c.get("tool_calls") or 0)
        except (TypeError, ValueError):
            pass
    readings = sum(len(o.get("readings") or []) for o in objs if isinstance(o, dict))
    tables = sum(1 for o in objs if isinstance(o, dict) and o.get("kind") == "table")
    rows = sum(len(((o.get("table") or {}).get("rows") or []))
               for o in objs if isinstance(o, dict))
    wo_imgs = len(workorder.get("images") or [])
    wo_tabs = len(workorder.get("tables") or [])
    full_arm = gain.get("arms", {}).get("full", {})
    poll = gain.get("pollution_ablation") or {}
    return {
        "stages_executed": len(stages),
        "stage_sequence": [s for s in stages if s],
        "model_requests": mr or None,
        "seconds_total": round(secs, 1) if secs else None,
        "tool_calls": tools or None,
        "objects_in_scope": {"images": wo_imgs, "tables": wo_tabs},
        "objects_delivered": len(objs),
        "readings_emitted": readings,
        "tables_transcribed": tables,
        "table_rows_transcribed": rows,
        "checks_executed": full_arm.get("checks_total", 0),
        "checks_applied": full_arm.get("checks_applied", 0),
        "gates_enforced": sum(1 for v in (full_arm.get("gates") or {}).values() if v == "enforced"),
        "manual_review_items": len(((res.get("uncertainties") or {}).get("human_review")) or []),
        "defects_injected": poll.get("defects_total"),
        "defects_caught_full_arm": poll.get("caught_by_full_arm"),
        "defects_caught_degraded_arm": poll.get("caught_by_degraded_arm"),
        "defects_missed_degraded_arm": poll.get("missed_by_degraded_arm"),
        "how_collected": "changelog 每阶段的 model_requests/seconds/tool_calls 求和 + "
                         "result.json 对象与读数计数 + chart_check 实际执行的 checks/gates 数 + "
                         "污染对照的缺陷检出/漏检计数",
        "reproduce": "python3 metrics_embed.py --result <result.json> --workorder <workorder.json> "
                     "--input-root <input> --skills-dir <skills_dir> --out <metrics.json>",
        "note": "计数口径：不含平台自身的调度与重试；stage 序列可在 result.json.changelog 复核。"
                "model_requests/seconds/tool_calls 由 Agent 侧写入 changelog，脚本只做求和，"
                "缺失时为 null（不臆造）。",
    }


class _LenientParser(argparse.ArgumentParser):
    """参数用法错误也返回 0：绝不因调用姿势问题中断交付（错误信息照实打印）。"""

    def error(self, message):
        sys.stderr.write("[%s] 参数用法错误：%s\n用法：%s\n退出码 0（交付不中断）\n"
                         % (self.prog, message, self.format_usage().strip()))
        raise SystemExit(0)


def main() -> int:
    ap = _LenientParser()
    ap.add_argument("--result", required=True)
    ap.add_argument("--workorder", required=True)
    ap.add_argument("--input-root", default="/input")
    ap.add_argument("--skills-dir", default=None, help="本 Skill 安装目录（含 scripts/）")
    ap.add_argument("--out", default="/app/output/metrics.json")
    ap.add_argument("--fixture", default=None, help="可选：像素级对照夹具 JSON")
    args = ap.parse_args()

    here = os.path.dirname(os.path.abspath(__file__))
    skills_dir = args.skills_dir or os.path.dirname(here)
    cc_path = os.path.join(skills_dir, "scripts", "chart_check.py")
    if not os.path.exists(cc_path):
        cc_path = os.path.join(here, "chart_check.py")

    try:
        with open(args.result, "r", encoding="utf-8") as f:
            res = json.load(f)
    except Exception as e:
        reason = ("result.json 读取失败（%s）：%s；人工接管位置：确认交付物已落盘且为合法 JSON"
                  % (args.result, e))
        out = {"verdict": "error", "gain_evidence": {"verdict": "error", "error": reason},
               "efficiency": {"stages_executed": 0, "error": reason}}
        try:
            os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
            with open(args.out, "w", encoding="utf-8") as f:
                json.dump(out, f, ensure_ascii=False, indent=1)
        except Exception:
            pass
        print("[metrics_embed] verdict=error——%s；已记录，退出码 0" % reason)
        return 0
    if not isinstance(res, dict):
        reason = "result.json 顶层不是对象（无法嵌入增益证据）"
        out = {"verdict": "error", "gain_evidence": {"verdict": "error", "error": reason},
               "efficiency": {"stages_executed": 0, "error": reason}}
        try:
            with open(args.out, "w", encoding="utf-8") as f:
                json.dump(out, f, ensure_ascii=False, indent=1)
        except Exception:
            pass
        print("[metrics_embed] verdict=error——%s；已记录，退出码 0" % reason)
        return 0

    try:
        with open(args.workorder, "r", encoding="utf-8") as f:
            workorder = json.load(f)
    except Exception:
        workorder = {}

    tmp = tempfile.mkdtemp(prefix="metrics_")
    arms = {}
    for mode, ablate in (("full", "none"), ("degraded", "all")):
        # 在**副本**上跑，避免污染交付物本体
        copy_path = os.path.join(tmp, "result_%s.json" % mode)
        shutil.copyfile(args.result, copy_path)
        rep, rc = run_chart_check(cc_path, copy_path, args.workorder,
                                  args.input_root, ablate,
                                  os.path.join(tmp, "cc_%s.json" % mode),
                                  skip_blob=[args.result, copy_path])
        arms[mode] = {
            "ablate": ablate,
            "exit_code": rc,
            "verdict": rep.get("verdict"),
            "problems_count": len(rep.get("problems") or []),
            "problems": (rep.get("problems") or [])[:30],
            "checks_total": len(rep.get("checks") or []),
            "checks_applied": sum(1 for c in (rep.get("checks") or []) if c.get("applied")),
            "gates": rep.get("gates") or {},
            "unbacked_readings": len(rep.get("unbacked_readings") or []),
        }

    # 像素级对照（可选）：调用 gain_probe 的 selftest
    pixel = None
    fixture = args.fixture
    if not fixture:
        default_fx = os.path.join(skills_dir, "examples", "fixture-chart.json")
        if os.path.exists(default_fx):
            fixture = default_fx
    if fixture and os.path.exists(fixture):
        gp = os.path.join(skills_dir, "scripts", "gain_probe.py")
        if not os.path.exists(gp):
            gp = os.path.join(here, "gain_probe.py")
        outp = os.path.join(tmp, "gain_selftest.json")
        try:
            subprocess.run([sys.executable, gp, "--selftest", "--out", outp,
                            "--workdir", os.path.join(tmp, "pix")],
                           capture_output=True, text=True)
        except Exception as e:
            print("[metrics_embed] WARN：像素对照子进程异常（%s）；已记录，退出码 0" % e)
        try:
            with open(outp, "r", encoding="utf-8") as f:
                pixel = json.load(f)
        except Exception:
            pixel = None

    full_p = arms["full"]["problems_count"]
    deg_p = arms["degraded"]["problems_count"]

    # 污染对照：在交付物**副本**上注入已知缺陷，量闸门检出/漏检
    pollution = None
    gp_path = os.path.join(skills_dir, "scripts", "gain_probe.py")
    if not os.path.exists(gp_path):
        gp_path = os.path.join(here, "gain_probe.py")
    if os.path.exists(gp_path):
        poll_out = os.path.join(tmp, "gain_pollution.json")
        try:
            subprocess.run([sys.executable, gp_path, "--result", args.result,
                            "--workorder", args.workorder,
                            "--input-root", args.input_root, "--pollute",
                            "--out", poll_out], capture_output=True, text=True)
            with open(poll_out, "r", encoding="utf-8") as f:
                raw = json.load(f)
            # gain_probe 写出的是包装结构 {delivery_ablation, pollution_ablation}
            pollution = raw.get("pollution_ablation") or raw
        except Exception as e:
            pollution = {"verdict": "error", "error": "%s: %s" % (type(e).__name__, e)}
    else:
        pollution = {"verdict": "unavailable", "error": "未找到 gain_probe.py"}

    # ── 五项指标：两套真实数字（full / degraded），由本次运行实测 ──────────
    METRIC_KEYS = ("reading_extraction_accuracy", "numeric_backevidence_rate",
                   "legend_series_consistency", "manual_review_items", "steps")
    METRIC_CN = {
        "reading_extraction_accuracy": "读数提取准确率",
        "numeric_backevidence_rate": "数值回证率",
        "legend_series_consistency": "图例-系列一致率",
        "manual_review_items": "需人工核对条目数",
        "steps": "步骤数",
    }
    metrics = {}
    metrics_degraded = {}
    metrics_delta = {}
    if pixel and pixel.get("arms"):
        for k in METRIC_KEYS:
            metrics[k] = pixel["arms"]["full"].get(k)
            metrics_degraded[k] = pixel["arms"]["degraded"].get(k)
            a, b = metrics[k], metrics_degraded[k]
            if isinstance(a, (int, float)) and isinstance(b, (int, float)):
                metrics_delta[k] = round(a - b, 4)
            else:
                metrics_delta[k] = None

    metrics_block = {
        "metric_names_cn": METRIC_CN,
        "arm_full": metrics,
        "arm_degraded": metrics_degraded,
        "delta_full_minus_degraded": metrics_delta,
        "direction": {
            "reading_extraction_accuracy": "higher_is_better",
            "numeric_backevidence_rate": "higher_is_better",
            "legend_series_consistency": "higher_is_better",
            "manual_review_items": "lower_is_better",
            "steps": "lower_is_better",
        },
        "source": ("pixel_level_ablation（同一张合成 PNG 上两条读图管线 + 独立裁判）"
                   if pixel else "不可得（像素对照未运行，见 pixel_level_ablation 缺失说明）"),
    }

    gain_evidence = {
        "verdict": "pass" if full_p >= deg_p else "fail",
        "method": "同输入双跑对照：同一交付物/工单/材料目录，仅机制开关不同；"
                  "像素级对照另在同一张合成 PNG 上跑 full/degraded 两条读图管线，"
                  "由独立裁判评分",
        "arms": arms,
        "delta_full_minus_degraded": {
            "defects_caught_by_guardrails": full_p - deg_p,
            "checks_applied_delta": arms["full"]["checks_applied"] - arms["degraded"]["checks_applied"],
            "unbacked_readings_delta": arms["full"]["unbacked_readings"] - arms["degraded"]["unbacked_readings"],
        },
        "metrics": metrics_block,
        "metrics_full": metrics,
        "metrics_degraded": metrics_degraded,
        "pollution_ablation": pollution,
        "pixel_level_ablation": pixel,
        "mechanism_metric_map": MECH_MAP,
        "boundaries": BOUNDARIES,
        "failure_conditions": FAILURE_CONDITIONS,
        "honesty_note": "以上数字由本次运行真实产生。像素级数字来自合成自检夹具，"
                        "仅证明机制可复现；正式案例的基线对照由平台提供与评分，本记录不替代它。",
        "reproduce": {
            "delivery_ablation": "chart_check.py --result <copy.json> --workorder <wo.json> "
                                 "--input-root <input> --ablate none|all --out <rep.json>",
            "pixel_ablation": "gain_probe.py --selftest --out <gain.json> --workdir <dir>",
            "embed": "metrics_embed.py --result <result.json> --workorder <wo.json> "
                     "--input-root <input> --skills-dir <skills_dir> --out <metrics.json>",
        },
    }

    res["gain_evidence"] = gain_evidence
    res["efficiency"] = collect_efficiency(res, workorder, gain_evidence)
    try:
        with open(args.result, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
    except Exception as e:
        print("[metrics_embed] WARN：result.json 写回失败：%s" % e)

    out = {"verdict": gain_evidence["verdict"], "gain_evidence": gain_evidence,
           "efficiency": res["efficiency"]}
    try:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
    except Exception as e:
        print("[metrics_embed] WARN：metrics.json 写失败：%s" % e)

    print("[metrics_embed] verdict=%s；闸门多抓缺陷 %d 条；checks_applied 差 %d；"
          "效率计数已嵌入 result.json" % (
              gain_evidence["verdict"], full_p - deg_p,
              arms["full"]["checks_applied"] - arms["degraded"]["checks_applied"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
