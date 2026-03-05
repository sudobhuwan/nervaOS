"""
NervaOS Context Engine - Environment and workflow awareness

This module provides:
- Active window detection via LibWnck
- Context mode inference (Dev, Media, Productivity)
- Time-of-day classification
- Current working directory detection
"""

import asyncio
import logging
import os
from datetime import datetime
from typing import Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum

# Check if we're on X11 (Wnck only works on X11, not Wayland)
import os
_display = os.environ.get('DISPLAY')
_wayland = os.environ.get('WAYLAND_DISPLAY')
_is_x11 = bool(_display) and not bool(_wayland)

# LibWnck for window introspection (X11 only)
WNCK_AVAILABLE = False
Wnck = None

if _is_x11:
    try:
        import gi
        gi.require_version('Wnck', '3.0')
        from gi.repository import Wnck, GLib
        WNCK_AVAILABLE = True
    except (ImportError, ValueError) as e:
        pass
else:
    # On Wayland - Wnck not supported
    pass

from ..core.monitor import SystemMonitor

logger = logging.getLogger('nerva-context')


class ContextMode(Enum):
    """User activity modes based on active applications"""
    DEV = "development"          # VS Code, Terminal, IDE
    MEDIA = "media"              # VLC, Spotify, Netflix
    PRODUCTIVITY = "productivity"  # LibreOffice, Docs
    BROWSING = "browsing"        # Firefox, Chrome
    GAMING = "gaming"            # Steam, game launchers
    GENERAL = "general"          # Unknown/mixed


@dataclass
class WindowInfo:
    """Information about a window"""
    title: str
    app_name: str
    pid: int
    is_active: bool


