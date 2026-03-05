"""
GOD LEVEL Chat History Panel for NervaOS
Beautiful sidebar with conversation list, search, and stats
"""

import logging
from datetime import datetime
from typing import Optional, Callable, List, Dict

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib, Pango, Gdk

logger = logging.getLogger('nerva-history')


class HistoryPanel(Gtk.Box):
    """Beautiful history sidebar"""
    
    def __init__(self, on_conversation_selected: Callable = None, on_search: Callable = None, 
                 on_delete: Callable = None, on_clear_all: Callable = None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        
        self._on_conversation_selected = on_conversation_selected
        self._on_search = on_search
        self._on_delete = on_delete
        self._clear_all_cb = on_clear_all  # avoid shadowing _on_clear_all method
        self._conversations: List[Dict] = []
        self._active_conversation_id: Optional[int] = None
        
        self.add_css_class('history-panel')
        self.set_size_request(320, -1)
        
        self._build_ui()
    
    def _build_ui(self):
        """Build the history panel UI"""
        
        #  Header
        header = self._create_header()
        self.append(header)
        
        # Stats card
        self._stats_card = self._create_stats_card()
        self.append(self._stats_card)
        
        # Search bar
        search_box = self._create_search_bar()
        self.append(search_box)
        
        # Separator
        sep = Gtk.Separator()
        self.append(sep)
        
        # Conversations list (scrollable)
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        
        self._conversations_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self._conversations_box.set_margin_start(8)
        self._conversations_box.set_margin_end(8)
        self._conversations_box.set_margin_top(8)
        
        scroll.set_child(self._conversations_box)
        self.append(scroll)
        
        # Footer with new conversation button
        footer = self._create_footer()
        self.append(footer)
    
    def _create_header(self) -> Gtk.Widget:
        """Create header with title"""
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        header_box.add_css_class('history-header')
        header_box.set_margin_start(16)
        header_box.set_margin_end(16)
        header_box.set_margin_top(16)
        header_box.set_margin_bottom(12)
        
        # Icon
        icon = Gtk.Label(label="💬")
        icon.add_css_class('history-icon')
        header_box.append(icon)
        
        # Title
        title = Gtk.Label(label="Chat History")
        title.add_css_class('history-title')
        title.set_hexpand(True)
        title.set_xalign(0)
        header_box.append(title)
        
        return header_box
    
    def _create_stats_card(self) -> Gtk.Widget:
        """Create stats card"""
        card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        card.add_css_class('stats-card')
        card.set_margin_start(12)
        card.set_margin_end(12)
        card.set_margin_bottom(12)
        
        # Conversations count
        self._conv_label = Gtk.Label(label="0\nChats")
        self._conv_label.add_css_class('stat-item')
        self._conv_label.set_justify(Gtk.Justification.CENTER)
        card.append(self._conv_label)
        
        # Messages count
        self._msg_label = Gtk.Label(label="0\nMessages")
        self._msg_label.add_css_class('stat-item')
        self._msg_label.set_justify(Gtk.Justification.CENTER)
        card.append(self._msg_label)
        
        return card
    
    def _create_search_bar(self) -> Gtk.Widget:
        """Create search bar"""
        search_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        search_box.set_margin_start(12)
        search_box.set_margin_end(12)
        search_box.set_margin_bottom(8)
        
        # Search entry
        self._search_entry = Gtk.Entry()
        self._search_entry.set_placeholder_text("🔍 Search messages...")
        self._search_entry.add_css_class('history-search')
        self._search_entry.set_hexpand(True)
        self._search_entry.connect('activate', self._on_search_activated)
        search_box.append(self._search_entry)
        
        return search_box
    
    def _create_footer(self) -> Gtk.Widget:
        """Create footer with new conversation and clear all buttons"""
        footer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        footer.set_margin_top(8)
        
        sep = Gtk.Separator()
        footer.append(sep)
        
        # Button container
        btn_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        btn_box.set_margin_start(12)
        btn_box.set_margin_end(12)
        btn_box.set_margin_top(12)
        btn_box.set_margin_bottom(12)
        
        # New conversation button
        new_btn = Gtk.Button(label="➕ New Conversation")
        new_btn.add_css_class('new-conversation-btn')
        new_btn.set_hexpand(True)
        new_btn.connect('clicked', self._on_new_conversation)
        btn_box.append(new_btn)
        
        # Clear all button
        clear_all_btn = Gtk.Button(label="🗑️ Clear All Chats")
        clear_all_btn.add_css_class('clear-all-btn')
        clear_all_btn.set_hexpand(True)
        clear_all_btn.connect('clicked', self._on_clear_all)
        btn_box.append(clear_all_btn)
        
        footer.append(btn_box)
        
        return footer
    
    def _create_conversation_card(self, conv: Dict) -> Gtk.Widget:
        """Create a beautiful conversation card with delete button"""
        # Main container
        card_container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        card_container.set_margin_start(4)
        card_container.set_margin_end(4)
        card_container.set_margin_top(2)
        card_container.set_margin_bottom(2)
        
        # Clickable card button
        card = Gtk.Button()
        card.add_css_class('conversation-card')
        
        # Highlight if active
        if conv['id'] == self._active_conversation_id:
            card.add_css_class('active-conversation')
        
        # Store conversation ID in name for retrieval
        card.set_name(f"conv_{conv['id']}")
        card.connect('clicked', lambda btn: self._on_conv_clicked(conv['id']))
        
        # Card content
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        content.set_margin_start(12)
        content.set_margin_end(12)
        content.set_margin_top(10)
        content.set_margin_bottom(10)
        
        # Title + count row
        top_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        
        title = Gtk.Label(label=conv['title'])
        title.add_css_class('conv-title')
        title.set_xalign(0)
        title.set_hexpand(True)
        title.set_ellipsize(Pango.EllipsizeMode.END)
        top_row.append(title)
        
        count = Gtk.Label(label=f"{conv['message_count']} 💬")
        count.add_css_class('conv-count')
        top_row.append(count)
        
        content.append(top_row)
        
        # Timestamp with robust parsing
        try:
            updated_at = conv.get('updated_at', '') or conv.get('created_at', '')
            if updated_at:
                if isinstance(updated_at, str):
                    # Try SQLite format first (most common)
                    try:
                        dt = datetime.strptime(updated_at, '%Y-%m-%d %H:%M:%S')
                    except:
                        # Try ISO format
                        try:
                            dt = datetime.fromisoformat(updated_at.replace('Z', '+00:00').split('.')[0])
                        except:
                            # Fallback to now
                            dt = datetime.now()
                    time_str = self._format_time(dt)
                else:
                    time_str = "Recently"
            else:
                time_str = "Recently"
        except Exception as e:
            logger.warning(f"Failed to parse timestamp '{updated_at}': {e}")
            time_str = "Recently"
        
        time_label = Gtk.Label(label=f"🕒 {time_str}")
        time_label.add_css_class('conv-time')
        time_label.set_xalign(0)
        content.append(time_label)
        
        card.set_child(content)
        card_container.append(card)
        
        # Delete button (always visible for better UX)
        delete_btn = Gtk.Button()
        delete_btn.set_icon_name('edit-delete-symbolic')
        delete_btn.add_css_class('delete-conv-btn')
        delete_btn.set_tooltip_text('Delete conversation')
        delete_btn.set_visible(True)  # Always visible
        delete_btn.connect('clicked', lambda b, cid=conv['id']: self._on_delete_clicked(cid))
        card_container.append(delete_btn)
        
        return card_container
    
    def _format_time(self, dt: datetime) -> str:
        """Format timestamp nicely with proper timezone and date handling"""
        from datetime import timezone, timedelta
        
        # Get current time (local)
        now = datetime.now()
        
        # If dt is timezone-aware, convert to local time
        if dt.tzinfo is not None:
            dt = dt.astimezone().replace(tzinfo=None)
        
        # Calculate difference
        diff = now - dt
        
        # Handle negative differences (future dates) - shouldn't happen but handle gracefully
        if diff.total_seconds() < 0:
            return "Just now"
        
        total_seconds = int(diff.total_seconds())
        total_days = diff.days
        
        # Same day
        if total_days == 0:
            if total_seconds < 60:
                return "Just now"
            elif total_seconds < 3600:
                mins = total_seconds // 60
                return f"{mins}m ago"
            else:
                hours = total_seconds // 3600
                return f"{hours}h ago"
        # Yesterday
        elif total_days == 1:
            return "Yesterday"
        # This week
        elif total_days < 7:
            return f"{total_days}d ago"
        # This month
        elif total_days < 30:
            weeks = total_days // 7
            return f"{weeks}w ago"
        # Older
        else:
            # Show date if older than a month
            return dt.strftime("%b %d")
    
    def load_conversations(self, conversations: List[Dict]):
        """Load and display conversations"""
        self._conversations = conversations
        
        # Clear existing
        child = self._conversations_box.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self._conversations_box.remove(child)
            child = next_child
        
        # Add conversations
        if not conversations:
            # Empty state
            empty = Gtk.Label(label="No conversations yet\n\nStart chatting!")
            empty.add_css_class('empty-state')
            empty.set_justify(Gtk.Justification.CENTER)
            self._conversations_box.append(empty)
        else:
            for conv in conversations:
                card = self._create_conversation_card(conv)
                self._conversations_box.append(card)
    
    def update_stats(self, stats: Dict):
        """Update statistics display"""
        total_convs = stats.get('total_conversations', 0)
        total_msgs = stats.get('total_messages', 0)
        
        self._conv_label.set_text(f"{total_convs}\nChats")
        self._msg_label.set_text(f"{total_msgs}\nMessages")
    
    def _on_conv_clicked(self, conv_id: int):
        """Handle conversation click"""
        logger.info(f"Conversation {conv_id} selected")
        if self._on_conversation_selected:
            self._on_conversation_selected(conv_id)
    
    def _on_search_activated(self, entry):
        """Handle search"""
        query = entry.get_text().strip()
        if query and self._on_search:
            logger.info(f"Searching for: {query}")
            self._on_search(query)
    
    def _on_new_conversation(self, button):
        """Create new conversation"""
        # Just clear the search and notify parent
        logger.info("New conversation requested")
        if self._on_conversation_selected:
            self._on_conversation_selected(-1)  # -1 = new conversation
    
    def _on_delete_clicked(self, conv_id: int):
        """Handle delete conversation click"""
        logger.info(f"Delete conversation {conv_id} requested")
        if self._on_delete:
            self._on_delete(conv_id)
    
    def _on_clear_all(self, button):
        """Handle clear all conversations click"""
        logger.info("Clear all conversations requested")
        if self._clear_all_cb:
            self._clear_all_cb()
    
    def set_active_conversation(self, conv_id: Optional[int]):
        """Set the active conversation ID for highlighting"""
        self._active_conversation_id = conv_id
        # Refresh the UI to show highlight
        if self._conversations:
            self.load_conversations(self._conversations)
