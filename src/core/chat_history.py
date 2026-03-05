"""
NervaOS Chat History Manager
Persistent conversation storage with SQLite
"""

import asyncio
import aiosqlite
import json
import logging
import shutil
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

from .paths import ensure_data_dir

logger = logging.getLogger('nerva-history')

_LEGACY_DB = Path.home() / '.config' / 'nervaos' / 'chat_history.db'
_READONLY_HINT = (
    "attempt to write a readonly database. "
    "Restart the daemon: systemctl --user restart nerva-service. "
    "Ensure ~/.local/share/nervaos/data exists and is writable."
)


def _reraise_readonly(e: Exception, log: logging.Logger) -> None:
    """If e is a readonly DB error, log and raise RuntimeError with hint. Else no-op."""
    err = str(e)
    if "readonly" in err.lower() or "read-only" in err.lower():
        log.error("Chat history DB readonly: %s. %s", err, _READONLY_HINT)
        raise RuntimeError(_READONLY_HINT) from e


class ChatHistory:
    """Manages conversation history with persistence"""
    
    def __init__(self, db_path: str = None):
        if db_path is None:
            data_dir = ensure_data_dir()
            db_path = data_dir / 'chat_history.db'
        else:
            db_path = Path(db_path)
        
        self.db_path = str(db_path)
        self._db = None
    
    async def initialize(self):
        """Create database and tables"""
        db_path = Path(self.db_path)
        data_dir = db_path.parent
        # Migrate from legacy ~/.config/nervaos/chat_history.db if present
        if not db_path.exists() and _LEGACY_DB.exists():
            try:
                shutil.copy2(str(_LEGACY_DB), self.db_path)
                logger.info("Migrated chat history from %s to %s", _LEGACY_DB, self.db_path)
            except OSError as e:
                logger.warning("Could not migrate legacy DB: %s", e)
        
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self.db_path)
        
        # Enable foreign keys - DISABLED for stability
        # await self._db.execute('PRAGMA foreign_keys = ON')
        await self._db.execute('PRAGMA foreign_keys = OFF')
        
        # Create conversations table
        await self._db.execute('''
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                context TEXT
            )
        ''')
        
        # Create messages table
        await self._db.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                metadata TEXT
            )
        ''')
        # Foreign Key removed explicitly
        
        # Create indexes for faster queries
        await self._db.execute(
            'CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id)'
        )
        await self._db.execute(
            'CREATE INDEX IF NOT EXISTS idx_messages_time ON messages(timestamp)'
        )
        
        await self._db.commit()
        logger.info(f"✓ Chat history initialized: {self.db_path}")
    
    async def create_conversation(self, title: str = None) -> int:
        """Create a new conversation"""
        if title is None:
            title = f"Chat {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        
        try:
            cursor = await self._db.execute(
                'INSERT INTO conversations (title) VALUES (?)',
                (title,)
            )
            await self._db.commit()
            conv_id = cursor.lastrowid
            logger.info(f"Created conversation {conv_id}: {title}")
            return conv_id
        except Exception as e:
            await self._db.rollback()
            _reraise_readonly(e, logger)
            logger.error(f"Failed to create conversation: {e}", exc_info=True)
            raise
    
    async def add_message(self, conversation_id: int, role: str, content: str, 
                         metadata: Dict = None):
        """Add a message to a conversation"""
        if not content or not content.strip():
            logger.warning(f"Attempted to save empty message to conversation {conversation_id}")
            return
        
        metadata_json = json.dumps(metadata) if metadata else None
        
        try:
            await self._db.execute('''
                INSERT INTO messages (conversation_id, role, content, metadata)
                VALUES (?, ?, ?, ?)
            ''', (conversation_id, role, content, metadata_json))
            
            # Update conversation timestamp
            await self._db.execute('''
                UPDATE conversations 
                SET updated_at = CURRENT_TIMESTAMP 
                WHERE id = ?
            ''', (conversation_id,))
            
            await self._db.commit()
            logger.debug(f"Saved {role} message to conversation {conversation_id}")
        except Exception as e:
            await self._db.rollback()
            _reraise_readonly(e, logger)
            logger.error(f"Failed to save message to conversation {conversation_id}: {e}", exc_info=True)
            raise  # noqa: B904
    
    async def get_conversation_messages(self, conversation_id: int) -> List[Dict]:
        """Get all messages in a conversation"""
        cursor = await self._db.execute('''
            SELECT id, role, content, timestamp, metadata
            FROM messages
            WHERE conversation_id = ?
            ORDER BY timestamp ASC
        ''', (conversation_id,))
        
        messages = []
        async for row in cursor:
            messages.append({
                'id': row[0],
                'role': row[1],
                'content': row[2],
                'timestamp': row[3],
                'metadata': json.loads(row[4]) if row[4] else None
            })
        
        return messages
    
    async def get_recent_conversations(self, limit: int = 20) -> List[Dict]:
        """Get recent conversations with accurate message counts"""
        cursor = await self._db.execute('''
            SELECT c.id, c.title, c.created_at, c.updated_at, 
                   COALESCE(COUNT(m.id), 0) as message_count
            FROM conversations c
            LEFT JOIN messages m ON c.id = m.conversation_id
            GROUP BY c.id, c.title, c.created_at, c.updated_at
            ORDER BY c.updated_at DESC
            LIMIT ?
        ''', (limit,))
        
        conversations = []
        async for row in cursor:
            conversations.append({
                'id': row[0],
                'title': row[1] or 'New Chat',
                'created_at': row[2] or '',
                'updated_at': row[3] or row[2] or '',  # Use created_at if updated_at is null
                'message_count': row[4] or 0
            })
        
        return conversations
    
    async def search_messages(self, query: str, limit: int = 50) -> List[Dict]:
        """Search messages by content"""
        cursor = await self._db.execute('''
            SELECT m.id, m.conversation_id, m.role, m.content, m.timestamp,
                   c.title
            FROM messages m
            JOIN conversations c ON m.conversation_id = c.id
            WHERE m.content LIKE ?
            ORDER BY m.timestamp DESC
            LIMIT ?
        ''', (f'%{query}%', limit))
        
        results = []
        async for row in cursor:
            results.append({
                'message_id': row[0],
                'conversation_id': row[1],
                'role': row[2],
                'content': row[3],
                'timestamp': row[4],
                'conversation_title': row[5]
            })
        
        return results
    
    async def delete_conversation(self, conversation_id: int):
        """Delete a conversation and all its messages"""
        await self._db.execute(
            'DELETE FROM conversations WHERE id = ?',
            (conversation_id,)
        )
        await self._db.commit()
        logger.info(f"Deleted conversation {conversation_id}")
    
    async def delete_all_conversations(self) -> int:
        """Delete all conversations and messages - optimized bulk delete"""
        try:
            # Get count before deletion
            cursor = await self._db.execute('SELECT COUNT(*) FROM conversations')
            count = (await cursor.fetchone())[0]
            
            if count == 0:
                return 0
            
            # Use transaction for speed - delete all in one go
            # SQLite handles foreign key cascades automatically
            await self._db.execute('DELETE FROM messages')
            await self._db.execute('DELETE FROM conversations')
            
            # Single commit for both operations
            await self._db.commit()
            
            logger.info(f"Bulk deleted {count} conversations and all messages")
            return count
        except Exception as e:
            logger.error(f"Failed to delete all conversations: {e}", exc_info=True)
            await self._db.rollback()
            return 0
    
    async def update_conversation_title(self, conversation_id: int, title: str):
        """Update conversation title"""
        try:
            await self._db.execute('''
                UPDATE conversations 
                SET title = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (title, conversation_id))
            await self._db.commit()
        except Exception as e:
            await self._db.rollback()
            _reraise_readonly(e, logger)
            logger.error(f"Failed to update conversation title: {e}", exc_info=True)
            raise
    
    async def get_conversation_context(self, conversation_id: int, 
                                      last_n_messages: int = 10) -> List[Dict]:
        """Get recent messages as context for AI"""
        cursor = await self._db.execute('''
            SELECT role, content
            FROM messages
            WHERE conversation_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (conversation_id, last_n_messages))
        
        messages = []
        async for row in cursor:
            messages.append({
                'role': row[0],
                'content': row[1]
            })
        
        # Reverse to chronological order
        return list(reversed(messages))
    
    async def get_stats(self) -> Dict:
        """Get usage statistics"""
        cursor = await self._db.execute('''
            SELECT 
                COUNT(DISTINCT c.id) as total_conversations,
                COUNT(m.id) as total_messages,
                COUNT(CASE WHEN m.role = 'user' THEN 1 END) as user_messages,
                COUNT(CASE WHEN m.role = 'assistant' THEN 1 END) as ai_messages
            FROM conversations c
            LEFT JOIN messages m ON c.id = m.conversation_id
        ''')
        
        row = await cursor.fetchone()
        return {
            'total_conversations': row[0] or 0,
            'total_messages': row[1] or 0,
            'user_messages': row[2] or 0,
            'ai_messages': row[3] or 0
        }
    
    async def close(self):
        """Close database connection"""
        if self._db:
            await self._db.close()
            logger.info("Chat history closed")


class ConversationManager:
    """High-level conversation management"""
    
    def __init__(self, history: ChatHistory):
        self.history = history
        self.current_conversation_id: Optional[int] = None
    
    async def start_new_conversation(self, title: str = None) -> int:
        """Start a new conversation"""
        self.current_conversation_id = await self.history.create_conversation(title)
        return self.current_conversation_id
    
    async def send_message(self, user_message: str) -> int:
        """Add user message to current conversation"""
        if self.current_conversation_id is None:
            await self.start_new_conversation()
        
        await self.history.add_message(
            self.current_conversation_id,
            'user',
            user_message
        )
        return self.current_conversation_id
    
    async def add_ai_response(self, response: str, metadata: Dict = None):
        """Add AI response to current conversation"""
        if self.current_conversation_id is None:
            return
        
        await self.history.add_message(
            self.current_conversation_id,
            'assistant',
            response,
            metadata
        )
    
    async def switch_conversation(self, conversation_id: int):
        """Switch to an existing conversation"""
        self.current_conversation_id = conversation_id
        logger.info(f"Switched to conversation {conversation_id}")
    
    async def get_current_context(self) -> List[Dict]:
        """Get context from current conversation"""
        if self.current_conversation_id is None:
            return []
        
        return await self.history.get_conversation_context(
            self.current_conversation_id
        )
