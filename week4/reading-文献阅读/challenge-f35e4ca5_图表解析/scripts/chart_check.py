#!/usr/bin/env python3
"""chart_check.py — 图表解析结果校验器（题面对齐 + 可退化对照 + 零中断）。

校验项（每条输出 {item, template_value, applied, match} 三元组并嵌入 result.json.verification）：
1. 工单全覆盖：images/tables 每个对象都有 object 记录；
2. status 枚举（parsed/not_applicable/unreadable/unprocessed）；
3. plot 类对象需有 axes；readings 需带 units 与 approx 标记；
4. table 类对象需有 columns/rows；
5. photo/schematic 对象不得写 readings（照片读数=编造）；
6. 数值回证：每条数据系列首/中/尾读数的数字须在证据 blob（claims 逐字引文+材料表格）
   中找到；unbacked 逐条列出（approx 读数降级为 warn+gate_note，非 approx 缺回证=FAIL）；
7. 图例-分类数：elements.series 数量 == readings 实际出现的不重复系列数；
8. 颜色映射：elements.colors 提供时每条系列必须有颜色条目（未提供 → gate=skipped_not_provided）；
9. 轴范围：axes 声明 end 时，读数坐标必须在 [min(start,end), max(start,end)] 内
   （未声明 end → gate=skipped_not_provided）；
10. 图例逐字+双向映射：elements.legend 必填，图例项与 series 双向一一对应；
11. 单位量级：读数 units 必须与对应轴 units 一致（不把 mV 当 V、不擅自换量级）；
12. 读数来源定位：每条读数必须带 how 与 source_locator（可回指原图位置）；
13. 源数据表全量：表格转录行数 == 材料中该表行数（少行=未全量转录）；
14. inventory 与实际对象计数一致。

闸门状态显式枚举：enforced / skipped_not_provided / not_found / unreadable。
未运行 ≠ 通过；skipped 必须 gate_note 写明「下游不得宣称已核对」。

退化对照臂（--ablate）：
  none          正常臂（默认），全闸门执行；
  backevidence  关闭数值回证与 unbacked 回填（其余闸门照常）；
  structure     关闭图例/单位/来源定位等结构闸门（数值回证照常）；
  all           全关（仅保留契约与覆盖检查）。
退化臂的 checks 记 applied=false + note=ablation:disabled，并在 verification.ablation
中登记 mode 与 disabled_gates；闸门四态枚举不受影响。

用法：
    python3 chart_check.py --result R.json --workorder WO.json \
        [--input-root /input] [--ablate none|backevidence|structure|all] --out report.json
退出码：恒为 0（禁止中断交付）；成败看 report.verdict 与 problems 明细。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

OBJ_STATUS = {"parsed", "not_applicable", "unreadable", "unprocessed"}
ALLT = {"none", "backevidence", "structure", "all"}


def norm(s) -> str:
    """空白归一化，用于逐字子串匹配。"""
    return re.sub(r"\s+", "", str(s or "")).lower()


def unit_norm(s) -> str:
    """单位归一化：去空白、去括号内容，便于 mV/V 等量级比较。"""
    t = norm(s)
    t = t.replace("（", "(").replace("）", ")")
    return t


def evidence_blob(res: dict, input_root: str | None, skip_paths=None) -> str:
    """汇总「材料侧」的可回证文本。

    skip_paths：本次被校验的 result.json 自身（及其副本）——**必须排除**，
    否则 result.json 里回写的 verification / gain_evidence 噪声会被当成
    「材料证据」，导致自证循环（自己写的数字能回证自己）。
    """
    skip = set()
    for p in (skip_paths or []):
        if not p:
            continue
        try:
            skip.add(os.path.normcase(os.path.abspath(p)))
        except Exception:
            skip.add(os.path.normcase(str(p)))

    parts = []
    for c in res.get("claims") or []:
        parts.append(str(c.get("text") or ""))
        for ev in (c.get("evidence") or []):
            if isinstance(ev, dict):
                parts.append(str(ev.get("quote") or ""))
            else:
                parts.append(str(ev))
    inner = res.get("result") or {}
    for o in inner.get("objects") or []:
        tb = (o.get("table") or {}) if isinstance(o, dict) else {}
        for row in tb.get("rows") or []:
            parts.extend(str(c) for c in row)
    if input_root and os.path.isdir(input_root):
        for root, _d, files in os.walk(input_root):
            for fn in files:
                if not fn.lower().endswith((".json", ".md", ".txt")):
                    continue
                fp = os.path.join(root, fn)
                try:
                    if os.path.normcase(os.path.abspath(fp)) in skip:
                        continue
                except Exception:
                    pass
                try:
                    with open(fp, "r", encoding="utf-8",
                              errors="replace") as f:
                        parts.append(f.read())
                except Exception:
                    pass
    return norm(" ".join(parts))


def material_table_rows(input_root: str | None, skip_paths=None) -> dict:
    """从材料 json 中提取 {table_id: 行数}，用于「源数据表全量」核对。

    兼容两种排布：{"material": {id: {...}}} 与 {id: {...}}；行数组取 rows/data/values。
    skip_paths：被校验的 result.json 自身须排除（其内容不是材料原表）。
    """
    out = {}
    if not input_root or not os.path.isdir(input_root):
        return out
    skip = set()
    for p in (skip_paths or []):
        if not p:
            continue
        try:
            skip.add(os.path.normcase(os.path.abspath(p)))
        except Exception:
            skip.add(os.path.normcase(str(p)))
    for root, _d, files in os.walk(input_root):
        for fn in files:
            if not fn.lower().endswith(".json"):
                continue
            fp = os.path.join(root, fn)
            try:
                if os.path.normcase(os.path.abspath(fp)) in skip:
                    continue
            except Exception:
                pass
            try:
                with open(fp, "r", encoding="utf-8",
                          errors="replace") as f:
                    doc = json.load(f)
            except Exception:
                continue
            if not isinstance(doc, dict):
                continue
            pools = []
            for key in ("material", "materials", "tables", "source_tables"):
                v = doc.get(key)
                if isinstance(v, dict):
                    pools.append(v)
                elif isinstance(v, list):
                    for it in v:
                        if isinstance(it, dict):
                            tid = it.get("id") or it.get("table_id")
                            if tid:
                                out.setdefault(str(tid), 0)
            for tid, tv in doc.items():
                if isinstance(tv, dict) and isinstance(tv.get("rows"), list):
                    pools.append({tid: tv})
            for pool in pools:
                for tid, tv in pool.items():
                    if not isinstance(tv, dict):
                        continue
                    rows = None
                    for key in ("rows", "data", "values", "table"):
                        if isinstance(tv.get(key), list):
                            rows = tv[key]
                            break
                    if rows is None:
                        continue
                    # 材料原表第一行通常是表头 → 记为「含表头的总行数」
                    out.setdefault(str(tid), len(rows))
    return out


def series_of(label: str) -> str:
    return str(label or "").split("@")[0].strip() or str(label)


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
    ap.add_argument("--input-root", default=None, help="材料目录，用于数值回证 blob")
    ap.add_argument("--out", default="/app/output/chart_check.json")
    ap.add_argument("--ablate", default="none", choices=sorted(ALLT),
                    help="退化对照臂：关闭部分闸门以产出对照记录")
    ap.add_argument("--skip-blob", action="append", default=[],
                    help="额外排除在「材料证据 blob」之外的文件（可重复）。"
                         "用于把 result.json 及其副本排除，避免自证循环。")
    args = ap.parse_args()

    mode = args.ablate if args.ablate in ALLT else "none"
    abl_back = mode in ("backevidence", "all")
    abl_struct = mode in ("structure", "all")
    disabled = []
    if abl_back:
        disabled.append("numeric_backevidence")
    if abl_struct:
        disabled += ["legend_series_map", "unit_consistency", "reading_locator"]

    problems, checks, unbacked = [], [], []
    gates = {}

    try:
        with open(args.result, "r", encoding="utf-8") as f:
            res = json.load(f)
    except Exception as e:
        report = {"ok": False, "verdict": "fail",
                  "problems": ["result.json 读取失败: %s" % e], "checks": [],
                  "gates": {}, "unbacked_readings": [], "ablation": {"mode": mode}}
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=1)
        print("[chart_check] FAIL（result.json 不可读：%s）；已记录，退出码 0" % e)
        return 0
    try:
        with open(args.workorder, "r", encoding="utf-8") as f:
            wo = json.load(f)
    except Exception as e:
        wo = {}

    def chk(item, template_value, applied, match, note=None):
        rec = {"item": item, "template_value": template_value,
               "applied": bool(applied), "match": match}
        if note:
            rec["note"] = note
        checks.append(rec)
        # match is None = 降级告警（approximate 读数无回证）→ 只记 unbacked + human_review，
        # **不算 FAIL**（题面口径：非 approx 缺回证才是编造风险）。
        # match is False = 真 FAIL。
        if applied is True and match is False:
            problems.append("%s: 期望 %r，实际不符" % (item, template_value))
        return rec

    if not res.get("case_id"):
        problems.append("缺少 case_id")
    for k in ("status", "result", "claims", "uncertainties", "changelog"):
        if k not in res:
            problems.append("缺少通用契约字段: %s" % k)

    inner = res.get("result") if isinstance(res.get("result"), dict) else {}
    objects = inner.get("objects")
    if not isinstance(objects, list):
        problems.append("result.objects 缺失")
        objects = []

    blob = evidence_blob(res, args.input_root,
                         skip_paths=[args.result] + list(args.skip_blob or []))
    mat_rows = material_table_rows(args.input_root,
                                    skip_paths=[args.result] + list(args.skip_blob or []))
    gates["numeric_backevidence"] = "skipped_not_provided" if abl_back else "enforced"
    gates["legend_category_count"] = "enforced"
    gates["color_mapping"] = "skipped_not_provided"
    gates["axis_range"] = "skipped_not_provided"
    gates["legend_series_map"] = "skipped_not_provided" if abl_struct else "enforced"
    gates["unit_consistency"] = "skipped_not_provided" if abl_struct else "enforced"
    gates["reading_locator"] = "skipped_not_provided" if abl_struct else "enforced"
    gates["table_fidelity"] = "enforced" if mat_rows else "skipped_not_provided"

    by_id = {}
    for i, o in enumerate(objects):
        if not isinstance(o, dict):
            problems.append("objects[%d] 不是对象" % i)
            continue
        oid = str(o.get("object_id"))
        if oid in by_id:
            problems.append("对象重复: %s" % oid)
        by_id[oid] = o

        st, kind = o.get("status"), o.get("kind")
        if st not in OBJ_STATUS:
            problems.append("[%s] status 非法: %r" % (oid, st))
            continue

        if kind == "image":
            cls = o.get("image_class")
            chk("%s.image_class" % oid, "photo|schematic|plot|unknown", True,
                cls in ("photo", "schematic", "plot", "unknown"))
            rd = o.get("readings") or []
            if cls in ("photo", "schematic") and rd:
                problems.append("[%s] 照片/示意图却写了 readings（=编造数据）" % oid)
            if st == "parsed" and cls == "plot" and not o.get("axes"):
                problems.append("[%s] plot 类已解析但缺 axes 清单" % oid)

            # 7) 图例-分类数
            series_decl = [str(s) for s in (o.get("elements") or {}).get("series") or []]
            series_seen = sorted({series_of(r.get("label")) for r in rd if isinstance(r, dict)})
            if cls == "plot" and st == "parsed":
                chk("%s.legend_category_count" % oid, len(series_decl), True,
                    len(series_decl) == len(series_seen) and set(series_decl) == set(series_seen),
                    note="声明系列 %r vs 读数系列 %r" % (series_decl, series_seen))

            # 8) 颜色映射
            colors = (o.get("elements") or {}).get("colors")
            if isinstance(colors, dict) and colors:
                gates["color_mapping"] = "enforced"
                missing = [s for s in series_decl if s not in colors]
                chk("%s.color_mapping" % oid, "每条系列有颜色条目", True, not missing,
                    note="缺颜色: %r" % missing)
            else:
                gates["color_mapping"] = "skipped_not_provided"
                chk("%s.color_mapping" % oid, None, False, None,
                    note="材料未提供颜色信息；下游不得宣称已核对颜色-系列对应")

            # 9) 轴范围
            axes = {a.get("name"): a for a in (o.get("axes") or []) if isinstance(a, dict)}
            range_ok, range_note, range_applied = True, [], False
            for a_name, a in axes.items():
                if a.get("end") is None:
                    continue
                range_applied = True
                lo, hi = min(a.get("start"), a.get("end")), max(a.get("start"), a.get("end"))
                for r in rd:
                    if isinstance(r, dict) and isinstance(r.get(a_name), (int, float)):
                        if not (lo - 1e-9 <= r[a_name] <= hi + 1e-9):
                            range_ok = False
                            range_note.append("%s 越轴: %r" % (a_name, r.get("label")))
            if range_applied:
                gates["axis_range"] = "enforced"
                chk("%s.axis_range" % oid, "读数在声明轴范围内", True, range_ok,
                    note="; ".join(range_note) or "全部在轴范围内")
            else:
                gates["axis_range"] = "skipped_not_provided"
                chk("%s.axis_range" % oid, None, False, None,
                    note="axes 未声明 end；下游不得宣称已核对轴范围")

            # 10) 图例逐字 + 双向映射
            legend = (o.get("elements") or {}).get("legend")
            if abl_struct:
                chk("%s.legend_series_map" % oid, None, False, None,
                    note="ablation:disabled（退化臂关闭结构闸门）")
            elif cls == "plot" and st == "parsed":
                if not isinstance(legend, list) or not legend:
                    gates["legend_series_map"] = "not_found"
                    chk("%s.legend_series_map" % oid, "图例逐字且与 series 双向对应", True, False,
                        note="elements.legend 缺失或为空（未逐字转录图例）")
                else:
                    labels = []
                    for it in legend:
                        if isinstance(it, dict):
                            labels.append(str(it.get("label") or ""))
                        else:
                            labels.append(str(it))
                    labels = [x.strip() for x in labels if x.strip()]
                    miss_s = [x for x in series_decl if x not in labels]
                    miss_l = [x for x in labels if x not in series_decl]
                    chk("%s.legend_series_map" % oid, "图例逐字且与 series 双向对应", True,
                        not miss_s and not miss_l and len(labels) == len(series_decl),
                        note="series未见于图例:%r；图例未列入series:%r" % (miss_s, miss_l))

            # 11) 单位量级一致
            if abl_struct:
                chk("%s.unit_consistency" % oid, None, False, None,
                    note="ablation:disabled（退化臂关闭结构闸门）")
            elif cls == "plot" and st == "parsed" and rd:
                # 读数单位对应**数值轴**（双轴时读数可用 axis 字段指定所属轴）
                val_axes = {n: a for n, a in axes.items() if n != "x"}
                bad = []
                for r in rd:
                    if not isinstance(r, dict):
                        continue
                    ru = str(r.get("units") or "")
                    if not ru:
                        continue
                    tgt = r.get("axis")
                    if tgt and tgt in val_axes:
                        au = str(val_axes[tgt].get("units") or "")
                        if au and unit_norm(au) != unit_norm(ru):
                            bad.append("%s units=%r 与指定轴 %s units=%r 不一致"
                                       % (r.get("label"), ru, tgt, au))
                        continue
                    aus = [unit_norm(a.get("units")) for a in val_axes.values()
                           if a.get("units")]
                    if aus and unit_norm(ru) not in aus:
                        bad.append("%s units=%r 与数值轴单位 %r 不一致"
                                   % (r.get("label"), ru, aus))
                chk("%s.unit_consistency" % oid, "读数单位与数值轴单位一致", True, not bad,
                    note="; ".join(bad) or "单位量级一致")

            # 12) 读数来源定位
            if abl_struct:
                chk("%s.reading_locator" % oid, None, False, None,
                    note="ablation:disabled（退化臂关闭结构闸门）")
            elif cls == "plot" and st == "parsed" and rd:
                bad = []
                for j, r in enumerate(rd):
                    if not isinstance(r, dict):
                        continue
                    if not str(r.get("how") or "").strip():
                        bad.append("readings[%d] 缺 how" % j)
                    if not str(r.get("source_locator") or "").strip():
                        bad.append("readings[%d] 缺 source_locator" % j)
                chk("%s.reading_locator" % oid, "每条读数带 how 与 source_locator", True,
                    not bad, note="; ".join(bad) or "读数均可回指原图位置")

            # 6) 数值回证：每条系列 首/中/尾
            if abl_back:
                gates["numeric_backevidence"] = "skipped_not_provided"
                chk("%s.numeric_backevidence" % oid, None, False, None,
                    note="ablation:disabled（退化臂关闭数值回证；下游不得宣称已核对）")
            else:
                for s in series_decl:
                    srs = [r for r in rd if isinstance(r, dict) and series_of(r.get("label")) == s]
                    if not srs:
                        continue
                    picks = {0: "首"}
                    if len(srs) >= 3:
                        picks[len(srs) // 2] = "中"
                    picks[len(srs) - 1] = "尾"
                    for idx, pos in sorted(picks.items()):
                        r = srs[idx]
                        nums = [norm(r.get(k)) for k in ("x", "y")
                                if isinstance(r.get(k), (int, float))]
                        backed = all(n and n in blob for n in nums) if nums else False
                        approx = r.get("approx") is True
                        tag = "%s.%s[%s/%s#%d]" % (oid, s, pos, r.get("label"), idx)
                        if backed:
                            chk(tag + ".backed", "数字在证据/表格中逐字可回证", True, True)
                        elif approx:
                            unbacked.append({"object": oid, "series": s, "position": pos,
                                             "label": r.get("label"),
                                             "values": [r.get("x"), r.get("y")]})
                            chk(tag + ".backed", "数字在证据/表格中逐字可回证", True, None,
                                note="approximate 读数无逐字回证，降级 warn；下游不得宣称已核对")
                        else:
                            chk(tag + ".backed", "数字在证据/表格中逐字可回证", True, False,
                                note="非 approx 读数缺回证=编造风险")

            for j, r in enumerate(rd):
                if isinstance(r, dict):
                    if r.get("approx") is not True:
                        problems.append("[%s] readings[%d] 缺 approx:true 标记" % (oid, j))
                    if not (r.get("units") or "").strip():
                        problems.append("[%s] readings[%d] 缺 units" % (oid, j))
        elif kind == "table":
            tb = o.get("table") or {}
            if st == "parsed" and (not tb.get("columns") or not tb.get("rows")):
                problems.append("[%s] 表格已解析但缺 columns/rows" % oid)
            # 13) 源数据表全量
            if mat_rows and oid in mat_rows:
                want = mat_rows[oid]
                # 转录行数 = 数据行 + 表头行（表头存于 columns）
                got = len(tb.get("rows") or []) + (1 if tb.get("columns") else 0)
                chk("%s.table_fidelity" % oid, want, True, got >= want,
                    note="材料原表 %d 行（含表头），转录 %d 行（表头+数据行）" % (want, got))
                if got < want:
                    problems.append("[%s] 源数据表未全量转录（材料 %d 行 vs 转录 %d 行）"
                                    % (oid, want, got))
            elif mat_rows:
                gates["table_fidelity"] = "not_found"
                chk("%s.table_fidelity" % oid, None, False, None,
                    note="材料中未找到该表 id（%s）；下游不得宣称已核对全量" % oid)

    for im in wo.get("images") or []:
        if str(im.get("object_id")) not in by_id:
            problems.append("工单图片对象缺失: %s" % im.get("object_id"))
    for t in wo.get("tables") or []:
        if str(t.get("object_id")) not in by_id:
            problems.append("工单表格对象缺失: %s" % t.get("object_id"))

    counts = {"parsed": 0, "not_applicable": 0, "unreadable": 0, "unprocessed": 0}
    for o in objects:
        if isinstance(o, dict):
            counts[o.get("status")] = counts.get(o.get("status"), 0) + 1
    if res.get("status") == "answered" and counts["unprocessed"] > 0:
        problems.append("整体 status=answered 但存在 %d 个 unprocessed 对象（应为 partial）" % counts["unprocessed"])
    inv = inner.get("object_inventory") or {}
    if inv and inv.get("parsed") != counts["parsed"]:
        problems.append("object_inventory.parsed(%s) 与实际(%d)不符" % (inv.get("parsed"), counts["parsed"]))
    unc = res.get("uncertainties") or {}
    if counts["unreadable"] and not (unc.get("unverifiable") or unc.get("human_review") or unc.get("unreported")):
        problems.append("存在 unreadable 对象但 uncertainties 未记录任何不可读项")
    if isinstance(unc, dict) and unbacked:
        for u in unbacked:
            msg = "近似读数 %s(%s) 无逐字回证，建议人工复核" % (u["label"], u["position"])
            if msg not in unc.get("human_review", []):
                unc.setdefault("human_review", []).append(msg)

    verdict = "pass" if not problems else "fail"
    report = {"ok": not problems, "verdict": verdict, "problems": problems,
              "status_counts": counts, "gates": gates, "checks": checks,
              "unbacked_readings": unbacked,
              "ablation": {"mode": mode, "disabled_gates": disabled}}
    res["verification"] = {"gates": gates, "checks": checks,
                           "unbacked_readings": unbacked,
                           "all_pass": not problems,
                           "verdict": verdict,
                           "problems": problems,
                           "ablation": {"mode": mode, "disabled_gates": disabled}}
    try:
        with open(args.result, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=1)
    except Exception as e:
        print("[chart_check] WARN：写盘失败（%s）；判定仍记录在 stdout" % e)

    if problems:
        print("[chart_check] verdict=fail（%d 处）——已记录，退出码 0，交付不中断" % len(problems))
        for p in problems[:50]:
            print("  - %s" % p)
        print("[chart_check] gates=%s ablation=%s" % (gates, mode))
    else:
        print("[chart_check] verdict=pass（对象状态：%s；gates=%s；回证缺口 %d 条已降级 human_review；ablation=%s）" % (
            counts, gates, len(unbacked), mode))
    return 0


if __name__ == "__main__":
    sys.exit(main())
