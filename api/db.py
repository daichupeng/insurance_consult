import sqlite3
import os
from typing import List, Optional, Dict, Any
import json

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "databases", "insurance.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    # Already created in earlier steps but let's ensure
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER NOT NULL, 
        email VARCHAR, 
        name VARCHAR, 
        picture VARCHAR, 
        dob VARCHAR,
        gender VARCHAR,
        smoking_status VARCHAR,
        marital_status VARCHAR,
        num_children INTEGER,
        PRIMARY KEY (id)
    )
    """)
    
    # Auto-migration: Check if columns exist, if not add them
    cursor.execute("PRAGMA table_info(users)")
    existing_columns = [row[1] for row in cursor.fetchall()]
    new_columns = [
        ("dob", "VARCHAR"),
        ("gender", "VARCHAR"),
        ("smoking_status", "VARCHAR"),
        ("marital_status", "VARCHAR"),
        ("num_children", "INTEGER")
    ]
    for col_name, col_type in new_columns:
        if col_name not in existing_columns:
            cursor.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}")
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email ON users (email)")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS policies (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        user_id INTEGER, 
        insurance_name VARCHAR, 
        status VARCHAR, 
        policy_document_url VARCHAR, 
        starting_year INTEGER, 
        payment_years INTEGER, 
        coverage_years INTEGER, 
        annual_premium FLOAT, 
        coverage_amount FLOAT, 
        category VARCHAR DEFAULT 'life',
        type VARCHAR DEFAULT 'personal',
        FOREIGN KEY(user_id) REFERENCES users (id)
    )
    """)
    
    # Auto-migration for policies table
    cursor.execute("PRAGMA table_info(policies)")
    existing_policy_columns = [row[1] for row in cursor.fetchall()]
    new_policy_columns = [
        ("category", "VARCHAR DEFAULT 'life'"),
        ("type", "VARCHAR DEFAULT 'personal'")
    ]
    for col_name, col_type in new_policy_columns:
        if col_name not in existing_policy_columns:
            cursor.execute(f"ALTER TABLE policies ADD COLUMN {col_name} {col_type}")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS conversations (
        id VARCHAR PRIMARY KEY,
        user_id INTEGER,
        title VARCHAR,
        phase VARCHAR,
        state_data TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users (id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id VARCHAR,
        role VARCHAR,
        type VARCHAR,
        content TEXT,
        raw_data TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(conversation_id) REFERENCES conversations(id)
    )
    """)

    conn.commit()
    conn.close()

# User operations
def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    conn.close()
    return dict(user) if user else None

def create_user(email: str, name: str, picture: str) -> Dict[str, Any]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO users (email, name, picture) VALUES (?, ?, ?)", (email, name, picture))
    user_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return {"id": user_id, "email": email, "name": name, "picture": picture}

def update_user(email: str, name: str, picture: str, profile_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    conn = get_db()
    if profile_data:
        conn.execute("""
            UPDATE users SET 
                name = ?, 
                dob = ?, 
                gender = ?, 
                smoking_status = ?, 
                marital_status = ?, 
                num_children = ? 
            WHERE email = ?
        """, (
            name, 
            profile_data.get("dob"), 
            profile_data.get("gender"), 
            profile_data.get("smoking_status"), 
            profile_data.get("marital_status"), 
            profile_data.get("num_children"), 
            email
        ))
    else:
        conn.execute("UPDATE users SET name = ?, picture = ? WHERE email = ?", (name, picture, email))
    conn.commit()
    user = get_user_by_email(email)
    conn.close()
    return user

# Policy operations
def get_user_policies(user_id: int) -> List[Dict[str, Any]]:
    conn = get_db()
    policies = conn.execute("SELECT * FROM policies WHERE user_id = ?", (user_id,)).fetchall()
    conn.close()
    return [dict(p) for p in policies]

def create_policy(user_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO policies (
            user_id, insurance_name, status, policy_document_url, 
            starting_year, payment_years, coverage_years, 
            annual_premium, coverage_amount, category, type
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id, data["insurance_name"], data["status"], data.get("policy_document_url"),
        data.get("starting_year"), data.get("payment_years"), data.get("coverage_years"),
        data.get("annual_premium"), data.get("coverage_amount"),
        data.get("category", "life"), data.get("type", "personal")
    ))
    policy_id = cursor.lastrowid
    conn.commit()
    conn.close()
    data["id"] = policy_id
    data["user_id"] = user_id
    return data

def update_policy(policy_id: int, user_id: int, data: Dict[str, Any]) -> bool:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE policies SET 
            insurance_name = ?, status = ?, policy_document_url = ?, 
            starting_year = ?, payment_years = ?, coverage_years = ?, 
            annual_premium = ?, coverage_amount = ?, category = ?, type = ?
        WHERE id = ? AND user_id = ?
    """, (
        data["insurance_name"], data["status"], data.get("policy_document_url"),
        data.get("starting_year"), data.get("payment_years"), data.get("coverage_years"),
        data.get("annual_premium"), data.get("coverage_amount"),
        data.get("category", "life"), data.get("type", "personal"),
        policy_id, user_id
    ))
    rows = cursor.rowcount
    conn.commit()
    conn.close()
    return rows > 0

