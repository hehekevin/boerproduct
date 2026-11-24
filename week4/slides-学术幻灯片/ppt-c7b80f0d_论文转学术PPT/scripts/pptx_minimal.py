#!/usr/bin/env python3
"""pptx_minimal.py — pure-stdlib minimal OOXML .pptx writer (offline fallback).

Builds an editable 16:9 deck from a slide spec list WITHOUT python-pptx.
Each slide dict supports:
  layout: title|section|bullets|bullets+figure|figure|two-col|table|closing
  title, subtitle, bullets(list[str]), columns(list[list[str]]),
  figure{"path","caption"}, table{"rows":[[str,...]]},
  notes(str), font sizes: title_size, body_size

Usage:
  python3 pptx_minimal.py spec.json out.pptx
  spec.json = {"deck_meta": {...}, "slides": [ ... ]}

Escapes all XML text; images are copied into ppt/media. Result opens in
PowerPoint / WPS / LibreOffice and remains fully editable.
"""
import json
import os
import re
import shutil
import sys
import zipfile
from xml.sax.saxutils import escape

EMU_IN = 914400
SLIDE_W, SLIDE_H = 12192000, 6858000  # 13.333 x 7.5 in (16:9)


def _xml(s):
    return escape(str(s))


def _r(text, size, bold=False, italic=False, color="1A1A1A", font_latin="Arial", font_ea="Noto Sans CJK SC"):
    b = ' b="1"' if bold else ""
    i = ' i="1"' if italic else ""
    return (
        '<a:r><a:rPr lang="zh-CN" altLang="en-US" sz="%d"%s%s dirty="0">'
        '<a:solidFill><a:srgbClr val="%s"/></a:solidFill>'
        '<a:latin typeface="%s"/><a:ea typeface="%s"/></a:rPr>'
        '<a:t>%s</a:t></a:r>'
        % (int(size * 100), b, i, color, _xml(font_latin), _xml(font_ea), _xml(text))
    )


def _p(text, size, bullet=False, bold=False, italic=False, color="1A1A1A",
       font_latin="Arial", font_ea="Noto Sans CJK SC", space_after=6, align=None):
    bu = '<a:buChar char="•"/>' if bullet else '<a:buNone/>'
    al = '<a:pPr algn="%s"><a:spcAft><a:spcPts val="%d"/></a:spcAft>%s</a:pPr>' % (
        align or "l", space_after * 100, bu)
    if not text:
        return "<a:p>%s<a:endParaRPr/></a:p>" % al
    return "<a:p>%s%s</a:p>" % (al, _r(text, size, bold, italic, color, font_latin, font_ea))


def _txbox(name, x, y, w, h, paras, wrap="square", anchor="t"):
    return (
        '<p:sp><p:nvSpPr><p:cNvPr id="0" name="%s"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>'
        '<p:spPr><a:xfrm><a:off x="%d" y="%d"/><a:ext cx="%d" cy="%d"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>'
        '<p:txBody><a:bodyPr wrap="%s" lIns="36000" tIns="18000" rIns="36000" bIns="18000" anchor="%s">'
        '<a:noAutofit/></a:bodyPr><a:lstStyle/>%s</p:txBody></p:sp>'
        % (_xml(name), int(x * EMU_IN), int(y * EMU_IN), int(w * EMU_IN), int(h * EMU_IN),
           wrap, anchor, "".join(paras))
    )


def _pic(rel_id, x, y, w, h):
    return (
        '<p:pic><p:nvPicPr><p:cNvPr id="0" name="figure"/><p:cNvPicPr/><p:nvPr/></p:nvPicPr>'
        '<p:blipFill><a:blip r:embed="%s"/><a:stretch><a:fillRect/></a:stretch></p:blipFill>'
        '<p:spPr><a:xfrm><a:off x="%d" y="%d"/><a:ext cx="%d" cy="%d"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr></p:pic>'
        % (rel_id, int(x * EMU_IN), int(y * EMU_IN), int(w * EMU_IN), int(h * EMU_IN))
    )


