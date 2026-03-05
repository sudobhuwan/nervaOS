# NervaOS Code Refactoring Plan

## Current Issues
- `service.py` is 1187 lines (too large)
- Multiple voice files with duplicated logic
- No clear separation of concerns

## Target Structure

```
src/
├── core/
│   ├── __init__.py
│   ├── daemon/
│   │   ├── __init__.py
│   │   ├── main.py          # NervaDaemon class (~200 lines)
│   │   ├── interface.py     # DBus interface (~400 lines)
│   │   └── handlers/
│   │       ├── __init__.py
│   │       ├── ai.py        # AskAI handler
│   │       ├── files.py     # File operations
│   │       ├── voice.py     # Voice control methods
│   │       └── system.py    # System commands
│   │
│   ├── actions/
│   │   ├── __init__.py
│   │   ├── web_search.py    # Web search action
│   │   ├── git.py           # Git actions
│   │   ├── code.py          # Code analysis
│   │   └── quick.py         # Quick actions
│   │
│   ├── voice/               # DISABLED for v1.0
│   │   ├── __init__.py
│   │   ├── engine.py        # Voice engine
│   │   ├── recognition.py   # Speech-to-text
│   │   └── synthesis.py     # Text-to-speech
│   │
│   ├── monitor.py           # System monitoring
│   ├── quick_actions.py     # Quick actions menu
│   ├── custom_alerts.py     # Alert rules
│   ├── smart_search.py      # File search
│   └── env_loader.py        # Environment config
│
├── integrations/
│   ├── __init__.py
│   ├── web_search.py        # DuckDuckGo
│   └── code_assistant.py    # Git/code tools
│
├── ai/
│   ├── __init__.py
│   ├── client.py            # AI client
│   ├── context.py           # Context engine
│   └── prompts.py           # System prompts
│
└── ui/
    ├── __init__.py
    ├── main.py              # Entry point
    ├── floating_sticky.py   # Chat bubble
    ├── message_renderers.py # Message cards
    └── themes.py            # Styling
```

## Refactoring Priority

### Phase 1: Clean service.py (HIGH)
1. Extract NervaDaemonInterface → daemon/interface.py
2. Extract NervaDaemon → daemon/main.py
3. Extract action handlers → daemon/handlers/

### Phase 2: Clean voice (LATER - disabled)
1. Remove duplicate files (voice.py, voice_simple.py)
2. Single voice_nerva.py for v2.0

### Phase 3: Documentation 
1. Add docstrings to all modules
2. Type hints throughout
3. README per module

## Benefits
- Each file < 300 lines
- Single responsibility
- Easier testing
- Better maintainability
- Clear dependencies

## Status: v1.0
- Voice: DISABLED (clean refactor planned for v2.0)
- All other features: WORKING
