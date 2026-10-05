"""
TenantMS - Tenant Management System
A complete rental management solution with Admin and Tenant portals.
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import sqlite3
import hashlib
import os
import shutil
from datetime import datetime, date, timedelta
import calendar
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
import threading
import time

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, "tenantms.db")
DOCS_DIR = os.path.join(BASE_DIR, "documents")
RECEIPTS_DIR = os.path.join(BASE_DIR, "receipts")
os.makedirs(DOCS_DIR, exist_ok=True)
os.makedirs(RECEIPTS_DIR, exist_ok=True)

# ── Colour Palette ─────────────────────────────────────────────────────────────
C = {
    "bg":       "#0F1923",
    "panel":    "#1A2740",
    "card":     "#243350",
    "accent":   "#3ADE1D",
    "accent2":  "#3ADE1D",
    "success":  "#4CAF50",
    "warning":  "#FFC107",
    "danger":   "#F44336",
    "text":     "#ECEFF1",
    "subtext":  "#90A4AE",
    "border":   "#2D4060",
    "white":    "#FFFFFF",
    "hover":    "#077B11",
    "entry_bg": "#162030",
}

FONT = "Segoe UI"

# ══════════════════════════════════════════════════════════════════════════════
#  DATABASE
# ══════════════════════════════════════════════════════════════════════════════
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            username    TEXT UNIQUE NOT NULL,
            password    TEXT NOT NULL,
            role        TEXT NOT NULL CHECK(role IN ('admin','tenant')),
            full_name   TEXT NOT NULL,
            email       TEXT,
            phone       TEXT,
            created_at  TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS properties (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            address     TEXT NOT NULL,
            unit_number TEXT,
            city        TEXT,
            monthly_rent REAL NOT NULL,
            status      TEXT DEFAULT 'vacant' CHECK(status IN ('occupied','vacant','maintenance')),
            created_at  TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS agreements (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id       INTEGER NOT NULL REFERENCES users(id),
            property_id     INTEGER NOT NULL REFERENCES properties(id),
            start_date      TEXT NOT NULL,
            end_date        TEXT NOT NULL,
            monthly_rent    REAL NOT NULL,
            security_deposit REAL DEFAULT 0,
            status          TEXT DEFAULT 'active' CHECK(status IN ('active','expired','terminated')),
            terms           TEXT,
            created_at      TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS payments (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            agreement_id    INTEGER NOT NULL REFERENCES agreements(id),
            tenant_id       INTEGER NOT NULL REFERENCES users(id),
            amount          REAL NOT NULL,
            payment_date    TEXT NOT NULL,
            due_date        TEXT,
            method          TEXT DEFAULT 'cash',
            status          TEXT DEFAULT 'paid' CHECK(status IN ('paid','pending','overdue')),
            notes           TEXT,
            receipt_number  TEXT UNIQUE,
            created_at      TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS id_proofs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id       INTEGER NOT NULL REFERENCES users(id),
            doc_type        TEXT NOT NULL,
            doc_number      TEXT NOT NULL,
            file_path       TEXT,
            verified        INTEGER DEFAULT 0,
            uploaded_at     TEXT DEFAULT (datetime('now','localtime'))
        );
    """)

    # Default admin
    pw = hashlib.sha256("admin123".encode()).hexdigest()
    c.execute("INSERT OR IGNORE INTO users (username,password,role,full_name,email,phone) VALUES (?,?,?,?,?,?)",
              ("admin", pw, "admin", "System Administrator", "admin@tenantms.com", "9999999999"))

    # Ensure property uniqueness so sample seed data doesn't duplicate on every startup
    c.execute("DELETE FROM properties WHERE id IN ("
              "SELECT p1.id FROM properties p1 "
              "JOIN properties p2 ON p1.name=p2.name "
              "AND p1.address=p2.address "
              "AND p1.unit_number=p2.unit_number "
              "AND p1.id>p2.id)")
    try:
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_properties_unique ON properties(name,address,unit_number)")
    except sqlite3.IntegrityError:
        c.execute("DELETE FROM properties WHERE id IN ("
                  "SELECT p1.id FROM properties p1 "
                  "JOIN properties p2 ON p1.name=p2.name "
                  "AND p1.address=p2.address "
                  "AND p1.unit_number=p2.unit_number "
                  "AND p1.id>p2.id)")
        c.execute("DROP INDEX IF EXISTS idx_properties_unique")
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_properties_unique ON properties(name,address,unit_number)")

    # Sample properties
    props = [
        ("Flat 101 - Sunrise Apts", "MG Road, Guwahati", "101", "Guwahati", 12000, "vacant"),
        ("Flat 202 - Sunrise Apts", "MG Road, Guwahati", "202", "Guwahati", 15000, "vacant"),
        ("Shop 1 - Market Complex",  "Fancy Bazar, Guwahati", "S1",  "Guwahati", 20000, "vacant"),
    ]
    c.executemany(
        "INSERT OR IGNORE INTO properties (name,address,unit_number,city,monthly_rent,status) VALUES (?,?,?,?,?,?)",
        props)

    conn.commit()
    conn.close()

def hash_pw(pw): return hashlib.sha256(pw.encode()).hexdigest()

def gen_receipt_no():
    return f"RCP{datetime.now().strftime('%Y%m%d%H%M%S')}"

# ══════════════════════════════════════════════════════════════════════════════
#  WIDGETS
# ══════════════════════════════════════════════════════════════════════════════
def styled_btn(parent, text, cmd, color=None, width=14, height=1, font_size=10):
    bg = color or C["accent"]
    b = tk.Button(parent, text=text, command=cmd, bg=bg, fg=C["white"],
                  font=(FONT, font_size, "bold"), relief="flat", cursor="hand2",
                  width=width, height=height, activebackground=C["hover"],
                  activeforeground=C["white"], bd=0, padx=8, pady=4)
    b.bind("<Enter>", lambda e: b.config(bg=C["hover"] if bg == C["accent"] else bg))
    b.bind("<Leave>", lambda e: b.config(bg=bg))
    return b

def entry_field(parent, placeholder="", show="", width=28):
    frame = tk.Frame(parent, bg=C["card"], bd=0)
    e = tk.Entry(frame, bg=C["entry_bg"], fg=C["text"], font=(FONT, 11),
                 relief="flat", bd=0, width=width, show=show,
                 insertbackground=C["accent"])
    e.pack(ipady=8, padx=8)
    if placeholder:
        e.insert(0, placeholder)
        e.config(fg=C["subtext"])
        def on_focus_in(ev):
            if e.get() == placeholder:
                e.delete(0, "end")
                e.config(fg=C["text"])
        def on_focus_out(ev):
            if not e.get():
                e.insert(0, placeholder)
                e.config(fg=C["subtext"])
        e.bind("<FocusIn>", on_focus_in)
        e.bind("<FocusOut>", on_focus_out)
    return frame, e

def label(parent, text, size=11, bold=False, color=None, anchor="w"):
    return tk.Label(parent, text=text, bg=C["card"],
                    fg=color or C["text"],
                    font=(FONT, size, "bold" if bold else "normal"),
                    anchor=anchor)

def card_frame(parent, **kw):
    return tk.Frame(parent, bg=C["card"], bd=0, **kw)

def separator(parent, color=None):
    return tk.Frame(parent, bg=color or C["border"], height=1)

def status_badge(parent, text, kind="info"):
    colors_map = {"info": C["accent"], "success": C["success"],
                  "warning": C["warning"], "danger": C["danger"]}
    bg = colors_map.get(kind, C["accent"])
    return tk.Label(parent, text=f"  {text}  ", bg=bg, fg=C["white"],
                    font=(FONT, 8, "bold"), relief="flat", padx=4, pady=2)

# ══════════════════════════════════════════════════════════════════════════════
#  RECEIPT GENERATOR (PDF)
# ══════════════════════════════════════════════════════════════════════════════
def generate_receipt(payment_id):
    conn = get_db()
    row = conn.execute("""
        SELECT p.*, u.full_name as tenant_name, u.phone as tenant_phone,
               pr.name as property_name, pr.address as property_address,
               pr.unit_number
        FROM payments p
        JOIN users u ON u.id = p.tenant_id
        JOIN agreements a ON a.id = p.agreement_id
        JOIN properties pr ON pr.id = a.property_id
        WHERE p.id = ?
    """, (payment_id,)).fetchone()
    conn.close()

    if not row:
        return None

    filename = f"Receipt_{row['receipt_number']}.pdf"
    filepath = os.path.join(RECEIPTS_DIR, filename)

    doc = SimpleDocTemplate(filepath, pagesize=A4,
                            topMargin=1.5*cm, bottomMargin=1.5*cm,
                            leftMargin=2*cm, rightMargin=2*cm)
    styles = getSampleStyleSheet()

    title_style   = ParagraphStyle("title",   parent=styles["Normal"],
                                   fontSize=20, textColor=colors.HexColor("#2196F3"),
                                   alignment=TA_CENTER, fontName="Helvetica-Bold", spaceAfter=4)
    sub_style     = ParagraphStyle("sub",     parent=styles["Normal"],
                                   fontSize=10, textColor=colors.HexColor("#607D8B"),
                                   alignment=TA_CENTER, spaceAfter=2)
    heading_style = ParagraphStyle("heading", parent=styles["Normal"],
                                   fontSize=12, textColor=colors.HexColor("#1A237E"),
                                   fontName="Helvetica-Bold", spaceAfter=6)
    normal_style  = ParagraphStyle("norm",    parent=styles["Normal"],
                                   fontSize=10, leading=14)

    story = [
        Paragraph("TenantMS", title_style),
        Paragraph("Tenant Management System", sub_style),
        Paragraph("━" * 70, sub_style),
        Spacer(1, 0.3*cm),
        Paragraph("PAYMENT RECEIPT", ParagraphStyle("rc", parent=title_style, fontSize=16,
                  textColor=colors.HexColor("#1A237E"))),
        Spacer(1, 0.5*cm),
    ]

    meta_data = [
        ["Receipt No.", row["receipt_number"], "Date", row["payment_date"]],
    ]
    meta_table = Table(meta_data, colWidths=[3.5*cm, 7*cm, 3*cm, 4*cm])
    meta_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (0,-1), colors.HexColor("#E3F2FD")),
        ("BACKGROUND", (2,0), (2,-1), colors.HexColor("#E3F2FD")),
        ("FONTNAME", (0,0), (-1,-1), "Helvetica"),
        ("FONTSIZE", (0,0), (-1,-1), 9),
        ("FONTNAME", (1,0), (1,-1), "Helvetica-Bold"),
        ("FONTNAME", (3,0), (3,-1), "Helvetica-Bold"),
        ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#BBDEFB")),
        ("PADDING", (0,0), (-1,-1), 6),
    ]))
    story += [meta_table, Spacer(1, 0.4*cm)]

    story.append(Paragraph("Tenant Details", heading_style))
    tenant_data = [
        ["Name",     row["tenant_name"]],
        ["Phone",    row["tenant_phone"] or "—"],
        ["Property", row["property_name"]],
        ["Address",  f"{row['property_address']} | Unit: {row['unit_number'] or '—'}"],
    ]
    t = Table(tenant_data, colWidths=[4*cm, 13.5*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (0,-1), colors.HexColor("#F5F5F5")),
        ("FONTNAME", (0,0), (0,-1), "Helvetica-Bold"),
        ("FONTNAME", (1,0), (1,-1), "Helvetica"),
        ("FONTSIZE", (0,0), (-1,-1), 9),
        ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#E0E0E0")),
        ("PADDING", (0,0), (-1,-1), 7),
    ]))
    story += [t, Spacer(1, 0.5*cm)]

    story.append(Paragraph("Payment Details", heading_style))
    pay_data = [
        ["Description", "Amount (₹)"],
        ["Rent Payment", f"₹ {row['amount']:,.2f}"],
        ["Payment Method", row["method"].upper()],
        ["Status", row["status"].upper()],
    ]
    if row["notes"]:
        pay_data.append(["Notes", row["notes"]])
    pt = Table(pay_data, colWidths=[9.75*cm, 7.75*cm])
    pt.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#1A237E")),
        ("TEXTCOLOR",  (0,0), (-1,0), colors.white),
        ("FONTNAME",   (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",   (0,0), (-1,-1), 10),
        ("BACKGROUND", (0,1), (-1,1), colors.HexColor("#E3F2FD")),
        ("FONTNAME",   (0,1), (-1,1), "Helvetica-Bold"),
        ("GRID",       (0,0), (-1,-1), 0.5, colors.HexColor("#BBDEFB")),
        ("PADDING",    (0,0), (-1,-1), 8),
        ("ALIGN",      (1,0), (1,-1), "RIGHT"),
    ]))
    story += [pt, Spacer(1, 1*cm)]

    story.append(Paragraph(
        "This is a computer-generated receipt and does not require a signature.",
        ParagraphStyle("footer", parent=styles["Normal"], fontSize=8,
                       textColor=colors.HexColor("#9E9E9E"), alignment=TA_CENTER)
    ))
    story.append(Paragraph(
        f"Generated on {datetime.now().strftime('%d-%b-%Y %I:%M %p')} by TenantMS",
        ParagraphStyle("footer2", parent=styles["Normal"], fontSize=8,
                       textColor=colors.HexColor("#9E9E9E"), alignment=TA_CENTER)
    ))

    doc.build(story)
    return filepath

