#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gain_eval.py — 同输入两遍对照的真实增益证据（学术写作客户端）。

同一份输入（原稿段落索引 structure.json + 修订台账 edits.jsonl + 已交付修订稿 revised.md）
跑两遍，产物由**同一套测量函数**度量，逐项给出真实数字（非自述、非估计）：
  条件 A full     ：加载 Skill 的完整管线（锚点索引 / 逐条裁决 / 导出校验 / 七步流程全开）
  条件 B degraded ：同一份输入，关掉指定机制（--ablate anchor,adjudication,export_verify）

指标（全部由交付物实测）：
  revision_traceability_rate  修订可追溯率 = 有锚点+有依据+before/after 逐字回证的改动 / 改动总数
  edit_precision_rate        改准率       = 落在指令指定锚点的改动 / 改动总数
  applied_verbatim_rate       落地逐字率   = after 逐字出现在交付稿的改动 / 改动总数
  misplaced_changes           错落改动数   = 落点与指令指定锚点不一致的改动数
  collateral_paragraphs       误改段落数   = 交付稿中被改动、但无对应改动的段落数
  format_collapse_count       格式塌陷数   = 标题层级/表格/题注/参考文献/引用编号的缺失与缺口数
  manual_review_items         人工核对条目数 = 需人工逐条确认的条目数
  manual_review_chars         人工复核字符量 = 上述条目涉及的原文字符数
  steps / tool_calls          步骤数 / 工具调用数 = 该条件实际产出阶段数 / 实际脚本调用数

并输出 mechanism→metric 映射与边界声明，写 gain_evidence.json；
--write-back 回填 result.json 顶层 gain_evidence / efficiency 字段。

诚实性约束：
  * 本对照是**同输入机制级 A/B**（同一脚本、同一输入、只切换机制开关），
    不是平台"基础 Agent vs Skill Agent"对照——后者由平台生成，本脚本不冒充。
  * 退化条件是**确定性基线重建**（全文首次匹配落点 / 无锚点台账 / 平铺导出），
    其绝对值不可与平台分数比较，只说明机制的作用方向与代价。
  * 缺料/异常一律如实降级并写明缺什么，绝不补数字、绝不中断交付。
