"""
NervaOS Automation Engine - Workflow & Pattern Learning System

This module provides:
- Workflow definition and execution
- Pattern learning from user behavior
- Proactive suggestions
- Time-based and event-based triggers
- Auto-optimization
"""

import asyncio
import logging
import json
import yaml
from pathlib import Path
from datetime import datetime, time as datetime_time, timedelta
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, asdict, field
from enum import Enum
import hashlib

logger = logging.getLogger('nerva-automation')


class TriggerType(Enum):
    """Types of workflow triggers"""
    TIME = "time"              # Daily at 09:00
    WEEKDAY = "weekday"        # Mon-Fri at 09:00
    EVENT = "event"            # When RAM > 90%
    FILE_COUNT = "file_count"  # When Downloads has >50 files
    BATTERY = "battery"        # When battery < 20%
    APP_LAUNCH = "app_launch"  # When VS Code opens
    PATTERN = "pattern"        # Learned from behavior


class ActionType(Enum):
    """Types of workflow actions"""
    OPEN_APP = "open"
    EXECUTE = "execute"
    CLOSE_APP = "close"
    ORGANIZE = "organize"
    NOTIFY = "notify"
    ASK_AI = "ask_ai"
    SUGGEST = "suggest"


@dataclass
class WorkflowTrigger:
    """Defines when a workflow should run"""
    type: TriggerType
    condition: Dict[str, Any]
    
    def matches(self, context: Dict[str, Any]) -> bool:
        """Check if current context matches this trigger"""
        if self.type == TriggerType.TIME:
            current_time = datetime.now().strftime("%H:%M")
            return current_time == self.condition.get('time')
        
        elif self.type == TriggerType.WEEKDAY:
            weekday = datetime.now().strftime("%a")
            allowed_days = self.condition.get('days', 'Mon-Fri')
            if '-' in allowed_days:
                # Handle ranges like "Mon-Fri"
                return weekday in ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']
            return weekday in allowed_days.split(',')
        
        elif self.type == TriggerType.EVENT:
            # Check system events
            metric = self.condition.get('metric')
            operator = self.condition.get('operator', '>')
            threshold = self.condition.get('value')
            
            current_value = context.get(metric, 0)
            
            if operator == '>':
                return current_value > threshold
            elif operator == '<':
                return current_value < threshold
            elif operator == '==':
                return current_value == threshold
        
        elif self.type == TriggerType.FILE_COUNT:
            path = Path(self.condition.get('path', '')).expanduser()
            if path.exists() and path.is_dir():
                count = len(list(path.iterdir()))
                threshold = self.condition.get('count', 50)
                return count > threshold
        
        elif self.type == TriggerType.BATTERY:
            battery_level = context.get('battery_percent', 100)
            threshold = self.condition.get('level', 20)
            return battery_level < threshold
        
        elif self.type == TriggerType.APP_LAUNCH:
            active_app = context.get('active_app', '').lower()
            target_app = self.condition.get('app', '').lower()
            return target_app in active_app
        
        return False


@dataclass
class WorkflowAction:
    """Defines what a workflow should do"""
    type: ActionType
    params: Dict[str, Any]
    
    async def execute(self, executor: 'WorkflowExecutor') -> bool:
        """Execute this action"""
        try:
            if self.type == ActionType.OPEN_APP:
                app = self.params.get('app')
                await executor.open_app(app)
            
            elif self.type == ActionType.EXECUTE:
                cmd = self.params.get('command')
                await executor.execute_command(cmd)
            
            elif self.type == ActionType.CLOSE_APP:
                app = self.params.get('app')
                await executor.close_app(app)
            
            elif self.type == ActionType.ORGANIZE:
                path = self.params.get('path')
                await executor.organize_folder(path)
            
            elif self.type == ActionType.NOTIFY:
                message = self.params.get('message')
                await executor.send_notification(message)
            
            elif self.type == ActionType.ASK_AI:
                query = self.params.get('query')
                await executor.ask_ai(query)
            
            elif self.type == ActionType.SUGGEST:
                suggestion = self.params.get('suggestion')
                await executor.show_suggestion(suggestion)
            
            return True
        
        except Exception as e:
            logger.error(f"Action execution failed: {e}")
            return False