# ══════════════════════════════════════════════════════════════════════════════
#  LOADING SCREEN
# ══════════════════════════════════════════════════════════════════════════════
class LoadingScreen(tk.Frame):
    def __init__(self, master, on_done):
        super().__init__(master, bg=C["bg"])
        self.master  = master
        self.on_done = on_done
        self.pack(fill="both", expand=True)
        self._build()

    def _build(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        center = tk.Frame(self, bg=C["bg"])
        center.place(relx=0.5, rely=0.5, anchor="center")

        # Logo
        canvas = tk.Canvas(center, width=100, height=100, bg=C["bg"], highlightthickness=0)
        canvas.pack(pady=(0, 20))
        canvas.create_oval(5, 5, 95, 95, fill=C["accent"], outline=C["accent2"], width=4)
        canvas.create_text(50, 45, text="T", font=(FONT, 42, "bold"), fill=C["white"])
        canvas.create_text(50, 85, text="MS", font=(FONT, 14, "bold"), fill=C["accent2"])

        tk.Label(center, text="TenantMS", bg=C["bg"], fg=C["white"],
                 font=(FONT, 32, "bold")).pack()
        tk.Label(center, text="Tenant Management System", bg=C["bg"], fg=C["subtext"],
                 font=(FONT, 13)).pack(pady=(4, 30))

        # Progress bar
        pb_frame = tk.Frame(center, bg=C["border"], width=360, height=6)
        pb_frame.pack()
        pb_frame.pack_propagate(False)
        self.pb_fill = tk.Frame(pb_frame, bg=C["accent"], height=6, width=0)
        self.pb_fill.place(x=0, y=0)

        self.status_lbl = tk.Label(center, text="Initialising…", bg=C["bg"],
                                   fg=C["subtext"], font=(FONT, 10))
        self.status_lbl.pack(pady=8)

        tk.Label(center, text="v1.0  •  Built with Python & Tkinter",
                 bg=C["bg"], fg=C["border"], font=(FONT, 8)).pack(pady=(30, 0))

        self._animate(0)

    def _animate(self, step):
        msgs = ["Initialising database…", "Loading configurations…",
                "Preparing modules…", "Almost ready…", "Welcome!"]
        total = 60
        if step <= total:
            w = int((step / total) * 360)
            self.pb_fill.config(width=w)
            idx = min(step // 13, len(msgs)-1)
            self.status_lbl.config(text=msgs[idx])
            self.master.after(30, lambda: self._animate(step + 1))
        else:
            self.master.after(300, self.on_done)

# ══════════════════════════════════════════════════════════════════════════════
#  AUTH SCREEN
# ══════════════════════════════════════════════════════════════════════════════
class AuthScreen(tk.Frame):
    def __init__(self, master, on_login):
        super().__init__(master, bg=C["bg"])
        self.master   = master
        self.on_login = on_login
        self.mode     = "login"   # or "signup"
        self.role_var = tk.StringVar(value="tenant")
        self.pack(fill="both", expand=True)
        self._build()

    def _build(self):
        # Left decorative panel
        left = tk.Frame(self, bg=C["panel"], width=320)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)

        tk.Label(left, text="", bg=C["panel"]).pack(pady=60)
        canvas = tk.Canvas(left, width=90, height=90, bg=C["panel"], highlightthickness=0)
        canvas.pack()
        canvas.create_oval(3, 3, 87, 87, fill=C["accent"], outline=C["accent2"], width=3)
        canvas.create_text(45, 40, text="T", font=(FONT, 36, "bold"), fill=C["white"])
        canvas.create_text(45, 72, text="MS", font=(FONT, 12, "bold"), fill=C["accent2"])

        tk.Label(left, text="TenantMS", bg=C["panel"], fg=C["white"],
                 font=(FONT, 26, "bold")).pack(pady=(16, 4))
        tk.Label(left, text="Tenant Management System", bg=C["panel"],
                 fg=C["subtext"], font=(FONT, 11)).pack()

        separator(left).pack(fill="x", padx=30, pady=30)

        features = ["📋  Track Rental Agreements",
                    "💳  Manage Payments & Receipts",
                    "🪪  Store ID Proofs Securely",
                    "🏠  Property Management",
                    "📊  Dashboards & Reports"]
        for f in features:
            tk.Label(left, text=f, bg=C["panel"], fg=C["subtext"],
                     font=(FONT, 10), anchor="w", padx=30).pack(fill="x", pady=4)

        # Right form panel
        self.right = tk.Frame(self, bg=C["bg"])
        self.right.pack(side="left", fill="both", expand=True)
        self._show_form()

    def _clear_right(self):
        for w in self.right.winfo_children():
            w.destroy()

    def _show_form(self):
        self._clear_right()
        container = tk.Frame(self.right, bg=C["card"], padx=50, pady=48)
        container.place(relx=0.5, rely=0.5, anchor="center", width=500)

        if self.mode == "login":
            self._login_form(container)
        else:
            self._signup_form(container)

    def _login_form(self, p):
        tk.Label(p, text="Welcome Back!", bg=C["card"], fg=C["white"],
                 font=(FONT, 24, "bold")).pack(anchor="w")
        tk.Label(p, text="Sign in to your account", bg=C["card"],
                 fg=C["subtext"], font=(FONT, 11)).pack(anchor="w", pady=(4, 24))

        role_row = tk.Frame(p, bg=C["card"])
        role_row.pack(fill="x", pady=(0, 18))
        tk.Label(role_row, text="Login as:", bg=C["card"], fg=C["subtext"],
                 font=(FONT, 10)).pack(side="left")
        for r, lbl in [("admin","Admin"), ("tenant","Tenant")]:
            tk.Radiobutton(role_row, text=lbl, variable=self.role_var, value=r,
                           bg=C["card"], fg=C["text"], activebackground=C["card"],
                           activeforeground=C["accent"], selectcolor=C["entry_bg"],
                           font=(FONT, 10), cursor="hand2").pack(side="left", padx=12)

        input_frame = tk.Frame(p, bg=C["card"])
        input_frame.pack(fill="x", pady=(0, 18))

        left_col = tk.Frame(input_frame, bg=C["card"])
        left_col.pack(side="left", fill="both", expand=True, padx=(0, 8))
        right_col = tk.Frame(input_frame, bg=C["card"])
        right_col.pack(side="left", fill="both", expand=True, padx=(8, 0))

        tk.Label(left_col, text="Username", bg=C["card"], fg=C["subtext"],
                 font=(FONT, 9)).pack(anchor="w")
        uf, self.username_e = entry_field(left_col, width=18)
        uf.pack(fill="x", pady=(4, 0))

        tk.Label(right_col, text="Password", bg=C["card"], fg=C["subtext"],
                 font=(FONT, 9)).pack(anchor="w")
        pf, self.password_e = entry_field(right_col, show="●", width=18)
        pf.pack(fill="x", pady=(4, 0))

        styled_btn(p, "Login →", self._do_login, width=36, height=2,
                   font_size=12).pack(fill="x", pady=(20, 0))

        separator(p).pack(fill="x", pady=22)
        row = tk.Frame(p, bg=C["card"])
        row.pack()
        tk.Label(row, text="New user?", bg=C["card"], fg=C["subtext"],
                 font=(FONT, 10)).pack(side="left")
        lnk = tk.Label(row, text=" Create account", bg=C["card"],
                       fg=C["accent"], font=(FONT, 10, "underline"), cursor="hand2")
        lnk.pack(side="left")
        lnk.bind("<Button-1>", lambda e: self._switch("signup"))

    def _signup_form(self, p):
        tk.Label(p, text="Create Account", bg=C["card"], fg=C["white"],
                 font=(FONT, 22, "bold")).pack(anchor="w")
        tk.Label(p, text="Tenant self-registration", bg=C["card"],
                 fg=C["subtext"], font=(FONT, 11)).pack(anchor="w", pady=(2, 14))

        fields = [("Full Name", False), ("Username", False),
                  ("Email", False), ("Phone", False),
                  ("Password", True), ("Confirm Password", True)]
        self.signup_entries = {}
        for label_text, is_pw in fields:
            tk.Label(p, text=label_text, bg=C["card"], fg=C["subtext"],
                     font=(FONT, 9)).pack(anchor="w")
            frm, ent = entry_field(p, show="●" if is_pw else "", width=32)
            frm.pack(fill="x", pady=(2, 8))
            self.signup_entries[label_text] = ent

        styled_btn(p, "Create Account", self._do_signup, color=C["success"],
                   width=32, height=2, font_size=11).pack(fill="x", pady=(8, 0))

        separator(p).pack(fill="x", pady=14)
        row = tk.Frame(p, bg=C["card"])
        row.pack()
        tk.Label(row, text="Already have an account?", bg=C["card"],
                 fg=C["subtext"], font=(FONT, 10)).pack(side="left")
        lnk = tk.Label(row, text=" Sign in", bg=C["card"],
                       fg=C["accent"], font=(FONT, 10, "underline"), cursor="hand2")
        lnk.pack(side="left")
        lnk.bind("<Button-1>", lambda e: self._switch("login"))

    def _switch(self, mode):
        self.mode = mode
        self._show_form()

    def _do_login(self):
        u = self.username_e.get().strip()
        p = self.password_e.get().strip()
        r = self.role_var.get()
        if not u or not p:
            messagebox.showerror("Error", "Please enter username and password.")
            return
        conn = get_db()
        row = conn.execute(
            "SELECT * FROM users WHERE username=? AND password=? AND role=?",
            (u, hash_pw(p), r)).fetchone()
        conn.close()
        if row:
            self.on_login(dict(row))
        else:
            messagebox.showerror("Login Failed", "Invalid credentials or wrong role selected.")

    def _do_signup(self):
        e = self.signup_entries
        name = e["Full Name"].get().strip()
        user = e["Username"].get().strip()
        email = e["Email"].get().strip()
        phone = e["Phone"].get().strip()
        pw   = e["Password"].get().strip()
        cpw  = e["Confirm Password"].get().strip()
        if not all([name, user, pw, cpw]):
            messagebox.showerror("Error", "Name, username and password are required.")
            return
        if pw != cpw:
            messagebox.showerror("Error", "Passwords do not match.")
            return
        if len(pw) < 6:
            messagebox.showerror("Error", "Password must be at least 6 characters.")
            return
        try:
            conn = get_db()
            conn.execute(
                "INSERT INTO users (username,password,role,full_name,email,phone) VALUES (?,?,?,?,?,?)",
                (user, hash_pw(pw), "tenant", name, email, phone))
            conn.commit()
            conn.close()
            messagebox.showinfo("Success", "Account created! Please login.")
            self._switch("login")
        except sqlite3.IntegrityError:
            messagebox.showerror("Error", "Username already exists.")

# ══════════════════════════════════════════════════════════════════════════════
#  SHARED COMPONENTS
# ══════════════════════════════════════════════════════════════════════════════
class Sidebar(tk.Frame):
    def __init__(self, master, menu_items, on_select, user_info, on_logout, width=220):
        super().__init__(master, bg=C["panel"], width=width)
        self.pack(side="left", fill="y")
        self.pack_propagate(False)
        self.buttons   = {}
        self.active    = None
        self.on_select = on_select
        self._build(menu_items, user_info, on_logout)

    def _build(self, items, user_info, on_logout):
        # Header
        hdr = tk.Frame(self, bg=C["panel"], pady=16)
        hdr.pack(fill="x")
        canvas = tk.Canvas(hdr, width=52, height=52, bg=C["panel"], highlightthickness=0)
        canvas.pack()
        canvas.create_oval(2, 2, 50, 50, fill=C["accent"], outline="")
        canvas.create_text(26, 26, text=user_info["full_name"][0].upper(),
                           font=(FONT, 22, "bold"), fill=C["white"])

        tk.Label(hdr, text=user_info["full_name"], bg=C["panel"], fg=C["white"],
                 font=(FONT, 11, "bold")).pack(pady=(6, 0))
        role_colors = {"admin": C["warning"], "tenant": C["accent2"]}
        tk.Label(hdr, text=user_info["role"].capitalize(),
                 bg=role_colors.get(user_info["role"], C["accent"]),
                 fg=C["white"], font=(FONT, 8, "bold"),
                 padx=8, pady=2).pack(pady=4)

        separator(self, C["border"]).pack(fill="x", padx=12, pady=8)

        # Menu
        for key, icon, label_text in items:
            btn = tk.Button(self, text=f"  {icon}  {label_text}",
                            command=lambda k=key: self.select(k),
                            bg=C["panel"], fg=C["subtext"],
                            font=(FONT, 10), relief="flat", anchor="w",
                            activebackground=C["card"], activeforeground=C["white"],
                            cursor="hand2", padx=12, pady=10)
            btn.pack(fill="x")
            self.buttons[key] = btn

        # Logout at bottom
        bottom = tk.Frame(self, bg=C["panel"])
        bottom.pack(side="bottom", fill="x", pady=12)
        separator(bottom, C["border"]).pack(fill="x", padx=12, pady=8)
        tk.Button(bottom, text="  🚪  Logout",
                  command=on_logout, bg=C["panel"], fg=C["danger"],
                  font=(FONT, 10), relief="flat", anchor="w",
                  activebackground=C["card"], cursor="hand2",
                  padx=12, pady=10).pack(fill="x")

    def select(self, key):
        if self.active and self.active in self.buttons:
            self.buttons[self.active].config(bg=C["panel"], fg=C["subtext"])
        self.active = key
        if key in self.buttons:
            self.buttons[key].config(bg=C["card"], fg=C["white"])
        self.on_select(key)

def make_tree(parent, columns, headings, widths, height=14):
    style = ttk.Style()
    style.theme_use("clam")
    style.configure("Custom.Treeview",
                    background=C["card"], fieldbackground=C["card"],
                    foreground=C["text"], rowheight=32, borderwidth=0,
                    font=(FONT, 9))
    style.configure("Custom.Treeview.Heading",
                    background=C["panel"], foreground=C["accent"],
                    font=(FONT, 9, "bold"), borderwidth=0, relief="flat")
    style.map("Custom.Treeview",
              background=[("selected", C["accent"])],
              foreground=[("selected", C["white"])])

    frame = tk.Frame(parent, bg=C["bg"])
    tree = ttk.Treeview(frame, columns=columns, show="headings",
                        height=height, style="Custom.Treeview")
    sb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=sb.set)

    for col, hdg, w in zip(columns, headings, widths):
        tree.heading(col, text=hdg)
        tree.column(col, width=w, minwidth=50)

    tree.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")
    return frame, tree

