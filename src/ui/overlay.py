"""
NervaOS Spotlight Overlay - Quick search and command interface

A floating, semi-transparent overlay that appears with Super+Space.
Provides quick access to AI queries without opening the full window.
"""

import logging
from typing import Optional

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gdk, GLib, Pango

logger = logging.getLogger('nerva-spotlight')


class SpotlightOverlay(Adw.Window):
    """
    A spotlight-style floating search bar.
    
    Features:
    - Centered on screen
    - Semi-transparent background
    - Auto-focus on entry
    - Escape to close
    - Enter to submit
    - Shows response inline
    """
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        self._setup_window()
        self._setup_ui()
        self._setup_shortcuts()
    
    def _setup_window(self):
        """Configure window properties"""
        self.set_title("NervaOS")
        self.set_default_size(600, 80)
        self.set_resizable(False)
        self.set_modal(True)
        self.set_decorated(False)  # No title bar
        
        # Center on screen
        # Note: GTK4 doesn't have set_position, we handle this via CSS/display
        
        # Make it floating above other windows
        self.set_deletable(False)  # No close button
    
    def _setup_ui(self):
        """Build the UI"""
        # Main container with styling
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        main_box.add_css_class('spotlight-overlay')
        main_box.set_margin_top(16)
        main_box.set_margin_bottom(16)
        main_box.set_margin_start(16)
        main_box.set_margin_end(16)
        
        # Header with branding
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        
        # Logo/icon
        icon = Gtk.Image.new_from_icon_name('system-search-symbolic')
        icon.set_pixel_size(24)
        header.append(icon)
        
        # Title
        title = Gtk.Label(label="NervaOS")
        title.add_css_class('title-4')
        header.append(title)
        
        # Status indicator
        self._status_dot = Gtk.Box()
        self._status_dot.set_size_request(8, 8)
        self._status_dot.add_css_class('status-indicator')
        self._status_dot.add_css_class('status-idle')
        self._status_dot.set_valign(Gtk.Align.CENTER)
        self._status_dot.set_halign(Gtk.Align.END)
        self._status_dot.set_hexpand(True)
        header.append(self._status_dot)
        
        main_box.append(header)
        
        # Search entry
        self._entry = Gtk.Entry()
        self._entry.set_placeholder_text("Ask anything... (Press Enter to submit, Escape to close)")
        self._entry.add_css_class('spotlight-entry')
        self._entry.connect('activate', self._on_submit)
        main_box.append(self._entry)
        
        # Response area (hidden initially)
        self._response_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self._response_box.set_visible(False)
        
        # Loading spinner
        self._spinner = Gtk.Spinner()
        self._spinner.set_size_request(24, 24)
        self._spinner_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self._spinner_box.set_halign(Gtk.Align.CENTER)
        self._spinner_box.append(self._spinner)
        self._spinner_box.set_visible(False)
        self._response_box.append(self._spinner_box)
        
        # Response label
        self._response_label = Gtk.Label()
        self._response_label.set_wrap(True)
        self._response_label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self._response_label.set_xalign(0)
        self._response_label.set_selectable(True)
        self._response_label.add_css_class('response-bubble')
        self._response_label.add_css_class('assistant')
        self._response_label.set_visible(False)
        self._response_box.append(self._response_label)
        
        # Action buttons (shown after response)
        self._action_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._action_box.set_halign(Gtk.Align.END)
        self._action_box.set_visible(False)
        
        copy_btn = Gtk.Button(label="Copy")
        copy_btn.connect('clicked', self._on_copy)
        self._action_box.append(copy_btn)
        
        open_btn = Gtk.Button(label="Open in Window")
        open_btn.connect('clicked', self._on_open_full)
        self._action_box.append(open_btn)
        
        self._response_box.append(self._action_box)
        main_box.append(self._response_box)
        
        self.set_content(main_box)
    
    def _setup_shortcuts(self):
        """Set up keyboard shortcuts"""
        controller = Gtk.EventControllerKey()
        controller.connect('key-pressed', self._on_key_pressed)
        self.add_controller(controller)
    
    def _on_key_pressed(self, controller, keyval, keycode, state):
        """Handle key presses"""
        if keyval == Gdk.KEY_Escape:
            self._close()
            return True
        return False
    
    def focus_entry(self):
        """Focus the search entry"""
        self._entry.grab_focus()
    
    def _on_submit(self, entry):
        """Handle query submission"""
        query = entry.get_text().strip()
        
        if not query:
            return
        
        # Show loading state
        self._show_loading()
        
        # Send query to daemon
        app = self.get_application()
        if app:
            app.send_query(query, self._on_response)
    
    def _show_loading(self):
        """Show loading state"""
        self._response_box.set_visible(True)
        self._spinner_box.set_visible(True)
        self._spinner.start()
        self._response_label.set_visible(False)
        self._action_box.set_visible(False)
        
        # Update status
        self._status_dot.remove_css_class('status-idle')
        self._status_dot.add_css_class('status-processing')
        
        # Expand window to show response
        self.set_default_size(600, 200)
    
    def _on_response(self, response: Optional[str], error: Optional[str]):
        """Handle response from daemon"""
        self._spinner.stop()
        self._spinner_box.set_visible(False)
        
        if error:
            self._response_label.set_text(f"Error: {error}")
            self._status_dot.remove_css_class('status-processing')
            self._status_dot.add_css_class('status-error')
        else:
            self._response_label.set_text(response or "No response")
            self._status_dot.remove_css_class('status-processing')
            self._status_dot.add_css_class('status-idle')
        
        self._response_label.set_visible(True)
        self._action_box.set_visible(True)
        
        # Adjust window height based on content
        # GTK4 will auto-resize based on content
    
    def _on_copy(self, button):
        """Copy response to clipboard"""
        text = self._response_label.get_text()
        clipboard = self.get_clipboard()
        clipboard.set(text)
        
        # Show feedback
        button.set_label("Copied!")
        GLib.timeout_add(1500, lambda: button.set_label("Copy"))
    
    def _on_open_full(self, button):
        """Open the response in the main window"""
        app = self.get_application()
        if app:
            app.activate()
            # Could pass the current query/response here
        self._close()
    
    def _close(self):
        """Close the overlay"""
        # Reset state
        self._entry.set_text("")
        self._response_box.set_visible(False)
        self._spinner.stop()
        self._status_dot.remove_css_class('status-processing')
        self._status_dot.remove_css_class('status-error')
        self._status_dot.add_css_class('status-idle')
        
        # Reset size
        self.set_default_size(600, 80)
        
        self.hide()
    
    def do_show(self):
        """Called when window is shown"""
        Adw.Window.do_show(self)
        
        # Focus entry after showing
        GLib.idle_add(self.focus_entry)


class SpotlightResult(Gtk.Box):
    """A single result item in spotlight suggestions"""
    
    def __init__(self, title: str, description: str, icon_name: str = 'dialog-information-symbolic'):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        
        self.add_css_class('spotlight-result')
        self.set_margin_top(8)
        self.set_margin_bottom(8)
        self.set_margin_start(12)
        self.set_margin_end(12)
        
        # Icon
        icon = Gtk.Image.new_from_icon_name(icon_name)
        icon.set_pixel_size(32)
        self.append(icon)
        
        # Text content
        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        
        title_label = Gtk.Label(label=title)
        title_label.set_xalign(0)
        title_label.add_css_class('heading')
        text_box.append(title_label)
        
        desc_label = Gtk.Label(label=description)
        desc_label.set_xalign(0)
        desc_label.add_css_class('dim-label')
        text_box.append(desc_label)
        
        self.append(text_box)
