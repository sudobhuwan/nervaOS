# NervaOS Feature Implementation Plan

## Overview
This document tracks the implementation of requested features for NervaOS.

## Priority 1: High Priority Features

### 1. ⚡ Quick Actions Menu [IN PROGRESS]
**Location**: Right-click on bubble
**Actions**:
- [ ] Screenshot (Full/Area/Window)
- [ ] Screen Record (Start/Stop)
- [ ] Quick Note (Opens text editor with AI)
- [ ] Lock Screen
- [ ] Sleep/Shutdown menu
- [ ] WiFi Toggle
- [ ] Bluetooth Toggle

**Files to modify**:
- `src/ui/floating_sticky.py` - Add right-click handler
- `src/core/quick_actions.py` - NEW - Action implementations

**Dependencies**: `scrot` or `gnome-screenshot`, `ffmpeg` for recording

---

### 2. 📋 Clipboard Manager [TODO]
**Features**:
- [ ] Store last 50 clipboard entries
- [ ] Search clipboard history
- [ ] Pin important items
- [ ] AI-powered clipboard analysis
- [ ] Show in bubble expansion

**Files to create**:
- `src/core/clipboard_manager.py` - Core clipboard tracking
- `src/ui/components/clipboard_widget.py` - UI component

**Dependencies**: `pyperclip` or GTK clipboard API

---

### 3. 🗓️ Calendar Integration [TODO]
**Features**:
- [ ] Show next 3 upcoming events
- [ ] Quick event creation via AI
- [ ] Event reminders (notifications)
- [ ] Sync with Google Calendar / CalDAV

**Files to create**:
- `src/integrations/calendar.py` - Calendar backend
- `src/ui/components/calendar_widget.py` - UI component

**Dependencies**: `google-api-python-client` or `caldav`

---

### 4. 📧 Email Integration [TODO]
**Features**:
- [ ] Show unread email count
- [ ] Quick compose window
- [ ] AI email drafting
- [ ] Priority inbox detection

**Files to create**:
- `src/integrations/email.py` - Email backend
- `src/ui/components/email_widget.py` - UI component

**Dependencies**: `imaplib`, `smtplib` (built-in), or Gmail API

---

### 5. 🎨 Theme System [TODO]
**Features**:
- [ ] Light mode theme
- [ ] Dark mode theme (default)
- [ ] Custom color picker
- [ ] Upload custom bubble icon
- [ ] Font selection

**Files to modify**:
- `src/core/settings.py` - Add theme settings
- `src/ui/floating_sticky.py` - Apply themes dynamically
- `src/ui/settings_page.py` - Add theme UI

---

## Priority 2: Medium Priority Features

### 6. 🔍 Smart Search [TODO]
**Features**:
- [ ] AI-powered file search ("Find that PDF about taxes")
- [ ] Content-aware search
- [ ] Semantic search (search by meaning, not filename)

**Files to create**:
- `src/core/smart_search.py` - Search engine
- `src/core/file_indexer.py` - File content indexing

---

### 7. 📸 Screenshot Tool [TODO]
**Features**:
- [ ] Area selection
- [ ] AI annotation
- [ ] OCR text extraction
- [ ] Auto-organize screenshots

**Files to create**:
- `src/tools/screenshot.py` - Screenshot tool
- Integration with Quick Actions

**Dependencies**: `tesseract` for OCR

---

### 8. 🌐 Web Search Integration [TODO]
**Features**:
- [ ] Web search via AI
- [ ] Show results in bubble
- [ ] AI summarization of results

**Files to create**:
- `src/integrations/web_search.py` - Search API integration

**Dependencies**: Google Search API or DuckDuckGo API

---

### 9. 💻 Code Assistant [TODO]
**Features**:
- [ ] Syntax highlighting in chat
- [ ] Code explanation
- [ ] Bug detection
- [ ] Git integration

**Files to modify**:
- `src/ui/floating_sticky.py` - Add code formatting
- `src/ai/code_assistant.py` - NEW - Code analysis

**Dependencies**: `pygments` for highlighting

---

### 10. 🔔 Custom Alert Rules [TODO]
**Features**:
- [ ] Battery < 20% alert
- [ ] Disk space < 10GB alert
- [ ] Process monitoring alerts
- [ ] Network disconnect alert
- [ ] System update available

**Files to create**:
- `src/core/custom_alerts.py` - Alert rule engine

---

## Implementation Timeline

### Week 1 (Jan 16-22, 2026)
- Day 1-2: Quick Actions Menu ✓
- Day 3-4: Clipboard Manager
- Day 5: Theme System (basics)

### Week 2 (Jan 23-29, 2026)
- Day 1-2: Calendar Integration
- Day 3-4: Email Integration
- Day 5: Theme System (complete)

### Week 3 (Jan 30 - Feb 5, 2026)
- Day 1: Smart Search
- Day 2-3: Screenshot Tool
- Day 4: Web Search Integration
- Day 5: Code Assistant

### Week 4 (Feb 6-12, 2026)
- Day 1-2: Custom Alert Rules
- Day 3-5: Testing & Polish

---

## Dependencies to Install

```bash
# Quick Actions
sudo apt install scrot ffmpeg

# Clipboard
pip install pyperclip

# Calendar
pip install google-api-python-client caldav

# Screenshot OCR
sudo apt install tesseract-ocr
pip install pytesseract

# Code highlighting
pip install pygments

# Web search
pip install duckduckgo-search
```

---

## Status Legend
- [ ] TODO
- [IN PROGRESS] Working on it
- [✓] Complete
- [BLOCKED] Waiting on something

---

Last Updated: 2026-01-16 17:52
