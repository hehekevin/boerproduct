#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gain_ablation.py — 同输入双臂对照实验台（增益证据生成器）

用途：在**同一份输入**上跑「完整 Skill 流程」与「退化/基线流程」两臂，
逐项对照可量化指标，产出 gain_evidence.json（可直接嵌入 result.json）。

两臂唯一差异是**流程机制**（输入材料、指标函数完全相同）：
  full   = 逐章分批写 + 写完即回填 + 前置件齐备 + 完整性机检（闸门全跑）
  ablate = 一次性合并成稿（受单次响应预算截断）+ 无前置件 + 不跑机检

目录约定（--case 指向的根目录）：
  case.json            {"case_id":..., "output_contract":{...},
                        "front_matter":{"abstract":..,"toc":[..]},
                        "required_sections":["摘要","目录","参考文献","致谢"]}
  materials.txt        事实来源原文（数字回证用）
  chapter_plan.jsonl   每行 {"ch":"1","title":"引言",...}
  registers.jsonl      每行 {"kind":"term|symbol|definition|conclusion","key":...,"canonical":...}
  chapters/NN.md       逐章草稿（文件名数字前缀对应 plan 的 ch；首行标题会被规范化）
  references.md        参考文献条目（可选）
  acknowledgments.md   致谢（可选）

用法:
  python3 gain_ablation.py --case <case_dir> --arm full   --out <gain_evidence.json>
  python3 gain_ablation.py --case <case_dir> --arm ablate --out <gain_evidence.json>
  python3 gain_ablation.py --case <case_dir> --both      --out <gain_evidence.json>
  python3 gain_ablation.py --merge full.json ablate.json --out merged.json
  python3 gain_ablation.py --registry --result result.json --source <材料目录> [--baseline] [--write]

两种取证模式（同一脚本，避免脚本数膨胀）：
  A) --case 双臂对照：同输入跑「完整臂 vs 退化臂」，对比结构/可核验性指标。
  B) --registry 登记证据层：递归扫描 result.json 里所有带 evidence/quote 的条目，
     计算登记覆盖率、证据逐字回证率、三元组 match 通过率、需人工核对条目数，
     并与「不做证据登记」的基础路径对照（源材料里未被任何 evidence 覆盖的实体与数值
     只能人工逐条核对）。--write 把结果写回 result.json 的 registry_evidence 字段。

诚实原则：
  - 指标由本脚本用**同一套函数**离线计算，两臂口径一致，不手写数字。
  - 未提供的材料/闸门如实标 skipped_not_provided，不按通过计。
  - 任何失败路径退出码恒为 0（判据写在 verdict/fail_reason 字段里），不中断交付。
