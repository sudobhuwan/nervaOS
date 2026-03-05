"""
GOD LEVEL Message Renderers for NervaOS
Beautiful, polished UI - no raw markdown symbols!
"""

import logging
import re
import subprocess
from gi.repository import Gtk, Pango, GLib

logger = logging.getLogger('nerva-renderers')


class MarkdownParser:
    """Parse markdown and return structured content"""
    
    @staticmethod
    def parse(text: str):
        """Parse markdown text into structured elements"""
        elements = []
        lines = text.split('\n')
        i = 0
        in_code_block = False
        code_lines = []
        code_lang = ''
        
        while i < len(lines):
            line = lines[i]
            
            # Code blocks
            if line.strip().startswith('```'):
                if not in_code_block:
                    in_code_block = True
                    code_lang = line.strip()[3:].strip() or 'text'
                    code_lines = []
                else:
                    in_code_block = False
                    elements.append({
                        'type': 'code_block',
                        'language': code_lang,
                        'content': '\n'.join(code_lines)
                    })
                    code_lines = []
                i += 1
                continue
            
            if in_code_block:
                code_lines.append(line)
                i += 1
                continue
            
            stripped = line.strip()
            if not stripped:
                i += 1
                continue
            
            # Headers (# ## ###)
            if stripped.startswith('#'):
                level = len(re.match(r'^#+', stripped).group())
                text = stripped.lstrip('#').strip()
                elements.append({'type': 'header', 'level': level, 'text': text})
            
            # Bold line (**text**) only when the whole line is bold.
            elif re.fullmatch(r'\*\*[^*].*[^*]\*\*', stripped):
                elements.append({'type': 'bold', 'text': stripped.replace('**', '')})
            
            # Bullet lists
            elif stripped.startswith(('- ', '* ', '• ')):
                # Collect consecutive list items
                items = []
                while i < len(lines):
                    line_stripped = lines[i].strip()
                    if line_stripped.startswith(('- ', '* ', '• ')):
                        item_text = re.sub(r'^[-*•]\s+', '', line_stripped)
                        items.append(item_text)
                        i += 1
                    else:
                        break
                elements.append({'type': 'list', 'items': items})
                continue
            
            # Numbered lists
            elif re.match(r'^\d+\.\s', stripped):
                items = []
                while i < len(lines):
                    line_stripped = lines[i].strip()
                    if re.match(r'^\d+\.\s', line_stripped):
                        item_text = re.sub(r'^\d+\.\s+', '', line_stripped)
                        items.append(item_text)
                        i += 1
                    else:
                        break
                elements.append({'type': 'numbered_list', 'items': items})
                continue
            
            # Pure inline-code line (`code`)
            elif re.fullmatch(r'`[^`]+`', stripped):
                elements.append({'type': 'inline_code', 'text': stripped})
            
            # Links [text](url)
            elif '[' in stripped and '](' in stripped:
                elements.append({'type': 'link', 'text': stripped})
            
            # Regular paragraph
            else:
                elements.append({'type': 'text', 'text': stripped})
            
            i += 1
        
        return elements


