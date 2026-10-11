"""Render the README screenshots without printing anything.

    YAZDIR_LANG=en python tools/screenshots.py docs/screenshots/en
    YAZDIR_LANG=tr python tools/screenshots.py docs/screenshots/tr

Uses a throw-away settings directory and replaces the CUPS calls with stubs.
"""

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
sys.path.insert(0, str(ROOT / "src"))

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Graphene", "1.0")
from gi.repository import GLib, Graphene, Gtk  # noqa: E402
from PIL import Image, ImageDraw, ImageFilter  # noqa: E402

from yazdir import app, printing  # noqa: E402

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
EXAMPLES = ROOT / "examples" / ("tr" if app.LANGUAGE == "tr" else "en")
PRINTER = "Office-Laser"

queue = {"busy": True}
printing.printers = lambda: ([PRINTER], PRINTER)
printing.submit = lambda *a, **k: "1"
printing.job_pending = lambda job: queue["busy"]


def shot(window, name):
    """Save the window like GNOME's window screenshot: rounded corners, soft shadow, transparent background."""
    paintable = Gtk.WidgetPaintable(widget=window)
    w, h = window.get_width(), window.get_height()
    snapshot = Gtk.Snapshot()
    paintable.snapshot(snapshot, w, h)
    texture = window.get_native().get_renderer().render_texture(snapshot.to_node(), Graphene.Rect().init(0, 0, w, h))
    raw = OUT / f".{name}"
    texture.save_to_png(str(raw))
    window_image = Image.open(raw).convert("RGBA")
    raw.unlink()
    radius, pad = 12, 36
    mask = Image.new("L", window_image.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius, fill=255)
    window_image.putalpha(mask)
    canvas = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((pad, pad + 6, pad + w, pad + h + 6), radius, fill=(0, 0, 0, 90))
    canvas = Image.alpha_composite(canvas, shadow.filter(ImageFilter.GaussianBlur(14)))
    canvas.alpha_composite(window_image, (pad, pad))
    canvas.save(OUT / name, optimize=True)
    print("saved", OUT / name)


def scroll_to(win, row):
    """Scroll the preferences page so that row is near the top."""
    scroller = win.get_content().get_child().get_content()
    while scroller and not isinstance(scroller, Gtk.ScrolledWindow):
        scroller = scroller.get_first_child()
    ok, point = row.compute_point(scroller.get_child(), Graphene.Point())
    if ok:
        scroller.get_vadjustment().set_value(max(0, point.y - 24))


def select(win, key, value):
    row, keys = win.combos[key]
    row.set_selected(keys.index(value))


def click(widget, label):
    """Click the first button under widget whose label matches."""
    stack = [widget]
    while stack:
        w = stack.pop()
        if isinstance(w, Gtk.Button) and w.get_label() == label and w.get_mapped():
            w.emit("clicked")
            return
        child = w.get_first_child()
        while child:
            stack.append(child)
            child = child.get_next_sibling()
    raise LookupError(label)


def main(application):
    tr = app._
    win = app.Window(application)
    win.set_default_size(900, 760)
    win.calibrations[PRINTER] = {"reverse": True, "rotate180": False, "note": ""}
    win.load_calibration()
    win.add_files([str(EXAMPLES / "3-pocket-planner-booklet.pdf"), str(EXAMPLES / "1-weekly-planner.pdf")])
    select(win, "mode", "duplex")
    win.present()
    steps = []

    def step(fn):
        steps.append(fn)

    @step
    def main_window():
        shot(win, "main.png")

    @step
    def advanced():
        select(win, "nup", 4)
        win.border.set_active(True)
        win.sections[2][0].set_expanded(True)

    @step
    def advanced_scroll():
        scroll_to(win, win.sections[0][0])

    @step
    def advanced_shot():
        shot(win, "advanced.png")
        win.sections[2][0].set_expanded(False)
        scroll_to(win, win.file_group)
        select(win, "nup", 1)
        win.border.set_active(False)
        queue["busy"] = True
        win.manual_duplex(win.options(), None, None, 3, True)

    @step
    def printing_fronts():
        shot(win, "duplex-printing.png")
        queue["busy"] = False

    @step
    def wait():
        pass

    @step
    def reload_paper():
        shot(win, "duplex-reload.png")
        click(win, tr("Cancel"))
        win.toasts.dismiss_all()
        queue["busy"] = True
        win.calibrate()

    @step
    def calibration_intro():
        shot(win, "calibration-1.png")
        click(win, tr("Print pages 1 and 3"))

    @step
    def wait_layout():
        queue["busy"] = False

    @step
    def calibration_reload():
        shot(win, "calibration-2.png")
        queue["busy"] = True
        click(win, tr("Print pages 2 and 4"))

    @step
    def backs_done():
        queue["busy"] = False

    @step
    def wait_backs():
        pass

    @step
    def calibration_result():
        shot(win, "calibration-3.png")
        application.quit()

    def tick():
        steps.pop(0)()
        return bool(steps)

    GLib.timeout_add(1100, tick)


class ScreenshotApp(app.Application):
    def do_activate(self):
        main(self)


application = ScreenshotApp(app_id="io.github.onesvat.Yazdir.Screenshots")
application.run([])
