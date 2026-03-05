"""
NervaOS Secrets Manager - Secure credential storage using Gnome Keyring

This module handles:
- Storing API keys securely in the OS keyring
- Retrieving keys for use by the AI client
- Managing multiple provider credentials
- Fallback to .env file when keyring is unavailable
- Optional JSON config (~/.config/nervaos/config/api_keys.json) for fill & retrieve

Priority for reading keys:
1. Gnome Keyring (most secure)
2. .env file (~/.config/nervaos/.env)
3. JSON config (~/.config/nervaos/config/api_keys.json) – user can manually fill
4. Environment variables
"""

import json
import logging
from typing import Optional, Dict, Any
from pathlib import Path

try:
    import keyring
    KEYRING_AVAILABLE = True
except ImportError:
    KEYRING_AVAILABLE = False
    keyring = None

# Import env loader for fallback
try:
    from .env_loader import get_env, get_api_key as env_get_api_key
    ENV_LOADER_AVAILABLE = True
except ImportError:
    ENV_LOADER_AVAILABLE = False
    get_env = None
    env_get_api_key = None

logger = logging.getLogger('nerva-secrets')

# JSON config folder and file – users can fill keys here and app retrieves
CONFIG_DIR = Path.home() / '.config' / 'nervaos'
CONFIG_JSON_DIR = CONFIG_DIR / 'config'
API_KEYS_JSON = CONFIG_JSON_DIR / 'api_keys.json'
USER_ENV_FILE = CONFIG_DIR / '.env'

PROVIDER_TO_ENV_KEY = {
    'gemini': 'GEMINI_API_KEY',
    'openai': 'OPENAI_API_KEY',
    'anthropic': 'ANTHROPIC_API_KEY',
    'custom': 'CUSTOM_API_KEY',
}


