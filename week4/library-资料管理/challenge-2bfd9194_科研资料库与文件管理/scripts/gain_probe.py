#!/usr/bin/env python3
"""gain_probe.py — 同输入消融双跑增益对照 + 效率计数 + 污染反例（lib-file-organizer）。

对同一份 result.json 用 verify_check.analyze() 跑多遍：
  normal        五组检查全开
  ablate:rules  关闭分类规则重放（归类无据不检测）
  ablate:duplicates 关闭哈希去重/版本链复算
  ablate:audit  关闭审计链完整性检查
  ablate:all    同时关闭 rules/duplicates/audit/evidence（仅留覆盖底线）
每遍记录各机制漏检数（rules_miss/dup_miss/version_miss/audit_miss/evidence_miss），
真实差值写入 result.gain_evidence；效率计数写入 result.efficiency。
--inject-pollution 在副本注入 4 类污染（改错归类/篡改哈希/断审计链/清空待定理由）：
正常模式必须抓到（caught_by_normal_mode=true），原 result.json 不被改动。
退化模式结果仅用于增益对照，不得当作交付自检结论。退出码恒 0。

用法：
    python3 gain_probe.py --result /app/output/result.json --case /input/case.json \
        --work-dir /app/work --emit-into --inject-pollution
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify_check import analyze  # noqa: E402

ABLATE_SETS = [("rules", ("rules",)), ("duplicates", ("duplicates",)),
               ("audit", ("audit",)), ("all", ("rules", "duplicates", "audit", "evidence"))]


def count_miss(metrics):
    return (metrics.get("rules_miss", 0) + metrics.get("dup_miss", 0)
            + metrics.get("version_miss", 0) + metrics.get("audit_miss", 0)
            + metrics.get("evidence_miss", 0))


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def inject_pollution(result):
    """副本注入 4 类污染，返回副本。原 result 不动。"""
    p = copy.deepcopy(result)
    inner = p.get("result") or {}
    files = inner.get("files") or []
    n_inj = 0
    # 1) 改错归类：把第一个已归类文件的 category 改成未声明值
    for f in files:
        if f.get("category"):
            f["category"] = "hacked_category"
            f["rule_hit"] = "R-XX"
            n_inj += 1
            break
    # 2) 篡改重复组哈希（证据回证失效）
    if inner.get("duplicates"):
        inner["duplicates"][0]["hash"] = "0" * 64
        n_inj += 1
    # 3) 断审计链：删一条操作并破坏下一条的 chain_hash
    ops = inner.get("ops") or []
    if len(ops) >= 2:
        del ops[0]
        ops[0]["chain_hash"] = "broken" * 8
        ops[0]["prev_op_id"] = "OP-9999"
        n_inj += 1
    # 4) 清空待定理由 + 伪判
    for f in files:
        if f.get("skip_reason"):
            f["skip_reason"] = None
            f["judged"] = True
            if not f.get("category"):
                f["category"] = "unsorted"
            n_inj += 1
            break
    p.setdefault("changelog", []).append({"step": "pollution", "change": "injected %d" % n_inj})
    return p, n_inj


def main():
    t0 = time.time()
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", required=True)
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--work-dir", default="/app/work")
        ap.add_argument("--emit-into", action="store_true")
        ap.add_argument("--inject-pollution", action="store_true")
        args = ap.parse_args()
    except Exception as e:
        print("[gain_probe] 参数解析失败: %s" % e)
        return 0

    problems = []
    result = None
    try:
        result = load_json(args.result)
    except Exception as e:
        print("[gain_probe] FAIL: result.json 读取失败: %s（不中断交付）" % e)
        return 0

    runs, pollution = [], {}
    try:
        # normal
        probs_n, _, met_n, _ = analyze(result, None, ())
        runs.append({"mode": "normal", "ablate": [], "problems": len(probs_n),
                     "miss_total": count_miss(met_n), "metrics": dict(met_n)})
        # 各消融
        for name, groups in ABLATE_SETS:
            probs_d, _, met_d, _ = analyze(result, None, groups)
            runs.append({"mode": "ablate:%s" % name, "ablate": list(groups),
                         "problems": len(probs_d), "miss_total": count_miss(met_d),
                         "metrics": dict(met_d)})
        met_map = {r["mode"]: r["metrics"] for r in runs}
        delta = {}
        for key in ("rules_miss", "dup_miss", "version_miss", "audit_miss", "evidence_miss"):
            d_all = met_map.get("ablate:all", {}).get(key, 0) - met_map.get("normal", {}).get(key, 0)
            delta[key] = {"normal": met_map.get("normal", {}).get(key, 0),
                          "degraded_all": met_map.get("ablate:all", {}).get(key, 0),
                          "delta": d_all}
        # 污染反例（副本）
        if args.inject_pollution:
            polluted, n_inj = inject_pollution(result)
            ppath = os.path.join(args.work_dir or ".", "gain_probe_polluted.json")
            try:
                os.makedirs(args.work_dir or ".", exist_ok=True)
                with open(ppath, "w", encoding="utf-8") as f:
                    json.dump(polluted, f, ensure_ascii=False, indent=1)
            except Exception as e:
                problems.append("污染副本写盘失败: %s" % e)
            probs_pn, _, met_pn, _ = analyze(polluted, None, ())
            probs_pd, _, met_pd, _ = analyze(polluted, None, ("rules", "duplicates", "audit", "evidence"))
            caught = len(probs_pn) > 0
            pollution = {"injected_count": n_inj, "polluted_copy": ppath,
                         "caught_by_normal_mode": caught,
                         "normal_problems": len(probs_pn),
                         "normal_miss_total": count_miss(met_pn),
                         "degraded_problems": len(probs_pd),
                         "degraded_miss_total": count_miss(met_pd),
                         "note": "正常模式抓到=%s；退化模式漏检 %d 处" % (caught, count_miss(met_pd))}
        # 回写
        if args.emit_into:
            inner = result.get("result") or {}
            inner["gain_evidence"] = {
                "available": True,
                "runs": runs,
                "delta_normal_minus_degraded": delta,
                "mechanism_to_metric_map": [
                    {"mechanism": "分类规则事前声明+重放", "metric": "rules_miss",
                     "meaning": "关闭后归类不一致漏检数上升"},
                    {"mechanism": "内容哈希去重/版本链复算", "metric": "dup_miss+version_miss",
                     "meaning": "关闭后按文件名误判重复/版本漏检数上升"},
                    {"mechanism": "操作审计链哈希重算", "metric": "audit_miss",
                     "meaning": "关闭后断链/缺复放漏检数上升"},
                    {"mechanism": "证据逐字回证", "metric": "evidence_miss",
                     "meaning": "关闭后哈希/引用无回证漏检数上升"}],
                "boundaries": ["本校验层正常 vs 退化对照，不等于平台基础 Agent 白板对照",
                               "干净输入上漏检均为 0，增益体现在污染/违规输入的抓错能力",
                               "退化模式结果仅用于增益对照，不得当作交付自检结论"],
                "failure_conditions": ["输入无可读文件内容（哈希缺失）时重复/版本机制退化",
                                       "规则未事前声明时归类整体暂停", "脚本异常时 available=false 如实登记"],
                "pollution_selftest": pollution,
            }
            inner["efficiency"] = {
                "available": True,
                "wall_clock_seconds_total": round(time.time() - t0, 3),
                "checker_runs": len(runs) + (2 if pollution else 0),
                "files_processed": len((result.get("result") or {}).get("files") or []),
                "manual_items": 0,
                "reproduce": "python3 gain_probe.py --result result.json --case case.json "
                             "--work-dir /app/work --emit-into --inject-pollution",
            }
            with open(args.result, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=1)
        # 证据落盘
        try:
            os.makedirs(args.work_dir or ".", exist_ok=True)
            with open(os.path.join(args.work_dir or ".", "gain_evidence.json"), "w", encoding="utf-8") as f:
                json.dump({"runs": runs, "delta": delta, "pollution": pollution,
                           "problems": problems}, f, ensure_ascii=False, indent=1)
        except Exception as e:
            problems.append("gain_evidence.json 写盘失败: %s" % e)
    except Exception as e:
        problems.append("增益对照执行异常: %s" % e)
        if args.emit_into:
            try:
                inner = result.get("result") or {}
                inner["gain_evidence"] = {"available": False, "reason": str(e)}
                inner["efficiency"] = {"available": False, "reason": str(e)}
                with open(args.result, "w", encoding="utf-8") as f:
                    json.dump(result, f, ensure_ascii=False, indent=1)
            except Exception:
                pass

    print("[gain_probe] runs=%d | 消融 delta=%s | 污染自测=%s"
          % (len(runs), json.dumps(delta) if runs else "-",
             "caught=%s" % pollution.get("caught_by_normal_mode") if pollution else "-"))
    for p in problems:
        print("  WARN: %s" % p)
    print("[gain_probe] 完成（退出码 0）")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[gain_probe] 未预期异常（已降级）: %s" % e)
        sys.exit(0)
