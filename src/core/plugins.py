"""
NervaOS Plugin System - Extensibility architecture

Allows users to add plugins that:
- Register new commands
- Add context providers
- Hook into events
- Extend the UI
"""

import os
import importlib.util
import logging
from pathlib import Path
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from enum import Enum
from abc import ABC, abstractmethod

logger = logging.getLogger('nerva-plugins')


class PluginHook(Enum):
    """Available plugin hooks"""
    ON_STARTUP = "on_startup"
    ON_SHUTDOWN = "on_shutdown"
    ON_QUERY = "on_query"  # Before sending to AI
    ON_RESPONSE = "on_response"  # After receiving from AI
    ON_CONTEXT = "on_context"  # When gathering context
    ON_FILE_EDIT = "on_file_edit"  # Before file modification
    ON_ALERT = "on_alert"  # When system alert triggers


@dataclass
class PluginInfo:
    """Plugin metadata"""
    name: str
    version: str
    author: str = ""
    description: str = ""
    homepage: str = ""
    enabled: bool = True


@dataclass
class PluginCommand:
    """A command registered by a plugin"""
    name: str
    description: str
    handler: Callable
    plugin_name: str


class NervaPlugin(ABC):
    """
    Base class for NervaOS plugins.
    
    Plugins should inherit from this and implement the required methods.
    """
    
    @property
    @abstractmethod
    def info(self) -> PluginInfo:
        """Return plugin metadata"""
        pass
    
    def on_load(self, api: 'PluginAPI') -> bool:
        """
        Called when plugin is loaded.
        
        Args:
            api: Plugin API for registering commands, hooks, etc.
            
        Returns:
            True if loaded successfully
        """
        return True
    
    def on_unload(self) -> bool:
        """Called when plugin is unloaded"""
        return True


class PluginAPI:
    """
    API provided to plugins for interacting with NervaOS.
    """
    
    def __init__(self, manager: 'PluginManager'):
        self._manager = manager
    
    def register_command(self, name: str, description: str, handler: Callable):
        """Register a slash command"""
        self._manager._register_command(name, description, handler)
    
    def register_hook(self, hook: PluginHook, callback: Callable):
        """Register a hook callback"""
        self._manager._register_hook(hook, callback)
    
    def get_context(self) -> dict:
        """Get current system context"""
        # Would call context engine
        return {}
    
    def show_notification(self, title: str, message: str):
        """Show a desktop notification"""
        from .notifications import notify
        notify(title, message)
    
    def log(self, message: str, level: str = "info"):
        """Log a message"""
        getattr(logger, level)(message)


