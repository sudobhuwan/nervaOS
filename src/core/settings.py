"""
NervaOS Settings Manager - Configuration persistence

Handles:
- API provider configuration
- Model selection
- User preferences
- Configuration file management
"""

import os
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict, field
from enum import Enum

logger = logging.getLogger('nerva-settings')


class AIProvider(Enum):
    """Supported AI providers"""
    GEMINI = "gemini"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    CUSTOM = "custom"


@dataclass
class ProviderConfig:
    """Configuration for a single AI provider"""
    enabled: bool = False
    api_key_set: bool = False  # Don't store the actual key here
    model: str = ""
    endpoint: str = ""  # For custom providers


@dataclass 
class NervaSettings:
    """Complete NervaOS settings"""
    
    # Active provider
    active_provider: str = "gemini"
    
    # Provider configurations
    providers: Dict[str, Dict[str, Any]] = field(default_factory=lambda: {
        "gemini": {
            "enabled": True,
            "model": "gemini-2.0-flash",
            "models_available": [
                "gemini-2.0-flash",
                "gemini-2.0-flash-lite", 
                "gemini-1.5-pro",
                "gemini-1.5-flash",
                "gemini-1.5-flash-8b"
            ]
        },
        "openai": {
            "enabled": False,
            "model": "gpt-4o-mini",
            "endpoint": "https://api.openai.com/v1/chat/completions",
            "models_available": [
                "gpt-4o",
                "gpt-4o-mini",
                "gpt-4-turbo",
                "gpt-3.5-turbo",
                "o1-preview",
                "o1-mini"
            ]
        },
        "anthropic": {
            "enabled": False,
            "model": "claude-3-5-sonnet-20241022",
            "endpoint": "https://api.anthropic.com/v1/messages",
            "models_available": [
                "claude-3-5-sonnet-20241022",
                "claude-3-5-haiku-20241022",
                "claude-3-opus-20240229"
            ]
        },
        "custom": {
            "enabled": False,
            "model": "",
            "endpoint": "",
            "models_available": []
        }
    })
    
    # Behavior settings
    context_awareness: bool = True
    auto_mode_switch: bool = True
    
    # Safety settings
    max_file_size_mb: int = 10
    backup_retention_days: int = 7
    command_mode: str = "power"  # safe, balanced, power
    
    # UI settings
    theme: str = "system"  # system, light, dark
    hotkey: str = "<Super>space"
    show_bubble: bool = True
    
    # Privacy settings
    log_api_calls: bool = True
    telemetry: bool = False


