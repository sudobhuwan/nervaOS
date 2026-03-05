#!/usr/bin/env bash
# NervaOS Ultimate Install Controller
# Idempotent, option-rich, full control over system deps, Python env, services, desktop, hotkeys, autostart.

set -e

# ─── Paths (single source of truth) ─────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="${INSTALL_DIR:-$HOME/.local/share/nervaos}"
VENV_PATH="$INSTALL_DIR/venv"
CONFIG_DIR="${CONFIG_DIR:-$HOME/.config/nervaos}"
SYSTEMD_DIR="$HOME/.config/systemd/user"
DESKTOP_DIR="$HOME/.local/share/applications"
BIN_DIR="$HOME/.local/bin"
AUTOSTART_DIR="$HOME/.config/autostart"
DBUS_SERVICES_DIR="$HOME/.local/share/dbus-1/services"

# ─── Options ────────────────────────────────────────────────────────────────
DO_DEPS=true
DO_HOTKEY=true
DO_AUTOSTART=true
YES=false

usage() {
    cat << 'EOF'
Usage: ./install.sh [OPTIONS]

NervaOS Ultimate Install Controller. Idempotent; safe to re-run (e.g. upgrade).

Options:
  -y, --yes           Non-interactive; assume yes to prompts
  --no-deps           Skip system (apt) dependencies
  --no-hotkey         Skip Cinnamon Super+Space hotkey
  --no-autostart      Skip adding NervaOS to session autostart
  -h, --help          Show this help

EOF
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -y|--yes)    YES=true; shift ;;
        --no-deps)   DO_DEPS=false; shift ;;
        --no-hotkey) DO_HOTKEY=false; shift ;;
        --no-autostart) DO_AUTOSTART=false; shift ;;
        -h|--help)   usage ;;
        *)           echo "Unknown option: $1"; usage ;;
    esac
done

# ─── Banner & confirmation ──────────────────────────────────────────────────
echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║         NervaOS Ultimate Install Controller                   ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

if [[ "$YES" != "true" ]]; then
    echo "This will install dependencies, Python venv, systemd service,"
    echo "desktop entry, optional hotkey (Super+Space) and autostart."
    echo "You may be prompted for sudo (apt)."
    echo ""
    read -p "Continue? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Installation cancelled."
        exit 0
    fi
    echo ""
fi

# ─── Phase 1: System dependencies ───────────────────────────────────────────
if [[ "$DO_DEPS" == "true" ]]; then
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "PHASE 1: System dependencies"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""

    echo "→ Updating package list..."
    sudo apt update -qq

    echo "→ Checking Python..."
    PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
    PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
    PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)
    if [[ "${PYTHON_MAJOR:-0}" -lt 3 ]] || [[ "${PYTHON_MINOR:-0}" -lt 11 ]]; then
        echo "  Installing Python 3.11+..."
        sudo apt install -y python3.11 python3.11-venv python3.11-dev || true
    fi
    echo "  ✓ Python $PYTHON_VERSION"

    echo "→ Installing system packages..."
    sudo apt install -y \
        python3-pip python3-venv python3-dev \
        libgtk-4-dev gir1.2-gtk-4.0 \
        libadwaita-1-dev gir1.2-adw-1 \
        libcairo2-dev libgirepository1.0-dev libgirepository-2.0-dev pkg-config \
        portaudio19-dev python3-pyaudio \
        espeak espeak-ng espeak-data libespeak-dev \
        alsa-utils pulseaudio dbus-x11 \
        libwnck-3-dev gir1.2-wnck-3.0 wmctrl \
        gnome-keyring libnotify-bin libnotify-dev dconf-cli \
        > /dev/null 2>&1 || true
    echo "  ✓ System dependencies done"

    echo "→ Verifying..."
    python3 -c "import gi; gi.require_version('Gtk', '4.0')" 2>/dev/null && echo "  ✓ GTK4" || echo "  ⚠ GTK4 check skipped"
    command -v espeak &>/dev/null && echo "  ✓ eSpeak" || echo "  ⚠ eSpeak check skipped"
    echo ""
else
    echo "━━ Skipping system dependencies (--no-deps)"
    echo ""
fi

# ─── Phase 2: Python environment ────────────────────────────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "PHASE 2: Python environment"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo "→ Creating directories..."
mkdir -p "$INSTALL_DIR" "$INSTALL_DIR/data" "$CONFIG_DIR" "$CONFIG_DIR/automation"
mkdir -p "$SYSTEMD_DIR" "$DESKTOP_DIR" "$BIN_DIR" "$AUTOSTART_DIR"
chmod 700 "$INSTALL_DIR/data" 2>/dev/null || true
echo "  ✓ Directories ready"

