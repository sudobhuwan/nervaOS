"""
NervaOS Settings Page - API Configuration UI

A dedicated settings page for managing:
- API provider selection (Gemini, OpenAI, Anthropic, Custom)
- API key input and storage
- Model selection per provider
- Custom endpoint configuration
"""

import logging
from typing import Optional, Callable

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib

from ..core.settings import get_settings_manager, AIProvider
from ..core.secrets import SecretsManager

logger = logging.getLogger('nerva-settings-page')


class APISettingsPage(Gtk.Box):
    """
    Complete API settings page with provider selection and key management.
    """
    
    def __init__(self, on_save_callback: Optional[Callable] = None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        
        self._settings = get_settings_manager()
        self._secrets = SecretsManager()
        self._on_save = on_save_callback
        
        self._setup_ui()
        
        self._initializing = True
        self._load_current_settings()
        self._initializing = False
    
    def _setup_ui(self):
        """Build the settings UI"""
        # Scrollable content
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        
        # Clamp for readable width
        clamp = Adw.Clamp()
        clamp.set_maximum_size(700)
        
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        content.set_margin_top(24)
        content.set_margin_bottom(24)
        content.set_margin_start(16)
        content.set_margin_end(16)
        
        # ─────────────────────────────────────────────────────────
        # User Interface
        # ─────────────────────────────────────────────────────────
        ui_group = Adw.PreferencesGroup()
        ui_group.set_title("User Interface")
        
        # Persistent Bubble
        self._bubble_switch = Adw.SwitchRow()
        self._bubble_switch.set_title("Persistent Bubble")
        self._bubble_switch.set_subtitle("Show floating AI bubble on desktop")
        self._bubble_switch.connect('notify::active', self._on_bubble_toggled)
        ui_group.add(self._bubble_switch)

        # Command capability mode
        self._command_mode_row = Adw.ComboRow()
        self._command_mode_row.set_title("Command Capability")
        self._command_mode_row.set_subtitle("Safe: strict allow-list, Balanced: broad with confirmations, Power: maximum non-destructive access")
        command_modes = Gtk.StringList.new([
            "Balanced (Recommended)",
            "Safe",
            "Power",
        ])
        self._command_mode_row.set_model(command_modes)
        ui_group.add(self._command_mode_row)
        
        content.append(ui_group)
        
        # ─────────────────────────────────────────────────────────
        # Provider Selection
        # ─────────────────────────────────────────────────────────
        provider_group = Adw.PreferencesGroup()
        provider_group.set_title("AI Provider")
        provider_group.set_description(
            "Choose your preferred AI provider. Paste your API keys below and click Save."
        )
        
        # Provider combo
        self._provider_row = Adw.ComboRow()
        self._provider_row.set_title("Active Provider")
        self._provider_row.set_subtitle("Select which AI service to use")
        
        providers = Gtk.StringList.new([
            "Google Gemini", 
            "OpenAI",
            "Anthropic (Claude)",
            "Custom Endpoint"
        ])
        self._provider_row.set_model(providers)
        self._provider_row.connect('notify::selected', self._on_provider_changed)
        provider_group.add(self._provider_row)
        
        content.append(provider_group)
        
        # ─────────────────────────────────────────────────────────
        # Gemini Configuration
        # ─────────────────────────────────────────────────────────
        self._gemini_group = Adw.PreferencesGroup()
        self._gemini_group.set_title("Google Gemini")
        self._gemini_group.set_description("Get your API key from Google AI Studio")
        
        # API Key link
        key_link = Adw.ActionRow()
        key_link.set_title("Get API Key")
        key_link.set_subtitle("ai.google.dev")
        key_link.set_activatable(True)
        key_link.add_suffix(Gtk.Image.new_from_icon_name('external-link-symbolic'))
        key_link.connect('activated', lambda r: self._open_url('https://aistudio.google.com/apikey'))
        self._gemini_group.add(key_link)
        
        # API Key entry
        self._gemini_key_row = Adw.PasswordEntryRow()
        self._gemini_key_row.set_title("API Key")
        self._gemini_group.add(self._gemini_key_row)
        
        # Model selection
        self._gemini_model_row = Adw.ComboRow()
        self._gemini_model_row.set_title("Model")
        self._gemini_model_row.set_subtitle("Choose the Gemini model to use")
        gemini_models = Gtk.StringList.new([
            "gemini-2.0-flash",
            "gemini-2.0-flash-lite",
            "gemini-1.5-pro",
            "gemini-1.5-flash",
            "gemini-1.5-flash-8b"
        ])
        self._gemini_model_row.set_model(gemini_models)
        self._gemini_group.add(self._gemini_model_row)
        
        # Status indicator
        self._gemini_status = Adw.ActionRow()
        self._gemini_status.set_title("Status")
        self._gemini_status_label = Gtk.Label(label="Not configured")
        self._gemini_status_label.add_css_class('dim-label')
        self._gemini_status.add_suffix(self._gemini_status_label)
        self._gemini_group.add(self._gemini_status)
        
        content.append(self._gemini_group)
        
        # ─────────────────────────────────────────────────────────
        # OpenAI Configuration  
        # ─────────────────────────────────────────────────────────
        self._openai_group = Adw.PreferencesGroup()
        self._openai_group.set_title("OpenAI")
        self._openai_group.set_description("Get your API key from OpenAI Platform")
        
        # API Key link
        openai_link = Adw.ActionRow()
        openai_link.set_title("Get API Key")
        openai_link.set_subtitle("platform.openai.com")
        openai_link.set_activatable(True)
        openai_link.add_suffix(Gtk.Image.new_from_icon_name('external-link-symbolic'))
        openai_link.connect('activated', lambda r: self._open_url('https://platform.openai.com/api-keys'))
        self._openai_group.add(openai_link)
        
        # API Key entry
        self._openai_key_row = Adw.PasswordEntryRow()
        self._openai_key_row.set_title("API Key")
        self._openai_group.add(self._openai_key_row)
        
        # Model selection
        self._openai_model_row = Adw.ComboRow()
        self._openai_model_row.set_title("Model")
        openai_models = Gtk.StringList.new([
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4-turbo",
            "gpt-3.5-turbo",
            "o1-preview",
            "o1-mini"
        ])
        self._openai_model_row.set_model(openai_models)
        self._openai_group.add(self._openai_model_row)
        
        # Status
        self._openai_status = Adw.ActionRow()
        self._openai_status.set_title("Status")
        self._openai_status_label = Gtk.Label(label="Not configured")
        self._openai_status_label.add_css_class('dim-label')
        self._openai_status.add_suffix(self._openai_status_label)
        self._openai_group.add(self._openai_status)
        
        content.append(self._openai_group)
        
        # ─────────────────────────────────────────────────────────
        # Anthropic Configuration
        # ─────────────────────────────────────────────────────────
        self._anthropic_group = Adw.PreferencesGroup()
        self._anthropic_group.set_title("Anthropic (Claude)")
        self._anthropic_group.set_description("Get your API key from Anthropic Console")
        
        # API Key link
        anthropic_link = Adw.ActionRow()
        anthropic_link.set_title("Get API Key")
        anthropic_link.set_subtitle("console.anthropic.com")
        anthropic_link.set_activatable(True)
        anthropic_link.add_suffix(Gtk.Image.new_from_icon_name('external-link-symbolic'))
        anthropic_link.connect('activated', lambda r: self._open_url('https://console.anthropic.com/settings/keys'))
        self._anthropic_group.add(anthropic_link)
        
        # API Key entry
        self._anthropic_key_row = Adw.PasswordEntryRow()
        self._anthropic_key_row.set_title("API Key")
        self._anthropic_group.add(self._anthropic_key_row)
        
        # Model selection
        self._anthropic_model_row = Adw.ComboRow()
        self._anthropic_model_row.set_title("Model")
        anthropic_models = Gtk.StringList.new([
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20241022",
            "claude-3-opus-20240229"
        ])
        self._anthropic_model_row.set_model(anthropic_models)
        self._anthropic_group.add(self._anthropic_model_row)
        
        # Status
        self._anthropic_status = Adw.ActionRow()
        self._anthropic_status.set_title("Status")
        self._anthropic_status_label = Gtk.Label(label="Not configured")
        self._anthropic_status_label.add_css_class('dim-label')
        self._anthropic_status.add_suffix(self._anthropic_status_label)
        self._anthropic_group.add(self._anthropic_status)
        
        content.append(self._anthropic_group)
        
        # ─────────────────────────────────────────────────────────
        # Custom Endpoint Configuration
        # ─────────────────────────────────────────────────────────
        self._custom_group = Adw.PreferencesGroup()
        self._custom_group.set_title("Custom Endpoint")
        self._custom_group.set_description("Use any OpenAI-compatible API endpoint")
        
        # Endpoint URL
        self._custom_endpoint_row = Adw.EntryRow()
        self._custom_endpoint_row.set_title("API Endpoint URL")
        self._custom_endpoint_row.set_text("https://api.example.com/v1/chat/completions")
        self._custom_group.add(self._custom_endpoint_row)
        
        # API Key
        self._custom_key_row = Adw.PasswordEntryRow()
        self._custom_key_row.set_title("API Key")
        self._custom_group.add(self._custom_key_row)
        
        # Model name
        self._custom_model_row = Adw.EntryRow()
        self._custom_model_row.set_title("Model Name")
        self._custom_model_row.set_text("gpt-4")
        self._custom_group.add(self._custom_model_row)
        
        content.append(self._custom_group)
        
        # ─────────────────────────────────────────────────────────
        # Save Button
        # ─────────────────────────────────────────────────────────
        save_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        save_box.set_halign(Gtk.Align.END)
        save_box.set_margin_top(16)
        
        test_btn = Gtk.Button(label="Test Connection")
        test_btn.connect('clicked', self._on_test_connection)
        save_box.append(test_btn)
        
        save_btn = Gtk.Button(label="Save Settings")
        save_btn.add_css_class('suggested-action')
        save_btn.connect('clicked', self._on_save_clicked)
        save_box.append(save_btn)
        
        content.append(save_box)
        
        # Status message area
        self._status_revealer = Gtk.Revealer()
        self._status_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        
        self._status_bar = Adw.Banner()
        self._status_bar.set_title("Settings saved successfully")
        self._status_revealer.set_child(self._status_bar)
        
        content.append(self._status_revealer)
        
        clamp.set_child(content)
        scroll.set_child(clamp)
        self.append(scroll)
        
        # Initial visibility
        self._update_provider_visibility()
        
    def _load_current_settings(self):
        """Load current settings into UI"""
        settings = self._settings.load()
        
        # Set active provider
        provider_map = {'gemini': 0, 'openai': 1, 'anthropic': 2, 'custom': 3}
        idx = provider_map.get(settings.active_provider, 0)
        idx = provider_map.get(settings.active_provider, 0)
        self._provider_row.set_selected(idx)
        
        # UI Settings
        self._bubble_switch.set_active(settings.show_bubble)
        mode_map = {'balanced': 0, 'safe': 1, 'power': 2}
        self._command_mode_row.set_selected(mode_map.get(getattr(settings, 'command_mode', 'balanced'), 0))
        
        # Load model selections
        self._set_model_selection(self._gemini_model_row, 
                                  settings.providers['gemini'].get('model', ''))
        self._set_model_selection(self._openai_model_row,
                                  settings.providers['openai'].get('model', ''))
        self._set_model_selection(self._anthropic_model_row,
                                  settings.providers['anthropic'].get('model', ''))
        
        # Custom endpoint
        custom = settings.providers.get('custom', {})
        if custom.get('endpoint'):
            self._custom_endpoint_row.set_text(custom['endpoint'])
        if custom.get('model'):
            self._custom_model_row.set_text(custom['model'])
        
        # Load existing API keys (show masked if present)
        # Note: We don't show the actual key for security, just indicate it's set
        # PasswordEntryRow doesn't support placeholder/subtitle, so we rely on status indicators
        # The status indicators below will show if keys are configured
        
        # Update status indicators
        self._update_status_indicators()
    
    def _set_model_selection(self, combo_row, model: str):
        """Set the selected model in a combo row"""
        if not model:
            return
        
        model_list = combo_row.get_model()
        for i in range(model_list.get_n_items()):
            if model_list.get_string(i) == model:
                combo_row.set_selected(i)
                break
    
    def _update_status_indicators(self):
        """Update the status labels based on API key presence"""
        providers = {
            'gemini': self._gemini_status_label,
            'openai': self._openai_status_label,
            'anthropic': self._anthropic_status_label
        }
        
        for provider, label in providers.items():
            if self._secrets.has_api_key(provider):
                label.set_text("✓ API Key configured")
                label.remove_css_class('dim-label')
                label.add_css_class('success')
            else:
                label.set_text("Not configured")
                label.remove_css_class('success')
                label.add_css_class('dim-label')
    
    def _on_provider_changed(self, combo_row, param):
        """Handle provider selection change"""
        self._update_provider_visibility()
    
    
    def _on_bubble_toggled(self, row, param):
        """Handle bubble toggle immediately"""
        if getattr(self, '_initializing', False):
            return
            
        settings = self._settings.load()
        settings.show_bubble = row.get_active()
        
        if self._settings.save():
            # Notify app to update visibility immediately
            if self._on_save:
                self._on_save()
    
    def _update_provider_visibility(self):
        """Show/hide provider sections based on selection"""
        selected = self._provider_row.get_selected()
        
        # Highlight the active provider section
        self._gemini_group.set_sensitive(True)
        self._openai_group.set_sensitive(True)
        self._anthropic_group.set_sensitive(True)
        self._custom_group.set_sensitive(True)
        
        # Could also collapse non-selected providers if desired
    
    def _open_url(self, url: str):
        """Open a URL in the default browser"""
        try:
            import subprocess
            subprocess.Popen(['xdg-open', url])
        except Exception as e:
            logger.error(f"Failed to open URL: {e}")
    
    def _on_save_clicked(self, button):
        """Save all settings with validation"""
        settings = self._settings.load()
        errors = []
        saved_keys = []
        
        # Save active provider
        provider_map = {0: 'gemini', 1: 'openai', 2: 'anthropic', 3: 'custom'}
        provider_map = {0: 'gemini', 1: 'openai', 2: 'anthropic', 3: 'custom'}
        settings.active_provider = provider_map.get(self._provider_row.get_selected(), 'gemini')
        
        # Save UI settings
        settings.show_bubble = self._bubble_switch.get_active()
        command_mode_map = {0: 'balanced', 1: 'safe', 2: 'power'}
        settings.command_mode = command_mode_map.get(self._command_mode_row.get_selected(), 'balanced')
        
        # Save Gemini settings
        gemini_key = self._gemini_key_row.get_text().strip()
        if gemini_key:
            if self._validate_api_key('gemini', gemini_key):
                if self._secrets.set_api_key('gemini', gemini_key):
                    saved_keys.append('Gemini')
                else:
                    errors.append("Failed to save Gemini API key")
            else:
                errors.append("Invalid Gemini API key format")
        
        gemini_model = self._gemini_model_row.get_model().get_string(
            self._gemini_model_row.get_selected()
        )
        settings.providers['gemini']['model'] = gemini_model
        
        # Save OpenAI settings
        openai_key = self._openai_key_row.get_text().strip()
        if openai_key:
            if self._validate_api_key('openai', openai_key):
                if self._secrets.set_api_key('openai', openai_key):
                    saved_keys.append('OpenAI')
                else:
                    errors.append("Failed to save OpenAI API key")
            else:
                errors.append("Invalid OpenAI API key format")
        
        openai_model = self._openai_model_row.get_model().get_string(
            self._openai_model_row.get_selected()
        )
        settings.providers['openai']['model'] = openai_model
        
        # Save Anthropic settings
        anthropic_key = self._anthropic_key_row.get_text().strip()
        if anthropic_key:
            if self._validate_api_key('anthropic', anthropic_key):
                if self._secrets.set_api_key('anthropic', anthropic_key):
                    saved_keys.append('Anthropic')
                else:
                    errors.append("Failed to save Anthropic API key")
            else:
                errors.append("Invalid Anthropic API key format")
        
        anthropic_model = self._anthropic_model_row.get_model().get_string(
            self._anthropic_model_row.get_selected()
        )
        settings.providers['anthropic']['model'] = anthropic_model
        
        # Save custom endpoint settings
        custom_key = self._custom_key_row.get_text().strip()
        if custom_key:
            if self._secrets.set_api_key('custom', custom_key):
                saved_keys.append('Custom')
            else:
                errors.append("Failed to save Custom API key")
        
        settings.providers['custom']['endpoint'] = self._custom_endpoint_row.get_text().strip()
        settings.providers['custom']['model'] = self._custom_model_row.get_text().strip()

        # Save to disk
        settings_ok = self._settings.save()
        if settings_ok and not errors:
            msg = f"✓ Settings saved! API keys saved for: {', '.join(saved_keys)}" if saved_keys else "✓ Settings saved!"
            self._show_status(msg, is_error=False)
        elif settings_ok and errors:
            parts = [f"✓ Saved: {', '.join(saved_keys)}"] if saved_keys else []
            parts.append("Issues: " + "; ".join(errors))
            self._show_status(" ".join(parts), is_error=True)
        elif not settings_ok and errors:
            self._show_status("✗ Failed to save settings. " + "; ".join(errors), is_error=True)
        else:
            self._show_status("✗ Failed to save settings", is_error=True)
        
        # Update status indicators
        self._update_status_indicators()
        
        # Notify callback (this will refresh model selectors in chat)
        if self._on_save:
            self._on_save()
    
    def _validate_api_key(self, provider: str, key: str) -> bool:
        """Validate API key format – relaxed to avoid rejecting valid keys."""
        if not key or not key.strip():
            return False
        key = key.strip()
        if len(key) < 8:
            return False
        if provider == 'gemini':
            return True
        if provider == 'openai':
            return key.startswith('sk-')
        if provider == 'anthropic':
            return key.startswith('sk-ant-')
        return True
    
    def _on_test_connection(self, button):
        """Test the API connection for the selected provider with better error handling"""
        provider_map = {0: 'gemini', 1: 'openai', 2: 'anthropic', 3: 'custom'}
        provider = provider_map.get(self._provider_row.get_selected(), 'gemini')
        
        # Get API key (check input field first, then stored key)
        api_key = None
        
        # Check input fields for new keys
        if provider == 'gemini':
            api_key = self._gemini_key_row.get_text().strip()
        elif provider == 'openai':
            api_key = self._openai_key_row.get_text().strip()
        elif provider == 'anthropic':
            api_key = self._anthropic_key_row.get_text().strip()
        elif provider == 'custom':
            api_key = self._custom_key_row.get_text().strip()
        
        # Fall back to stored key
        if not api_key:
            api_key = self._secrets.get_api_key(provider)
        
        if not api_key:
            self._show_status(f"✗ No API key configured for {provider}. Please enter an API key first.", is_error=True)
            return
        
        # Validate key format
        if not self._validate_api_key(provider, api_key):
            self._show_status(f"✗ Invalid API key format for {provider}", is_error=True)
            return
        
        button.set_sensitive(False)
        button.set_label("Testing...")
        
        # Test connection in background
        def do_test():
            try:
                from ..ai.client import AIClient
                
                # Get model from settings
                settings = self._settings.load()
                model = settings.providers.get(provider, {}).get('model', '')
                
                # Create client
                client = AIClient(api_key=api_key, provider=provider, model=model or None)
                
                # Simple test query
                import asyncio
                
                async def test_query():
                    response = await client.ask("Say 'Hello' in one word.", {})
                    if response and hasattr(response, 'content'):
                        return response.content
                    elif isinstance(response, str):
                        return response
                    else:
                        return "Connection successful"
                
                result = asyncio.run(test_query())
                
                GLib.idle_add(lambda: self._show_test_result(True, result[:100] if result else "Success", button))
                
            except Exception as e:
                error_msg = str(e)
                # Provide more helpful error messages
                if "API key" in error_msg or "authentication" in error_msg.lower():
                    error_msg = f"Invalid API key or authentication failed. Please check your {provider} API key."
                elif "network" in error_msg.lower() or "connection" in error_msg.lower():
                    error_msg = f"Network error. Please check your internet connection."
                elif "rate limit" in error_msg.lower():
                    error_msg = f"Rate limit exceeded. Please try again later."
                else:
                    error_msg = f"Connection failed: {error_msg}"
                
                GLib.idle_add(lambda: self._show_test_result(False, error_msg, button))
        
        import threading
        thread = threading.Thread(target=do_test)
        thread.daemon = True
        thread.start()
    
    def _show_test_result(self, success: bool, message: str, button):
        """Show test result with better formatting"""
        button.set_sensitive(True)
        button.set_label("Test Connection")
        
        if success:
            self._show_status(f"✓ Connection successful! Response: {message}", is_error=False)
            # Update status indicator
            provider_map = {0: 'gemini', 1: 'openai', 2: 'anthropic', 3: 'custom'}
            provider = provider_map.get(self._provider_row.get_selected(), 'gemini')
            if provider in ['gemini', 'openai', 'anthropic']:
                status_labels = {
                    'gemini': self._gemini_status_label,
                    'openai': self._openai_status_label,
                    'anthropic': self._anthropic_status_label
                }
                if provider in status_labels:
                    status_labels[provider].set_text("✓ API Key configured and working")
                    status_labels[provider].remove_css_class('dim-label')
                    status_labels[provider].add_css_class('success')
        else:
            self._show_status(f"✗ Connection failed: {message}", is_error=True)
    
    def _show_status(self, message: str, is_error: bool = False):
        """Show a status message"""
        self._status_bar.set_title(message)
        
        if is_error:
            self._status_bar.add_css_class('error')
        else:
            self._status_bar.remove_css_class('error')
        
        self._status_revealer.set_reveal_child(True)
        
        # Auto-hide after 5 seconds
        GLib.timeout_add(5000, lambda: self._status_revealer.set_reveal_child(False))
    