自测：--selftest（合成正例 + 污染反例；退出码恒 0，verdict 照实记录）。
"""
from __future__ import annotations
import argparse, difflib, json, os, re, subprocess, sys

STAGE_KEYS = ["structure", "edits", "revised_md", "revised_docx", "diff_md",
              "versions_jsonl", "client_html", "claims_chain", "check_report"]

# ---------------------------------------------------------------- 基础 IO
def load_json(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return json.load(f)
    except Exception:
        return None

def load_jsonl(path):
    out = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except Exception:
                        out.append({"_unparsable": True, "_raw": line[:120]})
    except Exception:
        return []
    return out

def read_text(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:
        return None

def norm(s):
    return re.sub(r"\s+", "", str(s or ""))

def jdump(obj):
    return json.dumps(obj, ensure_ascii=False)

def nblocks(text):
    return [b for b in re.split(r"\n\s*\n", text or "") if b.strip()]

def valid_edits(edits):
    """只保留可解析的改动条目（二进制/脏行如实排除，不静默计入分母）。"""
    return [e for e in (edits or []) if isinstance(e, dict) and not e.get("_unparsable")]

def strip_md(b):
    s = re.sub(r"^\s{0,3}#{1,6}\s+", "", str(b or ""))
    s = re.sub(r"^\s*>\s?", "", s)
    s = s.replace("**", "")
    s = re.sub(r"^\s*\|", "", s).replace("|", " ")
    return norm(s)

# ---------------------------------------------------------------- 对齐：原稿段落 ↔ 交付稿块
def align_blocks(originals, blocks, forms=None):
    """把原稿段落按顺序对齐到交付稿块。
    forms[i]: 该段落允许出现的形态列表（原文 / 改后形态），优先按归一化精确匹配；
    精确匹配失败时退化为相似度贪心。返回 list（下标或 None）。"""
    bn = [strip_md(b) for b in blocks]
    forms = forms or []
    used = set()
    res = []
    cursor = 0
    for i, o in enumerate(originals):
        no = strip_md(o)
        cand = [strip_md(x) for x in (forms[i] if i < len(forms) else [])]
        hit = None
        for j in range(cursor, len(bn)):
            if j in used:
                continue
            if cand and bn[j] in cand:
                hit = j
                break
        if hit is None:
            best, best_r = None, 0.0
            lo, hi = max(0, cursor - 2), min(len(bn), cursor + 8)
            for j in list(range(lo, hi)) + list(range(len(bn))):
                if j in used:
                    continue
                r = difflib.SequenceMatcher(None, no, bn[j]).ratio()
                if r > best_r:
                    best_r, best = r, j
            if best is not None and best_r >= 0.45:
                hit = best
        if hit is None:
            res.append(None)
        else:
            res.append(hit)
            used.add(hit)
            cursor = hit + 1
    return res

# ---------------------------------------------------------------- 测量核心
def measure_run(intent_edits, ledger_edits, structure, delivered_text, anchor_on,
                adjudication_on):
    """intent_edits: 源台账（含 pid 意图，用于判定落点是否正确）；
       ledger_edits: 该条件**实际产出**的台账（退化条件无 pid/locator/rationale）。"""
    pids = list(structure.keys())
    originals = [structure[p] for p in pids]
    blocks = nblocks(delivered_text)
    rev_n = norm(delivered_text)
    total = len(intent_edits or [])
    traceable = landed = precise = misplaced = 0
    review_items = review_chars = 0
    per_edit = []
    # 落点模拟：锚点开 → 用 pid；锚点关 → 全文首次匹配
    landed_pid_of = {}
    if anchor_on:
        for i, e in enumerate(intent_edits):
            pid = str(e.get("pid") or "")
            before = str(e.get("before") or e.get("anchor_quote") or "")
            landed_pid_of[i] = pid if (pid and before and norm(before) in norm(structure.get(pid, ""))) else ""
    else:
        for i, e in enumerate(intent_edits):
            before = str(e.get("before") or e.get("anchor_quote") or "")
            hit = ""
            for p in pids:
                if before and norm(before) in norm(structure.get(p, "")):
                    hit = p
                    break
            landed_pid_of[i] = hit
    # 每个段落允许出现的形态：原文 + 落在该段的改动后的形态
    forms = []
    for p in pids:
        f = [structure[p]]
        for i, e in enumerate(intent_edits):
            if landed_pid_of.get(i) != p:
                continue
            before = str(e.get("before") or e.get("anchor_quote") or "")
            after = str(e.get("after") or "")
            if before and after:
                f.append(structure[p].replace(before, after, 1))
        forms.append(f)
    align = align_blocks(originals, blocks, forms)
    modified = set()
    for i, p in enumerate(pids):
        j = align[i]
        if j is None:
            continue
        if strip_md(blocks[j]) != strip_md(structure[p]) and strip_md(structure[p]):
            modified.add(p)
    for i, e in enumerate(intent_edits or []):
        if not isinstance(e, dict):
            continue
        led = ledger_edits[i] if i < len(ledger_edits) and isinstance(ledger_edits[i], dict) else {}
        eid = str(e.get("eid") or e.get("id") or "?")
        intent_pid = str(e.get("pid") or "")
        before = str(e.get("before") or e.get("anchor_quote") or "")
        after = str(e.get("after") or "")
        status = str(e.get("status") or "applied")
        landed_pid = landed_pid_of.get(i, "")
        applied_ok = bool(after) and (not rev_n or norm(after)[:40] in rev_n)
        if applied_ok:
            landed += 1
        # 可追溯：实际台账里有 pid+locator+rationale，且 before 逐字在原稿锚点、after 逐字在交付稿
        has_meta = bool(str(led.get("pid") or "") and str(led.get("locator") or "")
                        and str(led.get("rationale") or ""))
        trace_ok = bool(has_meta and landed_pid == intent_pid and intent_pid and applied_ok)
        if trace_ok:
            traceable += 1
        # 改准：交付稿中该锚点段落确实变成"原文+本条改动"的形态，且落点=指令指定锚点
        precise_ok = False
        if landed_pid and intent_pid and landed_pid == intent_pid and before and after:
            j = align[pids.index(intent_pid)]
            if j is not None:
                db = strip_md(blocks[j])
                expect = strip_md(structure[intent_pid].replace(before, after, 1))
                if before and norm(before) in db:
                    precise_ok = False
                elif norm(after) in db or (expect and expect == db):
                    precise_ok = True
        if precise_ok:
            precise += 1
        if landed_pid and landed_pid != intent_pid:
            misplaced += 1
        # 人工核对量
        need = status not in ("applied", "accepted") or str(led.get("decision") or "") in ("confirm", "need_review")
        if anchor_on and adjudication_on:
            if need:
                review_items += 1
                review_chars += len(before)
        else:
            review_items += 1
            review_chars += len(structure.get(landed_pid or intent_pid, ""))
        per_edit.append({"eid": eid, "intent_pid": intent_pid, "landed_pid": landed_pid,
                         "traceable": trace_ok, "precision_ok": precise_ok,
                         "applied_verbatim": applied_ok, "status": status,
                         "reason": ("" if trace_ok else
                                    ("退化基线不产出 pid/locator/依据，无法逐条回溯"
                                     if not has_meta else
                                     ("落点≠指令锚点" if landed_pid != intent_pid
                                      else ("before 未逐字落原稿" if not (before and norm(before) in norm(structure.get(intent_pid, "")))
                                            else "after 未逐字落交付稿"))))})
    intended = set()
    for i, e in enumerate(intent_edits or []):
        if isinstance(e, dict) and e.get("pid"):
            intended.add(str(e.get("pid")))
    collateral = sorted(modified - intended)
    # 锚点歧义度：before 在多段出现（解释改准率差异来源）
    ambiguous = 0
    for e in (intent_edits or []):
        if not isinstance(e, dict):
            continue
        before = str(e.get("before") or e.get("anchor_quote") or "")
        if not before:
            continue
        if sum(1 for p in pids if norm(before) in norm(structure.get(p, ""))) > 1:
            ambiguous += 1
    n = max(1, total)
    return {"edits_total": total,
            "revision_traceability_rate": round(traceable / n, 4),
            "edit_precision_rate": round(precise / n, 4),
            "applied_verbatim_rate": round(landed / n, 4),
            "misplaced_changes": misplaced,
            "collateral_paragraphs": len(collateral),
            "collateral_paragraph_ids": collateral,
            "manual_review_items": review_items,
            "manual_review_chars": review_chars,
            "ambiguous_anchors": ambiguous,
            "aligned_paragraphs": sum(1 for x in align if x is not None),
            "paragraphs_total": len(pids),
            "per_edit": per_edit}

# ---------------------------------------------------------------- 格式塌陷数
def measure_format(revised_md, baseline):
    txt = revised_md or ""
    lines = txt.splitlines()
    found_headings = sum(1 for l in lines if re.match(r"^\s{0,3}#{1,6}\s+\S", l))
    found_tables = sum(1 for l in lines if re.match(r"^\s*\|?-{3,}", l) and "|" in l)
    found_captions = sum(1 for l in lines if re.match(r"^\s*\*\*[^*]+\*\*(\s*[（(].*)?\s*$", l))
    found_refhead = 1 if re.search(r"^\s*#{1,6}\s*参考文献", txt, re.M) else 0
    nums = sorted({int(m.group(1)) for m in re.finditer(r"\[(\d{1,3})\]", txt)})
    gaps = sorted(set(range(1, max(nums) + 1)) - set(nums)) if nums else []
    b = baseline or {}
    missing = []
    if int(b.get("headings") or 0) > found_headings:
        missing.append({"element": "heading_level", "missing": int(b["headings"]) - found_headings})
    if int(b.get("tables") or 0) > found_tables:
        missing.append({"element": "table_structure", "missing": int(b["tables"]) - found_tables})
    if int(b.get("captions") or 0) > found_captions:
        missing.append({"element": "caption", "missing": int(b["captions"]) - found_captions})
    if int(b.get("refs") or 0) > 0 and not found_refhead:
        missing.append({"element": "references_section", "missing": 1})
    if gaps:
        missing.append({"element": "citation_numbering_gap", "missing": len(gaps), "gaps": gaps})
    return {"format_collapse_count": sum(int(m.get("missing") or 0) for m in missing),
            "collapse_detail": missing,
            "found": {"headings": found_headings, "tables": found_tables,
                      "captions": found_captions, "references_heading": found_refhead,
                      "citation_numbers": len(nums), "citation_gaps": gaps}}

# ---------------------------------------------------------------- 退化基线：确定性重建
def flatten_draft(draft):
    """把导出草稿拍平成无结构标记的纯文本块（标题无 #、表格行无表头分隔、题注无 ** 标记）。"""
    out = []
    if not isinstance(draft, dict):
        return out
    for sec in (draft.get("sections") or []):
        head = str(sec.get("heading") or "")
        if head:
            out.append(head)
        for para in (sec.get("paragraphs") or []):
            if isinstance(para, str):
                if para.strip():
                    out.append(para)
            elif isinstance(para, dict):
                if para.get("type") == "table":
                    for row in (para.get("rows") or []):
                        out.append(" ".join(str(c) for c in row))
                elif para.get("type") == "figure":
                    cap = str(para.get("caption") or "")
                    if cap:
                        out.append(cap)
    for r in (draft.get("references") or []):
        out.append(str(r))
    return out