def delete_policy(policy_id: int, user_id: int) -> bool:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM policies WHERE id = ? AND user_id = ?", (policy_id, user_id))
    rows = cursor.rowcount
    conn.commit()
    conn.close()
    return rows > 0

# Conversation operations
def get_user_conversations(user_id: int) -> List[Dict[str, Any]]:
    conn = get_db()
    convs = conn.execute("SELECT * FROM conversations WHERE user_id = ? ORDER BY updated_at DESC", (user_id,)).fetchall()
    conn.close()
    return [dict(c) for c in convs]

def get_conversation(conv_id: str) -> Optional[Dict[str, Any]]:
    conn = get_db()
    conv = conn.execute("SELECT * FROM conversations WHERE id = ?", (conv_id,)).fetchone()
    conn.close()
    if conv:
        c = dict(conv)
        c['state_data'] = json.loads(c['state_data']) if c['state_data'] else {}
        return c
    return None

def create_conversation(conv_id: str, user_id: int, title: str = "New Conversation", phase: str = "idle", state_data: dict = {}) -> Dict[str, Any]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO conversations (id, user_id, title, phase, state_data)
        VALUES (?, ?, ?, ?, ?)
    """, (conv_id, user_id, title, phase, json.dumps(state_data)))
    conn.commit()
    conn.close()
    return {"id": conv_id, "user_id": user_id, "title": title, "phase": phase, "state_data": state_data}

def update_conversation(conv_id: str, phase: str, state_data: dict, title: Optional[str] = None):
    conn = get_db()
    cursor = conn.cursor()
    if title is not None:
        cursor.execute("""
            UPDATE conversations SET phase = ?, state_data = ?, title = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (phase, json.dumps(state_data), title, conv_id))
    else:
        cursor.execute("""
            UPDATE conversations SET phase = ?, state_data = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (phase, json.dumps(state_data), conv_id))
    conn.commit()
    conn.close()

def update_conversation_title(conv_id: str, title: str):
    conn = get_db()
    conn.execute("UPDATE conversations SET title = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (title, conv_id))
    conn.commit()
    conn.close()

def delete_conversation(conv_id: str, user_id: int) -> bool:
    conn = get_db()
    cursor = conn.cursor()
    # verify ownership
    conv = cursor.execute("SELECT id FROM conversations WHERE id = ? AND user_id = ?", (conv_id, user_id)).fetchone()
    if not conv:
        conn.close()
        return False
        
    cursor.execute("DELETE FROM messages WHERE conversation_id = ?", (conv_id,))
    cursor.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
    rows = cursor.rowcount
    conn.commit()
    conn.close()
    return rows > 0

def get_conversation_messages(conv_id: str) -> List[Dict[str, Any]]:
    conn = get_db()
    msgs = conn.execute("SELECT * FROM messages WHERE conversation_id = ? ORDER BY id ASC", (conv_id,)).fetchall()
    conn.close()
    result = []
    for m in msgs:
        d = dict(m)
        d['raw_data'] = json.loads(d['raw_data']) if d['raw_data'] else {}
        result.append(d)
    return result

def add_message(conv_id: str, role: str, msg_type: str, content: str, raw_data: dict):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO messages (conversation_id, role, type, content, raw_data)
        VALUES (?, ?, ?, ?, ?)
    """, (conv_id, role, msg_type, content, json.dumps(raw_data)))
    cursor.execute("UPDATE conversations SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (conv_id,))
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
