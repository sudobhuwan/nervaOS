"""
NervaOS Client - License Verification Module

This module runs on the client side to:
- Generate hardware ID (HWID)
- Activate licenses
- Validate licenses at startup
- Handle offline grace periods
"""

import os
import hashlib
import platform
import subprocess
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Tuple
import json

logger = logging.getLogger('nerva-license')


class LicenseManager:
    """
    Client-side license management.
    
    Handles:
    - Hardware ID generation
    - License activation with server
    - Offline validation with cached data
    - Grace period for network issues
    """
    
    # License server URL (change for production)
    SERVER_URL = "https://license.nervaos.com"
    
    # Cache location
    CACHE_DIR = Path.home() / '.config' / 'nervaos'
    CACHE_FILE = CACHE_DIR / '.license_cache'
    
    # Offline grace period (days)
    GRACE_PERIOD_DAYS = 7
    
    def __init__(self, server_url: Optional[str] = None):
        if server_url:
            self.SERVER_URL = server_url
        
        self.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self._hwid: Optional[str] = None
    
    def get_hwid(self) -> str:
        """
        Generate a unique hardware identifier.
        
        Combines:
        - Machine ID (from /etc/machine-id)
        - CPU info
        - MAC address
        """
        if self._hwid:
            return self._hwid
        
        components = []
        
        # Machine ID (Linux)
        machine_id_path = Path('/etc/machine-id')
        if machine_id_path.exists():
            components.append(machine_id_path.read_text().strip())
        
        # CPU info
        try:
            with open('/proc/cpuinfo', 'r') as f:
                for line in f:
                    if 'model name' in line or 'cpu cores' in line:
                        components.append(line.strip())
                        break
        except Exception:
            pass
        
        # Hostname + username (for uniqueness)
        components.append(platform.node())
        components.append(os.getenv('USER', 'unknown'))
        
        # Get primary MAC address
        try:
            result = subprocess.run(
                ['cat', '/sys/class/net/$(ip route show default | awk \'/default/ {print $5}\')/address'],
                capture_output=True, text=True, shell=True
            )
            if result.returncode == 0:
                components.append(result.stdout.strip())
        except Exception:
            pass
        
        # Create hash
        combined = '|'.join(components)
        self._hwid = hashlib.sha256(combined.encode()).hexdigest()[:32]
        
        return self._hwid
    
    def get_machine_info(self) -> dict:
        """Get machine information for activation"""
        return {
            "machine_name": platform.node(),
            "os_info": f"{platform.system()} {platform.release()}"
        }
    
    async def activate(self, license_key: str) -> Tuple[bool, str]:
        """
        Activate a license key on this device.
        
        Returns:
            Tuple of (success, message)
        """
        try:
            import httpx
            
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{self.SERVER_URL}/api/licenses/activate",
                    json={
                        "license_key": license_key,
                        "hwid": self.get_hwid(),
                        **self.get_machine_info()
                    }
                )
                
                data = response.json()
                
                if data.get('success'):
                    # Cache the license data
                    self._cache_license({
                        'license_key': license_key,
                        'license_type': data.get('license_type'),
                        'expires_at': data.get('expires_at'),
                        'activated_at': datetime.utcnow().isoformat(),
                        'last_validated': datetime.utcnow().isoformat()
                    })
                    
                    return True, data.get('message', 'Activated successfully')
                else:
                    return False, data.get('message', 'Activation failed')
                    
        except Exception as e:
            logger.error(f"Activation error: {e}")
            return False, f"Network error: {e}"
    
    async def validate(self) -> Tuple[bool, str]:
        """
        Validate the current license.
        
        Uses cached data if network is unavailable (grace period).
        """
        cached = self._get_cached_license()
        
        if not cached:
            return False, "No license found. Please activate."
        
        try:
            import httpx
            
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(
                    f"{self.SERVER_URL}/api/licenses/validate",
                    json={
                        "license_key": cached['license_key'],
                        "hwid": self.get_hwid()
                    }
                )
                
                data = response.json()
                
                if data.get('valid'):
                    # Update cache
                    cached['last_validated'] = datetime.utcnow().isoformat()
                    self._cache_license(cached)
                    return True, "License valid"
                else:
                    # Clear cache if explicitly invalid
                    self._clear_cache()
                    return False, data.get('message', 'License invalid')
                    
        except Exception as e:
            logger.warning(f"Validation network error: {e}, checking grace period")
            
            # Check grace period
            return self._check_grace_period(cached)
    
    def _check_grace_period(self, cached: dict) -> Tuple[bool, str]:
        """Check if we're within the offline grace period"""
        try:
            last_validated = datetime.fromisoformat(cached['last_validated'])
            grace_end = last_validated + timedelta(days=self.GRACE_PERIOD_DAYS)
            
            if datetime.utcnow() < grace_end:
                days_left = (grace_end - datetime.utcnow()).days
                return True, f"Offline mode ({days_left} days remaining)"
            else:
                return False, "Grace period expired. Please connect to internet."
                
        except Exception:
            return False, "Cannot validate license. Please connect to internet."
    
    def _cache_license(self, data: dict):
        """Cache license data locally"""
        try:
            # Encrypt/obfuscate in production
            with open(self.CACHE_FILE, 'w') as f:
                json.dump(data, f)
            
            # Make file readable only by owner
            self.CACHE_FILE.chmod(0o600)
            
        except Exception as e:
            logger.error(f"Failed to cache license: {e}")
    
    def _get_cached_license(self) -> Optional[dict]:
        """Get cached license data"""
        try:
            if self.CACHE_FILE.exists():
                with open(self.CACHE_FILE, 'r') as f:
                    return json.load(f)
        except Exception:
            pass
        return None
    
    def _clear_cache(self):
        """Clear cached license data"""
        try:
            if self.CACHE_FILE.exists():
                self.CACHE_FILE.unlink()
        except Exception:
            pass
    
    def get_license_info(self) -> Optional[dict]:
        """Get current license information"""
        return self._get_cached_license()
    
    def is_licensed(self) -> bool:
        """Quick check if a license is cached"""
        return self.CACHE_FILE.exists()


# Convenience functions

async def check_license() -> Tuple[bool, str]:
    """Check if the current license is valid"""
    manager = LicenseManager()
    
    if not manager.is_licensed():
        return False, "No license found"
    
    return await manager.validate()


async def activate_license(key: str) -> Tuple[bool, str]:
    """Activate a new license key"""
    manager = LicenseManager()
    return await manager.activate(key)


def get_hwid() -> str:
    """Get the hardware ID for this machine"""
    manager = LicenseManager()
    return manager.get_hwid()
