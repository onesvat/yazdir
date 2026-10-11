"""GTK 4 / libadwaita front end: N-up, booklet and guided manual duplex printing."""

import json
import re
import subprocess
import sys
import threading
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from . import __version__, engine  # noqa: E402
from .i18n import LANGUAGE, LANGUAGES, _  # noqa: E402

APP_ID = "io.github.onesvat.Yazdir"
from .i18n import SETTINGS_FILE  # noqa: E402
CACHE = Path(GLib.get_user_cache_dir()) / "yazdir"
DATA = Path(__file__).parent / "data"


def choices():
    return {
        "paper": [(k, k) for k in engine.PAPERS],
        "quality": [("Normal", _("Normal")), ("Draft", _("Draft (less toner)"))],
        "subset": [("all", _("All pages")), ("odd", _("Odd pages only")), ("even", _("Even pages only"))],
        "mode": [("simplex", _("One-sided")), ("duplex", _("Two-sided (manual)")), ("booklet", _("Booklet"))],
        "flip": [("book", _("Like a book (sideways)")), ("calendar", _("Like a calendar (upwards)"))],
        "nup": [(n, _("{n} pages").format(n=n) if n > 1 else _("1 page")) for n in (1, 2, 4, 6, 9, 16)],
        "order": [("rows", _("Left to right")), ("columns", _("Top to bottom"))],
        "scale": [("fit", _("Fit to paper")), ("actual", _("Actual size (100%)")), ("custom", _("Custom percentage"))],
        "rotate": [("auto", _("Automatic")), ("none", _("Don't rotate")), ("90", _("Rotate 90°"))],
        "enhance": [("none", _("None")), ("sharp", _("Sharp black and white")), ("ai", _("AI + sharp (best, slow)"))],
        "language": [("system", _("System default")), *LANGUAGES.items()],
    }


def load_settings():
    settings = dict(engine.DEFAULTS)
    try:
        settings.update(json.loads(SETTINGS_FILE.read_text()))
    except (OSError, ValueError):
        pass
    return settings


def printers():
    try:
        names = subprocess.run(["lpstat", "-e"], capture_output=True, text=True, check=False).stdout.split()
        default = subprocess.run(["lpstat", "-d"], capture_output=True, text=True, check=False).stdout
    except OSError:
        return [], None
    m = re.search(r":\s*(\S+)", default)
    return names, (m[1] if m else None)


def job_pending(job_id):
    out = subprocess.run(["lpstat", "-o"], capture_output=True, text=True, check=False).stdout
    return any(line.split()[0] == job_id for line in out.splitlines() if line.strip())


