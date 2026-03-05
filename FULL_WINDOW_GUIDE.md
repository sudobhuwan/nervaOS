# 🎛️ How to Access FULL NervaOS Application

## 🎯 **The Problem:**

Currently, the systemd service only launches the **bubble** mode:
```
ExecStart=... python -m src.ui.main --bubble
```

This gives you ONLY the chat bubble, not the full configuration window!

---

## ✅ **3 Ways to Access Full NervaOS:**

### **Option 1: Launch Full Window Manually** (Quick)

```bash
# From NervaOS directory:
cd /media/eklavya/STORAGE8/NervaOS
source ~/.local/share/nervaos/venv/bin/activate
python -m src.ui.main
```

This opens the **FULL window** with:
- Chat interface
- Settings panel
- Configuration options
- System status
- Everything!

---

### **Option 2: Desktop Launcher** (Recommended)

Create a desktop entry to launch from applications menu:

```bash
# Create desktop entry
cat > ~/.local/share/applications/nervaos.desktop << 'EOF'
[Desktop Entry]
Name=NervaOS
Comment=AI-Powered Desktop Assistant
Exec=/home/eklavya/.local/share/nervaos/venv/bin/python -m src.ui.main
Icon=preferences-system
Terminal=false
Type=Application
Categories=Utility;System;
Path=/media/eklavya/STORAGE8/NervaOS
EOF

# Make it executable
chmod +x ~/.local/share/applications/nervaos.desktop

# Update desktop database
update-desktop-database ~/.local/share/applications
```

Now search for "**NervaOS**" in your applications menu!

---

### **Option 3: Both Bubble + Full Window**

Run BOTH simultaneously:

**Keep bubble auto-starting** (current systemd service)
**AND** add a launcher for the full window

```bash
# Install the desktop launcher (Option 2 above)
# The bubble runs in background
# Click NervaOS icon to open full window when needed
```

---

## 🎨 **What You Get in Full Window:**

### **Main Window Features:**
```
┌──────────────────────────────────────┐
│  NervaOS - AI Desktop Assistant      │
├──────────────────────────────────────┤
│ Sidebar:                             │
│  • 💬 Chat                           │
│  • ⚙️  Settings                      │
│  • 📊 System Stats                   │
│  • 🔔 Notifications                  │
│  • 📚 History                        │
│  • 🎛️  Automations                   │
│                                      │
│ Main Area:                           │
│  • Chat input/output                 │
│  • AI responses                      │
│  • Settings panels                   │
│  • Configuration forms               │
└──────────────────────────────────────┘
```

### **Settings Available:**
- ⚙️ **AI Provider** - Choose Gemini/OpenAI/Claude
- 🔑 **API Keys** - Manage credentials securely
- 🎨 **UI Theme** - Dark/Light mode
- 🔔 **Notifications** - Configure alerts
- 🤖 **Automations** - Set up workflows
- 📁 **File Indexing** - Choose directories
- 🎙️ **Voice Control** - Enable/disable (v2.0)

---

## 🚀 **Quick Start:**

### **Launch Full Window NOW:**

```bash
cd /media/eklavya/STORAGE8/NervaOS
~/.local/share/nervaos/venv/bin/python -m src.ui.main
```

### **Launch JUST Bubble:**

```bash
cd /media/eklavya/STORAGE8/NervaOS
~/.local/share/nervaos/venv/bin/python -m src.ui.main --bubble
```

### **Launch Spotlight Search:**

```bash
cd /media/eklavya/STORAGE8/NervaOS
~/.local/share/nervaos/venv/bin/python -m src.ui.main --overlay
```

---

## 💡 **Keyboard Shortcuts:**

Once the full window is running:

- `Ctrl+Q` → Quit
- `Ctrl+,` → Open Settings
- `Super+Space` → Show Spotlight Search
- `Ctrl+B` → Toggle Bubble

---

## 🎯 **Recommended Setup:**

1. **Keep bubble service** (already running) ✅
2. **Install desktop launcher** (Option 2 above)
3. **Use both:**
   - Bubble for quick chats
   - Full window for settings/configuration

---

## 🔧 **Install Desktop Launcher:**

```bash
# Quick install:
cat > ~/.local/share/applications/nervaos.desktop << 'EOF'
[Desktop Entry]
Name=NervaOS
Comment=AI Desktop Assistant - Full Window
Exec=/home/eklavya/.local/share/nervaos/venv/bin/python -m src.ui.main
Icon=preferences-system-symbolic
Terminal=false
Type=Application
Categories=Utility;System;AI;
Path=/media/eklavya/STORAGE8/NervaOS
StartupNotify=true
EOF

chmod +x ~/.local/share/applications/nervaos.desktop
update-desktop-database ~/.local/share/applications 2>/dev/null

echo "✅ Desktop launcher installed!"
echo "Search for 'NervaOS' in your applications menu"
```

---

## 📋 **System Tray:**

The full window also adds a **system tray icon** with menu:
- Open Main Window
- Show Spotlight
- Settings
- Quit

---

## ✅ **Summary:**

**Current:** Bubble only (via systemd)  
**To Get Full Window:** Run command or install desktop launcher  
**Best Setup:** Keep bubble + add launcher  

**Launch now:**
```bash
cd /media/eklavya/STORAGE8/NervaOS && \
~/.local/share/nervaos/venv/bin/python -m src.ui.main
```

This opens the complete configuration interface! 🎛️
