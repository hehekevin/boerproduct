#!/usr/bin/env python3
"""render_export.py — 渲染 + 批量一致性 + 图表适配 + 导出校验（周4新增，纯标准库）。

直击题面列举的失败模式，全部机器判定：
  批量一致性   页码逐页正确且连续、标题字号阶梯(≤2档)、标题起始位置跨页一致、
              正文/图注字号落在阶梯内、页数一致性
  图表适配     嵌入框宽高比 vs 源图像素比 -> 拉伸变形抓捕(distortion>5%)；
              pic 引用数 vs ppt/media 文件数 -> 图片丢失抓捕
  图号引用     图注编号(Fig.N) 与正文引用(Fig.N) 互相错位 -> 引用错位抓捕
  导出渲染     pptx->pdf(soffice/PowerPoint COM) -> 逐页 PNG(pdftoppm/mutool/gs/fitz)，
              pdf 页数 vs pptx 页数；无渲染器如实记 pptx_only_no_renderer

审计部分（--audit-only）无渲染器也可跑（raw-xml 解析，不依赖 python-pptx）。
退出码恒 0；一切结论走 JSON（export_audit.json）。

用法: python3 render_export.py deck.pptx --outdir /app/output/previews [--audit-only] [--out export_audit.json]
"""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from xml.etree import ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pptx_minimal import png_size, jpg_size  # noqa: E402

NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS_P = "http://schemas.openxmlformats.org/presentationml/2006/main"
NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
EMU_IN = 914400
LADDER_SIZES = {28, 24, 18, 16, 14, 12, 11, 10}  # 标题+正文字号阶梯（周4显式枚举）
TOL_IN = 0.05
DISTORT_TOL = 0.05


def _in(v):
    try:
        return round(int(v) / EMU_IN, 3)
    except Exception:
        return None


def audit_slide_shapes(path):
    """raw-xml 逐页抽取：文本形状(text,x,y,cx,cy,sz,color) + 图片(rel,cx,cy)。"""
    z = zipfile.ZipFile(path)
    slide_names = sorted((n for n in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)),
                         key=lambda n: int(re.search(r"(\d+)", n).group(1)))
    slides = []
    for n in slide_names:
        root = ET.fromstring(z.read(n))
        shapes, pics = [], []
        for sp in root.iter():
            tag = sp.tag.split("}")[-1]
            if tag == "sp":
                texts = [t.text or "" for t in sp.iter("{%s}t" % NS_A)]
                txt = "".join(texts).strip()
                if not txt:
                    continue
                xfrm = sp.find("{%s}spPr/{%s}xfrm" % (NS_P, NS_A))
                x = y = cx = cy = None
                if xfrm is not None:
                    off, ext = xfrm.find("{%s}off" % NS_A), xfrm.find("{%s}ext" % NS_A)
                    if off is not None:
                        x, y = _in(off.get("x")), _in(off.get("y"))
                    if ext is not None:
                        cx, cy = _in(ext.get("cx")), _in(ext.get("cy"))
                szs = set()
                for rpr in sp.iter("{%s}rPr" % NS_A):
                    if rpr.get("sz"):
                        szs.add(int(rpr.get("sz")) / 100)
                shapes.append({"text_head": txt[:60], "text_full": txt, "x": x, "y": y,
                               "cx": cx, "cy": cy, "sizes": sorted(szs)})
            elif tag == "pic":
                blip = sp.find(".//{%s}blip" % NS_A)
                rel = blip.get("{%s}embed" % NS_R) if blip is not None else None
                ext = sp.find("{%s}spPr/{%s}xfrm/{%s}ext" % (NS_P, NS_A, NS_A))
                cx = cy = None
                if ext is not None:
                    cx, cy = _in(ext.get("cx")), _in(ext.get("cy"))
                pics.append({"rel": rel, "cx": cx, "cy": cy})
        # rels: rel id -> media 文件名
        rel_name = "ppt/slides/_rels/%s.rels" % os.path.basename(n)
        rels = {}
        if rel_name in z.namelist():
            rroot = ET.fromstring(z.read(rel_name))
            for rel in rroot:
                rels[rel.get("Id")] = rel.get("Target")
        for p in pics:
            tgt = rels.get(p["rel"])
            if tgt:
                media = "ppt/" + tgt.replace("../", "")
                p["media"] = media
                if media in z.namelist():
                    with z.open(media) as fh:
                        head = fh.read()
                    size = png_size_from_bytes(head) or jpg_size_from_bytes(head)
                    p["src_px"] = size
        slides.append({"part": n, "shapes": shapes, "pics": pics})
    media_files = [n for n in z.namelist() if n.startswith("ppt/media/")]
    return slides, media_files