def page_header(parent, title, subtitle=""):
    hdr = tk.Frame(parent, bg=C["bg"], pady=20, padx=24)
    hdr.pack(fill="x")
    tk.Label(hdr, text=title, bg=C["bg"], fg=C["white"],
             font=(FONT, 20, "bold")).pack(anchor="w")
    if subtitle:
        tk.Label(hdr, text=subtitle, bg=C["bg"], fg=C["subtext"],
                 font=(FONT, 10)).pack(anchor="w", pady=(2, 0))
    separator(hdr, C["border"]).pack(fill="x", pady=(12, 0))
    return hdr

# ══════════════════════════════════════════════════════════════════════════════
#  ADMIN DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
class AdminDashboard(tk.Frame):
    def __init__(self, master, user, on_logout):
        super().__init__(master, bg=C["bg"])
        self.user      = user
        self.on_logout = on_logout
        self.pack(fill="both", expand=True)
        self._build()

    def _build(self):
        menu = [
            ("home",       "🏠", "Dashboard"),
            ("tenants",    "👥", "Tenants"),
            ("properties", "🏢", "Properties"),
            ("agreements", "📋", "Agreements"),
            ("payments",   "💳", "Payments"),
            ("idproofs",   "🪪", "ID Proofs"),
        ]
        self.sidebar = Sidebar(self, menu, self._show_page,
                               self.user, self.on_logout)

        self.content = tk.Frame(self, bg=C["bg"])
        self.content.pack(side="left", fill="both", expand=True)

        self.pages = {}
        self.sidebar.select("home")

    def _clear_content(self):
        for w in self.content.winfo_children():
            w.destroy()

    def _show_page(self, key):
        self._clear_content()
        {
            "home":       self._page_home,
            "tenants":    self._page_tenants,
            "properties": self._page_properties,
            "agreements": self._page_agreements,
            "payments":   self._page_payments,
            "idproofs":   self._page_idproofs,
        }.get(key, self._page_home)()

    # ── HOME ──────────────────────────────────────────────────────────────────
    def _page_home(self):
        page_header(self.content, "Admin Dashboard",
                    f"Welcome back, {self.user['full_name']}  •  {datetime.now().strftime('%d %B %Y')}")

        scroll_canvas = tk.Canvas(self.content, bg=C["bg"], highlightthickness=0)
        sb = ttk.Scrollbar(self.content, orient="vertical", command=scroll_canvas.yview)
        scroll_frame = tk.Frame(scroll_canvas, bg=C["bg"])
        scroll_frame.bind("<Configure>",
                          lambda e: scroll_canvas.configure(scrollregion=scroll_canvas.bbox("all")))
        scroll_canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        scroll_canvas.configure(yscrollcommand=sb.set)
        scroll_canvas.pack(side="left", fill="both", expand=True, padx=24)
        sb.pack(side="right", fill="y")

        # Stats
        conn = get_db()
        tenants    = conn.execute("SELECT COUNT(*) FROM users WHERE role='tenant'").fetchone()[0]
        properties = conn.execute("SELECT COUNT(*) FROM properties").fetchone()[0]
        active_ag  = conn.execute("SELECT COUNT(*) FROM agreements WHERE status='active'").fetchone()[0]
        month_rev  = conn.execute(
            "SELECT COALESCE(SUM(amount),0) FROM payments WHERE strftime('%Y-%m',payment_date)=strftime('%Y-%m','now')").fetchone()[0]
        overdue    = conn.execute("SELECT COUNT(*) FROM payments WHERE status='overdue'").fetchone()[0]
        vacant     = conn.execute("SELECT COUNT(*) FROM properties WHERE status='vacant'").fetchone()[0]
        conn.close()

        stats = [
            ("👥 Tenants",           str(tenants),                C["accent"]),
            ("🏢 Properties",        str(properties),             C["accent2"]),
            ("📋 Active Agreements", str(active_ag),              C["success"]),
            ("💰 Month Revenue",     f"₹{month_rev:,.0f}",        C["warning"]),
            ("⚠️ Overdue",           str(overdue),                C["danger"]),
            ("🏠 Vacant Units",      str(vacant),                 C["subtext"]),
        ]
        stat_row = tk.Frame(scroll_frame, bg=C["bg"])
        stat_row.pack(fill="x", pady=(0, 20))
        for i, (lbl, val, col) in enumerate(stats):
            card = tk.Frame(stat_row, bg=C["card"], padx=18, pady=16)
            card.grid(row=0, column=i, padx=6, pady=4, sticky="ew")
            stat_row.columnconfigure(i, weight=1)
            tk.Label(card, text=val, bg=C["card"], fg=col,
                     font=(FONT, 22, "bold")).pack(anchor="w")
            tk.Label(card, text=lbl, bg=C["card"], fg=C["subtext"],
                     font=(FONT, 9)).pack(anchor="w")

        # Recent payments
        tk.Label(scroll_frame, text="Recent Payments", bg=C["bg"], fg=C["white"],
                 font=(FONT, 13, "bold")).pack(anchor="w", pady=(0, 8))
        tf, tree = make_tree(scroll_frame,
                             ("tenant","property","amount","date","status"),
                             ("Tenant", "Property", "Amount", "Date", "Status"),
                             (160, 200, 100, 120, 100), height=8)
        tf.pack(fill="x")
        conn = get_db()
        rows = conn.execute("""
            SELECT u.full_name, pr.name, p.amount, p.payment_date, p.status
            FROM payments p JOIN users u ON u.id=p.tenant_id
            JOIN agreements a ON a.id=p.agreement_id
            JOIN properties pr ON pr.id=a.property_id
            ORDER BY p.id DESC LIMIT 10
        """).fetchall()
        conn.close()
        for r in rows:
            tree.insert("", "end", values=(r[0], r[1], f"₹{r[2]:,.0f}", r[3], r[4].upper()))

    # ── TENANTS ───────────────────────────────────────────────────────────────
    def _page_tenants(self):
        page_header(self.content, "Tenants", "Manage all registered tenants")
        p = tk.Frame(self.content, bg=C["bg"], padx=24)
        p.pack(fill="both", expand=True)

        btn_row = tk.Frame(p, bg=C["bg"])
        btn_row.pack(fill="x", pady=(0, 12))
        styled_btn(btn_row, "+ Add Tenant", self._add_tenant_dialog, width=16).pack(side="left")
        styled_btn(btn_row, "🔄 Refresh", lambda: self._show_page("tenants"), color=C["card"], width=12).pack(side="left", padx=6)

        tf, self.tenant_tree = make_tree(p,
            ("id","name","username","email","phone","created"),
            ("ID","Full Name","Username","Email","Phone","Registered"),
            (40, 160, 120, 180, 120, 120), height=10)
        tf.pack(fill="both", expand=False, pady=(0, 10))
        self._load_tenants()

        btn_row2 = tk.Frame(p, bg=C["bg"])
        btn_row2.pack(fill="x", pady=(8, 18))
        styled_btn(btn_row2, "✏️ Edit", self._edit_tenant, color=C["warning"], width=12).pack(side="left")
        styled_btn(btn_row2, "🗑 Delete", self._delete_tenant, color=C["danger"], width=12).pack(side="left", padx=6)
        styled_btn(btn_row2, "� Payments", self._view_tenant_payments, color=C["accent2"], width=16).pack(side="left", padx=6)
        styled_btn(btn_row2, "�🪪 View ID Proofs", lambda: self._view_tenant_docs(), color=C["accent2"], width=16).pack(side="left", padx=6)

    def _load_tenants(self):
        self.tenant_tree.delete(*self.tenant_tree.get_children())
        conn = get_db()
        rows = conn.execute(
            "SELECT id,full_name,username,email,phone,created_at FROM users WHERE role='tenant' ORDER BY id DESC").fetchall()
        conn.close()
        for r in rows:
            self.tenant_tree.insert("", "end", values=tuple(r))

    def _add_tenant_dialog(self):
        self._tenant_dialog()

    def _edit_tenant(self):
        sel = self.tenant_tree.selection()
        if not sel:
            messagebox.showwarning("Select", "Please select a tenant first.")
            return
        tid = self.tenant_tree.item(sel[0])["values"][0]
        conn = get_db()
        row = conn.execute("SELECT * FROM users WHERE id=?", (tid,)).fetchone()
        conn.close()
        self._tenant_dialog(dict(row))

    def _tenant_dialog(self, data=None):
        dlg = tk.Toplevel(self)
        dlg.title("Add Tenant" if not data else "Edit Tenant")
        dlg.geometry("420x440")
        dlg.configure(bg=C["card"])
        dlg.grab_set()

        tk.Label(dlg, text="Tenant Details", bg=C["card"], fg=C["white"],
                 font=(FONT, 14, "bold")).pack(pady=(20, 10))

        fields = [("Full Name", "full_name"), ("Email", "email"), ("Phone", "phone")]
        entries = {}
        for lbl_txt, key in fields:
            tk.Label(dlg, text=lbl_txt, bg=C["card"], fg=C["subtext"],
                     font=(FONT, 9)).pack(anchor="w", padx=30)
            frm, ent = entry_field(dlg, width=36)
            frm.pack(padx=30, fill="x", pady=(2, 8))
            if data and data.get(key):
                ent.insert(0, data[key])
            entries[key] = ent

        if not data:
            for lbl_txt, key in [("Username", "username"), ("Password", "password")]:
                tk.Label(dlg, text=lbl_txt, bg=C["card"], fg=C["subtext"],
                         font=(FONT, 9)).pack(anchor="w", padx=30)
                frm, ent = entry_field(dlg, show="●" if key == "password" else "", width=36)
                frm.pack(padx=30, fill="x", pady=(2, 8))
                entries[key] = ent

        def save():
            name  = entries["full_name"].get().strip()
            email = entries["email"].get().strip()
            phone = entries["phone"].get().strip()
            if not name:
                messagebox.showerror("Error", "Full name is required.")
                return
            conn = get_db()
            if data:
                conn.execute("UPDATE users SET full_name=?,email=?,phone=? WHERE id=?",
                             (name, email, phone, data["id"]))
            else:
                uname = entries["username"].get().strip()
                pw    = entries["password"].get().strip()
                if not uname or not pw:
                    messagebox.showerror("Error", "Username and password required.")
                    conn.close(); return
                try:
                    conn.execute(
                        "INSERT INTO users (username,password,role,full_name,email,phone) VALUES (?,?,?,?,?,?)",
                        (uname, hash_pw(pw), "tenant", name, email, phone))
                except sqlite3.IntegrityError:
                    messagebox.showerror("Error", "Username already exists.")
                    conn.close(); return
            conn.commit(); conn.close()
            dlg.destroy()
            self._load_tenants()

        styled_btn(dlg, "Save", save, width=20, height=2).pack(pady=16)

    def _delete_tenant(self):
        sel = self.tenant_tree.selection()
        if not sel:
            return
        tid = self.tenant_tree.item(sel[0])["values"][0]
        if messagebox.askyesno("Confirm", "Delete this tenant? This action cannot be undone."):
            conn = get_db()
            conn.execute("DELETE FROM users WHERE id=?", (tid,))
            conn.commit(); conn.close()
            self._load_tenants()

    def _view_tenant_docs(self):
        sel = self.tenant_tree.selection()
        if not sel:
            messagebox.showwarning("Select", "Select a tenant first.")
            return
        tid = self.tenant_tree.item(sel[0])["values"][0]
        self._idproof_dialog(tenant_id=tid)

    def _view_tenant_payments(self):
        sel = self.tenant_tree.selection()
        if not sel:
            messagebox.showwarning("Select", "Select a tenant first.")
            return
        tid = self.tenant_tree.item(sel[0])["values"][0]
        conn = get_db()
        tenant = conn.execute("SELECT full_name FROM users WHERE id=?", (tid,)).fetchone()
        years = [r[0] for r in conn.execute(
            "SELECT DISTINCT strftime('%Y',payment_date) FROM payments WHERE tenant_id=? ORDER BY 1 DESC", (tid,)
        ).fetchall()]
        conn.close()
        if not years:
            messagebox.showinfo("No Payments", "This tenant has no payment records yet.")
            return

        dlg = tk.Toplevel(self)
        dlg.title(f"Payments - {tenant['full_name']}")
        dlg.geometry("780x560")
        dlg.configure(bg=C["bg"])
        dlg.grab_set()

        header = tk.Frame(dlg, bg=C["bg"], padx=20, pady=12)
        header.pack(fill="x")
        tk.Label(header, text=f"Payments for {tenant['full_name']}", bg=C["bg"], fg=C["white"],
                 font=(FONT, 16, "bold")).pack(anchor="w")
        tk.Label(header, text="Review yearly totals and monthly breakdowns for this tenant.",
                 bg=C["bg"], fg=C["subtext"], font=(FONT, 10)).pack(anchor="w", pady=(2, 0))
        separator(header, C["border"]).pack(fill="x", pady=(12, 0))

        control_row = tk.Frame(dlg, bg=C["bg"], pady=10)
        control_row.pack(fill="x", padx=20)

        tk.Label(control_row, text="Year:", bg=C["bg"], fg=C["subtext"],
                 font=(FONT, 9, "bold")).pack(side="left")
        month_options = ["All Months"] + [calendar.month_name[m] for m in range(1, 13)]
        year_var = tk.StringVar(value=years[0])
        month_var = tk.StringVar(value="All Months")

        year_menu = tk.OptionMenu(control_row, year_var, *(["All Years"] + years))
        year_menu.config(bg=C["card"], fg=C["white"], activebackground=C["hover"], relief="flat", highlightthickness=0)
        year_menu["menu"].config(bg=C["card"], fg=C["text"])
        year_menu.pack(side="left", padx=(6, 12))

        tk.Label(control_row, text="Month:", bg=C["bg"], fg=C["subtext"],
                 font=(FONT, 9, "bold")).pack(side="left")
        month_menu = tk.OptionMenu(control_row, month_var, *month_options)
        month_menu.config(bg=C["card"], fg=C["white"], activebackground=C["hover"], relief="flat", highlightthickness=0)
        month_menu["menu"].config(bg=C["card"], fg=C["text"])
        month_menu.pack(side="left", padx=(6, 0))

        summary_row = tk.Frame(dlg, bg=C["bg"])
        summary_row.pack(fill="x", padx=20, pady=(0, 10))

        def make_summary_card(label, value_var, color):
            card = tk.Frame(summary_row, bg=C["card"], padx=18, pady=16)
            card.pack(side="left", fill="x", expand=True, padx=6)
            tk.Label(card, textvariable=value_var, bg=C["card"], fg=color,
                     font=(FONT, 18, "bold")).pack(anchor="w")
            tk.Label(card, text=label, bg=C["card"], fg=C["subtext"],
                     font=(FONT, 9)).pack(anchor="w")

        total_text = tk.StringVar(value="₹0.00")
        selected_month_text = tk.StringVar(value="All Months")
        count_text = tk.StringVar(value="0")
        make_summary_card("Total Paid", total_text, C["warning"])
        make_summary_card("Selected Month", selected_month_text, C["accent"])
        make_summary_card("Records", count_text, C["accent2"])

        table_container = tk.Frame(dlg, bg=C["bg"])
        table_container.pack(fill="both", expand=True, padx=20, pady=(0, 8))

        def rebuild_table(columns, headings, widths, rows):
            for child in table_container.winfo_children():
                child.destroy()
            tf, tree = make_tree(table_container, columns, headings, widths, height=10)
            tf.pack(fill="both", expand=True)
            for row in rows:
                tree.insert("", "end", values=row)

        def refresh(*_):
            year_value = year_var.get()
            month_value = month_var.get()
            conn = get_db()
            if year_value == "All Years":
                conn_rows = conn.execute(
                    "SELECT strftime('%Y',payment_date) AS period, COALESCE(SUM(amount),0) FROM payments "
                    "WHERE tenant_id=? GROUP BY period ORDER BY period DESC",
                    (tid,)
                ).fetchall()
                data = [(r[0], f"₹{r[1]:,.2f}") for r in conn_rows]
                total = sum(r[1] for r in conn_rows)
                total_text.set(f"₹{total:,.2f}")
                selected_month_text.set("All Years")
                count_text.set(str(len(conn_rows)))
                month_menu.config(state="disabled")
                rebuild_table(("period", "amount"), ("Year", "Total Paid"), (180, 140), data)
            else:
                month_menu.config(state="normal")
                if month_value == "All Months":
                    conn_rows = conn.execute(
                        "SELECT strftime('%m',payment_date) AS period, COALESCE(SUM(amount),0) FROM payments "
                        "WHERE tenant_id=? AND strftime('%Y',payment_date)=? GROUP BY period ORDER BY period",
                        (tid, year_value)
                    ).fetchall()
                    data = [(calendar.month_name[int(r[0])], f"₹{r[1]:,.2f}") for r in conn_rows]
                    total = sum(r[1] for r in conn_rows)
                    total_text.set(f"₹{total:,.2f}")
                    selected_month_text.set("All Months")
                    count_text.set(str(len(conn_rows)))
                    rebuild_table(("period", "amount"), ("Month", "Total Paid"), (180, 140), data)
                else:
                    month_number = f"{month_options.index(month_value):02d}"
                    conn_rows = conn.execute(
                        "SELECT payment_date, amount, method, status FROM payments "
                        "WHERE tenant_id=? AND strftime('%Y',payment_date)=? AND strftime('%m',payment_date)=? "
                        "ORDER BY payment_date",
                        (tid, year_value, month_number)
                    ).fetchall()
                    data = [(r[0], f"₹{r[1]:,.2f}", r[2].upper(), r[3].upper()) for r in conn_rows]
                    total = sum(r[1] for r in conn_rows)
                    total_text.set(f"₹{total:,.2f}")
                    selected_month_text.set(month_value)
                    count_text.set(str(len(conn_rows)))
                    rebuild_table(("date", "amount", "method", "status"),
                                  ("Date", "Amount", "Method", "Status"),
                                  (130, 110, 150, 120), data)
            conn.close()

        def update_month_state(*_):
            if year_var.get() == "All Years":
                month_var.set("All Months")
                month_menu.config(state="disabled")
            else:
                month_menu.config(state="normal")
            refresh()

        year_var.trace_add("write", update_month_state)
        month_var.trace_add("write", refresh)
        update_month_state()

        footer = tk.Frame(dlg, bg=C["bg"], pady=12)
        footer.pack(fill="x", padx=20)
        styled_btn(footer, "✖ Close", dlg.destroy, color=C["danger"], width=12).pack(side="right")

    # ── PROPERTIES ────────────────────────────────────────────────────────────
    def _page_properties(self):
        page_header(self.content, "Properties", "Manage rental properties")
        p = tk.Frame(self.content, bg=C["bg"], padx=24)
        p.pack(fill="both", expand=True)

        br = tk.Frame(p, bg=C["bg"])
        br.pack(fill="x", pady=(0, 12))
        styled_btn(br, "+ Add Property", self._add_property, width=16).pack(side="left")
        styled_btn(br, "🔄 Refresh", lambda: self._show_page("properties"), color=C["card"], width=12).pack(side="left", padx=6)

        tf, self.prop_tree = make_tree(p,
            ("id","name","address","unit","city","rent","status"),
            ("ID","Name","Address","Unit","City","Rent/Mo","Status"),
            (40,180,200,60,100,90,90), height=10)
        tf.pack(fill="both", expand=False, pady=(0, 10))
        self._load_properties()

        br2 = tk.Frame(p, bg=C["bg"])
        br2.pack(fill="x", pady=(8, 18))
        styled_btn(br2, "✏️ Edit", self._edit_property, color=C["warning"], width=12).pack(side="left")
        styled_btn(br2, "🗑 Delete", self._delete_property, color=C["danger"], width=12).pack(side="left", padx=6)

    def _load_properties(self):
        self.prop_tree.delete(*self.prop_tree.get_children())
        conn = get_db()
        rows = conn.execute(
            "SELECT id,name,address,unit_number,city,monthly_rent,status FROM properties ORDER BY id DESC").fetchall()
        conn.close()
        for r in rows:
            self.prop_tree.insert("", "end",
                values=(r[0], r[1], r[2], r[3] or "", r[4] or "", f"₹{r[5]:,.0f}", r[6].upper()))

    def _add_property(self):
        self._property_dialog()

    def _edit_property(self):
        sel = self.prop_tree.selection()
        if not sel:
            messagebox.showwarning("Select", "Select a property first.")
            return
        pid = self.prop_tree.item(sel[0])["values"][0]
        conn = get_db()
        row = conn.execute("SELECT * FROM properties WHERE id=?", (pid,)).fetchone()
        conn.close()
        self._property_dialog(dict(row))

    def _property_dialog(self, data=None):
        dlg = tk.Toplevel(self)
        dlg.title("Add Property" if not data else "Edit Property")
        dlg.geometry("460x520")
        dlg.configure(bg=C["card"])
        dlg.grab_set()

        tk.Label(dlg, text="Property Details", bg=C["card"], fg=C["white"],
                 font=(FONT, 14, "bold")).pack(pady=(20, 10))

        fields = [("Property Name", "name"), ("Address", "address"),
                  ("Unit Number", "unit_number"), ("City", "city"),
                  ("Monthly Rent (₹)", "monthly_rent")]
        entries = {}
        for lbl_txt, key in fields:
            tk.Label(dlg, text=lbl_txt, bg=C["card"], fg=C["subtext"],
                     font=(FONT, 9)).pack(anchor="w", padx=30)
            frm, ent = entry_field(dlg, width=36)
            frm.pack(padx=30, fill="x", pady=(2, 8))
            if data and data.get(key):
                ent.insert(0, str(data[key]))
            entries[key] = ent

        tk.Label(dlg, text="Status", bg=C["card"], fg=C["subtext"],
                 font=(FONT, 9)).pack(anchor="w", padx=30)
        status_var = tk.StringVar(value=data["status"] if data else "vacant")
        sf = tk.Frame(dlg, bg=C["card"])
        sf.pack(fill="x", padx=30, pady=(2, 16))
        for s in ["vacant", "occupied", "maintenance"]:
            tk.Radiobutton(sf, text=s.capitalize(), variable=status_var, value=s,
                           bg=C["card"], fg=C["text"], activebackground=C["card"],
                           selectcolor=C["entry_bg"], font=(FONT, 10),
                           cursor="hand2").pack(side="left", padx=10)

        def save():
            name = entries["name"].get().strip()
            addr = entries["address"].get().strip()
            rent_str = entries["monthly_rent"].get().strip()
            if not name or not addr or not rent_str:
                messagebox.showerror("Error", "Name, address and rent are required.")
                return
            try:
                rent = float(rent_str.replace(",", ""))
            except ValueError:
                messagebox.showerror("Error", "Rent must be a number.")
                return
            conn = get_db()
            if data:
                conn.execute(
                    "UPDATE properties SET name=?,address=?,unit_number=?,city=?,monthly_rent=?,status=? WHERE id=?",
                    (name, addr, entries["unit_number"].get(), entries["city"].get(),
                     rent, status_var.get(), data["id"]))
            else:
                conn.execute(
                    "INSERT INTO properties (name,address,unit_number,city,monthly_rent,status) VALUES (?,?,?,?,?,?)",
                    (name, addr, entries["unit_number"].get(), entries["city"].get(),
                     rent, status_var.get()))
            conn.commit(); conn.close()
            dlg.destroy()
            self._load_properties()

        styled_btn(dlg, "Save", save, width=20, height=2).pack(pady=10)

    def _delete_property(self):
        sel = self.prop_tree.selection()
        if not sel:
            return
        pid = self.prop_tree.item(sel[0])["values"][0]
        if messagebox.askyesno("Confirm", "Delete this property?"):
            conn = get_db()
            conn.execute("DELETE FROM properties WHERE id=?", (pid,))
            conn.commit(); conn.close()
            self._load_properties()

    # ── AGREEMENTS ────────────────────────────────────────────────────────────
    def _page_agreements(self):
        page_header(self.content, "Rental Agreements", "Create and track rental agreements")
        p = tk.Frame(self.content, bg=C["bg"], padx=24)
        p.pack(fill="both", expand=True)

        br = tk.Frame(p, bg=C["bg"])
        br.pack(fill="x", pady=(0, 12))
        styled_btn(br, "+ New Agreement", self._add_agreement, width=18).pack(side="left")
        styled_btn(br, "🔄 Refresh", lambda: self._show_page("agreements"), color=C["card"], width=12).pack(side="left", padx=6)

        tf, self.ag_tree = make_tree(p,
            ("id","tenant","property","start","end","rent","deposit","status"),
            ("ID","Tenant","Property","Start","End","Rent","Deposit","Status"),
            (40,150,180,100,100,90,90,90), height=10)
        tf.pack(fill="both", expand=False, pady=(0, 10))
        self._load_agreements()

        br2 = tk.Frame(p, bg=C["bg"])
        br2.pack(fill="x", pady=(8, 18))
        styled_btn(br2, "✏️ Edit Status", self._edit_agreement_status, color=C["warning"], width=16).pack(side="left")
        styled_btn(br2, "🗑 Delete", self._delete_agreement, color=C["danger"], width=12).pack(side="left", padx=6)

    def _load_agreements(self):
        self.ag_tree.delete(*self.ag_tree.get_children())
        conn = get_db()
        rows = conn.execute("""
            SELECT a.id, u.full_name, pr.name, a.start_date, a.end_date,
                   a.monthly_rent, a.security_deposit, a.status
            FROM agreements a
            JOIN users u ON u.id=a.tenant_id
            JOIN properties pr ON pr.id=a.property_id
            ORDER BY a.id DESC
        """).fetchall()
        conn.close()
        for r in rows:
            self.ag_tree.insert("", "end",
                values=(r[0], r[1], r[2], r[3], r[4],
                        f"₹{r[5]:,.0f}", f"₹{r[6]:,.0f}", r[7].upper()))

    def _add_agreement(self):
        dlg = tk.Toplevel(self)
        dlg.title("New Rental Agreement")
        dlg.geometry("500x580")
        dlg.configure(bg=C["card"])
        dlg.grab_set()

        tk.Label(dlg, text="Rental Agreement", bg=C["card"], fg=C["white"],
                 font=(FONT, 14, "bold")).pack(pady=(20, 10))

        conn = get_db()
        tenants = conn.execute(
            "SELECT id, full_name FROM users WHERE role='tenant'").fetchall()
        props   = conn.execute(
            "SELECT id, name FROM properties WHERE status='vacant'").fetchall()
        conn.close()

        if not tenants:
            messagebox.showwarning("No Tenants", "Add tenants first.")
            dlg.destroy(); return
        if not props:
            messagebox.showwarning("No Properties", "No vacant properties available.")
            dlg.destroy(); return

        tenant_map   = {f"{t[1]} (ID:{t[0]})": t[0] for t in tenants}
        property_map = {f"{p[1]} (ID:{p[0]})": p[0] for p in props}

        fields_combo = [("Tenant", list(tenant_map)), ("Property", list(property_map))]
        combos = {}
        for lbl_txt, opts in fields_combo:
            tk.Label(dlg, text=lbl_txt, bg=C["card"], fg=C["subtext"],
                     font=(FONT, 9)).pack(anchor="w", padx=30)
            var = tk.StringVar(value=opts[0])
            cb = ttk.Combobox(dlg, textvariable=var, values=opts, state="readonly",
                              font=(FONT, 10), width=40)
            cb.pack(padx=30, fill="x", pady=(2, 8))
            combos[lbl_txt] = var

        fields_entry = [("Start Date (YYYY-MM-DD)", ""), ("End Date (YYYY-MM-DD)", ""),
                        ("Monthly Rent (₹)", ""), ("Security Deposit (₹)", "0")]
        entries = {}
        for lbl_txt, default in fields_entry:
            tk.Label(dlg, text=lbl_txt, bg=C["card"], fg=C["subtext"],
                     font=(FONT, 9)).pack(anchor="w", padx=30)
            frm, ent = entry_field(dlg, width=36)
            frm.pack(padx=30, fill="x", pady=(2, 8))
            if default:
                ent.insert(0, default)
            entries[lbl_txt] = ent

        # Pre-fill today / one year later
        entries["Start Date (YYYY-MM-DD)"].insert(0, date.today().strftime("%Y-%m-%d"))
        entries["End Date (YYYY-MM-DD)"].insert(
            0, (date.today() + timedelta(days=365)).strftime("%Y-%m-%d"))

        tk.Label(dlg, text="Terms & Conditions", bg=C["card"], fg=C["subtext"],
                 font=(FONT, 9)).pack(anchor="w", padx=30)
        terms_text = tk.Text(dlg, bg=C["entry_bg"], fg=C["text"], font=(FONT, 9),
                             height=4, bd=0, padx=6, pady=6, width=40)
        terms_text.pack(padx=30, fill="x", pady=(2, 10))

        def save():
            tid  = tenant_map[combos["Tenant"].get()]
            pid  = property_map[combos["Property"].get()]
            sd   = entries["Start Date (YYYY-MM-DD)"].get().strip()
            ed   = entries["End Date (YYYY-MM-DD)"].get().strip()
            rent_s = entries["Monthly Rent (₹)"].get().strip().replace(",", "")
            dep_s  = entries["Security Deposit (₹)"].get().strip().replace(",", "")
            terms  = terms_text.get("1.0", "end").strip()
            if not all([sd, ed, rent_s]):
                messagebox.showerror("Error", "All date and rent fields are required.")
                return
            try:
                rent = float(rent_s)
                dep  = float(dep_s) if dep_s else 0
            except ValueError:
                messagebox.showerror("Error", "Rent/Deposit must be numbers.")
                return
            conn = get_db()
            conn.execute(
                "INSERT INTO agreements (tenant_id,property_id,start_date,end_date,monthly_rent,security_deposit,terms) VALUES (?,?,?,?,?,?,?)",
                (tid, pid, sd, ed, rent, dep, terms))
            conn.execute("UPDATE properties SET status='occupied' WHERE id=?", (pid,))
            conn.commit(); conn.close()
            dlg.destroy()
            self._load_agreements()

        styled_btn(dlg, "Create Agreement", save, width=24, height=2).pack(pady=12)

    def _edit_agreement_status(self):
        sel = self.ag_tree.selection()
        if not sel:
            return
        aid = self.ag_tree.item(sel[0])["values"][0]
        dlg = tk.Toplevel(self)
        dlg.title("Update Agreement Status")
        dlg.geometry("340x220")
        dlg.configure(bg=C["card"])
        dlg.grab_set()
        tk.Label(dlg, text="Update Status", bg=C["card"], fg=C["white"],
                 font=(FONT, 14, "bold")).pack(pady=20)
        sv = tk.StringVar(value="active")
        for s in ["active", "expired", "terminated"]:
            tk.Radiobutton(dlg, text=s.capitalize(), variable=sv, value=s,
                           bg=C["card"], fg=C["text"], selectcolor=C["entry_bg"],
                           font=(FONT, 11), cursor="hand2").pack(pady=4)
        def save():
            conn = get_db()
            conn.execute("UPDATE agreements SET status=? WHERE id=?", (sv.get(), aid))
            if sv.get() in ("expired","terminated"):
                ag = conn.execute("SELECT property_id FROM agreements WHERE id=?", (aid,)).fetchone()
                if ag:
                    conn.execute("UPDATE properties SET status='vacant' WHERE id=?", (ag[0],))
            conn.commit(); conn.close()
            dlg.destroy()
            self._load_agreements()
        styled_btn(dlg, "Update", save, width=16, height=2).pack(pady=14)

    def _delete_agreement(self):
        sel = self.ag_tree.selection()
        if not sel:
            return
        aid = self.ag_tree.item(sel[0])["values"][0]
        if messagebox.askyesno("Confirm", "Delete this agreement?"):
            conn = get_db()
            conn.execute("DELETE FROM agreements WHERE id=?", (aid,))
            conn.commit(); conn.close()
            self._load_agreements()

    # ── PAYMENTS ──────────────────────────────────────────────────────────────
    def _page_payments(self):
        page_header(self.content, "Payments", "Record and track rent payments")
        p = tk.Frame(self.content, bg=C["bg"], padx=24)
        p.pack(fill="both", expand=True)

        br = tk.Frame(p, bg=C["bg"])
        br.pack(fill="x", pady=(0, 12))
        styled_btn(br, "+ Record Payment", self._add_payment, width=18).pack(side="left")
        styled_btn(br, "👁️ View Receipt", self._view_receipt, color=C["accent2"], width=16).pack(side="left", padx=6)
        styled_btn(br, "🔄 Refresh", lambda: self._show_page("payments"), color=C["card"], width=12).pack(side="left", padx=6)

        tf, self.pay_tree = make_tree(p,
            ("id","tenant","amount","date","method","status","receipt"),
            ("ID","Tenant","Amount","Date","Method","Status","Receipt No."),
            (40,160,100,110,100,90,150))
        tf.pack(fill="both", expand=True)
        self._load_payments()

    def _load_payments(self):
        self.pay_tree.delete(*self.pay_tree.get_children())
        conn = get_db()
        rows = conn.execute("""
            SELECT p.id, u.full_name, p.amount, p.payment_date,
                   p.method, p.status, p.receipt_number
            FROM payments p JOIN users u ON u.id=p.tenant_id
            ORDER BY p.id DESC
        """).fetchall()
        conn.close()
        for r in rows:
            self.pay_tree.insert("", "end",
                values=(r[0], r[1], f"₹{r[2]:,.0f}", r[3], r[4].upper(),
                        r[5].upper(), r[6] or ""))

    def _add_payment(self):
        dlg = tk.Toplevel(self)
        dlg.title("Record Payment")
        dlg.geometry("460x480")
        dlg.configure(bg=C["card"])
        dlg.grab_set()

        tk.Label(dlg, text="Record Rent Payment", bg=C["card"], fg=C["white"],
                 font=(FONT, 14, "bold")).pack(pady=(20, 10))

        conn = get_db()
        ags = conn.execute("""
            SELECT a.id, u.full_name, pr.name, a.monthly_rent, a.tenant_id
            FROM agreements a
            JOIN users u ON u.id=a.tenant_id
            JOIN properties pr ON pr.id=a.property_id
            WHERE a.status='active'
        """).fetchall()
        conn.close()

        if not ags:
            messagebox.showwarning("No Agreements", "No active agreements found.")
            dlg.destroy(); return

        ag_map = {f"{r[1]} – {r[2]} (₹{r[3]:,.0f}/mo)": (r[0], r[4], r[3]) for r in ags}

        tk.Label(dlg, text="Agreement", bg=C["card"], fg=C["subtext"],
                 font=(FONT, 9)).pack(anchor="w", padx=30)
        ag_var = tk.StringVar(value=list(ag_map.keys())[0])
        cb = ttk.Combobox(dlg, textvariable=ag_var, values=list(ag_map.keys()),
                          state="readonly", font=(FONT, 10), width=44)
        cb.pack(padx=30, fill="x", pady=(2, 8))

        fields = [("Amount (₹)", ""), ("Payment Date (YYYY-MM-DD)", ""),
                  ("Due Date (YYYY-MM-DD)", "")]
        entries = {}
        for lbl_txt, default in fields:
            tk.Label(dlg, text=lbl_txt, bg=C["card"], fg=C["subtext"],
                     font=(FONT, 9)).pack(anchor="w", padx=30)
            frm, ent = entry_field(dlg, width=36)
            frm.pack(padx=30, fill="x", pady=(2, 8))
            entries[lbl_txt] = ent

        entries["Payment Date (YYYY-MM-DD)"].insert(0, date.today().strftime("%Y-%m-%d"))

        def fill_rent(*a):
            info = ag_map.get(ag_var.get())
            if info:
                entries["Amount (₹)"].delete(0, "end")
                entries["Amount (₹)"].insert(0, str(info[2]))
        cb.bind("<<ComboboxSelected>>", fill_rent)
        fill_rent()

        tk.Label(dlg, text="Payment Method", bg=C["card"], fg=C["subtext"],
                 font=(FONT, 9)).pack(anchor="w", padx=30)
        method_var = tk.StringVar(value="cash")
        mf = tk.Frame(dlg, bg=C["card"])
        mf.pack(fill="x", padx=30, pady=(2, 8))
        for m in ["cash", "UPI", "bank transfer", "cheque"]:
            tk.Radiobutton(mf, text=m.upper(), variable=method_var, value=m,
                           bg=C["card"], fg=C["text"], selectcolor=C["entry_bg"],
                           font=(FONT, 9), cursor="hand2").pack(side="left", padx=6)

        tk.Label(dlg, text="Notes", bg=C["card"], fg=C["subtext"],
                 font=(FONT, 9)).pack(anchor="w", padx=30)
        frm_n, notes_e = entry_field(dlg, width=36)
        frm_n.pack(padx=30, fill="x", pady=(2, 12))

        def save():
            key = ag_var.get()
            ag_id, tenant_id, _ = ag_map[key]
            amt_s = entries["Amount (₹)"].get().strip().replace(",", "")
            pd_s  = entries["Payment Date (YYYY-MM-DD)"].get().strip()
            dd_s  = entries["Due Date (YYYY-MM-DD)"].get().strip() or None
            notes = notes_e.get().strip()
            if not amt_s or not pd_s:
                messagebox.showerror("Error", "Amount and payment date are required.")
                return
            try:
                amt = float(amt_s)
            except ValueError:
                messagebox.showerror("Error", "Amount must be a number.")
                return
            rcpt = gen_receipt_no()
            conn = get_db()
            cur = conn.execute(
                "INSERT INTO payments (agreement_id,tenant_id,amount,payment_date,due_date,method,status,notes,receipt_number) VALUES (?,?,?,?,?,?,?,?,?)",
                (ag_id, tenant_id, amt, pd_s, dd_s, method_var.get(), "paid", notes, rcpt))
            pid = cur.lastrowid
            conn.commit(); conn.close()
            dlg.destroy()
            self._load_payments()

            if messagebox.askyesno("Receipt", "Payment recorded. Generate PDF receipt?"):
                fp = generate_receipt(pid)
                if fp:
                    messagebox.showinfo("Receipt", f"Receipt saved:\n{fp}")
                    os.startfile(fp) if os.name == "nt" else os.system(f"xdg-open '{fp}'")

        styled_btn(dlg, "Record Payment", save, width=24, height=2).pack(pady=10)

    def _print_receipt(self):
        sel = self.pay_tree.selection()
        if not sel:
            messagebox.showwarning("Select", "Select a payment first.")
            return
        pid = self.pay_tree.item(sel[0])["values"][0]
        fp = generate_receipt(pid)
        if fp:
            messagebox.showinfo("Receipt", f"Receipt saved:\n{fp}")
            try:
                if os.name == "nt":
                    os.startfile(fp)
                else:
                    os.system(f"xdg-open '{fp}' &")
            except Exception:
                pass

    def _view_receipt(self):
        sel = self.pay_tree.selection()
        if not sel:
            messagebox.showwarning("Select", "Select a payment first.")
            return
        pid = self.pay_tree.item(sel[0])["values"][0]
        conn = get_db()
        row = conn.execute("""
            SELECT p.*, u.full_name as tenant_name, u.phone as tenant_phone,
                   pr.name as property_name, pr.address as property_address,
                   pr.unit_number
            FROM payments p
            JOIN users u ON u.id = p.tenant_id
            JOIN agreements a ON a.id = p.agreement_id
            JOIN properties pr ON pr.id = a.property_id
            WHERE p.id = ?
        """, (pid,)).fetchone()
        conn.close()

        if not row:
            messagebox.showerror("Error", "Receipt not found.")
            return

        dlg = tk.Toplevel(self)
        dlg.title(f"Receipt - {row['receipt_number']}")
        dlg.geometry("500x350")
        dlg.configure(bg=C["bg"])
        dlg.grab_set()

        header = tk.Frame(dlg, bg=C["panel"], padx=20, pady=10)
        header.pack(fill="x")
        tk.Label(header, text="Receipt Information", bg=C["panel"], fg=C["accent"],
                 font=(FONT, 14, "bold")).pack(anchor="w")

        content = tk.Frame(dlg, bg=C["card"], padx=20, pady=10)
        content.pack(fill="both", expand=True)

        def make_row(parent, label_text, value_text):
            row_frame = tk.Frame(parent, bg=C["card"])
            row_frame.pack(fill="x", pady=2)
            tk.Label(row_frame, text=label_text, bg=C["card"], fg=C["subtext"],
                     font=(FONT, 9), width=16, anchor="w").pack(side="left")
            tk.Label(row_frame, text=value_text, bg=C["card"], fg=C["white"],
                     font=(FONT, 9, "bold"), anchor="w").pack(side="left")

        section = tk.Frame(content, bg=C["card"])
        section.pack(fill="x", pady=(0, 8))
        tk.Label(section, text="Tenant Details", bg=C["card"], fg=C["accent"],
                 font=(FONT, 11, "bold")).pack(anchor="w", pady=(0, 4))
        make_row(section, "Tenant Name", row['tenant_name'])
        make_row(section, "Phone", row['tenant_phone'])
        make_row(section, "Property", row['property_name'])
        make_row(section, "Address", f"{row['property_address']} | Unit: {row['unit_number'] or 'N/A'}")

        pay_section = tk.Frame(content, bg=C["card"])
        pay_section.pack(fill="x", pady=(0, 8))
        tk.Label(pay_section, text="Payment Details", bg=C["card"], fg=C["accent"],
                 font=(FONT, 11, "bold")).pack(anchor="w", pady=(0, 4))

        amount_box = tk.Frame(pay_section, bg=C["success"], padx=12, pady=8)
        amount_box.pack(fill="x", pady=(0, 6))
        tk.Label(amount_box, text="Amount Paid", bg=C["success"], fg=C["white"],
                 font=(FONT, 9)).pack(anchor="w")
        tk.Label(amount_box, text=f"₹{row['amount']:,.2f}", bg=C["success"], fg=C["white"],
                 font=(FONT, 18, "bold")).pack(anchor="w", pady=(2, 0))

        make_row(pay_section, "Payment Date", row['payment_date'])
        make_row(pay_section, "Method", row['method'].upper())
        make_row(pay_section, "Status", row['status'].upper())
        make_row(pay_section, "Due Date", row['due_date'] or 'N/A')

        footer = tk.Frame(dlg, bg=C["bg"], pady=6)
        footer.pack(fill="x", padx=20, pady=(6, 6))

        def save_pdf():
            fp = generate_receipt(pid)
            if fp:
                messagebox.showinfo("Receipt", f"Receipt saved:\n{fp}")

        styled_btn(footer, "💾 Save as PDF", save_pdf, color=C["success"], width=18).pack(side="left")
        styled_btn(footer, "✖ Close", dlg.destroy, color=C["danger"], width=12).pack(side="left", padx=8)

    # ── ID PROOFS ─────────────────────────────────────────────────────────────
    def _page_idproofs(self):
        page_header(self.content, "ID Proofs", "Manage tenant identity documents")
        p = tk.Frame(self.content, bg=C["bg"], padx=24)
        p.pack(fill="both", expand=True)

        br = tk.Frame(p, bg=C["bg"])
        br.pack(fill="x", pady=(0, 12))
        styled_btn(br, "+ Add ID Proof", self._idproof_dialog, width=16).pack(side="left")
        styled_btn(br, "✅ Verify", self._verify_idproof, color=C["success"], width=12).pack(side="left", padx=6)
        styled_btn(br, "🔄 Refresh", lambda: self._show_page("idproofs"), color=C["card"], width=12).pack(side="left", padx=6)

        tf, self.idp_tree = make_tree(p,
            ("id","tenant","type","number","verified","uploaded"),
            ("ID","Tenant","Doc Type","Doc Number","Verified","Uploaded"),
            (40,180,150,160,90,150))
        tf.pack(fill="both", expand=True)
        self._load_idproofs()

    def _load_idproofs(self, tenant_id=None):
        self.idp_tree.delete(*self.idp_tree.get_children())
        conn = get_db()
        q = """SELECT ip.id, u.full_name, ip.doc_type, ip.doc_number,
                      ip.verified, ip.uploaded_at
               FROM id_proofs ip JOIN users u ON u.id=ip.tenant_id"""
        params = ()
        if tenant_id:
            q += " WHERE ip.tenant_id=?"
            params = (tenant_id,)
        q += " ORDER BY ip.id DESC"
        rows = conn.execute(q, params).fetchall()
        conn.close()
        for r in rows:
            v = "✅ Yes" if r[4] else "❌ No"
            self.idp_tree.insert("", "end", values=(r[0], r[1], r[2], r[3], v, r[5]))

    def _idproof_dialog(self, tenant_id=None):
        dlg = tk.Toplevel(self)
        dlg.title("Add ID Proof")
        dlg.geometry("440x380")
        dlg.configure(bg=C["card"])
        dlg.grab_set()

        tk.Label(dlg, text="Add ID Proof", bg=C["card"], fg=C["white"],
                 font=(FONT, 14, "bold")).pack(pady=(20, 10))

        conn = get_db()
        tenants = conn.execute(
            "SELECT id, full_name FROM users WHERE role='tenant'").fetchall()
        conn.close()

        tenant_map = {f"{t[1]} (ID:{t[0]})": t[0] for t in tenants}
        tk.Label(dlg, text="Tenant", bg=C["card"], fg=C["subtext"],
                 font=(FONT, 9)).pack(anchor="w", padx=30)
        t_var = tk.StringVar()
        if tenant_id:
            # Pre-select
            for k, v in tenant_map.items():
                if v == tenant_id:
                    t_var.set(k)
                    break
        else:
            t_var.set(list(tenant_map.keys())[0] if tenant_map else "")
        tcb = ttk.Combobox(dlg, textvariable=t_var, values=list(tenant_map.keys()),
                           state="readonly", font=(FONT, 10), width=40)
        tcb.pack(padx=30, fill="x", pady=(2, 8))

        tk.Label(dlg, text="Document Type", bg=C["card"], fg=C["subtext"],
                 font=(FONT, 9)).pack(anchor="w", padx=30)
        dtype_var = tk.StringVar(value="Aadhaar Card")
        dtypes = ["Aadhaar Card", "PAN Card", "Passport", "Voter ID", "Driving Licence", "Other"]
        ttk.Combobox(dlg, textvariable=dtype_var, values=dtypes,
                     state="readonly", font=(FONT, 10), width=40).pack(
                     padx=30, fill="x", pady=(2, 8))

        tk.Label(dlg, text="Document Number", bg=C["card"], fg=C["subtext"],
                 font=(FONT, 9)).pack(anchor="w", padx=30)
        _, num_e = entry_field(dlg, width=36)
        num_e.master.pack(padx=30, fill="x", pady=(2, 8))

        file_path_var = tk.StringVar(value="")
        def browse():
            fp = filedialog.askopenfilename(
                filetypes=[("Image/PDF", "*.jpg *.jpeg *.png *.pdf"), ("All", "*.*")])
            if fp:
                file_path_var.set(fp)
                file_lbl.config(text=os.path.basename(fp))

        file_row = tk.Frame(dlg, bg=C["card"])
        file_row.pack(fill="x", padx=30, pady=(4, 8))
        styled_btn(file_row, "📎 Attach File", browse, width=16, color=C["accent2"]).pack(side="left")
        file_lbl = tk.Label(file_row, text="No file selected", bg=C["card"],
                            fg=C["subtext"], font=(FONT, 9))
        file_lbl.pack(side="left", padx=10)

        def save():
            t_sel = t_var.get()
            if not t_sel or t_sel not in tenant_map:
                messagebox.showerror("Error", "Select a tenant.")
                return
            tid  = tenant_map[t_sel]
            dnum = num_e.get().strip()
            if not dnum:
                messagebox.showerror("Error", "Document number is required.")
                return
            dst = None
            if file_path_var.get():
                ext = os.path.splitext(file_path_var.get())[1]
                fn  = f"tenant_{tid}_{datetime.now().strftime('%Y%m%d%H%M%S')}{ext}"
                dst = os.path.join(DOCS_DIR, fn)
                shutil.copy2(file_path_var.get(), dst)
            conn = get_db()
            conn.execute(
                "INSERT INTO id_proofs (tenant_id,doc_type,doc_number,file_path) VALUES (?,?,?,?)",
                (tid, dtype_var.get(), dnum, dst))
            conn.commit(); conn.close()
            dlg.destroy()
            self._load_idproofs()

        styled_btn(dlg, "Save", save, width=20, height=2).pack(pady=10)

    def _verify_idproof(self):
        sel = self.idp_tree.selection()
        if not sel:
            return
        iid = self.idp_tree.item(sel[0])["values"][0]
        conn = get_db()
        conn.execute("UPDATE id_proofs SET verified=1 WHERE id=?", (iid,))
        conn.commit(); conn.close()
        self._load_idproofs()


