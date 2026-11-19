#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_result.py — 组装/更新 result.json（学术写作赛道统一收尾）

按题面「Skill 运行后的输出要求」表语义装配三块：
  1) 目标产物       -> deliverable / deliverable_content / structure（摘要·目录·各章·图表目录·参考文献·致谢）
  2) 事实与来源映射 -> evidence_map / fact_check / consistency_check / structure_check / source_mapping
  3) 版本与边界     -> version_boundary{ changelog, uncertainty, needs_human, gaps } / status / gate_notes
另装配增益证据 gain_evidence 与效率计数 efficiency（均可缺省）。

诚实原则：
  - output_contract 的字段一个不缺（列表或 {name: desc} 两种形态都识别）；无法填写时保留键并填 null，
    原因写进 uncertainty，绝不删键、绝不编造。
  - 任何失败路径退出码恒为 0（不中断交付），判据写在 verdict/fail_reason 字段。

用法:
  python3 build_result.py --case /input/case.json --out /app/output/result.json \
      --artifact thesis.docx --artifact-md thesis.md \
      --evidence /app/work/registers.jsonl --fact-check /app/output/fact_check.json \
      --consistency /app/output/cross_check.json --structure-check /app/output/completeness_check.json \
      --render /app/output/previews/render_log.json --gain-evidence /app/output/gain_evidence.json \
      --status complete --embed-file /app/output/thesis.md --embed-key deliverable_content \
      --changelog '取舍记录' --notes '待核条目'