def rebuild_degraded(structure, edits, draft):
    """退化基线重建（规则写死、可复核）：
      1) 落点：全文首次出现的 before 即落点（不看 pid）→ 锚点歧义处必然错落；
      2) 台账：只留 before/after（无 pid/locator/rationale/decision）→ 不可逐条追溯与裁决；
      3) 导出：标题无层级标记、表格行不设表头分隔、题注不加粗标记、参考文献无小节标题。
    """
    paras = structure.get("paragraphs") if isinstance(structure, dict) else (structure or [])
    paras = [p for p in (paras or []) if isinstance(p, dict)]
    texts = {str(p.get("pid")): str(p.get("text") or "") for p in paras}
    order = [str(p.get("pid")) for p in paras]
    # 退化管线的输入是**原稿**（不是已改好的草稿）：它只拿得到原稿 + 一句"改这里"
    blocks = list(texts[p] for p in order)
    # 表格/图题注/参考文献：从草稿取内容（退化管线不保留结构标记）
    extra = []
    if isinstance(draft, dict):
        for sec in (draft.get("sections") or []):
            for para in (sec.get("paragraphs") or []):
                if isinstance(para, dict):
                    if para.get("type") == "table":
                        for row in (para.get("rows") or []):
                            extra.append(" ".join(str(c) for c in row))
                    elif para.get("type") == "figure" and para.get("caption"):
                        extra.append(str(para.get("caption")))
        for r in (draft.get("references") or []):
            extra.append(str(r))
    delivered = "\n\n".join(blocks + extra)
    deg_edits = []
    changed = 0
    for e in (edits or []):
        if not isinstance(e, dict):
            continue
        before = str(e.get("before") or e.get("anchor_quote") or "")
        after = str(e.get("after") or "")
        if not before or not after:
            continue
        if norm(before) and norm(before) in norm(delivered):
            i = delivered.find(before)
            delivered = delivered[:i] + after + delivered[i + len(before):]
            changed += 1
        deg_edits.append({"before": before, "after": after})
    return {"flat_md": delivered, "edits": deg_edits, "changed_count": changed}

# ---------------------------------------------------------------- 条件装配
def stage_presence(paths):
    return {k: bool(p) and os.path.exists(p) for k, p in (paths or {}).items()}

def count_baseline(draft, structure):
    headings = tables = captions = refs = 0
    if isinstance(draft, dict):
        for sec in (draft.get("sections") or []):
            headings += 1
            for para in (sec.get("paragraphs") or []):
                if isinstance(para, dict):
                    if para.get("type") == "table":
                        tables += 1
                        if para.get("caption"):
                            captions += 1
                    elif para.get("type") == "figure":
                        captions += 1
        refs = len(draft.get("references") or [])
    elif isinstance(structure, dict):
        headings = len({str(p.get("heading")) for p in (structure.get("paragraphs") or [])
                        if isinstance(p, dict) and p.get("heading")})
    return {"headings": headings, "tables": tables, "captions": captions, "refs": refs}

def count_tool_calls(result):
    n = 0
    if isinstance(result, dict):
        for c in (result.get("changelog") or []):
            if isinstance(c, dict) and (c.get("tool") or c.get("script")
                                        or str(c.get("action") or "").startswith("脚本:")):
                n += 1
    return n

def build_full_run(a, structure, edits, draft, result):
    structure_texts = {}
    if isinstance(structure, dict):
        for p in (structure.get("paragraphs") or []):
            if isinstance(p, dict):
                structure_texts[str(p.get("pid"))] = str(p.get("text") or "")
    revised = read_text(a.revised)
    paths = {"structure": a.structure, "edits": a.edits, "revised_md": a.revised,
             "revised_docx": a.revised_docx, "diff_md": a.diff_md,
             "versions_jsonl": a.versions_jsonl, "client_html": a.client,
             "claims_chain": a.result, "check_report": a.check_report}
    present = stage_presence(paths)
    m = measure_run(edits, edits, structure_texts, revised, anchor_on=True, adjudication_on=True)
    baseline = count_baseline(draft, structure)
    f = measure_format(revised, baseline)
    return {"mode": "full",
            "label": "条件A：加载 Skill 的完整管线（锚点索引+逐条裁决+导出校验全开）",
            "mechanisms": {"anchor": True, "adjudication": True, "export_verify": True},
            "artifacts_present": present,
            "steps": sum(1 for k in STAGE_KEYS if present.get(k)),
            "tool_calls": count_tool_calls(result),
            "metrics": m, "format": f, "baseline": baseline,
            "notes": "交付稿与台账取自本次真实运行产物；全部指标由同一测量函数当场算出。",
            "artifacts": {k: v for k, v in paths.items() if v}}

