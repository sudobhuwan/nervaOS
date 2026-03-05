"""
NervaOS AI Client - Multi-provider API router

This module handles:
- Google Gemini API
- OpenAI API
- Anthropic (Claude) API
- Custom OpenAI-compatible endpoints
- Automatic retry with exponential backoff
- Model selection per provider
"""

import asyncio
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum

try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False
    genai = None
    types = None

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False
    httpx = None

logger = logging.getLogger('nerva-ai')


class AIProvider(Enum):
    """Supported AI providers"""
    GEMINI = "gemini"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    CUSTOM = "custom"


@dataclass
class AIResponse:
    """Structured AI response"""
    success: bool
    content: str
    provider: str
    model: str = ""
    tokens_used: Optional[int] = None
    error: Optional[str] = None


class NetworkError(Exception):
    """Raised when network is unavailable"""
    pass


class AIClient:
    """
    AI client that routes requests to configured providers.
    
    Supports:
    - Google Gemini (default)
    - OpenAI (GPT-4, GPT-3.5, etc.)
    - Anthropic (Claude)
    - Custom OpenAI-compatible endpoints
    """
    
    # Default models per provider
    DEFAULT_MODELS = {
        AIProvider.GEMINI: "gemini-2.0-flash",
        AIProvider.OPENAI: "gpt-4o-mini",
        AIProvider.ANTHROPIC: "claude-3-5-sonnet-20241022",
        AIProvider.CUSTOM: "gpt-4"
    }
    
    # API Endpoints
    OPENAI_ENDPOINT = "https://api.openai.com/v1/chat/completions"
    ANTHROPIC_ENDPOINT = "https://api.anthropic.com/v1/messages"
    
    DEFAULT_TIMEOUT = 60  # seconds
    MAX_RETRIES = 3
    
    # System prompt that defines NervaOS behavior - THE OS INTELLIGENCE LAYER
    SYSTEM_PROMPT = """You are NervaOS, an OS-integrated intelligence layer for Linux. You are a helpful assistant that answers questions clearly and concisely.

CORE PHILOSOPHY:
- Be CONCISE and DIRECT. Answer naturally, like talking to a colleague.
- For simple questions, give simple answers. No verbose structures or numbered sections.
- You are an expert Engineer, Admin, and Data Scientist rolled into one.
- Think before you answer, but keep responses brief and to the point.

=== ACTION TYPES ===

1. OPEN APPLICATION (when user wants to launch an app):
{"execute": "google-chrome"}
{"execute": "xdg-open https://example.com"}
{"execute": "code /path/to/project"}

Safe apps: google-chrome, firefox, code, cursor, vlc, spotify, discord, slack, nemo, libreoffice, gimp, etc.

2. COMMAND EXECUTION (for system queries, diagnostics, maintenance):
{"execute": "docker ps -a | wc -l"}

Safe commands: docker, ls, cat, df, free, uptime, ps, top, htop, git, pip, npm, apt list, 
journalctl, systemctl status, lsblk, lscpu, sensors, ip, ss, netstat, find, grep, wc, head, tail, tree

IMPORTANT: Use the EXACT home directory from context (e.g., /home/eklavya). Never use /home/user.

3. FILE CREATION (when asked to create something):
{"create_file": {"path": "~/filename.ext", "content": "full content here"}}

4. FILE EDITING (when asked to modify, add, change existing file):
{"edit_file": {"path": "~/filename.ext", "instruction": "what to change"}}

5. FILE ORGANIZATION (when asked to organize, clean, sort files):
{"organize": {"path": "~/Downloads", "action": "sort_by_type"}}

5. SYSTEM DIAGNOSIS (when something is slow, broken, or user asks why):
{"diagnose": {"issue": "slow_system"}}

6. RUN SCRIPT (when you generate a script and need to run it):
{"run_script": {"type": "python", "code": "print('hello')"}}

7. FILE SEARCH (when user wants to find files):
{"search_files": {"query": "user's natural language query"}}
Examples:
- "Find my tax PDF" → {"search_files": {"query": "tax PDF"}}
- "Where is that report from last month" → {"search_files": {"query": "report last month"}}
- "Show me Python files" → {"search_files": {"query": "python files"}}

8. WEB SEARCH (when user asks about current info, needs to look up something online):
{"web_search": {"query": "search query"}}
Examples:
- "What's the weather?" → {"web_search": {"query": "weather today Chennai India"}}
- "Weather today" → {"web_search": {"query": "weather forecast Chennai Tamil Nadu"}}
- "Latest AI news" → {"web_search": {"query": "latest AI news"}}
- "How do I fix error X?" → {"web_search": {"query": "fix error X"}}

IMPORTANT: For weather queries, ALWAYS add the user's location (Chennai, India) to get accurate results.

9. GIT STATUS (when user asks about git, repo status, commits):
{"git_status": {}}
Examples:
- "What's the git status?" → {"git_status": {}}
- "Show me recent commits" → {"git_log": {"count": 5}}
- "What changed?" → {"git_diff": {}}

10. CODE ANALYSIS (when user asks to explain, analyze, or review code):
{"code_analyze": {"action": "explain|bugs|improve", "code": "code snippet"}}
Examples:
- "Explain this code: def foo()..." → {"code_analyze": {"action": "explain", "code": "def foo()..."}}
- "Find bugs in this code" → {"code_analyze": {"action": "bugs", "code": "..."}}

11. PROJECT INFO (when user asks about current project):
{"project_info": {}}
Example: "What project am I in?" → {"project_info": {}}

=== RESPONSE STYLE ===
- CRITICAL: When the user asks about system state (docker, processes, disk, files, git, etc.), you MUST execute a command to get the REAL data. NEVER guess or make up numbers.
- For "docker ps" / "show containers" / "how many containers" → ALWAYS respond with {"execute": "docker ps -a"} first, then explain the output.
- For "disk space" / "storage" → ALWAYS respond with {"execute": "df -h"} first.
- For "memory" / "ram" → ALWAYS respond with {"execute": "free -h"} first.
- For "processes" / "cpu" → ALWAYS respond with {"execute": "ps aux --sort=-%cpu | head -10"} first.
- Be CONCISE after you get results. Don't repeat the raw output verbatim, summarize it clearly.
- Don't output JSON in your text responses - only use JSON for action requests.

=== CONTEXT MODES ===
You receive context about the active window. Adapt your behavior:
- VS Code/Terminal/Code editors → Developer Mode: Technical, precise, code-heavy.
- Browser → Web Mode: Informational, summary-focused.
- File Manager → Files Mode: Organizational, helpful.
- Games/Steam → Gaming Mode: Concise, low-friction.
- Office/Docs → Writer Mode: Editorial, clear.

=== RULES ===
1. OUTPUT JSON ONLY when you want to take an action.
2. For "add X to file" or "modify" → use edit_file
3. For "how many/what is/show me" → use execute
4. For "create/make/build" → use create_file
5. For "organize/clean/sort" → use organize
7. For "why is X slow/broken" → use diagnose
8. Always replace /home/user with actual home directory
9. NEVER suggest or emit commands with `sudo`, `su`, `rm -rf`, reboot/shutdown, or destructive package operations.
10. If user input starts with `/`, do NOT generate JSON actions. Return a short plain-text hint only.

=== SAFETY ===
You can NEVER touch: /etc, /usr, /bin, /boot, /sys, /proc
You can ONLY modify files in user's home directory
All file edits create automatic backups

You are the BRAIN of this computer. Act like it."""
    
    def __init__(
        self, 
        api_key: Optional[str] = None, 
        provider: str = "gemini",
        model: Optional[str] = None,
        endpoint: Optional[str] = None
    ):
        # Convert string to enum
        try:
            self.provider = AIProvider(provider.lower())
        except ValueError:
            self.provider = AIProvider.GEMINI
        
        self.api_key = api_key
        self.model = model or self.DEFAULT_MODELS.get(self.provider, "gemini-2.0-flash")
        self.custom_endpoint = endpoint
        
        # Initialize provider-specific clients
        self._gemini_client = None
        if GENAI_AVAILABLE and api_key and self.provider == AIProvider.GEMINI:
            self._init_gemini(api_key)
    
    def _init_gemini(self, api_key: str):
        """Initialize the Gemini client"""
        try:
            self._gemini_client = genai.Client(api_key=api_key)
            logger.info(f"Gemini client initialized with model: {self.model}")
        except Exception as e:
            logger.error(f"Failed to initialize Gemini: {e}")
            self._gemini_client = None
    
    def configure(
        self,
        provider: str,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        endpoint: Optional[str] = None
    ):
        """
        Configure the AI client dynamically.
        
        Args:
            provider: 'gemini', 'openai', 'anthropic', or 'custom'
            api_key: API key for the provider
            model: Model name to use
            endpoint: Custom endpoint URL (for custom provider)
        """
        try:
            self.provider = AIProvider(provider.lower())
        except ValueError:
            self.provider = AIProvider.GEMINI
        
        self.api_key = api_key
        self.model = model or self.DEFAULT_MODELS.get(self.provider, "")
        self.custom_endpoint = endpoint
        
        if self.provider == AIProvider.GEMINI and GENAI_AVAILABLE and api_key:
            self._init_gemini(api_key)
        
        logger.info(f"AI Client configured: provider={self.provider.value}, model={self.model}")
    
    @classmethod
    def from_env(cls) -> 'AIClient':
        """
        Create an AIClient from .env file configuration.
        
        This is the primary way to create an AI client.
        Reads GEMINI_API_KEY and AI_MODEL from .env file.
        """
        try:
            from ..core.env_loader import get_env
            
            env = get_env()
            
            # Get API key from .env
            api_key = env.get('GEMINI_API_KEY')
            
            # Get model from .env (default: gemini-2.0-flash)
            model = env.get('AI_MODEL', 'gemini-2.0-flash')
            
            if not api_key:
                logger.warning("GEMINI_API_KEY not found in .env file")
                logger.warning("Please copy .env.example to .env and add your API key")
            
            return cls(
                api_key=api_key,
                provider='gemini',
                model=model
            )
        except Exception as e:
            logger.error(f"Failed to create client from .env: {e}")
            return cls()
    
    @classmethod
    def from_settings(cls) -> 'AIClient':
        """
        Create an AIClient from saved settings.
        Loads provider, API key, and model from settings/secrets.
        
        Prioritizes settings.json over .env file to respect user's provider/model selection.
        """
        # First try settings.json (user's explicit choice)
        try:
            from ..core.settings import get_settings_manager
            from ..core.secrets import SecretsManager
            
            settings = get_settings_manager().load()
            secrets = SecretsManager()
            
            provider = settings.active_provider
            api_key = secrets.get_api_key(provider)
            model = settings.providers.get(provider, {}).get('model', '')
            endpoint = settings.providers.get(provider, {}).get('endpoint', '')
            
            # Gemini: avoid deprecated/unavailable models (404 NOT_FOUND for v1beta)
            _GEMINI_DEPRECATED = (
                "gemini-1.5-pro",
                "gemini-1.5-flash",
                "gemini-1.5-flash-8b",
            )
            if provider == "gemini" and model in _GEMINI_DEPRECATED:
                logger.info("Replacing deprecated Gemini model %s with gemini-2.0-flash", model)
                model = "gemini-2.0-flash"
                settings.providers["gemini"]["model"] = model
                get_settings_manager().save()
            
            # Only use settings.json if we have an API key for the selected provider
            if api_key:
                logger.info(f"Loading AI client from settings: provider={provider}, model={model}")
                return cls(
                    api_key=api_key,
                    provider=provider,
                    model=model,
                    endpoint=endpoint
                )
            else:
                logger.warning(f"No API key found for provider {provider} in settings, trying .env fallback")
        except Exception as e:
            logger.warning(f"Failed to load from settings.json: {e}, trying .env fallback")
        
        # Fallback to .env file if settings.json doesn't have API key
        try:
            from ..core.env_loader import get_env
            env = get_env()
            api_key = env.get('GEMINI_API_KEY')
            
            if api_key:
                model = env.get('AI_MODEL', 'gemini-2.0-flash')
                logger.info(f"Loading AI client from .env: provider=gemini, model={model}")
                return cls(api_key=api_key, provider='gemini', model=model)
        except Exception as e:
            logger.warning(f"Failed to load from .env: {e}")
        
        # Last resort: return empty client
        logger.error("Failed to create AI client from settings or .env")
        return cls()
    
    async def ask(self, query: str, context: Optional[Dict[str, Any]] = None) -> str:
        """
        Send a query to the AI and get a response.
        
        Args:
            query: The user's question or request
            context: Optional context dict (system stats, active window, etc.)
            
        Returns:
            The AI's response text
        """
        prompt = self._build_prompt(query, context)
        
        # Route to appropriate provider
        if self.provider == AIProvider.GEMINI:
            response = await self._ask_gemini(prompt)
        elif self.provider == AIProvider.OPENAI:
            response = await self._ask_openai(prompt)
        elif self.provider == AIProvider.ANTHROPIC:
            response = await self._ask_anthropic(prompt)
        else:
            response = await self._ask_custom(prompt)
        
        if response.success:
            return response.content
        else:
            raise Exception(response.error or "Unknown AI error")
    
    async def edit_file(
        self, 
        content: str, 
        instruction: str, 
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Request the AI to edit file content based on an instruction.
        """
        prompt = f"""I need you to edit the following file based on this instruction:

INSTRUCTION: {instruction}

CURRENT FILE CONTENT:
```
{content}
```

Please provide ONLY the complete modified file content, with no explanations or markdown code blocks. 
Just output the raw file content that should replace the original."""
        
        # Use lower temperature for edits
        if self.provider == AIProvider.GEMINI:
            response = await self._ask_gemini(prompt, temperature=0.3)
        elif self.provider == AIProvider.OPENAI:
            response = await self._ask_openai(prompt, temperature=0.3)
        elif self.provider == AIProvider.ANTHROPIC:
            response = await self._ask_anthropic(prompt, temperature=0.3)
        else:
            response = await self._ask_custom(prompt, temperature=0.3)
        
        if response.success:
            result = response.content.strip()
            # Clean markdown code fences
            if result.startswith('```'):
                lines = result.split('\n')
                if lines[0].startswith('```'):
                    lines = lines[1:]
                if lines and lines[-1].strip() == '```':
                    lines = lines[:-1]
                result = '\n'.join(lines)
            return result
        else:
            raise Exception(response.error or "File edit failed")
    
    def _build_prompt(self, query: str, context: Optional[Dict[str, Any]] = None) -> str:
        """Build the full prompt with system context"""
        import os
        from pathlib import Path
        
        parts = []
        
        if context:
            parts.append("=== CURRENT SYSTEM CONTEXT ===")
            
            # Add user's home directory so AI uses real paths
            home_dir = str(Path.home())
            username = os.environ.get('USER', 'user')
            parts.append(f"Username: {username}")
            parts.append(f"Home Directory: {home_dir}")
            
            if 'active_window' in context:
                parts.append(f"Active Application: {context['active_window']}")
            
            if 'system_stats' in context:
                stats = context['system_stats']
                parts.append(f"CPU Usage: {stats.get('cpu_percent', 'N/A')}%")
                parts.append(f"RAM Usage: {stats.get('ram_percent', 'N/A')}%")
            
            if 'mode' in context:
                parts.append(f"Context Mode: {context['mode']}")
            
            if 'time_of_day' in context:
                parts.append(f"Time: {context['time_of_day']}")

            if 'last_action_summary' in context and context['last_action_summary']:
                parts.append(f"Last Action Memory: {context['last_action_summary']}")

            recent_messages = context.get('recent_messages')
            if isinstance(recent_messages, list) and recent_messages:
                parts.append("=== RECENT CONVERSATION (oldest -> newest) ===")
                for msg in recent_messages[-8:]:
                    role = msg.get('role', 'unknown')
                    content = str(msg.get('content', '')).strip()
                    if not content:
                        continue
                    if len(content) > 220:
                        content = content[:220] + "..."
                    parts.append(f"{role}: {content}")
                parts.append(
                    "If the current user query is brief/ambiguous (e.g., 'still not', 'not working'), "
                    "interpret it as a follow-up to the most recent relevant action in this conversation."
                )
            
            parts.append("=== USER QUERY ===")
        
        parts.append(query)
        
        return '\n'.join(parts)
    
    # ─────────────────────────────────────────────────────────────
    # Provider-specific implementations
    # ─────────────────────────────────────────────────────────────
    
    async def _ask_gemini(self, prompt: str, temperature: float = 0.7) -> AIResponse:
        """Send request to Google Gemini API"""
        if not GENAI_AVAILABLE:
            return AIResponse(
                success=False, content="", provider="gemini",
                error="google-genai library not installed"
            )
        
        if not self._gemini_client:
            return AIResponse(
                success=False, content="", provider="gemini",
                error="Gemini API key not configured"
            )
        
        model_to_use = self.model
        tried_404_fallback = False
        fallback_model = "gemini-2.0-flash"
        
        for attempt in range(self.MAX_RETRIES):
            try:
                response = await asyncio.to_thread(
                    self._gemini_client.models.generate_content,
                    model=model_to_use,
                    contents=[
                        types.Content(
                            role="user",
                            parts=[types.Part(text=self.SYSTEM_PROMPT + "\n\n" + prompt)]
                        )
                    ],
                    config=types.GenerateContentConfig(
                        temperature=temperature,
                        max_output_tokens=4096,
                    )
                )
                
                return AIResponse(
                    success=True,
                    content=response.text,
                    provider="gemini",
                    model=model_to_use
                )
                
            except Exception as e:
                err_str = str(e)
                # 404 / model not found: retry once with gemini-2.0-flash
                if not tried_404_fallback and ("404" in err_str or "not found" in err_str.lower() or "NOT_FOUND" in err_str):
                    logger.warning(
                        "Gemini model %s not found (404), retrying with %s",
                        model_to_use, fallback_model
                    )
                    model_to_use = fallback_model
                    tried_404_fallback = True
                    continue
                if await self._handle_retry(e, attempt):
                    continue
                return AIResponse(
                    success=False, content="", provider="gemini",
                    model=model_to_use, error=err_str
                )
        
        return AIResponse(
            success=False, content="", provider="gemini",
            error="Max retries exceeded"
        )
    
    async def _ask_openai(self, prompt: str, temperature: float = 0.7) -> AIResponse:
        """Send request to OpenAI API"""
        if not HTTPX_AVAILABLE:
            return AIResponse(
                success=False, content="", provider="openai",
                error="httpx library not installed"
            )
        
        if not self.api_key:
            return AIResponse(
                success=False, content="", provider="openai",
                error="OpenAI API key not configured"
            )
        
        for attempt in range(self.MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=self.DEFAULT_TIMEOUT) as client:
                    response = await client.post(
                        self.OPENAI_ENDPOINT,
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json"
                        },
                        json={
                            "model": self.model,
                            "messages": [
                                {"role": "system", "content": self.SYSTEM_PROMPT},
                                {"role": "user", "content": prompt}
                            ],
                            "max_tokens": 4096,
                            "temperature": temperature
                        }
                    )
                    
                    response.raise_for_status()
                    data = response.json()
                    
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    tokens = data.get("usage", {}).get("total_tokens")
                    
                    return AIResponse(
                        success=True,
                        content=content,
                        provider="openai",
                        model=self.model,
                        tokens_used=tokens
                    )
                    
            except Exception as e:
                if await self._handle_retry(e, attempt):
                    continue
                return AIResponse(
                    success=False, content="", provider="openai",
                    model=self.model, error=str(e)
                )
        
        return AIResponse(
            success=False, content="", provider="openai",
            error="Max retries exceeded"
        )
    
    async def _ask_anthropic(self, prompt: str, temperature: float = 0.7) -> AIResponse:
        """Send request to Anthropic (Claude) API"""
        if not HTTPX_AVAILABLE:
            return AIResponse(
                success=False, content="", provider="anthropic",
                error="httpx library not installed"
            )
        
        if not self.api_key:
            return AIResponse(
                success=False, content="", provider="anthropic",
                error="Anthropic API key not configured"
            )
        
        for attempt in range(self.MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=self.DEFAULT_TIMEOUT) as client:
                    response = await client.post(
                        self.ANTHROPIC_ENDPOINT,
                        headers={
                            "x-api-key": self.api_key,
                            "anthropic-version": "2023-06-01",
                            "Content-Type": "application/json"
                        },
                        json={
                            "model": self.model,
                            "system": self.SYSTEM_PROMPT,
                            "messages": [
                                {"role": "user", "content": prompt}
                            ],
                            "max_tokens": 4096,
                            "temperature": temperature
                        }
                    )
                    
                    response.raise_for_status()
                    data = response.json()
                    
                    # Anthropic returns content as an array
                    content_blocks = data.get("content", [])
                    content = ""
                    for block in content_blocks:
                        if block.get("type") == "text":
                            content += block.get("text", "")
                    
                    tokens = data.get("usage", {}).get("input_tokens", 0) + \
                             data.get("usage", {}).get("output_tokens", 0)
                    
                    return AIResponse(
                        success=True,
                        content=content,
                        provider="anthropic",
                        model=self.model,
                        tokens_used=tokens
                    )
                    
            except Exception as e:
                if await self._handle_retry(e, attempt):
                    continue
                return AIResponse(
                    success=False, content="", provider="anthropic",
                    model=self.model, error=str(e)
                )
        
        return AIResponse(
            success=False, content="", provider="anthropic",
            error="Max retries exceeded"
        )
    
    async def _ask_custom(self, prompt: str, temperature: float = 0.7) -> AIResponse:
        """Send request to custom OpenAI-compatible endpoint"""
        if not HTTPX_AVAILABLE:
            return AIResponse(
                success=False, content="", provider="custom",
                error="httpx library not installed"
            )
        
        endpoint = self.custom_endpoint
        if not endpoint:
            return AIResponse(
                success=False, content="", provider="custom",
                error="Custom endpoint not configured"
            )
        
        for attempt in range(self.MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=self.DEFAULT_TIMEOUT) as client:
                    response = await client.post(
                        endpoint,
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json"
                        },
                        json={
                            "model": self.model or "default",
                            "messages": [
                                {"role": "system", "content": self.SYSTEM_PROMPT},
                                {"role": "user", "content": prompt}
                            ],
                            "max_tokens": 4096,
                            "temperature": temperature
                        }
                    )
                    
                    response.raise_for_status()
                    data = response.json()
                    
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    
                    return AIResponse(
                        success=True,
                        content=content,
                        provider="custom",
                        model=self.model,
                        tokens_used=data.get("usage", {}).get("total_tokens")
                    )
                    
            except Exception as e:
                if await self._handle_retry(e, attempt):
                    continue
                return AIResponse(
                    success=False, content="", provider="custom",
                    model=self.model, error=str(e)
                )
        
        return AIResponse(
            success=False, content="", provider="custom",
            error="Max retries exceeded"
        )
    
    async def _handle_retry(self, error: Exception, attempt: int) -> bool:
        """
        Handle retry logic for API errors.
        Returns True if should retry, False otherwise.
        """
        error_str = str(error).lower()
        
        # Network errors - retry
        if 'network' in error_str or 'connection' in error_str or 'timeout' in error_str:
            if attempt < self.MAX_RETRIES - 1:
                wait_time = 2 ** attempt
                logger.warning(f"Network error, retrying in {wait_time}s...")
                await asyncio.sleep(wait_time)
                return True
            raise NetworkError("Network unavailable")
        
        # Rate limiting - retry with longer wait
        if 'rate' in error_str or '429' in error_str:
            if attempt < self.MAX_RETRIES - 1:
                wait_time = 2 ** (attempt + 2)
                logger.warning(f"Rate limited, waiting {wait_time}s...")
                await asyncio.sleep(wait_time)
                return True
        
        # Other errors - don't retry
        logger.error(f"API error: {error}")
        return False
    
    def is_available(self) -> bool:
        """Check if the AI client is properly configured"""
        if self.provider == AIProvider.GEMINI:
            return self._gemini_client is not None
        else:
            return bool(self.api_key)
    
    def get_provider_info(self) -> Dict[str, str]:
        """Get current provider information"""
        return {
            "provider": self.provider.value,
            "model": self.model,
            "configured": str(self.is_available())
        }
