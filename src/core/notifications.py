"""
NervaOS Notifications - System notification integration

Uses libnotify to send desktop notifications for:
- AI responses
- System alerts (high CPU/RAM)
- File operation results
- License status
"""

import logging
from typing import Optional
from enum import Enum

import gi
gi.require_version('Notify', '0.7')
from gi.repository import Notify, Gio

logger = logging.getLogger('nerva-notifications')


class NotificationUrgency(Enum):
    """Notification urgency levels"""
    LOW = 0
    NORMAL = 1
    CRITICAL = 2


class NotificationManager:
    """
    Manages desktop notifications for NervaOS.
    
    Uses libnotify for native Linux Mint notifications.
    """
    
    # Notification categories
    CATEGORY_SYSTEM = "system"
    CATEGORY_AI = "ai.response"
    CATEGORY_FILE = "file.operation"
    CATEGORY_LICENSE = "license"
    
    def __init__(self, app_name: str = "NervaOS"):
        self._app_name = app_name
        self._initialized = False
        
        # Initialize libnotify
        if Notify.init(app_name):
            self._initialized = True
            logger.info("Notification system initialized")
        else:
            logger.error("Failed to initialize notifications")
    
    def show(
        self,
        title: str,
        message: str,
        icon: str = "nervaos",
        urgency: NotificationUrgency = NotificationUrgency.NORMAL,
        category: Optional[str] = None,
        timeout: int = 5000  # milliseconds
    ) -> bool:
        """
        Show a desktop notification.
        
        Args:
            title: Notification title
            message: Notification body
            icon: Icon name or path
            urgency: LOW, NORMAL, or CRITICAL
            category: Notification category for grouping
            timeout: Auto-hide timeout in milliseconds
            
        Returns:
            True if notification was shown successfully
        """
        if not self._initialized:
            logger.warning("Notifications not initialized")
            return False
        
        try:
            notification = Notify.Notification.new(title, message, icon)
            
            # Set urgency
            notification.set_urgency(urgency.value)
            
            # Set timeout
            notification.set_timeout(timeout)
            
            # Set category
            if category:
                notification.set_category(category)
            
            # Show it
            notification.show()
            
            logger.debug(f"Notification shown: {title}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to show notification: {e}")
            return False
    
    def show_ai_response(self, response: str, truncate: int = 100):
        """Show an AI response notification"""
        display_text = response[:truncate] + "..." if len(response) > truncate else response
        
        self.show(
            title="NervaOS Response",
            message=display_text,
            icon="user-idle-symbolic",
            urgency=NotificationUrgency.NORMAL,
            category=self.CATEGORY_AI
        )
    
    def show_system_alert(self, message: str):
        """Show a system alert notification"""
        self.show(
            title="System Alert",
            message=message,
            icon="dialog-warning-symbolic",
            urgency=NotificationUrgency.CRITICAL,
            category=self.CATEGORY_SYSTEM,
            timeout=10000  # 10 seconds for alerts
        )
    
    def show_file_operation(self, operation: str, file_path: str, success: bool):
        """Show file operation result notification"""
        if success:
            title = f"File {operation} Successful"
            icon = "emblem-ok-symbolic"
        else:
            title = f"File {operation} Failed"
            icon = "dialog-error-symbolic"
        
        self.show(
            title=title,
            message=file_path,
            icon=icon,
            category=self.CATEGORY_FILE
        )
    
    def show_license_status(self, status: str, message: str):
        """Show license status notification"""
        if status == "valid":
            icon = "security-medium-symbolic"
            urgency = NotificationUrgency.LOW
        elif status == "expired":
            icon = "dialog-warning-symbolic"
            urgency = NotificationUrgency.CRITICAL
        else:
            icon = "dialog-error-symbolic"
            urgency = NotificationUrgency.CRITICAL
        
        self.show(
            title=f"License {status.title()}",
            message=message,
            icon=icon,
            urgency=urgency,
            category=self.CATEGORY_LICENSE
        )
    
    def close(self):
        """Clean up notifications"""
        if self._initialized:
            Notify.uninit()
            self._initialized = False


# ─────────────────────────────────────────────────────────────────────────────
# Global instance
# ─────────────────────────────────────────────────────────────────────────────

_notification_manager: Optional[NotificationManager] = None


def get_notification_manager() -> NotificationManager:
    """Get the global notification manager"""
    global _notification_manager
    if _notification_manager is None:
        _notification_manager = NotificationManager()
    return _notification_manager


def notify(title: str, message: str, **kwargs):
    """Quick notification helper"""
    get_notification_manager().show(title, message, **kwargs)
