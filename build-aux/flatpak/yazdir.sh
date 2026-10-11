#!/bin/sh
# Flatpak launcher: the package lives in /app/share/yazdir.
export PYTHONPATH="/app/share/yazdir${PYTHONPATH:+:$PYTHONPATH}"
exec python3 -m yazdir "$@"
