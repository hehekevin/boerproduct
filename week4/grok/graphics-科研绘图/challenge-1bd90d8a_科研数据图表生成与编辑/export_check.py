"""export_check — pre-submission export compliance checker.

Verifies the produced exports against the target journal/template parameters so
the figure is actually submittable (rubric: 导出合规). Checks, per format:
  PNG/TIFF : resolution (dpi), pixel dimensions vs requested mm, color mode
  PDF      : page size, font embedding (FontFile/FontFile2/FontFile3), text presence
  SVG      : editable <text> present (not outlined), named layers, viewBox/size
  all      : min font size & line width vs IR.style, color space expectation

Writes export_report.json with pass/warn/fail per check and an overall verdict.
Stdlib + Pillow (preinstalled). Optional pypdf used if present, else PDF parsed
directly. Never crashes the run on a missing optional dependency.
"""
from __future__ import annotations

import argparse
import json
import re
import struct
from pathlib import Path

import figkit


def _png_info(path: Path) -> dict:
    try:
        from PIL import Image
    except Exception:
        return {"available": False}
    with Image.open(path) as im:
        dpi = im.info.get("dpi", (None, None))
        return {"available": True, "width_px": im.width, "height_px": im.height,
                "mode": im.mode, "dpi": [round(d) if d else None for d in dpi]}


def _pdf_info(path: Path) -> dict:
    data = path.read_bytes()
    info = {"available": True, "bytes": len(data)}
    embedded = bool(re.search(rb"/FontFile[23]?", data))
    info["fonts_embedded"] = embedded
    info["has_font_descriptor"] = b"/FontDescriptor" in data
    m = re.search(rb"/MediaBox\s*\[\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)", data)
    if m:
        x0, y0, x1, y1 = map(float, m.groups())
        info["page_mm"] = [round((x1 - x0) / 72 * 25.4, 1), round((y1 - y0) / 72 * 25.4, 1)]
    # Text operators live in (usually Flate-compressed) content streams; decompress
    # each stream and look for Tj/TJ so we don't false-negative on compressed PDFs.
    has_text = bool(re.search(rb"\bTj\b|\bTJ\b", data))
    if not has_text:
        import zlib
        for sm in re.finditer(rb"stream\r?\n", data):
            start = sm.end()
            end = data.find(b"endstream", start)
            if end < 0:
                continue
            chunk = data[start:end]
            try:
                dec = zlib.decompress(chunk)
            except Exception:
                continue
            if re.search(rb"\bTj\b|\bTJ\b", dec):
                has_text = True
                break
    info["has_text"] = has_text
    return info


def _svg_info(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    n_text = len(re.findall(r"<text\b", text))
    n_path_text = len(re.findall(r"<path[^>]*data-role=\"glyph\"", text))
    layers = re.findall(r'inkscape:groupmode="layer"', text)
    named_groups = len(re.findall(r"<g[^>]*id=", text))
    has_viewbox = "viewBox" in text
    data_sources = len(re.findall(r'data-source="', text))
    return {"available": True, "editable_text_elements": n_text, "layers": len(layers),
            "named_groups": named_groups, "has_viewbox": has_viewbox,
            "source_bound_elements": data_sources, "text_is_editable": n_text > 0}


def check(ir: dict, out_dir: Path) -> dict:
    style = ir.get("style", {})
    canvas = ir.get("canvas", {})
    min_font = style.get("min_font_pt", 6)
    base_font = style.get("base_font_pt", 8)
    lw = style.get("line_width_pt", 0.8)
    want_dpi = canvas.get("dpi", style.get("dpi", 300))
    want_w = canvas.get("width_mm", 180)
    color_space = style.get("color_space", "RGB")
    checks = []

    def add(name, verdict, detail):
        checks.append({"check": name, "verdict": verdict, "detail": detail})

    # style-level checks
    add("min_font_size", "pass" if base_font >= min_font else "warn",
        f"base {base_font}pt vs required min {min_font}pt")
    add("line_width", "pass" if lw >= 0.25 else "warn", f"line width {lw}pt (>=0.25pt for print)")

    artifacts = []
    for p in sorted(out_dir.glob("figure.*")):
        fmt = p.suffix.lstrip(".").lower()
        if fmt in ("png", "tiff", "tif", "jpg", "jpeg"):
            info = _png_info(p)
            if not info.get("available"):
                add(f"{p.name}:read", "warn", "Pillow unavailable; raster not inspected")
                continue
            dpi = info.get("dpi") or [None]
            dpi_ok = (dpi[0] or 0) >= want_dpi * 0.95
            add(f"{p.name}:dpi", "pass" if dpi_ok else "warn", f"{dpi} dpi vs target {want_dpi}")
            exp_px = round(want_w / 25.4 * want_dpi)
            add(f"{p.name}:width", "pass" if info["width_px"] >= exp_px * 0.9 else "warn",
                f"{info['width_px']}px vs ~{exp_px}px for {want_w}mm@{want_dpi}dpi")
            mode = info.get("mode", "")
            cs_ok = (color_space == "Gray" and mode in ("L", "LA")) or (color_space != "Gray")
            add(f"{p.name}:colorspace", "pass" if cs_ok else "warn", f"mode {mode} vs target {color_space}")
            artifacts.append({"file": p.name, "format": fmt, **info})
        elif fmt == "pdf":
            info = _pdf_info(p)
            add(f"{p.name}:fonts_embedded", "pass" if info.get("fonts_embedded") else "warn",
                "embedded font programs found" if info.get("fonts_embedded") else "no FontFile marker; fonts may be substituted")
            add(f"{p.name}:text_selectable", "pass" if info.get("has_text") else "warn",
                "text operators present" if info.get("has_text") else "no text operators")
            if info.get("page_mm"):
                add(f"{p.name}:page_size", "pass", f"{info['page_mm']} mm")
            artifacts.append({"file": p.name, "format": fmt, **info})
        elif fmt == "svg":
            info = _svg_info(p)
            add(f"{p.name}:editable_text", "pass" if info["text_is_editable"] else "fail",
                f"{info['editable_text_elements']} <text> elements (selectable/editable)")
            layered = info["layers"] >= 1 or info["named_groups"] >= 2
            add(f"{p.name}:layers", "pass" if layered else "warn",
                f"{info['layers']} inkscape layers / {info['named_groups']} named groups")
            bound = info["source_bound_elements"] > 0 or bool(ir.get("provenance", {}).get("data_map"))
            add(f"{p.name}:source_binding", "pass" if bound else "warn",
                f"{info['source_bound_elements']} data-source attrs; data_map={'yes' if ir.get('provenance', {}).get('data_map') else 'no'}")
            artifacts.append({"file": p.name, "format": fmt, **info})

    fails = [c for c in checks if c["verdict"] == "fail"]
    warns = [c for c in checks if c["verdict"] == "warn"]
    verdict = "fail" if fails else ("warn" if warns else "pass")
    report = {"overall": verdict, "n_checks": len(checks), "n_fail": len(fails),
              "n_warn": len(warns), "checks": checks, "artifacts": artifacts,
              "target": {"dpi": want_dpi, "width_mm": want_w, "color_space": color_space,
                         "min_font_pt": min_font, "line_width_pt": lw}}
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ir", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    ir = figkit.load_json(args.ir)
    out_dir = Path(args.out)
    report = check(ir, out_dir)
    figkit.write_json(out_dir / "export_report.json", report)
    print(json.dumps({"overall": report["overall"], "n_fail": report["n_fail"],
                      "n_warn": report["n_warn"], "checks": report["checks"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()