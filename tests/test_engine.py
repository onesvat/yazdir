import re
import sys
from pathlib import Path

import pytest
from pypdf import PageObject, PdfReader

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from yazdir import engine

A4 = (210 * engine.MM, 297 * engine.MM)


def numbered_pages(n, size=A4):
    """Source pages whose content carries a recognisable marker: a tiny rectangle at x = 1000 + page number."""
    pages = []
    for i in range(1, n + 1):
        p = engine._stream_page(*size, f"{1000 + i} 0 0.1 0.1 re f")
        pages.append(p)
    return pages


def markers(side: PageObject):
    data = side.get_contents().get_data().decode("latin-1")
    return [int(m) - 1000 for m in re.findall(r"\b(1\d{3}) 0 0\.1 0\.1 re", data)]


def opts(**kw):
    return dict(engine.DEFAULTS, **kw)


@pytest.mark.parametrize("text,n,expected", [
    ("", 3, [0, 1, 2]),
    ("1-3,5", 6, [0, 1, 2, 4]),
    ("4-", 6, [3, 4, 5]),
    ("-2", 6, [0, 1]),
    (" 2 , 4 ", 5, [1, 3]),
])
def test_parse_range(text, n, expected):
    assert engine.parse_range(text, n) == expected


@pytest.mark.parametrize("text", ["0", "7", "3-2", "a", "1-x"])
def test_parse_range_rejects(text):
    with pytest.raises(ValueError):
        engine.parse_range(text, 6)


@pytest.mark.parametrize("n,landscape,cols,rows", [(2, True, 2, 1), (4, False, 2, 2), (6, True, 3, 2), (9, False, 3, 3), (16, False, 4, 4)])
def test_choose_grid_for_portrait_pages(n, landscape, cols, rows):
    assert engine.choose_grid(n, *A4, *A4) == (landscape, cols, rows)


def test_simplex_nup_groups_pages_in_order():
    sides, duplex, blank = engine.impose(numbered_pages(9), opts(nup=4))
    assert not duplex and not blank
    assert [markers(s) for s in sides] == [[1, 2, 3, 4], [5, 6, 7, 8], [9]]


def test_subset_and_range():
    sides, *_ = engine.impose(numbered_pages(8), opts(page_range="2-7", subset="odd"))
    assert [markers(s) for s in sides] == [[3], [5], [7]]


def test_booklet_imposition_order():
    sides, duplex, blank = engine.impose(numbered_pages(8), opts(mode="booklet"))
    assert duplex and not blank
    assert [markers(s) for s in sides] == [[8, 1], [2, 7], [6, 3], [4, 5]]


def test_booklet_pads_to_multiple_of_four():
    sides, *_ = engine.impose(numbered_pages(5), opts(mode="booklet"))
    assert [markers(s) for s in sides] == [[1], [2], [3], [4, 5]]


def test_duplex_odd_count_adds_blank_back_with_dot():
    sides, duplex, blank = engine.impose(numbered_pages(5), opts(mode="duplex"))
    assert duplex and blank
    assert [markers(s) for s in sides] == [[1], [2], [3], [4], [5], []]
    assert b"re f" in sides[-1].get_contents().get_data()  # the anti-skip dot


def test_all_sides_are_portrait_paper_size():
    for mode, nup in (("duplex", 2), ("booklet", 1), ("simplex", 6)):
        sides, *_ = engine.impose(numbered_pages(6), opts(mode=mode, nup=nup))
        for s in sides:
            assert (round(float(s.mediabox.width)), round(float(s.mediabox.height))) == (595, 842)


def _cm_rotations(side):
    """Count 180° turns applied at the physical level (a 'cm' matrix starting with -1 0 0 -1)."""
    data = side.get_contents().get_data().decode("latin-1")
    count = 0
    for a, b, c, d in re.findall(r"(\S+) (\S+) (\S+) (\S+) \S+ \S+ cm", data):
        if float(a) == -1 and float(d) == -1 and abs(float(b)) < 1e-9 and abs(float(c)) < 1e-9:
            count += 1
    return count


@pytest.mark.parametrize("flip,nup,cal,expect_back_turned", [
    ("book", 1, True, True),  # portrait book flip on a C-path printer: backs turned
    ("book", 1, False, False),
    ("calendar", 1, True, False),
    ("calendar", 1, False, True),
])
def test_back_rotation_follows_flip_and_calibration(flip, nup, cal, expect_back_turned):
    sides, *_ = engine.impose(numbered_pages(2), opts(mode="duplex", flip=flip, nup=nup, cal_rotate180=cal))
    assert _cm_rotations(sides[0]) == 0
    assert (_cm_rotations(sides[1]) > 0) == expect_back_turned


def test_split_passes_reverses_backs_across_copies(tmp_path):
    sides, *_ = engine.impose(numbered_pages(3), opts(mode="duplex"))
    doc = engine.write_pdf(sides, tmp_path / "doc.pdf")
    front, back, sheets = engine.split_passes(doc, copies=2, reverse=True, tmp=tmp_path)
    assert sheets == 4
    assert [markers(p) for p in PdfReader(str(front)).pages] == [[1], [3], [1], [3]]
    assert [markers(p) for p in PdfReader(str(back)).pages] == [[], [2], [], [2]]


def test_split_passes_without_reverse(tmp_path):
    sides, *_ = engine.impose(numbered_pages(4), opts(mode="duplex"))
    doc = engine.write_pdf(sides, tmp_path / "doc.pdf")
    _front, back, _ = engine.split_passes(doc, copies=1, reverse=False, tmp=tmp_path)
    assert [markers(p) for p in PdfReader(str(back)).pages] == [[2], [4]]
