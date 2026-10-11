"""Imposition engine: page selection, N-up, booklet and manual duplex layout.

The output is always a "physical sides" PDF: every page is one side of a sheet,
portrait and exactly paper-sized. For manual duplex, odd pages are fronts and
even pages are backs.
"""

from __future__ import annotations

import hashlib
import math
import re
import subprocess
import tempfile
from pathlib import Path

from pypdf import PageObject, PdfReader, PdfWriter, Transformation
from pypdf.generic import DecodedStreamObject, NameObject

from .i18n import _

MM = 72 / 25.4
PAPERS = {"A4": (210, 297), "A5": (148, 210), "Letter": (215.9, 279.4), "Legal": (215.9, 355.6)}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".gif"}
ESRGAN = Path.home() / ".local/share/yazdir/realesrgan/realesrgan-ncnn-vulkan"

DEFAULTS = {
    "paper": "A4",
    "quality": "Normal",
    "copies": 1,
    "collate": True,
    "page_range": "",
    "subset": "all",  # all | odd | even
    "reverse": False,
    "mode": "simplex",  # simplex | duplex | booklet
    "flip": "book",  # book: turn sideways | calendar: turn upwards
    "nup": 1,
    "order": "rows",  # rows: left to right, then down | columns: top to bottom, then right
    "border": False,
    "scale": "fit",  # fit | actual | custom
    "percent": 100,
    "rotate": "auto",  # auto | none | 90
    "margin_mm": 5.0,
    "enhance": "none",  # none | sharp | ai
    # Manual duplex calibration. Defaults suit C-path printers such as the
    # HP LaserJet 1018/1020/P1102: output face down, re-fed without flipping.
    "cal_reverse": True,  # feed backs in reverse order (last printed sheet is fed first)
    "cal_rotate180": True,  # rotate backs 180° (the back is printed from the opposite edge)
    "cal_note": "",
    "language": "system",  # system | en | tr; not affected by Reset
}


def run(cmd, **kw):
    result = subprocess.run(cmd, capture_output=True, text=True, check=False, **kw)
    if result.returncode != 0:
        raise RuntimeError(_("{tool} failed:\n{output}").format(tool=Path(cmd[0]).name, output=(result.stderr or result.stdout).strip()[-800:]))
    return result.stdout


def image_to_pdf(src: Path, enhance: str, tmp: Path, log=print) -> Path:
    """Convert an image to a one-page PDF, optionally as crisp 600 DPI black and white."""
    out = Path(tempfile.mkstemp(suffix=".pdf", dir=tmp)[1])
    image = src
    if enhance == "ai":
        if not ESRGAN.exists():
            raise RuntimeError(_("Real-ESRGAN not found: {path}\nRun ./install.sh --with-ai").format(path=ESRGAN))
        log(_("AI upscaling: {name}").format(name=src.name))
        flat, big = out.with_suffix(".in.png"), out.with_suffix(".up.png")
        run(["magick", str(src), "-background", "white", "-alpha", "remove", str(flat)])
        run([str(ESRGAN), "-i", str(flat), "-o", str(big), "-n", "realesrgan-x4plus-anime",
             "-m", str(ESRGAN.parent / "models")], cwd=ESRGAN.parent)
        image = big
    if enhance in ("sharp", "ai"):
        log(_("Converting to 600 DPI black and white: {name}").format(name=src.name))
        w, h = run(["magick", "identify", "-format", "%w %h", f"{image}[0]"]).split()
        box = "6776x4720" if int(w) > int(h) else "4720x6776"
        tune = ["-blur", "0x0.8", "-threshold", "55%"] if enhance == "ai" else \
               ["-blur", "0x2", "-level", "10%,90%", "-threshold", "58%"]
        run(["magick", f"{image}[0]", "-background", "white", "-alpha", "remove", "-colorspace", "Gray",
             "-filter", "Lanczos", "-resize", box, *tune, "-type", "bilevel", "-compress", "Group4",
             "-units", "PixelsPerInch", "-density", "600", str(out)])
    else:
        run(["magick", f"{image}[0]", "-background", "white", "-alpha", "remove",
             "-units", "PixelsPerInch", "-density", "300", str(out)])
    return out


def page_count(path: Path) -> int:
    if path.suffix.lower() in IMAGE_SUFFIXES:
        return 1
    return len(PdfReader(str(path)).pages)