echo "→ Virtual environment..."
if [[ ! -f "$VENV_PATH/bin/activate" ]]; then
    python3 -m venv "$VENV_PATH"
    echo "  ✓ Venv created"
else
    echo "  ✓ Venv exists (idempotent)"
fi
# shellcheck source=/dev/null
source "$VENV_PATH/bin/activate"

echo "→ pip & Python deps..."
pip install -q --upgrade pip setuptools wheel
pip install -q -r "$SCRIPT_DIR/requirements.txt"
echo "  ✓ Python dependencies installed"
echo ""

# ─── Phase 3: Configuration ─────────────────────────────────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "PHASE 3: Configuration"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

CFG_DONE=
mkdir -p "$CONFIG_DIR/config"
if [[ ! -f "$CONFIG_DIR/nervaos.conf" ]]; then
    cp "$SCRIPT_DIR/config/default.conf" "$CONFIG_DIR/nervaos.conf" 2>/dev/null || true
    echo "  ✓ nervaos.conf"
    CFG_DONE=1
fi
if [[ ! -f "$CONFIG_DIR/automation/workflows.yaml" ]]; then
    cp "$SCRIPT_DIR/config/workflows.example.yaml" "$CONFIG_DIR/automation/workflows.yaml" 2>/dev/null || true
    echo "  ✓ workflows.yaml"
    CFG_DONE=1
fi
if [[ ! -f "$CONFIG_DIR/config/api_keys.json" ]]; then
    cp "$SCRIPT_DIR/config/api_keys.example.json" "$CONFIG_DIR/config/api_keys.json" 2>/dev/null || true
    echo "  ✓ config/api_keys.json (fill keys; or use Settings)"
    CFG_DONE=1
fi
if [[ ! -f "$SCRIPT_DIR/.env" ]]; then
    cp "$SCRIPT_DIR/env.example" "$SCRIPT_DIR/.env" 2>/dev/null || true
    echo "  ✓ .env created (add API keys)"
    CFG_DONE=1
fi
[[ -z "$CFG_DONE" ]] && echo "  ✓ Config present (nervaos.conf, workflows, config, .env)"
echo ""

# ─── Phase 4: Service & desktop & launchers ─────────────────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "PHASE 4: Service, desktop, launchers"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo "→ Systemd service..."
sed -e "s|%h|$HOME|g" -e "s|%P|$SCRIPT_DIR|g" "$SCRIPT_DIR/systemd/nerva-service.service" > "$SYSTEMD_DIR/nerva-service.service"
systemctl --user daemon-reload
systemctl --user enable nerva-service.service 2>/dev/null || true
systemctl --user restart nerva-service.service 2>/dev/null || true
echo "  ✓ nerva-service enabled (and restarted if already running)"

echo "→ Desktop entry (applications)..."
DESKTOP_IN="$SCRIPT_DIR/desktop/com.nervaos.ui.desktop.in"
DESKTOP_OUT="$DESKTOP_DIR/com.nervaos.ui.desktop"
if [[ -f "$DESKTOP_IN" ]]; then
    sed "s|@BIN_DIR@|$BIN_DIR|g" "$DESKTOP_IN" > "$DESKTOP_OUT"
else
    # Fallback: minimal desktop with Exec from BIN_DIR
    cat > "$DESKTOP_OUT" << EOF
[Desktop Entry]
Name=NervaOS
Comment=AI-powered system assistant
Exec=$BIN_DIR/nerva-ui
Icon=system-search-symbolic
Terminal=false
Type=Application
Categories=Utility;System;
StartupWMClass=com.nervaos.ui
EOF
fi
update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
echo "  ✓ $DESKTOP_OUT"

echo "→ Launcher symlinks..."
ln -sf "$SCRIPT_DIR/bin/nerva-daemon" "$BIN_DIR/nerva-daemon"
ln -sf "$SCRIPT_DIR/bin/nerva-ui" "$BIN_DIR/nerva-ui"
chmod +x "$SCRIPT_DIR/bin/nerva-daemon" "$SCRIPT_DIR/bin/nerva-ui" 2>/dev/null || true
echo "  ✓ nerva-daemon, nerva-ui in \$PATH"

