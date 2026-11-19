#!/usr/bin/env python3
"""deck_build.py — 构建可编辑演示稿（generate 双轨 / edit 工单编辑）+ 修改记录。

generate 模式（无起始稿）：
  python3 deck_build.py deck.json /app/output/presentation.pptx --mode generate \
      --template <模板.pptx> --report probe_report.json --log /app/output/layout_log.json
  有模板且 python-pptx 可用 → 克隆模板填充（主题真实继承，不写死字体）
  否则 → pptx_minimal stdlib 兜底（可编辑性保持），inheritance 如实登记

edit 模式（有 starting-deck，按 slide-workorder 编辑）：
  python3 deck_build.py edits.json /app/output/presentation.pptx --mode edit \
      --starting-deck /input/starting-deck.pptx --log /app/output/change_log.json
  逐条操作 set_title/set_bullets/set_notes/move_slide/delete_slide 应用到起始稿副本，
  其余页零改动（source preservation）；每条 applied/fallback/skipped 记入 change_log。

退出码恒 0：构建失败落 log（ok:false + 原因 + 降级建议），不抛栈不中断。
edits.json 格式（示意，非正式案例）：
  {"ops":[{"op":"set_title","slide":2,"text":"新标题"},
          {"op":"set_bullets","slide":2,"bullets":["a","b"]},
          {"op":"set_notes","slide":2,"text":"讲解备注"},
          {"op":"delete_slide","slide":5}]}
"""
import argparse
import copy
import json
import os
import re
import shutil
import sys
import zipfile
from xml.etree import ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS_P = "http://schemas.openxmlformats.org/presentationml/2006/main"
ET.register_namespace("a", NS_A)
ET.register_namespace("p", NS_P)


def _log(log, key, value):
    log.setdefault(key, []).append(value)


# ---------- generate：python-pptx 模板克隆 ----------
def build_with_pptx(deck, out_path, template_path, report):
    from pptx import Presentation
    from pptx.util import Inches, Pt
    rec = report or {}
    lay_map = (rec.get("template") or {}).get("recommendation") or {}
    if template_path:
        prs = Presentation(template_path)
    else:
        prs = Presentation()
        prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    blank = prs.slide_layouts[6] if len(prs.slide_layouts) > 6 else prs.slide_layouts[-1]
    used = []
    for sl in deck.get("slides", []):
        lay_name = lay_map.get(sl.get("layout", "bullets"))
        layout = None
        if lay_name:
            for cand in prs.slide_layouts:
                if cand.name == lay_name:
                    layout = cand
                    break
        layout = layout or blank
        used.append(layout.name)
        slide = prs.slides.add_slide(layout)
        phs = {p.placeholder_format.idx: p for p in slide.placeholders}
        title_ph = next((p for i, p in phs.items()
                         if str(p.placeholder_format.type).lower().find("title") >= 0), None)
        body_ph = next((p for i, p in phs.items()
                        if str(p.placeholder_format.type).lower().find("body") >= 0 and p is not title_ph), None)
        if title_ph is not None and sl.get("title"):
            title_ph.text_frame.text = sl["title"]
        elif sl.get("title"):
            box = slide.shapes.add_textbox(Inches(0.6), Inches(0.35), Inches(12.1), Inches(0.9))
            box.text_frame.text = sl["title"]
            _ = box  # textbox fallback（layout_slot_insufficient 时登记）
        if body_ph is not None:
            tf = body_ph.text_frame
            first = True
            for b in sl.get("bullets") or []:
                t = b.get("text") if isinstance(b, dict) else str(b)
                para = tf.paragraphs[0] if first else tf.add_paragraph()
                para.text = t
                first = False
        else:
            box = slide.shapes.add_textbox(Inches(0.6), Inches(1.45), Inches(12.1), Inches(5.3))
            tf = box.text_frame
            first = True
            for b in sl.get("bullets") or []:
                t = b.get("text") if isinstance(b, dict) else str(b)
                para = tf.paragraphs[0] if first else tf.add_paragraph()
                para.text = t
                first = False
        if sl.get("notes"):
            slide.notes_slide.notes_text_frame.text = sl["notes"]
    prs.save(out_path)
    return {"builder": "python-pptx", "font_mode": "theme_inherit" if template_path else "default_theme",
            "inheritance": "real" if template_path else "standalone_minimal_fallback",
            "layouts_used": used}


# ---------- generate：stdlib 兜底 ----------
def build_with_minimal(deck, out_path):
    import pptx_minimal
    pptx_minimal.build(deck, out_path)
    return {"builder": "pptx_minimal(stdlib)", "font_mode": "embedded_theme",
            "inheritance": "standalone_minimal_fallback",
            "layouts_used": [s.get("layout", "bullets") for s in deck.get("slides", [])]}