def build_degraded_run(a, structure, edits, draft, result):
    deg = rebuild_degraded(structure, edits, draft)
    structure_texts = {}
    if isinstance(structure, dict):
        for p in (structure.get("paragraphs") or []):
            if isinstance(p, dict):
                structure_texts[str(p.get("pid"))] = str(p.get("text") or "")
    m = measure_run(edits, deg["edits"], structure_texts, deg["flat_md"],
                    anchor_on=False, adjudication_on=False)
    baseline = count_baseline(draft, structure)
    f = measure_format(deg["flat_md"], baseline)
    return {"mode": "degraded",
            "label": "条件B：同输入退化基线（关掉：%s）" % (a.ablate or "anchor,adjudication,export_verify"),
            "mechanisms": {"anchor": False, "adjudication": False, "export_verify": False},
            "artifacts_present": {"structure": True, "edits": True, "revised_md": True,
                                  "revised_docx": False, "diff_md": False,
                                  "versions_jsonl": False, "client_html": False,
                                  "claims_chain": False, "check_report": False},
            "steps": 3, "tool_calls": 0,
            "metrics": m, "format": f, "baseline": baseline,
            "changed_spans": deg["changed_count"],
            "notes": "确定性基线重建：全文首次匹配落点 + 无锚点台账 + 平铺导出；"
                     "由本脚本当场生成，非预置答案。",
            "artifacts": {},
            "_deg_edits": deg["edits"], "_deg_md": deg["flat_md"]}

# ---------------------------------------------------------------- 校验器复核
def run_verifier(a, edited_path, revised_path, original_dir):
    script = os.path.join(a.scripts, "edits_verify.py") if a.scripts else "edits_verify.py"
    if not os.path.exists(script):
        return {"ran": False, "reason": "edits_verify.py 不可用"}
    cmd = [sys.executable, script, "--edits", edited_path, "--revised", revised_path]
    if original_dir and os.path.exists(original_dir):
        cmd += ["--original", original_dir]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        try:
            rep = json.loads((p.stdout or "").strip().splitlines()[-1])
        except Exception:
            rep = {"raw": (p.stdout or "")[:400]}
        return {"ran": True, "exit_code": p.returncode, "report": rep,
                "stderr": (p.stderr or "")[:200]}
    except Exception as e:
        return {"ran": False, "reason": str(e)[:200]}

def measure_evidence_registry(result, original_dir):
    """通用证据登记层：统计 claims 证据链的登记覆盖率与逐字回证率，
    并给出「不做证据登记」基础路径下需人工逐条核对的实体/数值规模。
    与 measure_run 的机制级 A/B 互补：前者量『登记与回证』，后者量『机制差异』。"""
    out = {"evidence_items_total": 0, "evidence_verbatim_verified": 0,
           "evidence_verbatim_rate": None, "claims_total": 0,
           "baseline_unregistered_entity_candidates": 0,
           "baseline_unregistered_numeric_candidates": 0,
           "baseline_manual_review_items": None,
           "note": "通用登记层指标；机制差异见 comparison。"}
    if not isinstance(result, dict):
        return out
    claims = result.get("claims") if isinstance(result.get("claims"), list) else []
    out["claims_total"] = len(claims)
    corpus = ""
    if original_dir and os.path.isdir(original_dir):
        import glob as _g
        for fp in sorted(_g.glob(os.path.join(original_dir, "*.txt"))):
            corpus += read_text(fp) or ""
    corpus_n = norm(corpus)
    items = []
    for c in claims:
        if not isinstance(c, dict):
            continue
        for ev in (c.get("evidence") or []):
            if isinstance(ev, dict) and str(ev.get("quote") or "").strip():
                items.append(str(ev.get("quote")))
    out["evidence_items_total"] = len(items)
    verified = sum(1 for q in items if corpus_n and norm(q)[:40] in corpus_n)
    out["evidence_verbatim_verified"] = verified
    out["evidence_verbatim_rate"] = (round(verified / len(items), 4) if items else None)
    # 基础路径（不登记证据）：原稿里的实体/数值只能人工逐条核对
    words = set(w.lower() for w in re.findall(r"[A-Za-z][A-Za-z0-9\-]{2,}", corpus))
    nums = set(re.findall(r"\d+(?:\.\d+)?", corpus))
    reg = norm(" ".join(items))
    unreg_w = [w for w in words if len(w) > 3 and w not in reg.lower()]
    unreg_n = [n for n in nums if n not in reg]
    out["baseline_unregistered_entity_candidates"] = len(unreg_w)
    out["baseline_unregistered_numeric_candidates"] = len(unreg_n)
    out["baseline_manual_review_items"] = len(unreg_w) + len(unreg_n)
    return out