def _tbl(rows, x, y, w, h, size=12):
    nrows, ncols = len(rows), max(len(r) for r in rows)
    col_w = int(w * EMU_IN / ncols)
    grid = "".join('<a:gridCol w="%d"/>' % col_w for _ in range(ncols))
    trs = []
    for ri, row in enumerate(rows):
        tcs = []
        for ci in range(ncols):
            val = row[ci] if ci < len(row) else ""
            bold = "1" if ri == 0 else "0"
            tcs.append(
                '<a:tc><a:txBody><a:bodyPr/><a:lstStyle/>%s</a:txBody><a:tcPr/></a:tc>'
                % _p(val, size, bold=(ri == 0))
            )
        trs.append('<a:tr h="380000">%s</a:tr>' % "".join(tcs))
    return (
        '<p:graphicFrame><p:nvGraphicFramePr><p:cNvPr id="0" name="table"/><p:cNvGraphicFramePr/>'
        '<p:nvPr/></p:nvGraphicFramePr><p:xfrm><a:off x="%d" y="%d"/><a:ext cx="%d" cy="%d"/></p:xfrm>'
        '<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/table">'
        '<a:tbl><a:tblPr firstRow="1"/><a:tblGrid>%s</a:tblGrid>%s</a:tbl></a:graphicData>'
        '</a:graphic></p:graphicFrame>' % (int(x * EMU_IN), int(y * EMU_IN), int(w * EMU_IN), int(h * EMU_IN), grid, "".join(trs))
    )


def _slide_xml(sp_shapes, pic_rels=None):
    body = "".join(sp_shapes)
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
        '<p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
        '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>'
        '<a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
        + body + '</p:spTree></p:cSld><p:clrMapOvr><a:overrideClrMapping bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2"/></p:clrMapOvr></p:sld>'
    )


def _notes_xml(text):
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<p:notes xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
        '<p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
        '<p:grpSpPr/>'
        '<p:sp><p:nvSpPr><p:cNvPr id="2" name="Notes Placeholder"/><p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr><p:nvPr><p:ph type="body" idx="1"/></p:nvPr></p:nvSpPr>'
        '<p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/>'
        '<a:p><a:r><a:rPr lang="zh-CN" dirty="0"/><a:t>%s</a:t></a:r></a:p>'
        '</p:txBody></p:sp></p:spTree></p:cSld></p:notes>' % _xml(text)
    )


def _contain_fit(img_w, img_h, box_w, box_h):
    """Return (w,h) inches preserving aspect inside box (values in EMU already /EMU_IN floats)."""
    if img_w <= 0 or img_h <= 0:
        return box_w, box_h
    scale = min(box_w / img_w, box_h / img_h)
    return img_w * scale, img_h * scale


def png_size(path):
    try:
        with open(path, "rb") as f:
            head = f.read(24)
        if head[:8] == b"\x89PNG\r\n\x1a\n":
            w = int.from_bytes(head[16:20], "big")
            h = int.from_bytes(head[20:24], "big")
            return w, h
    except Exception:
        pass
    return None


def jpg_size(path):
    try:
        with open(path, "rb") as f:
            data = f.read()
        i = 2
        while i < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3):
                h = int.from_bytes(data[i + 5:i + 7], "big")
                w = int.from_bytes(data[i + 7:i + 9], "big")
                return w, h
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                i += 2
                continue
            seglen = int.from_bytes(data[i + 2:i + 4], "big")
            i += 2 + seglen
    except Exception:
        pass
    return None


CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Default Extension="png" ContentType="image/png"/>'
    '<Default Extension="jpg" ContentType="image/jpeg"/>'
    '<Default Extension="jpeg" ContentType="image/jpeg"/>'
    '<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>'
    '<Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>'
    '<Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>'
    '<Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>'
    '%s'
    '</Types>'
)

ROOT_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>'
    '</Relationships>'
)

PRESENTATION = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
    'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" saveSubsetFonts="1">'
    '<p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>'
    '<p:sldIdLst>%SLIDES%</p:sldIdLst>'
    '<p:sldSz cx="12192000" cy="6858000"/><p:notesSz cx="6858000" cy="9144000"/></p:presentation>'
)

SLIDE_MASTER = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<p:sldMaster xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
    'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
    '<p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/></p:spTree></p:cSld>'
    '<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="hlink" accent2="folHlink" accent3="accent1" accent4="accent2" accent5="accent3" accent6="accent4" hlink="accent5" folHlink="accent6"/>'
    '<p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst></p:sldMaster>'
)

