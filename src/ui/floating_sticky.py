"""
NervaOS Sticky Floating Widget

Uses gtk-layer-shell for proper "always on top" sticky widget behavior.
Falls back to regular window if layer-shell is not available.
"""

import logging
import subprocess
import os
import shutil
from typing import Optional, Callable, List, Tuple

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
from gi.repository import Gtk, Gdk, GLib, Pango, Gio

from .message_renderers import WebSearchRenderer, MessageRenderer
from .components.history_panel import HistoryPanel

# Try to import layer shell
try:
    gi.require_version('Gtk4LayerShell', '1.0')
    from gi.repository import Gtk4LayerShell
    LAYER_SHELL_AVAILABLE = True
except (ValueError, ImportError):
    LAYER_SHELL_AVAILABLE = False
    # Only warn if not on X11 (where it's expected to fail)
    if os.environ.get('XDG_SESSION_TYPE') != 'x11':
        print("⚠️  gtk4-layer-shell not available. Widget will not be sticky.")


logger = logging.getLogger('nerva-sticky')


class StickyFloatingWidget(Gtk.Window):
    """
    A truly sticky floating widget that:
    - Stays on top of all windows
    - Is movable by dragging
    - Persists across workspace changes
    - Uses layer-shell protocol when available
    """
    
    def __init__(self, send_query_callback: Callable = None, **kwargs):
        super().__init__(**kwargs)
        
        self._send_query = send_query_callback
        self._expanded = False
        self._history_visible = False
        self._drag_start_x = 0
        self._drag_start_y = 0
        self._daemon_proxy = None  # Will be set by parent
        self._wmctrl_monitor_id: Optional[int] = None
        
        self._setup_layer_shell()
        self._setup_window()
        self._setup_ui()
        self._setup_styles()
    
    def _setup_layer_shell(self):
        """Initialize layer shell or fallback to wmctrl"""
        if not LAYER_SHELL_AVAILABLE:
            logger.warning("Layer shell not available - using wmctrl fallback")
            # We'll use wmctrl after window is realized
            self.connect('realize', self._setup_always_on_top_fallback)
            return
        
        # Initialize layer shell
        try:
            Gtk4LayerShell.init_for_window(self)
            
            # Set to top layer (above all windows)
            Gtk4LayerShell.set_layer(self, Gtk4LayerShell.Layer.TOP)
            
            # Set anchor to bottom-left
            Gtk4LayerShell.set_anchor(self, Gtk4LayerShell.Edge.BOTTOM, True)
            Gtk4LayerShell.set_anchor(self, Gtk4LayerShell.Edge.LEFT, True)
            
            # Add margin from edges
            Gtk4LayerShell.set_margin(self, Gtk4LayerShell.Edge.BOTTOM, 20)
            Gtk4LayerShell.set_margin(self, Gtk4LayerShell.Edge.LEFT, 20)
            
            # Set namespace for window manager
            Gtk4LayerShell.set_namespace(self, "nerva-widget")
            
            # Enable keyboard interactivity when expanded
            Gtk4LayerShell.set_keyboard_mode(self, Gtk4LayerShell.KeyboardMode.ON_DEMAND)
            
            logger.info("✓ Layer shell initialized - widget is now sticky!")
        except Exception as e:
            logger.error(f"Failed to init layer shell: {e}")
            self.connect('realize', self._setup_always_on_top_fallback)
    
    def _setup_always_on_top_fallback(self, *args):
        """Fallback method using wmctrl for always-on-top"""
        # Wait a bit for window to be fully mapped
        GLib.timeout_add(500, self._apply_wmctrl_hints)
        self._start_wmctrl_monitor()

    def _start_wmctrl_monitor(self):
        """Re-apply hints periodically so widget stays global across windows/workspaces."""
        if self._wmctrl_monitor_id is not None:
            return

        def _tick():
            if not self.get_visible():
                return True
            self._apply_wmctrl_hints()
            return True

        # Every 2s is enough to keep hints stable without being noisy.
        self._wmctrl_monitor_id = GLib.timeout_add_seconds(2, _tick)

    def _stop_wmctrl_monitor(self):
        if self._wmctrl_monitor_id is not None:
            GLib.source_remove(self._wmctrl_monitor_id)
            self._wmctrl_monitor_id = None

    def _find_window_ids(self) -> List[str]:
        """Find this widget's X11 window ids using title lookup."""
        title = self.get_title() or "NervaOS Bubble"
        ids: List[str] = []
        if not shutil.which("xdotool"):
            return ids
        try:
            proc = subprocess.run(
                ['xdotool', 'search', '--name', title],
                capture_output=True,
                text=True,
                timeout=1.0
            )
            if proc.returncode == 0 and proc.stdout.strip():
                ids = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
        except Exception:
            return []
        return ids
    
    def _apply_wmctrl_hints(self):
        """Apply window manager hints using wmctrl"""
        if not self.get_visible():
            return False
        if not shutil.which("wmctrl"):
            logger.warning("wmctrl not found - widget may not stay on top")
            logger.warning("Install with: sudo apt install wmctrl")
            return False

        try:
            title = self.get_title()

            # Prefer exact window IDs (reliable). Fallback to title target.
            targets = self._find_window_ids()
            ok = False
            if targets:
                for wid in targets:
                    r1 = subprocess.run(
                        ['wmctrl', '-i', '-r', wid, '-b', 'add,above,sticky,skip_taskbar,skip_pager'],
                        capture_output=True,
                        timeout=1
                    )
                    # Force all desktops/workspaces
                    subprocess.run(['wmctrl', '-i', '-r', wid, '-t', '-1'], capture_output=True, timeout=1)
                    if r1.returncode == 0:
                        ok = True
            else:
                r1 = subprocess.run(
                    ['wmctrl', '-r', title, '-b', 'add,above,sticky,skip_taskbar,skip_pager'],
                    capture_output=True,
                    timeout=1
                )
                subprocess.run(['wmctrl', '-r', title, '-t', '-1'], capture_output=True, timeout=1)
                ok = (r1.returncode == 0)

            if ok:
                logger.info("✓ Applied sticky widget hints (above + all workspaces)")
            else:
                logger.warning("wmctrl could not match bubble window yet; will retry")
        except Exception as e:
            logger.error(f"Failed to apply wmctrl hints: {e}")
        
        return False  # Don't repeat
    
    def _setup_window(self):
        """Configure window properties"""
        self.set_title("NervaOS Bubble")
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_default_size(90, 90)  # Fit icon + NERVA AI label
        
        # Connect to map event to ensure always-on-top after window is shown
        self.connect('map', self._on_window_mapped)
        self.connect('notify::visible', self._on_visibility_changed)

    def _on_visibility_changed(self, *args):
        if self.get_visible():
            self._start_wmctrl_monitor()
            GLib.timeout_add(120, self._apply_wmctrl_hints)
        else:
            self._stop_wmctrl_monitor()
    
    def _on_window_mapped(self, widget):
        """Called when window is mapped (shown) - ensure it stays on top"""
        # Re-apply wmctrl hints after window is shown to ensure they stick
        GLib.timeout_add(100, self._apply_wmctrl_hints)
        GLib.timeout_add(500, self._apply_wmctrl_hints)  # Apply again for safety
        self._start_wmctrl_monitor()
        return False
    
    def _setup_ui(self):
        """Build the UI"""
        # Main container
        self._main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._main_box.add_css_class('sticky-widget')
        
        # === BUBBLE VIEW (Minimized) ===
        self._bubble_view = self._create_bubble_view()
        self._main_box.append(self._bubble_view)
        
        # === EXPANDED VIEW CONTAINER (History + Chat) ===
        expanded_container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        expanded_container.set_visible(False)
        
        # History Panel (left side)
        self._history_panel = HistoryPanel(
            on_conversation_selected=self._load_conversation,
            on_search=self._search_history,
            on_delete=self._on_delete_conversation,
            on_clear_all=self._on_clear_all_conversations
        )
        self._current_conversation_id: Optional[int] = None
        self._history_panel.set_visible(False)
        expanded_container.append(self._history_panel)
        
        # Chat Panel (right side)
        self._expanded_view = self._create_expanded_view()
        expanded_container.append(self._expanded_view)
        
        self._expanded_container = expanded_container
        self._main_box.append(expanded_container)
        
        self.set_child(self._main_box)
        
        # Setup drag-to-move
        self._setup_drag()
    
    def _create_bubble_view(self):
        """Create NERVA AI branded bubble with icon"""
        # Use WindowHandle for dragging
        window_handle = Gtk.WindowHandle()
        window_handle.add_css_class('bubble-window-handle')
        window_handle.set_halign(Gtk.Align.CENTER)
        window_handle.set_valign(Gtk.Align.CENTER)
        
        # Container box for icon + label
        bubble_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        bubble_container.set_halign(Gtk.Align.CENTER)
        bubble_container.set_valign(Gtk.Align.CENTER)
        
        # Circular button with white background
        self._bubble_btn = Gtk.Button()
        self._bubble_btn.add_css_class('nerva-bubble-circle')
        self._bubble_btn.set_size_request(64, 64)
        
        # Load icon from assets with relative path
        current_dir = os.path.dirname(os.path.abspath(__file__))
        # src/ui -> src/assets
        icon_path = os.path.join(current_dir, '..', 'assets', 'message.png')
        
        try:
            if os.path.exists(icon_path):
                icon_image = Gtk.Image.new_from_file(icon_path)
                icon_image.set_pixel_size(36)
                logger.info(f"✓ Loaded NERVA icon from {icon_path}")
            else:
                # Fallback to system icon
                icon_image = Gtk.Image.new_from_icon_name('chat-bubble-symbolic')
                icon_image.set_pixel_size(36)
                logger.warning(f"Icon not found at {icon_path}, using fallback")
        except Exception as e:
            logger.error(f"Failed to load icon: {e}")
            icon_image = Gtk.Image.new_from_icon_name('chat-bubble-symbolic')
            icon_image.set_pixel_size(36)
        
        icon_image.add_css_class('nerva-icon')
        self._bubble_btn.set_child(icon_image)
        self._bubble_btn.connect('clicked', self._toggle_expand)
        
        bubble_container.append(self._bubble_btn)
        
        # "NERVA AI" branding label
        brand_label = Gtk.Label(label="NERVA AI v2")  # v2 = CLEAN version, no stats!
        brand_label.add_css_class('nerva-brand-label')
        bubble_container.append(brand_label)
        
        # Right-click menu
        menu_gesture = Gtk.GestureClick()
        menu_gesture.set_button(3)
        menu_gesture.connect('pressed', self._show_context_menu)
        self._bubble_btn.add_controller(menu_gesture)
        
        window_handle.set_child(bubble_container)
        window_handle.set_cursor(Gdk.Cursor.new_from_name('grab'))
        
        return window_handle
    
    def _create_expanded_view(self):
        """Create the modern expanded chat panel"""
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        panel.add_css_class('chat-panel')
        panel.set_visible(False)
        panel.set_size_request(420, 600)  # Slightly larger for better UX
        
        # Store reference for model selector refresh
        self._expanded_panel = panel
        
        # Modern header with gradient
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        header.add_css_class('chat-header')
        header.add_css_class('modern-header')
        header.set_margin_top(16)
        header.set_margin_start(20)
        header.set_margin_end(20)
        header.set_margin_bottom(16)
        
        # Icon with modern styling
        icon = Gtk.Image.new_from_icon_name('chat-bubbles-symbolic')
        icon.set_pixel_size(28)
        header.append(icon)
        
        # Title with better styling
        title = Gtk.Label(label="NERVA AI")
        title.add_css_class('chat-title')
        title.add_css_class('header-title')
        title.set_hexpand(True)
        title.set_xalign(0)
        header.append(title)
        
        # Model selector container (will be populated)
        self._model_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self._model_combo = None
        self._model_choices: List[Tuple[str, str]] = []
        
        # Create and populate model selector
        self._refresh_model_selector(header)
        
        # History button with modern style
        history_btn = Gtk.Button()
        history_btn.add_css_class('header-action-btn')
        history_btn.set_icon_name('view-list-symbolic')
        history_btn.set_tooltip_text('Chat History')
        history_btn.connect('clicked', lambda b: self._toggle_history())
        header.append(history_btn)

        # Open full app settings
        settings_btn = Gtk.Button()
        settings_btn.add_css_class('header-action-btn')
        settings_btn.set_icon_name('emblem-system-symbolic')
        settings_btn.set_tooltip_text('Open Settings')
        settings_btn.connect('clicked', lambda b: self._open_settings_page())
        header.append(settings_btn)
        
        # Minimize button with modern style
        minimize_btn = Gtk.Button()
        minimize_btn.add_css_class('header-action-btn')
        minimize_btn.set_icon_name('window-minimize-symbolic')
        minimize_btn.set_tooltip_text('Minimize')
        minimize_btn.connect('clicked', self._toggle_expand)
        header.append(minimize_btn)
        
        panel.append(header)
        
        # Chat area (scrollable) with modern styling
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_kinetic_scrolling(True)
        scroll.set_overlay_scrolling(True)
        scroll.add_css_class('chat-scroll')
        scroll.set_margin_top(8)
        
        self._chat_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self._chat_box.set_margin_start(20)
        self._chat_box.set_margin_end(20)
        self._chat_box.set_margin_top(16)
        self._chat_box.set_margin_bottom(16)
        self._chat_box.add_css_class('chat-messages-container')
        
        scroll.set_child(self._chat_box)
        panel.append(scroll)
        
        # Modern input area
        input_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        input_container.add_css_class('input-container')
        input_container.set_margin_start(20)
        input_container.set_margin_end(20)
        input_container.set_margin_bottom(20)
        input_container.set_margin_top(12)
        
        input_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        input_box.add_css_class('input-box')
        
        self._entry = Gtk.Entry()
        self._entry.set_placeholder_text("Message NervaOS...")
        self._entry.add_css_class('modern-input')
        self._entry.set_hexpand(True)
        self._entry.connect('activate', self._on_send)
        input_box.append(self._entry)
        
        send_btn = Gtk.Button()
        send_btn.add_css_class('send-button')
        send_btn.set_icon_name('paper-plane-symbolic')
        send_btn.set_tooltip_text('Send')
        send_btn.connect('clicked', self._on_send)
        input_box.append(send_btn)
        
        input_container.append(input_box)
        panel.append(input_container)
        
        return panel
    
    def _setup_drag(self):
        """Enable dragging the widget"""
        # WindowHandle already provides native drag-to-move functionality
        # for undecorated windows, no additional setup needed!
        # The bubble view uses WindowHandle which handles all the dragging.
        pass

    def _get_monitor_size(self):
        """Get active monitor width/height for responsive sizing."""
        try:
            display = Gdk.Display.get_default()
            if not display:
                return (1280, 800)
            monitor = None
            surface = self.get_surface()
            if surface:
                monitor = display.get_monitor_at_surface(surface)
            if monitor is None:
                monitor = display.get_primary_monitor()
            if monitor is None:
                monitors = display.get_monitors()
                if monitors and monitors.get_n_items() > 0:
                    monitor = monitors.get_item(0)
            if not monitor:
                return (1280, 800)
            geo = monitor.get_geometry()
            return (max(800, geo.width), max(600, geo.height))
        except Exception:
            return (1280, 800)

    def _apply_responsive_panel_size(self):
        """Resize expanded panel based on monitor dimensions."""
        mw, mh = self._get_monitor_size()
        base_w = int(mw * 0.38)
        if self._history_visible:
            base_w += int(mw * 0.20)
        width = max(360, min(base_w, int(mw * 0.90)))
        height = max(460, min(int(mh * 0.76), mh - 80))
        self.set_default_size(width, height)

    def _wrap_message_widget(self, widget: Gtk.Widget, is_user: bool) -> Gtk.Widget:
        """Create a full-width row so bubbles align properly and stay responsive."""
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        row.set_hexpand(True)
        row.set_halign(Gtk.Align.FILL)
        row.add_css_class('message-row')

        spacer = Gtk.Box()
        spacer.set_hexpand(True)

        widget.add_css_class('message-max-width')
        if is_user:
            row.append(spacer)
            row.append(widget)
        else:
            row.append(widget)
            row.append(spacer)
        return row
    
    def _toggle_expand(self, *args):
        """Toggle between bubble and chat panel"""
        self._expanded = not self._expanded
        
        if self._expanded:
            self._bubble_view.set_visible(False)
            self._expanded_container.set_visible(True)
            self._expanded_view.set_visible(True)
            
            # Responsive size based on monitor
            self._apply_responsive_panel_size()
            
            # Set window and entry to accept focus
            self.set_can_focus(True)
            
            # Grab focus after a short delay to ensure window is ready  
            GLib.timeout_add(100, self._grab_input_focus)
            
            # Enable keyboard mode for layer shell
            if LAYER_SHELL_AVAILABLE:
                Gtk4LayerShell.set_keyboard_mode(self, Gtk4LayerShell.KeyboardMode.EXCLUSIVE)
        else:
            self._bubble_view.set_visible(True)
            self._expanded_container.set_visible(False)
            self.set_default_size(90, 90)  # Match bubble + label size
            
            # Disable keyboard mode
            if LAYER_SHELL_AVAILABLE:
                Gtk4LayerShell.set_keyboard_mode(self, Gtk4LayerShell.KeyboardMode.NONE)
    
    def _grab_input_focus(self):
        """Helper to grab input focus"""
        try:
            self._entry.grab_focus()
            self._entry.set_can_focus(True)
            logger.info("✓ Input focus grabbed")
        except Exception as e:
            logger.error(f"Failed to grab focus: {e}")
        return False  # Don't repeat
    
    def _show_context_menu(self, gesture, n_press, x, y):
        """Show right-click quick actions menu"""
        from ..core.quick_actions import QuickActions
        
        if not hasattr(self, '_quick_actions'):
            self._quick_actions = QuickActions()
        
        popover = Gtk.Popover()
        popover.set_parent(self._bubble_btn)
        
        menu_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        menu_box.set_margin_top(6)
        menu_box.set_margin_bottom(6)
        menu_box.set_margin_start(6)
        menu_box.set_margin_end(6)
        
        # Header
        header = Gtk.Label(label="Quick Actions")
        header.add_css_class('menu-header')
        header.set_margin_bottom(6)
        menu_box.append(header)
        
        # Separator
        sep1 = Gtk.Separator()
        menu_box.append(sep1)
        
        # Screenshot submenu
        screenshot_expander = Gtk.Expander(label="📸 Screenshot")
        screenshot_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        screenshot_box.set_margin_start(12)
        screenshot_box.set_margin_top(4)
        
        ss_full = Gtk.Button(label="Full Screen")
        ss_full.add_css_class('flat')
        ss_full.connect('clicked', lambda b: (self._quick_actions.screenshot_full(), popover.popdown()))
        screenshot_box.append(ss_full)
        
        ss_area = Gtk.Button(label="Select Area")
        ss_area.add_css_class('flat')
        ss_area.connect('clicked', lambda b: (self._quick_actions.screenshot_area(), popover.popdown()))
        screenshot_box.append(ss_area)
        
        ss_window = Gtk.Button(label="Active Window")
        ss_window.add_css_class('flat')
        ss_window.connect('clicked', lambda b: (self._quick_actions.screenshot_window(), popover.popdown()))
        screenshot_box.append(ss_window)
        
        screenshot_expander.set_child(screenshot_box)
        menu_box.append(screenshot_expander)
        
        # Screen Record
        record_btn = Gtk.Button(label="🎥 Screen Record")
        record_btn.add_css_class('flat')
        record_btn.connect('clicked', lambda b: (self._quick_actions.screen_record_start(), popover.popdown()))
        menu_box.append(record_btn)
        
        # Quick Note
        note_btn = Gtk.Button(label="📝 Quick Note")
        note_btn.add_css_class('flat')
        note_btn.connect('clicked', lambda b: (self._quick_actions.quick_note(), popover.popdown()))
        menu_box.append(note_btn)
        
        # Separator
        sep2 = Gtk.Separator()
        sep2.set_margin_top(4)
        sep2.set_margin_bottom(4)
        menu_box.append(sep2)
        
        # WiFi Toggle
        wifi_btn = Gtk.Button(label="📶 Toggle WiFi")
        wifi_btn.add_css_class('flat')
        wifi_btn.connect('clicked', lambda b: self._quick_actions.toggle_wifi())
        menu_box.append(wifi_btn)
        
        # Bluetooth Toggle
        bt_btn = Gtk.Button(label="🔵 Toggle Bluetooth")
        bt_btn.add_css_class('flat')
        bt_btn.connect('clicked', lambda b: self._quick_actions.toggle_bluetooth())
        menu_box.append(bt_btn)
        
        # Separator
        sep3 = Gtk.Separator()
        sep3.set_margin_top(4)
        sep3.set_margin_bottom(4)
        menu_box.append(sep3)
        
        # Power options submenu
        power_expander = Gtk.Expander(label="⚡ Power")
        power_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        power_box.set_margin_start(12)
        power_box.set_margin_top(4)
        
        lock_btn = Gtk.Button(label="🔒 Lock Screen")
        lock_btn.add_css_class('flat')
        lock_btn.connect('clicked', lambda b: (self._quick_actions.lock_screen(), popover.popdown()))
        power_box.append(lock_btn)
        
        sleep_btn = Gtk.Button(label="😴 Sleep")
        sleep_btn.add_css_class('flat')
        sleep_btn.connect('clicked', lambda b: (self._quick_actions.sleep_system(), popover.popdown()))
        power_box.append(sleep_btn)
        
        reboot_btn = Gtk.Button(label="🔄 Reboot")
        reboot_btn.add_css_class('flat')
        reboot_btn.connect('clicked', lambda b: (self._quick_actions.reboot_system(), popover.popdown()))
        power_box.append(reboot_btn)
        
        shutdown_btn = Gtk.Button(label="⏻ Shutdown")
        shutdown_btn.add_css_class('flat')
        shutdown_btn.add_css_class('destructive-action')
        shutdown_btn.connect('clicked', lambda b: (self._quick_actions.shutdown_system(), popover.popdown()))
        power_box.append(shutdown_btn)
        
        power_expander.set_child(power_box)
        menu_box.append(power_expander)
        
        # Separator
        sep4 = Gtk.Separator()
        sep4.set_margin_top(4)
        sep4.set_margin_bottom(4)
        menu_box.append(sep4)
        
        # Hide/Minimize button (can't actually quit - always running!)
        hide_btn = Gtk.Button(label="➖ Minimize")
        hide_btn.add_css_class('flat')
        hide_btn.connect('clicked', lambda b: (self._toggle_expand() if self._expanded else None, popover.popdown()))
        menu_box.append(hide_btn)

        # Open full app settings page
        settings_menu_btn = Gtk.Button(label="⚙ Open Settings")
        settings_menu_btn.add_css_class('flat')
        settings_menu_btn.connect('clicked', lambda b: (self._open_settings_page(), popover.popdown()))
        menu_box.append(settings_menu_btn)
        
        popover.set_child(menu_box)
        popover.popup()

    def _open_settings_page(self):
        """Open the full app and navigate to Settings page."""
        try:
            app = Gio.Application.get_default()
            if app:
                # Ensure main window is shown, then route to settings action.
                app.activate()
                app.activate_action('settings', None)
                return
        except Exception as e:
            logger.warning(f"Could not open settings via app action: {e}")

        # Fallback: start the full UI process.
        try:
            subprocess.Popen(['/usr/bin/nerva-ui'])
        except Exception as e:
            logger.error(f"Failed to launch full UI for settings: {e}")
    
    def _on_send(self, widget):
        """Send chat message"""
        text = self._entry.get_text().strip()
        if not text:
            return
        
        # Add user message
        self._add_message(text, is_user=True)
        self._entry.set_text("")
        
        # Show thinking state
        # (Status label removed for cleaner UI)
        thinking = Gtk.Label(label="...")
        thinking.add_css_class('thinking-indicator')
        thinking.set_halign(Gtk.Align.START)
        self._chat_box.append(thinking)
        self._thinking_label = thinking
        
        # Send to daemon
        if self._send_query:
            self._send_query(text, self._on_response)
    
    def _add_message(self, text: str, is_user: bool):
        """Add a message to the chat with clickable file links"""
        import re
        import subprocess
        
        # Check if this is a web search result
        if '🌐 **Web Search:' in text and not is_user:
            web_widget = WebSearchRenderer.create_widget(text, self._open_url)
            self._chat_box.append(web_widget)
            GLib.idle_add(self._scroll_to_bottom)
            return
        
        # Check if message contains file paths (search results)
        if '📁 Path:' in text and not is_user:
            # This is a search result - create interactive message
            message_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            message_box.set_margin_start(8)
            message_box.set_margin_end(8)
            message_box.set_margin_top(4)
            message_box.set_margin_bottom(4)
            
            if is_user:
                message_box.set_halign(Gtk.Align.END)
            else:
                message_box.set_halign(Gtk.Align.START)
            
            # Parse file results
            lines = text.split('\n')
            current_file = None
            
            for line in lines:
                if line.startswith('🔍'):
                    # Header
                    label = Gtk.Label(label=line)
                    label.set_xalign(0)
                    label.set_wrap(True)
                    label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
                    label.add_css_class('search-header')
                    message_box.append(label)
                
                elif line.startswith('**') and '. ' in line:
                    # File name
                    file_name = line.replace('**', '').strip()
                    label = Gtk.Label(label=file_name)
                    label.set_xalign(0)
                    label.set_wrap(True)
                    label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
                    label.set_margin_top(8)
                    label.add_css_class('file-result-name')
                    message_box.append(label)
                
                elif '📁 Path:' in line:
                    # File path - make it clickable
                    path_match = re.search(r'`([^`]+)`', line)
                    if path_match:
                        file_path = path_match.group(1)
                        
                        # Create clickable button with ellipsized path
                        path_btn = Gtk.Button()
                        path_btn.add_css_class('flat')
                        path_btn.add_css_class('file-path-button')
                        path_btn.set_hexpand(True)
                        path_btn.set_halign(Gtk.Align.FILL)

                        path_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                        icon = Gtk.Image.new_from_icon_name('folder-open-symbolic')
                        path_row.append(icon)

                        path_label = Gtk.Label(label=file_path)
                        path_label.set_xalign(0)
                        path_label.set_hexpand(True)
                        path_label.set_single_line_mode(True)
                        path_label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
                        path_label.add_css_class('path-preview-label')
                        path_row.append(path_label)

                        path_btn.set_child(path_row)
                        path_btn.set_tooltip_text(file_path)
                        path_btn.connect('clicked', lambda b, p=file_path: self._open_file(p))
                        message_box.append(path_btn)
                
                elif line.strip() and ('📊' in line or '🕒' in line):
                    # File metadata
                    label = Gtk.Label(label=line.strip())
                    label.set_xalign(0)
                    label.set_wrap(True)
                    label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
                    label.add_css_class('file-metadata')
                    message_box.append(label)
            
            message_box.add_css_class('message-bubble')
            if is_user:
                message_box.add_css_class('user-message')
            else:
                message_box.add_css_class('assistant-message')
            
            self._chat_box.append(self._wrap_message_widget(message_box, is_user))
        
        else:
            # Regular message - use beautiful renderer
            message_widget = MessageRenderer.create_regular_message(text, is_user)
            self._chat_box.append(self._wrap_message_widget(message_widget, is_user))
        
        GLib.idle_add(self._scroll_to_bottom)
    
    def _open_file(self, file_path: str):
        """Open file or folder in default application"""
        try:
            import subprocess
            from pathlib import Path
            
            path = Path(file_path)
            
            if path.is_dir():
                # Open folder in file manager
                subprocess.Popen(['xdg-open', str(path)])
                logger.info(f"Opened folder: {path}")
            elif path.exists():
                # Open file
                subprocess.Popen(['xdg-open', str(path)])
                logger.info(f"Opened file: {path}")
            else:
                logger.warning(f"File not found: {path}")
                
        except Exception as e:
            logger.error(f"Failed to open {file_path}: {e}")
    
    def _open_url(self, url: str):
        """Open URL in browser"""
        try:
            import subprocess
            subprocess.Popen(['xdg-open', url])
            logger.info(f"Opened URL: {url}")
        except Exception as e:
            logger.error(f"Failed to open URL {url}: {e}")
    
    def _scroll_to_bottom(self):
        """Scroll chat to bottom"""
        adj = self._chat_box.get_parent().get_vadjustment()
        target = max(adj.get_lower(), adj.get_upper() - adj.get_page_size())
        adj.set_value(target)
        return False
    
    def _on_response(self, response: Optional[str], error: Optional[str]):
        """Handle response from AI"""
        # Remove thinking indicator
        if hasattr(self, '_thinking_label') and self._thinking_label:
            self._chat_box.remove(self._thinking_label)
            self._thinking_label = None
        
        # Status label removed
        
        if error:
            self._add_message(f"❌ {error}", is_user=False)
        else:
            self._add_message(response or "No response", is_user=False)
        
        # Refresh history to show updated conversation
        GLib.timeout_add(500, self._load_history_data)
    
    def _setup_styles(self):
        """Apply NERVA AI bubble styles"""
        css_provider = Gtk.CssProvider()
        css = """
        .sticky-widget { background: transparent; }
        .bubble-window-handle { background: transparent; }
        
        .nerva-bubble-circle {
            background-color: white;
            border: none;
            border-radius: 32px;
            min-width: 64px;
            min-height: 64px;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
        }
        
        .nerva-icon {
            color: rgba(99, 102, 241, 1);
        }
        
        .nerva-brand-label {
            color: rgba(99, 102, 241, 1);
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 0.5px;
        }
        
        .menu-header {
            color: rgba(99, 102, 241, 1);
            font-size: 12px;
            font-weight: 700;
            letter-spacing: 0.5px;
        }
        
        .chat-panel {
            background-color: rgba(17, 24, 39, 0.98);
            border-radius: 24px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.6);
            border: 1px solid rgba(255, 255, 255, 0.08);
        }
        
        .chat-header {
            border-bottom: 1px solid rgba(99, 102, 241, 0.2);
            padding-bottom: 16px;
            border-top-left-radius: 24px;
            border-top-right-radius: 24px;
            background-image: linear-gradient(to bottom right, rgba(99, 102, 241, 0.1), rgba(139, 92, 246, 0.05));
        }
        
        .chat-title {
            color: white;
            font-size: 20px;
            font-weight: 700;
            letter-spacing: -0.5px;
        }
        
        .header-action-btn {
            min-width: 36px;
            min-height: 36px;
            border-radius: 10px;
            background-color: rgba(255, 255, 255, 0.08);
            border: 1px solid rgba(255, 255, 255, 0.15);
            color: rgba(209, 213, 219, 1);
            transition: all 0.2s ease;
        }
        
        .header-action-btn:hover {
            background-color: rgba(255, 255, 255, 0.15);
            border-color: rgba(255, 255, 255, 0.25);
        }
        
        .status-label {
            color: rgba(156, 163, 175, 1);
            font-size: 11px;
        }
        
        .chat-input {
            background-color: rgba(255, 255, 255, 0.06);
            border: 1px solid rgba(99, 102, 241, 0.2);
            border-radius: 14px;
            color: white;
            padding: 12px 18px;
            min-height: 44px;
        }
        
        .chat-input:focus {
            border-color: rgba(99, 102, 241, 0.4);
            box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
        }
        
        .message-bubble {
            padding: 16px 20px;
            border-radius: 20px;
            margin: 8px 0;
            transition: all 0.2s ease;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
        }
        
        .user-message {
            background-image: linear-gradient(to bottom right, rgba(99, 102, 241, 0.95), rgba(139, 92, 246, 0.9));
            color: white;
            margin-right: 0;
            border-bottom-right-radius: 6px;
            box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3);
        }
        
        .user-message:hover {
            box-shadow: 0 6px 16px rgba(99, 102, 241, 0.4);
        }
        
        .assistant-message {
            background-image: linear-gradient(to bottom right, rgba(30, 30, 40, 0.95), rgba(40, 40, 50, 0.9));
            color: rgba(229, 231, 235, 1);
            margin-left: 0;
            border-bottom-left-radius: 6px;
            border: 1px solid rgba(99, 102, 241, 0.15);
        }
        
        .assistant-message:hover {
            border-color: rgba(99, 102, 241, 0.25);
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
        }
        
        /* Beautiful message cards for ALL messages */
        .user-message-card {
            background-image: linear-gradient(to bottom right, rgba(99, 102, 241, 0.15), rgba(139, 92, 246, 0.15));
            border-radius: 14px;
            padding: 12px;
            border: 1px solid rgba(99, 102, 241, 0.3);
        }
        
        .assistant-message-card {
            background-image: linear-gradient(to bottom right, rgba(30, 30, 40, 0.6), rgba(40, 40, 50, 0.6));
            border-radius: 14px;
            padding: 12px;
            border: 1px solid rgba(99, 102, 241, 0.2);
        }
        
        .message-header {
            color: rgba(99, 102, 241, 1);
            font-size: 14px;
            font-weight: 700;
            margin-bottom: 4px;
        }
        
        .message-emphasis {
            color: rgba(139, 92, 246, 1);
            font-size: 13px;
            font-style: italic;
            margin-top: 4px;
            margin-bottom: 4px;
        }
        
        .message-text {
            color: rgba(229, 231, 235, 0.95);
            font-size: 13px;
            line-height: 1.5;
        }
        
        .bullet-point {
            color: rgba(99, 102, 241, 1);
            font-size: 14px;
            font-weight: 700;
        }
        
        .bullet-text {
            color: rgba(229, 231, 235, 0.95);
            font-size: 12px;
            line-height: 1.4;
        }
        
        /* File search result styles */
        .search-header {
            color: rgba(99, 102, 241, 1);
            font-size: 14px;
            font-weight: 700;
            margin-bottom: 8px;
        }
        
        .file-result-name {
            color: rgba(229, 231, 235, 1);
            font-size: 13px;
            font-weight: 600;
        }
        
        .file-path-button {
            background-color: rgba(99, 102, 241, 0.15);
            border-radius: 8px;
            padding: 8px 12px;
            margin-top: 4px;
            margin-bottom: 4px;
            color: rgba(99, 102, 241, 1);
            font-size: 11px;
        }
        
        .file-path-button:hover {
            background-color: rgba(99, 102, 241, 0.25);
        }
        
        .file-metadata {
            color: rgba(156, 163, 175, 1);
            font-size: 11px;
            margin-top: 2px;
        }
        
        /* Web Search Result Styles */
        .web-search-container {
            background-image: linear-gradient(to bottom right, rgba(99, 102, 241, 0.08), rgba(139, 92, 246, 0.08));
            border-radius: 16px;
            padding: 16px;
            border: 1px solid rgba(99, 102, 241, 0.2);
        }
        
        .web-search-header {
            padding: 8px;
            background-image: linear-gradient(to right, rgba(99, 102, 241, 0.15), rgba(139, 92, 246, 0.15));
            border-radius: 12px;
            margin-bottom: 12px;
        }
        
        .search-icon {
            font-size: 20px;
        }
        
        .search-query {
            color: rgba(99, 102, 241, 1);
            font-size: 14px;
            font-weight: 700;
        }
        
        .summary-card {
            background: rgba(139, 92, 246, 0.12);
            border-radius: 12px;
            padding: 12px;
            border-left: 3px solid rgba(139, 92, 246, 1);
            margin-bottom: 8px;
        }
        
        .summary-title {
            color: rgba(139, 92, 246, 1);
            font-size: 13px;
            font-weight: 700;
            margin-bottom: 6px;
        }
        
        .summary-text {
            color: rgba(229, 231, 235, 0.95);
            font-size: 12px;
            line-height: 1.5;
        }
        
        .sources-header {
            color: rgba(99, 102, 241, 1);
            font-size: 13px;
            font-weight: 700;
            margin-top: 8px;
            margin-bottom: 8px;
        }
        
        .source-card {
            background: rgba(30, 30, 40, 0.6);
            border-radius: 10px;
            padding: 10px;
            margin-bottom: 8px;
            border: 1px solid rgba(99, 102, 241, 0.15);
            transition: all 0.2s;
        }
        
        .source-card:hover {
            background: rgba(40, 40, 50, 0.8);
            border-color: rgba(99, 102, 241, 0.3);
        }
        
        .source-title-btn {
            background: none;
            border: none;
            color: rgba(99, 102, 241, 1);
            font-size: 12px;
            font-weight: 600;
            padding: 4px 0;
        }
        
        .source-title-btn:hover {
            color: rgba(139, 92, 246, 1);
            text-decoration: underline;
        }
        
        .source-snippet {
            color: rgba(200, 200, 210, 1);
            font-size: 11px;
            line-height: 1.4;
            margin-top: 4px;
        }
        
        .source-url {
            color: rgba(156, 163, 175, 1);
            font-size: 10px;
            margin-top: 4px;
            font-family: monospace;
        }
        
        .file-search-container {
            background-image: linear-gradient(to bottom right, rgba(16, 185, 129, 0.08), rgba(5, 150, 105, 0.08));
            border-radius: 16px;
            padding: 16px;
            border: 1px solid rgba(16, 185, 129, 0.2);
        }
        
        .file-search-header {
            color: rgba(16, 185, 129, 1);
            font-size: 14px;
            font-weight: 700;
            margin-bottom: 12px;
        }
        
        .file-result-card {
            background: rgba(30, 30, 40, 0.6);
            border-radius: 10px;
            padding: 10px;
            margin-bottom: 8px;
            border-left: 3px solid rgba(16, 185, 129, 1);
        }
        
        .thinking-indicator {
            color: rgba(156, 163, 175, 1);
            font-style: italic;
        }
        
        /* ===== GOD LEVEL MARKDOWN STYLES ===== */
        
        /* Headers */
        .message-h1 {
            color: rgba(139, 92, 246, 1);
            font-size: 18px;
            font-weight: 800;
            margin-top: 8px;
            margin-bottom: 8px;
            letter-spacing: -0.5px;
        }
        
        .message-h2 {
            color: rgba(99, 102, 241, 1);
            font-size: 16px;
            font-weight: 700;
            margin-top: 6px;
            margin-bottom: 6px;
        }
        
        .message-h3 {
            color: rgba(129, 140, 248, 1);
            font-size: 14px;
            font-weight: 600;
            margin-top: 4px;
            margin-bottom: 4px;
        }
        
        .message-bold {
            color: rgba(229, 231, 235, 1);
            font-size: 13px;
            font-weight: 700;
        }
        
        /* Lists */
        .message-list {
            margin-top: 4px;
            margin-bottom: 4px;
            margin-left: 4px;
        }
        
        .bullet-icon {
            color: rgba(139, 92, 246, 1);
            font-size: 16px;
            font-weight: 700;
            min-width: 20px;
        }
        
        .number-icon {
            color: rgba(99, 102, 241, 1);
            font-size: 13px;
            font-weight: 700;
            min-width: 26px;
        }
        
        .list-item-text {
            color: rgba(229, 231, 235, 0.95);
            font-size: 13px;
            line-height: 1.6;
        }
        
        /* Code Blocks */
        .code-block {
            background-image: linear-gradient(to bottom right, rgba(20, 20, 30, 0.8), rgba(30, 30, 40, 0.8));
            border-radius: 12px;
            border: 1px solid rgba(99, 102, 241, 0.3);
            margin-top: 8px;
            margin-bottom: 8px;
        }
        
        .code-header {
            background-image: linear-gradient(to right, rgba(99, 102, 241, 0.2), rgba(139, 92, 246, 0.2));
            padding: 8px 12px;
            border-bottom: 1px solid rgba(99, 102, 241, 0.2);
        }
        
        .code-lang {
            color: rgba(139, 92, 246, 1);
            font-size: 11px;
            font-weight: 700;
            font-family: 'JetBrains Mono', 'Fira Code', monospace;
            letter-spacing: 0.5px;
        }
        
        .code-content {
            color: rgba(249, 250, 251, 1);
            font-size: 12px;
            font-family: 'JetBrains Mono', 'Fira Code', 'Courier New', monospace;
            line-height: 1.6;
            padding: 12px;
            background: rgba(10, 10, 15, 0.6);
        }
        
        /* Inline Code */
        .inline-code {
            background: rgba(99, 102, 241, 0.15);
            color: rgba(167, 139, 250, 1);
            padding: 2px 6px;
            border-radius: 4px;
            font-family: 'JetBrains Mono', 'Fira Code', monospace;
            font-size: 12px;
            border: 1px solid rgba(99, 102, 241, 0.3);
        }
        
        /* Links */
        .link-button {
            background-image: linear-gradient(to bottom right, rgba(59, 130, 246, 0.15), rgba(37, 99, 235, 0.15));
            border: 1px solid rgba(59, 130, 246, 0.3);
            border-radius: 8px;
            color: rgba(96, 165, 250, 1);
            font-size: 13px;
            padding: 8px 12px;
            margin-top: 4px;
            margin-bottom: 4px;
        }
        
        .link-button:hover {
            background-image: linear-gradient(to bottom right, rgba(59, 130, 246, 0.25), rgba(37, 99, 235, 0.25));
            border-color: rgba(59, 130, 246, 0.5);
        }
        
        /* ===== GOD LEVEL WEB SEARCH CARD ===== */
        
        .web-search-card {
            background-image: linear-gradient(to bottom right, rgba(30, 30, 40, 0.9), rgba(40, 40, 50, 0.9));
            border-radius: 18px;
            border: 1px solid rgba(99, 102, 241, 0.3);
            margin: 8px;
            padding: 0;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
        }
        
        .search-card-header {
            background-image: linear-gradient(to bottom right, rgba(99, 102, 241, 0.2), rgba(139, 92, 246, 0.2));
            padding: 16px;
            border-bottom: 1px solid rgba(99, 102, 241, 0.2);
        }
        
        .search-big-icon {
            font-size: 32px;
        }
        
        .search-card-title {
            color: rgba(167, 139, 250, 1);
            font-size: 16px;
            font-weight: 800;
            letter-spacing: -0.3px;
        }
        
        .search-card-query {
            color: rgba(199, 210, 254, 1);
            font-size: 13px;
            font-weight: 500;
        }
        
        .search-summary-section {
            padding: 16px;
            background-image: linear-gradient(to bottom right, rgba(139, 92, 246, 0.08), rgba(167, 139, 250, 0.08));
            border-bottom: 1px solid rgba(99, 102, 241, 0.1);
        }
        
        .section-header {
            color: rgba(139, 92, 246, 1);
            font-size: 14px;
            font-weight: 700;
            margin-bottom: 8px;
        }
        
        .summary-content {
            color: rgba(229, 231, 235, 0.95);
            font-size: 13px;
            line-height: 1.6;
        }
        
        .search-sources-section {
            padding: 16px;
        }
        
        .source-item-card {
            background-image: linear-gradient(to bottom right, rgba(99, 102, 241, 0.06), rgba(139, 92, 246, 0.06));
            border-radius: 10px;
            padding: 12px;
            margin-bottom: 8px;
            border: 1px solid rgba(99, 102, 241, 0.15);
            transition: all 0.2s;
        }
        
        .source-item-card:hover {
            background-image: linear-gradient(to bottom right, rgba(99, 102, 241, 0.12), rgba(139, 92, 246, 0.12));
            border-color: rgba(99, 102, 241, 0.3);
        }
        
        .source-title-button {
            background: none;
            border: none;
            color: rgba(129, 140, 248, 1);
            font-size: 13px;
            font-weight: 600;
        }
        
        .source-title-button:hover {
            color: rgba(167, 139, 250, 1);
        }
        
        .source-snippet-text {
            color: rgba(209, 213, 219, 1);
            font-size: 12px;
            line-height: 1.5;
        }
        
        /* Modern Input Box for Floating Widget */
        .input-box {
            background-image: linear-gradient(to bottom right, rgba(30, 30, 40, 0.9), rgba(40, 40, 50, 0.85));
            border-radius: 28px;
            padding: 8px 12px;
            border: 2px solid rgba(99, 102, 241, 0.2);
            transition: all 0.3s ease;
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
        }
        
        .input-box:focus-within {
            border-color: rgba(99, 102, 241, 0.4);
            box-shadow: 0 6px 24px rgba(99, 102, 241, 0.3);
        }
        
        .modern-input {
            background: transparent;
            border: none;
            font-size: 15px;
            padding: 10px 16px;
            color: white;
            min-height: 44px;
        }
        
        .modern-input:focus {
            outline: none;
        }
        
        .send-button {
            min-width: 44px;
            min-height: 44px;
            border-radius: 22px;
            background-image: linear-gradient(to bottom right, #6366f1, #8b5cf6);
            color: white;
            border: none;
            transition: all 0.2s ease;
            box-shadow: 0 2px 8px rgba(99, 102, 241, 0.3);
        }
        
        .send-button:hover {
            background-image: linear-gradient(to bottom right, rgba(99, 102, 241, 0.9), rgba(139, 92, 246, 0.9));
            box-shadow: 0 4px 12px rgba(99, 102, 241, 0.4);
        }
        
        .send-button:active {
        }
        
        /* ===== HISTORY PANEL STYLES ===== */
        .history-panel {
            background: rgba(20, 20, 30, 0.95);
            border-right: 1px solid rgba(99, 102, 241, 0.2);
        }
        
        .history-header {
            border-bottom: 1px solid rgba(99, 102, 241, 0.2);
        }
        
        .history-title {
            color: rgba(167, 139, 250, 1);
            font-size: 18px;
            font-weight: 700;
        }
        
        .stats-card {
            background-image: linear-gradient(to bottom right, rgba(99, 102, 241, 0.12), rgba(139, 92, 246, 0.12));
            border-radius: 12px;
            padding: 12px;
            border: 1px solid rgba(99, 102, 241, 0.2);
        }
        
        .stat-item {
            color: rgba(199, 210, 254, 1);
            font-size: 16px;
            font-weight: 700;
        }
        
        .history-search {
            background: rgba(255, 255, 255, 0.06);
            border: 1px solid rgba(99, 102, 241, 0.2);
            border-radius: 10px;
            color: white;
            padding: 10px 14px;
        }
        
        .conversation-card {
            background-image: linear-gradient(to bottom right, rgba(99, 102, 241, 0.08), rgba(139, 92, 246, 0.08));
            border-radius: 12px;
            border: 1px solid rgba(99, 102, 241, 0.15);
            transition: all 0.2s;
            min-width: 0;
        }
        
        .conversation-card:hover {
            background-image: linear-gradient(to bottom right, rgba(99, 102, 241, 0.15), rgba(139, 92, 246, 0.15));
            border-color: rgba(99, 102, 241, 0.3);
        }
        
        .active-conversation {
            background-image: linear-gradient(to bottom right, rgba(99, 102, 241, 0.25), rgba(139, 92, 246, 0.25)) !important;
            border-color: rgba(99, 102, 241, 0.5) !important;
            box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.3);
        }
        
        .active-conversation:hover {
            background-image: linear-gradient(to bottom right, rgba(99, 102, 241, 0.3), rgba(139, 92, 246, 0.3)) !important;
        }
        
        .conv-title {
            color: rgba(229, 231, 235, 1);
            font-size: 14px;
            font-weight: 600;
        }
        
        .conv-count {
            color: rgba(139, 92, 246, 1);
            font-size: 12px;
            font-weight: 600;
        }
        
        .conv-time {
            color: rgba(156, 163, 175, 1);
            font-size: 11px;
        }
        
        .delete-conv-btn {
            min-width: 32px;
            min-height: 32px;
            border-radius: 8px;
            background-color: rgba(239, 68, 68, 0.15);
            border: 1px solid rgba(239, 68, 68, 0.3);
            color: rgba(239, 68, 68, 1);
            opacity: 0.7;
        }
        
        .delete-conv-btn:hover {
            background-color: rgba(239, 68, 68, 0.25);
            border-color: rgba(239, 68, 68, 0.5);
            opacity: 1;
        }
        
        .new-conversation-btn {
            background-image: linear-gradient(to bottom right, #6366f1, #8b5cf6);
            border-radius: 12px;
            color: white;
            font-weight: 600;
            padding: 12px;
        }
        
        .new-conversation-btn:hover {
            background-image: linear-gradient(to bottom right, #7c3aed, #a855f7);
        }
        
        .clear-all-btn {
            background-image: linear-gradient(to bottom right, rgba(239, 68, 68, 0.15), rgba(239, 68, 68, 0.1));
            border-radius: 12px;
            color: rgba(239, 68, 68, 1);
            font-weight: 600;
            padding: 12px;
            border: 1px solid rgba(239, 68, 68, 0.3);
        }
        
        .clear-all-btn:hover {
            background-image: linear-gradient(to bottom right, rgba(239, 68, 68, 0.25), rgba(239, 68, 68, 0.15));
            border-color: rgba(239, 68, 68, 0.5);
        }
        
        .delete-conv-btn {
            min-width: 32px;
            min-height: 32px;
            border-radius: 8px;
            background-color: rgba(239, 68, 68, 0.15);
            border: 1px solid rgba(239, 68, 68, 0.3);
            color: rgba(239, 68, 68, 1);
            opacity: 0.8;
            transition: all 0.2s ease;
        }
        
        .delete-conv-btn:hover {
            background-color: rgba(239, 68, 68, 0.25);
            border-color: rgba(239, 68, 68, 0.5);
            opacity: 1;
        }
        
        .empty-state {
            color: rgba(156, 163, 175, 1);
            font-size: 14px;
            padding: 40px 20px;
        }
        
        /* Model Selector Styles */
        .model-selector {
            min-width: 160px;
            font-size: 12px;
        }
        
        .model-selector dropdown {
            padding: 4px 8px;
        }

        /* ===== LEGENDARY UI POLISH OVERRIDES ===== */
        .chat-panel {
            background-image: linear-gradient(to bottom right, rgba(7, 17, 32, 0.98), rgba(10, 24, 44, 0.96));
            border: 1px solid rgba(56, 189, 248, 0.20);
            border-radius: 22px;
        }

        .chat-header {
            background-image: linear-gradient(to bottom right, rgba(56, 189, 248, 0.14), rgba(45, 212, 191, 0.08));
            border-bottom: 1px solid rgba(56, 189, 248, 0.22);
        }

        .chat-title {
            color: rgba(236, 254, 255, 1);
            font-size: 21px;
            font-weight: 800;
            letter-spacing: -0.4px;
        }

        .user-message-card {
            background-image: linear-gradient(to bottom right, rgba(14, 116, 144, 0.34), rgba(8, 145, 178, 0.28));
            border: 1px solid rgba(56, 189, 248, 0.40);
            border-radius: 16px;
            padding: 10px 12px;
        }

        .assistant-message-card {
            background-image: linear-gradient(to bottom right, rgba(15, 23, 42, 0.82), rgba(30, 41, 59, 0.76));
            border: 1px solid rgba(148, 163, 184, 0.22);
            border-radius: 16px;
            padding: 10px 12px;
        }

        .message-text,
        .list-item-text {
            color: rgba(226, 232, 240, 0.98);
            font-size: 14px;
            line-height: 1.68;
            letter-spacing: 0.1px;
        }

        .bullet-icon,
        .number-icon {
            color: rgba(34, 211, 238, 0.95);
        }

        .code-block {
            border: 1px solid rgba(34, 211, 238, 0.26);
            background-image: linear-gradient(to bottom right, rgba(2, 6, 23, 0.96), rgba(15, 23, 42, 0.90));
        }

        .code-header {
            background-image: linear-gradient(to bottom right, rgba(34, 211, 238, 0.14), rgba(56, 189, 248, 0.08));
            border-bottom: 1px solid rgba(34, 211, 238, 0.20);
        }

        .code-lang {
            color: rgba(103, 232, 249, 1);
        }

        .inline-code {
            background: rgba(15, 118, 110, 0.26);
            border: 1px solid rgba(45, 212, 191, 0.38);
            color: rgba(153, 246, 228, 1);
            border-radius: 7px;
            padding: 1px 6px;
            font-size: 12px;
            font-family: 'JetBrains Mono', 'Fira Code', 'Courier New', monospace;
        }

        .input-box {
            background-image: linear-gradient(to bottom right, rgba(15, 23, 42, 0.90), rgba(30, 41, 59, 0.84));
            border: 2px solid rgba(56, 189, 248, 0.28);
            box-shadow: 0 8px 26px rgba(2, 6, 23, 0.52);
        }

        .send-button {
            background-image: linear-gradient(to bottom right, #0891b2, #0ea5e9);
            box-shadow: 0 6px 18px rgba(14, 165, 233, 0.38);
        }
        """
        css_provider.load_from_data(css.encode())
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def _toggle_history(self):
        """Toggle history panel visibility"""
        self._history_visible = not self._history_visible
        self._history_panel.set_visible(self._history_visible)
        if self._expanded:
            self._apply_responsive_panel_size()
            if self._history_visible:
                self._load_history_data()
    
    def refresh_model_selector(self):
        """Public method to refresh model selector after settings change"""
        if hasattr(self, '_expanded_view'):
            # Find the header in expanded view
            def find_header(widget):
                if isinstance(widget, Gtk.Box) and widget.has_css_class('chat-header'):
                    return widget
                child = widget.get_first_child()
                while child:
                    result = find_header(child)
                    if result:
                        return result
                    child = child.get_next_sibling()
                return None
            
            header = find_header(self._expanded_view)
            if header:
                self._refresh_model_selector(header)
                logger.info("Model selector refreshed in floating widget")
        
        # Adjust window size
        if self._expanded:
            self._apply_responsive_panel_size()
            if self._history_visible:
                self._load_history_data()
    
    def _load_history_data(self):
        """Load conversations and stats from daemon"""
        if not self._daemon_proxy:
            logger.warning("No daemon proxy available")
            return
        
        try:
            # Get conversations via DBus
            result = self._daemon_proxy.call_sync(
                'GetConversations',
                GLib.Variant('(i)', (20,)),
                Gio.DBusCallFlags.NONE,
                5000,
                None
            )
            
            conversations_raw = result.unpack()[0]
            conversations = []
            
            for conv_raw in conversations_raw:
                if isinstance(conv_raw, dict):
                    conv = {}
                    for key, value in conv_raw.items():
                        if hasattr(value, 'unpack'):
                            conv[key] = value.unpack()
                        else:
                            conv[key] = value
                    conversations.append(conv)
                else:
                    try:
                        conv = conv_raw.unpack() if hasattr(conv_raw, 'unpack') else conv_raw
                        conversations.append(conv)
                    except:
                        logger.warning(f"Could not unpack conversation: {conv_raw}")
            
            # Get stats
            stats_result = self._daemon_proxy.call_sync(
                'GetHistoryStats',
                None,
                Gio.DBusCallFlags.NONE,
                5000,
                None
            )
            
            stats_raw = stats_result.unpack()[0]
            stats = {}
            if isinstance(stats_raw, dict):
                for key, value in stats_raw.items():
                    if hasattr(value, 'unpack'):
                        stats[key] = value.unpack()
                    else:
                        stats[key] = value
            else:
                stats = stats_raw
            
            # Update UI
            GLib.idle_add(lambda: self._history_panel.load_conversations(conversations))
            GLib.idle_add(lambda: self._history_panel.update_stats(stats))
            
        except Exception as e:
            logger.error(f"Failed to load history: {e}", exc_info=True)
    
    def _load_conversation(self, conv_id: int):
        """Load a specific conversation"""
        if not self._daemon_proxy:
            logger.warning("No daemon proxy available")
            return
            
        if conv_id == -1:
            # New conversation
            try:
                result = self._daemon_proxy.call_sync(
                    'NewConversation',
                    GLib.Variant('(s)', ("New Chat",)),
                    Gio.DBusCallFlags.NONE,
                    5000,
                    None
                )
                v = result.unpack()
                new_conv_id = v[0] if isinstance(v, tuple) else v
                logger.info(f"Created new conversation {new_conv_id}")
                self._current_conversation_id = new_conv_id
                self._history_panel.set_active_conversation(new_conv_id)
                self._clear_chat()
                self._add_message("Start a new conversation below.", is_user=False)
                GLib.timeout_add(500, self._load_history_data)
            except Exception as e:
                logger.error(f"Failed to create conversation: {e}", exc_info=True)
        else:
            # Load existing conversation
            try:
                # Switch to conversation
                self._daemon_proxy.call_sync(
                    'LoadConversation',
                    GLib.Variant('(i)', (conv_id,)),
                    Gio.DBusCallFlags.NONE,
                    5000,
                    None
                )
                
                self._current_conversation_id = conv_id
                self._history_panel.set_active_conversation(conv_id)
                
                # Get messages
                result = self._daemon_proxy.call_sync(
                    'GetConversationMessages',
                    GLib.Variant('(i)', (conv_id,)),
                    Gio.DBusCallFlags.NONE,
                    5000,
                    None
                )
                
                messages_raw = result.unpack()[0]
                messages = []
                
                logger.info(f"📨 Received {len(messages_raw)} raw messages from DBus")
                
                # COMPREHENSIVE message parsing - handle all formats
                for i, msg_raw in enumerate(messages_raw):
                    try:
                        msg = {}
                        
                        # Handle dict format
                        if isinstance(msg_raw, dict):
                            for key, value in msg_raw.items():
                                if hasattr(value, 'unpack'):
                                    msg[key] = value.unpack()
                                elif isinstance(value, (str, int, float, bool)):
                                    msg[key] = value
                                else:
                                    try:
                                        msg[key] = str(value)
                                    except:
                                        msg[key] = None
                        
                        # Handle variant format
                        elif hasattr(msg_raw, 'unpack'):
                            try:
                                unpacked = msg_raw.unpack()
                                if isinstance(unpacked, dict):
                                    msg = unpacked
                                else:
                                    logger.warning(f"Message {i} unpacked to non-dict: {type(unpacked)}")
                                    continue
                            except Exception as unpack_err:
                                logger.warning(f"Failed to unpack message {i}: {unpack_err}")
                                continue
                        else:
                            logger.warning(f"Message {i} has unexpected type: {type(msg_raw)}")
                            continue
                        
                        # Validate message structure
                        if not isinstance(msg, dict):
                            continue
                        
                        # Ensure required fields
                        if 'role' not in msg:
                            msg['role'] = 'assistant'
                        if 'content' not in msg:
                            msg['content'] = ''
                        
                        # Only add messages with content
                        if msg.get('content') and msg['content'].strip():
                            messages.append(msg)
                        else:
                            logger.debug(f"Skipping empty message {i}")
                            
                    except Exception as unpack_error:
                        logger.error(f"Error processing message {i}: {unpack_error}", exc_info=True)
                
                logger.info(f"✅ Successfully parsed {len(messages)} valid messages")
                
                # Clear and load in UI
                self._clear_chat()
                
                if not messages:
                    self._add_message("This conversation is empty. Start chatting to add messages!", is_user=False)
                    logger.info("Displayed empty conversation state")
                else:
                    logger.info(f"Displaying {len(messages)} messages in floating widget")
                    for idx, msg in enumerate(messages):
                        role = msg.get('role', 'assistant')
                        content = msg.get('content', '')
                        if content and content.strip():
                            self._add_message(content, role == 'user')
                            logger.debug(f"Added message {idx+1}/{len(messages)}")
                
            except Exception as e:
                logger.error(f"Failed to load conversation: {e}", exc_info=True)
    
    def _on_delete_conversation(self, conv_id: int):
        """Handle conversation deletion with confirmation"""
        if not self._daemon_proxy:
            logger.error("No daemon proxy available")
            return
        
        # Show confirmation dialog
        from gi.repository import Adw
        
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading="Delete Conversation?",
            body="This conversation will be permanently deleted. This action cannot be undone.",
            close_response="cancel"
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("delete", "Delete")
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        
        def on_response(dialog, response):
            dialog.destroy()
            
            if response == "delete":
                def delete_async():
                    try:
                        logger.info(f"Deleting conversation {conv_id}")
                        result = self._daemon_proxy.call_sync(
                            'DeleteConversation',
                            GLib.Variant('(i)', (conv_id,)),
                            Gio.DBusCallFlags.NONE,
                            3000,
                            None
                        )
                        
                        deleted = result.unpack()[0]
                        if deleted:
                            logger.info(f"Successfully deleted conversation {conv_id}")
                            # If this was the current conversation, start a new one
                            if self._current_conversation_id == conv_id:
                                self._current_conversation_id = None
                                self._load_conversation(-1)  # Create new
                            
                            # Refresh history
                            GLib.idle_add(self._load_history_data)
                        else:
                            logger.warning(f"Failed to delete conversation {conv_id}")
                    except Exception as e:
                        logger.error(f"Failed to delete conversation: {e}", exc_info=True)
                    return False
                
                GLib.idle_add(delete_async)
        
        dialog.connect('response', on_response)
        dialog.present()
    
    def _on_clear_all_conversations(self):
        """Handle clear all conversations"""
        if not self._daemon_proxy:
            logger.error("No daemon proxy available")
            return
        
        from gi.repository import Adw
        
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading="Clear All Conversations?",
            body="This will permanently delete all your chat history. This action cannot be undone.",
            close_response="cancel"
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("delete", "Delete All")
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        
        def on_response(dialog, response):
            dialog.destroy()
            if response != "delete":
                return
            
            def on_delete_finish(proxy, result, user_data):
                try:
                    variant = proxy.call_finish(result)
                    v = variant.unpack()
                    count = v[0] if isinstance(v, tuple) else v
                    logger.info(f"✅ Deleted {count} conversations")
                    def do_ui():
                        self._current_conversation_id = None
                        self._clear_chat()
                        self._load_conversation(-1)
                        return False
                    GLib.idle_add(do_ui)
                    # _load_conversation(-1) schedules _load_history_data in 500ms
                except Exception as e:
                    logger.error(f"❌ Failed to clear all conversations: {e}", exc_info=True)
                    err = str(e)
                    def show_err():
                        self._add_message(f"❌ Failed to delete conversations: {err}", is_user=False)
                        return False
                    GLib.idle_add(show_err)
            
            logger.info("🗑️ Deleting all conversations...")
            self._daemon_proxy.call(
                'DeleteAllConversations',
                GLib.Variant('()', ()),
                Gio.DBusCallFlags.NONE,
                5000,
                None,
                on_delete_finish,
                None
            )
        
        dialog.connect('response', on_response)
        dialog.present()
    
    _PROVIDER_DISPLAY_NAMES = {"gemini": "Gemini", "openai": "OpenAI", "anthropic": "Anthropic", "custom": "Custom"}

    def _refresh_model_selector(self, header: Gtk.Box):
        """Refresh or create model selector. Shows models from ALL providers with API keys."""
        from ..core.settings import get_settings_manager
        from ..core.secrets import SecretsManager
        
        settings = get_settings_manager().load()
        secrets = SecretsManager()
        active_provider = settings.active_provider
        active_model = settings.providers.get(active_provider, {}).get('model', '')
        
        choices: List[Tuple[str, str]] = []
        display_strings: List[str] = []
        for provider in ('gemini', 'openai', 'anthropic', 'custom'):
            if not secrets.has_api_key(provider):
                continue
            config = settings.providers.get(provider, {})
            models = config.get('models_available', []) or []
            pname = self._PROVIDER_DISPLAY_NAMES.get(provider, provider)
            for model in models:
                if model:
                    choices.append((provider, model))
                    display_strings.append(f"{pname}: {model}")
        
        if active_model and (active_provider, active_model) not in choices:
            pname = self._PROVIDER_DISPLAY_NAMES.get(active_provider, active_provider)
            choices.append((active_provider, active_model))
            display_strings.append(f"{pname}: {active_model}")
        
        if self._model_box:
            child = self._model_box.get_first_child()
            while child:
                next_child = child.get_next_sibling()
                self._model_box.remove(child)
                child = next_child
        
        if not choices:
            self._model_box.set_visible(False)
            return
        
        self._model_choices = choices
        model_label = Gtk.Label(label="Model:")
        model_label.add_css_class('dim-label')
        model_label.set_margin_end(4)
        self._model_box.append(model_label)
        
        self._model_combo = Gtk.DropDown()
        model_list = Gtk.StringList.new(display_strings)
        self._model_combo.set_model(model_list)
        
        selected_idx = 0
        for i, (p, m) in enumerate(choices):
            if p == active_provider and m == active_model:
                selected_idx = i
                break
        self._model_combo.set_selected(selected_idx)
        
        self._model_combo.connect('notify::selected', self._on_model_changed)
        self._model_combo.set_tooltip_text(f"Select model ({len(choices)} available from configured providers)")
        self._model_combo.add_css_class('model-selector')
        self._model_box.append(self._model_combo)
        
        if self._model_box.get_parent() != header:
            header.append(self._model_box)
        
        self._model_box.set_visible(True)
    
    def _on_model_changed(self, combo, param):
        """Handle model selection. Uses (provider, model) from _model_choices."""
        try:
            selected = combo.get_selected()
            if selected == Gtk.INVALID_LIST_POSITION or selected >= len(getattr(self, '_model_choices', [])):
                return
            
            provider, model = self._model_choices[selected]
            
            from ..core.settings import get_settings_manager
            settings = get_settings_manager().load()
            if provider not in settings.providers:
                return
            
            settings.active_provider = provider
            settings.providers[provider]['model'] = model
            get_settings_manager().save()
            logger.info(f"Changed to {provider} / {model}")
            
            if self._daemon_proxy:
                try:
                    result = self._daemon_proxy.call_sync(
                        'ReloadSettings',
                        None,
                        Gio.DBusCallFlags.NONE,
                        5000,
                        None
                    )
                    if result and result.unpack():
                        logger.info("✅ Daemon settings reloaded successfully")
                    else:
                        logger.warning("⚠️ Daemon ReloadSettings returned False")
                except Exception as e:
                    logger.error(f"Failed to notify daemon of model change: {e}")
            
            self._add_message(f"✓ Model changed to: {provider} / {model}", is_user=False)
        except Exception as e:
            logger.error(f"Failed to change model: {e}")
    
    def _search_history(self, query: str):
        """Search messages"""
        if not self._daemon_proxy or not query:
            return
        
        try:
            result = self._daemon_proxy.call_sync(
                'SearchMessages',
                GLib.Variant('(si)', (query, 20)),
                Gio.DBusCallFlags.NONE,
                5000,
                None
            )
            
            results = []
            for res_dict in result.unpack()[0]:
                results.append({
                    'conversation_id': res_dict['conversation_id'].unpack(),
                    'content': res_dict['content'].unpack(),
                    'role': res_dict['role'].unpack(),
                    'conversation_title': res_dict['conversation_title'].unpack()
                })
            
            # TODO: Display search results in UI
            logger.info(f"Found {len(results)} search results")
            
        except Exception as e:
            logger.error(f"Search failed: {e}")
    
    def _clear_chat(self):
        """Clear chat messages"""
        child = self._chat_box.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self._chat_box.remove(child)
            child = next_child
    
    def show_bubble(self):
        """Show the widget in bubble mode"""
        self._expanded = False
        self._bubble_view.set_visible(True)
        self._expanded_container.set_visible(False)
        self.set_default_size(90, 90)  # Bubble + label
        self.present()
        GLib.timeout_add(100, self._apply_wmctrl_hints)
        GLib.timeout_add(400, self._apply_wmctrl_hints)
        self._start_wmctrl_monitor()
