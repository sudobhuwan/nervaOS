# NervaOS v1.0 - Project Structure

```
NervaOS/
├── src/
│   ├── __init__.py
│   │
│   ├── ai/                        # AI/LLM Integration
│   │   ├── __init__.py
│   │   ├── client.py              # Google Gemini client
│   │   ├── context.py             # Context engine (window/system info)
│   │   └── pruning.py             # Token pruning utilities
│   │
│   ├── core/                      # Core Daemon Services
│   │   ├── __init__.py
│   │   ├── service.py             # Main daemon (DBus interface)
│   │   ├── monitor.py             # System monitoring (CPU/RAM/Battery)
│   │   ├── quick_actions.py       # Screenshot/Recording/Power
│   │   ├── custom_alerts.py       # User-defined alerts
│   │   ├── smart_search.py        # File search with PDF extraction
│   │   ├── smart_notifications.py # Desktop notifications
│   │   ├── automation.py          # Automation rules
│   │   ├── safety.py              # Safe command validation
│   │   ├── secrets.py             # Keyring integration
│   │   ├── settings.py            # App settings
│   │   ├── env_loader.py          # Environment variables
│   │   ├── notifications.py       # System notifications
│   │   ├── plugins.py             # Plugin system
│   │   ├── updater.py             # Auto-update
│   │   ├── license.py             # License validation
│   │   │
│   │   ├── daemon/                # [Empty - future refactor]
│   │   │   └── __init__.py
│   │   │
│   │   └── voice/                 # Voice Control (DISABLED v1.0)
│   │       ├── __init__.py
│   │       └── engine.py          # Deepgram STT+TTS
│   │
│   ├── integrations/              # External Integrations
│   │   ├── __init__.py
│   │   ├── web_search.py          # DuckDuckGo + AI summaries
│   │   └── code_assistant.py      # Git integration + code analysis
│   │
│   └── ui/                        # User Interface
│       ├── __init__.py
│       ├── main.py                # Entry point
│       ├── floating_sticky.py     # Sticky chat bubble
│       ├── message_renderers.py   # Beautiful message cards
│       ├── floating.py            # Floating window base
│       ├── window.py              # Main window
│       ├── overlay.py             # Screen overlay
│       ├── tray.py                # System tray icon
│       ├── settings_page.py       # Settings UI
│       │
│       └── components/            # UI Components
│           ├── __init__.py
│           ├── chat_bubble.py     # Chat bubble widget
│           └── diff_view.py       # Diff viewer
│
├── .env                           # Environment config
├── README.md                      # Documentation
├── REFACTOR_PLAN.md              # Future refactoring notes
├── install.sh                     # Installation script
└── requirements.txt               # Dependencies
```

## Module Responsibilities

### `core/service.py` (Main Daemon)
- DBus interface (`com.nervaos.daemon`)
- AI query processing
- Action execution (web search, git, etc.)
- System monitoring loop

### `core/smart_search.py`
- File indexing (Documents, Downloads, Desktop)
- PDF content extraction
- Full-text search

### `core/custom_alerts.py`
- Battery level alerts
- Disk space monitoring
- Network status
- CPU temperature

### `core/quick_actions.py`
- Screenshots (full/area/window)
- Screen recording
- Power controls

### `integrations/web_search.py`
- DuckDuckGo queries
- AI-powered summaries
- Location-aware results

### `integrations/code_assistant.py`
- Git status/log/diff
- Project detection
- Code explanation
- Bug detection

### `ui/floating_sticky.py`
- Always-on-top chat bubble
- Message input
- Response display

### `ui/message_renderers.py`
- Gradient card rendering
- Markdown-like formatting
- Beautiful UI

## Dependencies

```
# Core
dbus-next        # DBus communication
psutil           # System monitoring
PyGObject        # GTK bindings

# AI
google-generativeai  # Gemini API

# Search
duckduckgo-search    # Web search
PyPDF2               # PDF extraction

# Voice (DISABLED)
deepgram-sdk         # Speech-to-text + TTS
pyaudio              # Audio capture
pygame               # Audio playback
```

## Status

✅ **Working (v1.0)**
- Web search
- File search
- Code assistant
- Custom alerts
- Quick actions
- Beautiful UI

❌ **Disabled (v2.0)**
- Voice control
