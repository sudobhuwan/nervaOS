"""
NervaOS Chat Bubble Widget - Message display component

A styled container for chat messages with:
- User vs assistant styling
- Loading state with spinner
- Error state styling
- Copy functionality
- Beautiful markdown rendering
"""

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib, Pango

from ..message_renderers import MessageRenderer


class ChatBubble(Gtk.Box):
    """
    A chat message bubble widget.
    
    Args:
        message: The message text
        is_user: True if from user, False if from AI
        is_loading: Show loading spinner
        is_error: Display as error message
    """
    
    def __init__(
        self, 
        message: str, 
        is_user: bool = False, 
        is_loading: bool = False,
        is_error: bool = False
    ):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        
        self._message = message
        self._is_user = is_user
        
        self._setup_style(is_user, is_error)
        self._setup_content(message, is_loading)
    
    def _setup_style(self, is_user: bool, is_error: bool):
        """Apply styling based on message type"""
        self.add_css_class('response-bubble')
        self.set_margin_start(12)
        self.set_margin_end(12)

        if is_user:
            self.add_css_class('user')
            self.set_halign(Gtk.Align.END)
            self.set_margin_start(44)
        else:
            self.add_css_class('assistant')
            self.set_halign(Gtk.Align.START)
            self.set_margin_end(44)
        
        if is_error:
            self.add_css_class('error')
        
        self.set_margin_top(8)
        self.set_margin_bottom(8)
    
    def _setup_content(self, message: str, is_loading: bool):
        """Build the bubble content with beautiful markdown rendering"""
        if is_loading:
            # Loading state with spinner
            loading_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            
            spinner = Gtk.Spinner()
            spinner.start()
            loading_box.append(spinner)
            
            label = Gtk.Label(label=message)
            label.add_css_class('dim-label')
            loading_box.append(label)
            
            self.append(loading_box)
        else:
            # Use MessageRenderer for beautiful markdown rendering (assistant only)
            if not self._is_user and message:
                # Render with markdown support
                try:
                    rendered_content = MessageRenderer.create_regular_message(message, is_user=False)
                    # Remove the classes from rendered content (we'll use our bubble classes)
                    rendered_content.remove_css_class('assistant-message-card')
                    self.append(rendered_content)
                except Exception as e:
                    # Fallback to plain text if rendering fails
                    import logging
                    logger = logging.getLogger('nerva-ui')
                    logger.warning(f"Failed to render markdown: {e}, using plain text")
                    content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
                    label = Gtk.Label(label=message)
                    label.set_wrap(True)
                    label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
                    label.set_xalign(0)
                    label.set_selectable(True)
                    label.set_max_width_chars(58)
                    label.set_use_markup(False)
                    content_box.append(label)
                    self.append(content_box)
            else:
                # User messages - simple text (no markdown needed)
                content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
                label = Gtk.Label(label=message)
                label.set_wrap(True)
                label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
                label.set_xalign(0)
                label.set_selectable(True)
                label.set_max_width_chars(58)
                label.set_use_markup(False)
                content_box.append(label)
                self.append(content_box)
            
            # Action buttons (only for assistant messages)
            if not self._is_user:
                actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                actions.set_halign(Gtk.Align.END)
                actions.add_css_class('dim-label')
                actions.set_margin_top(8)
                
                copy_btn = Gtk.Button()
                copy_btn.set_icon_name('edit-copy-symbolic')
                copy_btn.add_css_class('flat')
                copy_btn.set_tooltip_text("Copy to clipboard")
                copy_btn.connect('clicked', self._on_copy)
                actions.append(copy_btn)
                
                self.append(actions)
    
    def _on_copy(self, button):
        """Copy message to clipboard"""
        clipboard = self.get_clipboard()
        clipboard.set(self._message)
        
        # Visual feedback
        button.set_icon_name('emblem-ok-symbolic')
        GLib.timeout_add(1500, lambda: button.set_icon_name('edit-copy-symbolic'))


class CodeBlock(Gtk.Box):
    """
    A code block widget with syntax highlighting and copy button.
    """
    
    def __init__(self, code: str, language: str = ""):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        
        self._code = code
        
        self.add_css_class('code-block')
        
        # Header with language and copy button
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header.add_css_class('code-header')
        header.set_margin_start(12)
        header.set_margin_end(12)
        header.set_margin_top(8)
        
        if language:
            lang_label = Gtk.Label(label=language)
            lang_label.add_css_class('dim-label')
            lang_label.set_hexpand(True)
            lang_label.set_xalign(0)
            header.append(lang_label)
        else:
            spacer = Gtk.Box()
            spacer.set_hexpand(True)
            header.append(spacer)
        
        copy_btn = Gtk.Button()
        copy_btn.set_icon_name('edit-copy-symbolic')
        copy_btn.add_css_class('flat')
        copy_btn.set_tooltip_text("Copy code")
        copy_btn.connect('clicked', self._on_copy)
        header.append(copy_btn)
        
        self.append(header)
        
        # Code content
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        scroll.set_max_content_width(600)
        
        code_label = Gtk.Label(label=code)
        code_label.set_xalign(0)
        code_label.set_selectable(True)
        code_label.add_css_class('monospace')
        code_label.set_margin_start(12)
        code_label.set_margin_end(12)
        code_label.set_margin_bottom(12)
        
        scroll.set_child(code_label)
        self.append(scroll)
    
    def _on_copy(self, button):
        """Copy code to clipboard"""
        clipboard = self.get_clipboard()
        clipboard.set(self._code)
        
        button.set_icon_name('emblem-ok-symbolic')
        GLib.timeout_add(1500, lambda: button.set_icon_name('edit-copy-symbolic'))
