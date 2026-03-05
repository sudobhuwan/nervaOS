"""
NervaOS Main Window - Dashboard and settings interface

The main application window with:
- Chat history view
- Settings panel
- Operation history
- System status
"""

import logging
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gio, GLib, Pango

from .components.chat_bubble import ChatBubble
from .components.diff_view import DiffView
from .components.history_panel import HistoryPanel

logger = logging.getLogger('nerva-window')


class MainWindow(Adw.ApplicationWindow):
    """
    Main NervaOS window with sidebar navigation.
    """
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        self._setup_window()
        self._setup_ui()
        
        self._chat_history: List[Dict[str, str]] = []
        
        # Refresh history when connected
        GLib.timeout_add(1000, self._initial_load)
    
    def _initial_load(self):
        """Try to load history initially"""
        app = self.get_application()
        if app and app._daemon_proxy:
            self._refresh_history()
            return False
        return True
    
    def _setup_window(self):
        """Configure window properties"""
        self.set_title("NervaOS")
        self.set_default_size(1000, 700)
        self.set_size_request(800, 500)
    
    def _setup_ui(self):
        """Build the UI"""
        # Main layout with navigation
        self._navigation = Adw.NavigationSplitView()
        
        # Sidebar
        sidebar = self._create_sidebar()
        self._navigation.set_sidebar(sidebar)
        
        # Content area
        self._content_stack = Gtk.Stack()
        self._content_stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        
        # Add pages
        self._chat_page = self._create_chat_page()
        self._content_stack.add_titled(self._chat_page, 'chat', 'Chat')
        self._content_stack.add_titled(self._create_settings_page(), 'settings', 'Settings')
        self._content_stack.add_titled(self._create_history_page(), 'history', 'History')
        
        content_page = Adw.NavigationPage.new(self._content_stack, "NervaOS")
        self._navigation.set_content(content_page)
        
        self.set_content(self._navigation)
    
    def _create_sidebar(self) -> Adw.NavigationPage:
        """Create the sidebar navigation"""
        sidebar_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        
        # Header
        header = Adw.HeaderBar()
        header.set_show_end_title_buttons(False)
        sidebar_box.append(header)
        
        # Navigation items
        nav_list = Gtk.ListBox()
        nav_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        nav_list.add_css_class('navigation-sidebar')
        nav_list.connect('row-selected', self._on_nav_selected)
        
        # Chat
        chat_row = self._create_nav_row('Chat', 'user-available-symbolic', 'chat')
        nav_list.append(chat_row)
        
        # History
        history_row = self._create_nav_row('Chat History', 'document-open-recent-symbolic', 'history')
        nav_list.append(history_row)
        
        # Settings
        settings_row = self._create_nav_row('Settings', 'emblem-system-symbolic', 'settings')
        nav_list.append(settings_row)
        
        sidebar_box.append(nav_list)
        
        # Status at bottom
        status_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        status_box.set_margin_top(12)
        status_box.set_margin_bottom(12)
        status_box.set_margin_start(12)
        status_box.set_margin_end(12)
        status_box.set_vexpand(True)
        status_box.set_valign(Gtk.Align.END)
        
        # Daemon status
        self._daemon_status = Gtk.Label(label="● Connected")
        self._daemon_status.set_xalign(0)
        self._daemon_status.add_css_class('dim-label')
        status_box.append(self._daemon_status)
        
        sidebar_box.append(status_box)
        
        return Adw.NavigationPage.new(sidebar_box, "NervaOS")
    
    def _create_nav_row(self, label: str, icon_name: str, page_name: str) -> Gtk.ListBoxRow:
        """Create a navigation row"""
        row = Gtk.ListBoxRow()
        row.set_name(page_name)
        
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        box.set_margin_start(12)
        box.set_margin_end(12)
        
        icon = Gtk.Image.new_from_icon_name(icon_name)
        box.append(icon)
        
        label_widget = Gtk.Label(label=label)
        label_widget.set_xalign(0)
        box.append(label_widget)
        
        row.set_child(box)
        return row
    
    def _on_nav_selected(self, listbox, row):
        """Handle navigation selection"""
        if row:
            page_name = row.get_name()
            self._content_stack.set_visible_child_name(page_name)
            
            # Refresh history when opening history tab
            if page_name == 'history':
                self._refresh_history()
    
    # ─────────────────────────────────────────────────────────────
    # Chat Page
    # ─────────────────────────────────────────────────────────────
    
    def _create_chat_page(self) -> Gtk.Widget:
        """Create the modern chat interface"""
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        page.add_css_class('chat-page')
        
        # Modern header with gradient
        header = Adw.HeaderBar()
        header.add_css_class('modern-header')
        
        # Title with icon
        title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        title_box.set_margin_start(12)
        
        icon = Gtk.Image.new_from_icon_name('chat-bubbles-symbolic')
        icon.set_pixel_size(24)
        title_box.append(icon)
        
        self._chat_header_label = Gtk.Label(label="Chat with NervaOS")
        self._chat_header_label.add_css_class('header-title')
        title_box.append(self._chat_header_label)
        
        header.set_title_widget(title_box)
        
        # Model selector container (always create, will be populated)
        self._model_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._model_box.set_margin_end(12)
        self._model_combo = None
        self._model_choices: List[Tuple[str, str]] = []  # (provider, model) for each dropdown item
        
        # Create and populate model selector
        self._refresh_model_selector(header)
        
        page.append(header)
        
        # Chat messages (scrollable) with modern styling
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_kinetic_scrolling(True)
        scroll.set_overlay_scrolling(True)
        scroll.add_css_class('chat-scroll')

        self._chat_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self._chat_box.set_margin_top(16)
        self._chat_box.set_margin_bottom(16)
        self._chat_box.set_margin_start(14)
        self._chat_box.set_margin_end(14)
        self._chat_box.add_css_class('chat-messages-container')

        # Welcome message with modern styling
        welcome = ChatBubble(
            "Hello! I'm NervaOS, your AI assistant. How can I help you today?",
            is_user=False
        )
        self._chat_box.append(welcome)

        chat_clamp = Adw.Clamp()
        chat_clamp.set_maximum_size(980)
        chat_clamp.set_tightening_threshold(620)
        chat_clamp.set_child(self._chat_box)

        scroll.set_child(chat_clamp)
        page.append(scroll)
        
        # Modern input area with rounded design
        input_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        input_container.add_css_class('input-container')
        input_container.set_margin_start(14)
        input_container.set_margin_end(14)
        input_container.set_margin_bottom(14)
        input_container.set_margin_top(10)
        
        # Input box with modern styling
        input_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        input_box.add_css_class('input-box')
        
        self._chat_entry = Gtk.Entry()
        self._chat_entry.set_placeholder_text("Message NervaOS...")
        self._chat_entry.add_css_class('modern-input')
        self._chat_entry.set_hexpand(True)
        self._chat_entry.connect('activate', self._on_chat_submit)
        input_box.append(self._chat_entry)
        
        send_btn = Gtk.Button()
        send_btn.set_icon_name('paper-plane-symbolic')
        send_btn.add_css_class('send-button')
        send_btn.set_tooltip_text("Send message")
        send_btn.connect('clicked', self._on_chat_submit)
        input_box.append(send_btn)
        
        input_container.append(input_box)

        input_clamp = Adw.Clamp()
        input_clamp.set_maximum_size(980)
        input_clamp.set_tightening_threshold(620)
        input_clamp.set_child(input_container)
        page.append(input_clamp)
        
        return page
    
    def _on_chat_submit(self, widget):
        """Handle chat message submission"""
        text = self._chat_entry.get_text().strip()
        if not text:
            return
        
        # Add user message
        user_bubble = ChatBubble(text, is_user=True)
        self._chat_box.append(user_bubble)
        
        # Clear entry
        self._chat_entry.set_text("")
        
        # Add loading indicator
        loading = ChatBubble("Thinking...", is_user=False, is_loading=True)
        self._chat_box.append(loading)
        GLib.idle_add(self._scroll_to_bottom)
        
        # Send to daemon
        app = self.get_application()
        if app:
            app.send_query(text, lambda r, e: self._on_chat_response(r, e, loading))
    
    def _on_chat_response(self, response: Optional[str], error: Optional[str], loading_bubble):
        """Handle chat response"""
        # Remove loading bubble
        self._chat_box.remove(loading_bubble)
        
        # Add response
        if error:
            bubble = ChatBubble(f"Error: {error}", is_user=False, is_error=True)
        else:
            bubble = ChatBubble(response or "No response", is_user=False)
        
        self._chat_box.append(bubble)
        
        # Scroll to bottom
        GLib.idle_add(self._scroll_to_bottom)
        
        # Refresh history to show updated conversation
        GLib.timeout_add(500, self._refresh_history)
    
    def _scroll_to_bottom(self):
        """Scroll chat to bottom"""
        # Walk parents to support chat content wrapped in Adw.Clamp.
        parent = self._chat_box.get_parent()
        while parent and not isinstance(parent, Gtk.ScrolledWindow):
            parent = parent.get_parent()

        if isinstance(parent, Gtk.ScrolledWindow):
            adj = parent.get_vadjustment()
            target = max(adj.get_lower(), adj.get_upper() - adj.get_page_size())
            adj.set_value(target)
    
    def _on_model_changed(self, combo, param):
        """Handle model selection change. Uses (provider, model) from _model_choices."""
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
            
            # Notify daemon to reload settings
            app = self.get_application()
            if app and app._daemon_proxy:
                try:
                    result = app._daemon_proxy.call_sync(
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
            
            self._show_model_notification(f"Model changed to: {provider} / {model}")
        except Exception as e:
            logger.error(f"Failed to change model: {e}")
    
    def _show_model_notification(self, message: str):
        """Show a brief notification about model change"""
        logger.info(message)
        # Could add a toast notification here if needed
    
    # ─────────────────────────────────────────────────────────────
    # Settings Page
    # ─────────────────────────────────────────────────────────────
    
    def _create_settings_page(self) -> Gtk.Widget:
        """Create the settings interface using the dedicated settings page"""
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        
        # Header
        header = Adw.HeaderBar()
        header.set_title_widget(Gtk.Label(label="Settings"))
        page.append(header)
        
        # Use the comprehensive API settings page
        try:
            from .settings_page import APISettingsPage
            settings_content = APISettingsPage(on_save_callback=self._on_settings_saved)
            page.append(settings_content)
        except Exception as e:
            # Fallback if settings page fails to load
            logger.error(f"Failed to load settings page: {e}")
            error_page = Adw.StatusPage()
            error_page.set_icon_name('dialog-error-symbolic')
            error_page.set_title("Settings Unavailable")
            error_page.set_description(str(e))
            page.append(error_page)
        
        return page
    
    
    def set_settings_callback(self, callback):
        """Set callback for when settings are saved"""
        self._settings_saved_callback = callback

    def _on_settings_saved(self):
        """Handle settings save - refresh AI client and model selector"""
        logger.info("Settings saved, refreshing model selector and notifying daemon")
        
        # Notify callback (e.g. for bubble visibility)
        if hasattr(self, '_settings_saved_callback') and self._settings_saved_callback:
            self._settings_saved_callback()
        
        # Refresh model selector in chat header
        def refresh_selector():
            try:
                chat_page = self._content_stack.get_child_by_name('chat')
                if chat_page:
                    # Find header and refresh model selector
                    header = None
                    child = chat_page.get_first_child()
                    while child:
                        if isinstance(child, Adw.HeaderBar):
                            header = child
                            break
                        child = child.get_next_sibling()
                    
                    if header:
                        self._refresh_model_selector(header)
                        logger.info("✅ Model selector refreshed in desktop app")
                
                # Also refresh floating widget if it exists
                app = self.get_application()
                if app and hasattr(app, '_floating') and app._floating:
                    try:
                        app._floating.refresh_model_selector()
                        logger.info("✅ Model selector refreshed in floating widget")
                    except Exception as e:
                        logger.warning(f"Could not refresh floating widget model selector: {e}")
                
                # Notify daemon to reload settings
                app = self.get_application()
                if app and app._daemon_proxy:
                    try:
                        result = app._daemon_proxy.call_sync(
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
                        logger.error(f"Failed to notify daemon to reload settings: {e}")
            except Exception as e:
                logger.error(f"Failed to refresh model selector: {e}")
            return False
        
        GLib.idle_add(refresh_selector)
    
    _PROVIDER_DISPLAY_NAMES = {"gemini": "Gemini", "openai": "OpenAI", "anthropic": "Anthropic", "custom": "Custom"}

    def _refresh_model_selector(self, header: Adw.HeaderBar):
        """Refresh or create model selector dropdown. Shows models from ALL providers with API keys."""
        from ..core.settings import get_settings_manager
        from ..core.secrets import SecretsManager
        
        settings = get_settings_manager().load()
        secrets = SecretsManager()
        active_provider = settings.active_provider
        active_model = settings.providers.get(active_provider, {}).get('model', '')
        
        # Build list of (provider, model) for every provider that has an API key
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
        
        # If current (active_provider, active_model) not in list, add it
        if active_model and (active_provider, active_model) not in choices:
            pname = self._PROVIDER_DISPLAY_NAMES.get(active_provider, active_provider)
            choices.append((active_provider, active_model))
            display_strings.append(f"{pname}: {active_model}")
        
        logger.debug(f"Model selector: {len(choices)} models from providers with API keys")
        
        # Clear existing model box
        if self._model_box:
            child = self._model_box.get_first_child()
            while child:
                next_child = child.get_next_sibling()
                self._model_box.remove(child)
                child = next_child
        
        if not choices:
            self._model_box.set_visible(False)
            logger.debug("Model selector hidden: no providers with API keys")
            return
        
        self._model_choices = choices
        model_label = Gtk.Label(label="Model:")
        model_label.add_css_class('dim-label')
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
            header.pack_end(self._model_box)
        
        self._model_box.set_visible(True)
    
    # ─────────────────────────────────────────────────────────────
    # History Page
    # ─────────────────────────────────────────────────────────────
    
    def _create_history_page(self) -> Gtk.Widget:
        """Create the chat history interface"""
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        
        # Use the GOD I mean GOOD level HistoryPanel
        self._history_panel = HistoryPanel(
            on_conversation_selected=self._on_conversation_selected,
            on_search=self._on_history_search,
            on_delete=self._on_delete_conversation,
            on_clear_all=self._on_clear_all_conversations
        )
        self._current_conversation_id: Optional[int] = None
        # Expand to fill page
        self._history_panel.set_hexpand(True)
        self._history_panel.set_vexpand(True)
        
        page.append(self._history_panel)
        
        return page
    
    def _refresh_history(self):
        """Fetch history from daemon"""
        app = self.get_application()
        if not app or not app._daemon_proxy:
            return
            
        try:
            # Get conversations
            app._daemon_proxy.call(
                'GetConversations',
                GLib.Variant('(i)', (20,)),  # Limit 20
                Gio.DBusCallFlags.NONE,
                5000,
                None,
                self._on_history_received,
                None
            )
            
            # Get stats
            app._daemon_proxy.call(
                'GetHistoryStats',
                None,
                Gio.DBusCallFlags.NONE,
                5000,
                None,
                self._on_stats_received,
                None
            )
        except Exception as e:
            logger.error(f"Failed to refresh history: {e}")
    
    def _on_history_received(self, proxy, result, user_data):
        """Handle history data"""
        try:
            variant = proxy.call_finish(result)
            conversations_raw = variant.unpack()[0]
            
            # Convert DBus variants to plain dicts
            conversations = []
            for conv_raw in conversations_raw:
                if isinstance(conv_raw, dict):
                    # Already a dict, but values might be Variants
                    conv = {}
                    for key, value in conv_raw.items():
                        if hasattr(value, 'unpack'):
                            conv[key] = value.unpack()
                        else:
                            conv[key] = value
                    conversations.append(conv)
                else:
                    # Try to unpack as variant
                    try:
                        conv = conv_raw.unpack() if hasattr(conv_raw, 'unpack') else conv_raw
                        conversations.append(conv)
                    except:
                        logger.warning(f"Could not unpack conversation: {conv_raw}")
            
            logger.info(f"Loaded {len(conversations)} conversations")
            self._history_panel.load_conversations(conversations)
            
        except Exception as e:
            logger.error(f"Failed to parse history: {e}", exc_info=True)
    
    def _on_stats_received(self, proxy, result, user_data):
        """Handle stats data"""
        try:
            variant = proxy.call_finish(result)
            stats_raw = variant.unpack()[0]
            
            # Convert DBus variants to plain dict
            stats = {}
            if isinstance(stats_raw, dict):
                for key, value in stats_raw.items():
                    if hasattr(value, 'unpack'):
                        stats[key] = value.unpack()
                    else:
                        stats[key] = value
            else:
                stats = stats_raw
            
            self._history_panel.update_stats(stats)
        except Exception as e:
            logger.error(f"Failed to parse stats: {e}", exc_info=True)
    
    def _on_conversation_selected(self, conv_id: int):
        """Handle conversation selection from history"""
        if conv_id == -1:
            # New conversation
            self._current_conversation_id = None
            self._load_new_conversation()
        else:
            # Load existing
            self._current_conversation_id = conv_id
            self._load_conversation(conv_id)
        
        # Update active conversation in history panel
        self._history_panel.set_active_conversation(self._current_conversation_id)
            
        # Switch to chat tab
        # Find the nav row for chat and select it, or manually switch stack
        self._content_stack.set_visible_child_name('chat')
    
    def _on_delete_conversation(self, conv_id: int):
        """Handle conversation deletion with confirmation - FIXED"""
        app = self.get_application()
        if not app or not app._daemon_proxy:
            logger.error("No daemon proxy available for delete")
            return
        
        # Show confirmation dialog
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
                        logger.info(f"🗑️ Deleting conversation {conv_id}")
                        result = app._daemon_proxy.call_sync(
                            'DeleteConversation',
                            GLib.Variant('(i)', (conv_id,)),
                            Gio.DBusCallFlags.NONE,
                            3000,
                            None
                        )
                        
                        deleted = result.unpack()[0]
                        if deleted:
                            logger.info(f"✅ Successfully deleted conversation {conv_id}")
                            
                            # If this was the current conversation, start a new one
                            if self._current_conversation_id == conv_id:
                                self._current_conversation_id = None
                                self._load_new_conversation()
                            
                            # Refresh history immediately
                            def refresh():
                                self._refresh_history()
                                return False
                            GLib.idle_add(refresh)
                        else:
                            logger.warning(f"❌ Delete returned False for conversation {conv_id}")
                            # Show error
                            error_bubble = ChatBubble(
                                f"❌ Failed to delete conversation. Please try again.",
                                is_user=False,
                                is_error=True
                            )
                            GLib.idle_add(lambda: self._chat_box.append(error_bubble))
                    except Exception as e:
                        logger.error(f"❌ Failed to delete conversation: {e}", exc_info=True)
                        # Show error
                        error_bubble = ChatBubble(
                            f"❌ Error: {str(e)}",
                            is_user=False,
                            is_error=True
                        )
                        GLib.idle_add(lambda: self._chat_box.append(error_bubble))
                    return False
                
                GLib.idle_add(delete_async)
        
        dialog.connect('response', on_response)
        dialog.present()
    
    def _on_clear_all_conversations(self):
        """Handle clear all conversations"""
        app = self.get_application()
        if not app or not app._daemon_proxy:
            logger.error("No daemon proxy available")
            return
        
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
                        self._load_new_conversation()
                        return False
                    GLib.idle_add(do_ui)
                    # Refresh happens in _on_new_conversation_created (500ms after NewConversation)
                except Exception as e:
                    logger.error(f"❌ Failed to clear all conversations: {e}", exc_info=True)
                    err = str(e)
                    def show_err():
                        b = ChatBubble(
                            f"❌ Failed to delete conversations: {err}",
                            is_user=False,
                            is_error=True
                        )
                        self._chat_box.append(b)
                        return False
                    GLib.idle_add(show_err)
            
            logger.info("🗑️ Deleting all conversations...")
            app._daemon_proxy.call(
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
    
    def _on_history_search(self, query: str):
        """Handle search"""
        app = self.get_application()
        if not app or not app._daemon_proxy:
            return
            
        try:
            # Search messages
            app._daemon_proxy.call(
                'SearchMessages',
                GLib.Variant('(si)', (query, 20)),
                Gio.DBusCallFlags.NONE,
                5000,
                None,
                self._on_history_received, # Reuse handler as format is similar enough for list
                None
            )
        except Exception as e:
            logger.error(f"Search failed: {e}")

    def _load_conversation(self, conv_id: int):
        """Load a specific conversation into chat view"""
        app = self.get_application()
        if not app or not app._daemon_proxy:
            logger.error("No daemon proxy available")
            return
        
        logger.info(f"Loading conversation {conv_id}")
        
        # Show loading indicator
        self._clear_chat_bubbles()
        loading_bubble = ChatBubble("Loading conversation...", is_user=False, is_loading=True)
        self._chat_box.append(loading_bubble)
        
        # 1. Tell daemon to load/switch context
        try:
            # Switch conversation in daemon
            app._daemon_proxy.call(
                'LoadConversation',
                GLib.Variant('(i)', (conv_id,)),
                Gio.DBusCallFlags.NONE,
                5000,
                None,
                lambda p, r, u: self._on_conversation_loaded(p, r, u, conv_id, loading_bubble),
                None
            )
        except Exception as e:
            logger.error(f"Failed to load conversation: {e}", exc_info=True)
            # Remove loading indicator and show error
            self._chat_box.remove(loading_bubble)
            error_bubble = ChatBubble(f"❌ Failed to load conversation: {str(e)}", is_user=False, is_error=True)
            self._chat_box.append(error_bubble)
    
    def _on_conversation_loaded(self, proxy, result, user_data, conv_id, loading_bubble):
        """Callback after conversation is loaded in daemon"""
        try:
            proxy.call_finish(result)
            logger.info(f"Switched to conversation {conv_id} in daemon")
            self._current_conversation_id = conv_id
            self._history_panel.set_active_conversation(conv_id)
            
            # Remove loading indicator
            try:
                self._chat_box.remove(loading_bubble)
            except:
                pass
            
            # Now fetch messages
            app = self.get_application()
            if app and app._daemon_proxy:
                app._daemon_proxy.call(
                    'GetConversationMessages',
                    GLib.Variant('(i)', (conv_id,)),
                    Gio.DBusCallFlags.NONE,
                    5000,
                    None,
                    self._on_messages_received,
                    None
                )
            else:
                logger.error("No daemon proxy available for fetching messages")
        except Exception as e:
            logger.error(f"Failed to confirm conversation load: {e}", exc_info=True)
            # Remove loading and show error
            try:
                self._chat_box.remove(loading_bubble)
            except:
                pass
            error_bubble = ChatBubble(f"❌ Failed to load conversation: {str(e)}", is_user=False, is_error=True)
            self._chat_box.append(error_bubble)

    def _load_new_conversation(self):
        """Start a new conversation"""
        app = self.get_application()
        if not app or not app._daemon_proxy:
            return
        
        self._clear_chat_bubbles()
        self._chat_header_label.set_label("New Chat")
        
        # Create new conversation in daemon
        try:
            app._daemon_proxy.call(
                'NewConversation',
                GLib.Variant('(s)', ("New Chat",)),
                Gio.DBusCallFlags.NONE,
                5000,
                None,
                lambda p, r, u: self._on_new_conversation_created(p, r, u),
                None
            )
        except Exception as e:
            logger.error(f"Failed to create new conversation: {e}")
        
        # Add welcome message
        welcome = ChatBubble(
            "Started a new conversation. How can I help?",
            is_user=False
        )
        self._chat_box.append(welcome)
    
    def _on_new_conversation_created(self, proxy, result, user_data):
        """Callback after new conversation is created"""
        try:
            variant = proxy.call_finish(result)
            conv_id = variant.unpack()[0]
            logger.info(f"Created new conversation {conv_id}")
            self._current_conversation_id = conv_id
            self._history_panel.set_active_conversation(conv_id)
            
            # Refresh history to show new conversation
            GLib.timeout_add(500, self._refresh_history)
        except Exception as e:
            logger.error(f"Failed to get new conversation ID: {e}")

    def _clear_chat_bubbles(self):
        """Remove all bubbles from chat box"""
        child = self._chat_box.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self._chat_box.remove(child)
            child = next_child

    def _on_messages_received(self, proxy, result, user_data):
        """Handle messages for conversation - COMPLETELY FIXED VERSION"""
        try:
            variant = proxy.call_finish(result)
            messages_raw = variant.unpack()[0]
            
            logger.info(f"📨 Received {len(messages_raw)} raw messages from DBus")
            
            # Convert DBus variants to plain dicts - COMPREHENSIVE PARSING
            messages = []
            for i, msg_raw in enumerate(messages_raw):
                try:
                    msg = {}
                    
                    # Handle dict format (most common)
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
                    
                    # Ensure required fields exist
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
            
            # Update UI in main thread
            def update_ui():
                try:
                    # Clear chat completely
                    self._clear_chat_bubbles()
                    
                    if not messages:
                        # Empty state
                        empty_bubble = ChatBubble(
                            "This conversation is empty. Start chatting to add messages!",
                            is_user=False
                        )
                        self._chat_box.append(empty_bubble)
                        logger.info("Displayed empty conversation state")
                    else:
                        # Add all messages
                        logger.info(f"Adding {len(messages)} messages to chat view")
                        for idx, msg in enumerate(messages):
                            role = msg.get('role', 'assistant')
                            content = msg.get('content', '')
                            
                            if content and content.strip():
                                is_user = (role == 'user')
                                bubble = ChatBubble(content, is_user=is_user)
                                self._chat_box.append(bubble)
                                logger.debug(f"Added message {idx+1}/{len(messages)}: {role}")
                        
                        # Scroll to bottom after a brief delay
                        def scroll():
                            self._scroll_to_bottom()
                            return False
                        GLib.timeout_add(300, scroll)
                    
                except Exception as ui_error:
                    logger.error(f"Error updating UI: {ui_error}", exc_info=True)
                return False
            
            GLib.idle_add(update_ui)
            
        except Exception as e:
            logger.error(f"❌ Failed to load messages: {e}", exc_info=True)
            # Show error in UI
            def show_error():
                try:
                    self._clear_chat_bubbles()
                    error_bubble = ChatBubble(
                        f"❌ Failed to load messages: {str(e)}\n\nPlease try clicking the conversation again.",
                        is_user=False,
                        is_error=True
                    )
                    self._chat_box.append(error_bubble)
                except:
                    pass
            GLib.idle_add(show_error)

    def show_settings(self):
        """Navigate to settings page"""
        self._content_stack.set_visible_child_name('settings')