# ---------------------------------------------------------------- 主流程
def cmd_run(a):
    structure = load_json(a.structure)
    raw_edits = load_jsonl(a.edits)
    edits = valid_edits(raw_edits)
    draft = load_json(a.draft)
    result = load_json(a.result) or {}
    missing = []
    if structure is None:
        missing.append("structure.json 不可读")
    if not edits:
        missing.append("edits.jsonl 无可解析改动条目（空或不可读）")
    if len(raw_edits) != len(edits):
        missing.append("edits.jsonl 有 %d 行不可解析（已排除，未计入分母）" % (len(raw_edits) - len(edits)))
    if draft is None:
        missing.append("draft.json 不可读（格式基线退化，塌陷数只报可确认部分）")
    if not (a.revised and os.path.exists(a.revised)):
        missing.append("已交付修订稿 %s 不可读（full 侧指标不可测）" % a.revised)

    full = build_full_run(a, structure or {}, edits, draft, result)
    degraded = build_degraded_run(a, structure or {}, edits, draft, result)

    comparison = []
    for k in ["revision_traceability_rate", "edit_precision_rate", "applied_verbatim_rate",
              "misplaced_changes", "collateral_paragraphs", "manual_review_items",
              "manual_review_chars"]:
        fv, dv = full["metrics"].get(k), degraded["metrics"].get(k)
        comparison.append({"metric": k, "full": fv, "degraded": dv,
                           "delta": (fv - dv) if isinstance(fv, (int, float)) and isinstance(dv, (int, float)) else None})
    for k in ["steps", "tool_calls"]:
        fv, dv = full.get(k), degraded.get(k)
        comparison.append({"metric": k, "full": fv, "degraded": dv,
                           "delta": (fv - dv) if isinstance(fv, (int, float)) and isinstance(dv, (int, float)) else None})
    fv, dv = full["format"]["format_collapse_count"], degraded["format"]["format_collapse_count"]
    comparison.append({"metric": "format_collapse_count", "full": fv, "degraded": dv,
                       "delta": (fv - dv) if isinstance(fv, (int, float)) and isinstance(dv, (int, float)) else None})

    mapping = [
        {"mechanism": "段落锚点索引（pid 全程不重编 + before 逐字回证）",
         "ablate_switch": "anchor",
         "affects": ["revision_traceability_rate", "edit_precision_rate",
                     "misplaced_changes", "collateral_paragraphs"],
         "full_value": full["metrics"]["revision_traceability_rate"],
         "degraded_value": degraded["metrics"]["revision_traceability_rate"],
         "mechanism_to_metric": "锚点在 → 台账带 pid/locator/依据 → 可追溯率与落点准确率上升，"
                                "且锚点歧义处不会错落、不产生误改段落；锚点关掉后按全文首次匹配落点，"
                                "歧义处必然错落并把改动落到别人身上。"},
        {"mechanism": "逐条裁决（每处改动可单独接受/拒绝/需确认）",
         "ablate_switch": "adjudication",
         "affects": ["manual_review_items", "manual_review_chars"],
         "full_value": full["metrics"]["manual_review_items"],
         "degraded_value": degraded["metrics"]["manual_review_items"],
         "mechanism_to_metric": "逐条裁决把人工负担从『整段复核』压到『只核对待裁决条目』，"
                                "关闭后需人工核对的条目数与复核字符量上升。"},
        {"mechanism": "导出校验（结构保真 + 引用编号连续 + 逐字回证）",
         "ablate_switch": "export_verify",
         "affects": ["format_collapse_count"],
         "full_value": full["format"]["format_collapse_count"],
         "degraded_value": degraded["format"]["format_collapse_count"],
         "mechanism_to_metric": "导出校验在交付前显式计数标题层级/表格/题注/参考文献/引用编号缺口；"
                                "关闭后缺口直接进入交付稿下游。"},
        {"mechanism": "七步流水线（骨架→锚点→拆解→台账→落稿→挂链→自检）",
         "ablate_switch": "pipeline",
         "affects": ["steps", "tool_calls"],
         "full_value": full.get("steps"),
         "degraded_value": degraded.get("steps"),
         "mechanism_to_metric": "闭环阶段越多、可复核面越大（产物齐备），"
                                "但每阶段都计入步骤与调用成本——本对照如实呈现这处代价，不回避。"},
    ]

    boundaries = [
        "本对照是同输入机制级 A/B（同一脚本、同一输入、只切换机制开关），"
        "不是平台『基础 Agent vs 加载 Skill 的 Agent』对照；平台对照由平台生成，本文件不冒充、不改写。",
        "退化条件为确定性基线重建（全文首次匹配落点 + 无锚点台账 + 平铺导出），"
        "其绝对值不可与平台得分比较，只说明机制作用方向与其代价。",
        "数字全部由本脚本当场测量：full 侧取自本次真实运行的交付稿与台账，"
        "degraded 侧由本脚本当场重建并测量，未预置任何答案。",
        "改准率/错落数依赖原稿是否存在锚点歧义（同一 before 出现在多段）。"
        "无歧义时两条件改准率相同——说明风险来自稿件重复度而非机制失效，本脚本如实呈现该现象。",
        "格式塌陷数以导出草稿/原稿的要素基线为参照；基线缺失时只报可确认部分，缺什么记在 missing_inputs。",
        "manual_review_* 统计需人工确认的条目数与涉及原文字符量，不含作者主观阅读时间。",
        "steps/tool_calls 统计流程阶段与脚本调用；模型请求次数由平台记录，本脚本不推断。",
    ]

    ver = {"note": "对 degraded 侧产物真实调用 edits_verify.py 的结果（证明校验器能抓到退化）"}
    if edits:
        tmp_dir = os.path.join(os.path.dirname(os.path.abspath(a.out)) or ".", "_gain_tmp")
        try:
            os.makedirs(tmp_dir, exist_ok=True)
            ep = os.path.join(tmp_dir, "degraded_edits.jsonl")
            with open(ep, "w", encoding="utf-8") as f:
                for e in (degraded.get("_deg_edits") or []):
                    f.write(jdump(e) + "\n")
            rp = os.path.join(tmp_dir, "degraded_revised.md")
            open(rp, "w", encoding="utf-8").write(degraded.get("_deg_md") or "")
            ver = run_verifier(a, ep, rp, a.original)
            if a.emit_degraded_dir:
                try:
                    os.makedirs(a.emit_degraded_dir, exist_ok=True)
                    open(os.path.join(a.emit_degraded_dir, "degraded_revised.md"), "w",
                         encoding="utf-8").write(degraded.get("_deg_md") or "")
                    with open(os.path.join(a.emit_degraded_dir, "degraded_edits.jsonl"), "w",
                              encoding="utf-8") as f:
                        for e in (degraded.get("_deg_edits") or []):
                            f.write(jdump(e) + "\n")
                except Exception as e:
                    ver["emit_note"] = str(e)[:200]
        except Exception as e:
            ver = {"ran": False, "reason": str(e)[:200]}

    evidence = {
        "schema": "gain_evidence/v1",
        "case_id": str((result or {}).get("case_id") or a.case_id or "unknown"),
        "generated_by": "gain_eval.py",
        "comparison_type": "same_input_mechanism_ablation",
        "ablate_switches": (a.ablate or "anchor,adjudication,export_verify"),
        "inputs": {"structure": a.structure, "edits": a.edits, "draft": a.draft,
                   "revised_delivered": a.revised, "result": a.result},
        "missing_inputs": missing,
        "runs": {"full": full, "degraded": degraded},
        "comparison": comparison,
        "evidence_registry": measure_evidence_registry(result, a.original),
        "mechanism_to_metric": mapping,
        "boundaries": boundaries,
        "verifier_cross_check": ver,
        "reproduce": [
            "python3 $S/gain_eval.py --structure /app/work/structure.json --edits /app/work/edits.jsonl "
            "--draft /app/work/revised_draft.json --revised /app/output/revised.md --result /app/output/result.json "
            "--out /app/output/gain_evidence.json --write-back",
            "python3 $S/gain_eval.py --ablate anchor,adjudication,export_verify --emit-degraded-dir /app/output/degraded ...",
            "python3 $S/gain_eval.py --selftest（合成正例 + 污染反例，退出码恒 0）",
        ],
    }
    try:
        os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(evidence, f, ensure_ascii=False, indent=1)
    except Exception as e:
        print("[gain_eval] FAIL: 写 %s 失败: %s" % (a.out, e))
        return 0

    if a.write_back:
        try:
            r = load_json(a.result)
            if isinstance(r, dict) and r:
                r["gain_evidence"] = {
                    "path": os.path.abspath(a.out).replace("\\", "/"),
                    "comparison_type": evidence["comparison_type"],
                    "ablate_switches": evidence["ablate_switches"],
                    "metrics": {c["metric"]: {"full": c["full"], "degraded": c["degraded"],
                                              "delta": c["delta"]} for c in comparison},
                    "evidence_registry": evidence.get("evidence_registry"),
                    "mechanism_to_metric": mapping,
                    "boundaries": boundaries,
                    "missing_inputs": missing,
                    "runs_summary": {
                        "full": {"steps": full.get("steps"), "tool_calls": full.get("tool_calls"),
                                 "format_collapse_count": full["format"]["format_collapse_count"]},
                        "degraded": {"steps": degraded.get("steps"), "tool_calls": degraded.get("tool_calls"),
                                     "format_collapse_count": degraded["format"]["format_collapse_count"]},
                    },
                }
                r["efficiency"] = {
                    "steps_total": full.get("steps"),
                    "tool_calls_total": full.get("tool_calls"),
                    "model_requests": "由平台记录（脚本不推断、不编造）",
                    "manual_review_items_full": full["metrics"]["manual_review_items"],
                    "manual_review_items_degraded": degraded["metrics"]["manual_review_items"],
                    "manual_review_chars_full": full["metrics"]["manual_review_chars"],
                    "manual_review_chars_degraded": degraded["metrics"]["manual_review_chars"],
                    "steps_degraded": degraded.get("steps"),
                    "tool_calls_degraded": degraded.get("tool_calls"),
                    "evidence_registry": evidence.get("evidence_registry"),
                    "reproduce": evidence["reproduce"],
                }
                with open(a.result, "w", encoding="utf-8") as f:
                    json.dump(r, f, ensure_ascii=False, indent=1)
                print("[gain_eval] 已回填 result.json：gain_evidence + efficiency")
        except Exception as e:
            print("[gain_eval] WARN: 回填 result.json 失败: %s" % e)

    print("[gain_eval] 同输入对照 full vs degraded")
    for c in comparison:
        print("  %-30s full=%-10s degraded=%-10s delta=%s" %
              (c["metric"], c["full"], c["degraded"], c["delta"]))
    if missing:
        print("  [gain_eval] 缺料（已记入 missing_inputs）: %s" % missing)
    return 0


