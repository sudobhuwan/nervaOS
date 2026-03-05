"""
NervaOS System Tray - Status indicator and quick actions

This module provides:
- System tray icon with status colors
- Right-click menu with quick actions
- Status notifications
"""

import logging
from typing import Optional
from enum import Enum

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gio, GLib

logger = logging.getLogger('nerva-tray')


class TrayStatus(Enum):
    """Tray icon status states"""
    IDLE = "idle"           # Green - Ready
    PROCESSING = "processing"  # Blue - Working
    ERROR = "error"         # Red - Problem
    OFFLINE = "offline"     # Gray - No daemon


class TrayManager:
    """
    Manages the system tray icon and menu.
    
    Note: GTK4 doesn't have traditional tray icons.
    We use libappindicator or status notifier if available,
    otherwise fall back to showing a persistent notification.
    """
    
    # Status icon names (using standard icon names)
    STATUS_ICONS = {
        TrayStatus.IDLE: 'emblem-ok-symbolic',
        TrayStatus.PROCESSING: 'content-loading-symbolic', 
        TrayStatus.ERROR: 'dialog-error-symbolic',
        TrayStatus.OFFLINE: 'network-offline-symbolic'
    }
    
    def __init__(self, app):
        self._app = app
        self._status = TrayStatus.IDLE
        self._indicator = None
        
        # Try to set up system tray
        self._setup_tray()
    
    def _setup_tray(self):
        """Set up the system tray indicator"""
        # Try AppIndicator3 first (for Ubuntu/Unity/Cinnamon)
        try:
            gi.require_version('AyatanaAppIndicator3', '0.1')
            from gi.repository import AyatanaAppIndicator3 as AppIndicator
            
            self._indicator = AppIndicator.Indicator.new(
                'nervaos',
                'nervaos-idle',
                AppIndicator.IndicatorCategory.APPLICATION_STATUS
            )
            self._indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)
            self._indicator.set_menu(self._create_menu_gtk3())
            
            logger.info("Using AyatanaAppIndicator for tray")
            return
            
        except (ImportError, ValueError):
            pass
        
        # Try legacy AppIndicator
        try:
            gi.require_version('AppIndicator3', '0.1')
            from gi.repository import AppIndicator3 as AppIndicator
            
            self._indicator = AppIndicator.Indicator.new(
                'nervaos',
                'nervaos-idle',
                AppIndicator.IndicatorCategory.APPLICATION_STATUS
            )
            self._indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)
            self._indicator.set_menu(self._create_menu_gtk3())
            
            logger.info("Using AppIndicator3 for tray")
            return
            
        except (ImportError, ValueError):
            pass
        
        logger.warning(
            "No tray indicator available. "
            "Install gir1.2-ayatanaappindicator3-0.1 for tray support."
        )
    
    def _create_menu_gtk3(self):
        """Create GTK3 menu for AppIndicator (required by AppIndicator)"""
        # AppIndicator requires GTK3 menus
        gi.require_version('Gtk', '3.0')
        from gi.repository import Gtk as Gtk3
        
        menu = Gtk3.Menu()
        
        # Show main window
        item_show = Gtk3.MenuItem.new_with_label("Open NervaOS")
        item_show.connect('activate', lambda _: self._app.activate())
        menu.append(item_show)
        
        # Spotlight
        item_spotlight = Gtk3.MenuItem.new_with_label("Quick Search (Super+Space)")
        item_spotlight.connect('activate', lambda _: self._app.show_spotlight())
        menu.append(item_spotlight)
        
        menu.append(Gtk3.SeparatorMenuItem())
        
        # Settings
        item_settings = Gtk3.MenuItem.new_with_label("Settings")
        item_settings.connect('activate', lambda _: self._on_settings())
        menu.append(item_settings)
        
        menu.append(Gtk3.SeparatorMenuItem())
        
        # Quit
        item_quit = Gtk3.MenuItem.new_with_label("Quit")
        item_quit.connect('activate', lambda _: self._app.quit())
        menu.append(item_quit)
        
        menu.show_all()
        return menu
    
    def set_status(self, status: str):
        """
        Update the tray icon status.
        
        Args:
            status: One of 'idle', 'processing', 'error', 'offline'
        """
        try:
            self._status = TrayStatus(status)
        except ValueError:
            self._status = TrayStatus.IDLE
        
        icon_name = f"nervaos-{self._status.value}"
        
        if self._indicator:
            self._indicator.set_icon(icon_name)
        
        logger.debug(f"Tray status: {self._status.value}")
    
    def show_notification(self, title: str, message: str, icon: str = 'nervaos'):
        """Show a system notification"""
        try:
            notification = Gio.Notification.new(title)
            notification.set_body(message)
            notification.set_icon(Gio.ThemedIcon.new(icon))
            
            self._app.send_notification('nervaos-notification', notification)
            
        except Exception as e:
            logger.error(f"Failed to show notification: {e}")
    
    def _on_settings(self):
        """Handle settings menu item"""
        self._app.activate()
        if hasattr(self._app, '_main_window') and self._app._main_window:
            self._app._main_window.show_settings()


class TrayStatusWidget(Gtk.Box):
    """
    A GTK4 widget showing current status.
    Used when no system tray is available.
    """
    
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        
        self._status = TrayStatus.IDLE
        
        # Status indicator dot
        self._indicator = Gtk.Box()
        self._indicator.set_size_request(12, 12)
        self._indicator.add_css_class('status-indicator')
        self._indicator.add_css_class('status-idle')
        self.append(self._indicator)
        
        # Status label
        self._label = Gtk.Label(label="Ready")
        self.append(self._label)
    
    def set_status(self, status: str):
        """Update status display"""
        try:
            new_status = TrayStatus(status)
        except ValueError:
            new_status = TrayStatus.IDLE
        
        # Remove old class
        self._indicator.remove_css_class(f'status-{self._status.value}')
        
        # Set new status
        self._status = new_status
        self._indicator.add_css_class(f'status-{self._status.value}')
        
        # Update label
        labels = {
            TrayStatus.IDLE: "Ready",
            TrayStatus.PROCESSING: "Thinking...",
            TrayStatus.ERROR: "Error",
            TrayStatus.OFFLINE: "Offline"
        }
        self._label.set_label(labels.get(self._status, "Unknown"))
