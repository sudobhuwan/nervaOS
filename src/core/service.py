"""
NervaOS Core Service - Main AsyncIO daemon

This is the heart of NervaOS. It runs as a background service,
publishing a DBus interface that the UI connects to.
"""

import asyncio
import signal
import logging
from pathlib import Path
from typing import Optional

from dbus_next.aio import MessageBus
from dbus_next.service import ServiceInterface, method, signal as dbus_signal, dbus_property
from dbus_next import Variant, BusType

from .monitor import SystemMonitor
from .safety import SafetyManager
from .secrets import SecretsManager
from .smart_notifications import SmartNotificationManager
from .automation import AutomationEngine
from .custom_alerts import CustomAlertEngine

try:
    from .voice import VoiceManager
except ImportError as e:
    VoiceManager = None  # type: ignore[misc, assignment]
    logger.warning("Voice not available (missing deps e.g. pygame): %s", e)
from .smart_search import SmartSearchEngine
from .chat_history import ChatHistory, ConversationManager
from .feature_pack import FeaturePack
from ..integrations.web_search import WebSearchEngine
from ..integrations.code_assistant import CodeAssistant
from ..ai.client import AIClient
from ..ai.context import ContextEngine

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('nerva-service')


class NervaDaemonInterface(ServiceInterface):
    """
    DBus interface exposed at com.nervaos.daemon
    
    This is the API that the UI (and other apps) can call.
    """
    
    def __init__(self, daemon: 'NervaDaemon'):
        super().__init__('com.nervaos.daemon')
        self._daemon = daemon
        self._status = "idle"
    
    # ─────────────────────────────────────────────────────────────
    # Properties
    # ─────────────────────────────────────────────────────────────
    
    @dbus_property()
    def Status(self) -> 's':
        """Current daemon status: idle, processing, error"""
        return self._status
    
    @Status.setter
    def Status(self, value: 's'):
        self._status = value
    
    # ─────────────────────────────────────────────────────────────
    # Methods
    # ─────────────────────────────────────────────────────────────
    
    @method()
    async def Ping(self) -> 's':
        """Simple health check - returns 'pong' with CPU usage"""
        cpu = await self._daemon.monitor.get_cpu_percent()
        return f"pong (CPU: {cpu}%)"
    
    @method()
    async def GetSystemStatus(self) -> 'a{sv}':
        """Get comprehensive system status"""
        stats = await self._daemon.monitor.get_all_stats()
        # Convert to DBus variant dict
        return {k: Variant('s', str(v)) for k, v in stats.items()}
    
    @method()
    async def StartVoice(self) -> 's':
        """Start voice control"""
        if not self._daemon.voice:
            return "Voice control not initialized"
        
        if self._daemon.voice.enabled:
            return "Voice control already running"
        
        try:
            await self._daemon.voice.start()
            return "Voice control started successfully"
        except ValueError as e:
            # Missing API key or configuration issue
            error_msg = str(e)
            logger.error(f"Voice start failed (configuration): {error_msg}")
            return f"Configuration error: {error_msg}"
        except RuntimeError as e:
            # Missing dependencies
            error_msg = str(e)
            logger.error(f"Voice start failed (dependencies): {error_msg}")
            return f"Dependency error: {error_msg}"
        except Exception as e:
            # Other errors
            error_msg = f"Failed to start voice: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return error_msg
    
    @method()
    async def StopVoice(self) -> 's':
        """Stop voice control"""
        if not self._daemon.voice:
            return "Voice control not initialized"
        
        if not self._daemon.voice.enabled:
            return "Voice control not running"
        
        try:
            self._daemon.voice.stop()
            return "Voice control stopped"
        except Exception as e:
            logger.error(f"Failed to stop voice: {e}")
            return f"Failed to stop voice: {str(e)}"
    
    @method()
    async def GetVoiceStatus(self) -> 's':
        """Get voice control status"""
        if not self._daemon.voice:
            return "not_initialized"
        
        if not self._daemon.voice.enabled:
            return "disabled"
        
        if hasattr(self._daemon.voice, 'nerva') and self._daemon.voice.nerva:
            if self._daemon.voice.nerva.is_awake:
                return "listening"
            return "sleeping"
        
        return "active"
    
    # ─────────────────────────────────────────────────────────────
    # Chat History Methods
    # ─────────────────────────────────────────────────────────────
    
    @method()
    async def GetConversations(self, limit: 'i') -> 'aa{sv}':
        """Get recent conversations"""
        try:
            if not self._daemon.chat_history:
                return []
            
            conversations = await self._daemon.chat_history.get_recent_conversations(limit)
            
            # Return dicts with Variant-wrapped values for DBus
            result = []
            for conv in conversations:
                result.append({
                    'id': Variant('i', conv['id']),
                    'title': Variant('s', conv['title'] or ''),
                    'created_at': Variant('s', conv['created_at'] or ''),
                    'updated_at': Variant('s', conv['updated_at'] or ''),
                    'message_count': Variant('i', conv['message_count'] or 0)
                })
            
            return result
        except Exception as e:
            logger.error(f"Failed to get conversations: {e}")
            return []
    
    @method()
    async def GetConversationMessages(self, conversation_id: 'i') -> 'aa{sv}':
        """Get all messages in a conversation"""
        try:
            if not self._daemon.chat_history:
                return []
            
            messages = await self._daemon.chat_history.get_conversation_messages(conversation_id)
            
            # Return dicts with Variant-wrapped values for DBus
            result = []
            for msg in messages:
                result.append({
                    'id': Variant('i', msg['id']),
                    'role': Variant('s', msg['role'] or 'assistant'),
                    'content': Variant('s', msg['content'] or ''),
                    'timestamp': Variant('s', msg['timestamp'] or '')
                })
            
            return result
        except Exception as e:
            logger.error(f"Failed to get messages: {e}")
            return []
    
    @method()
    async def SearchMessages(self, query: 's', limit: 'i') -> 'aa{sv}':
        """Search messages by content"""
        try:
            if not self._daemon.chat_history:
                return []
            
            results = await self._daemon.chat_history.search_messages(query, limit)
            
            # Return dicts with Variant-wrapped values for DBus
            result = []
            for res in results:
                result.append({
                    'message_id': Variant('i', res['message_id']),
                    'conversation_id': Variant('i', res['conversation_id']),
                    'role': Variant('s', res['role'] or 'assistant'),
                    'content': Variant('s', res['content'][:200] if res.get('content') else ''),  # Preview
                    'timestamp': Variant('s', res['timestamp'] or ''),
                    'conversation_title': Variant('s', res['conversation_title'] or '')
                })
            
            return result
        except Exception as e:
            logger.error(f"Failed to search messages: {e}")
            return []
    
    @method()
    async def GetHistoryStats(self) -> 'a{sv}':
        """Get chat history statistics"""
        try:
            if not self._daemon.chat_history:
                return {}
            
            stats = await self._daemon.chat_history.get_stats()
            # Return dict with Variant-wrapped values for DBus
            return {
                'total_conversations': Variant('i', stats.get('total_conversations', 0)),
                'total_messages': Variant('i', stats.get('total_messages', 0)),
                'user_messages': Variant('i', stats.get('user_messages', 0)),
                'ai_messages': Variant('i', stats.get('ai_messages', 0))
            }
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {}
    
    @method()
    async def LoadConversation(self, conversation_id: 'i') -> 'b':
        """Switch to a conversation"""
        try:
            if not self._daemon.conversation_mgr:
                return False
            
            await self._daemon.conversation_mgr.switch_conversation(conversation_id)
            return True
        except Exception as e:
            logger.error(f"Failed to load conversation: {e}")
            return False
    
    @method()
    async def NewConversation(self, title: 's') -> 'i':
        """Create a new conversation"""
        try:
            if not self._daemon.conversation_mgr:
                return -1
            
            conv_id = await self._daemon.conversation_mgr.start_new_conversation(title)
            return conv_id
        except Exception as e:
            logger.error(f"Failed to create conversation: {e}")
            return -1
    
    @method()
    async def DeleteConversation(self, conversation_id: 'i') -> 'b':
        """Delete a conversation"""
        try:
            if not self._daemon.chat_history:
                return False
            
            await self._daemon.chat_history.delete_conversation(conversation_id)
            
            # If this was the current conversation, start a new one
            if (self._daemon.conversation_mgr and 
                self._daemon.conversation_mgr.current_conversation_id == conversation_id):
                await self._daemon.conversation_mgr.start_new_conversation()
            
            return True
        except Exception as e:
            logger.error(f"Failed to delete conversation: {e}")
            return False
    
    @method()
    async def UpdateConversationTitle(self, conversation_id: 'i', title: 's') -> 'b':
        """Update conversation title"""
        try:
            if not self._daemon.chat_history:
                return False
            
            await self._daemon.chat_history.update_conversation_title(conversation_id, title)
            return True
        except Exception as e:
            logger.error(f"Failed to update conversation title: {e}")
            return False
    
    @method()
    async def DeleteAllConversations(self) -> 'i':
        """Delete all conversations and return count deleted. UI creates new conv via NewConversation."""
        try:
            if not self._daemon.chat_history:
                return 0
            
            count = await self._daemon.chat_history.delete_all_conversations()
            
            # Clear current conv; do NOT create a new one – UI will call NewConversation
            if self._daemon.conversation_mgr:
                self._daemon.conversation_mgr.current_conversation_id = None
            
            logger.info(f"Deleted {count} conversations (bulk operation)")
            return count
        except Exception as e:
            logger.error(f"Failed to delete all conversations: {e}")
            return 0
    
    @method()
    async def AskAI(self, query: 's') -> 's':
        """
        Send a query to the AI and get a response.
        
        This method:
        1. Gathers current context (active window, system state)
        2. Formats the prompt with context
        3. Sends to AI provider
        4. If AI requests action (execute, create_file), performs it
        5. Returns the response
        """
        import json
        from pathlib import Path
        import os
        
        self._status = "processing"
        self.StatusChanged("processing")
        
        try:
            # Ensure conversation exists early so follow-up context is available.
            if self._daemon.conversation_mgr and self._daemon.conversation_mgr.current_conversation_id is None:
                await self._daemon.conversation_mgr.start_new_conversation()

            # Gather context
            context = await self._daemon.context.get_current_context()
            conv_id = self._daemon.conversation_mgr.current_conversation_id if self._daemon.conversation_mgr else None

            # Attach recent conversation memory to context.
            if conv_id and self._daemon.chat_history:
                try:
                    recent_msgs = await self._daemon.chat_history.get_conversation_context(conv_id, last_n_messages=8)
                    if recent_msgs:
                        context['recent_messages'] = recent_msgs
                except Exception as e:
                    logger.debug(f"Could not load recent messages for context: {e}")

            # Attach last action summary (if any) for ambiguous follow-ups like "still not".
            if conv_id and conv_id in self._daemon.action_memory:
                context['last_action_summary'] = self._daemon.action_memory.get(conv_id, "")

            # Built-in deterministic feature pack (slash commands).
            # If query starts with '/', NEVER route to AI. This prevents accidental
            # LLM tool-calls like create_file/sudo suggestions for slash commands.
            response = None
            stripped_query = query.strip()

            # Deterministic routing for common system intents so AI does not
            # generate unnecessary commands for simple checks.
            lowered_query = stripped_query.lower()
            if self._daemon.feature_pack and not stripped_query.startswith('/'):
                wifi_intent = (
                    ("wifi" in lowered_query or "wi-fi" in lowered_query or "ssid" in lowered_query)
                    and any(k in lowered_query for k in ("connected", "connection", "which", "name", "current"))
                )
                ip_intent = (
                    "ip address" in lowered_query
                    or ("my ip" in lowered_query)
                    or ("local ip" in lowered_query)
                )
                if wifi_intent:
                    response = await self._daemon.feature_pack.handle("/wifi")
                elif ip_intent:
                    ok, out = await self._daemon.safety.safe_execute_command("ip -4 addr show")
                    if ok:
                        # Keep response short and practical
                        import re
                        ips = re.findall(r'inet\s+(\d+\.\d+\.\d+\.\d+)', out)
                        if ips:
                            response = f"Your local IP address is `{ips[0]}`."
                        else:
                            response = "Could not detect a local IPv4 address right now."
                    else:
                        response = f"Could not read local IP address: {out}"

            if stripped_query.startswith('/'):
                if self._daemon.feature_pack:
                    response = await self._daemon.feature_pack.handle(stripped_query)
                if response is None:
                    response = "Unknown slash command. Use `/features` to see available built-in commands."
                
                # Save and return immediately; skip JSON action parsing entirely.
                if self._daemon.conversation_mgr:
                    try:
                        await self._daemon.conversation_mgr.send_message(query)
                        await self._daemon.conversation_mgr.add_ai_response(response)
                    except Exception as e:
                        logger.warning(f"Failed to save slash-command messages: {e}")
                self._status = "idle"
                self.StatusChanged("idle")
                self.ResponseReady(response)
                return response

            # Default AI flow for normal queries
            if response is None:
                if not self._daemon.ai_client or not self._daemon.ai_client.is_available():
                    return (
                        "AI provider is not configured yet. Open Settings -> AI Provider, "
                        "add API key, then retry. You can still use slash commands like "
                        "`/health`, `/wifi`, `/netcheck`, `/features`."
                    )
                response = await self._daemon.ai_client.ask(query, context)
            
            # Check if AI wants to perform an action
            response_stripped = response.strip()
            
            # Robust JSON Extraction
            json_str = None
            import re
            import json
            
            # 1. Try to find JSON block in markdown
            json_block_match = re.search(r'```json\s*(\{.*?\})\s*```', response_stripped, re.DOTALL)
            if json_block_match:
                json_str = json_block_match.group(1)
            
            # 2. Try to find raw JSON object (bracket to bracket)
            elif '{' in response_stripped and '}' in response_stripped:
                # Find first { and last }
                start = response_stripped.find('{')
                end = response_stripped.rfind('}') + 1
                potential_json = response_stripped[start:end]
                try:
                    # Verify it's valid JSON
                    json.loads(potential_json)
                    json_str = potential_json
                except:
                    pass
            
            if json_str:
                try:
                    action_request = json.loads(json_str)
                    
                    # Handle command execution
                    if 'execute' in action_request:
                        command = action_request['execute']
                        logger.info(f"AI requested command execution: {command}")
                        
                        # Check if this is an application launcher
                        app_launchers = [
                            'google-chrome', 'chromium-browser', 'firefox', 'brave-browser',
                            'code', 'cursor', 'gedit', 'xed', 'sublime_text',
                            'vlc', 'mpv', 'spotify', 'rhythmbox',
                            'nemo', 'nautilus', 'thunar',
                            'gnome-terminal', 'tilix', 'terminator', 'konsole',
                            'libreoffice', 'gimp', 'inkscape', 'blender',
                            'discord', 'slack', 'telegram-desktop', 'xdg-open',
                            'gio open', 'gtk-launch'
                        ]
                        
                        is_app_launch = any(launcher in command for launcher in app_launchers) or command.strip().lower().startswith(
                            ('open ', 'launch ', 'start ', 'run ')
                        )
                        
                        if is_app_launch:
                            # Launch app in background (don't wait for output)
                            try:
                                launch_cmd = command.strip()
                                app_name = launch_cmd.split()[0] if launch_cmd else "app"

                                if self._daemon.feature_pack:
                                    ok, msg = await self._daemon.feature_pack.open_target(launch_cmd)
                                    if not ok:
                                        raise RuntimeError(msg)
                                    response = f"✅ {msg}"
                                else:
                                    import subprocess
                                    import shlex
                                    import shutil
                                    low = launch_cmd.lower()

                                    # Common normalization for Cursor app launch intents
                                    if "cursor" in low:
                                        if shutil.which("cursor"):
                                            launch_cmd = "cursor"
                                        elif shutil.which("code"):
                                            launch_cmd = "code"

                                    # Prefer non-shell launch for reliability/safety
                                    if any(x in launch_cmd for x in ['|', '&&', '||', ';', '$(', '`']):
                                        proc = subprocess.Popen(
                                            launch_cmd,
                                            shell=True,
                                            stdout=subprocess.DEVNULL,
                                            stderr=subprocess.DEVNULL,
                                            start_new_session=True
                                        )
                                    else:
                                        argv = shlex.split(launch_cmd)
                                        if not argv:
                                            raise RuntimeError("Empty launch command")
                                        if argv[0] != "xdg-open" and not shutil.which(argv[0]):
                                            raise RuntimeError(f"App not found in PATH: {argv[0]}")
                                        proc = subprocess.Popen(
                                            argv,
                                            stdout=subprocess.DEVNULL,
                                            stderr=subprocess.DEVNULL,
                                            start_new_session=True
                                        )

                                    # Quick health check: process should not terminate immediately with error.
                                    await asyncio.sleep(0.35)
                                    if proc.poll() not in (None, 0):
                                        raise RuntimeError(f"Launcher exited early with code {proc.returncode}")
                                    response = f"✅ Launched {app_name}!"
                                if conv_id:
                                    self._daemon.action_memory[conv_id] = (
                                        f"Last action: launched `{app_name}` using `{launch_cmd}`."
                                    )
                                
                                # Log for pattern learning
                                if self._daemon.automation:
                                    self._daemon.automation.log_user_activity(
                                        'app_launch',
                                        {'app': app_name, 'via': 'ai_command'}
                                    )
                            except Exception as e:
                                response = f"❌ Failed to launch app: {str(e)}"
                        else:
                            # Regular command execution
                            # Replace /home/user and ~ with actual home directory
                            home = str(Path.home())
                            command = command.replace('/home/user', home)
                            command = command.replace('~/', f'{home}/')
                            command = command.replace(' ~', f' {home}')  # Handle ~ at start of args
                            success, output = await self._daemon.safety.safe_execute_command(command)
                            
                            if success:
                                follow_up = f"""The user asked: "{query}"
I executed: {command}
Output:
```
{output}
```
Give a clear, concise answer. Be direct and natural - no verbose structures or numbered sections. Just explain what the output means in simple terms."""
                                response = await self._daemon.ai_client.ask(follow_up, context)
                                if conv_id:
                                    self._daemon.action_memory[conv_id] = (
                                        f"Last action: executed `{command}` successfully."
                                    )
                            else:
                                response = f"I tried to check your system but encountered an issue: {output}"
                                if conv_id:
                                    self._daemon.action_memory[conv_id] = (
                                        f"Last action failed: `{command}` with error `{output}`."
                                    )
                    
                    # Handle file creation
                    elif 'create_file' in action_request:
                        file_info = action_request['create_file']
                        file_path = file_info.get('path', '')
                        file_content = file_info.get('content', '')
                        
                        # Replace /home/user with actual home directory
                        file_path = file_path.replace('/home/user', str(Path.home()))
                        
                        logger.info(f"AI requested file creation: {file_path}")
                        
                        # Validate path
                        is_safe, reason = self._daemon.safety.validate_path(file_path)
                        
                        if is_safe or file_path.startswith('/tmp') or file_path.startswith(str(Path.home())):
                            try:
                                import subprocess
                                
                                # Create parent directories if needed
                                Path(file_path).parent.mkdir(parents=True, exist_ok=True)
                                
                                # Write the file
                                with open(file_path, 'w') as f:
                                    f.write(file_content)
                                
                                # Auto-open HTML files in browser
                                if file_path.endswith('.html') or file_path.endswith('.htm'):
                                    subprocess.Popen(['xdg-open', file_path], 
                                                   stdout=subprocess.DEVNULL, 
                                                   stderr=subprocess.DEVNULL)
                                    response = f"✅ Created and opened `{file_path}` in your browser!"
                                else:
                                    # For other files, just open with default app
                                    subprocess.Popen(['xdg-open', file_path],
                                                   stdout=subprocess.DEVNULL,
                                                   stderr=subprocess.DEVNULL)
                                    response = f"✅ Created and opened `{file_path}`!"
                                
                            except Exception as e:
                                response = f"❌ Failed to create file: {str(e)}"
                        else:
                            response = f"❌ Cannot create file at that location: {reason}"
                    
                    # Handle file editing
                    elif 'edit_file' in action_request:
                        edit_info = action_request['edit_file']
                        file_path = edit_info.get('path', '')
                        instruction = edit_info.get('instruction', query)  # Use original query if no instruction
                        
                        # Replace /home/user with actual home directory
                        file_path = file_path.replace('/home/user', str(Path.home()))
                        
                        logger.info(f"AI requested file edit: {file_path}")
                        
                        # Check if file exists
                        if not Path(file_path).exists():
                            # Maybe they're referring to recently created file
                            # Try to find it in home directory
                            home_files = list(Path.home().glob('*.html')) + list(Path.home().glob('*.py'))
                            if home_files:
                                # Use the most recently modified file
                                file_path = str(max(home_files, key=lambda p: p.stat().st_mtime))
                                logger.info(f"Using most recent file: {file_path}")
                        
                        if Path(file_path).exists():
                            try:
                                import subprocess
                                
                                # Read current content
                                with open(file_path, 'r') as f:
                                    current_content = f.read()
                                
                                # Ask AI to edit the file
                                edit_prompt = f"""Edit the following file based on this instruction:

INSTRUCTION: {instruction}

CURRENT FILE CONTENT:
```
{current_content}
```

Respond with ONLY the complete new file content. No explanations, no markdown code blocks, just the raw file content."""
                                
                                new_content = await self._daemon.ai_client.ask(edit_prompt, context)
                                
                                # Clean up response (remove markdown if present)
                                new_content = new_content.strip()
                                if new_content.startswith('```'):
                                    lines = new_content.split('\n')
                                    if lines[0].startswith('```'):
                                        lines = lines[1:]
                                    if lines[-1].strip() == '```':
                                        lines = lines[:-1]
                                    new_content = '\n'.join(lines)
                                
                                # Write the updated content
                                with open(file_path, 'w') as f:
                                    f.write(new_content)
                                
                                # Auto-open the file
                                subprocess.Popen(['xdg-open', file_path],
                                               stdout=subprocess.DEVNULL,
                                               stderr=subprocess.DEVNULL)
                                
                                response = f"✅ Updated `{file_path}` and reopened it!"
                                
                            except Exception as e:
                                response = f"❌ Failed to edit file: {str(e)}"
                        else:
                            response = f"❌ File not found: {file_path}"
                    
                    # Handle file organization
                    elif 'organize' in action_request:
                        import subprocess
                        import shutil
                        
                        org_info = action_request['organize']
                        target_path = org_info.get('path', '').replace('/home/user', str(Path.home()))
                        action = org_info.get('action', 'sort_by_type')
                        
                        logger.info(f"AI requested file organization: {target_path}")
                        
                        if Path(target_path).exists() and Path(target_path).is_dir():
                            try:
                                # Define categories
                                categories = {
                                    'Images': ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp'],
                                    'Documents': ['.pdf', '.doc', '.docx', '.txt', '.odt', '.xls', '.xlsx', '.pptx'],
                                    'Videos': ['.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv'],
                                    'Audio': ['.mp3', '.wav', '.flac', '.aac', '.ogg'],
                                    'Archives': ['.zip', '.tar', '.gz', '.rar', '.7z'],
                                    'Code': ['.py', '.js', '.html', '.css', '.java', '.cpp', '.c', '.go', '.rs'],
                                    'ISOs': ['.iso', '.img'],
                                }
                                
                                moved_count = 0
                                target = Path(target_path)
                                
                                for file in target.iterdir():
                                    if file.is_file():
                                        ext = file.suffix.lower()
                                        for category, extensions in categories.items():
                                            if ext in extensions:
                                                cat_dir = target / category
                                                cat_dir.mkdir(exist_ok=True)
                                                shutil.move(str(file), str(cat_dir / file.name))
                                                moved_count += 1
                                                break
                                
                                # Open the folder
                                subprocess.Popen(['xdg-open', target_path],
                                               stdout=subprocess.DEVNULL,
                                               stderr=subprocess.DEVNULL)
                                
                                response = f"✅ Organized {moved_count} files into categories in `{target_path}`!"
                                
                            except Exception as e:
                                response = f"❌ Failed to organize: {str(e)}"
                        else:
                            response = f"❌ Directory not found: {target_path}"
                    
                    # Handle system diagnosis
                    elif 'diagnose' in action_request:
                        import subprocess
                        
                        diag_info = action_request['diagnose']
                        issue = diag_info.get('issue', 'general')
                        
                        logger.info(f"AI requested system diagnosis: {issue}")
                        
                        try:
                            # Gather diagnostic info
                            diag_data = {}
                            
                            # Top processes by memory
                            result = subprocess.run(['ps', 'aux', '--sort=-%mem'], 
                                                  capture_output=True, text=True, timeout=10)
                            diag_data['top_mem'] = '\n'.join(result.stdout.split('\n')[:6])
                            
                            # Top processes by CPU
                            result = subprocess.run(['ps', 'aux', '--sort=-%cpu'],
                                                  capture_output=True, text=True, timeout=10)
                            diag_data['top_cpu'] = '\n'.join(result.stdout.split('\n')[:6])
                            
                            # Disk usage
                            result = subprocess.run(['df', '-h', '/'],
                                                  capture_output=True, text=True, timeout=10)
                            diag_data['disk'] = result.stdout
                            
                            # Recent errors from journal
                            result = subprocess.run(['journalctl', '-p', 'err', '-n', '10', '--no-pager'],
                                                  capture_output=True, text=True, timeout=10)
                            diag_data['errors'] = result.stdout if result.stdout else "No recent errors"
                            
                            # Ask AI to analyze
                            diag_prompt = f"""Analyze this system diagnostic data. Give a clear, concise explanation of what's wrong:

ISSUE REPORTED: {issue}

TOP MEMORY PROCESSES:
{diag_data['top_mem']}

TOP CPU PROCESSES:
{diag_data['top_cpu']}

DISK USAGE:
{diag_data['disk']}

RECENT SYSTEM ERRORS:
{diag_data['errors']}

Be direct and concise. If you can fix it automatically, suggest the command."""
                            
                            response = await self._daemon.ai_client.ask(diag_prompt, context)
                            
                        except Exception as e:
                            response = f"❌ Diagnosis failed: {str(e)}"
                    
                    # Handle script execution
                    elif 'run_script' in action_request:
                        import subprocess
                        import tempfile
                        
                        script_info = action_request['run_script']
                        script_type = script_info.get('type', 'python')
                        script_code = script_info.get('code', '')
                        
                        logger.info(f"AI requested script execution: {script_type}")
                        
                        try:
                            # Write script to temp file
                            suffix = '.py' if script_type == 'python' else '.sh'
                            with tempfile.NamedTemporaryFile(mode='w', suffix=suffix, delete=False) as f:
                                f.write(script_code)
                                script_path = f.name
                            
                            # Execute
                            if script_type == 'python':
                                cmd = ['python3', script_path]
                            else:
                                os.chmod(script_path, 0o755)
                                cmd = ['bash', script_path]
                            
                            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                            
                            # Clean up
                            os.unlink(script_path)
                            
                            output = result.stdout if result.stdout else result.stderr
                            response = f"✅ Script executed!\n\n**Output:**\n```\n{output[:2000]}\n```"
                            
                        except subprocess.TimeoutExpired:
                            response = "❌ Script timed out after 30 seconds"
                        except Exception as e:
                            response = f"❌ Script failed: {str(e)}"
                    
                    # Handle file search
                    elif 'search_files' in action_request:
                        search_info = action_request['search_files']
                        query = search_info.get('query', '')
                        
                        logger.info(f"AI requested file search: {query}")
                        
                        try:
                            if self._daemon.smart_search:
                                # Use AI-powered semantic search
                                results = await self._daemon.smart_search.smart_search(query, max_results=5)
                                
                                if results:
                                    response_parts = [f"🔍 Found {len(results)} files matching '{query}':\n"]
                                    for i, file in enumerate(results, 1):
                                        size_mb = file.size / (1024 * 1024)
                                        response_parts.append(
                                            f"**{i}. {file.filename}**\n"
                                            f"   📁 Path: `{file.path}`\n"
                                            f"   📊 Size: {size_mb:.2f}MB | Type: {file.file_type}\n"
                                            f"   🕒 Modified: {file.modified.strftime('%Y-%m-%d %H:%M')}\n"
                                        )
                                    
                                    response = '\n'.join(response_parts)
                                else:
                                    response = f"❌ No files found matching '{query}'"
                            else:
                                response = "❌ Smart search not initialized"
                                
                        except Exception as e:
                            logger.error(f"File search failed: {e}")
                            response = f"❌ Search failed: {str(e)}"
                    
                    # Handle web search
                    elif 'web_search' in action_request:
                        search_info = action_request['web_search']
                        query = search_info.get('query', '')
                        
                        logger.info(f"AI requested web search: {query}")
                        
                        try:
                            if self._daemon.web_search:
                                result = await self._daemon.web_search.search_and_summarize(query, max_results=5)
                                
                                if result['results']:
                                    response_parts = [f"🌐 **Web Search: {query}**\n"]
                                    
                                    # Add summary
                                    if result.get('summary'):
                                        response_parts.append(f"📝 **Summary:**\n{result['summary']}\n")
                                    
                                    response_parts.append("\n**Sources:**\n")
                                    
                                    # Add all sources
                                    for i, r in enumerate(result['results'][:5], 1):
                                        response_parts.append(
                                            f"{i}. **{r.title}**\n"
                                            f"   {r.snippet}\n"
                                            f"   🔗 {r.url}\n"
                                        )
                                    
                                    response = '\n'.join(response_parts)
                                    logger.info(f"Web search response length: {len(response)} chars, sources: {len(result['results'])}")
                                else:
                                    response = (
                                        f"❌ No web results found for '{query}'.\n"
                                        f"Try a more specific query, e.g. include location or version number."
                                    )
                            else:
                                response = (
                                    "❌ Web search engine not available right now.\n"
                                    "You can still ask me to run direct commands, or retry shortly."
                                )
                                
                        except Exception as e:
                            logger.error(f"Web search failed: {e}")
                            response = (
                                f"❌ Web search failed: {str(e)}\n"
                                "Fallback options:\n"
                                "1. Ask with `/netcheck` to diagnose internet\n"
                                "2. Ask a command directly (example: `curl -I https://example.com`)\n"
                                "3. Retry with a narrower query"
                            )
                    
                    # Handle git status
                    elif 'git_status' in action_request:
                        logger.info("AI requested git status")
                        try:
                            if self._daemon.code_assistant:
                                git_status = self._daemon.code_assistant.get_git_status()
                                if git_status:
                                    response_parts = [f"📊 **Git Status**\n"]
                                    response_parts.append(f"**Branch:** {git_status.branch}\n")
                                    
                                    if git_status.ahead or git_status.behind:
                                        response_parts.append(f"**Sync:** ↑{git_status.ahead} ↓{git_status.behind}\n")
                                    
                                    if git_status.staged:
                                        response_parts.append(f"\n**✅ Staged ({len(git_status.staged)}):**\n")
                                        for f in git_status.staged[:5]:
                                            response_parts.append(f"  • {f}\n")
                                    
                                    if git_status.unstaged:
                                        response_parts.append(f"\n**📝 Modified ({len(git_status.unstaged)}):**\n")
                                        for f in git_status.unstaged[:5]:
                                            response_parts.append(f"  • {f}\n")
                                    
                                    if git_status.untracked:
                                        response_parts.append(f"\n**❓ Untracked ({len(git_status.untracked)}):**\n")
                                        for f in git_status.untracked[:5]:
                                            response_parts.append(f"  • {f}\n")
                                    
                                    if not git_status.staged and not git_status.unstaged and not git_status.untracked:
                                        response_parts.append("\n✨ Working tree clean!\n")
                                    
                                    response = ''.join(response_parts)
                                else:
                                    response = "❌ Not a git repository"
                            else:
                                response = "❌ Code assistant not available"
                        except Exception as e:
                            logger.error(f"Git status failed: {e}")
                            response = f"❌ Git status failed: {str(e)}"
                    
                    # Handle git log
                    elif 'git_log' in action_request:
                        count = action_request['git_log'].get('count', 5)
                        logger.info(f"AI requested git log (n={count})")
                        try:
                            if self._daemon.code_assistant:
                                commits = self._daemon.code_assistant.get_git_log(n=count)
                                if commits:
                                    response_parts = [f"📜 **Recent Commits ({len(commits)})**\n\n"]
                                    for commit in commits:
                                        response_parts.append(
                                            f"**{commit['hash']}** - {commit['message']}\n"
                                            f"   👤 {commit['author']} • 🕒 {commit['time']}\n\n"
                                        )
                                    response = ''.join(response_parts)
                                else:
                                    response = "❌ No commits found or not a git repository"
                            else:
                                response = "❌ Code assistant not available"
                        except Exception as e:
                            logger.error(f"Git log failed: {e}")
                            response = f"❌ Git log failed: {str(e)}"
                    
                    # Handle code analysis
                    elif 'code_analyze' in action_request:
                        action = action_request['code_analyze'].get('action', 'explain')
                        code = action_request['code_analyze'].get('code', '')
                        logger.info(f"AI requested code {action}")
                        try:
                            if self._daemon.code_assistant and code:
                                if action == 'explain':
                                    result = await self._daemon.code_assistant.explain_code(code)
                                elif action == 'bugs':
                                    result = await self._daemon.code_assistant.find_bugs(code)
                                else:
                                    result = "Unknown analysis action"
                                
                                response = f"💻 **Code {action.title()}**\n\n{result}"
                            else:
                                response = "❌ Code assistant not available or no code provided"
                        except Exception as e:
                            logger.error(f"Code analysis failed: {e}")
                            response = f"❌ Code analysis failed: {str(e)}"
                    
                    # Handle project info
                    elif 'project_info' in action_request:
                        logger.info("AI requested project info")
                        try:
                            if self._daemon.code_assistant:
                                project = self._daemon.code_assistant.detect_project()
                                if project:
                                    response = (
                                        f"📁 **Project: {project.name}**\n\n"
                                        f"**Language:** {project.language}\n"
                                        f"**Framework:** {project.framework or 'Not detected'}\n"
                                        f"**Path:** {project.path}\n"
                                        f"**Files:** {project.files_count}\n"
                                    )
                                else:
                                    response = "❌ Could not detect project information"
                            else:
                                response = "❌ Code assistant not available"
                        except Exception as e:
                            logger.error(f"Project info failed: {e}")
                            response = f"❌ Project info failed: {str(e)}"
                        
                except json.JSONDecodeError:
                    # Not valid JSON, just return the response as-is
                    pass
            
            # Save to chat history - ensure conversation exists
            if self._daemon.conversation_mgr:
                # Ensure we have an active conversation
                if self._daemon.conversation_mgr.current_conversation_id is None:
                    await self._daemon.conversation_mgr.start_new_conversation()
                    logger.info(f"Created new conversation {self._daemon.conversation_mgr.current_conversation_id} for message")
                
                # Save messages
                # Save messages
                try:
                    await self._daemon.conversation_mgr.send_message(query)
                    await self._daemon.conversation_mgr.add_ai_response(response)
                except Exception as e:
                    logger.warning(f"Failed to save messages to history (attempt 1): {e}")
                    # If FK error or similar, current_conversation_id might be invalid/stale
                    # Force a new conversation and retry
                    try:
                        logger.info("Starting new conversation and retrying history save...")
                        await self._daemon.conversation_mgr.start_new_conversation()
                        await self._daemon.conversation_mgr.send_message(query)
                        await self._daemon.conversation_mgr.add_ai_response(response)
                        logger.info(f"Retry successful. New Conv ID: {self._daemon.conversation_mgr.current_conversation_id}")
                    except Exception as e2:
                        logger.error(f"Failed to save messages to history (attempt 2): {e2}")
                        # Don't fail the entire request; user should still see the response in UI
                        # but history will be missing for this turn.

                logger.info(f"Saved message to conversation {self._daemon.conversation_mgr.current_conversation_id}")
                
                # Auto-generate title from first user message if title is generic
                if self._daemon.conversation_mgr.current_conversation_id:
                    conv_id = self._daemon.conversation_mgr.current_conversation_id
                    # Get conversation to check title
                    convs = await self._daemon.chat_history.get_recent_conversations(1)
                    if convs and convs[0]['id'] == conv_id:
                        title = convs[0].get('title', '')
                        # If title is generic, generate from first message
                        if title in ['New Chat', 'Chat', None, ''] or title.startswith('Chat '):
                            # Use first 50 chars of query as title
                            new_title = query[:50].strip()
                            if len(query) > 50:
                                new_title += '...'
                            await self._daemon.chat_history.update_conversation_title(conv_id, new_title)
            
            self._status = "idle"
            self.StatusChanged("idle")
            self.ResponseReady(response)
            
            return response
            
        except Exception as e:
            self._status = "error"
            self.StatusChanged("error")
            error_msg = f"Error: {str(e)}"
            self.AlertTriggered(error_msg)
            return error_msg
    
    @method()
    async def EditFile(self, path: 's', instruction: 's') -> 'a{sv}':
        """
        Request AI to edit a file based on instruction.
        
        Returns a dict with:
        - success: bool
        - diff: str (if success)
        - error: str (if failure)
        - backup_path: str (if success)
        """
        self._status = "processing"
        self.StatusChanged("processing")
        
        try:
            # Validate path safety
            is_safe, reason = self._daemon.safety.validate_path(path)
            if not is_safe:
                return {
                    'success': Variant('b', False),
                    'error': Variant('s', reason)
                }
            
            # Read current content
            file_path = Path(path)
            if not file_path.exists():
                return {
                    'success': Variant('b', False),
                    'error': Variant('s', 'File does not exist')
                }
            
            original_content = file_path.read_text()
            
            # Get AI to generate new content
            context = await self._daemon.context.get_current_context()
            new_content = await self._daemon.ai_client.edit_file(
                original_content, instruction, context
            )
            
            # Generate diff
            diff = self._daemon.safety.generate_diff(original_content, new_content)
            
            # Store pending edit for approval
            operation_id = await self._daemon.safety.store_pending_edit(
                path, original_content, new_content
            )
            
            self._status = "idle"
            self.StatusChanged("idle")
            
            return {
                'success': Variant('b', True),
                'diff': Variant('s', diff),
                'operation_id': Variant('s', operation_id),
                'preview': Variant('s', new_content[:500])  # First 500 chars
            }
            
        except Exception as e:
            self._status = "error"
            self.StatusChanged("error")
            return {
                'success': Variant('b', False),
                'error': Variant('s', str(e))
            }
    
    @method()
    async def ApplyEdit(self, operation_id: 's') -> 'b':
        """Apply a pending file edit after user approval"""
        try:
            success = await self._daemon.safety.apply_pending_edit(operation_id)
            return success
        except Exception as e:
            logger.error(f"Failed to apply edit: {e}")
            return False
    
    @method()
    async def Undo(self, operation_id: 's') -> 'b':
        """Revert a file edit using the backup"""
        try:
            success = await self._daemon.safety.undo_edit(operation_id)
            return success
        except Exception as e:
            logger.error(f"Failed to undo: {e}")
            return False
    
    @method()
    async def SetAPIKey(self, provider: 's', key: 's') -> 'b':
        """Store an API key securely in the keyring"""
        try:
            self._daemon.secrets.set_api_key(provider, key)
            return True
        except Exception as e:
            logger.error(f"Failed to store API key: {e}")
            return False
    
    @method()
    async def ReloadSettings(self) -> 'b':
        """Reload AI client configuration from settings.json and .env file"""
        try:
            # Invalidate settings cache so we read fresh from disk.
            # The UI (different process) saves to settings.json; daemon caches in memory.
            from .settings import get_settings_manager
            get_settings_manager().reload()
            self._daemon.ai_client = AIClient.from_settings()
            provider_info = self._daemon.ai_client.get_provider_info()
            logger.info(f"Settings reloaded: {provider_info['provider']} / {provider_info['model']}")
            return True
        except Exception as e:
            logger.error(f"Failed to reload settings: {e}")
            return False
    
    @method()
    async def GetProviderInfo(self) -> 'a{ss}':
        """Get current AI provider information"""
        if self._daemon.ai_client:
            return self._daemon.ai_client.get_provider_info()
        return {"provider": "none", "model": "", "configured": "false"}
    
    @method()
    async def ExecuteCommand(self, command: 's') -> 'a{sv}':
        """
        Execute a safe, read-only command and return the output.
        
        Only allows informational commands like:
        - docker ps, docker images
        - ls, cat, grep
        - df, free, uptime
        - git status, git log
        
        Returns dict with:
        - success: bool
        - output: str (if success)
        - error: str (if failure)
        """
        try:
            success, output = await self._daemon.safety.safe_execute_command(command)
            
            if success:
                return {
                    'success': Variant('b', True),
                    'output': Variant('s', output)
                }
            else:
                return {
                    'success': Variant('b', False),
                    'error': Variant('s', output)
                }
        except Exception as e:
            logger.error(f"Command execution failed: {e}")
            return {
                'success': Variant('b', False),
                'error': Variant('s', str(e))
            }
    
    # ─────────────────────────────────────────────────────────────
    # Signals
    # ─────────────────────────────────────────────────────────────
    
    @dbus_signal()
    def ResponseReady(self, response: 's') -> 's':
        """Emitted when an AI response is ready"""
        return response
    
    @dbus_signal()
    def StatusChanged(self, status: 's') -> 's':
        """Emitted when daemon status changes"""
        return status
    
    @dbus_signal()
    def AlertTriggered(self, message: 's') -> 's':
        """Emitted when a system alert is triggered"""
        return message