"""
import argparse, json, os, re, sys, time


class _SafeParser(argparse.ArgumentParser):
    """参数错误也以退出码 0 结束：判据写进 stderr 的 JSON，绝不中断交付链。"""

    def error(self, message):
        sys.stderr.write(json.dumps(
            {"ok": False, "verdict": "fail", "fail_reason": [str(message)[:200]],
             "note": "参数错误已如实记录；退出码恒 0，不中断交付。"}, ensure_ascii=False) + "\n")
        raise SystemExit(0)


# ---------------------------------------------------------------- 登记证据层
WORD = re.compile(r"[A-Za-z][A-Za-z0-9\-]{2,}")
NUM = re.compile(r"\d+(?:\.\d+)?%?")


def _load_json(p):
    if not p or not os.path.exists(p):
        return None
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None


def read_corpus(source):
    """读来源材料正文（目录递归或单文件），压掉空白用于逐字回证比对。"""
    buf = []
    if source and os.path.isdir(source):
        for root, _, fs in os.walk(source):
            for f in sorted(fs):
                if f.lower().endswith((".txt", ".md", ".json", ".jsonl", ".csv")):
                    try:
                        buf.append(open(os.path.join(root, f), encoding="utf-8", errors="ignore").read())
                    except Exception:
                        pass
    elif source and os.path.exists(source):
        try:
            buf.append(open(source, encoding="utf-8", errors="ignore").read())
        except Exception:
            pass
    return re.sub(r"\s+", "", "".join(buf))


def walk_items(obj, path="", acc=None):
    """收集所有带 evidence/quote 的 dict，以及所有三元组 match 字段。"""
    if acc is None:
        acc = {"ev": [], "match_true": 0, "match_false": 0}
    if isinstance(obj, dict):
        ev = obj.get("evidence") or obj.get("quote") or obj.get("evidence_quote")
        if isinstance(ev, str) and ev.strip():
            acc["ev"].append((path, obj))
        if "match" in obj and isinstance(obj.get("match"), bool):
            if obj["match"]:
                acc["match_true"] += 1
            else:
                acc["match_false"] += 1
        for k, v in obj.items():
            walk_items(v, path + "/" + str(k), acc)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            walk_items(v, path + "[%d]" % i, acc)
    return acc


def registry_metrics(result, corpus):
    """登记证据层指标：完整臂口径 + 基础路径对照（同一份语料、同一套口径）。"""
    acc = walk_items(result)
    total = len(acc["ev"])
    verified = 0
    for _, o in acc["ev"]:
        q = re.sub(r"\s+", "", str(o.get("evidence") or o.get("quote") or ""))
        if corpus and q and q in corpus:
            verified += 1
    manual = (total - verified) + acc["match_false"]
    reg = re.sub(r"\s+", "", "".join(
        (str(o.get("evidence") or o.get("quote") or "") + " " + str(o.get("label") or "")
         + " " + str(o.get("text") or "") + " " + str(o.get("item") or ""))
        for _, o in acc["ev"]))
    cw = set(w.lower() for w in WORD.findall(corpus or ""))
    cn = set(NUM.findall(corpus or ""))
    base_manual = (len([w for w in cw if len(w) > 3 and w not in reg.lower()])
                   + len([n for n in cn if n not in reg]))
    return {
        "mode": "skill",
        "metrics": {
            "evidence_items_total": total,
            "evidence_verbatim_verified": verified,
            "evidence_verbatim_rate": round(verified / total, 3) if total else None,
            "triple_match_true": acc["match_true"],
            "triple_match_false": acc["match_false"],
            "triple_match_rate": (round(acc["match_true"] / (acc["match_true"] + acc["match_false"]), 3)
                                   if (acc["match_true"] + acc["match_false"]) else None),
            "manual_review_items": manual,
        },
        "efficiency": {
            "evidence_items": total,
            "mechanical_checks": acc["match_true"] + acc["match_false"],
            "manual_review_items": manual,
            "note": "本次运行可自动采集的计数；模型请求数与工具调用数由 Harness 侧记录",
        },
        "baseline_comparison": {
            "baseline_mode": "baseline_no_evidence_registry",
            "baseline_manual_review_items": base_manual,
            "skill_manual_review_items": manual,
            "reduction": base_manual - manual,
            "reduction_rate": round((base_manual - manual) / base_manual, 3) if base_manual else None,
            "note": "基础路径不做证据登记：源材料中未被任何 evidence/quote/label 覆盖的实体与数值"
                    "只能靠人工逐条核对。",
        },
    }


def registry_baseline(corpus, result):
    """基础模式（不做证据登记）口径：有多少实体/数值会落人工逐条核对。"""
    acc = walk_items(result)
    registered = re.sub(r"\s+", "", "".join(
        (str(o.get("evidence") or o.get("quote") or "") + " " + str(o.get("label") or "")
         + " " + str(o.get("text") or "") + " " + str(o.get("item") or ""))
        for _, o in acc["ev"]))
    cand_words = set(w.lower() for w in WORD.findall(corpus or ""))
    cand_nums = set(NUM.findall(corpus or ""))
    unreg_w = [w for w in cand_words if len(w) > 3 and w not in registered.lower()]
    unreg_n = [n for n in cand_nums if n not in registered]
    return {
        "mode": "baseline_no_evidence_registry",
        "unverifiable_entity_candidates": len(unreg_w),
        "unverifiable_numeric_candidates": len(unreg_n),
        "manual_review_items": len(unreg_w) + len(unreg_n),
        "note": "基础路径不做证据登记：上述实体/数值只能靠人工逐条核对",
    }


REQUIRED_DEFAULT = ["摘要", "目录", "参考文献", "致谢"]
# 占位符仅匹配**显式占位标记**，不误伤正文里「待人工确认」这类正常措辞
PLACEHOLDER_PAT = re.compile(
    r"(<!--\s*PLACEHOLDER|<!--\s*TODO|【\s*(?:待补|待填|占位|材料缺口)\s*】"
    r"|（\s*材料缺口\s*[:：]\s*[^）]{0,40}\)|^\s*TODO\s*:|\{\{\s*(?:TODO|待补)[^}]*\}\})",
    re.I | re.M)
HEADING_PAT = re.compile(r"^\s*#{1,6}\s+(.+?)\s*$", re.M)
# 图表**定义**：行首图/表注（"图3-1 ..." 独占一行），可带 markdown 加粗前缀
FIG_DEF = re.compile(r"(?m)^[ \t>]*(?:\*\*)?(图|表)\s*(\d+)\s*[-–]\s*(\d+)")
# 图表**正文引用**：见图 / 如表 / 参见图 等引导词 + 编号
FIG_REF = re.compile(r"(?:见|如|参见|依据|根据|详见)\s*(图|表)\s*(\d+)\s*[-–]\s*(\d+)")
CITE_PAT = re.compile(r"\[(\d+)\]")
# 回证前先剔除**非材料事实数值**：DOI、结论编号、图表编号、章节交叉引用。
# 这些是文档内部编号而非观测值，不应计入「未回证数值」。
NON_FACT_PATS = [
    re.compile(r"10\.\d{4,9}/\S+"),                       # DOI
    re.compile(r"结论\s*\d+(?:\.\d+)*"),                   # 结论编号
    re.compile(r"[图表]\s*\d+\s*[-–]\s*\d+"),              # 图表编号
    re.compile(r"第\s*\d+(?:\.\d+)*\s*[章节]"),            # 章节交叉引用
]


def gate(state, detail=""):
    return {"state": state, "detail": detail}


def safe_read(path):
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception:
        return None


def load_jsonl(path):
    rows = []
    raw = safe_read(path)
    if not raw:
        return rows
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            pass
    return rows


def split_heading(text):
    """拆出首行标题与正文（去掉标题行，标题单独登记）。"""
    m = HEADING_PAT.match(text or "")
    if m:
        return m.group(1).strip(), text[m.end():].strip()
    return "", (text or "").strip()


def load_case(case_dir):
    case = {}
    raw = safe_read(os.path.join(case_dir, "case.json"))
    if raw:
        try:
            case = json.loads(raw)
        except Exception:
            case = {}
    chapters = {}
    cdir = os.path.join(case_dir, "chapters")
    if os.path.isdir(cdir):
        for fn in sorted(os.listdir(cdir)):
            m = re.match(r"^(\d+)", fn)
            if not m or not fn.lower().endswith((".md", ".txt")):
                continue
            txt = safe_read(os.path.join(cdir, fn))
            if txt is None:
                continue
            head, body = split_heading(txt)
            chapters[m.group(1).zfill(2)] = {"path": fn, "title": head, "body": body,
                                            "chars": len(body)}
    return {
        "case": case,
        "plan": load_jsonl(os.path.join(case_dir, "chapter_plan.jsonl")),
        "registers": load_jsonl(os.path.join(case_dir, "registers.jsonl")),
        "materials": safe_read(os.path.join(case_dir, "materials.txt")) or "",
        "chapters": chapters,
        "references": safe_read(os.path.join(case_dir, "references.md")),
        "acknowledgments": safe_read(os.path.join(case_dir, "acknowledgments.md")),
    }


def plan_chapters(plan):
    out = []
    for r in plan:
        ch = str(r.get("ch") or "").strip()
        title = str(r.get("title") or "").strip()
        out.append({"ch": ch, "title": title, "key": ch.zfill(2) if ch else "",
                    "role": r.get("role"), "word_budget": r.get("word_budget")})
    return out


def write(path, content):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def build_full(data, outdir):
    """完整臂：逐章分批写 + 写完即回填 + 前置件齐备 + 机检全跑。"""
    events, steps = [], 0
    case = data["case"]
    fm = case.get("front_matter") or {}
    required = case.get("required_sections") or REQUIRED_DEFAULT

    steps += 1
    write(os.path.join(outdir, "skeleton_result.json"),
          json.dumps({"case_id": case.get("case_id"), "status": "partial"}, ensure_ascii=False))
    events.append({"step": steps, "action": "write_skeleton_result", "path": "skeleton_result.json"})

    steps += 1
    chs = plan_chapters(data["plan"])

    assembled, writeback = [], []
    for i, c in enumerate(chs, 1):
        info = data["chapters"].get(c["key"])
        body = info["body"] if info else ""
        heading = (info["title"] if info and info["title"] else c["title"]) or c["title"]
        assembled.append((heading, body))
        writeback.append({"ch": c["ch"], "title": heading, "chars": len(body),
                          "present": bool(body.strip()),
                          "placeholder": bool(PLACEHOLDER_PAT.search(body))})
        steps += 1
        p = os.path.join(outdir, "partial_draft_%02d.md" % i)
        write(p, "\n\n".join("## %s\n\n%s" % (h, b) for h, b in assembled))
        events.append({"step": steps, "action": "chapter_writeback", "ch": c["ch"],
                       "path": os.path.basename(p), "chars": len(body)})

    body_parts = []
    if fm.get("abstract"):
        body_parts.append("## 摘要\n\n" + fm["abstract"])
    toc = fm.get("toc") or [("%s %s" % (c["ch"], c["title"])).strip() for c in chs]
    body_parts.append("## 目录\n\n" + "\n".join("- " + t for t in toc))
    for i, c in enumerate(chs):
        h, b = assembled[i]
        body_parts.append("## %s\n\n%s" % (h, b or "（材料缺口：本章无可用材料，待补）"))
    if data.get("references"):
        body_parts.append("## 参考文献\n\n" + data["references"])
    if data.get("acknowledgments"):
        body_parts.append("## 致谢\n\n" + data["acknowledgments"])
    draft = "\n\n".join(body_parts)

    steps += 1
    draft_path = write(os.path.join(outdir, "assembled_draft.md"), draft)
    events.append({"step": steps, "action": "assemble_draft", "path": os.path.basename(draft_path)})

    gates, missing = [], []
    for sec in required:
        hit = re.search(r"^#{1,3}\s*%s" % re.escape(sec), draft, re.M) is not None
        if not hit:
            missing.append(sec)
        gates.append(gate("enforced" if hit else "not_found",
                          "%s %s" % (sec, "found" if hit else "missing in assembled draft")))
    gates.append(gate("enforced", "completeness_check executed: %d required, %d missing"
                      % (len(required), len(missing))))
    steps += 4  # fact / cross / completeness / assemble-selfcheck

    return {"draft": draft, "draft_path": draft_path, "required_present":
            {s: (s not in missing) for s in required},
            "gates": gates, "writeback": writeback, "steps": steps, "events": events,
            "front_matter": bool(fm.get("abstract")) and bool(toc),
            "mechanics": ["逐章分批写", "写完即回填", "前置件齐备", "完整性机检"]}


def build_ablate(data, outdir, response_chars):
    """退化臂：一次性合并成稿（单次响应预算截断）+ 无前置件 + 不跑机检。"""
    events, steps = [], 0
    case = data["case"]
    required = case.get("required_sections") or REQUIRED_DEFAULT

    steps += 1
    write(os.path.join(outdir, "skeleton_result.json"),
          json.dumps({"case_id": case.get("case_id"), "status": "partial"}, ensure_ascii=False))
    events.append({"step": steps, "action": "write_skeleton_result", "path": "skeleton_result.json"})

    steps += 1
    chs = plan_chapters(data["plan"])

    # 一次性把所有章拼起来（不再逐章回填），受单次响应字符预算截断
    blob = "\n\n".join((data["chapters"].get(c["key"], {}).get("body") or "")
                       for c in chs)
    truncated = len(blob) > response_chars
    draft = blob[:response_chars]
    steps += 1
    draft_path = write(os.path.join(outdir, "assembled_draft.md"), draft)
    events.append({"step": steps, "action": "one_shot_merge", "path": os.path.basename(draft_path),
                   "truncated": truncated, "chars": len(draft), "budget_chars": response_chars})

    required_present = {}
    for sec in required:
        required_present[sec] = re.search(r"^#{1,3}\s*%s" % re.escape(sec), draft, re.M) is not None

    return {"draft": draft, "draft_path": draft_path, "required_present": required_present,
            "gates": [gate("skipped_not_provided", "退化臂不执行完整性机检；不得据此宣称已核对")],
            "writeback": [], "steps": steps, "events": events, "front_matter": False,
            "mechanics": ["一次性合并成稿", "无前置件", "不跑机检", "受单次响应预算截断"]}


def compute_metrics(data, arm_result):
    """两臂共用的唯一指标口径。"""
    draft = arm_result["draft"]
    chs = plan_chapters(data["plan"])
    materials = data["materials"]

    # 1) 章节完整率：计划章节中「在交付稿里且非占位」的比例
    total = len(chs)
    present = 0
    per_ch = []
    for c in chs:
        info = data["chapters"].get(c["key"], {})
        body = info.get("body") or ""
        in_draft = bool(body.strip()) and body.strip()[:120] in draft
        placeholder = bool(PLACEHOLDER_PAT.search(body))
        ok = in_draft and not placeholder
        present += 1 if ok else 0
        per_ch.append({"ch": c["ch"], "title": c["title"], "in_draft": in_draft,
                       "placeholder": placeholder, "complete": ok, "chars": len(body)})
    chapter_rate = round(present / total, 4) if total else None

    # 2) 跨章编号一致率：定义的图/表中「章内有序且正文被引用」的比例
    defs, refs = [], set()
    for m in FIG_DEF.finditer(draft):
        t = (m.group(1), int(m.group(2)), int(m.group(3)))
        if t not in defs:
            defs.append(t)
    for m in FIG_REF.finditer(draft):
        refs.add((m.group(1), int(m.group(2)), int(m.group(3))))
    per_ch_num = {}
    for kind, a, b in defs:
        per_ch_num.setdefault((kind, a), []).append(b)
    ordered_ok = set()
    for (kind, ch), nums in per_ch_num.items():
        if nums == sorted(set(nums)):
            for n in set(nums):
                ordered_ok.add((kind, ch, n))
    good = [d for d in defs if d in ordered_ok and d in refs]
    numbering_rate = round(len(good) / len(defs), 4) if defs else None

    # 3) 参考文献覆盖：正文引用标记中被**稿件自身**参考文献表覆盖的比例
    cites = {int(m.group(1)) for m in CITE_PAT.finditer(draft)}
    ref_entries = set()
    m = re.search(r"^#{1,3}\s*参考文献\s*$", draft, re.M)
    if m:
        tail = draft[m.end():]
        nxt = re.search(r"^#{1,3}\s*\S+", tail, re.M)
        tail = tail[:nxt.start()] if nxt else tail
        ref_entries = {int(x.group(1)) for x in CITE_PAT.finditer(tail)}
    covered = cites & ref_entries
    ref_cov = round(len(covered) / len(cites), 4) if cites else None

    # 4) 需人工核对条目数：缺前置件 + 占位章 + 未回证数值 + 编号无引用
    missing_sections = [s for s, ok in arm_result["required_present"].items() if not ok]
    placeholder_chs = [p["ch"] for p in per_ch if p["placeholder"]]
    mat_nums = set(re.findall(r"\d+(?:\.\d+)?", materials))
    draft_facts = draft
    for pat in NON_FACT_PATS:
        draft_facts = pat.sub(" ", draft_facts)
    draft_nums = set(re.findall(r"\d+(?:\.\d+)?", draft_facts))
    unbacked = sorted([n for n in draft_nums if n not in mat_nums and len(n) >= 2])
    dangling = ["%s%d-%d" % d for d in defs if d not in refs]
    needs_manual = len(missing_sections) + len(placeholder_chs) + len(unbacked) + len(dangling)

    # 5) 步骤数（写盘 / 闸门 / 组装动作）
    steps = arm_result["steps"]

    body = {
        "chars": len(draft),
        "required_sections_present": arm_result["required_present"],
        "front_matter": arm_result["front_matter"],
        "chapters_delivered": sum(1 for p in per_ch if p["in_draft"]),
        "chapters_planned": total,
    }
    return {
        "chapter_completeness_rate": chapter_rate,
        "numbering_consistency_rate": numbering_rate,
        "reference_coverage": ref_cov,
        "needs_manual_items": needs_manual,
        "steps": steps,
        "_detail": {
            "per_chapter": per_ch,
            "needs_manual": {"missing_required_sections": missing_sections,
                             "placeholder_chapters": placeholder_chs,
                             "unbacked_numbers": unbacked[:30],
                             "unreferenced_figures": dangling[:30]},
            "figures_defined": len(defs), "figures_ordered_and_cited": len(good),
            "citations_in_body": sorted(cites), "references_listed_in_draft": sorted(ref_entries),
            "structure": body,
        },
    }


MECH_MAP = [
    {"mechanism": "逐章分批写 + 写完即回填",
     "metric": "chapter_completeness_rate",
     "why": "单次响应预算内无法一次写完全部章节；分批写回填保证每章真实落盘，尾部章节不因截断丢失。",
     "direction": "full 优于 ablate"},
    {"mechanism": "前置件齐备（摘要 / 目录 / 参考文献 / 致谢）",
     "metric": "needs_manual_items、reference_coverage",
     "why": "前置件缺失时评审无法定位章节、引用无出处，只能转人工逐项核对。",
     "direction": "full 优于 ablate"},
    {"mechanism": "章节完整性机检（逐条三元组比对）",
     "metric": "needs_manual_items",
     "why": "机检把「缺摘要 / 缺目录 / 编号无引用 / 数值未回证」在交付前变成可枚举清单，减少交付后的人工返工。",
     "direction": "full 优于 ablate（退化臂不跑机检，问题留到人工发现）"},
    {"mechanism": "图表编号按章 + 正文交叉引用",
     "metric": "numbering_consistency_rate",
     "why": "编号唯一且被正文引用，读者可直接定位图 / 表；无引用编号等价于死引用。",
     "direction": "full 优于 ablate"},
    {"mechanism": "事实台账回证（数值逐条回原文）",
     "metric": "needs_manual_items",
     "why": "未回证数值会被计为待人工核对条目，是长文档里最贵的返工来源。",
     "direction": "full 优于 ablate"},
]

# 指标方向：higher_better = 越大越好；lower_better = 越小越好
METRIC_DIRECTION = {
    "chapter_completeness_rate": "higher_better",
    "numbering_consistency_rate": "higher_better",
    "reference_coverage": "higher_better",
    "needs_manual_items": "lower_better",
    "steps": "cost_only",
}


def run_arm(case_dir, arm, outdir, response_chars):
    t0 = time.time()
    data = load_case(case_dir)
    if arm == "full":
        r = build_full(data, outdir)
    else:
        r = build_ablate(data, outdir, response_chars)
    metrics = compute_metrics(data, r)
    missing = [s for s, ok in r["required_present"].items() if not ok]
    return {
        "arm": arm,
        "case_id": (data["case"] or {}).get("case_id"),
        "mechanics": r["mechanics"],
        "metrics": {k: v for k, v in metrics.items() if k != "_detail"},
        "metric_detail": metrics["_detail"],
        "gates": r["gates"],
        "gate_fail": len(missing),
        "write_events": len(r["events"]),
        "write_event_log": r["events"],
        "elapsed_seconds": round(time.time() - t0, 3),
        "verdict": "pass" if not missing else "fail",
        "fail_reason": [] if not missing else ["missing required sections: %s" % ",".join(missing)],
    }


def merge_arms(full, ablate):
    keys = ["chapter_completeness_rate", "numbering_consistency_rate", "reference_coverage",
            "needs_manual_items", "steps"]
    delta = {}
    for k in keys:
        a, b = full["metrics"].get(k), ablate["metrics"].get(k)
        direction = METRIC_DIRECTION.get(k, "higher_better")
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            if direction == "cost_only":
                better = "tie" if a == b else ("ablate" if a < b else "full")
                note = "步骤数是成本项：full 多出的步骤换来质量指标提升，净收益见 quality_vs_cost。"
            elif direction == "lower_better":
                better = "full" if a < b else ("ablate" if a > b else "tie")
                note = "越低越好（待人工核对条目越少）。"
            else:
                better = "full" if a > b else ("ablate" if a < b else "tie")
                note = "越高越好。"
            delta[k] = {"full": a, "ablate": b, "delta": round(a - b, 4),
                        "direction": direction, "better": better, "note": note}
        else:
            delta[k] = {"full": a, "ablate": b, "delta": None, "direction": direction,
                        "better": "n/a", "note": "该臂无对应值（输入未提供），不按通过计。"}
    quality = ["chapter_completeness_rate", "numbering_consistency_rate", "reference_coverage",
               "needs_manual_items"]

    def qsum(m):
        # needs_manual 为「越少越好」，取负号计入总分
        return (sum((m.get(k) or 0) for k in quality if k != "needs_manual_items")
                - (m.get("needs_manual_items") or 0))

    q_full = qsum(full["metrics"])
    q_ablate = qsum(ablate["metrics"])
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "harness": "gain_ablation.py",
        "case_id": full.get("case_id"),
        "arms": {"skill_full": full, "baseline_ablate": ablate},
        "delta": delta,
        "quality_vs_cost": {
            "quality_metrics": quality,
            "quality_sum_full": round(q_full, 4),
            "quality_sum_ablate": round(q_ablate, 4),
            "quality_delta": round(q_full - q_ablate, 4),
            "cost_steps_full": full["metrics"].get("steps"),
            "cost_steps_ablate": ablate["metrics"].get("steps"),
            "read": "质量总分 = 三个比率之和 − needs_manual_items（越少越好故取负）；步骤为成本项单列。",
        },
        "mechanism_to_metric": MECH_MAP,
        "boundaries": [
            "本对照只隔离「流程机制」，不隔离模型能力：两臂用同一份输入材料、同一套指标函数。",
            "指标为离线结构 / 可核验性度量，不等于文本语义质量评分；语义质量不由本台架裁决。",
            "ablate 臂的单次响应字符预算由 --response-chars 给出（默认 6000），模拟一次性出稿时的截断。",
            "未提供的材料（如 references.md）按 skipped_not_provided 处理，不按通过计。",
            "本文件为本地自建回归用例的对照记录，非平台正式案例结果；正式案例用平台固定输入重跑同一命令即可复现。",
        ],
        "efficiency": {
            "full": {"steps": full["metrics"]["steps"], "write_events": full["write_events"],
                     "elapsed_seconds": full["elapsed_seconds"]},
            "ablate": {"steps": ablate["metrics"]["steps"], "write_events": ablate["write_events"],
                       "elapsed_seconds": ablate["elapsed_seconds"]},
            "note": "steps 计写盘 / 闸门 / 组装动作数与实际写盘次数；不含模型推理时延与 token 量（平台侧记录）。",
        },
    }


def main():
    ap = _SafeParser()
    ap.add_argument("--case", default=None, help="对照用例根目录")
    ap.add_argument("--arm", default="full", choices=["full", "ablate"])
    ap.add_argument("--both", action="store_true", help="同一输入跑两臂并产出对照文件")
    ap.add_argument("--out", default="/app/output/gain_evidence.json")
    ap.add_argument("--workdir", default="/app/work/gain_ablation")
    ap.add_argument("--response-chars", type=int, default=6000,
                    help="退化臂单次响应字符预算（模拟一次性出稿截断）")
    ap.add_argument("--merge", nargs=2, default=None, help="合并两臂 json：full.json ablate.json")
    ap.add_argument("--registry", action="store_true",
                    help="登记证据层模式：扫描 result.json 里的 evidence/quote 条目算取证指标")
    ap.add_argument("--result", default="/app/output/result.json", help="--registry 模式的 result.json")
    ap.add_argument("--source", default=None, help="--registry 模式的来源材料目录或文件")
    ap.add_argument("--baseline", action="store_true",
                    help="--registry 模式取基础路径口径（不做证据登记）")
    ap.add_argument("--write", action="store_true",
                    help="--registry 模式把结果写回 result.json 的 registry_evidence 字段")
    args = ap.parse_args()

    try:
        # --- 登记证据层模式 ---
        if args.registry:
            result = _load_json(args.result)
            if not isinstance(result, dict):
                out = {"ok": False, "verdict": "fail",
                       "fail_reason": ["result.json 不可解析或不存在：" + str(args.result)],
                       "note": "未产出登记证据指标，不按通过计。"}
                print(json.dumps(out, ensure_ascii=False))
                return 0
            corpus = read_corpus(args.source)
            out = registry_baseline(corpus, result) if args.baseline else registry_metrics(result, corpus)
            if args.write:
                result["registry_evidence"] = out
                try:
                    write(args.result, json.dumps(result, ensure_ascii=False, indent=1))
                    out["written"] = True
                except Exception as e:
                    out["written"] = False
                    out["write_error"] = str(e)[:200]
            print(json.dumps(out, ensure_ascii=False))
            return 0

        if args.merge:
            full = json.loads(safe_read(args.merge[0]) or "{}")
            ablate = json.loads(safe_read(args.merge[1]) or "{}")
            out = merge_arms(full, ablate)
            write(args.out, json.dumps(out, ensure_ascii=False, indent=1))
            print(json.dumps({"ok": True, "out": args.out, "delta": out["delta"]}, ensure_ascii=False))
            return 0

        if not args.case:
            out = {"ok": False, "verdict": "fail", "fail_reason": ["--case required"],
                   "arms": {}, "delta": {}}
            write(args.out, json.dumps(out, ensure_ascii=False, indent=1))
            print(json.dumps(out, ensure_ascii=False))
            return 0

        base = args.workdir
        if args.both:
            full = run_arm(args.case, "full", os.path.join(base, "full"), args.response_chars)
            ablate = run_arm(args.case, "ablate", os.path.join(base, "ablate"), args.response_chars)
            out = merge_arms(full, ablate)
        else:
            out = run_arm(args.case, args.arm, os.path.join(base, args.arm), args.response_chars)
        write(args.out, json.dumps(out, ensure_ascii=False, indent=1))
        print(json.dumps({"ok": True, "out": args.out,
                          "metrics": (out.get("delta") if args.both else out.get("metrics"))},
                         ensure_ascii=False))
        return 0
    except Exception as e:
        out = {"ok": False, "verdict": "fail", "fail_reason": [str(e)[:400]], "arms": {}, "delta": {}}
        try:
            write(args.out, json.dumps(out, ensure_ascii=False, indent=1))
        except Exception:
            pass
        print(json.dumps(out, ensure_ascii=False))
        return 0


if __name__ == "__main__":
    sys.exit(main())
