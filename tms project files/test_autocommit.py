import sqlite3
import os
import hashlib
import time

DB_PATH = os.path.join(os.path.dirname(__file__), "tenantms.db")

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=20.0)
    conn.row_factory = sqlite3.Row
    conn.isolation_level = None  # Autocommit mode - data persists immediately
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA synchronous = FULL")  
    conn.execute("PRAGMA journal_mode = WAL")
    return conn

def hash_pw(pw): 
    return hashlib.sha256(pw.encode()).hexdigest()

# Test adding a tenant with autocommit mode
conn = get_db()
print("=== Test: Adding tenant with AUTOCOMMIT mode ===")
try:
    conn.execute(
        "INSERT INTO users (username,password,role,full_name,email,phone) VALUES (?,?,?,?,?,?)",
        ("autocommit_test", hash_pw("testpass"), "tenant", "AutoCommit Test", "auto@test.com", "8888888888"))
    # Note: no commit() needed in autocommit mode
    print("✓ Tenant added (autocommit)")
except Exception as e:
    print(f"✗ Error: {e}")

conn.close()

# Now simulate app restart - open new connection
print("\n=== Test: Reading tenants AFTER 'restart' ===")
time.sleep(0.5)  # Simulate closing and reopening app
conn2 = get_db()
rows = conn2.execute("SELECT id, username, full_name, role FROM users WHERE role='tenant' ORDER BY id DESC LIMIT 3").fetchall()
conn2.close()

print(f"Found {len(rows)} recent tenants:")
for r in rows:
    print(f"  ID: {r[0]}, Username: {r[1]}, Name: {r[2]}")
    if r[1] == "autocommit_test":
        print("  ✓ AUTOCOMMIT TEST TENANT FOUND - DATA PERSISTED!")
