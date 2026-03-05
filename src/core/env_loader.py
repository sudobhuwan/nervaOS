"""
NervaOS Environment Loader - Configuration from .env files

This module provides a unified way to load configuration from:
1. Environment variables (highest priority)
2. .env file in the project root
3. ~/.config/nervaos/.env (user config)
4. Default values

This is the preferred way to configure NervaOS for development.
For production, use the Gnome Keyring via SecretsManager.
"""

import os
import logging
from pathlib import Path
from typing import Optional, Any, Dict

logger = logging.getLogger('nerva-env')

# Try to import python-dotenv
try:
    from dotenv import load_dotenv, dotenv_values
    DOTENV_AVAILABLE = True
except ImportError:
    DOTENV_AVAILABLE = False
    load_dotenv = None
    dotenv_values = None


class EnvLoader:
    """
    Environment configuration loader with cascading priority.
    
    Priority (highest to lowest):
    1. OS environment variables
    2. .env in current working directory
    3. .env in project root (/path/to/NervaOS/.env)
    4. ~/.config/nervaos/.env
    5. Default values
    """
    
    # Default values for all configuration options
    DEFAULTS: Dict[str, Any] = {
        # API Keys (no defaults - must be set by user)
        'GEMINI_API_KEY': None,
        'OPENAI_API_KEY': None,
        'ANTHROPIC_API_KEY': None,
        'CUSTOM_API_KEY': None,
        
        # Provider settings
        'AI_PROVIDER': 'gemini',
        'AI_MODEL': '',
        'CUSTOM_API_URL': '',
        'CUSTOM_API_MODEL': '',
        
        # License
        'LICENSE_SERVER_URL': 'https://nervaos-license.onrender.com',
        'LICENSE_KEY': None,
        
        # Behavior
        'CONTEXT_AWARENESS': True,
        'AUTO_MODE_SWITCH': True,
        'MAX_FILE_SIZE_MB': 10,
        'BACKUP_RETENTION_DAYS': 7,
        
        # Monitoring
        'MONITOR_INTERVAL': 5,
        'RAM_ALERT_THRESHOLD': 90,
        'CPU_ALERT_THRESHOLD': 95,
        
        # UI
        'HOTKEY': '<Super>space',
        'THEME': 'system',
        
        # Privacy
        'LOG_API_CALLS': True,
        'TELEMETRY': False,
        'DEBUG': False,
    }
    
    _instance = None
    _loaded = False
    _values: Dict[str, str] = {}
    
    def __new__(cls):
        """Singleton pattern - only one instance"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._loaded:
            self._load_all_env_files()
            EnvLoader._loaded = True
    
    def _load_all_env_files(self):
        """Load .env files from all possible locations"""
        if not DOTENV_AVAILABLE:
            logger.warning(
                "python-dotenv not installed. "
                "Only OS environment variables will be used. "
                "Install with: pip install python-dotenv"
            )
            return
        
        # Find all possible .env file locations
        env_files = self._find_env_files()
        
        # Load in reverse order (lowest priority first, highest priority last)
        for env_file in reversed(env_files):
            if env_file.exists():
                logger.info(f"Loading config from: {env_file}")
                load_dotenv(env_file, override=True)
                
                # Also store values directly
                file_values = dotenv_values(env_file)
                self._values.update(file_values)
    
    def _find_env_files(self) -> list:
        """Find all possible .env file locations (priority order)"""
        locations = []
        
        # 1. User config directory (~/.config/nervaos/.env)
        user_config = Path.home() / '.config' / 'nervaos' / '.env'
        locations.append(user_config)
        
        # 2. Project root (find by looking for src/ directory)
        project_root = self._find_project_root()
        if project_root:
            locations.append(project_root / '.env')
        
        # 3. Current working directory
        cwd_env = Path.cwd() / '.env'
        if cwd_env not in locations:
            locations.append(cwd_env)
        
        return locations
    
    def _find_project_root(self) -> Optional[Path]:
        """Find the NervaOS project root directory"""
        # Start from this file's directory and go up
        current = Path(__file__).resolve().parent
        
        for _ in range(5):  # Max 5 levels up
            if (current / 'src').is_dir() and (current / 'requirements.txt').exists():
                return current
            current = current.parent
        
        return None
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value.
        
        Args:
            key: Configuration key (e.g., 'GEMINI_API_KEY')
            default: Default value if not found
            
        Returns:
            The configuration value
        """
        # Priority 1: OS environment variable
        value = os.environ.get(key)
        if value is not None:
            return self._convert_type(key, value)
        
        # Priority 2: Loaded .env values
        value = self._values.get(key)
        if value is not None:
            return self._convert_type(key, value)
        
        # Priority 3: Explicit default parameter
        if default is not None:
            return default
        
        # Priority 4: Class default values
        return self.DEFAULTS.get(key)
    
    def _convert_type(self, key: str, value: str) -> Any:
        """Convert string value to appropriate type based on default"""
        if value is None or value == '':
            return None
        
        default = self.DEFAULTS.get(key)
        
        # Boolean conversion
        if isinstance(default, bool):
            return value.lower() in ('true', '1', 'yes', 'on')
        
        # Integer conversion
        if isinstance(default, int):
            try:
                return int(value)
            except ValueError:
                return default
        
        # Float conversion
        if isinstance(default, float):
            try:
                return float(value)
            except ValueError:
                return default
        
        # String (default)
        return value
    
    def get_api_key(self, provider: str) -> Optional[str]:
        """
        Get API key for a specific provider.
        
        Args:
            provider: 'gemini', 'openai', 'anthropic', or 'custom'
            
        Returns:
            The API key or None
        """
        key_mapping = {
            'gemini': 'GEMINI_API_KEY',
            'openai': 'OPENAI_API_KEY',
            'anthropic': 'ANTHROPIC_API_KEY',
            'custom': 'CUSTOM_API_KEY',
        }
        
        env_key = key_mapping.get(provider.lower())
        if env_key:
            return self.get(env_key)
        
        return None
    
    def has_api_key(self, provider: str) -> bool:
        """Check if an API key is configured for the provider"""
        key = self.get_api_key(provider)
        return key is not None and len(key) > 0
    
    def get_configured_providers(self) -> list:
        """Get list of providers that have API keys configured"""
        providers = []
        for provider in ['gemini', 'openai', 'anthropic', 'custom']:
            if self.has_api_key(provider):
                providers.append(provider)
        return providers
    
    def is_configured(self) -> bool:
        """Check if at least one API provider is configured"""
        return len(self.get_configured_providers()) > 0
    
    def get_all(self) -> Dict[str, Any]:
        """Get all configuration values (for debugging)"""
        result = {}
        for key in self.DEFAULTS.keys():
            value = self.get(key)
            # Mask API keys
            if 'API_KEY' in key and value:
                value = value[:4] + '*' * (len(value) - 8) + value[-4:] if len(value) > 8 else '****'
            result[key] = value
        return result
    
    def reload(self):
        """Force reload of all .env files"""
        EnvLoader._loaded = False
        EnvLoader._values = {}
        self._load_all_env_files()
        EnvLoader._loaded = True
        logger.info("Configuration reloaded")


