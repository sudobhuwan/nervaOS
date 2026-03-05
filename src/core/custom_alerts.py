"""
NervaOS Custom Alert Rules Engine
Allows users to define custom system monitoring rules and alerts.
"""

import logging
import psutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, asdict
from datetime import datetime
import json

logger = logging.getLogger('nerva-alerts')


@dataclass
class AlertRule:
    """Represents a custom alert rule"""
    id: str
    name: str
    description: str
    enabled: bool
    rule_type: str  # 'battery', 'disk', 'process', 'network', 'temperature'
    condition: Dict  # e.g., {'operator': 'less_than', 'value': 20}
    action: str  # 'notify', 'execute'
    action_params: Dict  # e.g., {'message': '...', 'urgency': 'critical'}
    last_triggered: Optional[datetime] = None
    trigger_count: int = 0
    cooldown_minutes: int = 5  # Don't trigger again within cooldown
    
    def to_dict(self):
        d = asdict(self)
        if self.last_triggered:
            d['last_triggered'] = self.last_triggered.isoformat()
        return d
    
    @classmethod
    def from_dict(cls, data: Dict):
        if data.get('last_triggered'):
            data['last_triggered'] = datetime.fromisoformat(data['last_triggered'])
        return cls(**data)


class CustomAlertEngine:
    """Manages custom alert rules and checks them periodically"""
    
    def __init__(self, storage_path: Path, notification_callback: Optional[Callable] = None):
        self.storage_path = storage_path
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.rules_file = self.storage_path / 'alert_rules.json'
        
        self.rules: Dict[str, AlertRule] = {}
        self.notification_callback = notification_callback
        
        self._load_rules()
        self._create_default_rules()
    
    def _load_rules(self):
        """Load alert rules from disk"""
        if self.rules_file.exists():
            try:
                with open(self.rules_file, 'r') as f:
                    data = json.load(f)
                    for rule_id, rule_data in data.items():
                        self.rules[rule_id] = AlertRule.from_dict(rule_data)
                logger.info(f"Loaded {len(self.rules)} alert rules")
            except Exception as e:
                logger.error(f"Failed to load alert rules: {e}")
    
    def _save_rules(self):
        """Save alert rules to disk"""
        try:
            data = {rule_id: rule.to_dict() for rule_id, rule in self.rules.items()}
            with open(self.rules_file, 'w') as f:
                json.dump(data, f, indent=2)
            logger.debug("Alert rules saved")
        except Exception as e:
            logger.error(f"Failed to save alert rules: {e}")
    
    def _create_default_rules(self):
        """Create default alert rules if none exist"""
        if not self.rules:
            # Battery low alert
            self.add_rule(AlertRule(
                id='battery_low',
                name='Battery Low',
                description='Alert when battery is below 20%',
                enabled=True,
                rule_type='battery',
                condition={'operator': 'less_than', 'value': 20},
                action='notify',
                action_params={
                    'message': 'Battery is low! {value}% remaining',
                    'urgency': 'critical'
                },
                cooldown_minutes=10
            ))
            
            # Disk space low alert
            self.add_rule(AlertRule(
                id='disk_low',
                name='Disk Space Low',
                description='Alert when disk space is below 10GB',
                enabled=True,
                rule_type='disk',
                condition={'operator': 'less_than', 'value': 10},  # GB
                action='notify',
                action_params={
                    'message': 'Disk space is low! Only {value}GB remaining',
                    'urgency': 'normal'
                },
                cooldown_minutes=30
            ))
            
            # Network disconnect alert
            self.add_rule(AlertRule(
                id='network_down',
                name='Network Disconnected',
                description='Alert when network connection is lost',
                enabled=True,
                rule_type='network',
                condition={'operator': 'equals', 'value': 'disconnected'},
                action='notify',
                action_params={
                    'message': 'Network connection lost!',
                    'urgency': 'normal'
                },
                cooldown_minutes=5
            ))
            
            # High temperature alert
            self.add_rule(AlertRule(
                id='temp_high',
                name='High Temperature',
                description='Alert when CPU temperature exceeds 80°C',
                enabled=True,
                rule_type='temperature',
                condition={'operator': 'greater_than', 'value': 80},
                action='notify',
                action_params={
                    'message': 'CPU temperature is high! {value}°C',
                    'urgency': 'critical'
                },
                cooldown_minutes=10
            ))
            
            logger.info("Created default alert rules")
            self._save_rules()
    
    def add_rule(self, rule: AlertRule):
        """Add a new alert rule"""
        self.rules[rule.id] = rule
        self._save_rules()
        logger.info(f"Added alert rule: {rule.name}")
    
    def remove_rule(self, rule_id: str) -> bool:
        """Remove an alert rule"""
        if rule_id in self.rules:
            del self.rules[rule_id]
            self._save_rules()
            logger.info(f"Removed alert rule: {rule_id}")
            return True
        return False
    
    def enable_rule(self, rule_id: str):
        """Enable an alert rule"""
        if rule_id in self.rules:
            self.rules[rule_id].enabled = True
            self._save_rules()
    
    def disable_rule(self, rule_id: str):
        """Disable an alert rule"""
        if rule_id in self.rules:
            self.rules[rule_id].enabled = False
            self._save_rules()
    
    def check_all_rules(self):
        """Check all enabled rules and trigger alerts if needed"""
        for rule in self.rules.values():
            if rule.enabled:
                self._check_rule(rule)
    
    def _check_rule(self, rule: AlertRule):
        """Check a single rule and trigger if condition is met"""
        # Check cooldown
        if rule.last_triggered:
            from datetime import timedelta
            cooldown = timedelta(minutes=rule.cooldown_minutes)
            if datetime.now() - rule.last_triggered < cooldown:
                return  # Still in cooldown
        
        # Get current value based on rule type
        current_value = self._get_current_value(rule.rule_type)
        
        if current_value is None:
            return
        
        # Check condition
        if self._evaluate_condition(current_value, rule.condition):
            self._trigger_alert(rule, current_value)
    
    def _get_current_value(self, rule_type: str):
        """Get current system value for the rule type"""
        try:
            if rule_type == 'battery':
                battery = psutil.sensors_battery()
                if battery:
                    return battery.percent
                return None
            
            elif rule_type == 'disk':
                disk = psutil.disk_usage('/')
                # Return free space in GB
                return disk.free / (1024**3)
            
            elif rule_type == 'network':
                # Check if any network interface is up
                net_stats = psutil.net_if_stats()
                for interface, stats in net_stats.items():
                    if interface != 'lo' and stats.isup:
                        return 'connected'
                return 'disconnected'
            
            elif rule_type == 'temperature':
                # Try to get CPU temperature
                try:
                    temps = psutil.sensors_temperatures()
                    if temps:
                        # Get first available temperature sensor
                        for name, entries in temps.items():
                            if entries:
                                return entries[0].current
                except:
                    pass
                return None
            
            elif rule_type == 'process':
                # Check if specific process is running
                # (condition should have 'process_name')
                return None  # Implemented in _evaluate_condition
            
        except Exception as e:
            logger.error(f"Error getting value for {rule_type}: {e}")
            return None
    
    def _evaluate_condition(self, current_value, condition: Dict) -> bool:
        """Evaluate if condition is met"""
        operator = condition.get('operator')
        threshold = condition.get('value')
        
        if operator == 'less_than':
            return current_value < threshold
        elif operator == 'greater_than':
            return current_value > threshold
        elif operator == 'equals':
            return current_value == threshold
        elif operator == 'not_equals':
            return current_value != threshold
        elif operator == 'between':
            min_val = condition.get('min')
            max_val = condition.get('max')
            return min_val <= current_value <= max_val
        
        return False
    
    def _trigger_alert(self, rule: AlertRule, current_value):
        """Trigger the alert action"""
        rule.last_triggered = datetime.now()
        rule.trigger_count += 1
        self._save_rules()
        
        logger.info(f"Alert triggered: {rule.name} (value: {current_value})")
        
        if rule.action == 'notify':
            message = rule.action_params.get('message', '').format(value=current_value)
            urgency = rule.action_params.get('urgency', 'normal')
            
            # Send notification
            self._send_notification(rule.name, message, urgency)
            
            # Call callback if provided
            if self.notification_callback:
                self.notification_callback(rule.name, message, urgency)
        
        elif rule.action == 'execute':
            command = rule.action_params.get('command', '')
            if command:
                try:
                    subprocess.run(command, shell=True, check=False)
                    logger.info(f"Executed command: {command}")
                except Exception as e:
                    logger.error(f"Failed to execute command: {e}")
    
    def _send_notification(self, title: str, message: str, urgency: str = 'normal'):
        """Send system notification"""
        try:
            urgency_map = {
                'low': 'low',
                'normal': 'normal',
                'critical': 'critical'
            }
            subprocess.run([
                'notify-send',
                '-u', urgency_map.get(urgency, 'normal'),
                '-i', 'dialog-warning',
                title,
                message
            ])
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")
    
    def get_all_rules(self) -> List[AlertRule]:
        """Get all alert rules"""
        return list(self.rules.values())
    
    def get_rule(self, rule_id: str) -> Optional[AlertRule]:
        """Get a specific rule"""
        return self.rules.get(rule_id)
