#!/usr/bin/env bash
# Install Yazdır for the current user (no root needed).
#   ./install.sh             install or update
#   ./install.sh --with-ai   also download Real-ESRGAN for AI image upscaling (~45 MB)
#   ./install.sh --uninstall remove it again (settings are kept; add --purge to delete them)
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ID="io.github.onesvat.Yazdir"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
LIB="$DATA/yazdir"
BIN="$HOME/.local/bin"
ESRGAN_URL="https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesrgan-ncnn-vulkan-20220424-ubuntu.zip"

with_ai=false uninstall=false purge=false
for arg in "$@"; do
  case "$arg" in
    --with-ai) with_ai=true ;;
    --uninstall) uninstall=true ;;
    --purge) purge=true ;;
    -h|--help) sed -n '2,5p' "$0"; exit 0 ;;
    *) echo "Unknown option: $arg" >&2; exit 1 ;;
  esac
done

say() { printf '\033[1m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[33mwarning:\033[0m %s\n' "$*" >&2; }

if $uninstall; then
  say "Removing Yazdır"
  rm -rf "$LIB/venv"
  rm -f "$BIN/yazdir" "$DATA/applications/$APP_ID.desktop" "$DATA/icons/hicolor/scalable/apps/$APP_ID.svg" \
        "$DATA/nautilus/scripts/Yazdır…"
  if $purge; then
    rm -rf "$LIB" "${XDG_CONFIG_HOME:-$HOME/.config}/yazdir" "${XDG_CACHE_HOME:-$HOME/.cache}/yazdir"
  fi
  command -v update-desktop-database >/dev/null && update-desktop-database "$DATA/applications" || true
  say "Done"
  exit 0
fi

say "Checking requirements"
# Find a Python that has the GTK 4 / libadwaita bindings (a version manager's python3 usually doesn't).
find_python() {
  for py in "${PYTHON:-}" python3 /usr/bin/python3; do
    [[ -n "$py" ]] && command -v "$py" >/dev/null || continue
    "$py" - <<'PY' 2>/dev/null && { command -v "$py"; return 0; }
import gi
gi.require_version("Gtk", "4.0"); gi.require_version("Adw", "1")
from gi.repository import Adw
assert (Adw.MAJOR_VERSION, Adw.MINOR_VERSION) >= (1, 6)
PY
  done
  return 1
}
missing=()
PY_BIN="$(find_python)" || missing+=("GTK 4 + libadwaita (>= 1.6) Python bindings")
if ((${#missing[@]})); then
  echo "Missing: ${missing[*]}" >&2
  cat >&2 <<'HINT'
Fedora:        sudo dnf install python3-gobject gtk4 libadwaita python3-cups
Debian/Ubuntu: sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 python3-cups
Arch:          sudo pacman -S python-gobject gtk4 libadwaita python-pycups
HINT
  exit 1
fi
if ! "$PY_BIN" -c "import cups" 2>/dev/null && ! command -v lp >/dev/null; then
  warn "Neither pycups (python3-cups) nor the lp command was found: Yazdır can lay out and save PDFs but not print."
fi

say "Creating environment in $LIB/venv (using $PY_BIN)"
mkdir -p "$LIB" "$BIN"
if command -v uv >/dev/null; then
  uv venv -q --allow-existing --python "$PY_BIN" --system-site-packages "$LIB/venv"
  uv pip install -q --python "$LIB/venv/bin/python" --reinstall-package yazdir "$REPO"
else
  "$PY_BIN" -m venv --system-site-packages "$LIB/venv"
  "$LIB/venv/bin/pip" install -q --upgrade "$REPO"
fi
ln -sf "$LIB/venv/bin/yazdir" "$BIN/yazdir"

say "Adding menu entry, icon and file manager action"
install -Dm644 "$REPO/data/$APP_ID.svg" "$DATA/icons/hicolor/scalable/apps/$APP_ID.svg"
mkdir -p "$DATA/applications"
sed "s|^Exec=yazdir|Exec=$BIN/yazdir|" "$REPO/data/$APP_ID.desktop" > "$DATA/applications/$APP_ID.desktop"
mkdir -p "$DATA/nautilus/scripts"
cat > "$DATA/nautilus/scripts/Yazdır…" <<SCRIPT
#!/usr/bin/env bash
exec "$BIN/yazdir" "\$@"
SCRIPT
chmod +x "$DATA/nautilus/scripts/Yazdır…"
command -v update-desktop-database >/dev/null && update-desktop-database "$DATA/applications" || true
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q -t "$DATA/icons/hicolor" || true

if $with_ai; then
  say "Downloading Real-ESRGAN (ncnn/Vulkan build)"
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT
  curl -fL --progress-bar -o "$tmp/esrgan.zip" "$ESRGAN_URL"
  mkdir -p "$LIB/realesrgan"
  unzip -qo "$tmp/esrgan.zip" -d "$tmp/x"
  cp -r "$tmp/x/realesrgan-ncnn-vulkan" "$tmp/x/models" "$LIB/realesrgan/"
  chmod +x "$LIB/realesrgan/realesrgan-ncnn-vulkan"
fi

say "Installed. Start it from the app menu or run: yazdir [files…]"
case ":$PATH:" in *":$BIN:"*) ;; *) warn "$BIN is not in your PATH." ;; esac