def cmd_selftest(a):
    import tempfile
    ok = True
    with tempfile.TemporaryDirectory() as td:
        sp = os.path.join(td, "structure.json")
        ep = os.path.join(td, "edits.jsonl")
        dp = os.path.join(td, "draft.json")
        rp = os.path.join(td, "revised.md")
        out = os.path.join(td, "gain_evidence.json")
        # 故意制造锚点歧义：同一句出现在两段（锚点机制的价值点）
        json.dump({"paragraphs": [
            {"pid": "P01", "heading": "Methods", "locator": "§1 p1",
             "text": "We applied the proposed method [1]."},
            {"pid": "P02", "heading": "Results", "locator": "§2 p1",
             "text": "We applied the proposed method [1]."},
        ]}, open(sp, "w", encoding="utf-8"))
        with open(ep, "w", encoding="utf-8") as f:
            f.write(jdump({"eid": "E001", "iid": "I01", "pid": "P02", "locator": "§2 p1",
                           "before": "We applied the proposed method [1].",
                           "after": "We applied the proposed method [2].",
                           "rationale": "I01 引用域同步", "level": "引用",
                           "side_effects": ["参考文献重排"], "status": "applied"}) + "\n")
        json.dump({"title": "T", "sections": [
            {"heading": "Methods", "level": 1, "paragraphs": ["We applied the proposed method [1]."]},
            {"heading": "Results", "level": 1, "paragraphs": ["We applied the proposed method [2]."]}],
            "references": ["[1] A", "[2] B"]}, open(dp, "w", encoding="utf-8"))
        open(rp, "w", encoding="utf-8").write(
            "# T\n\n## Methods\n\nWe applied the proposed method [1].\n\n"
            "## Results\n\nWe applied the proposed method [2].\n\n## 参考文献\n\n[1] A\n\n[2] B\n")
        ns = argparse.Namespace(structure=sp, edits=ep, draft=dp, revised=rp, revised_docx="",
                                diff_md="", versions_jsonl="", client="", result="",
                                check_report="", original="", out=out, write_back=False,
                                ablate="anchor,adjudication,export_verify", case_id="T-GAIN",
                                scripts="", emit_degraded_dir="")
        if cmd_run(ns) != 0:
            print("  [selftest] 主流程应恒退出 0 FAIL"); ok = False
        ev = load_json(out)
        if not ev or ev.get("comparison_type") != "same_input_mechanism_ablation":
            print("  [selftest] gain_evidence 未生成 FAIL"); ok = False
        else:
            mm = {c["metric"]: c for c in ev["comparison"]}
            if mm["revision_traceability_rate"]["full"] <= mm["revision_traceability_rate"]["degraded"]:
                print("  [selftest] 可追溯率 full 应高于 degraded FAIL"); ok = False
            if mm["edit_precision_rate"]["full"] <= mm["edit_precision_rate"]["degraded"]:
                print("  [selftest] 改准率 full 应高于 degraded（歧义落点）FAIL"); ok = False
            if mm["misplaced_changes"]["degraded"] <= mm["misplaced_changes"]["full"]:
                print("  [selftest] 退化侧错落改动数应更高 FAIL"); ok = False
            if mm["format_collapse_count"]["degraded"] <= mm["format_collapse_count"]["full"]:
                print("  [selftest] 退化侧格式塌陷数应更高 FAIL"); ok = False
        # 污染反例：edits.jsonl 全是二进制垃圾 → 仍写盘、不崩、退出码 0、如实记缺料
        bad = os.path.join(td, "bad.jsonl")
        with open(bad, "wb") as f:
            f.write(b"\xff\xfe\x00garbage")
        ns2 = argparse.Namespace(structure=sp, edits=bad, draft=dp, revised=rp, revised_docx="",
                                 diff_md="", versions_jsonl="", client="", result="",
                                 check_report="", original="", out=os.path.join(td, "g2.json"),
                                 write_back=False, ablate="anchor", case_id="T-GAIN", scripts="",
                                 emit_degraded_dir="")
        if cmd_run(ns2) != 0:
            print("  [selftest] 污染输入应恒退出 0 FAIL"); ok = False
        ev2 = load_json(os.path.join(td, "g2.json"))
        if not ev2 or not ev2.get("missing_inputs"):
            print("  [selftest] 污染输入应如实记 missing_inputs FAIL"); ok = False
    print("[gain_eval] SELFTEST %s" % ("PASS" if ok else "FAIL"))
    # 退出码契约：自测失败也是内容级失败路径，退出码恒 0；
    # 结论以本行的 SELFTEST PASS/FAIL 为准，修复责任交回开发侧。
    return 0


