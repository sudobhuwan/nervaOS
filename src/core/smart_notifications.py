"""
NervaOS Smart Notifications - Interactive System Alerts

Provides intelligent, actionable notifications that:
- Analyze system issues with AI
- Offer clickable action buttons
- Auto-dismiss after user action
- Track notification history
"""

import logging
import subprocess
from typing import Optional, Callable, List, Dict
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger('nerva-smart-notifications')

# Check if notify-send is available
try:
    subprocess.run(['which', 'notify-send'], capture_output=True, check=True)
    NOTIFICATIONS_AVAILABLE = True
except:
    NOTIFICATIONS_AVAILABLE = False
    logger.warning("notify-send not available, notifications disabled")


class NotificationUrgency(Enum):
    """Notification urgency levels"""
    LOW = "low"
    NORMAL = "normal"
    CRITICAL = "critical"


@dataclass
class NotificationAction:
    """Represents a clickable action in a notification"""
    id: str
    label: str
    callback: Callable


class SmartNotificationManager:
    """
    Manages intelligent system notifications with AI analysis.
    
    Features:
    - Context-aware alerts
    - Actionable buttons
    - AI-powered suggestions
    - Non-intrusive (respects Gaming/Cinema modes)
    """
    
    def __init__(self, ai_client=None, context_engine=None):
        self.ai_client = ai_client
        self.context_engine = context_engine
        self._notification_history: List[Dict] = []
        self._suppressed = False
    
    async def notify_smart(
        self,
        title: str,
        message: str,
        urgency: NotificationUrgency = NotificationUrgency.NORMAL,
        actions: Optional[List[NotificationAction]] = None,
        icon: str = "dialog-information",
        analyze_with_ai: bool = False
    ):
        """
        Send an intelligent notification.
        
        Args:
            title: Notification title
            message: Notification body
            urgency: LOW, NORMAL, or CRITICAL
            actions: List of clickable actions
            icon: Icon name
            analyze_with_ai: Whether to enhance message with AI analysis
        """
        # Check context mode - suppress if gaming/cinema
        if self.context_engine and not urgency == NotificationUrgency.CRITICAL:
            try:
                mode = await self.context_engine.get_context_mode()
                if mode.value in ['gaming', 'media'] and not self._suppressed:
                    logger.info(f"Notification suppressed in {mode.value} mode")
                    return
            except:
                pass
        
        # Enhance message with AI if requested
        if analyze_with_ai and self.ai_client:
            try:
                enhanced = await self._ai_enhance_message(title, message)
                if enhanced:
                    message = enhanced
            except Exception as e:
                logger.error(f"AI enhancement failed: {e}")
        
        # Send notification
        await self._send_notification(title, message, urgency, actions, icon)
        
        # Log to history
        self._notification_history.append({
            'title': title,
            'message': message,
            'urgency': urgency.value,
            'actions': [a.label for a in (actions or [])],
            'timestamp': __import__('datetime').datetime.now().isoformat()
        })
    
    async def _ai_enhance_message(self, title: str, message: str) -> Optional[str]:
        """
        Use AI to provide better, actionable message.
        
        Example:
        Input: "High RAM usage: 90%"
        Output: "High RAM usage (90%). Chrome is using 3.2GB. 
                 Consider closing unused tabs or restarting the browser."
        """
        prompt = f"""System alert: {title}
Current message: {message}

Analyze this alert and provide:
1. What's happening (simple explanation)
2. Why it matters
3. What the user should do (1-2 specific actions)

Be concise (max 2 sentences). No fluff."""
        
        try:
            response = await self.ai_client.ask(prompt, {})
            return response.strip()
        except:
            return None
    
    async def _send_notification(
        self,
        title: str,
        message: str,
        urgency: NotificationUrgency,
        actions: Optional[List[NotificationAction]],
        icon: str
    ):
        """Send the actual notification using notify-send or DBus"""
        if not NOTIFICATIONS_AVAILABLE:
            logger.info(f"[Notification] {title}: {message}")
            return
        
        cmd = [
            'notify-send',
            title,
            message,
            f'--urgency={urgency.value}',
            f'--icon={icon}',
            '--app-name=NervaOS'
        ]
        
        # Add actions if supported (requires dunst or mako)
        if actions:
            for action in actions:
                cmd.extend(['--action', f'{action.id}={action.label}'])
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=5
            )
            
            # Handle action clicks (if notification server supports it)
            if result.stdout.strip() and actions:
                action_id = result.stdout.strip()
                for action in actions:
                    if action.id == action_id:
                        action.callback()
                        break
        
        except Exception as e:
            logger.error(f"Notification failed: {e}")
    
    # ─────────────────────────────────────────────────────────────
    # Pre-built Smart Notifications
    # ─────────────────────────────────────────────────────────────
    
    async def notify_high_ram(
        self,
        ram_percent: float,
        top_process: str,
        top_process_ram_mb: float
    ):
        """Smart notification for high RAM usage"""
        title = "🔴 High Memory Usage"
        message = f"RAM at {ram_percent:.1f}%\n{top_process} using {top_process_ram_mb:.1f}MB"
        
        actions = [
            NotificationAction(
                id="kill",
                label="Kill Process",
                callback=lambda: self._kill_process(top_process)
            ),
            NotificationAction(
                id="details",
                label="Details",
                callback=lambda: self._open_system_monitor()
            )
        ]
        
        await self.notify_smart(
            title,
            message,
            urgency=NotificationUrgency.CRITICAL,
            actions=actions,
            icon="dialog-warning",
            analyze_with_ai=True
        )
    
    async def notify_crash(self, app_name: str, error_details: str):
        """Smart notification for application crash"""
        title = f"💥 {app_name} Crashed"
        
        actions = [
            NotificationAction(
                id="fix",
                label="Auto-Fix",
                callback=lambda: self._attempt_autofix(app_name, error_details)
            ),
            NotificationAction(
                id="logs",
                label="View Logs",
                callback=lambda: self._show_logs(app_name)
            )
        ]
        
        await self.notify_smart(
            title,
            error_details[:100],
            urgency=NotificationUrgency.NORMAL,
            actions=actions,
            icon="dialog-error",
            analyze_with_ai=True
        )
    
    async def notify_disk_full(self, path: str, percent: float, largest_dir: str):
        """Smart notification for low disk space"""
        title = "💾 Low Disk Space"
        message = f"{path} is {percent:.1f}% full\nLargest: {largest_dir}"
        
        actions = [
            NotificationAction(
                id="clean",
                label="Clean Now",
                callback=lambda: self._auto_clean_disk()
            ),
            NotificationAction(
                id="analyze",
                label="Analyze",
                callback=lambda: self._open_disk_analyzer()
            )
        ]
        
        await self.notify_smart(
            title,
            message,
            urgency=NotificationUrgency.NORMAL if percent < 95 else NotificationUrgency.CRITICAL,
            actions=actions,
            icon="drive-harddisk",
            analyze_with_ai=True
        )
    
    async def notify_update_available(self, package_count: int):
        """Smart notification for system updates"""
        title = "📦 Updates Available"
        message = f"{package_count} packages can be updated"
        
        actions = [
            NotificationAction(
                id="update",
                label="Update Now",
                callback=lambda: self._run_updates()
            ),
            NotificationAction(
                id="later",
                label="Remind Later",
                callback=lambda: self._schedule_reminder(hours=6)
            )
        ]
        
        await self.notify_smart(
            title,
            message,
            urgency=NotificationUrgency.LOW,
            actions=actions,
            icon="software-update-available"
        )
    
    async def notify_ai_suggestion(self, suggestion: str):
        """Proactive AI suggestion based on user patterns"""
        title = "💡 NervaOS Suggestion"
        
        await self.notify_smart(
            title,
            suggestion,
            urgency=NotificationUrgency.LOW,
            icon="starred-symbolic"
        )
    
    # ─────────────────────────────────────────────────────────────
    # Action Handlers
    # ─────────────────────────────────────────────────────────────
    
    def _kill_process(self, process_name: str):
        """Kill a process by name"""
        try:
            subprocess.run(['pkill', '-9', process_name])
            logger.info(f"Killed process: {process_name}")
        except Exception as e:
            logger.error(f"Failed to kill {process_name}: {e}")
    
    def _open_system_monitor(self):
        """Open the system monitor application"""
        try:
            subprocess.Popen(['gnome-system-monitor'])
        except:
            try:
                subprocess.Popen(['htop'])
            except:
                logger.error("No system monitor available")
    
    def _attempt_autofix(self, app_name: str, error: str):
        """Attempt to auto-fix a crash"""
        # TODO: Use AI to suggest fix
        logger.info(f"Auto-fix requested for {app_name}")
    
    def _show_logs(self, app_name: str):
        """Show logs for an application"""
        try:
            subprocess.Popen([
                'gnome-terminal', '--', 'journalctl', '-f', '-u', app_name
            ])
        except:
            logger.error("Failed to open logs")
    
    def _auto_clean_disk(self):
        """Run disk cleanup utilities"""
        try:
            # Run common cleanup commands
            subprocess.Popen(['baobab'])  # Disk usage analyzer
        except:
            logger.error("Failed to start disk cleanup")
    
    def _open_disk_analyzer(self):
        """Open disk usage analyzer"""
        try:
            subprocess.Popen(['baobab'])
        except:
            logger.error("Disk analyzer not available")
    
    def _run_updates(self):
        """Run system updates"""
        try:
            subprocess.Popen([
                'gnome-terminal', '--', 'bash', '-c',
                'sudo apt update && sudo apt upgrade -y; read -p "Press Enter to close..."'
            ])
        except:
            logger.error("Failed to start updates")
    
    def _schedule_reminder(self, hours: int):
        """Schedule a reminder notification"""
        logger.info(f"Reminder scheduled for {hours} hours")
        # TODO: Implement reminder system
    
    def suppress_notifications(self, suppressed: bool = True):
        """Suppress all non-critical notifications"""
        self._suppressed = suppressed
        logger.info(f"Notifications {'suppressed' if suppressed else 'enabled'}")
    
    def get_history(self, limit: int = 10) -> List[Dict]:
        """Get notification history"""
        return self._notification_history[-limit:]
