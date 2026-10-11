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