class SecretsManager:
    """
    Secure secret storage using the system keyring.
    
    On Linux Mint/Cinnamon, this uses the Gnome Keyring backend,
    which stores credentials encrypted in the user's login keyring.
    
    Falls back to .env file when keyring is unavailable.
    
    Service name: 'nervaos'
    Keys:
    - gemini_api_key: Google Gemini API key
    - openai_api_key: OpenAI API key
    - anthropic_api_key: Anthropic (Claude) API key
    - custom_api_key: Custom endpoint API key
    - license_key: Product license key (optional)
    """
    
    SERVICE_NAME = 'nervaos'
    
    # Known key names
    KEY_GEMINI = 'gemini_api_key'
    KEY_OPENAI = 'openai_api_key'
    KEY_ANTHROPIC = 'anthropic_api_key'
    KEY_CUSTOM = 'custom_api_key'
    KEY_LICENSE = 'license_key'
    
    def __init__(self):
        if not KEYRING_AVAILABLE:
            logger.warning(
                "keyring library not available. "
                "Secrets will not be stored securely. "
                "Install with: pip install keyring"
            )

    def _load_api_config(self) -> Dict[str, Any]:
        """Load api_keys.json from ~/.config/nervaos/config/. Returns {} if missing/invalid."""
        try:
            if API_KEYS_JSON.exists():
                data = json.loads(API_KEYS_JSON.read_text())
                if isinstance(data, dict):
                    return data
        except Exception as e:
            logger.debug(f"Could not load api_keys.json: {e}")
        return {}

    def _save_api_config(self, data: Dict[str, Any]) -> bool:
        """Save api_keys.json. Creates config dir if needed."""
        try:
            CONFIG_JSON_DIR.mkdir(parents=True, exist_ok=True)
            API_KEYS_JSON.write_text(json.dumps(data, indent=2))
            return True
        except Exception as e:
            logger.error(f"Failed to save api_keys.json: {e}")
            return False

    def _update_json_key(self, provider: str, key: str) -> None:
        """Update a single key in api_keys.json; keep others. No-op on error."""
        env_key = PROVIDER_TO_ENV_KEY.get(provider.lower())
        if not env_key:
            return
        data = self._load_api_config()
        data[env_key] = key.strip()
        self._save_api_config(data)

    def _upsert_user_env_key(self, env_key: str, value: str) -> bool:
        """Upsert a key in ~/.config/nervaos/.env and reload env loader."""
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            env_content = USER_ENV_FILE.read_text() if USER_ENV_FILE.exists() else ""
            lines = env_content.split('\n')
            key_line = f"{env_key}={value.strip()}"
            found = False
            for i, line in enumerate(lines):
                if line.startswith(f"{env_key}="):
                    lines[i] = key_line
                    found = True
                    break
            if not found:
                lines.append(key_line)
            USER_ENV_FILE.write_text('\n'.join(lines))
            if ENV_LOADER_AVAILABLE and get_env:
                try:
                    get_env().reload()
                except Exception as r:
                    logger.debug(f"Env reload after key save: {r}")
            return True
        except Exception as e:
            logger.error(f"Failed to update user env key {env_key}: {e}")
            return False

    def set_api_key(self, provider: str, key: str) -> bool:
        """
        Store an API key in the keyring.
        
        Args:
            provider: 'gemini', 'openai', 'anthropic', or 'custom'
            key: The API key value
            
        Returns:
            True if stored successfully
        """
        # Validate key is not empty
        if not key or not key.strip():
            logger.error(f"Cannot store empty API key for provider: {provider}")
            return False
        
        env_key = PROVIDER_TO_ENV_KEY.get(provider.lower())
        if not env_key:
            return False

        # Try keyring first (most secure)
        if KEYRING_AVAILABLE:
            try:
                key_name = self._get_key_name(provider)
                keyring.set_password(self.SERVICE_NAME, key_name, key.strip())
                logger.info(f"✓ Stored API key for provider: {provider} (in keyring)")
                self._update_json_key(provider, key)
                return True
            except Exception as e:
                logger.warning(f"Keyring storage failed for {provider}: {e}, trying .env fallback")

        # Fallback: write to ~/.config/nervaos/.env (matches env_loader priority)
        if self._upsert_user_env_key(env_key, key):
            logger.info(f"✓ Stored API key for provider: {provider} (in {USER_ENV_FILE})")
            self._update_json_key(provider, key)
            return True
        return False

    def set_env_key(self, env_key: str, value: str) -> bool:
        """Store a non-provider key (for example DEEPGRAM_API_KEY) in user .env."""
        if not env_key or not env_key.strip() or not value or not value.strip():
            return False
        return self._upsert_user_env_key(env_key.strip(), value.strip())

    def get_env_key(self, env_key: str) -> Optional[str]:
        """Read a key from env loader first, then from ~/.config/nervaos/.env directly."""
        if not env_key or not env_key.strip():
            return None
        key = env_key.strip()
        if ENV_LOADER_AVAILABLE and get_env:
            try:
                value = get_env().get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            except Exception as e:
                logger.debug(f"Env loader read failed for {key}: {e}")
        try:
            if USER_ENV_FILE.exists():
                for line in USER_ENV_FILE.read_text().splitlines():
                    if line.startswith(f"{key}="):
                        value = line.split("=", 1)[1].strip()
                        if value:
                            return value
        except Exception as e:
            logger.debug(f"Direct user env read failed for {key}: {e}")
        return None
    
    def get_api_key(self, provider: str) -> Optional[str]:
        """
        Retrieve an API key with fallback chain.
        
        Priority:
        1. Gnome Keyring (most secure)
        2. .env file (convenient for development)
        3. Environment variables
        
        Args:
            provider: 'gemini', 'openai', 'anthropic', or 'custom'
            
        Returns:
            The API key or None if not found
        """
        key = None
        
        # Priority 1: Try keyring first
        if KEYRING_AVAILABLE:
            try:
                key_name = self._get_key_name(provider)
                key = keyring.get_password(self.SERVICE_NAME, key_name)
                
                if key and key.strip():
                    logger.debug(f"✓ Retrieved API key from keyring for: {provider}")
                    return key.strip()
                    
            except Exception as e:
                logger.debug(f"Keyring lookup failed for {provider}: {e}")
        
        # Priority 2: .env / env loader
        if ENV_LOADER_AVAILABLE and env_get_api_key:
            try:
                key = env_get_api_key(provider)
                if key and key.strip():
                    logger.debug(f"✓ Retrieved API key from .env for: {provider}")
                    return key.strip()
            except Exception as e:
                logger.debug(f"Env loader failed for {provider}: {e}")

        # Priority 3: JSON config (~/.config/nervaos/config/api_keys.json) – user can fill manually
        env_key = PROVIDER_TO_ENV_KEY.get(provider.lower())
        if env_key:
            data = self._load_api_config()
            key = data.get(env_key)
            if isinstance(key, str) and key.strip():
                logger.debug(f"✓ Retrieved API key from api_keys.json for: {provider}")
                return key.strip()

        # Priority 4: Direct environment variable
        if env_key:
            import os
            key = os.environ.get(env_key)
            if key and key.strip():
                logger.debug(f"✓ Retrieved API key from environment for: {provider}")
                return key.strip()

        logger.debug(f"✗ No API key found for provider: {provider}")
        return None
    
    def delete_api_key(self, provider: str) -> bool:
        """
        Delete an API key from the keyring.
        
        Args:
            provider: 'gemini' or 'custom'
            
        Returns:
            True if deleted successfully
        """
        if not KEYRING_AVAILABLE:
            logger.error("Cannot delete key: keyring not available")
            return False
        
        try:
            key_name = self._get_key_name(provider)
            keyring.delete_password(self.SERVICE_NAME, key_name)
            logger.info(f"Deleted API key for provider: {provider}")
            return True
        except keyring.errors.PasswordDeleteError:
            logger.warning(f"No key to delete for provider: {provider}")
            return False
        except Exception as e:
            logger.error(f"Failed to delete API key: {e}")
            return False
    
    def has_api_key(self, provider: str) -> bool:
        """Check if an API key exists for the given provider"""
        return self.get_api_key(provider) is not None
    
    def _get_key_name(self, provider: str) -> str:
        """Map provider name to key name"""
        mapping = {
            'gemini': self.KEY_GEMINI,
            'openai': self.KEY_OPENAI,
            'anthropic': self.KEY_ANTHROPIC,
            'custom': self.KEY_CUSTOM,
            'license': self.KEY_LICENSE
        }
        return mapping.get(provider.lower(), f"{provider}_api_key")
    
    # ─────────────────────────────────────────────────────────────
    # License Management (for optional licensing system)
    # ─────────────────────────────────────────────────────────────
    
    def set_license_key(self, key: str) -> bool:
        """Store the product license key"""
        return self.set_api_key('license', key)
    
    def get_license_key(self) -> Optional[str]:
        """Retrieve the product license key"""
        return self.get_api_key('license')
    
    def has_license(self) -> bool:
        """Check if a license key is stored"""
        return self.has_api_key('license')
    
    # ─────────────────────────────────────────────────────────────
    # Utility Methods
    # ─────────────────────────────────────────────────────────────
    
    def get_all_configured_providers(self) -> list:
        """Get list of providers that have API keys configured"""
        providers = []
        
        # Check all supported providers
        for provider in ['gemini', 'openai', 'anthropic', 'custom']:
            if self.has_api_key(provider):
                providers.append(provider)
        
        return providers
    
    def is_configured(self) -> bool:
        """Check if at least one API provider is configured"""
        return len(self.get_all_configured_providers()) > 0


