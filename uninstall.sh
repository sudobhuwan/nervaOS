#!/usr/bin/env bash
# NervaOS Ultimate Uninstall Controller
# Idempotent; removes all install artifacts. Matches install.sh exactly.

set -e

# ─── Paths (must match install.sh) ──────────────────────────────────────────
INSTALL_DIR="${INSTALL_DIR:-$HOME/.local/share/nervaos}"
CONFIG_DIR="${CONFIG_DIR:-$HOME/.config/nervaos}"
SYSTEMD_DIR="$HOME/.config/systemd/user"
DESKTOP_DIR="$HOME/.local/share/applications"
BIN_DIR="$HOME/.local/bin"
AUTOSTART_DIR="$HOME/.config/autostart"

# ─── Options ────────────────────────────────────────────────────────────────
PURGE=false
KEEP_CONFIG=false
YES=false

usage() {
    cat << 'EOF'
Usage: ./uninstall.sh [OPTIONS]

NervaOS Ultimate Uninstall Controller. Removes service, desktop entries,
autostart, hotkey, symlinks, venv. Idempotent; safe to re-run.

Options:
  -y, --yes         Non-interactive; assume yes to prompts
  --purge           Remove config (e.g. ~/.config/nervaos) without asking
  --keep-config     Never remove config; keep ~/.config/nervaos
  -h, --help        Show this help

EOF
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -y|--yes)       YES=true; shift ;;
        --purge)        PURGE=true; shift ;;
        --keep-config)  KEEP_CONFIG=true; shift ;;
        -h|--help)      usage ;;
        *)              echo "Unknown option: $1"; usage ;;
    esac
done

echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║         NervaOS Ultimate Uninstall Controller                 ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

if [[ "$YES" != "true" ]]; then
    echo "This will stop the daemon, kill nerva-ui, remove service,"
    echo "desktop entries, autostart, hotkey, symlinks, and venv."
    echo "Config (~/.config/nervaos) is kept unless you use --purge."
    echo ""
    read -p "Continue? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Uninstall cancelled."
        exit 0
    fi
    echo ""
fi

# ─── Kill running UI processes ──────────────────────────────────────────────
echo "→ Stopping NervaOS UI processes..."
pkill -x nerva-ui 2>/dev/null || true
pkill -f "src.ui.main" 2>/dev/null || true
echo "  ✓ UI processes stopped"

# ─── Systemd service ────────────────────────────────────────────────────────
echo "→ Stopping and disabling nerva-service..."
systemctl --user stop nerva-service.service 2>/dev/null || true
systemctl --user disable nerva-service.service 2>/dev/null || true
echo "→ Removing systemd unit..."
rm -f "$SYSTEMD_DIR/nerva-service.service"
systemctl --user daemon-reload 2>/dev/null || true
echo "  ✓ Service removed"

# ─── Desktop entries (must match install) ────────────────────────────────────
echo "→ Removing desktop entries..."
rm -f "$DESKTOP_DIR/com.nervaos.ui.desktop"
rm -f "$AUTOSTART_DIR/nerva-ui.desktop"
update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
echo "  ✓ Applications + autostart entries removed"

# ─── D-Bus activation ───────────────────────────────────────────────────────
echo "→ Removing D-Bus service (com.nervaos.daemon)..."
DBUS_SERVICES_DIR="$HOME/.local/share/dbus-1/services"
rm -f "$DBUS_SERVICES_DIR/com.nervaos.daemon.service"
echo "  ✓ D-Bus service removed"

# ─── Symlinks ───────────────────────────────────────────────────────────────
echo "→ Removing launcher symlinks..."
rm -f "$BIN_DIR/nerva-daemon"
rm -f "$BIN_DIR/nerva-ui"
echo "  ✓ Symlinks removed"

# ─── Hotkey (Cinnamon) ──────────────────────────────────────────────────────
echo "→ Removing hotkey (Super+Space)..."
if command -v dconf &>/dev/null; then
    dconf reset -f /org/cinnamon/desktop/keybindings/custom-keybindings/nervaos/ 2>/dev/null || true
    EXISTING=$(dconf read /org/cinnamon/desktop/keybindings/custom-list 2>/dev/null || echo "[]")
    if [[ "$EXISTING" =~ nervaos ]]; then
        NEW=$(python3 -c "
import ast, sys
s = sys.stdin.read().strip()
try:
    lst = ast.literal_eval(s)
    lst = [x for x in lst if x != 'nervaos']
    print(repr(lst))
except Exception:
    print(s)
" <<< "$EXISTING" 2>/dev/null || echo "$EXISTING")
        dconf write /org/cinnamon/desktop/keybindings/custom-list "$NEW" 2>/dev/null || true
    fi
    echo "  ✓ Hotkey removed"
else
    echo "  ⚠ dconf not found; hotkey left as-is"
fi

# ─── Venv / install dir ─────────────────────────────────────────────────────
echo "→ Removing virtual environment and install data..."
rm -rf "$INSTALL_DIR"
echo "  ✓ $INSTALL_DIR removed"

# ─── Config ─────────────────────────────────────────────────────────────────
if [[ "$KEEP_CONFIG" == "true" ]]; then
    echo "→ Config: kept (--keep-config)"
elif [[ "$PURGE" == "true" ]]; then
    echo "→ Removing config..."
    rm -rf "$CONFIG_DIR"
    echo "  ✓ $CONFIG_DIR removed"
else
    echo ""
    read -p "Remove config ($CONFIG_DIR)? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf "$CONFIG_DIR"
        echo "  ✓ Config removed"
    else
        echo "  Config preserved at $CONFIG_DIR"
    fi
fi

echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║              Uninstall complete                                ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
