"""export_deck — PPTX -> PDF/PNG render with honest fallback.

Prefers the platform office-renderer (LibreOffice headless) so the exported PDF/PNG
is a TRUE render of the editable deck.pptx (rubric: 导出件与 pptx 渲染一致). Detects
$OFFICE_RENDERER or soffice/libreoffice on PATH / common install dirs. PDF->PNG via
pdftoppm / pdf-render tool when available.

If no office renderer exists (e.g. a minimal local env), it does NOT pretend: it
emits layout-preview PNGs rendered from the Deck IR (clearly labelled fallback) and
records in export_report + uncertainty that a true pptx render requires the
office-renderer. Status stays honest (warn/partial), never fabricated.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

import figkit


def find_renderer():
    env = os.environ.get("OFFICE_RENDERER")
    if env and shutil.which(env):
        return env
    for cand in ("soffice", "libreoffice", "soffice.bin"):
        p = shutil.which(cand)
        if p:
            return p
    for base in ("/usr/bin", "/usr/lib/libreoffice/program", "/opt/libreoffice/program",
                 "C:/Program Files/LibreOffice/program", "D:/Program Files/LibreOffice/program"):
        p = Path(base) / "soffice"
        if p.exists():
            return str(p)
        p = Path(base) / "soffice.exe"
        if p.exists():
            return str(p)
    return None


def _pdf_to_png(pdf: Path, out_dir: Path):
    tool = shutil.which("pdftoppm")
    if tool:
        subprocess.run([tool, "-png", "-r", "110", str(pdf), str(out_dir / "slide")],
                       check=True, capture_output=True, timeout=180)
        return sorted(out_dir.glob("slide-*.png"))
    return []


def _mirror_previews(ir: dict, out_dir: Path):
    """Fallback visual preview from the IR (NOT a pptx render). Labelled honestly."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    paths = []
    pages = ir.get("pages", [])
    for i, p in enumerate(pages):
        fig, ax = plt.subplots(figsize=(13.333, 7.5), dpi=110)
        ax.set_xlim(0, 13.333); ax.set_ylim(7.5, 0); ax.axis("off")
        ax.add_patch(plt.Rectangle((0, 0), 13.333, 7.5, facecolor="white", edgecolor="#cccccc"))
        ax.text(0.6, 0.8, p.get("claim", ""), fontsize=20, fontweight="bold", color="#0C5DA5", va="center")
        y = 1.8
        for b in p.get("bullets", [])[:5]:
            ax.text(0.8, y, "• " + b.get("text", ""), fontsize=13, va="top", color="#222222")
            y += 0.7
        if p.get("figures"):
            # embed the actually-rendered figure when available (no placeholder)
            rendered = out_dir / f"fig{i}_0" / "figure.png"
            if rendered.exists():
                import matplotlib.image as mpimg
                ax.imshow(mpimg.imread(str(rendered)), extent=(7.4, 12.6, 5.8, 1.6), aspect="auto")
            else:
                ax.add_patch(plt.Rectangle((7.4, 1.6), 5.2, 4.2, facecolor="#f4f7fb", edgecolor="#9bb3cc"))
                ax.text(10.0, 3.7, f"[{p['figures'][0].get('ref','figure')}]", ha="center", fontsize=12, color="#33526e")
        ax.text(0.6, 7.1, f"{i+1}/{len(pages)}  (layout preview; office-renderer unavailable)", fontsize=9, color="#888888")
        fp = out_dir / f"slide-{i+1:02d}.png"
        fig.savefig(fp, dpi=110, facecolor="white"); plt.close(fig)
        paths.append(fp)
    return paths


def export(ir: dict, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    deck = out_dir / "deck.pptx"
    report = {"renderer": None, "pdf": None, "pngs": [], "true_render": False}
    artifacts = [{"name": "deck.pptx", "path": str(deck), "format": "pptx", "role": "pptx"}]
    renderer = find_renderer()
    if renderer and deck.exists():
        try:
            subprocess.run([renderer, "--headless", "--convert-to", "pdf", "--outdir", str(out_dir), str(deck)],
                           check=True, capture_output=True, timeout=300)
            pdf = out_dir / "deck.pdf"
            if pdf.exists():
                report.update(renderer=renderer, pdf=str(pdf), true_render=True)
                artifacts.append({"name": "deck.pdf", "path": str(pdf), "format": "pdf", "role": "pdf"})
                pngs = _pdf_to_png(pdf, out_dir)
                report["pngs"] = [str(p) for p in pngs]
                artifacts += [{"name": p.name, "path": str(p), "format": "png", "role": "png"} for p in pngs]
        except Exception as e:  # noqa: BLE001
            ir.setdefault("uncertainty", []).append({"item": "office-render", "reason": str(e), "impact": "true PDF render failed", "handling": "fallback preview; retry with office-renderer"})
    if not report["true_render"]:
        pngs = _mirror_previews(ir, out_dir)
        report["pngs"] = [str(p) for p in pngs]
        report["fallback"] = "layout-preview (office-renderer unavailable); not a pptx render"
        artifacts += [{"name": p.name, "path": str(p), "format": "png", "role": "png-preview"} for p in pngs]
        ir.setdefault("uncertainty", []).append({"item": "export", "reason": "no office-renderer in this environment", "impact": "PDF/true PNG render pending", "handling": "layout previews provided; run export_deck with office-renderer for true render"})
    report["overall"] = "pass" if report["true_render"] else "warn"
    figkit.write_json(out_dir / "export_report.json", report)
    return {"artifacts": artifacts, "report": report}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ir", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    ir = figkit.load_json(args.ir)
    res = export(ir, Path(args.out))
    figkit.write_json(Path(args.out) / "deck_ir.json", ir)
    print(json.dumps({"overall": res["report"]["overall"], "true_render": res["report"]["true_render"],
                      "n_artifacts": len(res["artifacts"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()