# ---------- edit：python-pptx 原位编辑 ----------
def edit_with_pptx(src, out_path, ops, log):
    from pptx import Presentation
    prs = Presentation(src)
    n = len(prs.slides._sldIdLst)
    for op in ops:
        kind = op.get("op")
        idx = int(op.get("slide", 0)) - 1
        try:
            if not (0 <= idx < n):
                raise IndexError("slide %d out of range (1..%d)" % (idx + 1, n))
            slide = prs.slides[idx]
            if kind == "set_title":
                if slide.shapes.title is None:
                    raise ValueError("no title placeholder")
                slide.shapes.title.text_frame.text = op["text"]
            elif kind == "set_bullets":
                ph = next(p for p in slide.placeholders
                          if str(p.placeholder_format.type).lower().find("body") >= 0)
                tf = ph.text_frame
                tf.clear()
                for i, b in enumerate(op.get("bullets") or []):
                    para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
                    para.text = str(b)
            elif kind == "set_notes":
                slide.notes_slide.notes_text_frame.text = op.get("text") or ""
            elif kind == "delete_slide":
                rId = prs.slides._sldIdLst[idx].get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
                prs.part.drop_rel(rId)
                prs.slides._sldIdLst.remove(prs.slides._sldIdLst[idx])
            elif kind == "move_slide":
                el = prs.slides._sldIdLst[idx]
                prs.slides._sldIdLst.remove(el)
                prs.slides._sldIdLst.insert(int(op.get("position", 0)), el)
            else:
                _log(log, "skipped", {"op": op, "reason": "unknown_op"})
                continue
            n = len(prs.slides._sldIdLst)
            _log(log, "applied", {"op": op, "engine": "python-pptx"})
        except Exception as e:
            _log(log, "fallback", {"op": op, "reason": str(e)[:160]})
    prs.save(out_path)


# ---------- edit：stdlib XML 原位编辑（无 python-pptx） ----------
def _slide_xml_names(z):
    return sorted([n for n in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)],
                  key=lambda n: int(re.search(r"(\d+)", n).group(1)))


def _set_shape_texts(root, want_title, bullets):
    """改标题与 body 文本。优先 ph 占位符；无占位符的 textbox 稿取最顶部文本框当标题。"""
    changed = {"title": False, "body": False}
    sps = [sp for sp in root.iter("{%s}sp" % NS_P)
           if sp.find(".//{%s}txBody" % NS_P) is not None]
    # 无占位符时的标题启发式：找 y 最小的含文本 shape
    def shape_top_y(sp):
        off = sp.find(".//{%s}off" % NS_A)
        try:
            return int(off.get("y")) if off is not None else 1 << 62
        except Exception:
            return 1 << 62
    title_sp = min(sps, key=shape_top_y) if sps else None
    for sp in sps:
        tx = sp.find(".//{%s}txBody" % NS_P)
        texts = [t for t in tx.iter("{%s}t" % NS_A)]
        if not texts:
            continue
        ph = sp.find(".//{%s}ph" % NS_P)
        ptype = ph.get("type") if ph is not None else ""
        is_title_shape = ptype in ("title", "ctrTitle") or (
            ph is None and sp == title_sp)
        if want_title is not None and is_title_shape and texts:
            texts[0].text = want_title
            for t in texts[1:]:
                t.text = ""
            changed["title"] = True
            want_title = None
        elif bullets is not None and sp is not title_sp and (ptype in ("body", "subTitle") or ph is None):
            ps = list(tx.findall("{%s}p" % NS_A))
            for i, b in enumerate(bullets):
                if i < len(ps):
                    ts = list(ps[i].iter("{%s}t" % NS_A))
                    if ts:
                        ts[0].text = str(b)
                        for t in ts[1:]:
                            t.text = ""
                    else:
                        r = ET.SubElement(ps[i], "{%s}r" % NS_A)
                        t = ET.SubElement(r, "{%s}t" % NS_A)
                        t.text = str(b)
                else:
                    newp = copy.deepcopy(ps[-1] if ps else ET.Element("{%s}p" % NS_A))
                    ts = list(newp.iter("{%s}t" % NS_A))
                    if ts:
                        ts[0].text = str(b)
                        for t in ts[1:]:
                            t.text = ""
                    tx.append(newp)
            for extra in ps[len(bullets):]:
                tx.remove(extra)
            changed["body"] = True
            bullets = None
    return changed, want_title, bullets