# ─────────────────────────────────────────────────────────────────
# CLI Helper for setting keys
# ─────────────────────────────────────────────────────────────────

def main():
    """CLI tool for managing NervaOS secrets"""
    import sys
    
    if len(sys.argv) < 3:
        print("Usage: python -m src.core.secrets <set|get|delete> <provider> [key]")
        print("Providers: gemini, custom, license")
        sys.exit(1)
    
    action = sys.argv[1]
    provider = sys.argv[2]
    
    secrets = SecretsManager()
    
    if action == 'set':
        if len(sys.argv) < 4:
            import getpass
            key = getpass.getpass(f"Enter {provider} API key: ")
        else:
            key = sys.argv[3]
        
        if secrets.set_api_key(provider, key):
            print(f"✓ API key stored for {provider}")
        else:
            print(f"✗ Failed to store API key")
            sys.exit(1)
    
    elif action == 'get':
        key = secrets.get_api_key(provider)
        if key:
            # Mask the key for display
            masked = key[:4] + '*' * (len(key) - 8) + key[-4:]
            print(f"{provider}: {masked}")
        else:
            print(f"No API key found for {provider}")
    
    elif action == 'delete':
        if secrets.delete_api_key(provider):
            print(f"✓ API key deleted for {provider}")
        else:
            print(f"✗ Failed to delete API key")
    
    else:
        print(f"Unknown action: {action}")
        sys.exit(1)


if __name__ == '__main__':
    main()