SLIDE_LAYOUT = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<p:sldLayout xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
    'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" type="blank" preserve="1">'
    '<p:cSld name="Blank"><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/></p:spTree></p:cSld>'
    '<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>'
)

THEME = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="Minimal Acad">'
    '<a:themeElements>'
    '<a:clrScheme name="Minimal"><a:dk1><a:srgbClr val="1A1A1A"/></a:dk1><a:lt1><a:srgbClr val="FFFFFF"/></a:lt1>'
    '<a:dk2><a:srgbClr val="2B3A55"/></a:dk2><a:lt2><a:srgbClr val="F2F5F9"/></a:lt2>'
    '<a:accent1><a:srgbClr val="2B5BA8"/></a:accent1><a:accent2><a:srgbClr val="3E7CB1"/></a:accent2>'
    '<a:accent3><a:srgbClr val="6AA1C4"/></a:accent3><a:accent4><a:srgbClr val="8FB8D8"/></a:accent4>'
    '<a:accent5><a:srgbClr val="B3CFE5"/></a:accent5><a:accent6><a:srgbClr val="D7E6F2"/></a:accent6>'
    '<a:hlink><a:srgbClr val="2B5BA8"/></a:hlink><a:folHlink><a:srgbClr val="6AA1C4"/></a:folHlink></a:clrScheme>'
    '<a:fontScheme name="Minimal"><a:majorFont><a:latin typeface="Arial"/><a:ea typeface="Noto Sans CJK SC"/><a:cs typeface=""/></a:majorFont>'
    '<a:minorFont><a:latin typeface="Arial"/><a:ea typeface="Noto Sans CJK SC"/><a:cs typeface=""/></a:minorFont></a:fontScheme>'
    '<a:fmtScheme name="Minimal"><a:fillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
    '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:fillStyleLst>'
    '<a:lnStyleLst><a:ln><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln>'
    '<a:ln><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln>'
    '<a:ln><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln></a:lnStyleLst>'
    '<a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle>'
    '<a:effectStyle><a:effectLst/></a:effectStyle><a:effectStyle><a:effectLst/></a:effectStyle></a:effectStyleLst>'
    '<a:bgFillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
    '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:bgFillStyleLst>'
    '</a:fmtScheme></a:themeElements></a:theme>'
)


