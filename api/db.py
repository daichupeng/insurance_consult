import sqlite3
import os
from typing import List, Optional, Dict, Any

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "insurance.db")

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
        FOREIGN KEY(user_id) REFERENCES users (id)
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
            annual_premium, coverage_amount
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id, data["insurance_name"], data["status"], data.get("policy_document_url"),
        data.get("starting_year"), data.get("payment_years"), data.get("coverage_years"),
        data.get("annual_premium"), data.get("coverage_amount")
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
            annual_premium = ?, coverage_amount = ?
        WHERE id = ? AND user_id = ?
    """, (
        data["insurance_name"], data["status"], data.get("policy_document_url"),
        data.get("starting_year"), data.get("payment_years"), data.get("coverage_years"),
        data.get("annual_premium"), data.get("coverage_amount"),
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

if __name__ == "__main__":
    init_db()
