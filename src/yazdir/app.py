"""GTK 4 / libadwaita front end: N-up, booklet and guided manual duplex printing."""

import json
import sys
import threading
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from . import __version__, engine, printing  # noqa: E402
from .i18n import LANGUAGE, LANGUAGES, SETTINGS_FILE, _  # noqa: E402

APP_ID = "io.github.onesvat.Yazdir"
CACHE = Path(GLib.get_user_cache_dir()) / "yazdir"
DATA = Path(__file__).parent / "data"
CAL_KEYS = {"cal_reverse": "reverse", "cal_rotate180": "rotate180", "cal_note": "note"}


def choices():
    enhance = [("none", _("None")), ("sharp", _("Sharp black and white"))]
    if engine.ai_available():
        enhance.append(("ai", _("AI + sharp (best, slow)")))
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
        "enhance": enhance,
        "language": [("system", _("System default")), *LANGUAGES.items()],
    }


def load_settings():
    settings = dict(engine.DEFAULTS, calibrations={})
    try:
        settings.update(json.loads(SETTINGS_FILE.read_text()))
    except (OSError, ValueError):
        pass
    return settings


def diagram(name):
    path = DATA / f"{name}-{LANGUAGE}.svg"
    return str(path if path.exists() else DATA / f"{name}-en.svg")


