"""
NervaOS Token Pruner - Optimize prompts for token efficiency

This module:
- Compresses system context into minimal text
- Truncates long file contents intelligently
- Summarizes conversation history
- Estimates token counts
"""

import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class PrunedContent:
    """Result of content pruning"""
    content: str
    original_length: int
    pruned_length: int
    estimated_tokens: int


class TokenPruner:
    """
    Optimizes content for LLM context windows.
    
    Target: Keep prompts under 2000 tokens for fast responses.
    Uses simple heuristics since we don't have a tokenizer locally.
    """
    
    # Rough estimate: 1 token ≈ 4 characters
    CHARS_PER_TOKEN = 4
    
    # Target limits
    MAX_CONTEXT_TOKENS = 500
    MAX_FILE_CONTENT_TOKENS = 1000
    MAX_HISTORY_TOKENS = 500
    
    def __init__(self):
        pass
    
    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for text"""
        return len(text) // self.CHARS_PER_TOKEN
    
    def prune_system_context(self, context: Dict[str, Any]) -> str:
        """
        Compress system context to minimal representation.
        
        Input:
            {
                'cpu_percent': 45.2,
                'ram_percent': 78.5,
                'ram_used_gb': 12.5,
                'ram_total_gb': 16.0,
                'active_window': 'main.py - Visual Studio Code',
                'mode': 'development'
            }
        
        Output:
            "CPU:45% RAM:78% (12.5/16GB) App:VS Code Mode:Dev"
        """
        parts = []
        
        # CPU
        if 'cpu_percent' in context:
            parts.append(f"CPU:{int(context['cpu_percent'])}%")
        
        # RAM
        if 'ram_percent' in context:
            ram_str = f"RAM:{int(context['ram_percent'])}%"
            if 'ram_used_gb' in context and 'ram_total_gb' in context:
                ram_str += f"({context['ram_used_gb']}/{context['ram_total_gb']}GB)"
            parts.append(ram_str)
        
        # Active app (compress)
        if 'active_app' in context:
            app = self._shorten_app_name(context['active_app'])
            parts.append(f"App:{app}")
        
        # Mode
        if 'mode' in context:
            mode = context['mode'][:3].title()  # dev -> Dev
            parts.append(f"Mode:{mode}")
        
        # Battery (if present and notable)
        if 'battery_percent' in context and context.get('battery_percent') is not None:
            battery = context['battery_percent']
            if battery < 20:
                parts.append(f"⚡{battery}%")
        
        return " ".join(parts)
    
    def _shorten_app_name(self, name: str) -> str:
        """Shorten application name"""
        shortcuts = {
            'visual studio code': 'VSCode',
            'google chrome': 'Chrome',
            'mozilla firefox': 'Firefox',
            'libreoffice writer': 'Writer',
            'libreoffice calc': 'Calc',
            'gnome-terminal': 'Term',
            'file manager': 'Files',
        }
        
        name_lower = name.lower()
        for full, short in shortcuts.items():
            if full in name_lower:
                return short
        
        # Just take first word if it's long
        if len(name) > 15:
            return name.split()[0][:10]
        
        return name
    
    def prune_file_content(
        self, 
        content: str, 
        max_tokens: Optional[int] = None,
        focus_lines: Optional[List[int]] = None
    ) -> PrunedContent:
        """
        Intelligently truncate file content.
        
        Strategies:
        1. If focus_lines provided, show context around those lines
        2. Otherwise, show head + tail + sample from middle
        3. Remove excessive blank lines
        4. Compress common patterns
        
        Args:
            content: The file content
            max_tokens: Maximum tokens to use
            focus_lines: Line numbers to focus on (0-indexed)
        
        Returns:
            PrunedContent with the pruned text
        """
        max_tokens = max_tokens or self.MAX_FILE_CONTENT_TOKENS
        max_chars = max_tokens * self.CHARS_PER_TOKEN
        
        original_length = len(content)
        
        # If already small enough, return as-is
        if len(content) <= max_chars:
            return PrunedContent(
                content=content,
                original_length=original_length,
                pruned_length=len(content),
                estimated_tokens=self.estimate_tokens(content)
            )
        
        lines = content.splitlines()
        total_lines = len(lines)
        
        if focus_lines:
            # Show context around focus lines
            result_lines = self._extract_focus_context(lines, focus_lines)
        else:
            # Show head, middle sample, tail
            result_lines = self._extract_summary(lines, max_chars)
        
        result = '\n'.join(result_lines)
        
        # Compress if still too long
        if len(result) > max_chars:
            result = result[:max_chars - 50] + f"\n... [{total_lines} lines total]"
        
        return PrunedContent(
            content=result,
            original_length=original_length,
            pruned_length=len(result),
            estimated_tokens=self.estimate_tokens(result)
        )
    
    def _extract_focus_context(
        self, 
        lines: List[str], 
        focus_lines: List[int],
        context_before: int = 5,
        context_after: int = 5
    ) -> List[str]:
        """Extract lines around focus points"""
        result = []
        included = set()
        
        for focus in sorted(focus_lines):
            start = max(0, focus - context_before)
            end = min(len(lines), focus + context_after + 1)
            
            # Add separator if there's a gap
            if result and start > max(included) + 1:
                result.append(f"... [{start - max(included) - 1} lines omitted] ...")
            
            for i in range(start, end):
                if i not in included:
                    prefix = ">>> " if i == focus else "    "
                    result.append(f"{i+1:4d}{prefix}{lines[i]}")
                    included.add(i)
        
        return result
    
    def _extract_summary(self, lines: List[str], max_chars: int) -> List[str]:
        """Extract head + middle + tail summary"""
        total = len(lines)
        
        if total <= 30:
            return [f"{i+1:4d} {line}" for i, line in enumerate(lines)]
        
        # Allocate: 40% head, 20% middle, 40% tail
        head_lines = int(total * 0.15)
        tail_lines = int(total * 0.15)
        
        result = []
        
        # Head
        for i in range(min(head_lines, total)):
            result.append(f"{i+1:4d} {lines[i]}")
        
        # Middle indicator
        middle_start = total // 2 - 3
        middle_end = total // 2 + 3
        
        if head_lines < middle_start:
            result.append(f"... [{middle_start - head_lines} lines omitted] ...")
            for i in range(middle_start, middle_end):
                result.append(f"{i+1:4d} {lines[i]}")
        
        # Tail
        tail_start = total - tail_lines
        if middle_end < tail_start:
            result.append(f"... [{tail_start - middle_end} lines omitted] ...")
        
        for i in range(tail_start, total):
            result.append(f"{i+1:4d} {lines[i]}")
        
        return result
    
    def prune_conversation_history(
        self, 
        messages: List[Dict[str, str]], 
        max_tokens: Optional[int] = None
    ) -> List[Dict[str, str]]:
        """
        Prune conversation history to fit token budget.
        
        Strategy:
        1. Always keep the most recent messages
        2. Summarize older messages if needed
        3. Drop very old messages
        """
        max_tokens = max_tokens or self.MAX_HISTORY_TOKENS
        
        if not messages:
            return []
        
        # Calculate current token usage
        total_tokens = sum(
            self.estimate_tokens(m.get('content', '')) 
            for m in messages
        )
        
        if total_tokens <= max_tokens:
            return messages
        
        # Keep last N messages, drop oldest
        result = []
        current_tokens = 0
        
        for msg in reversed(messages):
            msg_tokens = self.estimate_tokens(msg.get('content', ''))
            
            if current_tokens + msg_tokens <= max_tokens:
                result.insert(0, msg)
                current_tokens += msg_tokens
            else:
                # Add summary of dropped messages
                if result and result[0].get('role') != 'system':
                    result.insert(0, {
                        'role': 'system',
                        'content': f'[Earlier conversation summarized: {len(messages) - len(result)} messages omitted]'
                    })
                break
        
        return result
    
    def compress_code(self, code: str) -> str:
        """
        Compress code by removing excessive whitespace and comments.
        Use sparingly - only when really need to fit in context.
        """
        lines = code.splitlines()
        result = []
        
        for line in lines:
            # Skip empty lines (keep one)
            if not line.strip():
                if result and result[-1] == '':
                    continue
                result.append('')
                continue
            
            # Skip full-line comments (keep docstrings)
            stripped = line.lstrip()
            if stripped.startswith('#') and not stripped.startswith('#!'):
                continue
            
            result.append(line)
        
        return '\n'.join(result)


# Singleton instance
pruner = TokenPruner()
