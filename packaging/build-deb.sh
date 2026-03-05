#!/bin/bash
#
# NervaOS .deb Package Builder
#
# Creates a distributable Debian package for NervaOS
# Output: nervaos_<version>_amd64.deb
#

set -euo pipefail

VERSION="1.0.0"
PACKAGE_NAME="nervaos"
MAINTAINER="NervaOS Team <team@nervaos.com>"
DESCRIPTION="AI-powered intelligence layer for Linux Mint"
HOMEPAGE="https://nervaos.com"
ARCHITECTURE="amd64"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BUILD_DIR="$SCRIPT_DIR/deb/build"
OUTPUT_DIR="$SCRIPT_DIR/deb"
PKG_DIR="$BUILD_DIR/${PACKAGE_NAME}_${VERSION}_${ARCHITECTURE}"
APP_DIR="$PKG_DIR/opt/nervaos"
VENV_DIR="$APP_DIR/venv"

log() {
    echo "[$(date '+%H:%M:%S')] $1"
}

cleanup() {
    log "Cleaning up build directory..."
    rm -rf "$BUILD_DIR"
}

log "Building NervaOS .deb package v${VERSION}..."

cleanup
mkdir -p "$BUILD_DIR" "$OUTPUT_DIR"

mkdir -p \
    "$PKG_DIR/DEBIAN" \
    "$APP_DIR" \
    "$PKG_DIR/usr/bin" \
    "$PKG_DIR/usr/share/applications" \
    "$PKG_DIR/usr/share/dbus-1/services" \
    "$PKG_DIR/usr/lib/systemd/user" \
    "$PKG_DIR/etc/nervaos" \
    "$PKG_DIR/etc/xdg/autostart"

log "Copying application files..."
cp -r "$PROJECT_ROOT/src" "$APP_DIR/"
cp "$PROJECT_ROOT/requirements.txt" "$APP_DIR/"
cp "$PROJECT_ROOT/config/default.conf" "$PKG_DIR/etc/nervaos/nervaos.conf"

log "Creating bundled Python virtual environment..."
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"

log "Creating launchers..."
cat > "$PKG_DIR/usr/bin/nerva-ui" << 'EOF'
#!/usr/bin/env bash
set -e
APP_DIR="/opt/nervaos"
VENV_PATH="$APP_DIR/venv"
export PYTHONPATH="$APP_DIR:${PYTHONPATH:-}"
exec "$VENV_PATH/bin/python" -m src.ui.main "$@"
EOF

cat > "$PKG_DIR/usr/bin/nerva-daemon" << 'EOF'
#!/usr/bin/env bash
set -e
APP_DIR="/opt/nervaos"
VENV_PATH="$APP_DIR/venv"
export PYTHONPATH="$APP_DIR:${PYTHONPATH:-}"
exec "$VENV_PATH/bin/python" -m src.core.service "$@"
EOF

cat > "$PKG_DIR/usr/bin/com.nervaos.daemon" << 'EOF'
#!/usr/bin/env bash
exec /usr/bin/nerva-daemon "$@"
EOF

chmod +x "$PKG_DIR/usr/bin/nerva-ui" "$PKG_DIR/usr/bin/nerva-daemon" "$PKG_DIR/usr/bin/com.nervaos.daemon"

log "Creating desktop entry..."
DESKTOP_IN="$PROJECT_ROOT/desktop/com.nervaos.ui.desktop.in"
DESKTOP_OUT="$PKG_DIR/usr/share/applications/com.nervaos.ui.desktop"
if [[ -f "$DESKTOP_IN" ]]; then
    sed 's|@BIN_DIR@|/usr/bin|g' "$DESKTOP_IN" > "$DESKTOP_OUT"
else
    cat > "$DESKTOP_OUT" << 'EOF'
[Desktop Entry]
Name=NervaOS
GenericName=AI Assistant
X-GNOME-FullName=NervaOS AI Assistant
Comment=AI-powered system assistant
Exec=/usr/bin/nerva-ui
Icon=system-search-symbolic
Terminal=false
Type=Application
Categories=Utility;
Keywords=NervaOS;nervaos;nerva;AI;Assistant;System;Chat;
StartupNotify=true
StartupWMClass=com.nervaos.ui
EOF
fi

# Alias desktop id improves discoverability in app search on some desktop menus.
cp "$DESKTOP_OUT" "$PKG_DIR/usr/share/applications/nervaos.desktop"

log "Creating D-Bus service entry..."
DBUS_IN="$PROJECT_ROOT/dbus/com.nervaos.daemon.service.in"
DBUS_OUT="$PKG_DIR/usr/share/dbus-1/services/com.nervaos.daemon.service"
if [[ -f "$DBUS_IN" ]]; then
    sed 's|@BIN_DIR@|/usr/bin|g' "$DBUS_IN" > "$DBUS_OUT"
else
    cat > "$DBUS_OUT" << 'EOF'
[D-BUS Service]
Name=com.nervaos.daemon
Exec=/usr/bin/nerva-daemon
EOF
fi

log "Creating desktop autostart entry..."
cat > "$PKG_DIR/etc/xdg/autostart/com.nervaos.ui.desktop" << 'EOF'
[Desktop Entry]
Type=Application
Name=NervaOS
Comment=AI-powered system assistant
Exec=/usr/bin/nerva-ui --bubble
Icon=system-search-symbolic
Terminal=false
X-GNOME-Autostart-enabled=true
StartupNotify=false
EOF

log "Creating systemd user service..."
cat > "$PKG_DIR/usr/lib/systemd/user/nerva-service.service" << 'EOF'
[Unit]
Description=NervaOS Intelligence Daemon
After=graphical-session.target dbus.service
PartOf=graphical-session.target