# ══════════════════════════════════════════════════════════════════════════════
#  TENANT DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
class TenantDashboard(tk.Frame):
    def __init__(self, master, user, on_logout):
        super().__init__(master, bg=C["bg"])
        self.user      = user
        self.on_logout = on_logout
        self.pack(fill="both", expand=True)
        self._build()

    def _build(self):
        menu = [
            ("home",      "🏠", "My Dashboard"),
            ("agreement", "📋", "My Agreement"),
            ("payments",  "💳", "My Payments"),
            ("idproofs",  "🪪", "My ID Proofs"),
            ("profile",   "👤", "My Profile"),
        ]
        self.sidebar = Sidebar(self, menu, self._show_page,
                               self.user, self.on_logout)
        self.content = tk.Frame(self, bg=C["bg"])
        self.content.pack(side="left", fill="both", expand=True)
        self.sidebar.select("home")

    def _clear_content(self):
        for w in self.content.winfo_children():
            w.destroy()

    def _show_page(self, key):
        self._clear_content()
        {
            "home":      self._page_home,
            "agreement": self._page_agreement,
            "payments":  self._page_payments,
            "idproofs":  self._page_idproofs,
            "profile":   self._page_profile,
        }.get(key, self._page_home)()

    def _page_home(self):
        page_header(self.content, f"Hello, {self.user['full_name'].split()[0]}! 👋",
                    f"Tenant Portal  •  {datetime.now().strftime('%d %B %Y')}")

        scroll_canvas = tk.Canvas(self.content, bg=C["bg"], highlightthickness=0)
        sb = ttk.Scrollbar(self.content, orient="vertical", command=scroll_canvas.yview)
        scroll_frame  = tk.Frame(scroll_canvas, bg=C["bg"])
        scroll_frame.bind("<Configure>",
                          lambda e: scroll_canvas.configure(scrollregion=scroll_canvas.bbox("all")))
        scroll_canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        scroll_canvas.configure(yscrollcommand=sb.set)
        scroll_canvas.pack(side="left", fill="both", expand=True, padx=24)
        sb.pack(side="right", fill="y")

        conn = get_db()
        ag = conn.execute("""
            SELECT a.*, pr.name as prop_name, pr.address, pr.unit_number
            FROM agreements a JOIN properties pr ON pr.id=a.property_id
            WHERE a.tenant_id=? AND a.status='active'
        """, (self.user["id"],)).fetchone()

        total_paid = conn.execute(
            "SELECT COALESCE(SUM(amount),0) FROM payments WHERE tenant_id=? AND status='paid'",
            (self.user["id"],)).fetchone()[0]
        pay_count = conn.execute(
            "SELECT COUNT(*) FROM payments WHERE tenant_id=?",
            (self.user["id"],)).fetchone()[0]
        overdue = conn.execute(
            "SELECT COUNT(*) FROM payments WHERE tenant_id=? AND status='overdue'",
            (self.user["id"],)).fetchone()[0]
        conn.close()

        # Stats
        stats_data = [
            ("📋 Agreement", "Active" if ag else "None", C["success"] if ag else C["danger"]),
            ("💰 Total Paid", f"₹{total_paid:,.0f}", C["accent"]),
            ("🧾 Payments", str(pay_count), C["accent2"]),
            ("⚠️ Overdue", str(overdue), C["danger"] if overdue else C["success"]),
        ]
        row = tk.Frame(scroll_frame, bg=C["bg"])
        row.pack(fill="x", pady=(0, 20))
        for i, (lbl, val, col) in enumerate(stats_data):
            card = tk.Frame(row, bg=C["card"], padx=20, pady=18)
            card.grid(row=0, column=i, padx=6, pady=4, sticky="ew")
            row.columnconfigure(i, weight=1)
            tk.Label(card, text=val, bg=C["card"], fg=col,
                     font=(FONT, 20, "bold")).pack(anchor="w")
            tk.Label(card, text=lbl, bg=C["card"], fg=C["subtext"],
                     font=(FONT, 9)).pack(anchor="w")

        # Current agreement details
        if ag:
            tk.Label(scroll_frame, text="Current Rental", bg=C["bg"], fg=C["white"],
                     font=(FONT, 13, "bold")).pack(anchor="w", pady=(0, 8))
            info_card = tk.Frame(scroll_frame, bg=C["card"], padx=20, pady=16)
            info_card.pack(fill="x")

            info = [
                ("🏢 Property",       ag["prop_name"]),
                ("📍 Address",        f"{ag['address']} | Unit: {ag['unit_number'] or '—'}"),
                ("📅 Lease Period",   f"{ag['start_date']}  to  {ag['end_date']}"),
                ("💵 Monthly Rent",   f"₹{ag['monthly_rent']:,.0f}"),
                ("🔒 Security Dep.",  f"₹{ag['security_deposit']:,.0f}"),
            ]
            for lbl_txt, val in info:
                r2 = tk.Frame(info_card, bg=C["card"])
                r2.pack(fill="x", pady=4)
                tk.Label(r2, text=lbl_txt, bg=C["card"], fg=C["subtext"],
                         font=(FONT, 10), width=18, anchor="w").pack(side="left")
                tk.Label(r2, text=val, bg=C["card"], fg=C["white"],
                         font=(FONT, 10, "bold"), anchor="w").pack(side="left")

        # Recent payments
        tk.Label(scroll_frame, text="Recent Payments", bg=C["bg"], fg=C["white"],
                 font=(FONT, 13, "bold")).pack(anchor="w", pady=(20, 8))
        tf, tree = make_tree(scroll_frame,
                             ("amount","date","method","status","receipt"),
                             ("Amount","Date","Method","Status","Receipt"),
                             (100,120,120,90,180), height=6)
        tf.pack(fill="x")
        conn = get_db()
        pays = conn.execute(
            "SELECT amount,payment_date,method,status,receipt_number FROM payments WHERE tenant_id=? ORDER BY id DESC LIMIT 8",
            (self.user["id"],)).fetchall()
        conn.close()
        for r in pays:
            tree.insert("", "end",
                values=(f"₹{r[0]:,.0f}", r[1], r[2].upper(), r[3].upper(), r[4] or ""))

    def _page_agreement(self):
        page_header(self.content, "My Rental Agreement")
        p = tk.Frame(self.content, bg=C["bg"], padx=24)
        p.pack(fill="both", expand=True)

        conn = get_db()
        ags = conn.execute("""
            SELECT a.*, pr.name as prop_name, pr.address, pr.unit_number, pr.city
            FROM agreements a JOIN properties pr ON pr.id=a.property_id
            WHERE a.tenant_id=? ORDER BY a.id DESC
        """, (self.user["id"],)).fetchall()
        conn.close()

        if not ags:
            tk.Label(p, text="No agreements found.", bg=C["bg"], fg=C["subtext"],
                     font=(FONT, 12)).pack(pady=40)
            return

        for ag in ags:
            card = tk.Frame(p, bg=C["card"], padx=20, pady=16)
            card.pack(fill="x", pady=6)

            header_row = tk.Frame(card, bg=C["card"])
            header_row.pack(fill="x")
            tk.Label(header_row, text=ag["prop_name"], bg=C["card"], fg=C["white"],
                     font=(FONT, 13, "bold")).pack(side="left")
            colors_s = {"active": C["success"], "expired": C["warning"], "terminated": C["danger"]}
            tk.Label(header_row, text=f"  {ag['status'].upper()}  ",
                     bg=colors_s.get(ag["status"], C["accent"]),
                     fg=C["white"], font=(FONT, 8, "bold"),
                     padx=6, pady=2).pack(side="right")

            separator(card).pack(fill="x", pady=8)
            details = [
                ("Address",         f"{ag['address']}, {ag['city'] or ''} | Unit: {ag['unit_number'] or '—'}"),
                ("Lease Period",    f"{ag['start_date']}  →  {ag['end_date']}"),
                ("Monthly Rent",    f"₹{ag['monthly_rent']:,.0f}"),
                ("Security Deposit",f"₹{ag['security_deposit']:,.0f}"),
                ("Terms",           ag["terms"] or "Standard Terms Apply"),
            ]
            for k, v in details:
                rr = tk.Frame(card, bg=C["card"])
                rr.pack(fill="x", pady=3)
                tk.Label(rr, text=k+":", bg=C["card"], fg=C["subtext"],
                         font=(FONT, 10), width=20, anchor="w").pack(side="left")
                tk.Label(rr, text=v, bg=C["card"], fg=C["text"],
                         font=(FONT, 10), anchor="w", wraplength=500).pack(side="left")

    def _page_payments(self):
        page_header(self.content, "My Payments", "View your payment history")
        p = tk.Frame(self.content, bg=C["bg"], padx=24)
        p.pack(fill="both", expand=True)

        conn = get_db()
        years = [r[0] for r in conn.execute(
            "SELECT DISTINCT strftime('%Y',payment_date) FROM payments WHERE tenant_id=? ORDER BY 1 DESC",
            (self.user["id"],)).fetchall()]
        conn.close()
        year_options = ["All Years"] + years
        month_options = ["All Months"] + [calendar.month_name[m] for m in range(1, 13)]
        year_var = tk.StringVar(value=year_options[0])
        month_var = tk.StringVar(value=month_options[0])

        br = tk.Frame(p, bg=C["bg"])
        br.pack(fill="x", pady=(0, 12))
        tk.Label(br, text="Year:", bg=C["bg"], fg=C["subtext"],
                 font=(FONT, 9, "bold")).pack(side="left")
        year_menu = tk.OptionMenu(br, year_var, *year_options)
        year_menu.config(bg=C["card"], fg=C["white"], activebackground=C["hover"], relief="flat", highlightthickness=0)
        year_menu["menu"].config(bg=C["card"], fg=C["text"])
        year_menu.pack(side="left", padx=(6, 12))

        tk.Label(br, text="Month:", bg=C["bg"], fg=C["subtext"],
                 font=(FONT, 9, "bold")).pack(side="left")
        month_menu = tk.OptionMenu(br, month_var, *month_options)
        month_menu.config(bg=C["card"], fg=C["white"], activebackground=C["hover"], relief="flat", highlightthickness=0)
        month_menu["menu"].config(bg=C["card"], fg=C["text"])
        month_menu.pack(side="left", padx=(6, 0))

        styled_btn(br, "🔄 Refresh", lambda: refresh_payments(), color=C["card"], width=12).pack(side="left", padx=12)

        summary_row = tk.Frame(p, bg=C["bg"])
        summary_row.pack(fill="x", pady=(0, 12))
        total_text = tk.StringVar(value="₹0.00")
        selected_text = tk.StringVar(value="All Years")
        count_text = tk.StringVar(value="0")

        def make_summary_card(label, value_var, color):
            card = tk.Frame(summary_row, bg=C["card"], padx=18, pady=16)
            card.pack(side="left", fill="x", expand=True, padx=6)
            tk.Label(card, textvariable=value_var, bg=C["card"], fg=color,
                     font=(FONT, 18, "bold")).pack(anchor="w")
            tk.Label(card, text=label, bg=C["card"], fg=C["subtext"],
                     font=(FONT, 9)).pack(anchor="w")

        make_summary_card("Total Paid", total_text, C["warning"])
        make_summary_card("Selected Period", selected_text, C["accent"])
        make_summary_card("Records", count_text, C["accent2"])

        table_container = tk.Frame(p, bg=C["bg"])
        table_container.pack(fill="both", expand=True)
        self.t_pay_tree = None
        self.t_pay_table_mode = "summary"

        def rebuild_table(columns, headings, widths, rows):
            for child in table_container.winfo_children():
                child.destroy()
            tf, tree = make_tree(table_container, columns, headings, widths, height=10)
            tf.pack(fill="both", expand=True)
            for row in rows:
                tree.insert("", "end", values=row)
            self.t_pay_tree = tree

        def refresh_payments(*_):
            year_value = year_var.get()
            month_value = month_var.get()
            conn = get_db()
            if year_value == "All Years":
                rows = conn.execute(
                    "SELECT strftime('%Y',payment_date) AS period, COALESCE(SUM(amount),0) "
                    "FROM payments WHERE tenant_id=? GROUP BY period ORDER BY period DESC",
                    (self.user["id"],)).fetchall()
                data = [(r[0], f"₹{r[1]:,.2f}") for r in rows]
                total = sum(r[1] for r in rows)
                total_text.set(f"₹{total:,.2f}")
                selected_text.set("All Years")
                count_text.set(str(len(rows)))
                month_menu.config(state="disabled")
                self.t_pay_table_mode = "summary"
                rebuild_table(("period", "amount"), ("Year", "Total Paid"), (180, 140), data)
            else:
                month_menu.config(state="normal")
                if month_value == "All Months":
                    rows = conn.execute(
                        "SELECT strftime('%m',payment_date) AS period, COALESCE(SUM(amount),0) "
                        "FROM payments WHERE tenant_id=? AND strftime('%Y',payment_date)=? "
                        "GROUP BY period ORDER BY period",
                        (self.user["id"], year_value)).fetchall()
                    data = [(calendar.month_name[int(r[0])], f"₹{r[1]:,.2f}") for r in rows]
                    total = sum(r[1] for r in rows)
                    total_text.set(f"₹{total:,.2f}")
                    selected_text.set(year_value)
                    count_text.set(str(len(rows)))
                    self.t_pay_table_mode = "summary"
                    rebuild_table(("period", "amount"), ("Month", "Total Paid"), (180, 140), data)
                else:
                    month_number = f"{month_options.index(month_value):02d}"
                    rows = conn.execute(
                        "SELECT id, amount, payment_date, method, status, receipt_number "
                        "FROM payments WHERE tenant_id=? AND strftime('%Y',payment_date)=? "
                        "AND strftime('%m',payment_date)=? ORDER BY payment_date",
                        (self.user["id"], year_value, month_number)).fetchall()
                    data = [(r[0], f"₹{r[1]:,.2f}", r[2], r[3].upper(), r[4].upper(), r[5] or "") for r in rows]
                    total = sum(r[1] for r in rows)
                    total_text.set(f"₹{total:,.2f}")
                    selected_text.set(f"{month_value} {year_value}")
                    count_text.set(str(len(rows)))
                    self.t_pay_table_mode = "details"
                    rebuild_table(("id", "amount", "date", "method", "status", "receipt"),
                                  ("ID", "Amount", "Date", "Method", "Status", "Receipt"),
                                  (40, 100, 120, 120, 90, 180), data)
            conn.close()

        def update_month_state(*_):
            if year_var.get() == "All Years":
                month_var.set("All Months")
                month_menu.config(state="disabled")
            else:
                month_menu.config(state="normal")
            refresh_payments()

        year_var.trace_add("write", update_month_state)
        month_var.trace_add("write", refresh_payments)
        update_month_state()

        actions = tk.Frame(p, bg=C["bg"])
        actions.pack(fill="x", pady=(12, 0))
        styled_btn(actions, "👁️ View Receipt", self._view_receipt, color=C["accent2"], width=16).pack(side="left")
        styled_btn(actions, "🧾 Save as PDF", self._download_receipt,
                   color=C["success"], width=20).pack(side="left", padx=6)

    def _load_my_payments(self):
        self.t_pay_tree.delete(*self.t_pay_tree.get_children())
        conn = get_db()
        rows = conn.execute(
            "SELECT id,amount,payment_date,method,status,receipt_number FROM payments WHERE tenant_id=? ORDER BY id DESC",
            (self.user["id"],)).fetchall()
        conn.close()
        for r in rows:
            self.t_pay_tree.insert("", "end",
                values=(r[0], f"₹{r[1]:,.0f}", r[2], r[3].upper(), r[4].upper(), r[5] or ""))

    def _download_receipt(self):
        if getattr(self, "t_pay_table_mode", "summary") != "details":
            messagebox.showwarning("Selection Required", "Select a specific payment month detail row to save its receipt.")
            return
        sel = self.t_pay_tree.selection()
        if not sel:
            messagebox.showwarning("Select", "Select a payment first.")
            return
        pid = self.t_pay_tree.item(sel[0])["values"][0]
        try:
            pid = int(pid)
        except Exception:
            messagebox.showwarning("Invalid Selection", "Select a valid payment row.")
            return
        fp  = generate_receipt(pid)
        if fp:
            messagebox.showinfo("Receipt", f"Receipt saved:\n{fp}")
            try:
                if os.name == "nt":
                    os.startfile(fp)
                else:
                    os.system(f"xdg-open '{fp}' &")
            except Exception:
                pass

    def _view_receipt(self):
        if getattr(self, "t_pay_table_mode", "summary") != "details":
            messagebox.showwarning("Selection Required", "Select a specific payment month detail row to view its receipt.")
            return
        sel = self.t_pay_tree.selection()
        if not sel:
            messagebox.showwarning("Select", "Select a payment first.")
            return
        pid = self.t_pay_tree.item(sel[0])["values"][0]
        try:
            pid = int(pid)
        except Exception:
            messagebox.showwarning("Invalid Selection", "Select a valid payment row.")
            return
        conn = get_db()
        row = conn.execute("""
            SELECT p.*, u.full_name as tenant_name, u.phone as tenant_phone,
                   pr.name as property_name, pr.address as property_address,
                   pr.unit_number
            FROM payments p
            JOIN users u ON u.id = p.tenant_id
            JOIN agreements a ON a.id = p.agreement_id
            JOIN properties pr ON pr.id = a.property_id
            WHERE p.id = ?
        """, (pid,)).fetchone()
        conn.close()

        if not row:
            messagebox.showerror("Error", "Receipt not found.")
            return

        dlg = tk.Toplevel(self)
        dlg.title(f"Receipt - {row['receipt_number']}")
        dlg.geometry("500x350")
        dlg.configure(bg=C["bg"])
        dlg.grab_set()

        header = tk.Frame(dlg, bg=C["panel"], padx=20, pady=16)
        header.pack(fill="x")
        tk.Label(header, text="Receipt Information", bg=C["panel"], fg=C["accent"],
                 font=(FONT, 14, "bold")).pack(anchor="w")

        content = tk.Frame(dlg, bg=C["card"], padx=20, pady=16)
        content.pack(fill="both", expand=True)

        def make_row(parent, label_text, value_text):
            row_frame = tk.Frame(parent, bg=C["card"])
            row_frame.pack(fill="x", pady=4)
            tk.Label(row_frame, text=label_text, bg=C["card"], fg=C["subtext"],
                     font=(FONT, 10), width=16, anchor="w").pack(side="left")
            tk.Label(row_frame, text=value_text, bg=C["card"], fg=C["white"],
                     font=(FONT, 10, "bold"), anchor="w").pack(side="left")

        section = tk.Frame(content, bg=C["card"])
        section.pack(fill="x", pady=(0, 16))
        tk.Label(section, text="Tenant Details", bg=C["card"], fg=C["accent"],
                 font=(FONT, 13, "bold")).pack(anchor="w", pady=(0, 8))
        make_row(section, "Tenant Name", row['tenant_name'])
        make_row(section, "Phone", row['tenant_phone'])
        make_row(section, "Property", row['property_name'])
        make_row(section, "Address", f"{row['property_address']} | Unit: {row['unit_number'] or 'N/A'}")

        pay_section = tk.Frame(content, bg=C["card"])
        pay_section.pack(fill="x", pady=(0, 16))
        tk.Label(pay_section, text="Payment Details", bg=C["card"], fg=C["accent"],
                 font=(FONT, 13, "bold")).pack(anchor="w", pady=(0, 8))

        amount_box = tk.Frame(pay_section, bg=C["success"], padx=16, pady=16)
        amount_box.pack(fill="x", pady=(0, 10))
        tk.Label(amount_box, text="Amount Paid", bg=C["success"], fg=C["white"],
                 font=(FONT, 10)).pack(anchor="w")
        tk.Label(amount_box, text=f"₹{row['amount']:,.2f}", bg=C["success"], fg=C["white"],
                 font=(FONT, 24, "bold")).pack(anchor="w", pady=(6, 0))

        make_row(pay_section, "Payment Date", row['payment_date'])
        make_row(pay_section, "Method", row['method'].upper())
        make_row(pay_section, "Status", row['status'].upper())
        make_row(pay_section, "Due Date", row['due_date'] or 'N/A')

        footer = tk.Frame(dlg, bg=C["bg"], pady=12)
        footer.pack(fill="x", padx=20, pady=(12, 12))

        def save_pdf():
            fp = generate_receipt(pid)
            if fp:
                messagebox.showinfo("Receipt", f"Receipt saved:\n{fp}")

        styled_btn(footer, "💾 Save as PDF", save_pdf, color=C["success"], width=18).pack(side="left")
        styled_btn(footer, "✖ Close", dlg.destroy, color=C["danger"], width=12).pack(side="left", padx=8)

    def _page_idproofs(self):
        page_header(self.content, "My ID Proofs", "Manage your identity documents")
        p = tk.Frame(self.content, bg=C["bg"], padx=24)
        p.pack(fill="both", expand=True)

        br = tk.Frame(p, bg=C["bg"])
        br.pack(fill="x", pady=(0, 12))
        styled_btn(br, "+ Upload ID Proof", self._upload_idproof, width=18).pack(side="left")

        tf, self.t_idp_tree = make_tree(p,
            ("id","type","number","verified","uploaded"),
            ("ID","Doc Type","Doc Number","Verified","Uploaded"),
            (40,160,180,90,160))
        tf.pack(fill="both", expand=True)
        self._load_my_idproofs()

    def _load_my_idproofs(self):
        self.t_idp_tree.delete(*self.t_idp_tree.get_children())
        conn = get_db()
        rows = conn.execute(
            "SELECT id,doc_type,doc_number,verified,uploaded_at FROM id_proofs WHERE tenant_id=? ORDER BY id DESC",
            (self.user["id"],)).fetchall()
        conn.close()
        for r in rows:
            v = "✅ Verified" if r[3] else "⏳ Pending"
            self.t_idp_tree.insert("", "end", values=(r[0], r[1], r[2], v, r[4]))

    def _upload_idproof(self):
        dlg = tk.Toplevel(self)
        dlg.title("Upload ID Proof")
        dlg.geometry("400x320")
        dlg.configure(bg=C["card"])
        dlg.grab_set()

        tk.Label(dlg, text="Upload ID Proof", bg=C["card"], fg=C["white"],
                 font=(FONT, 14, "bold")).pack(pady=(20, 10))

        tk.Label(dlg, text="Document Type", bg=C["card"], fg=C["subtext"],
                 font=(FONT, 9)).pack(anchor="w", padx=30)
        dtype_var = tk.StringVar(value="Aadhaar Card")
        dtypes = ["Aadhaar Card", "PAN Card", "Passport", "Voter ID", "Driving Licence", "Other"]
        ttk.Combobox(dlg, textvariable=dtype_var, values=dtypes,
                     state="readonly", font=(FONT, 10), width=38).pack(padx=30, fill="x", pady=(2, 8))

        tk.Label(dlg, text="Document Number", bg=C["card"], fg=C["subtext"],
                 font=(FONT, 9)).pack(anchor="w", padx=30)
        _, num_e = entry_field(dlg, width=36)
        num_e.master.pack(padx=30, fill="x", pady=(2, 8))

        file_path_var = tk.StringVar()
        def browse():
            fp = filedialog.askopenfilename(
                filetypes=[("Image/PDF", "*.jpg *.jpeg *.png *.pdf"), ("All", "*.*")])
            if fp:
                file_path_var.set(fp)
                file_lbl.config(text=os.path.basename(fp))

        fr = tk.Frame(dlg, bg=C["card"])
        fr.pack(fill="x", padx=30, pady=4)
        styled_btn(fr, "📎 Choose File", browse, color=C["accent2"], width=16).pack(side="left")
        file_lbl = tk.Label(fr, text="No file chosen", bg=C["card"], fg=C["subtext"],
                            font=(FONT, 9))
        file_lbl.pack(side="left", padx=10)

        def save():
            dnum = num_e.get().strip()
            if not dnum:
                messagebox.showerror("Error", "Document number is required.")
                return
            dst = None
            if file_path_var.get():
                ext = os.path.splitext(file_path_var.get())[1]
                fn  = f"tenant_{self.user['id']}_{datetime.now().strftime('%Y%m%d%H%M%S')}{ext}"
                dst = os.path.join(DOCS_DIR, fn)
                shutil.copy2(file_path_var.get(), dst)
            conn = get_db()
            conn.execute(
                "INSERT INTO id_proofs (tenant_id,doc_type,doc_number,file_path) VALUES (?,?,?,?)",
                (self.user["id"], dtype_var.get(), dnum, dst))
            conn.commit(); conn.close()
            dlg.destroy()
            self._load_my_idproofs()
            messagebox.showinfo("Uploaded", "ID Proof submitted. Admin will verify it shortly.")

        styled_btn(dlg, "Submit", save, width=20, height=2).pack(pady=14)

    def _page_profile(self):
        page_header(self.content, "My Profile", "View and update your information")
        p = tk.Frame(self.content, bg=C["bg"], padx=24)
        p.pack(fill="both", expand=True)

        card = tk.Frame(p, bg=C["card"], padx=30, pady=30)
        card.pack(fill="x", pady=10)
        card.columnconfigure(1, weight=1)

        top_row = tk.Frame(card, bg=C["card"])
        top_row.pack(fill="x")

        avatar_frame = tk.Frame(top_row, bg=C["card"])
        avatar_frame.grid(row=0, column=0, sticky="nw")
        canvas = tk.Canvas(avatar_frame, width=100, height=100, bg=C["card"], highlightthickness=0)
        canvas.pack()
        canvas.create_oval(4, 4, 96, 96, fill=C["accent"], outline="")
        canvas.create_text(50, 50, text=self.user["full_name"][0].upper(),
                           font=(FONT, 32, "bold"), fill=C["white"])
        tk.Label(avatar_frame, text=self.user["full_name"], bg=C["card"], fg=C["white"],
                 font=(FONT, 11, "bold")).pack(pady=(12, 0))

        form_frame = tk.Frame(top_row, bg=C["card"])
        form_frame.grid(row=0, column=1, sticky="nsew", padx=(40, 0))
        form_frame.columnconfigure(0, weight=1)

        fields_def = [("Full Name", "full_name"), ("Email", "email"), ("Phone", "phone")]
        entries = {}
        for idx, (lbl_txt, key) in enumerate(fields_def):
            tk.Label(form_frame, text=lbl_txt, bg=C["card"], fg=C["subtext"],
                     font=(FONT, 9)).grid(row=idx * 2, column=0, sticky="w", pady=(8, 0))
            frm, ent = entry_field(form_frame, width=42)
            frm.grid(row=idx * 2 + 1, column=0, sticky="ew", pady=(4, 0))
            if self.user.get(key):
                ent.insert(0, self.user[key])
            entries[key] = ent

        separator(card).pack(fill="x", pady=24)
        tk.Label(card, text="Change Password", bg=C["card"], fg=C["white"],
                 font=(FONT, 11, "bold")).pack(anchor="w", pady=(0, 8))

        pw_row = tk.Frame(card, bg=C["card"])
        pw_row.pack(fill="x")
        left_pw = tk.Frame(pw_row, bg=C["card"])
        left_pw.pack(side="left", fill="x", expand=True)
        right_pw = tk.Frame(pw_row, bg=C["card"])
        right_pw.pack(side="left", fill="x", expand=True, padx=(18, 0))

        pw_entries = {}
        pw_labels = ["New Password", "Confirm Password"]
        for idx, lbl_txt in enumerate(pw_labels):
            container = left_pw if idx == 0 else right_pw
            tk.Label(container, text=lbl_txt, bg=C["card"], fg=C["subtext"],
                     font=(FONT, 9)).pack(anchor="w")
            frm, ent = entry_field(container, show="●", width=24)
            frm.pack(fill="x", pady=(4, 8))
            pw_entries[lbl_txt] = ent

        def save():
            name  = entries["full_name"].get().strip()
            email = entries["email"].get().strip()
            phone = entries["phone"].get().strip()
            npw   = pw_entries["New Password"].get().strip()
            cpw   = pw_entries["Confirm Password"].get().strip()
            if not name:
                messagebox.showerror("Error", "Name is required.")
                return
            conn = get_db()
            if npw:
                if npw != cpw:
                    messagebox.showerror("Error", "Passwords do not match.")
                    conn.close(); return
                if len(npw) < 6:
                    messagebox.showerror("Error", "Password must be 6+ characters.")
                    conn.close(); return
                conn.execute(
                    "UPDATE users SET full_name=?,email=?,phone=?,password=? WHERE id=?",
                    (name, email, phone, hash_pw(npw), self.user["id"]))
            else:
                conn.execute(
                    "UPDATE users SET full_name=?,email=?,phone=? WHERE id=?",
                    (name, email, phone, self.user["id"]))
            conn.commit(); conn.close()
            self.user["full_name"] = name
            messagebox.showinfo("Saved", "Profile updated successfully.")

        styled_btn(card, "💾 Save Changes", save, width=20, height=2).pack(pady=16, anchor="e")

# ══════════════════════════════════════════════════════════════════════════════
#  APPLICATION CONTROLLER
# ══════════════════════════════════════════════════════════════════════════════
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("TenantMS – Tenant Management System")
        self.geometry("1200x720")
        self.minsize(1000, 620)
        self.configure(bg=C["bg"])

        self.update_idletasks()
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        taskbar_margin = 40
        x = max((screen_w - 1200) // 2, 0)
        y = max((screen_h - 720 - taskbar_margin) // 2, 0)
        self.geometry(f"1200x720+{x}+{y}")
        self.maxsize(screen_w, max(screen_h - taskbar_margin, 620))

        init_db()
        self._show_loading()

    def _clear(self):
        for w in self.winfo_children():
            w.destroy()

    def _show_loading(self):
        self._clear()
        LoadingScreen(self, self._show_auth)

    def _show_auth(self):
        self._clear()
        AuthScreen(self, self._on_login)

    def _on_login(self, user):
        self._clear()
        if user["role"] == "admin":
            AdminDashboard(self, user, self._show_auth)
        else:
            TenantDashboard(self, user, self._show_auth)


if __name__ == "__main__":
    app = App()
    app.mainloop()
