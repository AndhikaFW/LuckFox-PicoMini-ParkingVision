#!/usr/bin/env python3
"""Print the flat patterns 1:1 on A4 paper (for a paper mock-up before cutting metal).

    python3 make_print_a4.py      ->  out/cetak_A4_1to1.pdf

* Every part is printed WHOLE on one page (nothing is tiled or split).
  Portrait pages hold the small/narrow parts (packed several per page); parts that are
  wider than a portrait page (the ceiling box) get a landscape page.
* Every part keeps >= 3 mm of white space to the edge of the printable window, so no
  line is clipped; the window itself keeps >= 6.8 mm to the paper edge.
* Every page has a 100 mm scale bar: if it measures 100 mm with a ruler, the print is 1:1.
* Small + marks at every hole centre (prick through the paper with a pin).
* Print at "Actual size" / 100 %. NOT "Fit to page".
"""
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from ezdxf.addons.drawing import Frontend, RenderContext
from ezdxf.addons.drawing.config import BackgroundPolicy, ColorPolicy, Configuration
from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
from matplotlib.backends.backend_pdf import PdfPages
from rectpack import MaxRectsBssf, newPacker

import make_laser_cut as L

MM = 1 / 25.4
MARGIN = 10.0
PAD = 6.0                          # white space around each part (3 mm each side)
LABEL = 5.0                        # label band above each part
CFG = Configuration(background_policy=BackgroundPolicy.WHITE, color_policy=ColorPolicy.COLOR)

# page layouts: page size, content window (left, bottom, width, height) in page millimetres
PORTRAIT = dict(name="portrait", pw=210.0, ph=297.0, left=MARGIN, bottom=23.0, w=190.0, h=264.0)
LANDSCAPE = dict(name="landscape", pw=297.0, ph=210.0, left=MARGIN, bottom=18.0, w=277.0, h=180.0)


def new_page(lay, title, page_no, total):
    pw, ph = lay["pw"], lay["ph"]
    fig = plt.figure(figsize=(pw * MM, ph * MM), dpi=100, facecolor="white")
    ov = fig.add_axes([0, 0, 1, 1])                 # overlay in page millimetres
    ov.set_xlim(0, pw); ov.set_ylim(0, ph); ov.axis("off")
    ov.text(MARGIN, ph - 8.5, title, fontsize=9, va="center", weight="bold")
    ov.text(pw - MARGIN, ph - 8.5, f"hal {page_no}/{total}", fontsize=8, ha="right", va="center")
    y = 9.0                                          # 100 mm scale bar
    ov.plot([MARGIN, MARGIN + 100], [y, y], color="k", lw=0.8)
    for k in range(0, 101, 10):
        h = 2.2 if k % 50 == 0 else 1.2
        ov.plot([MARGIN + k, MARGIN + k], [y - h, y + h], color="k", lw=0.6)
    ov.text(MARGIN + 104, y, "= 100 mm. Ukur dengan penggaris.", fontsize=6.5, va="center")
    if lay["name"] == "portrait":
        ov.text(MARGIN, 15.0, "Cetak 'Ukuran sebenarnya' (100%), BUKAN 'Sesuaikan halaman'.", fontsize=6.5, va="center", weight="bold")
        ov.text(MARGIN, 19.5, "HITAM = potong  |  putus BIRU = lipat  |  + = pusat lubang (tusuk dengan jarum)",
                fontsize=6.2, va="center", color="#444")
    else:
        ov.text(MARGIN, 14.8, "Cetak 'Ukuran sebenarnya' (100%), BUKAN 'Sesuaikan halaman'.   HITAM = potong | putus BIRU = lipat | + = pusat lubang",
                fontsize=6.2, va="center", weight="bold")
    return fig


