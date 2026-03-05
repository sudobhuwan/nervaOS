"""
NervaOS Safety Manager - File operation safety and backup management

This module ensures all file operations are:
1. SAFE - Only user-owned files in allowed paths
2. REVERSIBLE - Auto-backup before any modification
3. ATOMIC - Write to temp file, then rename
4. TRACKED - All operations logged in SQLite for undo
"""

import logging
import os
import difflib
import hashlib
import sqlite3
import tempfile
import shutil
from datetime import datetime
from pathlib import Path
from typing import Tuple, Optional, Dict, Any
from dataclasses import dataclass

from .paths import ensure_data_dir
from .settings import get_settings_manager

logger = logging.getLogger('nerva-safety')


@dataclass
class PendingEdit:
    """Represents a file edit waiting for user approval"""
    operation_id: str
    file_path: str
    original_content: str
    new_content: str
    created_at: datetime


class SafetyManager:
    """
    Manages safe file operations with automatic backups and undo.
    
    BLACKLIST: These paths are NEVER touched, even if user-owned:
    - /etc/, /usr/, /bin/, /sbin/, /boot/, /sys/, /proc/, /dev/
    - Hidden files (starting with .) unless explicitly named
    
    WHITELIST: Only files owned by current user in:
    - /home/user/
    - /tmp/ (with warnings)
    """
    
    # Absolute blacklist - never touch these
    BLACKLISTED_PATHS = [
        '/etc', '/usr', '/bin', '/sbin', '/boot',
        '/sys', '/proc', '/dev', '/lib', '/lib64',
        '/root', '/var'
    ]
    
    # Max file size we'll edit (10MB default)
    MAX_FILE_SIZE = 10 * 1024 * 1024
    
    _LEGACY_DB = Path.home() / '.config' / 'nervaos' / 'operations.db'
    _LEGACY_BACKUPS = Path.home() / '.config' / 'nervaos' / 'backups'
    
    def __init__(self):
        data_dir = ensure_data_dir()
        self._db_path = data_dir / 'operations.db'
        self._backup_dir = data_dir / 'backups'
        self._pending_edits: Dict[str, PendingEdit] = {}
        self._init_database()
    
    def _init_database(self):
        """Initialize the SQLite database for operation tracking"""
        self._backup_dir.mkdir(parents=True, exist_ok=True)
        # Migrate legacy DB if present and new one doesn't exist
        if not self._db_path.exists() and self._LEGACY_DB.exists():
            try:
                shutil.copy2(str(self._LEGACY_DB), str(self._db_path))
                logger.info("Migrated operations DB from %s to %s", self._LEGACY_DB, self._db_path)
            except OSError as e:
                logger.warning("Could not migrate legacy operations DB: %s", e)
        
        conn = sqlite3.connect(str(self._db_path))
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS operations (
                id TEXT PRIMARY KEY,
                file_path TEXT NOT NULL,
                operation_type TEXT NOT NULL,
                backup_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                applied_at TIMESTAMP,
                undone_at TIMESTAMP,
                status TEXT DEFAULT 'pending'
            )
        ''')
        
        conn.commit()
        conn.close()
    
    # ─────────────────────────────────────────────────────────────
    # Path Validation
    # ─────────────────────────────────────────────────────────────
    
    def validate_path(self, path: str) -> Tuple[bool, str]:
        """
        Validate if a path is safe to modify.
        
        Returns:
            (is_safe, reason)
        """
        try:
            # Convert to absolute path
            abs_path = Path(path).resolve()
            path_str = str(abs_path)
            
            # Check blacklist
            for blacklisted in self.BLACKLISTED_PATHS:
                if path_str.startswith(blacklisted):
                    return False, f"Path '{blacklisted}' is protected and cannot be modified"
            
            # Check if it's a hidden file (unless in user's home)
            if abs_path.name.startswith('.'):
                # Allow hidden files only if explicitly in a project directory
                if not self._is_in_project_context(abs_path):
                    return False, "Hidden files require explicit user approval"
            
            # Check file existence for edits
            if abs_path.exists():
                # Check ownership
                if not self._is_user_owned(abs_path):
                    return False, "File is not owned by current user"
                
                # Check size
                if abs_path.stat().st_size > self.MAX_FILE_SIZE:
                    size_mb = abs_path.stat().st_size / (1024 * 1024)
                    return False, f"File too large ({size_mb:.1f}MB > 10MB limit)"
                
                # Check if it's a binary file
                if self._is_binary_file(abs_path):
                    return False, "Binary files cannot be edited"
            
            # Check if parent directory is writable
            parent = abs_path.parent
            if parent.exists() and not os.access(parent, os.W_OK):
                return False, "Parent directory is not writable"
            
            return True, "Path is safe"
            
        except Exception as e:
            return False, f"Validation error: {str(e)}"
    
    def _is_user_owned(self, path: Path) -> bool:
        """Check if file is owned by current user"""
        try:
            return path.stat().st_uid == os.getuid()
        except (OSError, AttributeError):
            return False
    
    def _is_in_project_context(self, path: Path) -> bool:
        """Check if path is in a typical project directory"""
        # Look for project markers
        project_markers = ['.git', 'package.json', 'setup.py', 'Cargo.toml', 'go.mod']
        
        current = path.parent
        for _ in range(5):  # Look up to 5 levels
            for marker in project_markers:
                if (current / marker).exists():
                    return True
            if current == current.parent:
                break
            current = current.parent
        
        return False
    
    def _is_binary_file(self, path: Path) -> bool:
        """Check if file appears to be binary"""
        try:
            with open(path, 'rb') as f:
                chunk = f.read(8192)
                # Check for null bytes (common in binary files)
                if b'\x00' in chunk:
                    return True
            return False
        except Exception:
            return True
    
    # ─────────────────────────────────────────────────────────────
    # Diff Generation
    # ─────────────────────────────────────────────────────────────
    
    def generate_diff(self, original: str, modified: str, filename: str = "file") -> str:
        """
        Generate a unified diff between original and modified content.
        """
        original_lines = original.splitlines(keepends=True)
        modified_lines = modified.splitlines(keepends=True)
        
        diff = difflib.unified_diff(
            original_lines,
            modified_lines,
            fromfile=f"a/{filename}",
            tofile=f"b/{filename}",
            lineterm=''
        )
        
        return ''.join(diff)
    
    def generate_html_diff(self, original: str, modified: str) -> str:
        """Generate an HTML diff for UI display"""
        differ = difflib.HtmlDiff()
        return differ.make_table(
            original.splitlines(),
            modified.splitlines(),
            fromdesc='Original',
            todesc='Modified',
            context=True
        )
    
    # ─────────────────────────────────────────────────────────────
    # Pending Edits
    # ─────────────────────────────────────────────────────────────
    
    async def store_pending_edit(
        self, 
        file_path: str, 
        original_content: str, 
        new_content: str
    ) -> str:
        """
        Store a pending edit for user approval.
        Returns the operation_id.
        """
        # Generate unique operation ID
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        content_hash = hashlib.md5(new_content.encode()).hexdigest()[:8]
        operation_id = f"{timestamp}_{content_hash}"
        
        # Store in memory
        self._pending_edits[operation_id] = PendingEdit(
            operation_id=operation_id,
            file_path=file_path,
            original_content=original_content,
            new_content=new_content,
            created_at=datetime.now()
        )
        
        # Log to database
        conn = sqlite3.connect(str(self._db_path))
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO operations (id, file_path, operation_type, status)
            VALUES (?, ?, 'edit', 'pending')
        ''', (operation_id, file_path))
        conn.commit()
        conn.close()
        
        return operation_id
    
    async def apply_pending_edit(self, operation_id: str) -> bool:
        """
        Apply a pending edit after user approval.
        
        This:
        1. Creates a backup of the original file
        2. Writes new content atomically
        3. Records the operation
        """
        if operation_id not in self._pending_edits:
            return False
        
        edit = self._pending_edits[operation_id]
        file_path = Path(edit.file_path)
        
        # Create backup
        backup_path = await self._create_backup(file_path, edit.original_content)
        
        # Write atomically
        success = await self._atomic_write(file_path, edit.new_content)
        
        if success:
            # Update database
            conn = sqlite3.connect(str(self._db_path))
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE operations 
                SET backup_path = ?, applied_at = CURRENT_TIMESTAMP, status = 'applied'
                WHERE id = ?
            ''', (str(backup_path), operation_id))
            conn.commit()
            conn.close()
            
            # Remove from pending
            del self._pending_edits[operation_id]
        
        return success
    
    async def _create_backup(self, file_path: Path, content: str) -> Path:
        """Create a backup of the file content"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_name = f"{file_path.name}.bak_{timestamp}"
        backup_path = self._backup_dir / backup_name
        
        backup_path.write_text(content)
        return backup_path
    
    async def _atomic_write(self, file_path: Path, content: str) -> bool:
        """Write content to file atomically using temp file + rename"""
        try:
            # Write to temp file in same directory (for same filesystem)
            temp_fd, temp_path = tempfile.mkstemp(
                dir=file_path.parent,
                prefix='.nerva_tmp_'
            )
            
            try:
                os.write(temp_fd, content.encode('utf-8'))
                os.close(temp_fd)
                
                # Preserve original permissions if file exists
                if file_path.exists():
                    original_mode = file_path.stat().st_mode
                    os.chmod(temp_path, original_mode)
                
                # Atomic rename
                shutil.move(temp_path, file_path)
                return True
                
            except Exception:
                # Clean up temp file on error
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
                raise
                
        except Exception as e:
            print(f"Atomic write failed: {e}")
            return False
    
    # ─────────────────────────────────────────────────────────────
    # Undo Operations
    # ─────────────────────────────────────────────────────────────
    
    async def undo_edit(self, operation_id: str) -> bool:
        """Revert a file to its backup state"""
        conn = sqlite3.connect(str(self._db_path))
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT file_path, backup_path FROM operations 
            WHERE id = ? AND status = 'applied'
        ''', (operation_id,))
        
        row = cursor.fetchone()
        if not row:
            conn.close()
            return False
        
        file_path, backup_path = row
        
        try:
            # Read backup content
            backup_content = Path(backup_path).read_text()
            
            # Restore it
            success = await self._atomic_write(Path(file_path), backup_content)
            
            if success:
                cursor.execute('''
                    UPDATE operations 
                    SET undone_at = CURRENT_TIMESTAMP, status = 'undone'
                    WHERE id = ?
                ''', (operation_id,))
                conn.commit()
            
            conn.close()
            return success
            
        except Exception as e:
            conn.close()
            print(f"Undo failed: {e}")
            return False
    
    async def get_recent_operations(self, limit: int = 10) -> list:
        """Get recent file operations for history display"""
        conn = sqlite3.connect(str(self._db_path))
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, file_path, operation_type, status, created_at, applied_at
            FROM operations
            ORDER BY created_at DESC
            LIMIT ?
        ''', (limit,))
        
        operations = []
        for row in cursor.fetchall():
            operations.append({
                'id': row[0],
                'file_path': row[1],
                'type': row[2],
                'status': row[3],
                'created_at': row[4],
                'applied_at': row[5]
            })
        
        conn.close()
        return operations
    
    # ─────────────────────────────────────────────────────────────
    # Safe Command Execution
    # ─────────────────────────────────────────────────────────────
    
    # Commands that are safe to execute (read-only, informational)
    SAFE_COMMANDS = [
        # System info
        'df', 'du', 'free', 'uptime', 'uname', 'hostname', 'whoami', 'id',
        'lsb_release', 'cat /etc/os-release', 'lscpu', 'lsmem', 'lsblk',
        # Process info
        'ps', 'top -bn1', 'htop', 'pgrep', 'pidof',
        # File listing (no modification)
        'ls', 'find', 'locate', 'which', 'whereis', 'file', 'stat', 'wc',
        'head', 'tail', 'cat', 'less', 'more', 'grep', 'awk', 'sed',
        # Network info
        'ip', 'ifconfig', 'netstat', 'ss', 'ping', 'host', 'dig', 'nslookup',
        'nmcli', 'iwgetid', 'iwconfig', 'rfkill', 'resolvectl',
        'curl', 'wget', 'traceroute', 'tracepath', 'mtr',
        # Docker (read-only)
        'docker ps', 'docker images', 'docker stats', 'docker info',
        'docker container ls', 'docker image ls', 'docker volume ls',
        'docker network ls', 'docker compose ps',
        # Git (read-only)  
        'git status', 'git log', 'git branch', 'git remote', 'git diff',
        'git show', 'git ls-files',
        # Package info (no install/remove)
        'apt list', 'dpkg -l', 'pip list', 'pip show', 'npm list',
        # Misc read-only
        'date', 'cal', 'env', 'printenv', 'echo', 'pwd', 'tree',
        'uname', 'hostname', 'hostnamectl', 'lsb_release', 'whoami', 'id',
        'journalctl', 'free', 'uptime', 'top', 'ps', 'du', 'df',
        # Application launchers (safe - just opens apps)
        'xdg-open', 'gnome-open', 'gio open',
        'google-chrome', 'chromium-browser', 'firefox', 'brave-browser',
        'code', 'cursor', 'gedit', 'xed', 'sublime_text',
        'vlc', 'mpv', 'spotify', 'rhythmbox',
        'nemo', 'nautilus', 'thunar',  # File managers
        'gnome-terminal', 'tilix', 'terminator', 'konsole',
        'libreoffice', 'gimp', 'inkscape', 'blender',
        'discord', 'slack', 'telegram-desktop',
    ]
    
    # Commands that are NEVER allowed
    BLOCKED_COMMANDS = [
        # Explicit delete/removal/destructive operations
        'rm ', 'rmdir', 'shred ', 'wipefs ', 'mkfs', 'fdisk', 'parted',
        'apt remove', 'apt purge', 'apt-get remove', 'apt-get purge',
        'pip uninstall', 'npm uninstall',
        'docker rm', 'docker rmi', 'docker image rm', 'docker container rm',
    ]

    # Potentially risky but useful actions (allowed with mode-based policy)
    RISKY_COMMANDS = [
        'systemctl ', 'service ', 'ufw ', 'iptables ', 'docker exec', 'docker compose up',
        'mount ', 'umount ', 'pkexec ', 'kill ', 'killall ', 'pkill ', 'chmod ', 'chown ',
        'cp ', 'mv ', 'truncate ', 'tee ', 'dd ',
    ]
    
    async def safe_execute_command(self, command: str, timeout: int = 30) -> Tuple[bool, str]:
        """
        Execute a command safely if it's in the allowed list.
        
        Returns:
            (success, output_or_error)
        """
        import subprocess
        import shlex
        
        # Normalize command
        raw_cmd = command.strip()
        cmd_lower = raw_cmd.lower()
        settings = get_settings_manager().load()
        mode = getattr(settings, 'command_mode', 'balanced').lower()

        # Explicit user confirmation prefix in balanced mode.
        # Example: "confirm: systemctl --user restart nerva-service"
        confirmed = False
        if cmd_lower.startswith("confirm:"):
            confirmed = True
            raw_cmd = raw_cmd[len("confirm:"):].strip()
            cmd_lower = raw_cmd.lower()
        
        # Check for blocked patterns
        for blocked in self.BLOCKED_COMMANDS:
            if blocked in cmd_lower:
                return False, f"Command blocked for safety: contains '{blocked}'"

        # Safe mode: strict allow-list only.
        if mode == 'safe':
            for safe_cmd in self.SAFE_COMMANDS:
                if cmd_lower.startswith(safe_cmd.lower()):
                    break
            else:
                return False, "Command blocked in Safe mode (not in allow-list)."

        # Balanced mode: broad access, but risky commands require explicit confirmation.
        if mode == 'balanced':
            risky_hit = next((r for r in self.RISKY_COMMANDS if r in cmd_lower), None)
            if risky_hit and not confirmed:
                return False, (
                    f"Risky command detected ('{risky_hit.strip()}'). "
                    "Re-send with `confirm:` prefix to proceed."
                )
        
        try:
            # Execute command with timeout
            result = subprocess.run(
                raw_cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(Path.home())  # Run from home directory
            )
            
            output = result.stdout
            if result.stderr:
                output += f"\n[stderr]: {result.stderr}"
            
            if result.returncode != 0:
                return False, f"Command exited with code {result.returncode}:\n{output}"
            
            # Limit output size
            if len(output) > 5000:
                output = output[:5000] + "\n... (output truncated)"
            
            return True, output
            
        except subprocess.TimeoutExpired:
            return False, f"Command timed out after {timeout} seconds"
        except Exception as e:
            return False, f"Command execution error: {str(e)}"
    
    def is_command_safe(self, command: str) -> Tuple[bool, str]:
        """Check if a command would be allowed without executing it"""
        raw_cmd = command.strip()
        cmd_lower = raw_cmd.lower()
        settings = get_settings_manager().load()
        mode = getattr(settings, 'command_mode', 'balanced').lower()
        confirmed = False
        if cmd_lower.startswith("confirm:"):
            confirmed = True
            raw_cmd = raw_cmd[len("confirm:"):].strip()
            cmd_lower = raw_cmd.lower()
        
        for blocked in self.BLOCKED_COMMANDS:
            if blocked in cmd_lower:
                return False, f"Contains blocked pattern: '{blocked}'"

        if mode == 'safe':
            for safe_cmd in self.SAFE_COMMANDS:
                if cmd_lower.startswith(safe_cmd.lower()):
                    return True, "Command allowed in Safe mode"
            return False, "Blocked in Safe mode (not in allow-list)"

        if mode == 'balanced':
            risky_hit = next((r for r in self.RISKY_COMMANDS if r in cmd_lower), None)
            if risky_hit and not confirmed:
                return False, f"Requires explicit confirmation (prefix with `confirm:`). Risk: '{risky_hit.strip()}'"

        return True, "Command allowed"