def load_pages(files, enhance, tmp: Path, log=print):
    pages = []
    for f in map(Path, files):
        pdf = image_to_pdf(f, enhance, tmp, log) if f.suffix.lower() in IMAGE_SUFFIXES else f
        for p in PdfReader(str(pdf)).pages:
            p.transfer_rotation_to_content()
            pages.append(p)
    return pages


def parse_range(text: str, n: int):
    """'1-3,5,8-' → zero-based page indices. Empty means all pages."""
    text = text.replace(" ", "")
    if not text:
        return list(range(n))
    picked = []
    for part in filter(None, text.split(",")):
        if m := re.fullmatch(r"(\d*)-(\d*)", part):
            a, b = int(m[1] or 1), int(m[2] or n)
        elif part.isdigit():
            a = b = int(part)
        else:
            raise ValueError(_("Invalid page range: “{part}”").format(part=part))
        if a < 1 or b > n or a > b:
            raise ValueError(_("Out of range: “{part}” (document has {n} pages)").format(part=part, n=n))
        picked.extend(range(a - 1, b))
    return picked


def choose_grid(n, pw, ph, sw, sh):
    """Pick sheet orientation and columns × rows that give the largest scale for n pages."""
    best = None
    for landscape in (False, True):
        W, H = (ph, pw) if landscape else (pw, ph)
        for cols in range(1, n + 1):
            if n % cols:
                continue
            rows = n // cols
            scale = min(W / cols / sw, H / rows / sh)
            if best is None or scale > best[0] + 1e-9:
                best = (scale, landscape, cols, rows)
    return best[1:]


def _stream_page(W, H, ops):
    page = PageObject.create_blank_page(width=W, height=H)
    stream = DecodedStreamObject()
    stream.set_data(ops.encode())
    page[NameObject("/Contents")] = stream
    return page


def _border_page(W, H, boxes):
    return _stream_page(W, H, "0.5 w 0 G " + " ".join(f"{x:.2f} {y:.2f} {w:.2f} {h:.2f} re S" for x, y, w, h in boxes))


def _blank_side(Wp, Hp, margin_mm):
    """A blank side with a single ~0.1 mm dot, so drivers that skip empty pages don't break the sheet order."""
    m = max(margin_mm, 5) * MM
    return _stream_page(Wp, Hp, f"0 g {Wp - m:.2f} {m:.2f} 0.3 0.3 re f")


def _place(sheet, page, x0, y0, aw, ah, o, single):
    box = page.cropbox
    llx, lly, sw, sh = float(box.left), float(box.bottom), float(box.width), float(box.height)
    turn = {"90": True, "none": False}.get(o["rotate"], (sw > sh) != (aw > ah) and abs(sw - sh) > 1)
    ew, eh = (sh, sw) if turn else (sw, sh)
    if not single or o["scale"] == "fit":
        s = min(aw / ew, ah / eh)
    else:
        s = 1.0 if o["scale"] == "actual" else o["percent"] / 100
    t = Transformation().translate(-llx, -lly)
    if turn:
        t = t.rotate(90).translate(sh, 0)
    t = t.scale(s, s).translate(x0 + (aw - ew * s) / 2, y0 + (ah - eh * s) / 2)
    sheet.merge_transformed_page(page, t, expand=False)


