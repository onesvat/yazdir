# Changelog

## 1.1.1 — 2026-10-11

- Screenshots retaken at the default window size, with rounded corners and shadow, for app stores.

## 1.1.0 — 2026-10-11

Works with any printer that can't print on both sides by itself.

- New calibration wizard: two sheets, one question ("what is on the back of page 1?"), and Yazdır knows how your
  printer stacks and feeds paper. Calibration is stored per printer and offered before the first two-sided job.
- Generic reload instructions, plus your own short note on how you put the stack back.
- Printing goes through pycups when available (and always inside Flatpak), with `lp` as a fallback.
- Images are converted with Pillow; ImageMagick is no longer needed. Test pages are generated as native PDF.
- Flatpak manifest, AppStream metadata and a validated desktop entry, ready for Flathub.
- Removed the printer-specific documentation.

## 1.0.0 — 2026-10-11

First public release.

- Guided manual duplex printing with a feed diagram, a print-progress wait and a calibration (reverse order, rotate backs 180°).
- Booklet imposition (fold in half, reads in order) and 1/2/4/6/9/16 pages per sheet with automatic grid choice.
- "Book" (sideways) and "calendar" (upwards) flip, correct for portrait and landscape sheets.
- Blank backs get an almost invisible dot so drivers cannot skip them and break the sheet order.
- Page ranges, odd/even subsets, copies, collation, reverse order, scaling, rotation, margins, borders.
- Image printing with optional sharp 600 DPI black and white or Real-ESRGAN AI upscaling.
- Advanced settings tucked into collapsible sections that show what differs from the defaults.
- English and Turkish interface, in-app language switch.
- Bilingual example set (planner, notes, booklet, lists, recipe cards, calendar, trackers) that doubles as a duplex test.