def edit_with_stdlib(src, out_path, ops, log):
    tmp = out_path + ".tmpdir"
    if os.path.exists(tmp):
        shutil.rmtree(tmp)
    os.makedirs(tmp)
    with zipfile.ZipFile(src) as z:
        z.extractall(tmp)
    slide_dir = os.path.join(tmp, "ppt", "slides")
    names = sorted([n for n in os.listdir(slide_dir) if re.match(r"slide\d+\.xml$", n)],
                   key=lambda n: int(re.search(r"(\d+)", n).group(1)))
    for op in ops:
        kind, idx = op.get("op"), int(op.get("slide", 0)) - 1
        if kind in ("move_slide", "delete_slide"):
            _log(log, "skipped", {"op": op, "reason": "stdlib 兜底不支持重排/删页，已在 change_log 登记，需人工或 python-pptx 完成"})
            continue
        if not (0 <= idx < len(names)):
            _log(log, "skipped", {"op": op, "reason": "slide out of range"})
            continue
        path = os.path.join(slide_dir, names[idx])
        root = ET.parse(path).getroot()
        if kind == "set_notes":
            changed = {"notes": True}
            npath = os.path.join(tmp, "ppt", "notesSlides", "notesSlide%d.xml" % (idx + 1))
            if os.path.exists(npath):
                nroot = ET.parse(npath).getroot()
                ts = list(nroot.iter("{%s}t" % NS_A))
                if ts:
                    ts[0].text = op.get("text") or ""
                _log(log, "applied", {"op": op, "engine": "raw-xml"})
            else:
                _log(log, "fallback", {"op": op, "reason": "no notesSlide part"})
            continue
        want_title = op.get("text") if kind == "set_title" else None
        bullets = op.get("bullets") if kind == "set_bullets" else None
        changed, want_title, bullets = _set_shape_texts(root, want_title, bullets)
        ET.ElementTree(root).write(path, encoding="UTF-8", xml_declaration=True)
        ok = (kind == "set_title" and changed["title"]) or (kind == "set_bullets" and changed["body"])
        _log(log, "applied" if ok else "fallback", {"op": op, "engine": "raw-xml",
             "reason": None if ok else "未找到目标占位符，操作未生效（如实登记）"})
    if os.path.exists(out_path):
        os.remove(out_path)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zout:
        for r, _d, fs in os.walk(tmp):
            for fn in fs:
                full = os.path.join(r, fn)
                zout.write(full, os.path.relpath(full, tmp).replace(os.sep, "/"))
    shutil.rmtree(tmp)


def main():
    class P(argparse.ArgumentParser):
        def error(self, m):
            print(json.dumps({"argparse_error": m}, ensure_ascii=False))
            sys.exit(0)
    ap = P()
    ap.add_argument("spec", help="deck.json（generate）或 edits.json（edit）")
    ap.add_argument("out", help="输出 pptx 路径（/app/output/presentation.pptx）")
    ap.add_argument("--mode", choices=["generate", "edit"], default="generate")
    ap.add_argument("--template", default=None)
    ap.add_argument("--starting-deck", default=None)
    ap.add_argument("--report", default=None, help="probe_report.json（模板推荐映射）")
    ap.add_argument("--log", default=None, help="构建/修改记录输出")
    args = ap.parse_args()

    log = {"mode": args.mode, "spec": args.spec, "out": args.out, "ok": False,
           "degrade_chain": []}
    try:
        spec = json.load(open(args.spec, encoding="utf-8"))
    except Exception as e:
        log["error"] = "spec unreadable: %s" % e
        _finish(log, args)
        return
    try:
        if args.mode == "generate":
            report = None
            if args.report and os.path.exists(args.report):
                report = json.load(open(args.report, encoding="utf-8"))
            tpl_ok = args.template and os.path.exists(args.template)
            try:
                info = build_with_pptx(spec, args.out, args.template if tpl_ok else None, report)
            except ImportError:
                log["degrade_chain"].append({"stage": "build", "fallback": "pptx_minimal",
                                             "reason": "python-pptx unavailable"})
                info = build_with_minimal(spec, args.out)
            except Exception as e:
                log["degrade_chain"].append({"stage": "build", "fallback": "pptx_minimal",
                                             "reason": str(e)[:200]})
                info = build_with_minimal(spec, args.out)
            log["build_info"] = info
            if not tpl_ok and args.template:
                log["degrade_chain"].append({"stage": "template", "fallback": "no_template",
                                             "reason": "template path missing"})
        else:
            src = args.starting_deck
            if not src or not os.path.exists(src):
                log["error"] = "edit 模式需要 --starting-deck 且文件存在"
                _finish(log, args)
                return
            shutil.copyfile(src, args.out)  # 保真基线：先整体复制，再原位改
            ops = spec.get("ops") if isinstance(spec, dict) else spec
            ops = ops or []
            try:
                edit_with_pptx(src, args.out, ops, log)
                log["build_info"] = {"builder": "python-pptx", "inheritance": "source_deck_kept"}
            except ImportError:
                log["degrade_chain"].append({"stage": "edit", "fallback": "raw-xml",
                                             "reason": "python-pptx unavailable"})
                edit_with_stdlib(src, args.out, ops, log)
                log["build_info"] = {"builder": "raw-xml stdlib", "inheritance": "source_deck_kept"}
        log["ok"] = os.path.exists(args.out)
    except Exception as e:
        log["error"] = "%s: %s" % (type(e).__name__, e)
    _finish(log, args)


def _finish(log, args):
    if args.log:
        try:
            with open(args.log, "w", encoding="utf-8") as f:
                json.dump(log, f, ensure_ascii=False, indent=1)
        except Exception as e:
            log["log_write_error"] = str(e)
    print(json.dumps({k: log.get(k) for k in ("ok", "mode", "build_info", "error", "degrade_chain")},
                     ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    main()
