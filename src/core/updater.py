"""
NervaOS Auto-Update System

Checks for updates and applies them:
- Version comparison
- Download from release server
- Safe update with rollback
"""

import os
import sys
import json
import shutil
import tempfile
import logging
import asyncio
from pathlib import Path
from typing import Optional, Tuple, Dict
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger('nerva-updater')


@dataclass
class UpdateInfo:
    """Information about an available update"""
    version: str
    release_date: str
    download_url: str
    changelog: str
    size_bytes: int
    checksum: str  # SHA256


class AutoUpdater:
    """
    Auto-update system for NervaOS.
    
    Handles:
    - Version checking against release server
    - Download with progress
    - Backup current version
    - Apply update
    - Rollback on failure
    """
    
    # Update server URL (change for production)
    UPDATE_SERVER = "https://updates.nervaos.com"
    
    # Installation directory
    INSTALL_DIR = Path("/opt/nervaos")
    BACKUP_DIR = Path.home() / ".config" / "nervaos" / "backups"
    
    def __init__(self, current_version: str = "1.0.0"):
        self.current_version = current_version
        self.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    
    async def check_for_updates(self) -> Optional[UpdateInfo]:
        """
        Check the update server for new versions.
        
        Returns:
            UpdateInfo if update available, None otherwise
        """
        try:
            import httpx
            
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(
                    f"{self.UPDATE_SERVER}/api/releases/latest"
                )
                
                if response.status_code != 200:
                    logger.warning(f"Update check failed: {response.status_code}")
                    return None
                
                data = response.json()
                
                # Compare versions
                if self._is_newer_version(data['version'], self.current_version):
                    return UpdateInfo(
                        version=data['version'],
                        release_date=data.get('release_date', ''),
                        download_url=data['download_url'],
                        changelog=data.get('changelog', ''),
                        size_bytes=data.get('size_bytes', 0),
                        checksum=data.get('checksum', '')
                    )
                
                return None
                
        except Exception as e:
            logger.error(f"Update check error: {e}")
            return None
    
    def _is_newer_version(self, new: str, current: str) -> bool:
        """Compare version strings"""
        try:
            def parse_version(v: str) -> tuple:
                return tuple(map(int, v.split('.')))
            
            return parse_version(new) > parse_version(current)
        except Exception:
            return False
    
    async def download_update(
        self, 
        update: UpdateInfo,
        progress_callback: Optional[callable] = None
    ) -> Optional[Path]:
        """
        Download an update package.
        
        Args:
            update: Update information
            progress_callback: Called with (downloaded, total) bytes
            
        Returns:
            Path to downloaded file, or None on failure
        """
        try:
            import httpx
            import hashlib
            
            download_path = Path(tempfile.gettempdir()) / f"nervaos-{update.version}.tar.gz"
            
            async with httpx.AsyncClient(timeout=300) as client:
                async with client.stream('GET', update.download_url) as response:
                    if response.status_code != 200:
                        logger.error(f"Download failed: {response.status_code}")
                        return None
                    
                    total = int(response.headers.get('content-length', 0))
                    downloaded = 0
                    hasher = hashlib.sha256()
                    
                    with open(download_path, 'wb') as f:
                        async for chunk in response.aiter_bytes(chunk_size=8192):
                            f.write(chunk)
                            hasher.update(chunk)
                            downloaded += len(chunk)
                            
                            if progress_callback:
                                progress_callback(downloaded, total)
            
            # Verify checksum
            if update.checksum:
                actual_hash = hasher.hexdigest()
                if actual_hash != update.checksum:
                    logger.error(f"Checksum mismatch: {actual_hash} != {update.checksum}")
                    download_path.unlink()
                    return None
            
            logger.info(f"Downloaded update to {download_path}")
            return download_path
            
        except Exception as e:
            logger.error(f"Download error: {e}")
            return None
    
    def backup_current_version(self) -> Optional[Path]:
        """
        Backup the current installation.
        
        Returns:
            Path to backup, or None on failure
        """
        try:
            if not self.INSTALL_DIR.exists():
                logger.warning("No installation to backup")
                return None
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_path = self.BACKUP_DIR / f"nervaos_{self.current_version}_{timestamp}"
            
            shutil.copytree(self.INSTALL_DIR, backup_path)
            
            logger.info(f"Backed up to {backup_path}")
            return backup_path
            
        except Exception as e:
            logger.error(f"Backup error: {e}")
            return None
    
    def apply_update(self, update_path: Path) -> bool:
        """
        Apply an update package.
        
        Args:
            update_path: Path to the update tarball
            
        Returns:
            True if update applied successfully
        """
        try:
            import tarfile
            
            # Extract to temp directory first
            extract_dir = Path(tempfile.mkdtemp())
            
            with tarfile.open(update_path, 'r:gz') as tar:
                tar.extractall(extract_dir)
            
            # Find the extracted content
            contents = list(extract_dir.iterdir())
            if len(contents) == 1 and contents[0].is_dir():
                source_dir = contents[0]
            else:
                source_dir = extract_dir
            
            # Replace installation
            if self.INSTALL_DIR.exists():
                # Keep config and venv
                config_backup = None
                venv_backup = None
                
                config_dir = self.INSTALL_DIR / "config"
                venv_dir = self.INSTALL_DIR / "venv"
                
                if config_dir.exists():
                    config_backup = Path(tempfile.mkdtemp()) / "config"
                    shutil.move(str(config_dir), str(config_backup))
                
                if venv_dir.exists():
                    venv_backup = Path(tempfile.mkdtemp()) / "venv"
                    shutil.move(str(venv_dir), str(venv_backup))
                
                # Remove old installation
                shutil.rmtree(self.INSTALL_DIR)
            
            # Install new version
            shutil.copytree(source_dir, self.INSTALL_DIR)
            
            # Restore config and venv
            if config_backup and config_backup.exists():
                shutil.move(str(config_backup), str(self.INSTALL_DIR / "config"))
            
            if venv_backup and venv_backup.exists():
                shutil.move(str(venv_backup), str(self.INSTALL_DIR / "venv"))
            
            # Cleanup
            shutil.rmtree(extract_dir)
            update_path.unlink()
            
            logger.info("Update applied successfully")
            return True
            
        except Exception as e:
            logger.error(f"Update apply error: {e}")
            return False
    
    def rollback(self, backup_path: Path) -> bool:
        """
        Rollback to a previous version.
        
        Args:
            backup_path: Path to the backup to restore
            
        Returns:
            True if rollback successful
        """
        try:
            if not backup_path.exists():
                logger.error(f"Backup not found: {backup_path}")
                return False
            
            # Remove current installation
            if self.INSTALL_DIR.exists():
                shutil.rmtree(self.INSTALL_DIR)
            
            # Restore backup
            shutil.copytree(backup_path, self.INSTALL_DIR)
            
            logger.info(f"Rolled back from {backup_path}")
            return True
            
        except Exception as e:
            logger.error(f"Rollback error: {e}")
            return False
    
    def list_backups(self) -> list:
        """List available backups"""
        backups = []
        
        for item in self.BACKUP_DIR.iterdir():
            if item.is_dir() and item.name.startswith('nervaos_'):
                parts = item.name.split('_')
                if len(parts) >= 2:
                    backups.append({
                        'path': item,
                        'version': parts[1],
                        'timestamp': '_'.join(parts[2:]) if len(parts) > 2 else ''
                    })
        
        return sorted(backups, key=lambda x: x['timestamp'], reverse=True)
    
    def cleanup_old_backups(self, keep: int = 3):
        """Remove old backups, keeping the most recent ones"""
        backups = self.list_backups()
        
        for backup in backups[keep:]:
            try:
                shutil.rmtree(backup['path'])
                logger.info(f"Removed old backup: {backup['path']}")
            except Exception as e:
                logger.error(f"Failed to remove backup: {e}")


async def check_and_notify_updates():
    """Check for updates and notify user if available"""
    from .notifications import get_notification_manager
    
    updater = AutoUpdater()
    update = await updater.check_for_updates()
    
    if update:
        notifier = get_notification_manager()
        notifier.show(
            title="NervaOS Update Available",
            message=f"Version {update.version} is available. Open settings to update.",
            icon="software-update-available-symbolic"
        )
        return update
    
    return None