class ContextEngine:
    """
    Gathers environmental context to inform AI responses.
    
    The AI adapts its behavior based on:
    - What application the user is actively using
    - Time of day
    - System resource state
    - Inferred user activity mode
    """
    
    # Application to mode mapping
    APP_MODE_MAP = {
        # Development
        'code': ContextMode.DEV,
        'visual studio code': ContextMode.DEV,
        'pycharm': ContextMode.DEV,
        'intellij': ContextMode.DEV,
        'android-studio': ContextMode.DEV,
        'gnome-terminal': ContextMode.DEV,
        'tilix': ContextMode.DEV,
        'terminator': ContextMode.DEV,
        'konsole': ContextMode.DEV,
        'sublime_text': ContextMode.DEV,
        'atom': ContextMode.DEV,
        'vim': ContextMode.DEV,
        'nvim': ContextMode.DEV,
        'emacs': ContextMode.DEV,
        'gitg': ContextMode.DEV,
        'meld': ContextMode.DEV,
        
        # Media
        'vlc': ContextMode.MEDIA,
        'mpv': ContextMode.MEDIA,
        'spotify': ContextMode.MEDIA,
        'rhythmbox': ContextMode.MEDIA,
        'totem': ContextMode.MEDIA,
        'audacity': ContextMode.MEDIA,
        'obs': ContextMode.MEDIA,
        'kdenlive': ContextMode.MEDIA,
        'gimp': ContextMode.MEDIA,
        'inkscape': ContextMode.MEDIA,
        'blender': ContextMode.MEDIA,
        
        # Productivity
        'libreoffice': ContextMode.PRODUCTIVITY,
        'soffice': ContextMode.PRODUCTIVITY,
        'evince': ContextMode.PRODUCTIVITY,
        'eog': ContextMode.PRODUCTIVITY,
        'gedit': ContextMode.PRODUCTIVITY,
        'xed': ContextMode.PRODUCTIVITY,
        'thunderbird': ContextMode.PRODUCTIVITY,
        
        # Browsing
        'firefox': ContextMode.BROWSING,
        'chromium': ContextMode.BROWSING,
        'google-chrome': ContextMode.BROWSING,
        'brave': ContextMode.BROWSING,
        'opera': ContextMode.BROWSING,
        
        # Gaming
        'steam': ContextMode.GAMING,
        'lutris': ContextMode.GAMING,
        'retroarch': ContextMode.GAMING,
    }
    
    def __init__(self):
        self._monitor = SystemMonitor()
        self._screen: Optional[Any] = None
        self._init_wnck()
    
    def _init_wnck(self):
        """Initialize LibWnck screen object"""
        if not WNCK_AVAILABLE:
            logger.warning("LibWnck not available. Window context will be limited.")
            return
        
        try:
            self._screen = Wnck.Screen.get_default()
            # Force an update
            if self._screen:
                self._screen.force_update()
            logger.info("LibWnck initialized")
        except Exception as e:
            logger.error(f"Failed to initialize LibWnck: {e}")
            self._screen = None
    
    async def get_current_context(self) -> Dict[str, Any]:
        """
        Get a comprehensive snapshot of the current context.
        
        Returns a dict with:
        - active_window: Title of active window
        - active_app: Name of active application
        - mode: Inferred context mode
        - time_of_day: morning/afternoon/evening/night
        - system_stats: CPU/RAM/disk stats
        """
        context = {}
        
        # Get active window info
        window_info = await self.get_active_window()
        if window_info:
            context['active_window'] = window_info.title
            context['active_app'] = window_info.app_name
            context['active_pid'] = window_info.pid
        
        # Infer mode
        mode = await self.get_context_mode()
        context['mode'] = mode.value
        
        # Time of day
        context['time_of_day'] = self._get_time_of_day()
        
        # System stats
        context['system_stats'] = await self._monitor.get_all_stats()
        
        # Working directory (if in terminal)
        if window_info and 'terminal' in window_info.app_name.lower():
            context['cwd'] = os.getcwd()
        
        return context
    
    async def get_active_window(self) -> Optional[WindowInfo]:
        """Get information about the currently active window"""
        if not WNCK_AVAILABLE or not self._screen:
            return None
        
        try:
            # Run in executor since Wnck can block
            return await asyncio.get_event_loop().run_in_executor(
                None, self._get_active_window_sync
            )
        except Exception as e:
            logger.error(f"Failed to get active window: {e}")
            return None
    
    def _get_active_window_sync(self) -> Optional[WindowInfo]:
        """Synchronous helper for getting active window"""
        if not self._screen:
            return None
        
        self._screen.force_update()
        active = self._screen.get_active_window()
        
        if not active:
            return None
        
        app = active.get_application()
        
        return WindowInfo(
            title=active.get_name() or "Unknown",
            app_name=app.get_name() if app else "Unknown",
            pid=active.get_pid(),
            is_active=True
        )
    
    async def get_all_windows(self) -> list:
        """Get information about all open windows"""
        if not WNCK_AVAILABLE or not self._screen:
            return []
        
        try:
            return await asyncio.get_event_loop().run_in_executor(
                None, self._get_all_windows_sync
            )
        except Exception as e:
            logger.error(f"Failed to get windows: {e}")
            return []
    
    def _get_all_windows_sync(self) -> list:
        """Synchronous helper for getting all windows"""
        if not self._screen:
            return []
        
        self._screen.force_update()
        windows = []
        active = self._screen.get_active_window()
        
        for window in self._screen.get_windows():
            if window.get_window_type() == Wnck.WindowType.NORMAL:
                app = window.get_application()
                windows.append(WindowInfo(
                    title=window.get_name() or "Unknown",
                    app_name=app.get_name() if app else "Unknown",
                    pid=window.get_pid(),
                    is_active=(window == active)
                ))
        
        return windows
    
    async def get_context_mode(self) -> ContextMode:
        """Infer the current context mode from active application"""
        window = await self.get_active_window()
        
        if not window:
            return ContextMode.GENERAL
        
        # Normalize app name for lookup
        app_name = window.app_name.lower().replace(' ', '-')
        
        # Direct match
        if app_name in self.APP_MODE_MAP:
            return self.APP_MODE_MAP[app_name]
        
        # Partial match
        for key, mode in self.APP_MODE_MAP.items():
            if key in app_name or app_name in key:
                return mode
        
        # Check window title for hints
        title_lower = window.title.lower()
        
        if any(t in title_lower for t in ['netflix', 'youtube', 'prime video']):
            return ContextMode.MEDIA
        
        if any(t in title_lower for t in ['.py', '.js', '.ts', '.go', '.rs', 'github']):
            return ContextMode.DEV
        
        return ContextMode.GENERAL
    
    def _get_time_of_day(self) -> str:
        """Get time of day classification"""
        hour = datetime.now().hour
        
        if 5 <= hour < 12:
            return "morning"
        elif 12 <= hour < 17:
            return "afternoon"
        elif 17 <= hour < 21:
            return "evening"
        else:
            return "night"
    
    async def get_context_summary(self) -> str:
        """
        Get a human-readable summary of current context for AI prompts.
        """
        ctx = await self.get_current_context()
        
        lines = [
            f"Time: {ctx.get('time_of_day', 'Unknown').capitalize()}",
            f"Mode: {ctx.get('mode', 'general').capitalize()}",
        ]
        
        if 'active_window' in ctx:
            lines.append(f"Active Window: {ctx['active_window']}")
        
        if 'active_app' in ctx:
            lines.append(f"Application: {ctx['active_app']}")
        
        stats = ctx.get('system_stats', {})
        if stats:
            lines.append(f"System: CPU {stats.get('cpu_percent', 0)}%, RAM {stats.get('ram_percent', 0)}%")
        
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────
# Mode-specific behavior recommendations
# ─────────────────────────────────────────────────────────────────

MODE_BEHAVIORS = {
    ContextMode.DEV: {
        'response_style': 'technical',
        'prefer_code': True,
        'verbosity': 'concise',
        'suggestions': ['Show code examples', 'Explain with technical terms']
    },
    ContextMode.MEDIA: {
        'response_style': 'minimal',
        'prefer_code': False,
        'verbosity': 'brief',
        'suggestions': ['Keep notifications quiet', 'Quick answers only']
    },
    ContextMode.PRODUCTIVITY: {
        'response_style': 'formal',
        'prefer_code': False,
        'verbosity': 'moderate',
        'suggestions': ['Help with formatting', 'Grammar assistance']
    },
    ContextMode.BROWSING: {
        'response_style': 'conversational',
        'prefer_code': False,
        'verbosity': 'moderate',
        'suggestions': ['Summarize pages', 'Research assistance']
    },
    ContextMode.GAMING: {
        'response_style': 'minimal',
        'prefer_code': False,
        'verbosity': 'brief',
        'suggestions': ['Minimize interruptions', 'Gaming tips only']
    },
    ContextMode.GENERAL: {
        'response_style': 'balanced',
        'prefer_code': False,
        'verbosity': 'moderate',
        'suggestions': ['General assistance']
    }
}


def get_mode_behavior(mode: ContextMode) -> Dict[str, Any]:
    """Get the recommended behavior for a given mode"""
    return MODE_BEHAVIORS.get(mode, MODE_BEHAVIORS[ContextMode.GENERAL])