class Window(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Yazdır", default_width=560, default_height=860)
        self.settings = load_settings()
        self.choices = choices()
        self.files = []
        self.file_rows = {}
        self.combos = {}
        self.busy = False

        self.toasts = Adw.ToastOverlay()
        view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        self.print_btn = Gtk.Button(label=_("Print"), css_classes=["suggested-action"])
        self.print_btn.connect("clicked", lambda *a: self.start("print"))
        self.preview_btn = Gtk.Button(label=_("Preview"))
        self.preview_btn.connect("clicked", lambda *a: self.start("preview"))
        reset = Gtk.Button(child=Adw.ButtonContent(icon_name="edit-undo-symbolic", label=_("Reset")),
                           tooltip_text=_("Restore default settings (printer, files and duplex calibration are kept)"))
        reset.connect("clicked", lambda *a: self.reset())
        save = Gtk.Button(icon_name="document-save-symbolic", tooltip_text=_("Save the laid-out PDF"))
        save.connect("clicked", lambda *a: self.start("save"))
        self.spinner = Gtk.Spinner()
        menu = Gio.Menu()
        menu.append(_("About Yazdır"), "app.about")
        header.pack_end(Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu, tooltip_text=_("Main menu")))
        header.pack_end(self.print_btn)
        header.pack_end(self.preview_btn)
        header.pack_end(reset)
        header.pack_start(save)
        header.pack_start(self.spinner)
        view.add_top_bar(header)

        page = Adw.PreferencesPage()
        view.set_content(page)
        self.toasts.set_child(view)
        self.set_content(self.toasts)

        # Files
        self.file_group = Adw.PreferencesGroup(title=_("Files"), description=_("PDFs or images; you can drag and drop them onto the window."))
        add = Gtk.Button(icon_name="list-add-symbolic", tooltip_text=_("Add files"), css_classes=["flat"])
        add.connect("clicked", self.pick_files)
        self.file_group.set_header_suffix(add)
        self.empty_row = Adw.ActionRow(title=_("No files yet"))
        self.file_group.add(self.empty_row)
        page.add(self.file_group)

        # Everyday settings
        g = Adw.PreferencesGroup(title=_("Printing"))
        names, default = printers()
        wanted = self.settings.get("printer") or default
        self.printers = names or [_("(no printer found)")]
        self.printer_row = Adw.ComboRow(title=_("Printer"), model=Gtk.StringList.new(self.printers))
        if wanted in self.printers:
            self.printer_row.set_selected(self.printers.index(wanted))
        g.add(self.printer_row)
        g.add(self.combo("mode", _("Print type")))
        g.add(self.combo("flip", _("Flip"), _("How you turn the sheet to read the back")))
        g.add(self.combo("nup", _("Pages per sheet")))
        self.copies = self.spin(1, 99, 1, "copies", _("Copies"))
        g.add(self.copies)
        page.add(g)

        # Advanced settings
        g = Adw.PreferencesGroup(title=_("Advanced settings"))
        self.sections = []

        def section(title, keys, rows):
            e = Adw.ExpanderRow(title=title)
            for r in rows:
                e.add_row(r)
            g.add(e)
            self.sections.append((e, keys))

        self.margin = self.spin(0, 30, 0.5, "margin_mm", _("Margin (mm)"), _("Most printers can't print the outer ~4 mm"), digits=1)
        section(_("Paper and quality"), ["paper", "quality", "margin_mm"], [
            self.combo("paper", _("Paper size")), self.combo("quality", _("Print quality")), self.margin,
        ])
        self.page_range = Adw.EntryRow(title=_("Page range (empty = all, e.g. 1-3,5,8-)"))
        self.page_range.set_text(self.settings["page_range"])
        self.reverse = Adw.SwitchRow(title=_("Print in reverse order"), subtitle=_("One-sided printing only"),
                                     active=self.settings["reverse"])
        self.collate = Adw.SwitchRow(title=_("Collate"), subtitle=_("Print as 1,2,3 – 1,2,3"), active=self.settings["collate"])
        section(_("Pages and copies"), ["page_range", "subset", "reverse", "collate"], [
            self.page_range, self.combo("subset", _("Page subset")), self.reverse, self.collate,
        ])
        self.border = Adw.SwitchRow(title=_("Border around pages"), active=self.settings["border"])
        self.percent = self.spin(10, 400, 5, "percent", _("Custom scale (%)"))
        section(_("Layout and scale"), ["order", "border", "scale", "percent", "rotate"], [
            self.combo("order", _("Page order")),
            self.border,
            self.combo("scale", _("Scale"), _("Applies to one page per sheet")),
            self.percent,
            self.combo("rotate", _("Page rotation"), _("Automatic turns landscape pages to fit the sheet")),
        ])
        section(_("Images"), ["enhance"], [
            self.combo("enhance", _("Quality enhancement"), _("Images only; sharp: 600 DPI black and white for drawings")),
        ])
        self.cal_reverse = Adw.SwitchRow(title=_("Reverse order in the second pass"),
                                         subtitle=_("Change this if backs land on the wrong sheets"),
                                         active=self.settings["cal_reverse"])
        self.cal_rotate = Adw.SwitchRow(title=_("Rotate backs 180°"), subtitle=_("Toggle this if backs come out upside down"),
                                        active=self.settings["cal_rotate180"])
        self.cal_note = Adw.EntryRow(title=_("Extra note (shown in the duplex dialog)"))
        self.cal_note.set_text(self.settings["cal_note"])
        test = Adw.ButtonRow(title=_("Print test pages (2 sheets)"))
        test.connect("activated", lambda *a: self.start("test"))
        section(_("Manual duplex calibration"), [], [self.cal_reverse, self.cal_rotate, self.cal_note, test])
        self.sections[-1][0].set_subtitle(_("Tuned for your printer; not affected by Reset"))
        language = self.combo("language", _("Language"), _("Takes effect after restarting the app"))
        language.connect("notify::selected", lambda *a: (self.save_settings(self.options()),
                                                         self.notify(_("Restart Yazdır to change the language."))))
        section(_("Application"), [], [language])
        self.sections[-1][0].set_subtitle(LANGUAGES.get(LANGUAGE, LANGUAGE))
        page.add(g)

        for w in (self.copies, self.percent, self.margin):
            w.connect("notify::value", lambda *a: self.summarize())
        for w in (self.reverse, self.collate, self.border):
            w.connect("notify::active", lambda *a: self.summarize())
        self.page_range.connect("changed", lambda *a: self.summarize())
        for row, _keys in self.combos.values():
            row.connect("notify::selected", lambda *a: self.summarize())
        self.summarize()

        for key in ("mode", "nup", "scale"):
            self.combos[key][0].connect("notify::selected", lambda *a: self.update_sensitivity())
        self.update_sensitivity()

        drop = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        drop.connect("drop", lambda _t, value, *a: (self.add_files([f.get_path() for f in value.get_files()]), True)[1])
        self.add_controller(drop)

    # --- Widgets -------------------------------------------------------------

    def combo(self, key, title, subtitle=None):
        keys = [k for k, _label in self.choices[key]]
        row = Adw.ComboRow(title=title, model=Gtk.StringList.new([label for _k, label in self.choices[key]]))
        if subtitle:
            row.set_subtitle(subtitle)
        if self.settings.get(key) in keys:
            row.set_selected(keys.index(self.settings[key]))
        self.combos[key] = (row, keys)
        return row

    def spin(self, lo, hi, step, key, title, subtitle=None, digits=0):
        row = Adw.SpinRow.new_with_range(lo, hi, step)
        row.set_digits(digits)
        row.set_title(title)
        if subtitle:
            row.set_subtitle(subtitle)
        row.set_value(self.settings[key])
        return row

    def selected(self, key):
        row, keys = self.combos[key]
        return keys[row.get_selected()]

    def label_for(self, key, value):
        if key in self.choices:
            return dict(self.choices[key])[value]
        return {
            "margin_mm": lambda: _("margin {mm} mm").format(mm=f"{value:g}"),
            "page_range": lambda: _("pages {range}").format(range=value),
            "reverse": lambda: _("reverse order"),
            "collate": lambda: _("not collated"),
            "border": lambda: _("border"),
            "percent": lambda: f"{value:g}%",
        }[key]()

    def summarize(self):
        """Show non-default values in the subtitle of each advanced section."""
        o = self.options()
        for expander, keys in self.sections:
            if not keys:
                continue
            changed = [self.label_for(k, o[k]) for k in keys if o[k] != engine.DEFAULTS[k]]
            expander.set_subtitle(_("Changed: {list}").format(list=" · ".join(changed)) if changed else _("Default"))

    def update_sensitivity(self):
        booklet = self.selected("mode") == "booklet"
        single = self.selected("nup") == 1 and not booklet
        self.combos["flip"][0].set_sensitive(self.selected("mode") == "duplex")
        self.combos["nup"][0].set_sensitive(not booklet)
        self.combos["order"][0].set_sensitive(not single)
        self.combos["scale"][0].set_sensitive(single)
        self.percent.set_sensitive(single and self.selected("scale") == "custom")
        self.reverse.set_sensitive(self.selected("mode") == "simplex")

    def reset(self):
        """Restore print defaults; keep the printer, files and duplex calibration."""
        d = engine.DEFAULTS
        for key, (row, keys) in self.combos.items():
            if key == "language":
                continue
            row.set_selected(keys.index(d[key]))
        self.copies.set_value(d["copies"])
        self.collate.set_active(d["collate"])
        self.page_range.set_text(d["page_range"])
        self.reverse.set_active(d["reverse"])
        self.border.set_active(d["border"])
        self.percent.set_value(d["percent"])
        self.margin.set_value(d["margin_mm"])
        self.save_settings(self.options())
        self.notify(_("Settings restored to defaults (duplex calibration kept)."))

    def notify(self, text):
        self.toasts.add_toast(Adw.Toast(title=text, timeout=4))

    def error(self, text):
        d = Adw.AlertDialog(heading=_("Error"), body=text)
        d.add_response("ok", _("OK"))
        d.present(self)

    def options(self):
        o = {key: self.selected(key) for key in self.combos}
        o.update(copies=int(self.copies.get_value()), collate=self.collate.get_active(), page_range=self.page_range.get_text(),
                 reverse=self.reverse.get_active(), border=self.border.get_active(), percent=self.percent.get_value(),
                 margin_mm=self.margin.get_value(), cal_reverse=self.cal_reverse.get_active(),
                 cal_rotate180=self.cal_rotate.get_active(), cal_note=self.cal_note.get_text(),
                 printer=self.printers[self.printer_row.get_selected()], last_folder=self.settings.get("last_folder"))
        return o

    def save_settings(self, o):
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(json.dumps(o, ensure_ascii=False, indent=2))

    # --- Files ---------------------------------------------------------------

    def pick_files(self, *args):
        f = Gtk.FileFilter(name=_("PDFs and images"))
        f.add_mime_type("application/pdf")
        f.add_pixbuf_formats()
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(f)
        d = Gtk.FileDialog(title=_("Add files"), filters=filters)
        self.set_start_folder(d)
        d.open_multiple(self, None, self._picked)

    def set_start_folder(self, dialog):
        folder = Path(self.settings.get("last_folder") or GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOWNLOAD)
                      or Path.home())
        if folder.is_dir():
            dialog.set_initial_folder(Gio.File.new_for_path(str(folder)))

    def remember_folder(self, path):
        self.settings["last_folder"] = str(Path(path).parent)
        self.save_settings(self.options())

    def _picked(self, dialog, result):
        try:
            picked = dialog.open_multiple_finish(result)
        except GLib.Error:
            return
        paths = [picked.get_item(i).get_path() for i in range(picked.get_n_items())]
        if paths and paths[0]:
            self.remember_folder(paths[0])
        self.add_files(paths)

    def add_files(self, paths):
        for path in map(Path, filter(None, paths)):
            if path in self.files or not path.is_file():
                continue
            try:
                n = engine.page_count(path)
            except Exception as e:  # broken or unsupported file
                self.notify(_("Could not open {name}: {error}").format(name=path.name, error=e))
                continue
            if not self.files:
                self.file_group.remove(self.empty_row)
            self.files.append(path)
            row = Adw.ActionRow(title=GLib.markup_escape_text(path.name),
                                subtitle=_("{n} pages").format(n=n) if n > 1 else _("1 page"))
            remove = Gtk.Button(icon_name="user-trash-symbolic", valign=Gtk.Align.CENTER, css_classes=["flat"],
                                tooltip_text=_("Remove"))
            remove.connect("clicked", lambda _b, p=path: self.remove_file(p))
            row.add_suffix(remove)
            self.file_rows[path] = row
            self.file_group.add(row)

    def remove_file(self, path):
        self.file_group.remove(self.file_rows.pop(path))
        self.files.remove(path)
        if not self.files:
            self.file_group.add(self.empty_row)

    # --- Jobs ----------------------------------------------------------------

    def start(self, action):
        if self.busy:
            return
        o = self.options()
        if action == "test":
            o.update(mode="duplex", flip="book", nup=1, page_range="", subset="all", copies=1, scale="fit",
                     enhance="none", border=False)
            files = None
        else:
            if not self.files:
                self.notify(_("Add a file first."))
                return
            files = list(self.files)
        if action in ("print", "test") and o["printer"] not in printers()[0]:
            self.error(_("No usable printer."))
            return
        self.save_settings(o)
        if action == "save":
            d = Gtk.FileDialog(title=_("Save as PDF"), initial_name=_("laid-out.pdf"))
            self.set_start_folder(d)
            d.save(self, None, lambda dlg, res: self._save_picked(dlg, res, o, files))
            return
        self.run_job(action, o, files)

    def _save_picked(self, dialog, result, o, files):
        try:
            target = dialog.save_finish(result).get_path()
        except GLib.Error:
            return
        self.remember_folder(target)
        o["last_folder"] = self.settings["last_folder"]
        self.run_job("save", o, files, Path(target))

    def run_job(self, action, o, files, target=None):
        self.busy = True
        self.spinner.start()
        for b in (self.print_btn, self.preview_btn):
            b.set_sensitive(False)

        def worker():
            try:
                CACHE.mkdir(parents=True, exist_ok=True)
                sources = [engine.test_document(CACHE, _("↑ TOP ↑"))] if files is None else files
                pages = engine.load_pages(sources, o["enhance"], CACHE, lambda m: GLib.idle_add(self.notify, m))
                sides, duplex, last_blank = engine.impose(pages, o)
                doc = engine.write_pdf(sides, target or CACHE / "document.pdf")
                GLib.idle_add(self._done, action, o, doc, duplex, last_blank, None)
            except Exception as e:
                GLib.idle_add(self._done, action, o, None, False, False, str(e))

        threading.Thread(target=worker, daemon=True).start()

    def _done(self, action, o, doc, duplex, last_blank, err):
        self.busy = False
        self.spinner.stop()
        for b in (self.print_btn, self.preview_btn):
            b.set_sensitive(True)
        if err:
            self.error(err)
        elif action == "preview":
            Gio.AppInfo.launch_default_for_uri(Gio.File.new_for_path(str(doc)).get_uri(), None)
        elif action == "save":
            self.notify(_("Saved: {name}").format(name=doc.name))
        elif duplex:
            try:
                front, back, sheets = engine.split_passes(doc, o["copies"], o["cal_reverse"], CACHE)
            except Exception as e:
                self.error(str(e))
                return
            self.manual_duplex(o, front, back, sheets, last_blank)
        else:
            extra = ["-n", str(o["copies"]), "-o", f"collate={'true' if o['collate'] else 'false'}"]
            if o["reverse"]:
                extra += ["-o", "outputorder=reverse"]
            if self.lp(o, doc, "Yazdır", extra):
                self.notify(_("Sent to the printer."))

    def lp(self, o, pdf, title, extra=()):
        cmd = ["lp", "-d", o["printer"], "-t", title, "-o", f"media={o['paper']}", "-o", "scaling=100",
               "-o", f"OutputMode={o['quality']}", *extra, str(pdf)]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            self.error(_("Could not send to the printer:\n{error}").format(error=result.stderr.strip()))
            return None
        m = re.search(r"request id is (\S+)", result.stdout)
        return m[1] if m else "?"

    def manual_duplex(self, o, front, back, sheets, last_blank):
        job = self.lp(o, front, "Yazdır (fronts)")
        if not job:
            return
        steps = [
            _("<b>1.</b> Take <b>all {n} sheets</b> from the output tray without changing their order.").format(n=sheets),
            _("<b>2.</b> Put them in the front input tray <b>without flipping or rotating</b>: "
              "edge <b>B</b> towards the printer, blank sides up."),
            _("<b>3.</b> Press <b>Continue</b>."),
        ]
        if last_blank:
            steps.append("\n<i>" + _("The top sheet has an empty back and will pass through blank. Don't remove it; "
                                     "it keeps the other sheets in order.") + "</i>")
        if o["cal_note"].strip():
            steps.append("\n" + GLib.markup_escape_text(o["cal_note"].strip()))

        d = Adw.Dialog(title=_("Manual duplex"), content_width=720, can_close=False)
        view = Adw.ToolbarView()
        view.add_top_bar(Adw.HeaderBar(show_end_title_buttons=False))
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16,
                      margin_start=24, margin_end=24, margin_bottom=24, margin_top=6)
        title = Gtk.Label(label=_("Printing the fronts ({n} sheets)…").format(n=sheets), wrap=True, css_classes=["title-2"])
        subtitle = Gtk.Label(label=_("When it finishes you will reload the paper as shown below."), wrap=True,
                             css_classes=["dim-label"])
        diagram = DATA / f"feed-diagram-{LANGUAGE}.svg"
        picture = Gtk.Picture.new_for_filename(str(diagram if diagram.exists() else DATA / "feed-diagram-en.svg"))
        picture.set_content_fit(Gtk.ContentFit.CONTAIN)
        picture.set_size_request(-1, 300)
        steps_label = Gtk.Label(xalign=0, wrap=True, use_markup=True, label="\n".join(steps), visible=False)
        cancel = Gtk.Button(label=_("Cancel"), css_classes=["pill"])
        cont = Gtk.Button(label=_("Continue"), css_classes=["pill", "suggested-action"], sensitive=False)
        buttons = Gtk.Box(spacing=12, halign=Gtk.Align.CENTER, margin_top=8, homogeneous=True)
        buttons.append(cancel)
        buttons.append(cont)
        for w in (title, subtitle, picture, steps_label, buttons):
            box.append(w)
        view.set_content(box)
        d.set_child(view)

        def poll():
            if job_pending(job):
                return GLib.SOURCE_CONTINUE
            title.set_label(_("Reload the paper for the backs"))
            subtitle.set_visible(False)
            steps_label.set_visible(True)
            cont.set_sensitive(True)
            cont.grab_focus()
            return GLib.SOURCE_REMOVE

        source = GLib.timeout_add_seconds(1, poll)

        def finish(_button, answer):
            if GLib.main_context_default().find_source_by_id(source):
                GLib.source_remove(source)
            d.force_close()
            if answer == "continue" and self.lp(o, back, "Yazdır (backs)"):
                self.notify(_("Backs sent to the printer."))
            elif answer != "continue":
                self.notify(_("Backs cancelled."))

        cancel.connect("clicked", finish, "cancel")
        cont.connect("clicked", finish, "continue")
        d.present(self)


class Application(Adw.Application):
    def __init__(self, app_id=APP_ID):
        super().__init__(application_id=app_id, flags=Gio.ApplicationFlags.HANDLES_OPEN)
        about = Gio.SimpleAction.new("about", None)
        about.connect("activate", lambda *a: self.show_about())
        self.add_action(about)

    def window(self):
        return self.props.active_window or Window(self)

    def do_activate(self):
        self.window().present()

    def do_open(self, files, _n, _hint):
        w = self.window()
        w.add_files([f.get_path() for f in files])
        w.present()

    def show_about(self):
        Adw.AboutDialog(application_name="Yazdır", application_icon=APP_ID, version=__version__,
                        developer_name="Onur Neşvat", license_type=Gtk.License.MIT_X11,
                        website="https://github.com/onesvat/yazdir",
                        issue_url="https://github.com/onesvat/yazdir/issues").present(self.props.active_window)


def main():
    return Application().run(sys.argv)
