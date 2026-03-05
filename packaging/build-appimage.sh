#!/bin/bash
#
# NervaOS AppImage Builder
#
# Creates a portable AppImage for NervaOS
# Output: NervaOS-x86_64.AppImage
#

set -e

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

VERSION="1.0.0"
APP_NAME="NervaOS"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BUILD_DIR="$SCRIPT_DIR/appimage/build"
OUTPUT_DIR="$SCRIPT_DIR/appimage"

# AppImage tool
APPIMAGETOOL_URL="https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage"

# ─────────────────────────────────────────────────────────────────────────────
# Functions
# ─────────────────────────────────────────────────────────────────────────────

log() {
    echo "[$(date '+%H:%M:%S')] $1"
}

error() {
    echo "[ERROR] $1" >&2
    exit 1
}

download_appimagetool() {
    if [ ! -f "$SCRIPT_DIR/appimagetool" ]; then
        log "Downloading appimagetool..."
        wget -q "$APPIMAGETOOL_URL" -O "$SCRIPT_DIR/appimagetool"
        chmod +x "$SCRIPT_DIR/appimagetool"
    fi
}

# ─────────────────────────────────────────────────────────────────────────────
# Build
# ─────────────────────────────────────────────────────────────────────────────

log "Building NervaOS AppImage v${VERSION}..."

# Clean previous build
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"
mkdir -p "$OUTPUT_DIR"

# Get appimagetool
download_appimagetool

# Create AppDir structure
APP_DIR="$BUILD_DIR/NervaOS.AppDir"
mkdir -p "$APP_DIR/usr/bin"
mkdir -p "$APP_DIR/usr/lib"
mkdir -p "$APP_DIR/usr/share/applications"
mkdir -p "$APP_DIR/usr/share/icons/hicolor/256x256/apps"
mkdir -p "$APP_DIR/opt/nervaos"

log "Setting up Python environment..."

# Create a minimal Python environment
python3 -m venv "$APP_DIR/opt/nervaos/venv"
source "$APP_DIR/opt/nervaos/venv/bin/activate"

# Install dependencies
pip install --quiet --upgrade pip
pip install --quiet -r "$PROJECT_ROOT/requirements.txt"

# Deactivate
deactivate

log "Copying application files..."

# Copy source code
cp -r "$PROJECT_ROOT/src" "$APP_DIR/opt/nervaos/"
cp "$PROJECT_ROOT/requirements.txt" "$APP_DIR/opt/nervaos/"

# Copy config
mkdir -p "$APP_DIR/opt/nervaos/config"
cp "$PROJECT_ROOT/config/default.conf" "$APP_DIR/opt/nervaos/config/"

# Create AppRun script
cat > "$APP_DIR/AppRun" << 'EOF'
#!/bin/bash
APPDIR="$(dirname "$(readlink -f "$0")")"

# Activate virtual environment
export PATH="$APPDIR/opt/nervaos/venv/bin:$PATH"
export PYTHONPATH="$APPDIR/opt/nervaos:$PYTHONPATH"

# Set GI typelib path for GTK
export GI_TYPELIB_PATH="/usr/lib/x86_64-linux-gnu/girepository-1.0:$GI_TYPELIB_PATH"

# Launch the UI
exec python3 -m src.ui.main "$@"
EOF
chmod +x "$APP_DIR/AppRun"

# Create desktop entry
cat > "$APP_DIR/nervaos.desktop" << EOF
[Desktop Entry]
Type=Application
Name=NervaOS
Comment=AI-powered intelligence layer for Linux
Exec=AppRun
Icon=nervaos
Categories=Utility;System;
Terminal=false
StartupWMClass=nervaos
EOF

# Also copy to standard location
cp "$APP_DIR/nervaos.desktop" "$APP_DIR/usr/share/applications/"

# Create a simple icon (placeholder - replace with actual icon)
cat > "$APP_DIR/nervaos.svg" << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<svg width="256" height="256" viewBox="0 0 256 256" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="grad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:#7c3aed;stop-opacity:1" />
      <stop offset="100%" style="stop-color:#a78bfa;stop-opacity:1" />
    </linearGradient>
  </defs>
  <circle cx="128" cy="128" r="120" fill="url(#grad)"/>
  <circle cx="128" cy="128" r="80" fill="none" stroke="white" stroke-width="8"/>
  <circle cx="128" cy="128" r="40" fill="white"/>
  <path d="M128 48 L128 88 M128 168 L128 208 M48 128 L88 128 M168 128 L208 128" 
        stroke="white" stroke-width="8" stroke-linecap="round"/>
</svg>
EOF
cp "$APP_DIR/nervaos.svg" "$APP_DIR/usr/share/icons/hicolor/256x256/apps/"

log "Building AppImage..."

# Build the AppImage
cd "$BUILD_DIR"
ARCH=x86_64 "$SCRIPT_DIR/appimagetool" --no-appstream "$APP_DIR" "$OUTPUT_DIR/${APP_NAME}-${VERSION}-x86_64.AppImage"

# Clean up build directory
rm -rf "$BUILD_DIR"

log "AppImage built successfully!"
echo ""
echo "Output: $OUTPUT_DIR/${APP_NAME}-${VERSION}-x86_64.AppImage"
echo ""
echo "To run:"
echo "  chmod +x $OUTPUT_DIR/${APP_NAME}-${VERSION}-x86_64.AppImage"
echo "  ./${APP_NAME}-${VERSION}-x86_64.AppImage"
echo ""
echo "Note: The AppImage requires GTK4 and libadwaita to be installed on the host system."
echo ""