class SettingsManager:
    """
    Manages NervaOS settings persistence.
    
    Settings are stored in ~/.config/nervaos/settings.json
    API keys are stored separately in the keyring (secrets.py)
    """
    
    def __init__(self):
        self._config_dir = Path.home() / '.config' / 'nervaos'
        self._settings_file = self._config_dir / 'settings.json'
        self._settings: Optional[NervaSettings] = None
        
        # Ensure config directory exists
        self._config_dir.mkdir(parents=True, exist_ok=True)
    
    def reload(self) -> None:
        """Invalidate cached settings so next load() reads from disk.
        Call this when another process (e.g. UI) may have saved new settings."""
        self._settings = None
    
    def load(self) -> NervaSettings:
        """Load settings from disk or create defaults"""
        if self._settings is not None:
            return self._settings
        
        if self._settings_file.exists():
            try:
                with open(self._settings_file, 'r') as f:
                    data = json.load(f)
                self._settings = self._dict_to_settings(data)
                logger.info("Settings loaded from disk")
            except Exception as e:
                logger.error(f"Failed to load settings: {e}")
                self._settings = NervaSettings()
        else:
            self._settings = NervaSettings()
            self.save()  # Create default settings file
            logger.info("Created default settings")
        
        return self._settings
    
    def save(self) -> bool:
        """Save settings to disk"""
        if self._settings is None:
            return False
        
        try:
            # Ensure models_available is preserved for all providers
            # This prevents losing the model list when settings are saved
            # Use cached defaults to avoid creating new object every time
            if not hasattr(self, '_default_settings'):
                self._default_settings = NervaSettings()
            
            for provider, config in self._settings.providers.items():
                if 'models_available' not in config or not config.get('models_available'):
                    # Restore from defaults if missing
                    if provider in self._default_settings.providers:
                        default_models = self._default_settings.providers[provider].get('models_available', [])
                        if default_models:
                            config['models_available'] = default_models.copy()
                            logger.debug(f"Restored models_available for {provider}: {len(default_models)} models")
            
            data = self._settings_to_dict(self._settings)
            with open(self._settings_file, 'w') as f:
                json.dump(data, f, indent=2)
            logger.debug("Settings saved to disk")
            return True
        except Exception as e:
            logger.error(f"Failed to save settings: {e}")
            return False
    
    def _settings_to_dict(self, settings: NervaSettings) -> dict:
        """Convert settings to dictionary"""
        return {
            'active_provider': settings.active_provider,
            'providers': settings.providers,
            'context_awareness': settings.context_awareness,
            'auto_mode_switch': settings.auto_mode_switch,
            'max_file_size_mb': settings.max_file_size_mb,
            'backup_retention_days': settings.backup_retention_days,
            'command_mode': settings.command_mode,
            'theme': settings.theme,
            'hotkey': settings.hotkey,
            'show_bubble': settings.show_bubble,
            'log_api_calls': settings.log_api_calls,
            'telemetry': settings.telemetry
        }
    
    def _dict_to_settings(self, data: dict) -> NervaSettings:
        """Convert dictionary to settings object"""
        settings = NervaSettings()
        
        # Merge with defaults (in case new fields were added)
        for key, value in data.items():
            if hasattr(settings, key):
                if key == 'providers':
                    # Merge provider configs intelligently
                    for provider, config in value.items():
                        if provider in settings.providers:
                            # Get default config for this provider (before update overwrites it)
                            default_config = settings.providers[provider].copy()
                            default_models = default_config.get('models_available', [])
                            
                            # Update with saved config
                            default_config.update(config)
                            
                            # CRITICAL: Ensure models_available is always present and complete
                            # If models_available is missing or empty, restore from defaults
                            if 'models_available' not in config or not config.get('models_available'):
                                default_config['models_available'] = default_models.copy()
                            else:
                                # Merge saved models with defaults so all are available
                                saved_models = config.get('models_available', [])
                                all_models = list(dict.fromkeys(default_models + saved_models))
                                default_config['models_available'] = all_models
                            
                            settings.providers[provider] = default_config
                        else:
                            # New provider not in defaults
                            settings.providers[provider] = config
                else:
                    setattr(settings, key, value)
        
        return settings
    
    # ─────────────────────────────────────────────────────────────
    # Convenience Methods
    # ─────────────────────────────────────────────────────────────
    
    def get_active_provider(self) -> str:
        """Get the currently active provider"""
        return self.load().active_provider
    
    def set_active_provider(self, provider: str) -> bool:
        """Set the active provider"""
        settings = self.load()
        if provider in settings.providers:
            settings.active_provider = provider
            return self.save()
        return False
    
    def get_active_model(self) -> str:
        """Get the model for the active provider"""
        settings = self.load()
        provider = settings.active_provider
        return settings.providers.get(provider, {}).get('model', '')
    
    def set_model(self, provider: str, model: str) -> bool:
        """Set the model for a provider"""
        settings = self.load()
        if provider in settings.providers:
            settings.providers[provider]['model'] = model
            return self.save()
        return False
    
    def get_available_models(self, provider: str) -> List[str]:
        """Get available models for a provider"""
        settings = self.load()
        return settings.providers.get(provider, {}).get('models_available', [])
    
    def set_custom_endpoint(self, endpoint: str, model: str = "") -> bool:
        """Configure a custom endpoint"""
        settings = self.load()
        settings.providers['custom']['endpoint'] = endpoint
        settings.providers['custom']['model'] = model
        settings.providers['custom']['enabled'] = True
        return self.save()
    
    def add_custom_model(self, model: str) -> bool:
        """Add a model to custom provider's available list"""
        settings = self.load()
        if model not in settings.providers['custom']['models_available']:
            settings.providers['custom']['models_available'].append(model)
            return self.save()
        return True
    
    def get_provider_config(self, provider: str) -> Dict[str, Any]:
        """Get configuration for a specific provider"""
        settings = self.load()
        return settings.providers.get(provider, {})
    
    def is_provider_configured(self, provider: str) -> bool:
        """Check if a provider has an API key set"""
        from .secrets import SecretsManager
        secrets = SecretsManager()
        return secrets.has_api_key(provider)


# Singleton instance
_settings_manager: Optional[SettingsManager] = None


def get_settings_manager() -> SettingsManager:
    """Get the global settings manager instance"""
    global _settings_manager
    if _settings_manager is None:
        _settings_manager = SettingsManager()
    return _settings_manager