[Service]
Type=simple
WorkingDirectory=/opt/nervaos
ExecStart=/opt/nervaos/venv/bin/python -m src.core.service
Restart=on-failure
RestartSec=5
Environment=DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/%U/bus
Environment=PYTHONPATH=/opt/nervaos
MemoryMax=200M
CPUQuota=50%

[Install]
WantedBy=default.target
EOF

log "Creating DEBIAN control scripts..."
cat > "$PKG_DIR/DEBIAN/control" << EOF
Package: ${PACKAGE_NAME}
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: ${ARCHITECTURE}
Maintainer: ${MAINTAINER}
Homepage: ${HOMEPAGE}
Description: ${DESCRIPTION}
 NervaOS is a native, OS-integrated AI intelligence layer for Linux Mint.
 It provides context-aware assistance, safe file operations with automatic
 backups, and seamless integration with the Cinnamon desktop environment.
Depends: python3 (>= 3.10), python3-gi, python3-gi-cairo, gir1.2-gtk-4.0, gir1.2-adw-1, gir1.2-wnck-3.0, gir1.2-notify-0.7, libsecret-1-0
Recommends: gir1.2-ayatanaappindicator3-0.1, wmctrl, xdotool
EOF

cat > "$PKG_DIR/DEBIAN/postinst" << 'EOF'
#!/bin/bash
set -e

echo "Installing NervaOS..."

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database /usr/share/applications >/dev/null 2>&1 || true
fi
if command -v xdg-desktop-menu >/dev/null 2>&1; then
    xdg-desktop-menu forceupdate >/dev/null 2>&1 || true
fi

if command -v systemctl >/dev/null 2>&1; then
    # Enable user service for all users by default.
    systemctl --global enable nerva-service.service >/dev/null 2>&1 || true
fi

# If installed with sudo, clean stale per-user DBus service from older manual installs.
if [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != "root" ]; then
    USER_HOME="$(getent passwd "$SUDO_USER" | cut -d: -f6)"
    USER_DBUS_SVC="$USER_HOME/.local/share/dbus-1/services/com.nervaos.daemon.service"
    if [ -f "$USER_DBUS_SVC" ]; then
        if grep -q "/home/.*/\\.local/bin/nerva-daemon" "$USER_DBUS_SVC" 2>/dev/null || \
           grep -q "STORAGE" "$USER_DBUS_SVC" 2>/dev/null; then
            rm -f "$USER_DBUS_SVC" || true
            echo "Removed stale user DBus service override: $USER_DBUS_SVC"
        fi
    fi

    # Best-effort: reload/start service for the currently logged-in installer user.
    if id "$SUDO_USER" >/dev/null 2>&1; then
        USER_UID="$(id -u "$SUDO_USER")"
        USER_RUNTIME="/run/user/$USER_UID"
        USER_BUS="$USER_RUNTIME/bus"
        if [ -S "$USER_BUS" ] && command -v runuser >/dev/null 2>&1; then
            runuser -u "$SUDO_USER" -- env \
                XDG_RUNTIME_DIR="$USER_RUNTIME" \
                DBUS_SESSION_BUS_ADDRESS="unix:path=$USER_BUS" \
                systemctl --user daemon-reload >/dev/null 2>&1 || true
            runuser -u "$SUDO_USER" -- env \
                XDG_RUNTIME_DIR="$USER_RUNTIME" \
                DBUS_SESSION_BUS_ADDRESS="unix:path=$USER_BUS" \
                systemctl --user enable --now nerva-service.service >/dev/null 2>&1 || true
            runuser -u "$SUDO_USER" -- env \
                XDG_RUNTIME_DIR="$USER_RUNTIME" \
                DBUS_SESSION_BUS_ADDRESS="unix:path=$USER_BUS" \
                sh -lc 'nohup /usr/bin/nerva-ui --bubble >/dev/null 2>&1 &' || true
        fi
    fi
fi

echo ""
echo "NervaOS installed. It is configured to auto-start on login."
echo "You can launch it anytime from the app menu (NervaOS)."
echo ""

exit 0
EOF
chmod +x "$PKG_DIR/DEBIAN/postinst"

cat > "$PKG_DIR/DEBIAN/prerm" << 'EOF'
#!/bin/bash
set -e

if command -v systemctl >/dev/null 2>&1; then
    systemctl --user stop nerva-service >/dev/null 2>&1 || true
    systemctl --user disable nerva-service >/dev/null 2>&1 || true
fi

exit 0
EOF
chmod +x "$PKG_DIR/DEBIAN/prerm"

cat > "$PKG_DIR/DEBIAN/postrm" << 'EOF'
#!/bin/bash
set -e

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database /usr/share/applications >/dev/null 2>&1 || true
fi
if command -v xdg-desktop-menu >/dev/null 2>&1; then
    xdg-desktop-menu forceupdate >/dev/null 2>&1 || true
fi

exit 0
EOF
chmod +x "$PKG_DIR/DEBIAN/postrm"

log "Building .deb package..."
dpkg-deb --build "$PKG_DIR"

DEB_FILE="${PACKAGE_NAME}_${VERSION}_${ARCHITECTURE}.deb"
mv "$BUILD_DIR/$DEB_FILE" "$OUTPUT_DIR/"
rm -rf "$BUILD_DIR"

log "Package built successfully!"
echo "Output: $OUTPUT_DIR/$DEB_FILE"
echo "Install with:"
echo "  sudo dpkg -i $OUTPUT_DIR/$DEB_FILE"
