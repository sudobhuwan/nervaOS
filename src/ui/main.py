"""
NervaOS UI - Main GTK4 Application Entry Point

This is the main entry point for the NervaOS user interface.
It initializes the GTK application and manages the window lifecycle.
"""

import sys
import logging
import asyncio
from typing import Optional

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
gi.require_version('Gdk', '4.0')
from gi.repository import Gtk, Gdk, Adw, Gio, GLib

from .tray import TrayManager
from .overlay import SpotlightOverlay
from .window import MainWindow
from .floating_sticky import StickyFloatingWidget

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('nerva-ui')


class NervaApplication(Adw.Application):
    """
    Main GTK4 Application for NervaOS.
    
    This manages:
    - Single instance enforcement
    - Window lifecycle
    - System tray integration
    - DBus connection to daemon
    """
    
    def __init__(self):
        super().__init__(
            application_id='com.nervaos.ui',
            flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE
        )
        
        # Windows
        self._main_window: Optional[MainWindow] = None
        self._spotlight: Optional[SpotlightOverlay] = None
        self._floating: Optional[StickyFloatingWidget] = None
        
        # Tray manager
        self._tray: Optional[TrayManager] = None
        
        # DBus connection
        self._daemon_proxy = None
        self._reconnect_source_id: Optional[int] = None  # GLib timeout for periodic reconnect
        
        # Command line options
        self.add_main_option(
            'overlay',
            ord('o'),
            GLib.OptionFlags.NONE,
            GLib.OptionArg.NONE,
            'Open spotlight overlay instead of main window',
            None
        )
        
        self.add_main_option(
            'minimized',
            ord('m'),
            GLib.OptionFlags.NONE,
            GLib.OptionArg.NONE,
            'Start minimized to tray',
            None
        )
        
        self.add_main_option(
            'bubble',
            ord('b'),
            GLib.OptionFlags.NONE,
            GLib.OptionArg.NONE,
            'Start with floating bubble',
            None
        )
    
    def do_startup(self):
        """Called when application starts"""
        Adw.Application.do_startup(self)
        
        # Ensure program name matches ID for proper grouping
        GLib.set_prgname('com.nervaos.ui')
        GLib.set_application_name('NervaOS')
        
        # Keep application alive even with no windows open (tray mode)
        self.hold()
        
        logger.info("NervaOS UI starting...")
        
        # Set up application actions
        self._setup_actions()
        
        # Apply custom CSS
        self._load_css()
        
        # Initialize tray icon
        self._tray = TrayManager(self)
        
        # Connect to daemon via DBus
        GLib.idle_add(self._connect_daemon)

        # Check for persistent bubble setting
        GLib.timeout_add(1000, self._check_persistent_bubble)
        
        logger.info("NervaOS UI startup complete")
    
    def _check_persistent_bubble(self):
        """Check if persistent bubble should be shown"""
        from ..core.settings import get_settings_manager
        # Force reload from disk/memory to match latest save
        get_settings_manager().reload()
        settings = get_settings_manager().load()
        logger.info(f"Checking persistent bubble: enabled={settings.show_bubble}")
        
        if settings.show_bubble:
            if not self._floating or not self._floating.is_visible():
                logger.info("Showing persistent bubble")
                self.show_floating_bubble()
        else:
            if self._floating and self._floating.is_visible():
                logger.info("Hiding persistent bubble")
                self._floating.hide()
        
        return False  # Run once

    
    def do_activate(self):
        """Called when application is activated (window shown)"""
        # Reconnect to daemon if we're disconnected (e.g. after sleep/wake, open UI)
        if not self._daemon_proxy:
            GLib.idle_add(self._connect_daemon, 0, False)
        # Always create/show main window on regular activation
        if not self._main_window:
            self._main_window = MainWindow(application=self)
            # Connect settings save to bubble check
            self._main_window.set_settings_callback(self._check_persistent_bubble)
        
        self._main_window.present()
        self._main_window.set_visible(True)
        
        # Check bubble state (settings might have changed)
        self._check_persistent_bubble()
    
    def do_command_line(self, command_line):
        """Handle command line arguments"""
        options = command_line.get_options_dict()
        
        if options.contains('overlay'):
            # Show spotlight overlay
            GLib.idle_add(self.show_spotlight)
        elif options.contains('minimized'):
            # Start minimized - just stay running (held in startup)
            pass
        elif options.contains('bubble'):
            # Start with floating bubble only
            GLib.idle_add(self.show_floating_bubble)
        else:
            # Normal activation - show main window
            self.activate()
        
        return 0
    
    def _setup_actions(self):
        """Set up application actions"""
        # Quit action
        quit_action = Gio.SimpleAction.new('quit', None)
        quit_action.connect('activate', self._on_quit)
        self.add_action(quit_action)
        self.set_accels_for_action('app.quit', ['<Control>q'])
        
        # Show main window
        show_action = Gio.SimpleAction.new('show-main', None)
        show_action.connect('activate', self._on_show_main)
        self.add_action(show_action)
        
        # Show spotlight
        spotlight_action = Gio.SimpleAction.new('spotlight', None)
        spotlight_action.connect('activate', self._on_spotlight)
        self.add_action(spotlight_action)
        self.set_accels_for_action('app.spotlight', ['<Super>space'])
        
        # Open settings
        settings_action = Gio.SimpleAction.new('settings', None)
        settings_action.connect('activate', self._on_settings)
        self.add_action(settings_action)
        self.set_accels_for_action('app.settings', ['<Control>comma'])
        
        # Toggle floating bubble
        bubble_action = Gio.SimpleAction.new('bubble', None)
        bubble_action.connect('activate', self._on_toggle_bubble)
        self.add_action(bubble_action)
        self.set_accels_for_action('app.bubble', ['<Control>b'])
    
    def _load_css(self):
        """Load custom CSS styles"""
        css_provider = Gtk.CssProvider()
        
        css = """
        /* NervaOS Custom Styles */
        
        .spotlight-overlay {
            background-color: alpha(@window_bg_color, 0.95);
            border-radius: 12px;
            padding: 12px;
        }
        
        .spotlight-entry {
            font-size: 18px;
            padding: 12px 16px;
            border-radius: 8px;
            background: @view_bg_color;
            min-height: 48px;
        }
        
        .spotlight-entry:focus {
            outline: 2px solid @accent_color;
        }
        
        .response-bubble {
            background: @card_bg_color;
            border-radius: 12px;
            padding: 12px 16px;
            margin: 8px 0;
        }
        
        .response-bubble.user {
            background: @accent_bg_color;
            color: @accent_fg_color;
            margin-left: 48px;
        }
        
        .response-bubble.assistant {
            background: @card_bg_color;
            margin-right: 48px;
        }
        
        .status-indicator {
            min-width: 12px;
            min-height: 12px;
            border-radius: 6px;
        }
        
        .status-idle {
            background: @success_color;
        }
        
        .status-processing {
            background: @accent_color;
        }
        
        .status-error {
            background: @error_color;
        }
        
        .diff-view {
            font-family: monospace;
            font-size: 13px;
        }
        
        .diff-added {
            background-color: alpha(@success_color, 0.2);
        }
        
        .diff-removed {
            background-color: alpha(@error_color, 0.2);
        }
        
        .sidebar-button {
            padding: 8px 12px;
            border-radius: 6px;
        }
        
        .sidebar-button:hover {
            background: alpha(@view_fg_color, 0.1);
        }
        
        /* History Panel Styles */
        .history-panel {
            background: alpha(@window_bg_color, 0.98);
        }
        
        .history-header {
            border-bottom: 1px solid alpha(@accent_color, 0.2);
        }
        
        .history-title {
            color: @accent_color;
            font-size: 18px;
            font-weight: 700;
        }
        
        .stats-card {
            background: alpha(@accent_bg_color, 0.12);
            border-radius: 12px;
            padding: 12px;
            border: 1px solid alpha(@accent_color, 0.2);
        }
        
        .stat-item {
            color: @accent_fg_color;
            font-size: 16px;
            font-weight: 700;
        }
        
        .history-search {
            background: alpha(@view_bg_color, 0.6);
            border: 1px solid alpha(@accent_color, 0.2);
            border-radius: 10px;
            color: @view_fg_color;
            padding: 10px 14px;
        }
        
        .conversation-card {
            background: alpha(@accent_bg_color, 0.08);
            border-radius: 12px;
            border: 1px solid alpha(@accent_color, 0.15);
            transition: all 0.2s;
            min-width: 0;
        }
        
        .conversation-card:hover {
            background: alpha(@accent_bg_color, 0.15);
            border-color: alpha(@accent_color, 0.3);
        }
        
        .active-conversation {
            background: alpha(@accent_bg_color, 0.25) !important;
            border-color: alpha(@accent_color, 0.5) !important;
            box-shadow: 0 0 0 2px alpha(@accent_color, 0.3);
        }
        
        .active-conversation:hover {
            background: alpha(@accent_bg_color, 0.3) !important;
        }
        
        .conv-title {
            color: @view_fg_color;
            font-size: 14px;
            font-weight: 600;
        }
        
        .conv-count {
            color: @accent_color;
            font-size: 12px;
            font-weight: 600;
        }
        
        .conv-time {
            color: alpha(@view_fg_color, 0.6);
            font-size: 11px;
        }
        
        .delete-conv-btn {
            min-width: 32px;
            min-height: 32px;
            border-radius: 8px;
            background-color: alpha(@error_color, 0.15);
            border: 1px solid alpha(@error_color, 0.3);
            color: @error_color;
            opacity: 0.7;
        }
        
        .delete-conv-btn:hover {
            background-color: alpha(@error_color, 0.25);
            border-color: alpha(@error_color, 0.5);
            opacity: 1;
        }
        
        .new-conversation-btn {
            background-image: linear-gradient(to bottom right, @accent_color, @accent_bg_color);
            border-radius: 12px;
            color: @accent_fg_color;
            font-weight: 600;
            padding: 12px;
        }
        
        .new-conversation-btn:hover {
            background-image: linear-gradient(to bottom right, alpha(@accent_color, 0.9), alpha(@accent_bg_color, 0.9));
        }
        
        .clear-all-btn {
            background-image: linear-gradient(to bottom right, alpha(@error_color, 0.15), alpha(@error_color, 0.1));
            border-radius: 12px;
            color: @error_color;
            font-weight: 600;
            padding: 12px;
            border: 1px solid alpha(@error_color, 0.3);
        }
        
        .clear-all-btn:hover {
            background-image: linear-gradient(to bottom right, alpha(@error_color, 0.25), alpha(@error_color, 0.15));
            border-color: alpha(@error_color, 0.5);
        }
        
        .delete-conv-btn {
            min-width: 32px;
            min-height: 32px;
            border-radius: 8px;
            background-color: alpha(@error_color, 0.15);
            border: 1px solid alpha(@error_color, 0.3);
            color: @error_color;
            opacity: 0.8;
            transition: all 0.2s ease;
        }
        
        .delete-conv-btn:hover {
            background-color: alpha(@error_color, 0.25);
            border-color: alpha(@error_color, 0.5);
            opacity: 1;
        }
        
        .empty-state {
            color: alpha(@view_fg_color, 0.6);
            font-size: 14px;
            padding: 40px 20px;
        }
        
        /* ===== MODERN CHAT INTERFACE ===== */
        .chat-page {
            background-image: linear-gradient(to bottom, 
                alpha(@window_bg_color, 1.0) 0%,
                alpha(@window_bg_color, 0.98) 100%);
        }
        
        .modern-header {
            background-image: linear-gradient(to bottom right, 
                alpha(@accent_color, 0.1) 0%,
                alpha(@accent_bg_color, 0.05) 100%);
            border-bottom: 1px solid alpha(@accent_color, 0.15);
            padding: 12px 0;
        }
        
        .header-title {
            font-size: 20px;
            font-weight: 700;
            color: @accent_color;
            letter-spacing: -0.5px;
        }
        
        .chat-scroll {
            background: transparent;
        }
        
        .chat-messages-container {
            background: transparent;
        }
        
        /* Modern Message Bubbles */
        .response-bubble {
            border-radius: 20px;
            padding: 16px 20px;
            margin: 4px 0;
            transition: all 0.2s ease;
            box-shadow: 0 2px 8px alpha(black, 0.08);
        }
        
        .response-bubble.user {
            background-image: linear-gradient(to bottom right, 
                alpha(@accent_color, 0.9) 0%,
                alpha(@accent_bg_color, 0.85) 100%);
            color: white;
            margin-right: 0;
            border-bottom-right-radius: 6px;
            box-shadow: 0 4px 12px alpha(@accent_color, 0.3);
        }
        
        .response-bubble.user:hover {
            box-shadow: 0 6px 16px alpha(@accent_color, 0.4);
        }
        
        .response-bubble.assistant {
            background-image: linear-gradient(to bottom right, 
                alpha(@card_bg_color, 1.0) 0%,
                alpha(@window_bg_color, 0.95) 100%);
            color: @view_fg_color;
            margin-left: 0;
            border-bottom-left-radius: 6px;
            border: 1px solid alpha(@accent_color, 0.12);
            padding: 18px 22px;
        }
        
        .response-bubble.assistant:hover {
            border-color: alpha(@accent_color, 0.25);
            box-shadow: 0 4px 16px alpha(black, 0.15);
        }
        
        .response-bubble.user {
            padding: 16px 20px;
        }
        
        .response-bubble.error {
            background-image: linear-gradient(to bottom right, 
                alpha(@error_color, 0.1) 0%,
                alpha(@error_color, 0.05) 100%);
            border: 1px solid alpha(@error_color, 0.3);
            color: @error_color;
        }
        
        /* Modern Input Area */
        .input-container {
            background: transparent;
        }
        
        .input-box {
            background-image: linear-gradient(to bottom right, 
                alpha(@card_bg_color, 0.8) 0%,
                alpha(@window_bg_color, 0.9) 100%);
            border-radius: 28px;
            padding: 8px 12px;
            border: 2px solid alpha(@accent_color, 0.15);
            transition: all 0.3s ease;
            box-shadow: 0 4px 16px alpha(black, 0.08);
        }
        
        .input-box:focus-within {
            border-color: alpha(@accent_color, 0.4);
            box-shadow: 0 6px 24px alpha(@accent_color, 0.2);
        }
        
        .modern-input {
            background: transparent;
            border: none;
            font-size: 15px;
            padding: 10px 16px;
            color: @view_fg_color;
            min-height: 44px;
        }
        
        .modern-input:focus {
            outline: none;
        }
        
        .send-button {
            min-width: 44px;
            min-height: 44px;
            border-radius: 22px;
            background-image: linear-gradient(to bottom right, @accent_color, @accent_bg_color);
            color: white;
            border: none;
            transition: all 0.2s ease;
            box-shadow: 0 2px 8px alpha(@accent_color, 0.3);
        }
        
        .send-button:hover {
            background-image: linear-gradient(to bottom right, 
                alpha(@accent_color, 0.9), 
                alpha(@accent_bg_color, 0.9));
            box-shadow: 0 4px 12px alpha(@accent_color, 0.4);
        }
        
        .send-button:active {
            box-shadow: 0 1px 4px alpha(@accent_color, 0.25);
        }
        
        /* Improved Sidebar */
        .navigation-sidebar {
            background-image: linear-gradient(to bottom, 
                alpha(@window_bg_color, 1.0) 0%,
                alpha(@window_bg_color, 0.98) 100%);
            border-right: 1px solid alpha(@accent_color, 0.1);
        }
        
        /* Better Typography */
        .response-bubble label {
            font-size: 15px;
            line-height: 1.6;
            font-weight: 400;
        }
        
        .response-bubble.user label {
            color: white;
            font-weight: 500;
        }
        
        .response-bubble.assistant label {
            color: @view_fg_color;
        }
        
        /* ===== MARKDOWN RENDERING STYLES ===== */
        .message-h1 {
            font-size: 22px;
            font-weight: 700;
            color: @accent_color;
            margin-top: 16px;
            margin-bottom: 10px;
            line-height: 1.35;
            letter-spacing: -0.5px;
        }
        
        .message-h2 {
            font-size: 18px;
            font-weight: 600;
            color: @accent_color;
            margin-top: 14px;
            margin-bottom: 8px;
            line-height: 1.4;
            letter-spacing: -0.3px;
        }
        
        .message-h3 {
            font-size: 16px;
            font-weight: 600;
            color: alpha(@accent_color, 0.92);
            margin-top: 12px;
            margin-bottom: 6px;
            line-height: 1.45;
        }
        
        .message-bold {
            font-weight: 600;
            color: @view_fg_color;
        }
        
        .message-text {
            font-size: 15px;
            line-height: 1.75;
            color: @view_fg_color;
            margin: 6px 0;
            letter-spacing: 0.01em;
        }
        
        .message-list {
            margin: 10px 0;
            padding-left: 4px;
        }
        
        .bullet-icon {
            color: @accent_color;
            font-size: 14px;
            min-width: 24px;
            font-weight: 600;
        }
        
        .number-icon {
            color: @accent_color;
            font-weight: 600;
            min-width: 28px;
            font-size: 14px;
        }
        
        .list-item-text {
            font-size: 15px;
            line-height: 1.7;
            color: @view_fg_color;
        }
        
        .code-block {
            background-image: linear-gradient(to bottom right, 
                alpha(@window_bg_color, 0.75) 0%,
                alpha(@window_bg_color, 0.55) 100%);
            border: 1px solid alpha(@accent_color, 0.28);
            border-radius: 14px;
            margin: 16px 0;
            box-shadow: 0 3px 12px alpha(black, 0.12);
        }
        
        .code-header {
            background-image: linear-gradient(to bottom right, 
                alpha(@accent_color, 0.18) 0%,
                alpha(@accent_color, 0.1) 100%);
            padding: 10px 14px;
            border-bottom: 1px solid alpha(@accent_color, 0.22);
        }
        
        .code-lang {
            font-family: 'Monospace', 'Courier New', monospace;
            font-size: 12px;
            font-weight: 600;
            color: @accent_color;
            letter-spacing: 0.5px;
        }
        
        .code-content {
            font-family: 'Monospace', 'Courier New', monospace;
            font-size: 13px;
            line-height: 1.65;
            color: @view_fg_color;
            padding: 14px;
            background: alpha(@window_bg_color, 0.5);
        }
        
        .inline-code {
            background-image: linear-gradient(to bottom right, 
                alpha(@accent_color, 0.2) 0%,
                alpha(@accent_color, 0.14) 100%);
            color: @accent_color;
            font-family: 'Monospace', 'Courier New', monospace;
            font-size: 13px;
            padding: 2px 6px;
            border-radius: 4px;
            font-weight: 500;
        }
        
        .link-button {
            background: alpha(@accent_color, 0.1);
            border: 1px solid alpha(@accent_color, 0.3);
            border-radius: 8px;
            padding: 8px 12px;
            color: @accent_color;
            font-weight: 500;
            margin: 4px 0;
        }
        
        .link-button:hover {
            background: alpha(@accent_color, 0.2);
            border-color: alpha(@accent_color, 0.5);
        }
        
        /* Better spacing for rendered content */
        .response-bubble > box {}
        
        .response-bubble.assistant .message-text {
            color: alpha(@view_fg_color, 0.95);
        }
        
        .response-bubble.assistant .message-h1,
        .response-bubble.assistant .message-h2,
        .response-bubble.assistant .message-h3 {
            color: @accent_color;
        }
        
        /* Model Selector Styles */
        .model-selector {
            min-width: 180px;
            font-size: 13px;
        }
        
        .model-selector dropdown {
            padding: 4px 8px;
        }
        """
        
        css_provider.load_from_data(css.encode())
        
        # Get display - can't use get_active_window() during startup
        display = Gdk.Display.get_default()
        if display:
            Gtk.StyleContext.add_provider_for_display(
                display,
                css_provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )
    
    def _cancel_reconnect_timer(self):
        """Cancel any scheduled daemon reconnect"""
        if self._reconnect_source_id is not None:
            GLib.source_remove(self._reconnect_source_id)
            self._reconnect_source_id = None

    def _schedule_periodic_reconnect(self):
        """Schedule reconnect in 15s. Survives sleep/wake; UI reconnects when daemon is back."""
        self._cancel_reconnect_timer()
        def _tick():
            self._reconnect_source_id = None
            self._connect_daemon(0, from_periodic=True)
            return False
        self._reconnect_source_id = GLib.timeout_add_seconds(15, _tick)

    def _connect_daemon(self, retry_count=0, from_periodic=False):
        """Connect to the NervaOS daemon via DBus. Starts daemon if needed, retries, then periodic reconnect."""
        try:
            bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            self._daemon_proxy = Gio.DBusProxy.new_sync(
                bus,
                Gio.DBusProxyFlags.NONE,
                None,
                'com.nervaos.daemon',
                '/com/nervaos/daemon',
                'com.nervaos.daemon',
                None
            )
            result = self._daemon_proxy.call_sync(
                'Ping',
                None,
                Gio.DBusCallFlags.NONE,
                5000,
                None
            )
            logger.info(f"Connected to NervaOS daemon: {result.unpack()[0]}")
            self._cancel_reconnect_timer()
            if self._tray:
                self._tray.set_status('idle')
            if hasattr(self, '_floating') and self._floating:
                self._floating._daemon_proxy = self._daemon_proxy
            return False
        except Exception as e:
            err_str = str(e).lower()
            logger.warning(f"Could not connect to daemon (attempt {retry_count + 1}): {e}")
            if retry_count < 3 and not from_periodic:
                self._cancel_reconnect_timer()
                # On first failure, aggressively attempt daemon startup (service + direct binary).
                if retry_count == 0 and (
                    'servicename' in err_str or
                    'service unknown' in err_str or
                    'not provided' in err_str or
                    'startservicebyname' in err_str or
                    'failed to execute program' in err_str
                ):
                    self._try_start_daemon()
                    delay_ms = 3000
                else:
                    delay_ms = 1000
                def _retry():
                    self._connect_daemon(retry_count + 1, False)
                    return False
                GLib.timeout_add(delay_ms, _retry)
            else:
                if not from_periodic:
                    logger.info("Will keep trying every 15s (e.g. after sleep/wake). Open UI to reconnect now.")
                    if self._tray:
                        self._tray.set_status('error')
                self._schedule_periodic_reconnect()
            return False

    def _try_start_daemon(self):
        """Best-effort daemon start: first systemd user service, then direct launcher."""
        import subprocess

        try:
            subprocess.run(
                ['systemctl', '--user', 'start', 'nerva-service.service'],
                timeout=8,
                capture_output=True,
                check=False
            )
            logger.info("Tried starting nerva-service via systemd user service.")
        except Exception as e:
            logger.debug(f"systemctl --user start failed: {e}")

        # Direct fallback helps when DBus activation files are stale/broken.
        try:
            subprocess.Popen(
                ['nerva-daemon'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            logger.info("Tried starting daemon directly via nerva-daemon.")
        except Exception as e:
            logger.debug(f"Direct daemon start failed: {e}")
    
    def show_spotlight(self):
        """Show the spotlight overlay"""
        if not self._spotlight:
            self._spotlight = SpotlightOverlay(application=self)
        
        self._spotlight.present()
        self._spotlight.focus_entry()
    
    def hide_spotlight(self):
        """Hide the spotlight overlay"""
        if self._spotlight:
            self._spotlight.hide()
    
    def show_floating_bubble(self):
        """Show the floating assistant bubble"""
        if not self._floating:
            self._floating = StickyFloatingWidget(
                send_query_callback=self.send_query,
                application=self
            )
            # Set daemon proxy for history
            self._floating._daemon_proxy = self._daemon_proxy
        self._floating.show_bubble()
    
    def _on_toggle_bubble(self, action, param):
        """Toggle the floating bubble visibility"""
        if self._floating and self._floating.is_visible():
            self._floating.hide()
        else:
            self.show_floating_bubble()
    
    def send_query(self, query: str, callback=None):
        """Send a query to the daemon"""
        if not self._daemon_proxy:
            self._connect_daemon(0, False)  # try reconnect (e.g. after sleep/wake)
            if not self._daemon_proxy:
                logger.error("Not connected to daemon")
                if callback:
                    callback(
                        None,
                        "Not connected to NervaOS daemon. Health check: daemon unavailable. "
                        "Open Settings to verify API key, then retry. I will keep auto-reconnecting."
                    )
                return
        
        if self._tray:
            self._tray.set_status('processing')
        
        # Call daemon asynchronously
        self._daemon_proxy.call(
            'AskAI',
            GLib.Variant('(s)', (query,)),
            Gio.DBusCallFlags.NONE,
            30000,  # 30 second timeout
            None,
            self._on_query_complete,
            callback
        )
    
    def _is_connection_error(self, e: Exception) -> bool:
        """True if error indicates DBus/connection lost (e.g. after sleep/wake)."""
        s = str(e).lower()
        return any(
            x in s for x in (
                'connection', 'noreply', 'disconnected', 'no reply',
                'name has no owner', 'connection refused', 'connection closed'
            )
        )

    def _on_query_complete(self, proxy, result, callback):
        """Handle query completion"""
        try:
            variant = proxy.call_finish(result)
            response = variant.unpack()[0]
            if self._tray:
                self._tray.set_status('idle')
            if callback:
                callback(response, None)
        except Exception as e:
            logger.error(f"Query failed: {e}")
            if self._tray:
                self._tray.set_status('error')
            if callback:
                callback(None, str(e))
            if self._is_connection_error(e):
                self._daemon_proxy = None
                if hasattr(self, '_floating') and self._floating:
                    self._floating._daemon_proxy = None
                self._connect_daemon(0, False)
    
    # ─────────────────────────────────────────────────────────────
    # Action Handlers
    # ─────────────────────────────────────────────────────────────
    
    def _on_quit(self, action, param):
        """Handle quit action"""
        logger.info("Quitting NervaOS UI")
        self._cancel_reconnect_timer()
        self.quit()
    
    def _on_show_main(self, action, param):
        """Handle show main window action"""
        self.activate()
    
    def _on_spotlight(self, action, param):
        """Handle spotlight action"""
        self.show_spotlight()
    
    def _on_settings(self, action, param):
        """Handle settings action"""
        if self._main_window:
            self._main_window.show_settings()


def main():
    """Main entry point"""
    app = NervaApplication()
    return app.run(sys.argv)


if __name__ == '__main__':
    sys.exit(main())