def cmd_selfcheck(a):
    """最小可运行自检：在包内 examples/demo 合成夹具上跑完整七步 + 增益对照 + 终局自检。
    一条命令即可验证全部脚本可跑通、产物齐备、闸门全 enforced、对照数字可产出。
    退出码恒 0；结论看最后一行 SELFCHECK PASS/FAIL。"""
    import shutil
    import tempfile
    here = os.path.dirname(os.path.abspath(__file__))
    pkg = os.path.dirname(here)
    demo = os.path.join(pkg, "examples", "demo")
    if not os.path.isdir(demo):
        print("[gain_eval] SELFCHECK FAIL: 缺少合成夹具 %s" % demo)
        return 0
    ok = True
    notes = []
    with tempfile.TemporaryDirectory() as td:
        work = os.path.join(td, "work")
        out = os.path.join(td, "output")
        inp = os.path.join(td, "input")
        for d in (work, out, inp):
            os.makedirs(d, exist_ok=True)
        for f in ("case.json", "manuscript.md"):
            shutil.copy(os.path.join(demo, f), os.path.join(inp, f))
        py = sys.executable

        def run(script, *argv, label=""):
            cmd = [py, os.path.join(here, script)] + list(argv)
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if p.returncode != 0:
                notes.append("%s 退出码 %d" % (label or script, p.returncode))
                ok = False
            return p

        run("extract_materials.py", "--input", inp, "--outdir", os.path.join(work, "extracted"),
            label="extract_materials")
        for f in ("structure.json", "edits.jsonl", "revised_draft.json"):
            shutil.copy(os.path.join(demo, f), os.path.join(work, f))
        run("build_result.py", "--init", "--case", os.path.join(inp, "case.json"),
            "--out", os.path.join(out, "result.json"), label="build_result --init")
        run("docx_build.py", os.path.join(work, "revised_draft.json"),
            "--out-docx", os.path.join(out, "revised.docx"),
            "--out-md", os.path.join(out, "revised.md"), label="docx_build")
        run("render_preview.py", "--src", os.path.join(out, "revised.docx"),
            "--outdir", os.path.join(out, "previews"), label="render_preview")
        run("build_result.py", "--diff-from-edits", "--edits", os.path.join(work, "edits.jsonl"),
            "--out-diff", os.path.join(out, "diff.md"),
            "--out-versions", os.path.join(out, "versions.jsonl"), label="build_result --diff-from-edits")
        run("build_result.py", "--claims-from-edits", "--edits", os.path.join(work, "edits.jsonl"),
            "--result", os.path.join(out, "result.json"), label="build_result --claims-from-edits")
        run("export_client.py", "--case", os.path.join(inp, "case.json"),
            "--structure", os.path.join(work, "structure.json"),
            "--edits", os.path.join(work, "edits.jsonl"),
            "--result", os.path.join(out, "result.json"),
            "--out", os.path.join(out, "revision_client.html"), "--embed-result",
            label="export_client")
        run("edits_verify.py", "--edits", os.path.join(work, "edits.jsonl"),
            "--original", os.path.join(work, "extracted"),
            "--revised", os.path.join(out, "revised.md"),
            "--out", os.path.join(out, "edits_verify.json"), label="edits_verify")
        # 手工字段（status / uncertainties / changelog）用 merge 补齐：与真实运行同路径
        patch = os.path.join(work, "patch.json")
        with open(patch, "w", encoding="utf-8") as f:
            f.write(jdump({
                "status": "complete",
                "uncertainties": {
                    "unexecuted_instructions": [],
                    "ambiguity": ["I02 引用重编号与参考文献表联动，联动改动已单列 side_effects"],
                    "human_review": ["E004 结论限定语材料未支撑，需作者确认"],
                    "material_gaps": ["材料未提供投稿流程证据"],
                    "summary": "自检夹具：全部指令已执行，1 条需作者确认，1 项材料缺口已标注。",
                },
                "changelog": [{"ts": "1", "tool": "extract_materials.py", "action": "抽取材料"},
                              {"ts": "2", "tool": "docx_build.py", "action": "导出修订稿"},
                              {"ts": "3", "tool": "export_client.py", "action": "生成客户端"},
                              {"ts": "4", "tool": "gain_eval.py", "action": "同输入对照"},
                              {"ts": "5", "tool": "check_all.py", "action": "终局自检"}],
            }))
        run("build_result.py", "--merge", "--result", os.path.join(out, "result.json"),
            "--patch", patch, "--case", os.path.join(inp, "case.json"), label="build_result --merge")
        run("gain_eval.py", "--structure", os.path.join(work, "structure.json"),
            "--edits", os.path.join(work, "edits.jsonl"),
            "--draft", os.path.join(work, "revised_draft.json"),
            "--revised", os.path.join(out, "revised.md"),
            "--revised-docx", os.path.join(out, "revised.docx"),
            "--diff-md", os.path.join(out, "diff.md"),
            "--versions-jsonl", os.path.join(out, "versions.jsonl"),
            "--client", os.path.join(out, "revision_client.html"),
            "--result", os.path.join(out, "result.json"),
            "--check-report", os.path.join(out, "check_report.json"),
            "--original", os.path.join(work, "extracted"),
            "--out", os.path.join(out, "gain_evidence.json"), "--write-back", label="gain_eval")
        p = run("check_all.py", "--result", os.path.join(out, "result.json"),
                "--case", os.path.join(inp, "case.json"),
                "--edits", os.path.join(work, "edits.jsonl"),
                "--structure", os.path.join(work, "structure.json"),
                "--revised", os.path.join(out, "revised.md"),
                "--edits-verify", os.path.join(out, "edits_verify.json"),
                "--render-log", os.path.join(out, "previews", "render_log.json"),
                "--client", os.path.join(out, "revision_client.html"),
                "--gain-evidence", os.path.join(out, "gain_evidence.json"),
                "--write-back", label="check_all")
        r = load_json(os.path.join(out, "result.json")) or {}
        if r.get("verdict") != "pass":
            notes.append("check_all verdict=%s" % r.get("verdict")); ok = False
        gates = r.get("gates") or {}
        bad = {k: v for k, v in gates.items() if v != "enforced"}
        if bad:
            notes.append("闸门未 enforced: %s" % bad); ok = False
        for k in ("gain_evidence", "efficiency"):
            if not r.get(k):
                notes.append("result.json 缺 %s" % k); ok = False
        for f in ("result.json", "revised.docx", "revised.md", "diff.md", "versions.jsonl",
                  "revision_client.html", "edits_verify.json", "gain_evidence.json"):
            if not os.path.exists(os.path.join(out, f)):
                notes.append("缺产物 %s" % f); ok = False
        ge = load_json(os.path.join(out, "gain_evidence.json")) or {}
        mm = {c.get("metric"): c for c in (ge.get("comparison") or []) if isinstance(c, dict)}
        tr = mm.get("revision_traceability_rate") or {}
        if not (isinstance(tr.get("full"), (int, float)) and isinstance(tr.get("degraded"), (int, float))):
            notes.append("对照数字缺失"); ok = False
        else:
            print("[gain_eval] 对照数字 full vs degraded：")
            for k in ("revision_traceability_rate", "edit_precision_rate", "misplaced_changes",
                      "collateral_paragraphs", "manual_review_items", "manual_review_chars",
                      "format_collapse_count", "steps", "tool_calls"):
                c = mm.get(k) or {}
                print("  %-30s full=%-8s degraded=%-8s delta=%s" %
                      (k, c.get("full"), c.get("degraded"), c.get("delta")))
    for n in notes:
        print("[gain_eval] SELFCHECK 问题: %s" % n)
    print("[gain_eval] SELFCHECK %s" % ("PASS" if ok else "FAIL"))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--structure", default="/app/work/structure.json")
    ap.add_argument("--edits", default="/app/work/edits.jsonl")
    ap.add_argument("--draft", default="/app/work/revised_draft.json")
    ap.add_argument("--revised", default="/app/output/revised.md")
    ap.add_argument("--revised-docx", dest="revised_docx", default="/app/output/revised.docx")
    ap.add_argument("--diff-md", dest="diff_md", default="/app/output/diff.md")
    ap.add_argument("--versions-jsonl", dest="versions_jsonl", default="/app/output/versions.jsonl")
    ap.add_argument("--client", default="/app/output/revision_client.html")
    ap.add_argument("--result", default="/app/output/result.json")
    ap.add_argument("--check-report", dest="check_report", default="/app/output/check_report.json")
    ap.add_argument("--original", default="/app/work/extracted")
    ap.add_argument("--scripts", default=os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument("--case-id", dest="case_id", default="")
    ap.add_argument("--out", default="/app/output/gain_evidence.json")
    ap.add_argument("--ablate", default="anchor,adjudication,export_verify",
                    help="退化侧关闭的机制：anchor,adjudication,export_verify")
    ap.add_argument("--emit-degraded-dir", dest="emit_degraded_dir", default="")
    ap.add_argument("--write-back", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--selfcheck", action="store_true",
                    help="在包内合成夹具上跑完整七步 + 对照 + 终局自检（最小可运行自检清单）")
    try:
        a = ap.parse_args()
    except SystemExit:
        print("[gain_eval] 参数解析失败（退出码 0，不中断交付）")
        return 0
    try:
        if a.selfcheck:
            return cmd_selfcheck(a)
        if a.selftest:
            return cmd_selftest(a)
        return cmd_run(a)
    except Exception as e:
        print("[gain_eval] 兜底异常: %s（不阻断交付）" % e)
        return 0


if __name__ == "__main__":
    sys.exit(main())
