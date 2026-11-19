#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gain_probe.py — 增益探针：同输入消融双跑 + 污染反例（机器判定增益）

--ablate 机制（同一 verify_check.validate 校验器对三臂各跑一遍）：
  arm_skill   技能臂：论断清单 + 证据表 + 强度措辞修正（实际管线产物）
  arm_base    基础臂：同一论断文本，但剥离证据绑定与定位（模拟基础 Agent
              「写了论断但无证据表可回查」路径——机制差异在证据登记层）
  arm_polluted 污染臂：技能臂副本注入 2 条反例（编造 quote+假定位、相关证据
              写因果）——校验器必须 FAIL，证明判据灵敏、不是逢检必过
判定：fail_count_base - fail_count_skill 为机器判定的增益差；
     arm_polluted 必须 verdict=FAIL，否则记为 sensitivity_check FAIL（照实）。
机制→指标映射、边界与失效条件一并写入 gain_evidence；efficiency 记录
可机械复核的检查数与人工核对条目削减量。
键归属：本脚本只写 result.json 的 gain_evidence 与 efficiency 两个键。
退出码恒为 0。
"""
import argparse
import copy
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify_check import validate  # 同一校验器，禁另起炉灶



class _ArgParser(argparse.ArgumentParser):
    """参数错误也退出码 0：结论写 JSON，不以退出码表达成败（硬约束）。"""
    def error(self, message):
        print(json.dumps({"ok": False, "error": "argparse: %s" % message,
                          "note": "参数错误照实记录，退出码 0"}, ensure_ascii=False))
        self.exit(0)

def load_jsonl(p):
    rows = []
    if p and os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            rows.append(json.loads(line))
                        except Exception:
                            pass
        except Exception:
            pass
    return rows


def strip_bindings(evs):
    """基础臂：清空证据绑定（保留论断文本本身，机制=不做证据登记）。"""
    base = []
    for r in evs:
        b = copy.deepcopy(r)
        b["source_id"] = None
        b["locator"] = None
        b["quote"] = None
        b["match"] = "none"
        base.append(b)
    return base


def inject_pollution(claims, evs, draft_text):
    """污染反例注入副本（只改副本，不动正表）：
    P01 编造证据（quote 语料中不存在 + 假定位）；P02 相关证据写因果。"""
    pc, pe = copy.deepcopy(claims), copy.deepcopy(evs)
    pc.append({"claim_id": "P01", "section": "pollution", "type": "numeric",
               "text": "该疗法使全因死亡率降低百分之四十二（所有患者均痊愈）。",
               "numbers": ["42"], "hedged": False, "strong_wording": True,
               "universal": True})
    pe.append({"claim_id": "P01", "source_id": "M99", "locator": "M99:p1",
               "quote": "本研究未报告全因死亡率数据。", "source_type": "原始研究",
               "match": "exact"})
    pc.append({"claim_id": "P02", "section": "pollution", "type": "interpretive",
               "text": "摄入量与发病率相关，因此补充剂导致发病率下降。",
               "numbers": [], "hedged": False, "strong_wording": False,
               "universal": False})
    pe.append({"claim_id": "P02", "source_id": "M01", "locator": "M01:p2",
               "quote": "两者在人群中呈正相关。", "source_type": "综述",
               "match": "exact"})
    return pc, pe


def main():
    ap = _ArgParser()
    ap.add_argument("--result", default="/app/output/result.json")
    ap.add_argument("--claims", default="/app/work/claims.jsonl")
    ap.add_argument("--evidence-table", default="/app/work/evidence_table.jsonl")
    ap.add_argument("--sources", default="/app/work/sources")
    ap.add_argument("--draft", default="/app/output/draft.md")
    ap.add_argument("--ablate", action="store_true")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    try:
        claims = load_jsonl(args.claims)
        evs = load_jsonl(args.evidence_table)
        from evidence_bind import read_sources
        sources = read_sources(args.sources)
        draft = ""
        if args.draft and os.path.exists(args.draft):
            draft = open(args.draft, encoding="utf-8", errors="ignore").read()

        if not args.ablate:
            out = {"ok": True, "note": "未指定 --ablate；增益对照需 --ablate 双跑"}
            print(json.dumps(out, ensure_ascii=False))
            return 0

        if not claims or not sources:
            gain = {"ok": False,
                    "note": "claims/sources 缺失，消融无法成立；照实记录，不编造增益",
                    "failure_condition": "输入材料不足时两臂同为 FAIL，差值无意义",
                    "gain_confirmed": False}
            eff = {"mechanical_checks": 0, "manual_review_items": len(claims),
                   "note": "材料缺失，全部论断需人工核对"}
        else:
            _, s_skill = validate(claims, evs, sources, draft, "skill")
            _, s_base = validate(claims, strip_bindings(evs), sources, draft, "base")
            pc, pe = inject_pollution(claims, evs, draft)
            _, s_poll = validate(pc, pe, sources, draft, "polluted")

            diff = s_base["fail_count"] - s_skill["fail_count"]
            bound_skill = s_skill["fail_by_check"]["bound"]
            bound_base = s_base["fail_by_check"]["bound"]
            manual_skill = sum(s_skill["fail_by_check"].values())
            manual_base = sum(s_base["fail_by_check"].values())
            gain = {
                "ok": True,
                "mechanism_metric_map": {
                    "证据登记与逐字回证机制": ["bound", "verbatim"],
                    "定位锚点（章节/页码/段落）": ["locator_format"],
                    "强度分级与措辞相称规则": ["wording"],
                },
                "comparison": {
                    "arm_skill": {"fail_count": s_skill["fail_count"],
                                  "verdict": s_skill["verdict"],
                                  "fail_by_check": s_skill["fail_by_check"]},
                    "arm_base": {"fail_count": s_base["fail_count"],
                                 "verdict": s_base["verdict"],
                                 "fail_by_check": s_base["fail_by_check"]},
                    "fail_count_diff_base_minus_skill": diff,
                },
                "pollution_counterexample": {
                    "arm_polluted_fail_count": s_poll["fail_count"],
                    "arm_polluted_verdict": s_poll["verdict"],
                    "sensitivity_check": "PASS" if s_poll["verdict"] == "FAIL" else "FAIL",
                    "note": "副本注入 2 条反例（编造 quote/假定位、相关写因果）；"
                            "校验器必须 FAIL 才证明判据灵敏",
                },
                "boundary": [
                    "增益以同一校验器 fail_count 差为准，仅在本包规则范围内判定",
                    "若论断措辞本身已合规，wording 维度两臂差为 0（上限：措辞问题数）",
                    "若来源材料缺失，verbatim 两臂同 FAIL，差值不构成增益",
                ],
                "failure_conditions": [
                    "claims 为空 / sources 目录为空 / 校验器异常时 gain_confirmed=False",
                    "基础臂与技能臂同分（说明证据登记层未带来可机检差异）",
                ],
                "gain_confirmed": diff > 0 and s_poll["verdict"] == "FAIL",
            }
            eff = {
                "mechanical_checks": s_skill["checks_total"] * 3,
                "manual_review_items_skill": manual_skill,
                "manual_review_items_base": manual_base,
                "manual_review_reduction": manual_base - manual_skill,
                "note": "manual_review=机检未过项数（需人工回原文核对）；"
                        "模型请求数/工具调用数由 Harness 侧记录，不在此冒充",
            }

        if args.write:
            result = {}
            if os.path.exists(args.result):
                try:
                    result = json.load(open(args.result, encoding="utf-8"))
                except Exception:
                    result = {}
            result["gain_evidence"] = gain      # 独占键，其它脚本不写
            result["efficiency"] = eff          # 独占键，其它脚本不写
            try:
                os.makedirs(os.path.dirname(args.result) or ".", exist_ok=True)
                json.dump(result, open(args.result, "w", encoding="utf-8"),
                          ensure_ascii=False, indent=1)
                gain["written"] = True
            except Exception as e:
                gain["written"] = False
                gain["write_error"] = str(e)
        print(json.dumps({"ok": True, "gain_evidence": gain,
                          "efficiency": eff}, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e),
                          "note": "增益探针异常照实记录，退出码 0"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