def window_axes(fig, lay):
    ax = fig.add_axes([lay["left"] / lay["pw"], lay["bottom"] / lay["ph"], lay["w"] / lay["pw"], lay["h"] / lay["ph"]])
    ax.set_xlim(0, lay["w"]); ax.set_ylim(0, lay["h"])
    ax.set_aspect("equal", adjustable="box"); ax.axis("off")
    return ax


def render(ax, doc, lay):
    # finalize=False / adjust_figure=False: ezdxf must NOT rescale the axes or resize the page,
    # otherwise the print is no longer 1:1.
    Frontend(RenderContext(doc), MatplotlibBackend(ax, adjust_figure=False), config=CFG).draw_layout(
        doc.modelspace(), finalize=False)
    ax.set_xlim(0, lay["w"]); ax.set_ylim(0, lay["h"]); ax.set_aspect("equal", adjustable="box")
    pts = [(e.dxf.center.x, e.dxf.center.y) for e in doc.modelspace().query("CIRCLE")]
    if pts:
        ax.plot([p[0] for p in pts], [p[1] for p in pts], "+", color="#c00", ms=3.5, mew=0.5)


def pack(parts, lay):
    """MaxRects packing in tenths of a millimetre. Returns [page_items], each item (part, x, y) in window mm."""
    packer = newPacker(rotation=False, pack_algo=MaxRectsBssf)
    for i, p in enumerate(parts):
        w, h = p.size()
        packer.add_rect(int(round((w + PAD) * 10)), int(round((h + PAD + LABEL) * 10)), rid=i)
    packer.add_bin(int(lay["w"] * 10), int(lay["h"] * 10), count=20)
    packer.pack()
    pages = []
    for abin in packer:
        items = [(parts[r.rid], r.x / 10.0, r.y / 10.0) for r in abin]
        if items:
            pages.append(items)
    placed = sum(len(p) for p in pages)
    assert placed == len(parts), f"{len(parts) - placed} part(s) do not fit the {lay['name']} window"
    return pages


def main():
    L.build_all()
    fits = lambda p, lay: p.size()[0] + PAD <= lay["w"] and p.size()[1] + PAD + LABEL <= lay["h"]
    port = [p for p in L.PARTS if fits(p, PORTRAIT)]
    land = [p for p in L.PARTS if p not in port]
    for p in land:
        assert fits(p, LANDSCAPE), f"{p.key} ({p.size()[0]:.0f} x {p.size()[1]:.0f} mm) fits no A4 orientation"
    plan = [(PORTRAIT, items) for items in pack(sorted(port, key=lambda q: -q.size()[1]), PORTRAIT)]
    if land:
        plan += [(LANDSCAPE, items) for items in pack(land, LANDSCAPE)]

    out = os.path.join(L.OUT, "cetak_A4_1to1.pdf")
    with PdfPages(out) as pdf:
        for i, (lay, items) in enumerate(plan, 1):
            names = ", ".join(q.key for q, _, _ in items)
            fig = new_page(lay, f"Pola potong 1:1  -  {names}", i, len(plan))
            ax = window_axes(fig, lay)
            doc = L.new_doc()
            for q, x, y in items:
                q.draw(doc.modelspace(), x + PAD / 2, y + PAD / 2, label=False)
            render(ax, doc, lay)
            for q, x, y in items:
                w, h = q.size()
                ax.text(x + PAD / 2, y + PAD / 2 + h + 1.2,
                        f"{q.key}  {q.title.split(' (')[0]}  [{q.material.split()[0]} {q.t:g} mm]  {w:.0f} x {h:.0f} mm",
                        fontsize=5.8, va="bottom", color="#222")
            fig.savefig(pdf, format="pdf", facecolor="white")
            plt.close(fig)
    print("pages:", len(plan), "->", out)
    for i, (lay, items) in enumerate(plan, 1):
        print(f"  hal {i} ({lay['name']}): " + ", ".join(f"{q.key} {q.size()[0]:.0f}x{q.size()[1]:.0f}" for q, _, _ in items))


if __name__ == "__main__":
    main()