def build(spec, out_path):
    meta = spec.get("deck_meta", {})
    slides = spec.get("slides", [])
    font_latin = meta.get("font_latin", "Arial")
    font_ea = meta.get("font_ea", "Noto Sans CJK SC")

    tmp = out_path + ".tmpdir"
    if os.path.exists(tmp):
        shutil.rmtree(tmp)
    os.makedirs(os.path.join(tmp, "ppt", "slides", "_rels"), exist_ok=True)
    os.makedirs(os.path.join(tmp, "ppt", "_rels"), exist_ok=True)
    os.makedirs(os.path.join(tmp, "ppt", "slideLayouts", "_rels"), exist_ok=True)
    os.makedirs(os.path.join(tmp, "ppt", "slideMasters", "_rels"), exist_ok=True)
    os.makedirs(os.path.join(tmp, "ppt", "notesSlides", "_rels"), exist_ok=True)
    os.makedirs(os.path.join(tmp, "ppt", "media"), exist_ok=True)
    os.makedirs(os.path.join(tmp, "ppt", "theme"), exist_ok=True)
    os.makedirs(os.path.join(tmp, "_rels"), exist_ok=True)

    overrides = []
    slide_id_entries = []
    pres_rels = ['<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/>']

    for idx, sl in enumerate(slides, start=1):
        layout = sl.get("layout", "bullets")
        tsize = sl.get("title_size", 28)
        bsize = sl.get("body_size", 18)
        shapes = []
        slide_rels = ['<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>']
        img_rel = 2

        # page number footer
        shapes.append(_txbox("pageno", 12.45, 7.05, 0.6, 0.35,
                             [_p(str(idx), 10, color="808080", align="r",
                                 font_latin=font_latin, font_ea=font_ea, space_after=0)],
                             wrap="none", anchor="t"))

        if layout in ("title", "closing"):
            shapes.append(_txbox("title", 1.0, 2.7, 11.33, 1.3,
                                 [_p(sl.get("title", ""), tsize + 8, bold=True, color="2B3A55", align="ctr",
                                     font_latin=font_latin, font_ea=font_ea, space_after=10)],
                                 wrap="square", anchor="ctr"))
            if sl.get("subtitle"):
                shapes.append(_txbox("subtitle", 1.0, 4.0, 11.33, 1.4,
                                     [_p(line, 16, color="444444", align="ctr",
                                         font_latin=font_latin, font_ea=font_ea, space_after=4)
                                      for line in (sl.get("subtitle") if isinstance(sl.get("subtitle"), list) else [sl.get("subtitle")])],
                                     wrap="square", anchor="t"))
        elif layout == "section":
            shapes.append(_txbox("section", 1.0, 3.0, 11.33, 1.5,
                                 [_p(sl.get("title", ""), 34, bold=True, color="2B5BA8", align="ctr",
                                     font_latin=font_latin, font_ea=font_ea, space_after=0)],
                                 wrap="square", anchor="ctr"))
        elif layout in ("bullets", "bullets+figure", "two-col", "table", "figure"):
            tw = 12.13
            shapes.append(_txbox("title", 0.6, 0.35, tw, 0.9,
                                 [_p(sl.get("title", ""), tsize, bold=True, color="2B3A55",
                                     font_latin=font_latin, font_ea=font_ea, space_after=0)],
                                 wrap="square", anchor="t"))
            fig = sl.get("figure")
            if fig and fig.get("path") and layout in ("bullets+figure", "figure"):
                fpath = fig["path"]
                dims = png_size(fpath) or jpg_size(fpath) or (1600, 1200)
                if layout == "figure":
                    bx, by, bw, bh = 1.2, 1.35, 10.9, 5.1
                    bw_pts, bh_pts = _contain_fit(dims[0] / 96.0, dims[1] / 96.0, bw, bh)
                    fx = bx + (bw - bw_pts) / 2
                    fy = by + (bh - bh_pts) / 2
                    shapes.append(_pic("rId%d" % img_rel, fx, fy, bw_pts, bh_pts))
                    slide_rels.append('<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/img%d%s"/>' % (img_rel, idx, os.path.splitext(fpath)[1].lower()))
                    shutil.copyfile(fpath, os.path.join(tmp, "ppt", "media", "img%d%s" % (idx, os.path.splitext(fpath)[1].lower())))
                    img_rel += 1
                    if fig.get("caption"):
                        shapes.append(_txbox("caption", 1.2, 6.5, 10.9, 0.5,
                                             [_p(fig["caption"], 11, italic=True, color="555555", align="ctr",
                                                 font_latin=font_latin, font_ea=font_ea, space_after=0)],
                                             wrap="square", anchor="t"))
                else:
                    fx, fy, fw, fh = 8.35, 1.45, 4.35, 4.6
                    bw_pts, bh_pts = _contain_fit(dims[0] / 96.0, dims[1] / 96.0, fw, fh)
                    fx2 = fx + (fw - bw_pts) / 2
                    shapes.append(_pic("rId%d" % img_rel, fx2, fy, bw_pts, bh_pts))
                    slide_rels.append('<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/img%d%s"/>' % (img_rel, idx, os.path.splitext(fpath)[1].lower()))
                    shutil.copyfile(fpath, os.path.join(tmp, "ppt", "media", "img%d%s" % (idx, os.path.splitext(fpath)[1].lower())))
                    img_rel += 1
                    if fig.get("caption"):
                        shapes.append(_txbox("caption", fx, fy + fh + 0.08, fw, 0.75,
                                             [_p(fig["caption"], 10, italic=True, color="555555",
                                                 font_latin=font_latin, font_ea=font_ea, space_after=0)],
                                             wrap="square", anchor="t"))
                    tw = 7.5
            if layout == "table":
                rows = sl.get("table", {}).get("rows", sl.get("rows", [[""]]))
                shapes.append(_tbl(rows, 0.7, 1.5, 11.9, 4.8, size=sl.get("body_size", 13)))
            elif layout == "two-col":
                cols = sl.get("columns", [[], []])
                colw = 5.85
                for ci, col in enumerate(cols[:2]):
                    cx = 0.6 + ci * (colw + 0.35)
                    paras = [_p(b, bsize, bullet=True, font_latin=font_latin, font_ea=font_ea) for b in col]
                    shapes.append(_txbox("col%d" % ci, cx, 1.45, colw, 5.3, paras, wrap="square", anchor="t"))
            else:
                paras = []
                for b in sl.get("bullets", []):
                    if isinstance(b, dict):
                        paras.append(_p(b.get("text", ""), b.get("size", bsize), bullet=b.get("bullet", True),
                                        bold=b.get("bold", False), color=b.get("color", "1A1A1A"),
                                        font_latin=font_latin, font_ea=font_ea))
                    else:
                        paras.append(_p(b, bsize, bullet=True, font_latin=font_latin, font_ea=font_ea))
                shapes.append(_txbox("body", 0.6, 1.45, tw, 5.3, paras, wrap="square", anchor="t"))

        slide_path = os.path.join(tmp, "ppt", "slides", "slide%d.xml" % idx)
        with open(slide_path, "w", encoding="utf-8") as f:
            f.write(_slide_xml(shapes))
        if sl.get("notes"):
            with open(os.path.join(tmp, "ppt", "notesSlides", "notesSlide%d.xml" % idx), "w", encoding="utf-8") as f:
                f.write(_notes_xml(sl["notes"]))
            with open(os.path.join(tmp, "ppt", "notesSlides", "_rels", "notesSlide%d.xml.rels" % idx), "w", encoding="utf-8") as f:
                f.write('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="../slides/slide%d.xml"/>'
                        "</Relationships>" % idx)
            # link slide -> notesSlide so PowerPoint actually shows the note
            slide_rels.append('<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesSlide" Target="../notesSlides/notesSlide%d.xml"/>' % (img_rel, idx))
            img_rel += 1
            overrides.append('<Override PartName="/ppt/notesSlides/notesSlide%d.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.notesSlide+xml"/>' % idx)
        with open(os.path.join(tmp, "ppt", "slides", "_rels", "slide%d.xml.rels" % idx), "w", encoding="utf-8") as f:
            f.write('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                    + "".join(slide_rels) + "</Relationships>")
        overrides.append('<Override PartName="/ppt/slides/slide%d.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>' % idx)
        slide_id_entries.append('<p:sldId id="%d" r:id="rId%d"/>' % (255 + idx, idx + 1))
        pres_rels.append('<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide%d.xml"/>' % (idx + 1, idx))

    with open(os.path.join(tmp, "[Content_Types].xml"), "w", encoding="utf-8") as f:
        f.write(CONTENT_TYPES % "".join(overrides))
    with open(os.path.join(tmp, "_rels", ".rels"), "w", encoding="utf-8") as f:
        f.write(ROOT_RELS)
    with open(os.path.join(tmp, "ppt", "presentation.xml"), "w", encoding="utf-8") as f:
        f.write(PRESENTATION.replace("%SLIDES%", "".join(slide_id_entries)))
    with open(os.path.join(tmp, "ppt", "_rels", "presentation.xml.rels"), "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                + "".join(pres_rels) + "</Relationships>")
    with open(os.path.join(tmp, "ppt", "slideMasters", "slideMaster1.xml"), "w", encoding="utf-8") as f:
        f.write(SLIDE_MASTER)
    with open(os.path.join(tmp, "ppt", "slideMasters", "_rels", "slideMaster1.xml.rels"), "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>'
                '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/>'
                "</Relationships>")
    with open(os.path.join(tmp, "ppt", "slideLayouts", "slideLayout1.xml"), "w", encoding="utf-8") as f:
        f.write(SLIDE_LAYOUT)
    with open(os.path.join(tmp, "ppt", "slideLayouts", "_rels", "slideLayout1.xml.rels"), "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/>'
                "</Relationships>")
    with open(os.path.join(tmp, "ppt", "theme", "theme1.xml"), "w", encoding="utf-8") as f:
        f.write(THEME)

    if os.path.exists(out_path):
        os.remove(out_path)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _dirs, files in os.walk(tmp):
            for fn in files:
                full = os.path.join(root, fn)
                rel = os.path.relpath(full, tmp)
                z.write(full, rel.replace(os.sep, "/"))
    shutil.rmtree(tmp)
    return out_path


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: pptx_minimal.py spec.json out.pptx（参数缺失已如实登记，退出码 0）")
        sys.exit(0)
    with open(sys.argv[1], "r", encoding="utf-8") as f:
        spec = json.load(f)
    build(spec, sys.argv[2])
    print("written:", sys.argv[2])
