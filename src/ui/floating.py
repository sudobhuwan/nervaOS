"""
NervaOS Floating Assistant - Always-visible chat bubble

A small floating widget that stays on screen, providing quick access
to the AI assistant. Expands into a mini chat when clicked.
"""

import logging
from typing import Optional, Callable

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
gi.require_version('Gdk', '4.0')
from gi.repository import Gtk, Gdk, Adw, GLib, Pango

logger = logging.getLogger('nerva-floating')


class FloatingAssistant(Gtk.Window):
    """
    A floating assistant bubble that stays on screen.
    
    Features:
    - Small circular button when minimized
    - Expands to chat panel when clicked
    - Draggable to any position
    - Always on top
    - Remembers position
    """
    
    def __init__(self, send_query_callback: Callable = None, **kwargs):
        super().__init__(**kwargs)
        
        self._send_query = send_query_callback
        self._expanded = False
        self._margin = 20  # Distance from screen edges (like website chat widgets)
        self._drag_start_x = 0
        self._drag_start_y = 0
        self._window_x = 0
        self._window_y = 0
        self._xid = None  # Cached window XID for faster dragging
        self._is_dragging = False
        self._positioned_once = False
        self._keep_on_top_timeout = None
        
        self._setup_window()
        self._setup_ui()
        self._setup_styles()
    
    def _setup_window(self):
        """Configure window properties"""
        self.set_title("NervaOS Assistant")
        self.set_decorated(False)  # No title bar
        self.set_resizable(False)
        
        # Set initial size (bubble mode)
        self.set_default_size(60, 60)
        
        # Keep on top (always sticky - never goes behind other apps)
        self.set_modal(False)
        self.set_transient_for(None)
        
        # Set window type hint for better always-on-top behavior
        # This helps window managers understand this is a utility/overlay window
        self.set_icon_name('starred-symbolic')
        
        # Connect signals
        self.connect('realize', self._on_realize)
        self.connect('notify::visible', self._on_visibility_changed)
        self.connect('notify::mapped', self._on_mapped)
        
        # Note: GTK4 doesn't have notify::is-active, so we rely on periodic monitoring
        # and visibility changes instead
        
        # Don't auto-reposition on size changes - user can drag it
    
    def _on_realize(self, widget):
        """Called when window is realized (mapped to screen) - position at bottom-right and keep on top"""
        # Set proper window hints for always-on-top
        self._apply_always_on_top_hints()
        
        # Position window
        if not self._positioned_once:
            GLib.idle_add(self._position_at_bottom_right)
            self._positioned_once = True
        
        # Cache XID for X11 operations
        self._cache_xid()
        
        # Start keep-on-top monitoring
        self._start_keep_on_top_monitor()
    
    def _on_visibility_changed(self, widget, param):
        """Called when window visibility changes"""
        if self.get_visible():
            self._apply_always_on_top_hints()
            self._start_keep_on_top_monitor()
        else:
            self._stop_keep_on_top_monitor()
    
    def _on_mapped(self, widget, param):
        """Called when window is mapped (shown on screen)"""
        if self.get_mapped():
            self._apply_always_on_top_hints()
            self.present()
    
    def _on_focus_changed(self, widget, param):
        """Called when window focus changes"""
        # When window loses focus, ensure it stays on top
        # Note: GTK4 doesn't have get_is_active(), so we just ensure it stays visible
        if self.get_visible() and self.get_mapped():
            # Small delay to avoid focus loop
            GLib.timeout_add(100, lambda: self._apply_always_on_top_hints() if self.get_visible() else False)
    
    def _apply_always_on_top_hints(self):
        """Apply window manager hints to keep window always on top"""
        try:
            surface = self.get_surface()
            if not surface:
                return
            
            toplevel = surface.get_toplevel()
            if not isinstance(toplevel, Gdk.Toplevel):
                return
            
            # Request window to be kept above other windows
            # This uses the NET_WM_STATE_ABOVE hint
            toplevel.set_title("NervaOS Assistant")
            
            # On X11, we can use more aggressive methods
            if self._xid:
                self._apply_x11_always_on_top()
            
            # Use present() to bring to front
            self.present()
            
        except Exception as e:
            logger.debug(f"Could not apply always-on-top hints: {e}")
    
    def _apply_x11_always_on_top(self):
        """Apply X11-specific always-on-top hints"""
        if not self._xid:
            return
        
        try:
            import subprocess
            # Use wmctrl or xdotool to set window above others
            # Try wmctrl first (more standard)
            try:
                subprocess.run(
                    ['wmctrl', '-i', '-r', str(self._xid), '-b', 'add,above'],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=0.5
                )
            except (FileNotFoundError, subprocess.TimeoutExpired):
                # Fallback to xdotool
                try:
                    subprocess.run(
                        ['xdotool', 'windowraise', str(self._xid)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=0.5
                    )
                    # Also set window type to utility/dock for better behavior
                    subprocess.run(
                        ['xdotool', 'set_window', '--class', 'NervaOS', str(self._xid)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=0.5
                    )
                except (FileNotFoundError, subprocess.TimeoutExpired):
                    pass
        except Exception as e:
            logger.debug(f"X11 always-on-top failed: {e}")
    
    def _start_keep_on_top_monitor(self):
        """Start monitoring to keep window on top"""
        if self._keep_on_top_timeout:
            return
        
        def keep_on_top():
            if not self.get_visible() or self._is_dragging:
                return True
            
            try:
                # Periodically bring window to front
                if self.get_mapped():
                    self.present()
                    self._apply_x11_always_on_top()
            except:
                pass
            
            return True  # Keep timeout running
        
        # Check every 200ms to keep on top (less aggressive but more reliable)
        self._keep_on_top_timeout = GLib.timeout_add(200, keep_on_top)
    
    def _stop_keep_on_top_monitor(self):
        """Stop the keep-on-top monitoring"""
        if self._keep_on_top_timeout:
            GLib.source_remove(self._keep_on_top_timeout)
            self._keep_on_top_timeout = None
    
    def _position_at_bottom_right(self):
        """Position window at bottom-right corner (sticky like website chat widgets)"""
        try:
            display = Gdk.Display.get_default()
            if not display:
                return False
            
            # Get primary monitor (or first monitor)
            monitor = display.get_primary_monitor()
            if not monitor:
                monitors = display.get_monitors()
                if monitors and monitors.get_n_items() > 0:
                    monitor = monitors.get_item(0)
            
            if not monitor:
                return False
            
            # Get monitor geometry
            geometry = monitor.get_geometry()
            monitor_width = geometry.width
            monitor_height = geometry.height
            
            # Get window size
            width = self.get_width() if self.get_width() > 0 else self.get_default_width()
            height = self.get_height() if self.get_height() > 0 else self.get_default_height()
            
            # Calculate bottom-right position with margin
            x = monitor_width - width - self._margin
            y = monitor_height - height - self._margin
            
            # Position window using GTK4 methods
            surface = self.get_surface()
            if surface:
                # On X11, use xdotool for precise positioning
                if self._xid:
                    try:
                        import subprocess
                        subprocess.run(
                            ['xdotool', 'windowmove', str(self._xid), str(x), str(y)],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            timeout=0.5
                        )
                        self._window_x = x
                        self._window_y = y
                        return True
                    except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.SubprocessError):
                        pass
                
                # Fallback: Try using wmctrl
                if self._xid:
                    try:
                        import subprocess
                        subprocess.run(
                            ['wmctrl', '-i', '-r', str(self._xid), '-e', f'0,{x},{y},-1,-1'],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            timeout=0.5
                        )
                        self._window_x = x
                        self._window_y = y
                        return True
                    except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.SubprocessError):
                        pass
                
                # Wayland fallback: Use geometry constraints (may not work perfectly)
                # The window manager will position it, but we can try to hint
                try:
                    from gi.repository import GdkWayland
                    if isinstance(surface, GdkWayland.WaylandSurface):
                        # Wayland positioning is limited - just ensure size is set
                        self.set_default_size(width, height)
                        # Note: Wayland compositors handle positioning differently
                        return False
                except (ImportError, AttributeError):
                    pass
                
        except Exception as e:
            logger.debug(f"Could not position window: {e}")
        
        return False
    
    def _cache_xid(self):
        """Cache window XID for faster operations"""
        try:
            surface = self.get_surface()
            if surface:
                try:
                    from gi.repository import GdkX11
                    if isinstance(surface, GdkX11.X11Surface):
                        self._xid = GdkX11.X11Surface.get_xid(surface)
                        logger.debug(f"Cached window XID: {self._xid}")
                        return True
                except (ImportError, AttributeError):
                    pass
        except Exception as e:
            logger.debug(f"Could not cache XID: {e}")
        
        return False
    
    
    def _setup_ui(self):
        """Build the UI"""
        # Main container
        self._main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._main_box.add_css_class('floating-assistant')
        
        # === MINIMIZED VIEW (Bubble) ===
        self._bubble_view = Gtk.Box()
        self._bubble_view.add_css_class('assistant-bubble')
        self._bubble_view.set_size_request(56, 56)
        self._bubble_view.set_halign(Gtk.Align.CENTER)
        self._bubble_view.set_valign(Gtk.Align.CENTER)
        
        # Bubble button
        self._bubble_btn = Gtk.Button()
        self._bubble_btn.add_css_class('circular')
        self._bubble_btn.add_css_class('suggested-action')
        self._bubble_btn.set_size_request(56, 56)
        
        # Icon
        bubble_icon = Gtk.Image.new_from_icon_name('starred-symbolic')
        bubble_icon.set_pixel_size(28)
        self._bubble_btn.set_child(bubble_icon)
        self._bubble_btn.connect('clicked', self._toggle_expand)
        
        # Right click menu setup
        click_gesture = Gtk.GestureClick()
        click_gesture.set_button(3)  # Right click
        click_gesture.connect('pressed', self._on_right_click)
        self._bubble_btn.add_controller(click_gesture)
        
        self._bubble_view.append(self._bubble_btn)
        self._main_box.append(self._bubble_view)

        # === EXPANDED VIEW (Chat Panel) ===
        self._expanded_view = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self._expanded_view.add_css_class('expanded-panel')
        self._expanded_view.set_visible(False)
        self._expanded_view.set_size_request(350, 450)
        
        # Header (also draggable)
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header.add_css_class('panel-header')
        header.set_margin_start(12)
        header.set_margin_end(12)
        header.set_margin_top(12)
        self._header = header  # Store reference for drag setup
        
        # Logo
        logo = Gtk.Image.new_from_icon_name('starred-symbolic')
        logo.set_pixel_size(24)
        header.append(logo)
        
        # Title
        title = Gtk.Label(label="NervaOS")
        title.add_css_class('title-3')
        title.set_hexpand(True)
        title.set_xalign(0)
        header.append(title)
        
        # Status
        self._status_label = Gtk.Label(label="Ready")
        self._status_label.add_css_class('dim-label')
        header.append(self._status_label)
        
        # Minimize button
        minimize_btn = Gtk.Button()
        minimize_btn.add_css_class('flat')
        minimize_btn.set_child(Gtk.Image.new_from_icon_name('window-minimize-symbolic'))
        minimize_btn.connect('clicked', self._toggle_expand)
        header.append(minimize_btn)
        
        self._expanded_view.append(header)
        
        # Separator
        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        self._expanded_view.append(sep)
        
        # Chat history (scrollable)
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        
        self._chat_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self._chat_box.set_margin_start(12)
        self._chat_box.set_margin_end(12)
        self._chat_box.set_margin_top(8)
        self._chat_box.set_margin_bottom(8)
        
        scroll.set_child(self._chat_box)
        self._expanded_view.append(scroll)
        
        # Input area
        input_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        input_box.set_margin_start(12)
        input_box.set_margin_end(12)
        input_box.set_margin_bottom(12)
        
        self._entry = Gtk.Entry()
        self._entry.set_placeholder_text("Ask me anything...")
        self._entry.set_hexpand(True)
        self._entry.connect('activate', self._on_send)
        input_box.append(self._entry)
        
        send_btn = Gtk.Button()
        send_btn.add_css_class('suggested-action')
        send_btn.set_child(Gtk.Image.new_from_icon_name('mail-send-symbolic'))
        send_btn.connect('clicked', self._on_send)
        input_box.append(send_btn)
        
        self._expanded_view.append(input_box)
        
        self._main_box.append(self._expanded_view)
        self.set_child(self._main_box)
        
        # Add drag gesture for moving the window
        self._setup_drag()
        
        # Add drag to header after it's created
        if hasattr(self, '_header'):
            header_drag = Gtk.GestureDrag()
            header_drag.connect('drag-begin', self._on_drag_begin)
            header_drag.connect('drag-update', self._on_drag_update)
            header_drag.connect('drag-end', self._on_drag_end)
            self._header.add_controller(header_drag)
    
    def _setup_drag(self):
        """Allow dragging the window anywhere on screen"""
        drag = Gtk.GestureDrag()
        drag.connect('drag-begin', self._on_drag_begin)
        drag.connect('drag-update', self._on_drag_update)
        drag.connect('drag-end', self._on_drag_end)
        self.add_controller(drag)
    
    def _on_drag_begin(self, gesture, x, y):
        """Start dragging - capture initial position"""
        self._is_dragging = True
        
        # Cache XID if not already cached
        if not self._xid:
            self._cache_xid()
        
        # Get current window position
        surface = self.get_surface()
        if surface:
            # Try to get position from GTK4 first
            alloc = self.get_allocation()
            if alloc:
                # Get root coordinates
                display = Gdk.Display.get_default()
                if display:
                    monitor = display.get_monitor_at_surface(surface)
                    if monitor:
                        geom = monitor.get_geometry()
                        # Try to get window position
                        pass
        
        # Get position using xdotool (X11) or system tools
        if self._xid:
            import subprocess
            try:
                result = subprocess.run(
                    ['xdotool', 'getwindowgeometry', '--shell', str(self._xid)],
                    capture_output=True,
                    text=True,
                    timeout=0.3
                )
                # Parse position from shell format (X=1234 Y=567)
                for line in result.stdout.split('\n'):
                    if line.startswith('X='):
                        self._window_x = int(line.split('=')[1].strip())
                    elif line.startswith('Y='):
                        self._window_y = int(line.split('=')[1].strip())
            except Exception as e:
                logger.debug(f"Could not get window position: {e}")
                # Fallback: assume current position is at origin (will be corrected on first move)
                self._window_x = 0
                self._window_y = 0
        else:
            # Wayland or XID not available - use gesture coordinates
            # Get root coordinates of the drag start point
            self._window_x = 0
            self._window_y = 0
        
        self._drag_start_x = x
        self._drag_start_y = y
    
    def _on_drag_update(self, gesture, offset_x, offset_y):
        """Update window position during drag - works on X11 and Wayland"""
        surface = self.get_surface()
        if not surface:
            return
        
        # Calculate new position
        # On X11, use cached position + offset
        # On Wayland, use GDK methods if available
        
        if self._xid:
            # X11 path: use xdotool for precise control
            new_x = self._window_x + offset_x
            new_y = self._window_y + offset_y
            
            # Constrain to screen bounds
            display = Gdk.Display.get_default()
            if display:
                monitor = display.get_monitor_at_surface(surface)
                if monitor:
                    geom = monitor.get_geometry()
                    width = self.get_width() if self.get_width() > 0 else self.get_default_width()
                    height = self.get_height() if self.get_height() > 0 else self.get_default_height()
                    
                    # Allow dragging across entire screen (no constraints)
                    # But keep it visible
                    new_x = max(0, min(new_x, geom.width - width))
                    new_y = max(0, min(new_y, geom.height - height))
            
            # Use xdotool in non-blocking way for smooth dragging
            import subprocess
            try:
                subprocess.Popen(
                    ['xdotool', 'windowmove', str(self._xid), str(int(new_x)), str(int(new_y))],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                # Update cached position to avoid drift
                self._window_x = int(new_x)
                self._window_y = int(new_y)
            except Exception as e:
                logger.debug(f"Drag update failed: {e}")
        else:
            # Wayland path: try using GDK methods
            # Note: Wayland has limited window positioning support
            # The compositor handles most of this
            try:
                # Calculate relative movement
                toplevel = surface.get_toplevel()
                if isinstance(toplevel, Gdk.Toplevel):
                    # On Wayland, we can't directly set position
                    # But we can try to present the window
                    pass
            except Exception as e:
                logger.debug(f"Wayland drag update: {e}")
    
    def _on_drag_end(self, gesture, offset_x, offset_y):
        """Drag ended - update stored position and ensure on top"""
        self._is_dragging = False
        
        # Final position update
        if self._xid and offset_x != 0 and offset_y != 0:
            new_x = self._window_x
            new_y = self._window_y
            
            import subprocess
            try:
                subprocess.run(
                    ['xdotool', 'windowmove', str(self._xid), str(int(new_x)), str(int(new_y))],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=0.5
                )
            except:
                pass
        
        # Ensure it stays on top after drag
        GLib.idle_add(self.present)
        GLib.idle_add(self._apply_always_on_top_hints)
    
    def _on_right_click(self, gesture, n_press, x, y):
        """Show context menu on right click"""
        popover = Gtk.Popover()
        popover.set_parent(self._bubble_btn)
        
        menu_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        menu_box.set_margin_top(8)
        menu_box.set_margin_bottom(8)
        menu_box.set_margin_start(8)
        menu_box.set_margin_end(8)
        
        # Always on top toggle (Best effort)
        top_btn = Gtk.Button(label="Toggle Always on Top")
        top_btn.add_css_class('flat')
        top_btn.connect('clicked', lambda b: self.present()) # Re-present brings to front
        menu_box.append(top_btn)
        
        # Reset position
        reset_btn = Gtk.Button(label="Reset Position")
        reset_btn.add_css_class('flat')
        reset_btn.connect('clicked', lambda b: self.set_default_size(60, 60)) 
        menu_box.append(reset_btn)
        
        # Close option
        close_btn = Gtk.Button(label="Quit Assistant")
        close_btn.add_css_class('flat')
        close_btn.add_css_class('destructive-action')
        close_btn.connect('clicked', lambda b: self.get_application().quit())
        menu_box.append(close_btn)
        
        popover.set_child(menu_box)
        popover.popup()
    
    def _setup_styles(self):
        """Apply custom CSS styles"""
        css_provider = Gtk.CssProvider()
        css = """
        .floating-assistant {
            background: transparent;
        }
        
        .assistant-bubble {
            background: linear-gradient(135deg, #2193b0 0%, #6dd5ed 100%);
            border-radius: 50%;
            box-shadow: 0 4px 15px rgba(33, 147, 176, 0.4);
            transition: all 0.2s ease;
        }
        
        .assistant-bubble:hover {
            transform: scale(1.05);
            box-shadow: 0 6px 20px rgba(33, 147, 176, 0.6);
        }
        
        .assistant-bubble button {
            background: transparent;
            border: none;
            color: white;
            border-radius: 50%;
        }
        
        .expanded-panel {
            background: #2b2b2b;
            color: #ffffff;
            border-radius: 16px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.5);
            border: 1px solid rgba(255,255,255,0.1);
        }
        
        .panel-header {
            padding: 12px;
            border-bottom: 1px solid rgba(255,255,255,0.05);
            background: rgba(0,0,0,0.1);
            border-top-left-radius: 16px;
            border-top-right-radius: 16px;
        }
        
        .chat-bubble {
            padding: 10px 14px;
            border-radius: 12px;
            font-size: 14px;
        }
        
        .user-bubble {
            background: #007bff;
            color: white;
            margin-left: 30px;
            border-bottom-right-radius: 4px;
        }
        
        .assistant-bubble-chat {
            background: #3e3e3e;
            color: #eeeeee;
            border: 1px solid rgba(255,255,255,0.1);
            margin-right: 30px;
            border-bottom-left-radius: 4px;
        }
        
        .thinking-indicator {
            color: #aaaaaa;
            font-style: italic;
            font-size: 12px;
        }
        """
        
        css_provider.load_from_data(css.encode())
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def do_close_request(self) -> bool:
        """Handle window close request - minimize to bubble instead of closing"""
        if self._expanded:
            self._toggle_expand()
            return True  # Prevent closing
        
        # If already bubble, prevent closing too (it's persistent)
        # User must quit from tray or main app to exit completely
        return True
    
    def do_destroy(self):
        """Clean up when window is destroyed"""
        self._stop_keep_on_top_monitor()
        super().do_destroy()
    
    def _toggle_expand(self, button=None):
        """Toggle between bubble and expanded view"""
        self._expanded = not self._expanded
        
        if self._expanded:
            self._bubble_view.set_visible(False)
            self._expanded_view.set_visible(True)
            self.set_default_size(350, 450)
            GLib.timeout_add(100, lambda: self._entry.grab_focus() if self._entry else False)
        else:
            self._bubble_view.set_visible(True)
            self._expanded_view.set_visible(False)
            self.set_default_size(60, 60)
        
        # Keep on top after toggle
        self.present()
        self._apply_always_on_top_hints()
    
    def _add_message(self, text: str, is_user: bool):
        """Add a message bubble to the chat"""
        bubble = Gtk.Label(label=text)
        bubble.set_wrap(True)
        bubble.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        bubble.set_xalign(0)
        bubble.set_selectable(True)
        bubble.add_css_class('chat-bubble')
        
        if is_user:
            bubble.add_css_class('user-bubble')
            bubble.set_halign(Gtk.Align.END)
        else:
            bubble.add_css_class('assistant-bubble-chat')
            bubble.set_halign(Gtk.Align.START)
        
        self._chat_box.append(bubble)
        
        # Scroll to bottom
        GLib.idle_add(self._scroll_to_bottom)
    
    def _scroll_to_bottom(self):
        """Scroll chat to bottom"""
        adj = self._chat_box.get_parent().get_vadjustment()
        adj.set_value(adj.get_upper())
        return False
    
    def _on_send(self, widget):
        """Send message"""
        text = self._entry.get_text().strip()
        if not text:
            return
        
        # Add user message
        self._add_message(text, is_user=True)
        self._entry.set_text("")
        
        # Show thinking indicator
        self._status_label.set_text("Thinking...")
        thinking = Gtk.Label(label="...")
        thinking.add_css_class('thinking-indicator')
        thinking.set_halign(Gtk.Align.START)
        self._chat_box.append(thinking)
        self._thinking_label = thinking
        
        # Send query
        if self._send_query:
            self._send_query(text, self._on_response)
    
    def _on_response(self, response: Optional[str], error: Optional[str]):
        """Handle response from daemon"""
        # Remove thinking indicator
        if hasattr(self, '_thinking_label') and self._thinking_label:
            self._chat_box.remove(self._thinking_label)
            self._thinking_label = None
        
        self._status_label.set_text("Ready")
        
        if error:
            self._add_message(f"Error: {error}", is_user=False)
        else:
            self._add_message(response or "No response", is_user=False)
    
    def show_bubble(self):
        """Show the floating bubble (draggable, always on top)"""
        self._expanded = False
        self._bubble_view.set_visible(True)
        self._expanded_view.set_visible(False)
        self.set_default_size(60, 60)
        
        # Show and apply always-on-top
        self.present()
        
        # Position window if not already positioned
        if not self._positioned_once:
            if self.get_realized():
                GLib.idle_add(self._position_at_bottom_right)
            else:
                # Will be positioned in _on_realize
                pass
            self._positioned_once = True
        
        # Apply always-on-top hints after a short delay to ensure window is mapped
        GLib.timeout_add(100, self._apply_always_on_top_hints)
        
        # Ensure it stays on top
        self._start_keep_on_top_monitor()
    
    def show_expanded(self):
        """Show the expanded chat panel (draggable, always on top)"""
        self._expanded = True
        self._bubble_view.set_visible(False)
        self._expanded_view.set_visible(True)
        self.set_default_size(350, 450)
        
        # Show and apply always-on-top
        self.present()
        self._apply_always_on_top_hints()
        self._start_keep_on_top_monitor()
        
        # Focus entry after a small delay to ensure window is ready
        GLib.timeout_add(100, lambda: self._entry.grab_focus() if self._entry else False)