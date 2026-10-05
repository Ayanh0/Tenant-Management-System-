import sqlite3
import os
import hashlib

DB_PATH = os.path.join(os.path.dirname(__file__), "tenantms.db")

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=20.0)
    conn.row_factory = sqlite3.Row
    conn.isolation_level = ""  # Explicit transaction mode
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA synchronous = FULL")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn

def hash_pw(pw): 
    return hashlib.sha256(pw.encode()).hexdigest()

# Test adding a tenant
conn = get_db()
print("=== Test: Adding a test tenant ===")
try:
    conn.execute("BEGIN")
    conn.execute(
        "INSERT INTO users (username,password,role,full_name,email,phone) VALUES (?,?,?,?,?,?)",
        ("testuser123", hash_pw("testpass"), "tenant", "Test User", "test@test.com", "9999999999"))
    conn.commit()
    print("✓ Tenant added successfully")
except Exception as e:
    print(f"✗ Error adding tenant: {e}")
    conn.rollback()

# Now test reading it back
print("\n=== Test: Reading tenants back ===")
conn2 = get_db()
rows = conn2.execute("SELECT id, username, full_name, role FROM users WHERE role='tenant' ORDER BY id DESC").fetchall()
conn2.close()

print(f"Found {len(rows)} tenants:")
for r in rows:
    print(f"  ID: {r[0]}, Username: {r[1]}, Name: {r[2]}")

conn.close()