"""
import argparse, json, os, re, sys

SECTION_KEYS = ["摘要", "目录", "各章", "图表目录", "参考文献", "致谢"]


class _SafeParser(argparse.ArgumentParser):
    """参数错误也以退出码 0 结束：判据写进 stderr 的 JSON，绝不中断交付链。"""

    def error(self, message):
        sys.stderr.write(json.dumps(
            {"ok": False, "verdict": "fail", "fail_reason": [str(message)[:200]],
             "note": "参数错误已如实记录；退出码恒 0，不中断交付。"}, ensure_ascii=False) + "\n")
        raise SystemExit(0)


def load_jsonish(p):
    if not p or not os.path.exists(p):
        return None
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        try:
            return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
        except Exception:
            return {"raw_path": p}


def contract_fields(contract):
    """output_contract 可能是 [name,...] 或 {name: desc} 或 {fields:[...]}。"""
    if isinstance(contract, list):
        return [k for k in contract if isinstance(k, str)]
    if isinstance(contract, dict):
        if isinstance(contract.get("fields"), list):
            return [k for k in contract["fields"] if isinstance(k, str)]
        if isinstance(contract.get("required"), list):
            return [k for k in contract["required"] if isinstance(k, str)]
        return [k for k in contract.keys() if isinstance(k, str)]
    return []


def as_list(s):
    if not s:
        return []
    try:
        v = json.loads(s)
        return v if isinstance(v, list) else [str(v)]
    except Exception:
        return [x.strip() for x in str(s).split(";") if x.strip()]


def ablation_state(flag_ablate=False):
    """消融开关状态：环境变量 SKILL_ABLATE=1 或 --ablate → 本轮跑基线臂。

    消融臂关闭的机制与 SKILL.md「消融开关」一节逐条对应，供平台把两臂结果对齐比较。
    """
    env = os.environ.get("SKILL_ABLATE", "")
    enabled = bool(flag_ablate) or env.strip() not in ("", "0", "false", "False", "no")
    return {
        "enabled": enabled,
        "arm": "baseline_ablate" if enabled else "skill_full",
        "source": ("cli:--ablate" if flag_ablate
                   else ("env:SKILL_ABLATE" if env.strip() not in ("", "0", "false", "False", "no")
                         else "default")),
        "disabled_mechanisms": (
            ["逐章分批写+写完即回填", "前置件齐备(摘要/目录/参考文献/致谢)",
             "章节完整性机检", "跨章登记簿", "事实台账回证"] if enabled else []),
        "note": ("本轮为消融臂：基线机制被关闭，产物不得与完整臂直接比较质量指标，"
                 "仅用于同输入对照。" if enabled else
                 "本轮为完整臂（默认）：全部增强机制生效。"),
    }


def build_structure(draft_text, struct_check):
    """题面「结果完整性」语义：摘要/目录/各章/图表目录/参考文献/致谢 的逐项在位状态。"""
    text = draft_text or ""
    heads = [re.sub(r"\s+", "", h) for h in re.findall(r"^#{1,3}\s+(.+)$", text, re.M)]

    def has(kw):
        return any(kw in h for h in heads)

    figs = sorted(set(re.findall(r"(图|表)\s*(\d+)[-–](\d+)", text)))
    structure = {
        "摘要": {"present": has("摘要"), "kind": "front_matter"},
        "目录": {"present": has("目录"), "kind": "front_matter"},
        "各章": {"present": bool([h for h in heads if re.match(r"^\d", h)]) or bool(heads),
                 "kind": "body", "chapter_headings": len(heads)},
        "图表目录": {"present": has("图表目录") or has("图目录") or has("表目录"),
                     "kind": "front_matter",
                     "numbered_objects": ["%s%s-%s" % f for f in figs]},
        "参考文献": {"present": has("参考文献"), "kind": "back_matter"},
        "致谢": {"present": has("致谢"), "kind": "back_matter"},
    }
    if struct_check:
        for c in struct_check.get("checks", []) or []:
            item = str(c.get("item") or "")
            for key in SECTION_KEYS:
                if item.startswith(key) or item == key:
                    structure[key].setdefault("machine_check", {})
                    structure[key]["machine_check"] = {
                        "template_value": c.get("template_value"),
                        "applied": c.get("applied"),
                        "match": c.get("match"),
                    }
        structure["gates"] = struct_check.get("gates", [])
        structure["verdict"] = struct_check.get("verdict")
    structure["present_count"] = sum(1 for k in SECTION_KEYS if structure[k]["present"])
    structure["total"] = len(SECTION_KEYS)
    return structure


def main():
    ap = _SafeParser()
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--out", default="/app/output/result.json")
    ap.add_argument("--artifact", default=None)
    ap.add_argument("--artifact-md", default=None)
    ap.add_argument("--evidence", default=None)
    ap.add_argument("--fact-check", default=None)
    ap.add_argument("--consistency", default=None)
    ap.add_argument("--structure-check", default=None)
    ap.add_argument("--render", default=None)
    ap.add_argument("--ledger", default=None)
    ap.add_argument("--gain-evidence", default=None)
    ap.add_argument("--efficiency", default=None)
    ap.add_argument("--status", default="partial")
    ap.add_argument("--notes", default=None, help="JSON 数组字符串或 ; 分隔文本 → uncertainty")
    ap.add_argument("--needs-human", default=None, help="JSON 数组字符串或 ; 分隔文本")
    ap.add_argument("--gaps", default=None, help="材料缺口：JSON 数组字符串或 ; 分隔文本")
    ap.add_argument("--changelog", default=None, help="JSON 数组字符串或 ; 分隔文本")
    ap.add_argument("--gate-notes", default=None)
    ap.add_argument("--embed-file", default=None)
    ap.add_argument("--embed-key", default="deliverable_content")
    ap.add_argument("--set", action="append", default=[], help="--set key=value 直接回填契约字段")
    ap.add_argument("--ablate", action="store_true",
                    help="标记本轮为消融臂（基线机制）；等价于环境变量 SKILL_ABLATE=1")
    args = ap.parse_args()

    try:
        case = load_jsonish(args.case) or {}
        if not isinstance(case, dict):
            case = {}
        case_id = case.get("case_id") or case.get("id") or "unknown_case"
        contract = case.get("output_contract") or {}

        result_path = args.out
        old = load_jsonish(result_path) if os.path.exists(result_path) else None
        result = old if isinstance(old, dict) else {}

        # 1) 契约字段一个不缺（识别 list / {name:desc} / {fields:[...]} 三种形态）
        fields = contract_fields(contract)
        for k in fields:
            result.setdefault(k, None)

        for kv in args.set:
            if "=" in kv:
                k, v = kv.split("=", 1)
                try:
                    v = json.loads(v)
                except Exception:
                    pass
                result[k] = v

        # 2) 目标产物
        embed_text = None
        if args.embed_file and os.path.exists(args.embed_file):
            embed_text = load_text(args.embed_file)
        draft_text = embed_text
        if draft_text is None and args.artifact_md and os.path.exists(args.artifact_md):
            draft_text = load_text(args.artifact_md)

        deliverable = {"docx": args.artifact, "markdown": args.artifact_md, "editable": True}
        rd = load_jsonish(args.render)
        if isinstance(rd, dict):
            deliverable["preview_pdf"] = rd.get("pdf")
            deliverable["preview_pngs"] = rd.get("pngs") or []
            deliverable["render_status"] = rd.get("status")
        result["deliverable"] = deliverable
        if embed_text is not None and args.embed_key:
            result[args.embed_key] = embed_text

        # 3) 事实与来源映射
        ev = load_jsonish(args.evidence)
        if ev is not None:
            result["evidence_map"] = ev
        fc = load_jsonish(args.fact_check)
        if fc is not None:
            result["fact_check"] = fc
        cc = load_jsonish(args.consistency)
        if cc is not None:
            result["consistency_check"] = cc
        sc = load_jsonish(args.structure_check)
        if sc is not None:
            result["structure_check"] = sc
        if args.ledger:
            result["fact_ledger_ref"] = args.ledger
        result["source_mapping"] = {
            "evidence_map": "result.evidence_map",
            "fact_check": "result.fact_check",
            "consistency_check": "result.consistency_check",
            "structure_check": "result.structure_check",
            "locator_format": "M<nn>:<locator>（材料编号:位置）",
            "quote_rule": "每条论断挂 locator + ≤30 字逐字摘录",
        }
        result["structure"] = build_structure(draft_text, sc if isinstance(sc, dict) else None)

        # 4) 版本与边界
        uncertainty = as_list(args.notes)
        needs_human = as_list(args.needs_human)
        gaps = as_list(args.gaps)
        changelog = as_list(args.changelog)
        if uncertainty:
            result["uncertainty"] = uncertainty
        else:
            result.setdefault("uncertainty", [])
        result["needs_human"] = needs_human
        result["material_gaps"] = gaps
        result["changelog"] = changelog
        result["version_boundary"] = {
            "changelog": changelog,
            "uncertainty": result.get("uncertainty", []),
            "needs_human": needs_human,
            "material_gaps": gaps,
            "status": args.status,
        }
        gate_notes = as_list(args.gate_notes)
        if gate_notes:
            result["gate_notes"] = gate_notes
        else:
            result.setdefault("gate_notes", [])

        # 5) 增益证据与效率
        ge = load_jsonish(args.gain_evidence)
        if ge is not None:
            result["gain_evidence"] = ge
        eff = load_jsonish(args.efficiency)
        if eff is None and isinstance(ge, dict) and ge.get("efficiency"):
            eff = ge.get("efficiency")
        if eff is not None:
            result["efficiency"] = eff

        # 5b) 消融开关状态（供平台做同输入 A/B 对照时识别本轮跑的是哪一臂）
        result["ablation"] = ablation_state(args.ablate)

        result["case_id"] = case_id
        result["status"] = args.status
        result["output_contract_fields"] = fields
        missing = [k for k in fields if result.get(k) is None]
        result["missing_contract_fields"] = missing
        if missing:
            note = "契约字段未填写（保留键，值 null）：%s；原因见 uncertainty" % ",".join(missing)
            if note not in result["uncertainty"]:
                result["uncertainty"].append(note)
            result["version_boundary"]["uncertainty"] = result["uncertainty"]

        os.makedirs(os.path.dirname(result_path) or ".", exist_ok=True)
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=1)
        print(json.dumps({"ok": True, "result": result_path, "status": args.status,
                          "contract_fields": len(fields), "missing": missing,
                          "keys": len(result.keys())}, ensure_ascii=False))
        return 0
    except Exception as e:
        # 失败也要交付：写一个合法骨架，绝不抛栈中断
        out = {"case_id": "unknown_case", "status": "failed", "verdict": "fail",
               "fail_reason": [str(e)[:400]], "uncertainty": ["build_result 异常：" + str(e)[:200]],
               "deliverable": {"editable": False}, "uncertainty_list": True}
        try:
            os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
            with open(args.out, "w", encoding="utf-8") as f:
                json.dump(out, f, ensure_ascii=False, indent=1)
        except Exception:
            pass
        print(json.dumps(out, ensure_ascii=False))
        return 0


def load_text(p):
    try:
        with open(p, encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception:
        return None


if __name__ == "__main__":
    sys.exit(main())