def png_size_from_bytes(head):
    try:
        if head[:8] == b"\x89PNG\r\n\x1a\n" and len(head) >= 24:
            return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")
    except Exception:
        pass
    return None


def jpg_size_from_bytes(data):
    try:
        i = 2
        while i < len(data) - 9:
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


def consistency_audit(slides, media_files):
    """批量一致性 + 图表适配 + 图号引用机器审计。"""
    report = {"checks": {}, "fail": 0, "warn": 0, "per_slide": []}
    n = len(slides)

    # 1) 页码批量一致性：每页页脚文本 == 页序号
    pn_ok, pn_detail = 0, []
    for i, sl in enumerate(slides, 1):
        texts = [s["text_full"] for s in sl["shapes"]]
        hit = str(i) in texts
        pn_ok += bool(hit)
        pn_detail.append({"no": i, "found": hit})
    report["checks"]["page_numbers"] = {
        "found": pn_ok, "total": n, "mode": "per_slide_footer",
        "ok": pn_ok == n or pn_ok == 0,  # 母版统一出页码时页内无文本属正常
        "detail": pn_detail}
    if pn_ok not in (0, n):
        report["checks"]["page_numbers"]["ok"] = False
        report["warn"] += 1

    # 2) 标题字号阶梯：内容页顶部形状字号跨页一致且 ≤2 档
    title_sizes, title_xs, body_sizes = [], [], []
    for i, sl in enumerate(slides, 1):
        top = min((s for s in sl["shapes"] if s["y"] is not None and s["sizes"]),
                  key=lambda s: s["y"], default=None)
        if top and top["y"] is not None and top["y"] < 1.3:
            title_sizes.append((i, tuple(top["sizes"])))
            title_xs.append((i, top["x"]))
        for s in sl["shapes"]:
            if s["y"] is not None and 1.3 <= s["y"] < 6.9:
                body_sizes.extend(s["sizes"])
    distinct_titles = sorted({sz for _, szs in title_sizes for sz in szs})
    ok_titles = len(distinct_titles) <= 2
    report["checks"]["title_size_ladder"] = {
        "values": distinct_titles, "pages": [p for p, _ in title_sizes], "ok": ok_titles,
        "note": "标题字号跨页 >2 档即批量不一致"}
    if not ok_titles:
        report["fail"] += 1
    xs = [x for _, x in title_xs if x is not None]
    ok_x = len(set(xs)) <= 1 or (xs and max(xs) - min(xs) <= TOL_IN)
    report["checks"]["title_position"] = {"xs": sorted(set(xs)), "ok": bool(ok_x),
                                          "note": "标题起始 x 跨页漂移 >%.2f in 即不一致" % TOL_IN}
    if not ok_x and len(set(xs)) > 1:
        report["warn"] += 1

    # 3) 正文字号阶梯合规（不在阶梯内的字号=压字号/越级硬塞）
    #    >20pt 属标题/节标题类（28/34/36 等），不进正文阶梯校验
    body_class = sorted({s for s in body_sizes if s <= 20})
    title_class = sorted({s for s in body_sizes if s > 20})
    off_ladder = sorted({s for s in body_class if s not in LADDER_SIZES})
    report["checks"]["body_size_ladder"] = {
        "ladder": sorted(LADDER_SIZES), "body_sizes": body_class,
        "title_class_sizes": title_class,
        "off_ladder": off_ladder, "ok": not off_ladder,
        "note": "正文阶梯 18→10（>20pt 归标题类不计入）；10pt 仍溢出应删内容而非压到阶梯外"}
    if off_ladder:
        report["fail"] += 1

    # 4) 图号引用错位：图注编号 vs 正文引用 必须互相配对
    cap_ids, ref_ids = [], []
    for i, sl in enumerate(slides, 1):
        for s in sl["shapes"]:
            m_cap = re.findall(r"Fig(?:ure)?\.?\s*(\d+)", s["text_full"])
            y = s.get("y")
            if m_cap and y is not None and y > 6.0:
                cap_ids.extend((i, int(v)) for v in m_cap)
            elif m_cap:
                ref_ids.extend((i, int(v)) for v in m_cap)
    cap_set, ref_set = {v for _, v in cap_ids}, {v for _, v in ref_ids}
    unreferenced = sorted(cap_set - ref_set)
    dangling = sorted(ref_set - cap_set)
    report["checks"]["figure_ref_alignment"] = {
        "captions": sorted(cap_set), "references": sorted(ref_set),
        "caption_no_reference": unreferenced, "reference_no_caption": dangling,
        "ok": not dangling,
        "note": "正文引用了不存在的图号=错位（图注未被正文引用仅 warn，允许备用图）"}
    if dangling:
        report["fail"] += 1
    if unreferenced:
        report["warn"] += 1

    # 5) 图片拉伸变形：嵌入框宽高比 vs 源图像素比
    distort = []
    pic_total = 0
    for i, sl in enumerate(slides, 1):
        for p in sl["pics"]:
            pic_total += 1
            if not p.get("cx") or not p.get("cy") or not p.get("src_px"):
                continue
            w, h = p["src_px"]
            if not w or not h:
                continue
            r_box, r_src = p["cx"] / p["cy"], w / h
            if abs(r_box / r_src - 1) > DISTORT_TOL:
                distort.append({"slide": i, "media": p.get("media"),
                                "ratio_box": round(r_box, 3), "ratio_src": round(r_src, 3)})
    report["checks"]["image_aspect"] = {
        "pics": pic_total, "checked": pic_total - len(distort), "distorted": distort,
        "tolerance": DISTORT_TOL, "ok": not distort,
        "note": "嵌入框比例与源图比例偏差 >%.0f%% 即拉伸变形（图表禁止非等比缩放）" % (DISTORT_TOL * 100)}
    if distort:
        report["fail"] += 1

    # 6) 图片丢失：pic 引用 vs media 实际文件
    missing_media = [p.get("media") for sl in slides for p in sl["pics"]
                     if p.get("media") and p.get("media") not in media_files]
    report["checks"]["image_loss"] = {"media_files": len(media_files), "pic_refs": pic_total,
                                      "missing": missing_media, "ok": not missing_media}
    if missing_media:
        report["fail"] += 1

    report["summary"] = {"fail": report["fail"], "warn": report["warn"],
                         "verdict": "pass" if report["fail"] == 0 else "fail"}
    return report