class NervaDaemon:
    """
    Main daemon class that orchestrates all components.
    """
    
    def __init__(self):
        self.bus: Optional[MessageBus] = None
        self.interface: Optional[NervaDaemonInterface] = None
        self.running = False
        
        # Initialize components
        self.monitor = SystemMonitor()
        self.safety = SafetyManager()
        self.secrets = SecretsManager()
        self.context = ContextEngine()
        self.ai_client: Optional[AIClient] = None
        self.notifications: Optional[SmartNotificationManager] = None
        self.automation: Optional[AutomationEngine] = None
        self.voice: Optional[VoiceManager] = None
        self.custom_alerts = None  # Custom alert rules engine
        self.smart_search = None  # Smart search engine
        self.web_search = None  # Web search engine
        self.code_assistant = None  # Code assistant
        self.feature_pack = None  # Built-in slash-command features
        self.chat_history: Optional[ChatHistory] = None  # Chat history manager
        self.conversation_mgr: Optional[ConversationManager] = None  # Active conversation
        self.action_memory = {}  # conversation_id -> summary of last action/result
        
        # Monitoring settings
        self.monitor_interval = 5  # seconds
        self.ram_alert_threshold = 90
        self.cpu_alert_threshold = 95
        self.custom_alerts_interval = 10  # Check custom alerts every 10 seconds
    
    async def start(self):
        """Start the daemon and connect to DBus"""
        logger.info("Starting NervaOS daemon...")
        
        # Initialize AI client from settings.json (preferred) or .env file
        # This respects user's provider/model selection from settings
        self.ai_client = AIClient.from_settings()
        
        provider_info = self.ai_client.get_provider_info()
        logger.info(f"AI Client: {provider_info['provider']} / {provider_info['model']}")
        
        if not self.ai_client.is_available():
            logger.warning("AI Client not configured!")
            logger.warning("Please create .env file with GEMINI_API_KEY")
            logger.warning("Run: cp .env.example .env && nano .env")
        
        # Initialize smart notifications
        self.notifications = SmartNotificationManager(
            ai_client=self.ai_client,
            context_engine=self.context
        )
        logger.info("Smart notifications initialized")
        
        # Initialize automation engine
        automation_dir = Path.home() / '.config' / 'nervaos' / 'automation'
        self.automation = AutomationEngine(
            daemon=self,
            storage_dir=automation_dir
        )
        logger.info("Automation engine initialized")
        
        # Initialize voice control (optional; requires pygame etc.)
        self.voice = VoiceManager(daemon=self) if VoiceManager else None
        if self.voice:
            logger.info("Voice control initialized")
        else:
            logger.info("Voice control skipped (missing deps)")
        
        # Initialize custom alert rules
        alerts_dir = Path.home() / '.config' / 'nervaos' / 'alerts'
        self.custom_alerts = CustomAlertEngine(
            storage_path=alerts_dir,
            notification_callback=self._on_custom_alert
        )
        logger.info(f"Custom alerts initialized with {len(self.custom_alerts.get_all_rules())} rules")
        
        # Initialize smart search engine
        self.smart_search = SmartSearchEngine(ai_client=self.ai_client)
        logger.info("Smart search engine initialized")
        
        # Initialize web search engine
        self.web_search = WebSearchEngine(ai_client=self.ai_client)
        logger.info("Web search engine initialized")
        
        # Initialize code assistant
        self.code_assistant = CodeAssistant(ai_client=self.ai_client)
        logger.info("Code assistant initialized")

        # Initialize deterministic feature pack
        self.feature_pack = FeaturePack(daemon=self)
        logger.info("Feature pack initialized")
        
        # Initialize chat history
        self.chat_history = ChatHistory()
        await self.chat_history.initialize()
        self.conversation_mgr = ConversationManager(self.chat_history)
        await self.conversation_mgr.start_new_conversation()
        stats = await self.chat_history.get_stats()
        logger.info(f"Chat history initialized ({stats['total_conversations']} conversations, {stats['total_messages']} messages)")
        
        # Index files in background (non-blocking)
        asyncio.create_task(self._index_files_background())
        
        # Connect to session bus
        self.bus = await MessageBus(bus_type=BusType.SESSION).connect()
        
        # Create and export the interface
        self.interface = NervaDaemonInterface(self)
        self.bus.export('/com/nervaos/daemon', self.interface)
        
        # Request the service name
        await self.bus.request_name('com.nervaos.daemon')
        logger.info("DBus interface published at com.nervaos.daemon")
        
        self.running = True
        
        # Start the monitoring loop
        asyncio.create_task(self._monitoring_loop())
        
        # Start custom alerts monitoring loop
        if self.custom_alerts:
            asyncio.create_task(self._custom_alerts_loop())
        
        # Start the automation loop
        # DISABLED: Automation opens apps automatically which is irritating
        # if self.automation:
        #     asyncio.create_task(self.automation.run_loop())
        
        # Auto-start voice control (with retry logic)
        if self.voice:
            asyncio.create_task(self._auto_start_voice())
        
        logger.info("NervaOS daemon started successfully")
    
    async def _auto_start_voice(self):
        """Auto-start voice control with retry logic"""
        logger.info("Voice disabled for v1.0 - Coming in v2.0")
        return  # DISABLED
        if not self.voice:
            return
        
        max_retries = 3
        retry_delay = 5  # seconds
        
        for attempt in range(max_retries):
            try:
                await self.voice.start()
                logger.info("Voice control auto-started successfully")
                
                # Start monitoring loop to keep it running
                asyncio.create_task(self._voice_monitoring_loop())
                return
                
            except ValueError as e:
                # Configuration error (missing API key) - don't retry
                logger.warning(f"Voice control not started (configuration): {e}")
                logger.info("Voice control will start automatically once DEEPGRAM_API_KEY is configured")
                return
                
            except RuntimeError as e:
                # Dependency error - log but don't retry immediately
                if attempt < max_retries - 1:
                    logger.warning(f"Voice control start failed (attempt {attempt + 1}/{max_retries}): {e}")
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    await asyncio.sleep(retry_delay)
                else:
                    logger.error(f"Voice control failed to start after {max_retries} attempts: {e}")
                    logger.info("Install dependencies with: pip install pyaudio deepgram-sdk pyttsx3 pygame websockets")
                    
            except Exception as e:
                # Other errors - retry
                if attempt < max_retries - 1:
                    logger.warning(f"Voice control start failed (attempt {attempt + 1}/{max_retries}): {e}")
                    await asyncio.sleep(retry_delay)
                else:
                    logger.error(f"Voice control failed to start after {max_retries} attempts: {e}")
    
    async def _voice_monitoring_loop(self):
        """Monitor voice control and restart if it stops"""
        logger.info("Starting voice control monitoring loop")
        
        while self.running:
            try:
                await asyncio.sleep(30)  # Check every 30 seconds
                
                if not self.voice:
                    continue
                
                # Check if voice is supposed to be running but isn't
                if self.voice.enabled:
                    # Just check if enabled - NervaVoice runs in background threads
                    pass
                    # No need to restart - always-listening mode handles itself
                            
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in voice monitoring loop: {e}")
                await asyncio.sleep(30)
    
    async def _monitoring_loop(self):
        """Background loop that monitors system health"""
        logger.info("Starting system monitoring loop")
        
        while self.running:
            try:
                stats = await self.monitor.get_all_stats()
                
                # Check for alerts
                ram_percent = stats.get('ram_percent', 0)
                cpu_percent = stats.get('cpu_percent', 0)
                
                if ram_percent > self.ram_alert_threshold:
                    # Get detailed process info
                    top_procs = await self.monitor.get_top_processes_by_memory(1)
                    if top_procs:
                        top_proc = top_procs[0]
                        
                        # Send smart notification
                        if self.notifications:
                            await self.notifications.notify_high_ram(
                                ram_percent,
                                top_proc['name'],
                                top_proc['memory_mb']
                            )
                        
                        # Also send DBus signal for UI
                        if self.interface:
                            self.interface.AlertTriggered(
                                f"High RAM usage: {ram_percent}%. Top: {top_proc['name']}"
                            )
                
                if cpu_percent > self.cpu_alert_threshold:
                    if self.interface:
                        top_process = await self.monitor.get_top_cpu_process()
                        self.interface.AlertTriggered(
                            f"High CPU usage: {cpu_percent}%. Top: {top_process}"
                        )
                
            except Exception as e:
                logger.error(f"Monitoring error: {e}")
            
            await asyncio.sleep(self.monitor_interval)
    
    async def _custom_alerts_loop(self):
        """Background loop for custom alert rules"""
        logger.info("Starting custom alerts monitoring loop")
        
        while self.running:
            try:
                if self.custom_alerts:
                    self.custom_alerts.check_all_rules()
            except Exception as e:
                logger.error(f"Custom alerts error: {e}")
            
            await asyncio.sleep(self.custom_alerts_interval)
    
    def _on_custom_alert(self, title: str, message: str, urgency: str):
        """Handle custom alert notifications"""
        logger.info(f"Custom alert: {title} - {message}")
        
        # Send DBus signal for UI
        if self.interface:
            self.interface.AlertTriggered(f"{title}: {message}")
    
    async def _index_files_background(self):
        """Index files in the background without blocking startup"""
        try:
            # Wait a bit before starting to index
            await asyncio.sleep(10)
            
            if self.smart_search:
                logger.info("Starting background file indexing...")
                # Run indexing in executor to avoid blocking
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self.smart_search.index_directories)
                logger.info("Background file indexing complete")
        except Exception as e:
            logger.error(f"Background indexing failed: {e}")
    
    async def stop(self):
        """Gracefully stop the daemon"""
        logger.info("Stopping NervaOS daemon...")
        self.running = False
        
        # Stop voice control gracefully
        if self.voice and self.voice.enabled:
            try:
                self.voice.stop()
                logger.info("Voice control stopped")
            except Exception as e:
                logger.error(f"Error stopping voice control: {e}")
        
        if self.bus:
            self.bus.disconnect()
        
        logger.info("NervaOS daemon stopped")


async def main():
    """Main entry point for the daemon"""
    daemon = NervaDaemon()

    loop = asyncio.get_event_loop()

    def signal_handler():
        logger.info("Received shutdown signal")
        asyncio.create_task(daemon.stop())

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except (NotImplementedError, OSError, ValueError) as e:
            logger.debug(f"Could not add signal handler for {sig}: {e}")

    try:
        await daemon.start()
    except Exception as e:
        logger.error(f"Daemon startup failed: {e}", exc_info=True)
        raise

    try:
        while daemon.running:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        pass
    finally:
        await daemon.stop()


if __name__ == '__main__':
    import sys
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f"NervaOS daemon exited: {e}", exc_info=True)
        sys.exit(1)