@dataclass
class Workflow:
    """A complete automation workflow"""
    id: str
    name: str
    description: str
    enabled: bool
    trigger: WorkflowTrigger
    actions: List[WorkflowAction]
    last_run: Optional[datetime] = None
    run_count: int = 0
    learned: bool = False  # Whether this was learned from user behavior
    confidence: float = 0.0  # Confidence score for learned workflows
    
    async def execute(self, executor: 'WorkflowExecutor') -> bool:
        """Execute all actions in this workflow"""
        logger.info(f"Executing workflow: {self.name}")
        
        success = True
        for action in self.actions:
            result = await action.execute(executor)
            success = success and result
        
        self.last_run = datetime.now()
        self.run_count += 1
        
        return success
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for storage"""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'enabled': self.enabled,
            'trigger': {
                'type': self.trigger.type.value,
                'condition': self.trigger.condition
            },
            'actions': [
                {
                    'type': action.type.value,
                    'params': action.params
                }
                for action in self.actions
            ],
            'last_run': self.last_run.isoformat() if self.last_run else None,
            'run_count': self.run_count,
            'learned': self.learned,
            'confidence': self.confidence
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Workflow':
        """Create workflow from dictionary"""
        trigger = WorkflowTrigger(
            type=TriggerType(data['trigger']['type']),
            condition=data['trigger']['condition']
        )
        
        actions = [
            WorkflowAction(
                type=ActionType(a['type']),
                params=a['params']
            )
            for a in data['actions']
        ]
        
        last_run = None
        if data.get('last_run'):
            last_run = datetime.fromisoformat(data['last_run'])
        
        return cls(
            id=data['id'],
            name=data['name'],
            description=data['description'],
            enabled=data['enabled'],
            trigger=trigger,
            actions=actions,
            last_run=last_run,
            run_count=data.get('run_count', 0),
            learned=data.get('learned', False),
            confidence=data.get('confidence', 0.0)
        )


@dataclass
class UserPattern:
    """Represents a learned user behavior pattern"""
    id: str
    pattern_type: str  # "app_sequence", "time_routine", "condition_action"
    description: str
    occurrences: List[datetime]
    confidence: float
    suggested: bool = False
    accepted: bool = False
    
    def get_frequency(self) -> int:
        """Get how many times this pattern occurred"""
        return len(self.occurrences)
    
    def get_last_occurrence(self) -> Optional[datetime]:
        """Get when this pattern last occurred"""
        return max(self.occurrences) if self.occurrences else None
    
    def is_frequent(self, min_occurrences: int = 3) -> bool:
        """Check if pattern is frequent enough to suggest"""
        return len(self.occurrences) >= min_occurrences


class PatternLearner:
    """
    Learns user behavior patterns and suggests automations.
    
    Tracks:
    - App launch sequences
    - Time-based routines
    - Condition-action patterns
    """
    
    def __init__(self, storage_path: Path):
        self.storage_path = storage_path
        self.patterns: Dict[str, UserPattern] = {}
        self.activity_log: List[Dict] = []
        self._load_patterns()
    
    def _load_patterns(self):
        """Load learned patterns from disk"""
        pattern_file = self.storage_path / 'learned_patterns.json'
        if pattern_file.exists():
            try:
                with open(pattern_file, 'r') as f:
                    data = json.load(f)
                    for p in data.get('patterns', []):
                        pattern = UserPattern(
                            id=p['id'],
                            pattern_type=p['pattern_type'],
                            description=p['description'],
                            occurrences=[datetime.fromisoformat(d) for d in p['occurrences']],
                            confidence=p['confidence'],
                            suggested=p.get('suggested', False),
                            accepted=p.get('accepted', False)
                        )
                        self.patterns[pattern.id] = pattern
                logger.info(f"Loaded {len(self.patterns)} learned patterns")
            except Exception as e:
                logger.error(f"Failed to load patterns: {e}")
    
    def _save_patterns(self):
        """Save learned patterns to disk"""
        pattern_file = self.storage_path / 'learned_patterns.json'
        try:
            data = {
                'patterns': [
                    {
                        'id': p.id,
                        'pattern_type': p.pattern_type,
                        'description': p.description,
                        'occurrences': [d.isoformat() for d in p.occurrences],
                        'confidence': p.confidence,
                        'suggested': p.suggested,
                        'accepted': p.accepted
                    }
                    for p in self.patterns.values()
                ]
            }
            with open(pattern_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save patterns: {e}")
    
    def log_activity(self, activity_type: str, details: Dict):
        """Log user activity for pattern detection"""
        entry = {
            'type': activity_type,
            'details': details,
            'timestamp': datetime.now().isoformat()
        }
        self.activity_log.append(entry)
        
        # Keep only last 1000 entries
        if len(self.activity_log) > 1000:
            self.activity_log = self.activity_log[-1000:]
        
        # Analyze for patterns
        self._analyze_recent_activity()
    
    def _analyze_recent_activity(self):
        """Analyze recent activity for patterns"""
        # Look for app sequences (e.g., always open Code → Chrome → Terminal)
        self._detect_app_sequences()
        
        # Look for time-based routines (e.g., always at 9am)
        self._detect_time_routines()
        
        # Look for condition-action patterns
        self._detect_condition_actions()
    
    def _detect_app_sequences(self):
        """Detect sequences of app launches"""
        # Get last 10 app launches
        app_launches = [
            entry for entry in self.activity_log[-20:]
            if entry['type'] == 'app_launch'
        ]
        
        if len(app_launches) < 3:
            return
        
        # Look for sequences of 3 apps within 5 minutes
        for i in range(len(app_launches) - 2):
            sequence = app_launches[i:i+3]
            
            # Check if within 5 minutes
            times = [datetime.fromisoformat(e['timestamp']) for e in sequence]
            if (times[-1] - times[0]).total_seconds() > 300:
                continue
            
            # Create pattern signature
            apps = [e['details']['app'] for e in sequence]
            pattern_id = hashlib.md5('_'.join(apps).encode()).hexdigest()[:16]
            
            # Add or update pattern
            if pattern_id in self.patterns:
                pattern = self.patterns[pattern_id]
                pattern.occurrences.append(datetime.now())
                pattern.confidence = min(1.0, len(pattern.occurrences) / 10.0)
            else:
                pattern = UserPattern(
                    id=pattern_id,
                    pattern_type='app_sequence',
                    description=f"Open {' → '.join(apps)}",
                    occurrences=[datetime.now()],
                    confidence=0.1
                )
                self.patterns[pattern_id] = pattern
                logger.info(f"Detected new pattern: {pattern.description}")
        
        self._save_patterns()
    
    def _detect_time_routines(self):
        """Detect time-based routines"""
        # Group activities by hour
        hourly_activities: Dict[int, List[str]] = {}
        
        for entry in self.activity_log[-100:]:
            timestamp = datetime.fromisoformat(entry['timestamp'])
            hour = timestamp.hour
            
            if hour not in hourly_activities:
                hourly_activities[hour] = []
            
            if entry['type'] == 'app_launch':
                hourly_activities[hour].append(entry['details']['app'])
        
        # Find consistent patterns
        for hour, apps in hourly_activities.items():
            if len(apps) < 3:
                continue
            
            # Check for most common app at this hour
            app_counts = {}
            for app in apps:
                app_counts[app] = app_counts.get(app, 0) + 1
            
            most_common = max(app_counts.items(), key=lambda x: x[1])
            if most_common[1] >= 3:  # At least 3 occurrences
                pattern_id = f"time_routine_{hour}_{most_common[0]}"
                
                if pattern_id not in self.patterns:
                    pattern = UserPattern(
                        id=pattern_id,
                        pattern_type='time_routine',
                        description=f"Open {most_common[0]} around {hour}:00",
                        occurrences=[datetime.now()],
                        confidence=most_common[1] / len(apps)
                    )
                    self.patterns[pattern_id] = pattern
                    logger.info(f"Detected time routine: {pattern.description}")
        
        self._save_patterns()
    
    def _detect_condition_actions(self):
        """Detect condition → action patterns"""
        # Example: When Downloads folder has >50 files, user organizes it
        # This would require more sophisticated tracking
        pass
    
    def get_suggestions(self) -> List[Dict]:
        """Get workflow suggestions based on learned patterns"""
        suggestions = []
        
        for pattern in self.patterns.values():
            # Only suggest if:
            # 1. High confidence
            # 2. Not already suggested
            # 3. Frequent enough
            if (pattern.confidence > 0.7 and 
                not pattern.suggested and 
                pattern.is_frequent(min_occurrences=5)):
                
                suggestion = {
                    'pattern_id': pattern.id,
                    'title': 'Automate Routine?',
                    'description': pattern.description,
                    'occurrences': pattern.get_frequency(),
                    'confidence': pattern.confidence
                }
                suggestions.append(suggestion)
                
                # Mark as suggested
                pattern.suggested = True
        
        self._save_patterns()
        return suggestions
    
    def accept_suggestion(self, pattern_id: str) -> Optional[Workflow]:
        """Convert a pattern into a workflow"""
        if pattern_id not in self.patterns:
            return None
        
        pattern = self.patterns[pattern_id]
        pattern.accepted = True
        self._save_patterns()
        
        # Convert pattern to workflow
        if pattern.pattern_type == 'app_sequence':
            # Parse app sequence
            apps = pattern.description.replace('Open ', '').split(' → ')
            
            actions = [
                WorkflowAction(
                    type=ActionType.OPEN_APP,
                    params={'app': app}
                )
                for app in apps
            ]
            
            workflow = Workflow(
                id=f"learned_{pattern.id}",
                name=f"Auto: {pattern.description}",
                description=f"Learned from {pattern.get_frequency()} occurrences",
                enabled=True,
                trigger=WorkflowTrigger(
                    type=TriggerType.PATTERN,
                    condition={'pattern_id': pattern.id}
                ),
                actions=actions,
                learned=True,
                confidence=pattern.confidence
            )
            
            return workflow
        
        elif pattern.pattern_type == 'time_routine':
            # Parse time routine
            # "Open VS Code around 9:00"
            import re
            match = re.search(r'Open (\w+) around (\d+):00', pattern.description)
            if match:
                app, hour = match.groups()
                
                workflow = Workflow(
                    id=f"learned_{pattern.id}",
                    name=f"Morning Routine: {app}",
                    description=f"Learned from {pattern.get_frequency()} occurrences",
                    enabled=True,
                    trigger=WorkflowTrigger(
                        type=TriggerType.TIME,
                        condition={'time': f"{hour}:00"}
                    ),
                    actions=[
                        WorkflowAction(
                            type=ActionType.OPEN_APP,
                            params={'app': app}
                        )
                    ],
                    learned=True,
                    confidence=pattern.confidence
                )
                
                return workflow
        
        return None


class WorkflowExecutor:
    """
    Executes workflow actions by calling appropriate system functions.
    """
    
    def __init__(self, daemon):
        self.daemon = daemon
    
    async def open_app(self, app: str):
        """Open an application"""
        import subprocess
        subprocess.Popen(
            app,
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        logger.info(f"Opened app: {app}")
    
    async def execute_command(self, command: str):
        """Execute a safe command"""
        if self.daemon.safety:
            success, output = await self.daemon.safety.safe_execute_command(command)
            if success:
                logger.info(f"Executed: {command}")
            else:
                logger.error(f"Command failed: {output}")
    
    async def close_app(self, app: str):
        """Close an application"""
        import subprocess
        subprocess.run(['pkill', '-9', app])
        logger.info(f"Closed app: {app}")
    
    async def organize_folder(self, path: str):
        """Organize a folder"""
        # Use the organize action from service.py
        logger.info(f"Organizing: {path}")
        # This would call the organize action handler
    
    async def send_notification(self, message: str):
        """Send a notification"""
        if self.daemon.notifications:
            await self.daemon.notifications.notify_ai_suggestion(message)
    
    async def ask_ai(self, query: str):
        """Ask AI a question"""
        if self.daemon.ai_client:
            response = await self.daemon.ai_client.ask(query, {})
            await self.send_notification(response[:200])
    
    async def show_suggestion(self, suggestion: str):
        """Show a proactive suggestion"""
        if self.daemon.notifications:
            await self.daemon.notifications.notify_ai_suggestion(suggestion)


class AutomationEngine:
    """
    Main automation engine that manages workflows and learning.
    """
    
    def __init__(self, daemon, storage_dir: Path):
        self.daemon = daemon
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        self.workflows: Dict[str, Workflow] = {}
        self.learner = PatternLearner(storage_dir)
        self.executor = WorkflowExecutor(daemon)
        
        self.running = False
        self._check_interval = 60  # Check triggers every minute
        
        self._load_workflows()
    
    def _load_workflows(self):
        """Load workflows from JSON or YAML"""
        # Try JSON first (internal storage)
        workflows_file = self.storage_dir / 'workflows.json'
        if workflows_file.exists():
            try:
                with open(workflows_file, 'r') as f:
                    data = json.load(f)
                    for w in data.get('workflows', []):
                        workflow = Workflow.from_dict(w)
                        self.workflows[workflow.id] = workflow
                logger.info(f"Loaded {len(self.workflows)} workflows from JSON")
            except Exception as e:
                logger.error(f"Failed to load workflows from JSON: {e}")
        
        # Also load YAML workflows (user-defined)
        yaml_file = self.storage_dir / 'workflows.yaml'
        if yaml_file.exists():
            try:
                with open(yaml_file, 'r') as f:
                    data = yaml.safe_load(f)
                    for w in data.get('workflows', []):
                        workflow = self._workflow_from_yaml(w)
                        if workflow:
                            self.workflows[workflow.id] = workflow
                logger.info(f"Loaded {len(self.workflows)} total workflows")
            except Exception as e:
                logger.error(f"Failed to load workflows from YAML: {e}")
    
    def _workflow_from_yaml(self, data: Dict) -> Optional[Workflow]:
        """Convert YAML workflow definition to Workflow object"""
        try:
            # Generate ID from name
            workflow_id = hashlib.md5(data['name'].encode()).hexdigest()[:16]
            
            # Parse trigger
            trigger_data = data['trigger']
            trigger = WorkflowTrigger(
                type=TriggerType(trigger_data['type']),
                condition=trigger_data['condition']
            )
            
            # Parse actions
            actions = []
            for action_data in data['actions']:
                action = WorkflowAction(
                    type=ActionType(action_data['type']),
                    params=action_data['params']
                )
                actions.append(action)
            
            workflow = Workflow(
                id=workflow_id,
                name=data['name'],
                description=data.get('description', ''),
                enabled=data.get('enabled', True),
                trigger=trigger,
                actions=actions
            )
            
            return workflow
        except Exception as e:
            logger.error(f"Failed to parse workflow from YAML: {e}")
            return None
    
    def _save_workflows(self):
        """Save workflows to disk"""
        workflows_file = self.storage_dir / 'workflows.json'
        try:
            data = {
                'workflows': [w.to_dict() for w in self.workflows.values()]
            }
            with open(workflows_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save workflows: {e}")
    
    def add_workflow(self, workflow: Workflow):
        """Add a new workflow"""
        self.workflows[workflow.id] = workflow
        self._save_workflows()
        logger.info(f"Added workflow: {workflow.name}")
    
    def remove_workflow(self, workflow_id: str):
        """Remove a workflow"""
        if workflow_id in self.workflows:
            del self.workflows[workflow_id]
            self._save_workflows()
            logger.info(f"Removed workflow: {workflow_id}")
    
    def enable_workflow(self, workflow_id: str, enabled: bool = True):
        """Enable/disable a workflow"""
        if workflow_id in self.workflows:
            self.workflows[workflow_id].enabled = enabled
            self._save_workflows()
    
    async def check_triggers(self, context: Dict[str, Any]):
        """Check all workflow triggers against current context"""
        triggered = []
        
        for workflow in self.workflows.values():
            if not workflow.enabled:
                continue
            
            if workflow.trigger.matches(context):
                # Check cooldown (don't run same workflow too frequently)
                if workflow.last_run:
                    elapsed = (datetime.now() - workflow.last_run).total_seconds()
                    if elapsed < 3600:  # 1 hour cooldown
                        continue
                
                triggered.append(workflow)
        
        return triggered
    
    async def run_loop(self):
        """Main automation loop"""
        self.running = True
        logger.info("Automation engine started")
        
        while self.running:
            try:
                # Get current context
                context = {}
                if self.daemon.monitor:
                    stats = await self.daemon.monitor.get_all_stats()
                    context.update(stats)
                
                if self.daemon.context:
                    ctx = await self.daemon.context.get_current_context()
                    context.update(ctx)
                
                # Check triggers
                triggered = await self.check_triggers(context)
                
                # Execute triggered workflows
                for workflow in triggered:
                    logger.info(f"Workflow triggered: {workflow.name}")
                    await workflow.execute(self.executor)
                    self._save_workflows()
                
                # Check for new suggestions every 10 minutes
                if datetime.now().minute % 10 == 0:
                    await self._check_suggestions()
                
            except Exception as e:
                logger.error(f"Automation loop error: {e}")
            
            await asyncio.sleep(self._check_interval)
    
    async def _check_suggestions(self):
        """Check for and present workflow suggestions"""
        suggestions = self.learner.get_suggestions()
        
        for suggestion in suggestions:
            # Send notification about suggestion
            if self.daemon.notifications:
                message = f"""💡 {suggestion['title']}

{suggestion['description']}
(Detected {suggestion['occurrences']} times, {int(suggestion['confidence']*100)}% confidence)

React with 👍 to automate this!"""
                
                await self.daemon.notifications.notify_ai_suggestion(message)
    
    def log_user_activity(self, activity_type: str, details: Dict):
        """Log user activity for pattern learning"""
        self.learner.log_activity(activity_type, details)
    
    def accept_suggestion(self, pattern_id: str):
        """Accept a workflow suggestion"""
        workflow = self.learner.accept_suggestion(pattern_id)
        if workflow:
            self.add_workflow(workflow)
            logger.info(f"Accepted suggestion, created workflow: {workflow.name}")
    
    def stop(self):
        """Stop the automation engine"""
        self.running = False
        logger.info("Automation engine stopped")