# ---- 渲染（沿用 week3 已验证链路，退出码改恒 0） ----
def which_any(names):
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    return None


def soffice_pdf(pptx, outdir):
    soffice = which_any(["soffice", "libreoffice", "loffice"])
    if not soffice:
        for pat in (r"C:\Program Files\LibreOffice\program\soffice.exe",
                    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
                    "/usr/bin/soffice", "/usr/local/bin/soffice", "/opt/libreoffice/program/soffice"):
            if os.path.exists(pat):
                soffice = pat
                break
    if not soffice:
        return None, "no soffice/libreoffice binary"
    try:
        r = subprocess.run([soffice, "--headless", "--norestore", "--convert-to", "pdf",
                            "--outdir", outdir, os.path.abspath(pptx)],
                           capture_output=True, timeout=180, text=True)
        pdf = os.path.join(outdir, os.path.splitext(os.path.basename(pptx))[0] + ".pdf")
        if os.path.exists(pdf):
            return pdf, "soffice ok (rc=%s)" % r.returncode
        return None, "soffice rc=%s stderr=%s" % (r.returncode, (r.stderr or "")[:300])
    except Exception as e:
        return None, "soffice failed: %s" % e


def pdf_page_count(pdf):
    try:
        with open(pdf, "rb") as f:
            data = f.read()
        m = re.findall(rb"/Type\s*/Page[^s]", data)
        if m:
            return len(m)
        m = re.findall(rb"/Count\s+(\d+)", data)
        if m:
            return max(int(v) for v in m)
    except Exception:
        pass
    return None


