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

from gi.repository import GLib, Graphene, Gtk  # noqa: E402

from yazdir import app  # noqa: E402

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
EXAMPLES = ROOT / "examples" / ("tr" if app.LANGUAGE == "tr" else "en")


def shot(window, name):
    paintable = Gtk.WidgetPaintable(widget=window)
    w, h = window.get_width(), window.get_height()
    snapshot = Gtk.Snapshot()
    paintable.snapshot(snapshot, w, h)
    texture = window.get_native().get_renderer().render_texture(snapshot.to_node(), Graphene.Rect().init(0, 0, w, h))
    texture.save_to_png(str(OUT / name))
    print("saved", OUT / name)


def select(win, key, value):
    row, keys = win.combos[key]
    row.set_selected(keys.index(value))


def main(application):
    win = app.Window(application)
    win.set_default_size(620, 1180)
    win.lp = lambda *a, **k: "printer-1"
    pending = {"n": 0}
    app.job_pending = lambda job: pending["n"] < 1
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
        win.sections[2][0].grab_focus()

    @step
    def advanced_shot():
        shot(win, "advanced.png")
        win.sections[2][0].set_expanded(False)
        win.get_content().get_child().get_content().scroll_to_top()
        win.manual_duplex(win.options(), None, None, 3, True)

    @step
    def printing_fronts():
        shot(win, "duplex-printing.png")
        pending["n"] = 1

    @step
    def wait():
        pass

    @step
    def reload_paper():
        shot(win, "duplex-reload.png")
        application.quit()

    def tick():
        steps.pop(0)()
        return bool(steps)

    GLib.timeout_add(900, tick)


class ScreenshotApp(app.Application):
    def do_activate(self):
        main(self)


application = ScreenshotApp(app_id="io.github.onesvat.Yazdir.Screenshots")
application.run([])