class PluginManager:
    """
    Manages plugin loading, unloading, and execution.
    """
    
    # Plugin directory
    PLUGIN_DIR = Path.home() / '.config' / 'nervaos' / 'plugins'
    
    def __init__(self):
        self._plugins: Dict[str, NervaPlugin] = {}
        self._commands: Dict[str, PluginCommand] = {}
        self._hooks: Dict[PluginHook, List[Callable]] = {hook: [] for hook in PluginHook}
        
        # Create plugin directory
        self.PLUGIN_DIR.mkdir(parents=True, exist_ok=True)
    
    def discover_plugins(self) -> List[Path]:
        """Find all plugin files"""
        plugins = []
        
        for item in self.PLUGIN_DIR.iterdir():
            if item.is_dir() and (item / '__init__.py').exists():
                plugins.append(item / '__init__.py')
            elif item.suffix == '.py' and not item.name.startswith('_'):
                plugins.append(item)
        
        return plugins
    
    def load_plugin(self, path: Path) -> bool:
        """Load a plugin from a file path"""
        try:
            # Load the module
            spec = importlib.util.spec_from_file_location(
                f"nerva_plugin_{path.stem}",
                path
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Find the plugin class
            plugin_class = None
            for item_name in dir(module):
                item = getattr(module, item_name)
                if (isinstance(item, type) and 
                    issubclass(item, NervaPlugin) and 
                    item is not NervaPlugin):
                    plugin_class = item
                    break
            
            if not plugin_class:
                logger.warning(f"No plugin class found in {path}")
                return False
            
            # Instantiate and load
            plugin = plugin_class()
            api = PluginAPI(self)
            
            if plugin.on_load(api):
                self._plugins[plugin.info.name] = plugin
                logger.info(f"Loaded plugin: {plugin.info.name} v{plugin.info.version}")
                return True
            else:
                logger.warning(f"Plugin {plugin.info.name} failed to load")
                return False
                
        except Exception as e:
            logger.error(f"Failed to load plugin from {path}: {e}")
            return False
    
    def load_all_plugins(self):
        """Load all discovered plugins"""
        for path in self.discover_plugins():
            self.load_plugin(path)
        
        logger.info(f"Loaded {len(self._plugins)} plugins")
    
    def unload_plugin(self, name: str) -> bool:
        """Unload a plugin by name"""
        if name not in self._plugins:
            return False
        
        plugin = self._plugins[name]
        
        try:
            plugin.on_unload()
        except Exception as e:
            logger.error(f"Error unloading {name}: {e}")
        
        # Remove commands
        self._commands = {
            cmd: data for cmd, data in self._commands.items()
            if data.plugin_name != name
        }
        
        del self._plugins[name]
        logger.info(f"Unloaded plugin: {name}")
        return True
    
    def _register_command(self, name: str, description: str, handler: Callable):
        """Internal: Register a command"""
        # Get calling plugin name from handler
        plugin_name = handler.__module__.split('_')[-1]
        
        self._commands[name] = PluginCommand(
            name=name,
            description=description,
            handler=handler,
            plugin_name=plugin_name
        )
    
    def _register_hook(self, hook: PluginHook, callback: Callable):
        """Internal: Register a hook"""
        self._hooks[hook].append(callback)
    
    async def execute_hook(self, hook: PluginHook, **kwargs) -> List[Any]:
        """Execute all callbacks for a hook"""
        results = []
        
        for callback in self._hooks[hook]:
            try:
                result = callback(**kwargs)
                if hasattr(result, '__await__'):
                    result = await result
                results.append(result)
            except Exception as e:
                logger.error(f"Hook {hook.value} callback error: {e}")
        
        return results
    
    def get_command(self, name: str) -> Optional[PluginCommand]:
        """Get a registered command"""
        return self._commands.get(name)
    
    def list_commands(self) -> List[PluginCommand]:
        """List all registered commands"""
        return list(self._commands.values())
    
    def list_plugins(self) -> List[PluginInfo]:
        """List all loaded plugins"""
        return [p.info for p in self._plugins.values()]


# ─────────────────────────────────────────────────────────────────────────────
# Example Plugin Template
# ─────────────────────────────────────────────────────────────────────────────

EXAMPLE_PLUGIN = '''
"""
Example NervaOS Plugin

This is a template for creating your own plugin.
Save this file in ~/.config/nervaos/plugins/
"""

from nervaos.core.plugins import NervaPlugin, PluginInfo, PluginAPI, PluginHook


class MyPlugin(NervaPlugin):
    """Example plugin that adds a custom command"""
    
    @property
    def info(self) -> PluginInfo:
        return PluginInfo(
            name="my-plugin",
            version="1.0.0",
            author="Your Name",
            description="An example NervaOS plugin"
        )
    
    def on_load(self, api: PluginAPI) -> bool:
        # Register a command
        api.register_command(
            name="greet",
            description="Say hello",
            handler=self.greet_command
        )
        
        # Register a hook
        api.register_hook(PluginHook.ON_QUERY, self.on_query)
        
        api.log("MyPlugin loaded!")
        return True
    
    def greet_command(self, args: str) -> str:
        return f"Hello from MyPlugin! Args: {args}"
    
    def on_query(self, query: str) -> str:
        # Modify or inspect queries before they go to AI
        return query  # Return modified query or original
    
    def on_unload(self) -> bool:
        return True
'''


def create_example_plugin():
    """Create an example plugin file"""
    plugin_dir = PluginManager.PLUGIN_DIR
    example_path = plugin_dir / 'example_plugin.py'
    
    if not example_path.exists():
        example_path.write_text(EXAMPLE_PLUGIN)
        logger.info(f"Created example plugin at {example_path}")
