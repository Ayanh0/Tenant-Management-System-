# TenantMS – Tenant Management System
### Built with Python 3 + Tkinter + SQLite + ReportLab

---

## Quick Start

### 1. Install dependencies
```
pip install reportlab Pillow
```

### 2. Run the application
```
python main.py
```

---

## Default Login Credentials

| Role  | Username | Password  |
|-------|----------|-----------|
| Admin | admin    | admin123  |

Tenants can self-register from the Login page → **Create Account**

---

## Features
- Loading splash screen
- Login + Sign-Up (Admin / Tenant roles)
- Admin Dashboard: manage tenants, properties, agreements, payments, ID proofs
- Tenant Dashboard: view agreement, payments, upload ID proofs, profile
- PDF receipt generation for every payment
- SQLite database (auto-created on first run)

---

## Folder Structure
```
TenantMS/
├── main.py          ← Main application
├── requirements.txt ← Python dependencies
├── tenantms.db      ← SQLite database (auto-created)
├── documents/       ← Uploaded ID proof files
└── receipts/        ← Generated PDF receipts
```

---

## Tech Stack
- **Language**: Python 3.8+
- **GUI**: Tkinter (built-in)
- **Database**: SQLite3 (built-in)
- **PDF**: ReportLab
- **Hashing**: hashlib SHA-256
