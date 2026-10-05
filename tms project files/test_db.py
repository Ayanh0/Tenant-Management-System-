import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "tenantms.db")

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

# Check tables
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print("Tables:", [t[0] for t in tables])

# Check users (tenants)
users = conn.execute("SELECT id, username, full_name, role FROM users WHERE role='tenant'").fetchall()
print("\nTenants in database:")
for u in users:
    print(f"  ID: {u[0]}, Username: {u[1]}, Name: {u[2]}, Role: {u[3]}")

conn.close()
print("\nDatabase file exists:", os.path.exists(DB_PATH))