echo "→ D-Bus activation (com.nervaos.daemon)..."
mkdir -p "$DBUS_SERVICES_DIR"
DBUS_SVC_IN="$SCRIPT_DIR/dbus/com.nervaos.daemon.service.in"
DBUS_SVC_OUT="$DBUS_SERVICES_DIR/com.nervaos.daemon.service"
if [[ -f "$DBUS_SVC_IN" ]]; then
    sed "s|@BIN_DIR@|$BIN_DIR|g" "$DBUS_SVC_IN" > "$DBUS_SVC_OUT"
    echo "  ✓ $DBUS_SVC_OUT"
else
    echo "  ⚠ D-Bus service template missing, skipping"
fi

# ─── Hotkey (Cinnamon) ──────────────────────────────────────────────────────
if [[ "$DO_HOTKEY" == "true" ]] && command -v dconf &>/dev/null; then
    echo "→ Hotkey (Super+Space)..."
    EXISTING=$(dconf read /org/cinnamon/desktop/keybindings/custom-list 2>/dev/null || true)
    EXISTING="${EXISTING:-[]}"
    EXISTING=$(printf '%s' "$EXISTING" | tr -d '\n' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
    if [[ -z "$EXISTING" || "$EXISTING" != "["* ]]; then
        EXISTING="[]"
    fi
    if [[ ! "$EXISTING" =~ nervaos ]]; then
        NEW=$(python3 -c "
import ast, sys
s = sys.stdin.read().strip()
try:
    lst = ast.literal_eval(s) if s and s != '[]' else []
    if not isinstance(lst, list):
        lst = []
    lst = [x for x in lst if isinstance(x, str)]
    if 'nervaos' not in lst:
        lst.append('nervaos')
    print(repr(lst))
except Exception:
    print(\"['nervaos']\")
" <<< "$EXISTING" 2>/dev/null || echo "['nervaos']")
        set +e
        dconf write /org/cinnamon/desktop/keybindings/custom-list "$NEW" 2>/dev/null
        d1=$?
        dconf write /org/cinnamon/desktop/keybindings/custom-keybindings/nervaos/name "'NervaOS Spotlight'" 2>/dev/null
        d2=$?
        dconf write /org/cinnamon/desktop/keybindings/custom-keybindings/nervaos/command "'nerva-ui --overlay'" 2>/dev/null
        d3=$?
        dconf write /org/cinnamon/desktop/keybindings/custom-keybindings/nervaos/binding "['<Super>space']" 2>/dev/null
        d4=$?
        set -e
        if [[ $d1 -eq 0 && $d2 -eq 0 && $d3 -eq 0 && $d4 -eq 0 ]]; then
            echo "  ✓ Super+Space → nerva-ui --overlay"
        else
            echo "  ⚠ Hotkey setup skipped (not Cinnamon? dconf path missing)"
        fi
    else
        echo "  ✓ Hotkey already configured"
    fi
elif [[ "$DO_HOTKEY" == "true" ]]; then
    echo "→ Hotkey: dconf not found, skipping. Set manually: nerva-ui --overlay"
else
    echo "→ Hotkey: skipped (--no-hotkey)"
fi

# ─── Autostart ──────────────────────────────────────────────────────────────
if [[ "$DO_AUTOSTART" == "true" ]]; then
    echo "→ Autostart (bubble)..."
    cat > "$AUTOSTART_DIR/nerva-ui.desktop" << EOF
[Desktop Entry]
Type=Application
Name=NervaOS Assistant
Comment=AI OS Intelligence Layer
Exec=$BIN_DIR/nerva-ui --minimized
Icon=system-search-symbolic
Terminal=false
Categories=Utility;
X-GNOME-Autostart-enabled=true
X-GNOME-Autostart-Delay=5
EOF
    echo "  ✓ $AUTOSTART_DIR/nerva-ui.desktop"
else
    echo "→ Autostart: skipped (--no-autostart)"
fi

echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║              Installation complete                             ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo "Configure API keys (pick one):"
echo "  • Settings UI:  nerva-ui → ⚙ Settings → API → paste keys → Save"
echo "  • JSON:         nano ~/.config/nervaos/config/api_keys.json"
echo "  • .env:         nano $SCRIPT_DIR/.env"
echo "  GEMINI_API_KEY, OPENAI_API_KEY, etc.  DEEPGRAM_API_KEY (optional, voice)"
echo ""
echo "Start:   systemctl --user start nerva-service"
echo "Status:  systemctl --user status nerva-service"
echo "Launch:  nerva-ui   |   Super+Space (overlay)"
echo "Logs:    journalctl --user -u nerva-service -f"
echo ""