class MessageRenderer:
    """GOD LEVEL renderer for all messages"""
    
    @staticmethod
    def create_regular_message(text: str, is_user: bool) -> Gtk.Widget:
        """Create BEAUTIFUL message with proper markdown rendering"""
        
        # Parse markdown
        elements = MarkdownParser.parse(text)
        
        # Create container
        container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        container.set_margin_start(10)
        container.set_margin_end(10)
        container.set_margin_top(6)
        container.set_margin_bottom(6)
        
        if is_user:
            container.add_css_class('user-message-card')
            container.set_halign(Gtk.Align.END)
        else:
            container.add_css_class('assistant-message-card')
            container.set_halign(Gtk.Align.START)
        
        # Render each element
        for elem in elements:
            widget = MessageRenderer._render_element(elem)
            if widget:
                container.append(widget)
        
        return container
    
    @staticmethod
    def _render_element(elem: dict) -> Gtk.Widget:
        """Render a single markdown element"""
        
        if elem['type'] == 'header':
            return MessageRenderer._create_header(elem['text'], elem['level'])
        
        elif elem['type'] == 'bold':
            return MessageRenderer._create_bold(elem['text'])
        
        elif elem['type'] == 'list':
            return MessageRenderer._create_list(elem['items'])
        
        elif elem['type'] == 'numbered_list':
            return MessageRenderer._create_numbered_list(elem['items'])
        
        elif elem['type'] == 'code_block':
            return MessageRenderer._create_code_block(elem['content'], elem['language'])
        
        elif elem['type'] == 'inline_code':
            return MessageRenderer._create_inline_code(elem['text'])
        
        elif elem['type'] == 'link':
            return MessageRenderer._create_link(elem['text'])
        
        elif elem['type'] == 'text':
            return MessageRenderer._create_text(elem['text'])
        
        return None
    
    @staticmethod
    def _create_header(text: str, level: int) -> Gtk.Widget:
        """Create beautiful header"""
        label = Gtk.Label(label=text)
        label.set_xalign(0)
        label.set_wrap(True)
        label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        label.set_max_width_chars(68)
        
        if level == 1:
            label.add_css_class('message-h1')
        elif level == 2:
            label.add_css_class('message-h2')
        else:
            label.add_css_class('message-h3')
        
        return label
    
    @staticmethod
    def _create_bold(text: str) -> Gtk.Widget:
        """Create bold text"""
        label = Gtk.Label(label=text)
        label.set_xalign(0)
        label.set_wrap(True)
        label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        label.set_max_width_chars(68)
        label.add_css_class('message-bold')
        return label
    
    @staticmethod
    def _create_list(items: list) -> Gtk.Widget:
        """Create beautiful bullet list"""
        list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        list_box.add_css_class('message-list')
        
        for item in items:
            item_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            
            # Bullet icon
            bullet = Gtk.Label(label="◆")
            bullet.add_css_class('bullet-icon')
            item_box.append(bullet)
            
            # Item text (with inline formatting support)
            text_label = Gtk.Label()
            text_label.set_xalign(0)
            text_label.set_wrap(True)
            text_label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
            text_label.set_max_width_chars(66)
            text_label.set_hexpand(True)
            text_label.set_use_markup(True)
            text_label.set_markup(MessageRenderer._format_inline_markup(item))
            text_label.add_css_class('list-item-text')
            item_box.append(text_label)
            
            list_box.append(item_box)
        
        return list_box
    
    @staticmethod
    def _create_numbered_list(items: list) -> Gtk.Widget:
        """Create beautiful numbered list"""
        list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        list_box.add_css_class('message-list')
        
        for i, item in enumerate(items, 1):
            item_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            
            # Number
            number = Gtk.Label(label=f"{i}.")
            number.add_css_class('number-icon')
            item_box.append(number)
            
            # Item text
            text_label = Gtk.Label()
            text_label.set_xalign(0)
            text_label.set_wrap(True)
            text_label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
            text_label.set_max_width_chars(66)
            text_label.set_hexpand(True)
            text_label.set_use_markup(True)
            text_label.set_markup(MessageRenderer._format_inline_markup(item))
            text_label.add_css_class('list-item-text')
            item_box.append(text_label)
            
            list_box.append(item_box)
        
        return list_box
    
    @staticmethod
    def _create_code_block(code: str, language: str) -> Gtk.Widget:
        """Create beautiful code block"""
        code_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        code_box.add_css_class('code-block')
        
        # Header with language
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header.add_css_class('code-header')
        
        lang_icon = Gtk.Label(label="</>" if language == 'text' else f"<{language}>")
        lang_icon.add_css_class('code-lang')
        header.append(lang_icon)
        
        code_box.append(header)
        
        # Code content (scrollable)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        scroll.set_max_content_height(200)
        
        code_label = Gtk.Label(label=code)
        code_label.set_xalign(0)
        code_label.set_yalign(0)
        code_label.set_selectable(True)
        code_label.add_css_class('code-content')
        code_label.set_wrap(False)
        
        scroll.set_child(code_label)
        code_box.append(scroll)
        
        return code_box
    
    @staticmethod
    def _create_inline_code(text: str) -> Gtk.Widget:
        """Create single-chip inline code line (avoids broken wrapped pill layout)."""
        code_text = text.strip()
        if code_text.startswith('`') and code_text.endswith('`'):
            code_text = code_text[1:-1]
        label = Gtk.Label(label=code_text)
        label.set_xalign(0)
        label.set_wrap(True)
        label.add_css_class('inline-code')
        return label
    
    @staticmethod
    def _create_link(text: str) -> Gtk.Widget:
        """Create clickable link"""
        # Parse [text](url)
        match = re.search(r'\[([^\]]+)\]\(([^)]+)\)', text)
        
        if match:
            link_text = match.group(1)
            url = match.group(2)
            
            btn = Gtk.Button(label=f"🔗 {link_text}")
            btn.add_css_class('link-button')
            btn.set_halign(Gtk.Align.START)
            btn.set_hexpand(False)
            btn.connect('clicked', lambda b: subprocess.Popen(['xdg-open', url]))
            return btn
        
        # Fallback to regular text
        return MessageRenderer._create_text(text)
    
    @staticmethod
    def _create_text(text: str) -> Gtk.Widget:
        """Create regular text paragraph"""
        label = Gtk.Label()
        label.set_xalign(0)
        label.set_wrap(True)
        label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        label.set_max_width_chars(62)
        label.set_selectable(True)
        label.set_use_markup(True)
        label.set_markup(MessageRenderer._format_inline_markup(text))
        label.add_css_class('message-text')
        
        return label

    @staticmethod
    def _format_inline_markup(text: str) -> str:
        """Render inline markdown (bold/code) into safe Pango markup."""
        if not text:
            return ""

        parts = re.split(r'(`[^`]+`)', text)
        out = []
        for part in parts:
            if part.startswith('`') and part.endswith('`') and len(part) >= 2:
                code = GLib.markup_escape_text(part[1:-1])
                out.append(
                    f'<span font_family="monospace" foreground="#93C5FD">{code}</span>'
                )
            else:
                escaped = GLib.markup_escape_text(part)
                escaped = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', escaped)
                out.append(escaped)
        return "".join(out)
    
    @staticmethod
    def _clean_inline(text: str) -> str:
        """Remove inline markdown symbols"""
        # Remove bold
        text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
        # Remove italic
        text = re.sub(r'\*([^*]+)\*', r'\1', text)
        # Remove inline code backticks (keep for separate rendering)
        # text = re.sub(r'`([^`]+)`', r'\1', text)
        return text