class Window(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Yazdır", default_width=560, default_height=860)
        self.settings = load_settings()
        self.calibrations = self.settings["calibrations"]
        self.choices = choices()
        self.files = []
        self.file_rows = {}
        self.combos = {}
        self.busy = False
        self.loading = True

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
        names, default = printing.printers()
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
            return e

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

        calibrate = Adw.ButtonRow(title=_("Calibrate this printer…"), start_icon_name="printer-symbolic")
        calibrate.connect("activated", lambda *a: self.calibrate())
        self.cal_reverse = Adw.SwitchRow(title=_("Reverse order in the second pass"),
                                         subtitle=_("Set by calibration; change it if backs land on the wrong sheets"))
        self.cal_rotate = Adw.SwitchRow(title=_("Rotate backs 180°"),
                                        subtitle=_("Set by calibration; change it if backs come out upside down"))
        self.cal_note = Adw.EntryRow(title=_("How you reload the stack (shown every time)"))
        self.cal_section = section(_("Manual duplex calibration"), [], [calibrate, self.cal_reverse, self.cal_rotate, self.cal_note])

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
        for key in ("mode", "nup", "scale"):
            self.combos[key][0].connect("notify::selected", lambda *a: self.update_sensitivity())
        self.printer_row.connect("notify::selected", lambda *a: self.load_calibration())
        for w in (self.cal_reverse, self.cal_rotate):
            w.connect("notify::active", lambda *a: self.store_calibration())
        self.cal_note.connect("changed", lambda *a: self.store_calibration())

        self.load_calibration()
        self.summarize()
        self.update_sensitivity()
        self.loading = False

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
        """Restore print defaults; keep the printer, files, calibration and language."""
        d = engine.DEFAULTS
        for key, (row, keys) in self.combos.items():
            if key != "language":
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

    # --- Settings ------------------------------------------------------------

    @property
    def printer(self):
        return self.printers[self.printer_row.get_selected()]

    def calibration(self, printer=None):
        return self.calibrations.get(printer or self.printer)

    def load_calibration(self):
        cal = self.calibration() or {}
        loading, self.loading = self.loading, True
        self.cal_reverse.set_active(cal.get("reverse", engine.DEFAULTS["cal_reverse"]))
        self.cal_rotate.set_active(cal.get("rotate180", engine.DEFAULTS["cal_rotate180"]))
        self.cal_note.set_text(cal.get("note", ""))
        self.loading = loading
        self.cal_section.set_subtitle(_("Calibrated for {printer}").format(printer=self.printer) if cal
                                      else _("Not calibrated yet for {printer}").format(printer=self.printer))

    def store_calibration(self, **values):
        """Remember switch/note changes (or wizard results) for the selected printer."""
        if self.loading:
            return
        cal = {"reverse": self.cal_reverse.get_active(), "rotate180": self.cal_rotate.get_active(), "note": self.cal_note.get_text()}
        cal.update(values)
        self.calibrations[self.printer] = cal
        self.load_calibration()
        self.save_settings(self.options())

    def options(self):
        o = {key: self.selected(key) for key in self.combos}
        o.update(copies=int(self.copies.get_value()), collate=self.collate.get_active(), page_range=self.page_range.get_text(),
                 reverse=self.reverse.get_active(), border=self.border.get_active(), percent=self.percent.get_value(),
                 margin_mm=self.margin.get_value(), cal_reverse=self.cal_reverse.get_active(),
                 cal_rotate180=self.cal_rotate.get_active(), cal_note=self.cal_note.get_text().strip(),
                 printer=self.printer, last_folder=self.settings.get("last_folder"), calibrations=self.calibrations)
        return o

    def save_settings(self, o):
        stored = {k: v for k, v in o.items() if k not in CAL_KEYS}
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(json.dumps(stored, ensure_ascii=False, indent=2))

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

    def printer_ok(self):
        if self.printer not in printing.printers()[0]:
            self.error(_("No usable printer."))
            return False
        return True

    def start(self, action, skip_calibration_check=False):
        if self.busy:
            return
        o = self.options()
        if not self.files:
            self.notify(_("Add a file first."))
            return
        if action == "print" and not self.printer_ok():
            return
        self.save_settings(o)
        if action == "print" and o["mode"] != "simplex" and not self.calibration() and not skip_calibration_check:
            self.offer_calibration()
            return
        if action == "save":
            d = Gtk.FileDialog(title=_("Save as PDF"), initial_name=_("laid-out.pdf"))
            self.set_start_folder(d)
            d.save(self, None, lambda dlg, res: self._save_picked(dlg, res, o))
            return
        self.run_job(action, o, list(self.files))

    def offer_calibration(self):
        d = Adw.AlertDialog(heading=_("Calibrate two-sided printing first?"),
                            body=_("Yazdır needs to learn what your printer does with a reloaded stack. "
                                   "It takes 2 sheets and is done once per printer."))
        d.add_response("skip", _("Print anyway"))
        d.add_response("calibrate", _("Calibrate"))
        d.set_response_appearance("calibrate", Adw.ResponseAppearance.SUGGESTED)
        d.set_default_response("calibrate")
        d.connect("response", lambda _d, r: self.calibrate() if r == "calibrate" else self.start("print", True))
        d.present(self)

    def _save_picked(self, dialog, result, o):
        try:
            target = dialog.save_finish(result).get_path()
        except GLib.Error:
            return
        self.remember_folder(target)
        o["last_folder"] = self.settings["last_folder"]
        self.run_job("save", o, list(self.files), Path(target))

    def run_job(self, action, o, files, target=None, done=None):
        self.busy = True
        self.spinner.start()
        for b in (self.print_btn, self.preview_btn):
            b.set_sensitive(False)

        def worker():
            try:
                CACHE.mkdir(parents=True, exist_ok=True)
                pages = engine.load_pages(files, o["enhance"], CACHE, lambda m: GLib.idle_add(self.notify, m))
                sides, duplex, last_blank = engine.impose(pages, o)
                doc = engine.write_pdf(sides, target or CACHE / "document.pdf")
                GLib.idle_add(self._done, action, o, doc, duplex, last_blank, None, done)
            except Exception as e:
                GLib.idle_add(self._done, action, o, None, False, False, str(e), done)

        threading.Thread(target=worker, daemon=True).start()

    def _done(self, action, o, doc, duplex, last_blank, err, done):
        self.busy = False
        self.spinner.stop()
        for b in (self.print_btn, self.preview_btn):
            b.set_sensitive(True)
        if err:
            self.error(err)
        elif done:
            done(doc)
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
        elif self.submit(o, doc, "Yazdır", printing.job_options(o["paper"], o["quality"], o["copies"], o["collate"], o["reverse"])):
            self.notify(_("Sent to the printer."))

    def submit(self, o, pdf, title, options=None):
        try:
            return printing.submit(o["printer"], str(pdf), title, options or printing.job_options(o["paper"], o["quality"]))
        except printing.PrintError as e:
            self.error(_("Could not send to the printer:\n{error}").format(error=e))
            return None

    def wait_for(self, job, callback):
        """Call callback() once the job has left the queue."""
        def poll():
            if printing.job_pending(job):
                return GLib.SOURCE_CONTINUE
            callback()
            return GLib.SOURCE_REMOVE
        return GLib.timeout_add_seconds(1, poll)

    # --- Manual duplex -------------------------------------------------------

    def manual_duplex(self, o, front, back, sheets, last_blank):
        job = self.submit(o, front, "Yazdır (fronts)")
        if not job:
            return
        how = GLib.markup_escape_text(o["cal_note"]) if o["cal_note"] else _("the same way as during calibration")
        steps = [
            _("<b>1.</b> Take <b>all {n} sheets</b> from the output tray without changing their order.").format(n=sheets),
            _("<b>2.</b> Put them back into the input tray so the blank sides get printed: <b>{how}</b>.").format(how=how),
            _("<b>3.</b> Press <b>Continue</b>."),
        ]
        if last_blank:
            steps.append("\n<i>" + _("The top sheet has an empty back and will pass through blank. Don't remove it; "
                                     "it keeps the other sheets in order.") + "</i>")

        title = Gtk.Label(label=_("Printing the fronts ({n} sheets)…").format(n=sheets), wrap=True, css_classes=["title-2"])
        subtitle = Gtk.Label(label=_("When it finishes you will reload the paper as shown below."), wrap=True, css_classes=["dim-label"])
        picture = Gtk.Picture.new_for_filename(diagram("reload"))
        picture.set_content_fit(Gtk.ContentFit.CONTAIN)
        picture.set_size_request(-1, 240)
        steps_label = Gtk.Label(xalign=0, wrap=True, use_markup=True, label="\n".join(steps), visible=False)
        cancel = Gtk.Button(label=_("Cancel"), css_classes=["pill"])
        cont = Gtk.Button(label=_("Continue"), css_classes=["pill", "suggested-action"], sensitive=False)
        d = self.step_dialog(_("Manual duplex"), [title, subtitle, picture, steps_label], [cancel, cont])

        def ready():
            title.set_label(_("Reload the paper for the backs"))
            subtitle.set_visible(False)
            steps_label.set_visible(True)
            cont.set_sensitive(True)
            cont.grab_focus()

        source = self.wait_for(job, ready)

        def finish(_button, answer):
            if GLib.main_context_default().find_source_by_id(source):
                GLib.source_remove(source)
            d.force_close()
            if answer == "continue" and self.submit(o, back, "Yazdır (backs)"):
                self.notify(_("Backs sent to the printer."))
            elif answer != "continue":
                self.notify(_("Backs cancelled."))

        cancel.connect("clicked", finish, "cancel")
        cont.connect("clicked", finish, "continue")
        d.present(self)

    def step_dialog(self, heading, widgets, buttons):
        d = Adw.Dialog(title=heading, content_width=720, can_close=False)
        view = Adw.ToolbarView()
        view.add_top_bar(Adw.HeaderBar(show_end_title_buttons=False))
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16, margin_start=24, margin_end=24, margin_bottom=24, margin_top=6)
        for w in widgets:
            box.append(w)
        row = Gtk.Box(spacing=12, halign=Gtk.Align.CENTER, margin_top=8, homogeneous=True)
        for b in buttons:
            row.append(b)
        box.append(row)
        view.set_content(box)
        d.set_child(view)
        return d

    # --- Calibration wizard --------------------------------------------------

    def calibrate(self):
        """Print 4 numbered sides on 2 sheets, let the user reload them their own way, and ask what came out."""
        if not self.printer_ok() or self.busy:
            return
        printer = self.printer
        o = dict(self.options(), mode="duplex", flip="book", nup=1, page_range="", subset="all", copies=1, scale="fit",
                 enhance="none", border=False, cal_reverse=False, cal_rotate180=False)
        stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.SLIDE_LEFT, vhomogeneous=False)

        def page(name, heading, body, extra=()):
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
            box.append(Gtk.Label(label=heading, wrap=True, css_classes=["title-2"]))
            box.append(Gtk.Label(label=body, wrap=True, use_markup=True, xalign=0))
            for w in extra:
                box.append(w)
            stack.add_named(box, name)
            return box

        page("intro", _("Calibrate two-sided printing"),
             _("Printers differ in how they stack printed sheets and how a stack is fed back in. "
               "Yazdır will print pages <b>1</b> and <b>3</b> on two sheets, you put them back in, "
               "it prints pages <b>2</b> and <b>4</b>, and you tell it what you see.\n\n"
               "Put at least 2 sheets of plain paper in the printer."))
        note = Gtk.Entry(placeholder_text=_("e.g. take the stack as it is and slide it in, top edge first"))
        status = Gtk.Label(label=_("Printing pages 1 and 3…"), css_classes=["dim-label"])
        page("reload", _("Put the two sheets back"),
             _("When both sheets are out, put them back into the input tray <b>so that the blank sides will be printed</b>. "
               "Do whatever is easiest on your printer, keep the two sheets in the order they came out, and "
               "remember the move: you'll repeat it every time.\n\nDescribe it in a few words (optional, shown every time):"),
             [note, status])
        picture = Gtk.Picture.new_for_filename(diagram("calibration"))
        picture.set_content_fit(Gtk.ContentFit.CONTAIN)
        picture.set_size_request(-1, 170)
        answers = Gtk.Grid(column_spacing=10, row_spacing=10, column_homogeneous=True, sensitive=False)
        result_status = Gtk.Label(label=_("Printing pages 2 and 4…"), css_classes=["dim-label"])
        page("result", _("What is on the back of page 1?"),
             _("Take the sheet with <b>1</b> and turn it over <b>like a book page</b> (sideways). Which page do you see, "
               "and is its <b>TOP</b> mark at the top?"),
             [picture, answers, result_status])
        page("retry", _("The sheets went in the wrong way"),
             _("The backs were printed over the fronts or not at all, so the blank sides weren't facing the print side. "
               "Turn the stack over (or around) next time and calibrate again."))

        cancel = Gtk.Button(label=_("Cancel"), css_classes=["pill"])
        go = Gtk.Button(label=_("Print pages 1 and 3"), css_classes=["pill", "suggested-action"])
        d = self.step_dialog(_("Calibration"), [stack], [cancel, go])
        state = {"source": 0, "back": None}

        def stop_polling():
            if state["source"] and GLib.main_context_default().find_source_by_id(state["source"]):
                GLib.source_remove(state["source"])

        def close(*_a):
            stop_polling()
            d.force_close()

        def choose(reverse, rotate180):
            close()
            self.store_calibration(reverse=reverse, rotate180=rotate180, note=note.get_text().strip())
            self.cal_reverse.set_active(reverse)
            self.cal_rotate.set_active(rotate180)
            self.notify(_("Calibration saved for {printer}.").format(printer=printer))

        for i, (label, rev, rot) in enumerate([
            (_("2, right way up"), False, False), (_("2, upside down"), False, True),
            (_("4, right way up"), True, False), (_("4, upside down"), True, True),
        ]):
            b = Gtk.Button(label=label, css_classes=["pill"])
            b.connect("clicked", lambda _b, rev=rev, rot=rot: choose(rev, rot))
            answers.attach(b, i % 2, i // 2, 1, 1)
        other = Gtk.Button(label=_("Something else (printed over the front, or nothing)"), css_classes=["flat"])
        other.connect("clicked", lambda *a: (stack.set_visible_child_name("retry"), go.set_visible(False)))
        answers.attach(other, 0, 2, 2, 1)

        def fronts_printed():
            status.set_label(_("Done. Reload the sheets, then continue."))
            go.set_sensitive(True)

        def backs_printed():
            result_status.set_visible(False)
            answers.set_sensitive(True)

        def print_backs():
            go.set_visible(False)
            stack.set_visible_child_name("result")
            job = self.submit(o, state["back"], "Yazdır calibration (backs)")
            if job:
                state["source"] = self.wait_for(job, backs_printed)

        def laid_out(doc):
            front, back, _sheets = engine.split_passes(doc, 1, False, CACHE)
            state["back"] = back
            job = self.submit(o, front, "Yazdır calibration (fronts)")
            if not job:
                close()
                return
            stack.set_visible_child_name("reload")
            go.set_label(_("Print pages 2 and 4"))
            go.set_sensitive(False)
            state["source"] = self.wait_for(job, fronts_printed)

        def on_go(_b):
            if stack.get_visible_child_name() == "intro":
                go.set_sensitive(False)
                self.run_job("calibrate", o, [engine.test_document(CACHE, _("TOP"))], done=laid_out)
            else:
                print_backs()

        go.connect("clicked", on_go)
        cancel.connect("clicked", close)
        CACHE.mkdir(parents=True, exist_ok=True)
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