def pngs_from_pdf(pdf, outdir, stem):
    tool = which_any(["pdftoppm", "mutool", "gs"])
    if tool:
        base = os.path.join(outdir, stem)
        try:
            if os.path.basename(tool) == "pdftoppm":
                subprocess.run([tool, "-png", "-r", "110", pdf, base], capture_output=True, timeout=180)
            elif os.path.basename(tool) == "mutool":
                subprocess.run([tool, "draw", "-o", base + "-page%d.png", "-r", "110", pdf],
                               capture_output=True, timeout=180)
            else:
                subprocess.run([tool, "-sDEVICE=png16m", "-r110", "-o", base + "-page-%03d.png", pdf],
                               capture_output=True, timeout=180)
            pngs = sorted(glob.glob(base + "*.png"))
            if pngs:
                return pngs, os.path.basename(tool)
        except Exception:
            pass
    try:
        import fitz
        doc = fitz.open(pdf)
        pngs = []
        for i, page in enumerate(doc, 1):
            pix = page.get_pixmap(dpi=110)
            out = os.path.join(outdir, "%s-%02d.png" % (stem, i))
            pix.save(out)
            pngs.append(out)
        return pngs, "pymupdf"
    except Exception:
        pass
    return [], None


def render(pptx, outdir, log):
    result = {"pdf": None, "pngs": [], "png_tool": None}
    pdf, note = soffice_pdf(pptx, outdir)
    log["steps"].append({"step": "pdf", "tool": "soffice", "ok": bool(pdf), "note": note})
    result["pdf"] = pdf
    if pdf:
        pngs, tool = pngs_from_pdf(pdf, outdir, os.path.splitext(os.path.basename(pptx))[0])
        result["pngs"], result["png_tool"] = pngs, tool
        log["steps"].append({"step": "png", "tool": tool or "none", "ok": bool(pngs), "count": len(pngs)})
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pptx")
    ap.add_argument("--outdir", default=None)
    ap.add_argument("--audit-only", action="store_true", help="跳过渲染，只跑一致性/图表/引用审计")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    outdir = args.outdir or (os.path.splitext(args.pptx)[0] + "_previews")
    out_path = args.out or os.path.join(outdir, "export_audit.json")
    report = {"pptx": args.pptx, "ok": True}

    # 审计部分（无渲染器也可跑）
    try:
        slides, media_files = audit_slide_shapes(args.pptx)
        report["slides"] = len(slides)
        report["consistency"] = consistency_audit(slides, media_files)
    except Exception as e:
        report["ok"] = False
        report["audit_error"] = "%s: %s" % (type(e).__name__, e)
        report["consistency"] = {"checks": {}, "fail": 0, "warn": 0, "summary": {"verdict": "not_run"},
                                 "note": "审计未执行（%s），下游不得宣称已核对一致性" % type(e).__name__}

    # 渲染部分
    if args.audit_only:
        report["render"] = {"status": "skipped_audit_only",
                            "note": "--audit-only 未执行渲染，不得宣称导出已核对"}
    else:
        os.makedirs(outdir, exist_ok=True)
        log = {"steps": []}
        result = render(args.pptx, outdir, log)
        if result["pdf"] and result["pngs"]:
            status = "ok"
        elif result["pdf"]:
            status = "pdf_only_no_png"
        else:
            status = "pptx_only_no_renderer"
        pdf_pages = pdf_page_count(result["pdf"]) if result["pdf"] else None
        export = {"status": status, "pdf": result["pdf"], "pdf_pages": pdf_pages,
                  "pptx_slides": report.get("slides"),
                  "page_count_match": (pdf_pages == report.get("slides")) if pdf_pages else None,
                  "pngs": len(result["pngs"]), "png_tool": result["png_tool"],
                  "outdir": outdir, "steps": log["steps"]}
        if pdf_pages and report.get("slides") and pdf_pages != report["slides"]:
            export["page_count_note"] = "pdf 页数与 pptx 页数不一致，导出可能丢页"
        report["render"] = export

    # 汇总 verdict：审计 fail 或导出异常都如实呈现，退出码恒 0
    verdict_fail = report["consistency"]["summary"].get("fail", 0)
    report["summary"] = {
        "consistency_fail": verdict_fail,
        "render_status": (report.get("render") or {}).get("status"),
        "verdict": "pass" if (verdict_fail == 0 and
                              (report.get("render") or {}).get("status") in ("ok", "skipped_audit_only"))
                   else "fail"}
    try:
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=1)
    except Exception as e:
        print(json.dumps({"ok": False, "error": "write_report_failed: %s" % e}, ensure_ascii=False))
        return 0
    print("export_audit:", json.dumps(report["summary"], ensure_ascii=False), "->", out_path)
    for k, v in report["consistency"].get("checks", {}).items():
        if not v.get("ok", True):
            print("  check", k, json.dumps({kk: v[kk] for kk in v if kk not in ("detail",)}, ensure_ascii=False)[:300])
    return 0


if __name__ == "__main__":
    sys.exit(main())