# ─────────────────────────────────────────────────────────────────────────────────
# Convenience functions
# ─────────────────────────────────────────────────────────────────────────────────

# Global instance
_env = None

def get_env() -> EnvLoader:
    """Get the global EnvLoader instance"""
    global _env
    if _env is None:
        _env = EnvLoader()
    return _env


def env(key: str, default: Any = None) -> Any:
    """Shorthand for getting an environment variable"""
    return get_env().get(key, default)


def get_api_key(provider: str) -> Optional[str]:
    """Shorthand for getting an API key"""
    return get_env().get_api_key(provider)


# ─────────────────────────────────────────────────────────────────────────────────
# CLI for testing
# ─────────────────────────────────────────────────────────────────────────────────

def main():
    """CLI tool for viewing configuration"""
    import sys
    import json
    
    loader = EnvLoader()
    
    if len(sys.argv) > 1:
        key = sys.argv[1].upper()
        value = loader.get(key)
        if value is not None:
            print(f"{key}={value}")
        else:
            print(f"{key} is not set")
            sys.exit(1)
    else:
        print("═" * 60)
        print("           NERVAOS CONFIGURATION STATUS")
        print("═" * 60)
        print()
        
        config = loader.get_all()
        
        # Group by category
        categories = {
            'API Keys': ['GEMINI_API_KEY', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'CUSTOM_API_KEY'],
            'Provider': ['AI_PROVIDER', 'AI_MODEL', 'CUSTOM_API_URL', 'CUSTOM_API_MODEL'],
            'License': ['LICENSE_SERVER_URL', 'LICENSE_KEY'],
            'Behavior': ['CONTEXT_AWARENESS', 'AUTO_MODE_SWITCH', 'MAX_FILE_SIZE_MB', 'BACKUP_RETENTION_DAYS'],
            'Monitoring': ['MONITOR_INTERVAL', 'RAM_ALERT_THRESHOLD', 'CPU_ALERT_THRESHOLD'],
            'UI': ['HOTKEY', 'THEME'],
            'Privacy': ['LOG_API_CALLS', 'TELEMETRY', 'DEBUG'],
        }
        
        for category, keys in categories.items():
            print(f"┌─ {category} {'─' * (55 - len(category))}")
            for key in keys:
                value = config.get(key, 'not set')
                status = "✓" if value and value != 'not set' else "○"
                display = str(value) if value else "(not set)"
                print(f"│ {status} {key}: {display}")
            print("│")
        
        print("═" * 60)
        
        # Summary
        providers = loader.get_configured_providers()
        if providers:
            print(f"✓ Configured providers: {', '.join(providers)}")
        else:
            print("✗ No API keys configured!")
            print("  Copy .env.example to .env and add your API key")


if __name__ == '__main__':
    main()
