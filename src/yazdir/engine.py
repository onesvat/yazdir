"""Imposition engine: page selection, N-up, booklet and manual duplex layout.

The output is always a "physical sides" PDF: every page is one side of a sheet,
portrait and exactly paper-sized. For manual duplex, odd pages are fronts and
even pages are backs.
"""

from __future__ import annotations

import hashlib
import math
import os
import re
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageFilter, ImageOps
from pypdf import PageObject, PdfReader, PdfWriter, Transformation
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from .i18n import _

MM = 72 / 25.4
PAPERS = {"A4": (210, 297), "A5": (148, 210), "Letter": (215.9, 279.4), "Legal": (215.9, 355.6)}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".gif"}
DATA_HOME = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")
ESRGAN = DATA_HOME / "yazdir/realesrgan/realesrgan-ncnn-vulkan"

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
    # Manual duplex calibration of the selected printer (set by the calibration wizard):
    "cal_reverse": True,  # feed the backs in reverse order: the last printed sheet is fed first
    "cal_rotate180": False,  # turn backs 180°: the printer prints the back from the opposite edge
    "cal_note": "",  # the user's own words for how they reload the stack
    "language": "system",  # system | en | tr; not affected by Reset
}

# A4 portrait at 600 DPI minus 5 mm margins; images are fitted into this box when sharpened.
SHARP_BOX = (4720, 6776)


def run(cmd, **kw):
    result = subprocess.run(cmd, capture_output=True, text=True, check=False, **kw)
    if result.returncode != 0:
        raise RuntimeError(_("{tool} failed:\n{output}").format(tool=Path(cmd[0]).name, output=(result.stderr or result.stdout).strip()[-800:]))
    return result.stdout


def ai_available() -> bool:
    return ESRGAN.is_file() and os.access(ESRGAN, os.X_OK)


def _flatten(im: Image.Image) -> Image.Image:
    """First frame, alpha composited onto white, in RGB or L."""
    im = ImageOps.exif_transpose(im)
    if im.mode in ("RGBA", "LA", "P", "PA"):
        im = im.convert("RGBA")
        bg = Image.new("RGBA", im.size, "white")
        im = Image.alpha_composite(bg, im).convert("RGB")
    elif im.mode not in ("RGB", "L"):
        im = im.convert("RGB")
    return im


def sharpen_bw(im: Image.Image, ai: bool) -> Image.Image:
    """Fit into SHARP_BOX with Lanczos, smooth the edges, then threshold to pure black and white."""
    gray = im.convert("L")
    bw, bh = SHARP_BOX if gray.width <= gray.height else SHARP_BOX[::-1]
    s = min(bw / gray.width, bh / gray.height)
    gray = gray.resize((max(1, round(gray.width * s)), max(1, round(gray.height * s))), Image.Resampling.LANCZOS)
    # AI output is already clean: light blur, threshold at 55 %. Plain images: stronger blur and a
    # 10–90 % level stretch before a 58 % threshold, which equals a single cut at ~56 %.
    radius, cut = (0.8, 0.55) if ai else (2.0, 0.564)
    gray = gray.filter(ImageFilter.GaussianBlur(radius))
    return gray.point(lambda v: 255 if v > cut * 255 else 0).convert("1", dither=Image.Dither.NONE)


def image_to_pdf(src: Path, enhance: str, tmp: Path, log=print) -> Path:
    """Convert an image to a one-page PDF, optionally as crisp 600 DPI black and white."""
    out = Path(tempfile.mkstemp(suffix=".pdf", dir=tmp)[1])
    with Image.open(src) as opened:
        im = _flatten(opened)
    if enhance == "ai":
        if not ai_available():
            raise RuntimeError(_("Real-ESRGAN not found: {path}\nRun ./install.sh --with-ai").format(path=ESRGAN))
        log(_("AI upscaling: {name}").format(name=src.name))
        flat, big = out.with_suffix(".in.png"), out.with_suffix(".up.png")
        im.convert("RGB").save(flat)
        run([str(ESRGAN), "-i", str(flat), "-o", str(big), "-n", "realesrgan-x4plus-anime",
             "-m", str(ESRGAN.parent / "models")], cwd=ESRGAN.parent)
        with Image.open(big) as up:
            im = _flatten(up)
    if enhance in ("sharp", "ai"):
        log(_("Converting to 600 DPI black and white: {name}").format(name=src.name))
        sharpen_bw(im, enhance == "ai").save(out, "PDF", resolution=600)
    else:
        im.save(out, "PDF", resolution=300)
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
    stream.set_data(ops.encode("latin-1"))
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


# Helvetica-Bold advance widths (1/1000 em) for the characters used on the test pages.
_HELV_BOLD = {**dict.fromkeys("0123456789", 556), "T": 611, "O": 778, "P": 667, "U": 722, "Ü": 722, "S": 667,
              "A": 722, "E": 667, "R": 722, "N": 722, "H": 722, "I": 278, "Ç": 722, "Ö": 778, "Ğ": 778, " ": 278}


def _text_width(text, size):
    return sum(_HELV_BOLD.get(c, 667) for c in text) * size / 1000


def _pdf_string(text):
    raw = text.encode("cp1252", errors="replace")
    return "(" + raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)").decode("latin-1") + ")"


def _test_page(number, top_label):
    W, H = PAPERS["A4"][0] * MM, PAPERS["A4"][1] * MM
    big, small = 380, 30
    label_w = _text_width(top_label, small)
    lx, ly = (W - label_w) / 2, H - 70
    arrow = lambda x: f"{x:.1f} {ly + 22:.1f} m {x - 9:.1f} {ly + 8:.1f} l {x - 3:.1f} {ly + 8:.1f} l {x - 3:.1f} {ly - 6:.1f} l " \
                      f"{x + 3:.1f} {ly - 6:.1f} l {x + 3:.1f} {ly + 8:.1f} l {x + 9:.1f} {ly + 8:.1f} l h f"  # noqa: E731
    ops = " ".join([
        "0 g",
        arrow(lx - 22), arrow(lx + label_w + 22),
        f"BT /F1 {small} Tf {lx:.1f} {ly:.1f} Td {_pdf_string(top_label)} Tj ET",
        f"BT /F1 {big} Tf {(W - _text_width(str(number), big)) / 2:.1f} {H / 2 - big * 0.36:.1f} Td ({number}) Tj ET",
        f"1.5 w 0.6 G 28 28 {W - 56:.1f} {H - 56:.1f} re S",
    ])
    page = _stream_page(W, H, ops)
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"),
                             NameObject("/BaseFont"): NameObject("/Helvetica-Bold"),
                             NameObject("/Encoding"): NameObject("/WinAnsiEncoding")})
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
    return page


def test_document(tmp: Path, top_label: str = "TOP") -> Path:
    """Four numbered A4 pages with a TOP marker, for calibrating manual duplex on 2 sheets."""
    path = tmp / f"duplex-test-{hashlib.sha1(top_label.encode()).hexdigest()[:8]}.pdf"
    if not path.exists():
        write_pdf([_test_page(i, top_label) for i in range(1, 5)], path)
    return path
