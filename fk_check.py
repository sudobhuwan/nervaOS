
import asyncio
import aiosqlite
import os
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('fk-check')

DB_PATH = os.path.expanduser('~/.local/share/nervaos/data/chat_history.db')

async def check_fk():
    print(f"Checking DB: {DB_PATH}")
    
    conn = await aiosqlite.connect(DB_PATH)
    await conn.execute('PRAGMA foreign_keys = ON')
    
    # 1. Create a conversation
    try:
        cursor = await conn.execute("INSERT INTO conversations (title) VALUES ('FK Test')")
        conv_id = cursor.lastrowid
        await conn.commit()
        print(f"Created conversation {conv_id}")
    except Exception as e:
        print(f"Failed to create conversation: {e}")
        return

    # 2. Insert message linked to it
    try:
        await conn.execute(
            "INSERT INTO messages (conversation_id, role, content) VALUES (?, ?, ?)",
            (conv_id, 'user', 'test message')
        )
        await conn.commit()
        print("Inserted message successfully")
    except Exception as e:
        print(f"Failed to insert message with valid FK: {e}")

    # 3. Try to insert message with INVALID FK
    try:
        await conn.execute(
            "INSERT INTO messages (conversation_id, role, content) VALUES (?, ?, ?)",
            (999999, 'user', 'invalid fk')
        )
        await conn.commit()
        print("ERROR: Inserted message with INVALID FK (Should have failed!)")
    except Exception as e:
        print(f"SUCCESS: Blocked invalid FK: {e}")
        
    # Cleanup
    await conn.execute("DELETE FROM messages WHERE content='test message'")
    await conn.execute(f"DELETE FROM conversations WHERE id={conv_id}")
    await conn.commit()
    await conn.close()

if __name__ == "__main__":
    asyncio.run(check_fk())