def _compose(cells, W, H, cols, rows, o):
    sheet = PageObject.create_blank_page(width=W, height=H)
    m = o["margin_mm"] * MM
    gap = 4 * MM if cols * rows > 1 else 0
    aw = (W - 2 * m - (cols - 1) * gap) / cols
    ah = (H - 2 * m - (rows - 1) * gap) / rows
    boxes = []
    for i, page in enumerate(cells):
        c, r = (i % cols, i // cols) if o["order"] == "rows" else (i // rows, i % rows)
        x0, y0 = m + c * (aw + gap), H - m - (r + 1) * ah - r * gap
        if page is not None:
            _place(sheet, page, x0, y0, aw, ah, o, cols * rows == 1)
            boxes.append((x0, y0, aw, ah))
    if o["border"] and boxes:
        sheet.merge_page(_border_page(W, H, boxes))
    return sheet


def _physical(sheet, Wp, Hp, landscape, rot180):
    if not landscape and not rot180:
        return sheet
    t = Transformation()
    if landscape:
        t = t.rotate(90).translate(Wp, 0)
    if rot180:
        t = t.rotate(180).translate(Wp, Hp)
    page = PageObject.create_blank_page(width=Wp, height=Hp)
    page.merge_transformed_page(sheet, t, expand=False)
    return page


def impose(pages, o):
    """Lay out the selected pages on sheet sides. Returns (sides, is_duplex, last_back_blank)."""
    Wp, Hp = (v * MM for v in PAPERS[o["paper"]])
    picked = parse_range(o["page_range"], len(pages))
    if o["subset"] != "all":
        rem = 0 if o["subset"] == "odd" else 1
        picked = [i for i in picked if i % 2 == rem]
    if not picked:
        raise ValueError(_("No pages left in the selection."))
    seq = [pages[i] for i in picked]

    if o["mode"] == "booklet":
        n = math.ceil(len(seq) / 4) * 4
        seq += [None] * (n - len(seq))
        sides = []
        for i in range(n // 4):
            sides.append([seq[n - 1 - 2 * i], seq[2 * i]])
            sides.append([seq[2 * i + 1], seq[n - 2 - 2 * i]])
        landscape, cols, rows, calendar = True, 2, 1, False
    else:
        first = seq[0].cropbox
        landscape, cols, rows = choose_grid(o["nup"], Wp, Hp, float(first.width), float(first.height)) \
            if o["nup"] > 1 else (False, 1, 1)
        sides = [seq[i:i + o["nup"]] for i in range(0, len(seq), o["nup"])]
        calendar = o["flip"] == "calendar"

    duplex = o["mode"] != "simplex"
    W, H = (Hp, Wp) if landscape else (Wp, Hp)
    out = []
    for i, cells in enumerate(sides):
        back = duplex and i % 2 == 1
        # In reading orientation a "book" flip of a landscape sheet is a short-edge flip of the paper,
        # so the back turns 180° when the flip and the sheet orientation disagree, then the calibration applies.
        rot = back and ((calendar != landscape) != o["cal_rotate180"])
        if all(c is None for c in cells):
            out.append(_blank_side(Wp, Hp, o["margin_mm"]))
        else:
            out.append(_physical(_compose(cells, W, H, cols, rows, o), Wp, Hp, landscape, rot))
    if duplex and len(out) % 2:
        # Odd number of sides: the last sheet has an empty back. It is the first sheet fed
        # in the second pass and must pass through blank to keep the other sheets aligned.
        out.append(_blank_side(Wp, Hp, o["margin_mm"]))
        return out, duplex, True
    return out, duplex, False


def write_pdf(sides, path: Path) -> Path:
    w = PdfWriter()
    for s in sides:
        w.add_page(s)
    with open(path, "wb") as f:
        w.write(f)
    return path


def split_passes(doc: Path, copies: int, reverse: bool, tmp: Path):
    """Split a physical-sides PDF into front and back pass PDFs. Returns (front, back, sheets)."""
    n = len(PdfReader(str(doc)).pages)
    readers = [PdfReader(str(doc)) for _ in range(copies)]
    fronts = [(c, i) for c in range(copies) for i in range(0, n, 2)]
    backs = [(c, i) for c in range(copies) for i in range(1, n, 2)]
    if reverse:
        backs.reverse()
    paths = []
    for name, items in (("front", fronts), ("back", backs)):
        w = PdfWriter()
        for c, i in items:
            w.add_page(readers[c].pages[i])
        path = tmp / f"pass_{name}.pdf"
        with open(path, "wb") as f:
            w.write(f)
        paths.append(path)
    return paths[0], paths[1], len(fronts)


def test_document(tmp: Path, top_label: str = "↑ TOP ↑") -> Path:
    """Four numbered pages for checking the manual duplex calibration."""
    path = tmp / f"duplex-test-{hashlib.sha1(top_label.encode()).hexdigest()[:8]}.pdf"
    if not path.exists():
        images = []
        for i in range(1, 5):
            img = tmp / f"test{i}.png"
            run(["magick", "-size", "1240x1754", "xc:white", "-gravity", "center", "-pointsize", "500",
                 "-annotate", "+0+0", str(i), "-gravity", "north", "-pointsize", "80",
                 "-annotate", "+0+80", top_label, str(img)])
            images.append(str(img))
        run(["magick", *images, "-units", "PixelsPerInch", "-density", "150", str(path)])
    return path
