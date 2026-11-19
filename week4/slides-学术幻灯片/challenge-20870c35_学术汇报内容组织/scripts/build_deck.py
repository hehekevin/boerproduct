#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_deck.py — 纯标准库 OOXML .pptx 构建器（可编辑，无外部依赖）。

输入 spec：{"deck_meta":{...}, "slides":[{layout,title,claim,bullets,figure,
notes,columns,table,...}]}，输出可编辑 16:9 pptx（PowerPoint/WPS 可打开），
notes 写入真实备注页。构建失败写 --log 后照常退出 0（状态经由 log 传递）。
"""
import argparse, json, os, shutil, sys, zipfile
from xml.sax.saxutils import escape

EMU_IN = 914400
FONT_L = "Arial"
FONT_EA = "Noto Sans CJK SC"


def _r(text, size, bold=False, italic=False, color="1A1A1A"):
    b = ' b="1"' if bold else ""
    i = ' i="1"' if italic else ""
    return ('<a:r><a:rPr lang="zh-CN" altLang="en-US" sz="%d"%s%s dirty="0">'
            '<a:solidFill><a:srgbClr val="%s"/></a:solidFill>'
            '<a:latin typeface="%s"/><a:ea typeface="%s"/></a:rPr>'
            '<a:t>%s</a:t></a:r>' % (int(size * 100), b, i, color, FONT_L, FONT_EA,
                                     escape(str(text))))


def _p(text, size, bullet=False, bold=False, italic=False, color="1A1A1A",
       align=None, space_after=6):
    bu = '<a:buChar char="•"/>' if bullet else '<a:buNone/>'
    al = '<a:pPr algn="%s"><a:spcAft><a:spcPts val="%d"/></a:spcAft>%s</a:pPr>' % (
        align or "l", space_after * 100, bu)
    if not text:
        return "<a:p>%s<a:endParaRPr/></a:p>" % al
    return "<a:p>%s%s</a:p>" % (al, _r(text, size, bold, italic, color))


def _txbox(name, x, y, w, h, paras, anchor="t"):
    return ('<p:sp><p:nvSpPr><p:cNvPr id="0" name="%s"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>'
            '<p:spPr><a:xfrm><a:off x="%d" y="%d"/><a:ext cx="%d" cy="%d"/></a:xfrm>'
            '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>'
            '<p:txBody><a:bodyPr wrap="square" lIns="36000" tIns="18000" rIns="36000" bIns="18000" anchor="%s">'
            '<a:noAutofit/></a:bodyPr><a:lstStyle/>%s</p:txBody></p:sp>'
            % (escape(name), int(x * EMU_IN), int(y * EMU_IN), int(w * EMU_IN),
               int(h * EMU_IN), anchor, "".join(paras)))


def _tbl(rows, x, y, w, size=12):
    ncols = max(len(r) for r in rows)
    grid = "".join('<a:gridCol w="%d"/>' % int(w * EMU_IN / ncols) for _ in range(ncols))
    trs = []
    for ri, row in enumerate(rows):
        tcs = ['<a:tc><a:txBody><a:bodyPr/><a:lstStyle/>%s</a:txBody><a:tcPr/></a:tc>'
               % _p(row[ci] if ci < len(row) else "", size, bold=(ri == 0))
               for ci in range(ncols)]
        trs.append('<a:tr h="380000">%s</a:tr>' % "".join(tcs))
    return ('<p:graphicFrame><p:nvGraphicFramePr><p:cNvPr id="0" name="table"/>'
            '<p:cNvGraphicFramePr/><p:nvPr/></p:nvGraphicFramePr>'
            '<p:xfrm><a:off x="%d" y="%d"/><a:ext cx="%d" cy="4800000"/></p:xfrm>'
            '<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/table">'
            '<a:tbl><a:tblPr firstRow="1"/><a:tblGrid>%s</a:tblGrid>%s</a:tbl></a:graphicData>'
            '</a:graphic></p:graphicFrame>'
            % (int(x * EMU_IN), int(y * EMU_IN), int(w * EMU_IN), grid, "".join(trs)))


def _slide_xml(body):
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
            'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
            '<p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
            '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>'
            '<a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
            + body + '</p:spTree></p:cSld></p:sld>')


def _notes_xml(text):
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<p:notes xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
            'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
            '<p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
            '<p:grpSpPr/><p:sp><p:nvSpPr><p:cNvPr id="2" name="Notes Placeholder"/>'
            '<p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr><p:nvPr><p:ph type="body" idx="1"/></p:nvPr></p:nvSpPr>'
            '<p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/>'
            '<a:p><a:r><a:rPr lang="zh-CN" dirty="0"/><a:t>%s</a:t></a:r></a:p>'
            '</p:txBody></p:sp></p:spTree></p:cSld></p:notes>' % escape(str(text)))


CT = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
      '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
      '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
      '<Default Extension="xml" ContentType="application/xml"/>'
      '<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>'
      '<Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>'
      '<Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>'
      '<Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>%s</Types>')

THEME = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
         '<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="Minimal Acad">'
         '<a:themeElements><a:clrScheme name="Minimal"><a:dk1><a:srgbClr val="1A1A1A"/></a:dk1>'
         '<a:lt1><a:srgbClr val="FFFFFF"/></a:lt1><a:dk2><a:srgbClr val="2B3A55"/></a:dk2>'
         '<a:lt2><a:srgbClr val="F2F5F9"/></a:lt2><a:accent1><a:srgbClr val="2B5BA8"/></a:accent1>'
         '<a:accent2><a:srgbClr val="3E7CB1"/></a:accent2><a:accent3><a:srgbClr val="6AA1C4"/></a:accent3>'
         '<a:accent4><a:srgbClr val="8FB8D8"/></a:accent4><a:accent5><a:srgbClr val="B3CFE5"/></a:accent5>'
         '<a:accent6><a:srgbClr val="D7E6F2"/></a:accent6><a:hlink><a:srgbClr val="2B5BA8"/></a:hlink>'
         '<a:folHlink><a:srgbClr val="6AA1C4"/></a:folHlink></a:clrScheme>'
         '<a:fontScheme name="Minimal"><a:majorFont><a:latin typeface="Arial"/><a:ea typeface="Noto Sans CJK SC"/><a:cs typeface=""/></a:majorFont>'
         '<a:minorFont><a:latin typeface="Arial"/><a:ea typeface="Noto Sans CJK SC"/><a:cs typeface=""/></a:minorFont></a:fontScheme>'
         '<a:fmtScheme name="Minimal"><a:fillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
         '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:fillStyleLst>'
         '<a:lnStyleLst><a:ln><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln>'
         '<a:ln><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln>'
         '<a:ln><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln></a:lnStyleLst>'
         '<a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle><a:effectStyle><a:effectLst/></a:effectStyle>'
         '<a:effectStyle><a:effectLst/></a:effectStyle></a:effectStyleLst>'
         '<a:bgFillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
         '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
         '</a:bgFillStyleLst></a:fmtScheme></a:themeElements></a:theme>')


def build(spec, out_path):
    slides = spec.get("slides", [])
    tmp = out_path + ".tmpdir"
    if os.path.exists(tmp):
        shutil.rmtree(tmp)
    for d in ("ppt/slides/_rels", "ppt/_rels", "ppt/slideLayouts/_rels",
              "ppt/slideMasters/_rels", "ppt/notesSlides/_rels", "ppt/media",
              "ppt/theme", "_rels"):
        os.makedirs(os.path.join(tmp, d), exist_ok=True)
    overrides, id_entries = [], []
    pres_rels = ['<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/>']
    for idx, sl in enumerate(slides, start=1):
        layout = str(sl.get("layout") or "bullets")
        shapes = []
        rels = ['<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>']
        rid = 2
        shapes.append(_txbox("pageno", 12.45, 7.05, 0.6, 0.35,
                             [_p(str(idx), 10, color="808080", align="r", space_after=0)]))
        if layout in ("title", "closing"):
            shapes.append(_txbox("title", 1.0, 2.7, 11.33, 1.3,
                                 [_p(sl.get("title", ""), 36, bold=True, color="2B3A55",
                                     align="ctr", space_after=10)], anchor="ctr"))
            sub = sl.get("subtitle")
            if sub:
                subs = sub if isinstance(sub, list) else [sub]
                shapes.append(_txbox("subtitle", 1.0, 4.0, 11.33, 1.4,
                                     [_p(x, 16, color="444444", align="ctr", space_after=4)
                                      for x in subs], anchor="t"))
        elif layout == "section":
            shapes.append(_txbox("section", 1.0, 3.0, 11.33, 1.5,
                                 [_p(sl.get("title", ""), 34, bold=True, color="2B5BA8",
                                     align="ctr", space_after=0)], anchor="ctr"))
        elif layout == "table":
            shapes.append(_txbox("title", 0.6, 0.35, 12.13, 0.9,
                                 [_p(sl.get("title", ""), 28, bold=True, color="2B3A55",
                                     space_after=0)], anchor="t"))
            rows = (sl.get("table") or {}).get("rows") or sl.get("rows") or [[""]]
            shapes.append(_tbl(rows, 0.7, 1.5, 11.9, size=sl.get("body_size", 13)))
        elif layout == "two-col":
            shapes.append(_txbox("title", 0.6, 0.35, 12.13, 0.9,
                                 [_p(sl.get("title", ""), 28, bold=True, color="2B3A55",
                                     space_after=0)], anchor="t"))
            for ci, col in enumerate((sl.get("columns") or [[], []])[:2]):
                paras = [_p(b, sl.get("body_size", 18), bullet=True) for b in col]
                shapes.append(_txbox("col%d" % ci, 0.6 + ci * 6.2, 1.45, 5.85, 5.3, paras))
        else:  # bullets / bullets+claim
            shapes.append(_txbox("title", 0.6, 0.35, 12.13, 0.9,
                                 [_p(sl.get("title", ""), 28, bold=True, color="2B3A55",
                                     space_after=0)], anchor="t"))
            paras = []
            claim = sl.get("claim")
            if claim:
                paras.append(_p("主张：" + claim, sl.get("body_size", 18), bullet=False,
                                bold=True, color="2B5BA8"))
            for b in sl.get("bullets") or []:
                paras.append(_p(b, sl.get("body_size", 18), bullet=True))
            shapes.append(_txbox("body", 0.6, 1.45, 12.13, 5.3, paras))
        if sl.get("notes"):
            with open(os.path.join(tmp, "ppt", "notesSlides", "notesSlide%d.xml" % idx),
                      "w", encoding="utf-8") as f:
                f.write(_notes_xml(sl["notes"]))
            with open(os.path.join(tmp, "ppt", "notesSlides", "_rels",
                                   "notesSlide%d.xml.rels" % idx), "w", encoding="utf-8") as f:
                f.write('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="../slides/slide%d.xml"/></Relationships>' % idx)
            rels.append('<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesSlide" Target="../notesSlides/notesSlide%d.xml"/>' % (rid, idx))
            rid += 1
            overrides.append('<Override PartName="/ppt/notesSlides/notesSlide%d.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.notesSlide+xml"/>' % idx)
        with open(os.path.join(tmp, "ppt", "slides", "slide%d.xml" % idx), "w",
                  encoding="utf-8") as f:
            f.write(_slide_xml("".join(shapes)))
        with open(os.path.join(tmp, "ppt", "slides", "_rels", "slide%d.xml.rels" % idx),
                  "w", encoding="utf-8") as f:
            f.write('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                    + "".join(rels) + "</Relationships>")
        overrides.append('<Override PartName="/ppt/slides/slide%d.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>' % idx)
        id_entries.append('<p:sldId id="%d" r:id="rId%d"/>' % (255 + idx, idx + 1))
        pres_rels.append('<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide%d.xml"/>' % (idx + 1, idx))
    with open(os.path.join(tmp, "[Content_Types].xml"), "w", encoding="utf-8") as f:
        f.write(CT % "".join(overrides))
    with open(os.path.join(tmp, "_rels", ".rels"), "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/></Relationships>')
    with open(os.path.join(tmp, "ppt", "presentation.xml"), "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
                'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" saveSubsetFonts="1">'
                '<p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>'
                '<p:sldIdLst>%s</p:sldIdLst><p:sldSz cx="12192000" cy="6858000"/>'
                '<p:notesSz cx="6858000" cy="9144000"/></p:presentation>' % "".join(id_entries))
    with open(os.path.join(tmp, "ppt", "_rels", "presentation.xml.rels"), "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                + "".join(pres_rels) + "</Relationships>")
    with open(os.path.join(tmp, "ppt", "slideMasters", "slideMaster1.xml"), "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<p:sldMaster xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
                'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
                '<p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
                '<p:grpSpPr/></p:spTree></p:cSld>'
                '<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="hlink" accent2="folHlink" '
                'accent3="accent1" accent4="accent2" accent5="accent3" accent6="accent4" '
                'hlink="accent5" folHlink="accent6"/>'
                '<p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst></p:sldMaster>')
    with open(os.path.join(tmp, "ppt", "slideMasters", "_rels", "slideMaster1.xml.rels"), "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>'
                '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/></Relationships>')
    with open(os.path.join(tmp, "ppt", "slideLayouts", "slideLayout1.xml"), "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<p:sldLayout xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
                'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" type="blank" preserve="1">'
                '<p:cSld name="Blank"><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/>'
                '<p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/></p:spTree></p:cSld>'
                '<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>')
    with open(os.path.join(tmp, "ppt", "slideLayouts", "_rels", "slideLayout1.xml.rels"), "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/></Relationships>')
    with open(os.path.join(tmp, "ppt", "theme", "theme1.xml"), "w", encoding="utf-8") as f:
        f.write(THEME)
    if os.path.exists(out_path):
        os.remove(out_path)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _d, files in os.walk(tmp):
            for fn in files:
                full = os.path.join(root, fn)
                z.write(full, os.path.relpath(full, tmp).replace(os.sep, "/"))
    shutil.rmtree(tmp)
    return out_path


def main():
    log = {"builder": "stdlib_zip_ooxml", "ok": False}
    try:
        args = parse_args()
        spec = json.load(open(args.spec, encoding="utf-8"))
        build(spec, args.out)
        log["ok"] = True
        log["slides"] = len(spec.get("slides", []))
        log["out"] = args.out
        if args.log:
            json.dump(log, open(args.log, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)
    except SystemExit:
        print("usage: build_deck.py spec.json out.pptx --log layout_log.json（参数缺失，退出码 0）")
        return 0
    except Exception as e:
        log["error"] = str(e)
        try:
            args = parse_args()
            if args.log:
                json.dump(log, open(args.log, "w", encoding="utf-8"),
                          ensure_ascii=False, indent=1)
        except Exception:
            pass
    print(json.dumps(log, ensure_ascii=False))
    return 0


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("spec")
    ap.add_argument("out")
    ap.add_argument("--log", default=None)
    return ap.parse_args()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        sys.exit(0)  # 所有失败路径（含 argparse error）一律退出码 0

