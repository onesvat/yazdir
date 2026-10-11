# Development tasks. Run `just` to list them.

default:
    @just --list

# Create the development environment (uses the system Python for GTK bindings)
setup:
    uv venv --python /usr/bin/python3 --system-site-packages .venv
    uv pip install --python .venv/bin/python -e . pytest ruff

# Run the tests
test:
    .venv/bin/pytest -q

# Lint
lint:
    .venv/bin/ruff check src tests tools

# Run the app from the source tree (LANG=en or tr)
run lang="":
    YAZDIR_LANG={{lang}} .venv/bin/python -m yazdir

# Rebuild the example PDFs in English and Turkish (needs typst)
examples:
    for f in examples/src/[0-9]-*.typ; do \
      for l in en tr; do typst compile --root examples/src --input lang=$l "$f" "examples/$l/$(basename "$f" .typ).pdf"; done; \
    done

# Refresh the translation template and merge it into the Turkish catalogue
pot:
    xgettext --language=Python --keyword=_ --from-code=UTF-8 --no-wrap --package-name=yazdir -o src/yazdir/locale/yazdir.pot src/yazdir/app.py src/yazdir/engine.py
    msgmerge -q --no-wrap -U --backup=none src/yazdir/locale/tr.po src/yazdir/locale/yazdir.pot
    msgfmt -c --statistics -o /dev/null src/yazdir/locale/tr.po

# Re-render the README screenshots
screenshots:
    for l in en tr; do YAZDIR_LANG=$l .venv/bin/python tools/screenshots.py docs/screenshots/$l; done

# Build and install the Flatpak for the current user (needs org.flatpak.Builder and org.gnome.Sdk//51)
flatpak:
    flatpak run org.flatpak.Builder --user --install --force-clean --install-deps-from=flathub build-dir build-aux/flatpak/io.github.onesvat.Yazdir.yml

# Build a single-file Flatpak bundle for a GitHub release (runtime comes from Flathub on install)
bundle:
    flatpak run org.flatpak.Builder --user --force-clean --install-deps-from=flathub --repo=repo build-dir build-aux/flatpak/io.github.onesvat.Yazdir.yml
    flatpak build-bundle repo "yazdir-$(.venv/bin/python -c 'import sys; sys.path.insert(0, "src"); import yazdir; print(yazdir.__version__)')-x86_64.flatpak" io.github.onesvat.Yazdir --runtime-repo=https://dl.flathub.org/repo/flathub.flatpakrepo

# Validate the desktop entry and AppStream metadata
validate:
    desktop-file-validate data/io.github.onesvat.Yazdir.desktop
    appstreamcli validate --no-net data/io.github.onesvat.Yazdir.metainfo.xml
