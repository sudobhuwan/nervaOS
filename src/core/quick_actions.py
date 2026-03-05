"""
NervaOS Quick Actions - System control shortcuts
Provides quick access to common system actions via right-click menu.
"""

import logging
import subprocess
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger('nerva-quick-actions')


class QuickActions:
    """Handles system quick actions"""
    
    def __init__(self):
        self.screenshot_dir = Path.home() / "Pictures" / "Screenshots"
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        self.notes_dir = Path.home() / "Documents" / "NervaOS" / "QuickNotes"
        self.notes_dir.mkdir(parents=True, exist_ok=True)
        
        # Check available tools
        self.screenshot_tool = self._detect_screenshot_tool()
        self.screen_recorder = self._detect_screen_recorder()
    
    def _detect_screenshot_tool(self) -> str:
        """Detect which screenshot tool is available"""
        tools = ['gnome-screenshot', 'scrot', 'spectacle', 'flameshot']
        for tool in tools:
            try:
                subprocess.run(['which', tool], capture_output=True, check=True)
                logger.info(f"Using screenshot tool: {tool}")
                return tool
            except subprocess.CalledProcessError:
                continue
        logger.warning("No screenshot tool found")
        return None
    
    def _detect_screen_recorder(self) -> str:
        """Detect which screen recorder is available"""
        tools = ['simplescreenrecorder', 'recordmydesktop', 'kazam']
        for tool in tools:
            try:
                subprocess.run(['which', tool], capture_output=True, check=True)
                logger.info(f"Using screen recorder: {tool}")
                return tool
            except subprocess.CalledProcessError:
                continue
        logger.warning("No screen recorder found")
        return None
    
    def screenshot_full(self) -> bool:
        """Take a full screenshot"""
        try:
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = self.screenshot_dir / f"screenshot_{timestamp}.png"
            
            if self.screenshot_tool == 'gnome-screenshot':
                subprocess.run(['gnome-screenshot', '-f', str(filename)])
            elif self.screenshot_tool == 'scrot':
                subprocess.run(['scrot', str(filename)])
            elif self.screenshot_tool == 'spectacle':
                subprocess.run(['spectacle', '-f', '-b', '-o', str(filename)])
            elif self.screenshot_tool == 'flameshot':
                subprocess.run(['flameshot', 'full', '-p', str(self.screenshot_dir)])
            else:
                logger.error("No screenshot tool available")
                return False
            
            logger.info(f"Screenshot saved: {filename}")
            # Show notification
            subprocess.run(['notify-send', 'Screenshot Saved', str(filename)])
            return True
            
        except Exception as e:
            logger.error(f"Screenshot failed: {e}")
            return False
    
    def screenshot_area(self) -> bool:
        """Take an area screenshot"""
        try:
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = self.screenshot_dir / f"screenshot_{timestamp}.png"
            
            if self.screenshot_tool == 'gnome-screenshot':
                subprocess.run(['gnome-screenshot', '-a', '-f', str(filename)])
            elif self.screenshot_tool == 'scrot':
                subprocess.run(['scrot', '-s', str(filename)])
            elif self.screenshot_tool == 'spectacle':
                subprocess.run(['spectacle', '-r', '-b', '-o', str(filename)])
            elif self.screenshot_tool == 'flameshot':
                subprocess.run(['flameshot', 'gui', '-p', str(self.screenshot_dir)])
            else:
                logger.error("No screenshot tool available")
                return False
            
            logger.info(f"Area screenshot saved: {filename}")
            return True
            
        except Exception as e:
            logger.error(f"Area screenshot failed: {e}")
            return False
    
    def screenshot_window(self) -> bool:
        """Take a window screenshot"""
        try:
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = self.screenshot_dir / f"screenshot_{timestamp}.png"
            
            if self.screenshot_tool == 'gnome-screenshot':
                subprocess.run(['gnome-screenshot', '-w', '-f', str(filename)])
            elif self.screenshot_tool == 'scrot':
                subprocess.run(['scrot', '-u', str(filename)])
            elif self.screenshot_tool == 'spectacle':
                subprocess.run(['spectacle', '-a', '-b', '-o', str(filename)])
            else:
                logger.error("No screenshot tool available")
                return False
            
            logger.info(f"Window screenshot saved: {filename}")
            return True
            
        except Exception as e:
            logger.error(f"Window screenshot failed: {e}")
            return False
    
    def screen_record_start(self) -> bool:
        """Start screen recording"""
        try:
            if self.screen_recorder:
                subprocess.Popen([self.screen_recorder])
                logger.info("Screen recorder launched")
                return True
            else:
                # Fallback to ffmpeg
                logger.info("Using ffmpeg for recording")
                from datetime import datetime
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                video_dir = Path.home() / "Videos" / "Recordings"
                video_dir.mkdir(parents=True, exist_ok=True)
                filename = video_dir / f"recording_{timestamp}.mkv"
                
                # Launch ffmpeg in background
                subprocess.Popen([
                    'ffmpeg', '-video_size', '1920x1080', '-framerate', '25',
                    '-f', 'x11grab', '-i', ':0.0', str(filename)
                ])
                subprocess.run(['notify-send', 'Recording Started', 'Stop with Ctrl+C in terminal'])
                return True
                
        except Exception as e:
            logger.error(f"Screen recording failed: {e}")
            return False
    
    def quick_note(self, ai_client=None) -> bool:
        """Create a quick note (optionally with AI assistance)"""
        try:
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = self.notes_dir / f"note_{timestamp}.txt"
            
            # Create empty note or AI-generated starter
            if ai_client:
                # Could ask AI to create a note template
                content = f"# Quick Note - {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
            else:
                content = f"# Quick Note - {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
            
            filename.write_text(content)
            
            # Open in default text editor
            subprocess.Popen(['xdg-open', str(filename)])
            logger.info(f"Quick note created: {filename}")
            return True
            
        except Exception as e:
            logger.error(f"Quick note failed: {e}")
            return False
    
    def lock_screen(self) -> bool:
        """Lock the screen"""
        try:
            # Try different desktop environments
            lock_commands = [
                ['gnome-screensaver-command', '--lock'],  # GNOME
                ['xflock4'],  # XFCE
                ['qdbus', 'org.freedesktop.ScreenSaver', '/ScreenSaver', 'Lock'],  # KDE
                ['loginctl', 'lock-session'],  # systemd
                ['xdg-screensaver', 'lock'],  # Generic
            ]
            
            for cmd in lock_commands:
                try:
                    subprocess.run(cmd, check=True, timeout=2)
                    logger.info("Screen locked")
                    return True
                except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
                    continue
            
            logger.error("Could not lock screen")
            return False
            
        except Exception as e:
            logger.error(f"Lock screen failed: {e}")
            return False
    
    def sleep_system(self) -> bool:
        """Put system to sleep"""
        try:
            subprocess.run(['systemctl', 'suspend'], check=True)
            logger.info("System suspended")
            return True
        except Exception as e:
            logger.error(f"Sleep failed: {e}")
            return False
    
    def shutdown_system(self) -> bool:
        """Shutdown the system"""
        try:
            subprocess.run(['systemctl', 'poweroff'], check=True)
            logger.info("System shutdown initiated")
            return True
        except Exception as e:
            logger.error(f"Shutdown failed: {e}")
            return False
    
    def reboot_system(self) -> bool:
        """Reboot the system"""
        try:
            subprocess.run(['systemctl', 'reboot'], check=True)
            logger.info("System reboot initiated")
            return True
        except Exception as e:
            logger.error(f"Reboot failed: {e}")
            return False
    
    def toggle_wifi(self) -> bool:
        """Toggle WiFi on/off"""
        try:
            # Check current state
            result = subprocess.run(['nmcli', 'radio', 'wifi'], capture_output=True, text=True)
            current_state = result.stdout.strip()
            
            if current_state == 'enabled':
                subprocess.run(['nmcli', 'radio', 'wifi', 'off'])
                subprocess.run(['notify-send', 'WiFi', 'Disabled'])
                logger.info("WiFi disabled")
            else:
                subprocess.run(['nmcli', 'radio', 'wifi', 'on'])
                subprocess.run(['notify-send', 'WiFi', 'Enabled'])
                logger.info("WiFi enabled")
            
            return True
            
        except Exception as e:
            logger.error(f"WiFi toggle failed: {e}")
            return False
    
    def toggle_bluetooth(self) -> bool:
        """Toggle Bluetooth on/off"""
        try:
            # Check current state
            result = subprocess.run(['bluetoothctl', 'show'], capture_output=True, text=True)
            
            if 'Powered: yes' in result.stdout:
                subprocess.run(['bluetoothctl', 'power', 'off'])
                subprocess.run(['notify-send', 'Bluetooth', 'Disabled'])
                logger.info("Bluetooth disabled")
            else:
                subprocess.run(['bluetoothctl', 'power', 'on'])
                subprocess.run(['notify-send', 'Bluetooth', 'Enabled'])
                logger.info("Bluetooth enabled")
            
            return True
            
        except Exception as e:
            logger.error(f"Bluetooth toggle failed: {e}")
            return False