class WebSearchRenderer:
    """GOD LEVEL web search results"""
    
    @staticmethod
    def create_widget(text: str, open_url_callback) -> Gtk.Widget:
        """Create STUNNING web search result card"""
        
        # Create main container
        container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        container.add_css_class('web-search-card')
        
        lines = text.split('\n')
        
        # Parse query
        query = ""
        if lines and '🌐' in lines[0]:
            query_match = re.search(r'Web Search: (.+?)(\*\*|$)', lines[0])
            if query_match:
                query = query_match.group(1).strip()
        
        # BEAUTIFUL Header
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        header.add_css_class('search-card-header')
        
        icon = Gtk.Label(label="🌐")
        icon.add_css_class('search-big-icon')
        header.append(icon)
        
        header_text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        
        title = Gtk.Label(label="Web Search Results")
        title.add_css_class('search-card-title')
        title.set_xalign(0)
        header_text_box.append(title)
        
        query_label = Gtk.Label(label=query)
        query_label.add_css_class('search-card-query')
        query_label.set_xalign(0)
        query_label.set_wrap(True)
        header_text_box.append(query_label)
        
        header.append(header_text_box)
        container.append(header)
        
        # Parse content
        summary_text = []
        sources = []
        current_source = {}
        in_summary = False
        
        for line in lines:
            if '📝 **Summary:**' in line or 'Summary:' in line:
                in_summary = True
                continue
            elif '**Sources:**' in line or 'Sources:' in line:
                in_summary = False
                continue
            elif in_summary and line.strip() and not line.startswith('**'):
                summary_text.append(line.strip())
            elif re.match(r'^\d+\.\s+\*\*', line):
                if current_source:
                    sources.append(current_source)
                title_match = re.sub(r'^\d+\.\s+\*\*(.+?)\*\*', r'\1', line)
                current_source = {'title': title_match, 'snippet': '', 'url': ''}
            elif current_source and '🔗' in line:
                current_source['url'] = line.replace('🔗', '').strip()
            elif current_source and line.strip() and not line.startswith(('**', '🔗')):
                if not current_source['snippet']:
                    current_source['snippet'] = line.strip()
        
        if current_source:
            sources.append(current_source)
        
        # AI Summary Section
        if summary_text:
            summary_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            summary_section.add_css_class('search-summary-section')
            
            summary_header = Gtk.Label(label="✨ AI Summary")
            summary_header.add_css_class('section-header')
            summary_header.set_xalign(0)
            summary_section.append(summary_header)
            
            summary_content = Gtk.Label(label=' '.join(summary_text))
            summary_content.set_wrap(True)
            summary_content.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
            summary_content.set_xalign(0)
            summary_content.add_css_class('summary-content')
            summary_section.append(summary_content)
            
            container.append(summary_section)
        
        # Sources Section
        if sources:
            sources_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            sources_section.add_css_class('search-sources-section')
            
            sources_header = Gtk.Label(label=f"📚 Sources ({len(sources)})")
            sources_header.add_css_class('section-header')
            sources_header.set_xalign(0)
            sources_section.append(sources_header)
            
            for i, source in enumerate(sources[:5], 1):
                if not source.get('title'):
                    continue
                
                source_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
                source_card.add_css_class('source-item-card')
                
                # Clickable title
                title_btn = Gtk.Button(label=f"{i}. {source['title']}")
                title_btn.add_css_class('source-title-button')
                if source.get('url'):
                    title_btn.connect('clicked', lambda b, url=source['url']: open_url_callback(url))
                source_card.append(title_btn)
                
                # Snippet
                if source.get('snippet'):
                    snippet = source['snippet'][:200] + ('...' if len(source['snippet']) > 200 else '')
                    snippet_label = Gtk.Label(label=snippet)
                    snippet_label.set_wrap(True)
                    snippet_label.set_xalign(0)
                    snippet_label.add_css_class('source-snippet-text')
                    source_card.append(snippet_label)
                
                sources_section.append(source_card)
            
            container.append(sources_section)
        
        return container
