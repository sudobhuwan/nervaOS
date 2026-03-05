# ✅ NervaOS Auto-Start Configuration

## What's Enabled Now:

### 1. Chat Bubble Always Visible
```
✅ Auto-starts on login
✅ Can't be closed (only minimized)
✅ Persists even if daemon restarts
✅ Right-click menu for quick actions
```

### 2. Two Services Running

#### **nerva-service.service** (Backend Daemon)
- Location: `/home/eklavya/.config/systemd/user/nerva-service.service`
- Status: `enabled` (auto-starts on login)
- Provides: AI processing, web search, file search, alerts

#### **nerva-ui.service** (Chat Bubble)
- Location: `/home/eklavya/.config/systemd/user/nerva-ui.service`
- Status: `enabled` (auto-starts on login)
- Provides: Always-visible chat bubble interface

---

## How It Works:

1. **On System Login:**
   - Both services start automatically
   - Chat bubble appears in bottom-left corner
   - Daemon runs in background

2. **If You Reboot:**
   - Everything starts automatically
   - No manual intervention needed

3. **If Daemon Crashes:**
   - Bubble stays visible
   - Shows "Connecting..." until daemon restarts
   - Daemon auto-restarts within 3 seconds

4. **If UI Crashes:**
   - Auto-restarts within 5 seconds
   - Chat history preserved in daemon

---

## User Controls:

### Chat Bubble (Collapsed)
- **Click:** Expand to full chat
- **Right-click:** Quick actions menu
  - Screenshots
  - Screen recording
  - Power controls
  - Minimize option

### Chat Panel (Expanded)
- **Minimize button:** Collapse to bubble
- **Close button:** Removed (can't close!)
- **Drag:** Move anywhere on screen

---

## Service Management Commands:

```bash
# Check status
systemctl --user status nerva-service
systemctl --user status nerva-ui

# View logs
journalctl --user -u nerva-service -f
journalctl --user -u nerva-ui -f

# Restart services
systemctl --user restart nerva-service
systemctl --user restart nerva-ui

# Disable auto-start (if needed)
systemctl --user disable nerva-service
systemctl --user disable nerva-ui
```

---

## File Locations:

```
/home/eklavya/.config/systemd/user/
├── nerva-service.service    # Backend daemon
└── nerva-ui.service          # Chat bubble UI

/media/eklavya/STORAGE8/NervaOS/
├── src/
│   ├── core/service.py       # Daemon logic
│   └── ui/
│       ├── main.py           # UI entry point
│       └── floating_sticky.py # Chat bubble
```

---

## ✨ Result:

**NervaOS chat bubble is now:**
- ✅ Always visible on screen
- ✅ Auto-starts on login
- ✅ Can't be accidentally closed
- ✅ Survives crashes/restarts
- ✅ Accessible with one click

Perfect for a desktop AI assistant! 🎯
