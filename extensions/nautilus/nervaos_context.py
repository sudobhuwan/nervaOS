#!/usr/bin/env python3
"""
NervaOS Nautilus/Nemo Extension - Context Menu Integration

Installation:
  cp nervaos_context.py ~/.local/share/nautilus-python/extensions/
  nautilus -q  # Restart file manager

Requires:
  sudo apt install python3-nautilus
"""

import os
import subprocess
from gi.repository import Nautilus, GObject
from typing import List


class NervaOSMenuProvider(GObject.GObject, Nautilus.MenuProvider):
    """Adds NervaOS actions to file manager context menu"""
    
    def get_file_items(self, files: List[Nautilus.FileInfo]) -> List[Nautilus.MenuItem]:
        """Called when user right-clicks on file(s)"""
        
        if len(files) != 1:
            # Only show for single file selection for now
            return []
        
        file_info = files[0]
        file_path = file_info.get_uri().replace('file://', '')
        
        # Create main menu item
        menu = Nautilus.MenuItem(
            name='NervaOSMenu::Root',
            label='🤖 NervaOS',
            tip='AI-powered file operations'
        )
        
        # Create submenu
        submenu = Nautilus.Menu()
        menu.set_submenu(submenu)
        
        # Add actions based on file type
        if file_info.get_mime_type().startswith('text/'):
            # Text files
            summarize = self._create_menu_item(
                'Summarize', 'document-properties-symbolic',
                lambda: self._ask_nerva(f"Summarize this file: {file_path}")
            )
            submenu.append_item(summarize)
            
            improve = self._create_menu_item(
                'Improve Writing', 'accessories-text-editor-symbolic',
                lambda: self._ask_nerva(f"Improve the writing in: {file_path}")
            )
            submenu.append_item(improve)
        
        elif file_info.get_mime_type().startswith('image/'):
            # Images
            describe = self._create_menu_item(
                'Describe Image', 'image-x-generic-symbolic',
                lambda: self._ask_nerva(f"Describe this image: {file_path}")
            )
            submenu.append_item(describe)
        
        elif file_info.is_directory():
            # Directories
            organize = self._create_menu_item(
                'Organize Files', 'folder-symbolic',
                lambda: self._organize_folder(file_path)
            )
            submenu.append_item(organize)
            
            analyze = self._create_menu_item(
                'Analyze Disk Usage', 'drive-harddisk-symbolic',
                lambda: self._ask_nerva(f"Analyze disk usage in: {file_path}")
            )
            submenu.append_item(analyze)
        
        # Universal actions
        separator = Nautilus.MenuItem(name='NervaOSMenu::Sep1', label='─' * 20)
        submenu.append_item(separator)
        
        ask_about = self._create_menu_item(
            'Ask About This File', 'dialog-question-symbolic',
            lambda: self._open_chat_with_file(file_path)
        )
        submenu.append_item(ask_about)
        
        return [menu]
    
    def _create_menu_item(self, label: str, icon: str, callback) -> Nautilus.MenuItem:
        """Helper to create menu item with icon"""
        item = Nautilus.MenuItem(
            name=f'NervaOSMenu::{label.replace(" ", "")}',
            label=label,
            icon=icon
        )
        item.connect('activate', lambda x: callback())
        return item
    
    def _ask_nerva(self, query: str):
        """Send query to NervaOS daemon via DBus"""
        try:
            subprocess.Popen([
                'dbus-send',
                '--session',
                '--type=method_call',
                '--dest=com.nervaos.daemon',
                '/com/nervaos/daemon',
                'com.nervaos.daemon.AskAI',
                f'string:{query}'
            ])
        except Exception as e:
            self._show_error(f"Failed to contact NervaOS: {e}")
    
    def _organize_folder(self, path: str):
        """Organize folder using NervaOS"""
        query = f"organize {path}"
        self._ask_nerva(query)
    
    def _open_chat_with_file(self, path: str):
        """Open NervaOS UI with file context"""
        try:
            subprocess.Popen(['nerva-ui', '--file', path])
        except Exception as e:
            self._show_error(f"Failed to open NervaOS: {e}")
    
    def _show_error(self, message: str):
        """Show error notification"""
        subprocess.run([
            'notify-send',
            'NervaOS Error',
            message,
            '--icon=dialog-error'
        ])
