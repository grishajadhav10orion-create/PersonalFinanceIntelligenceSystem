import sqlite3
import json
import os

DB_PATH = os.environ.get("DB_PATH") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "finance.db")   # always next to the code, whatever folder the app is started from

# ─── Init ─────────────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS masters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE NOT NULL,
            categories TEXT NOT NULL,
            subcategories TEXT NOT NULL,
            receivers TEXT NOT NULL,
            payers TEXT NOT NULL,
            opening_balance REAL NOT NULL DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            type TEXT NOT NULL CHECK(type IN ('expense','earning')),
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            subcategory TEXT DEFAULT '',
            receiver_payer TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            date TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS budgets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            period TEXT NOT NULL CHECK(period IN ('weekly','monthly')),
            amount REAL NOT NULL,
            category TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(user_id, period, category),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    _migrate_records(conn)
    conn.commit()
    conn.close()

# New columns added to `records` for bank-statement import + ML categorisation.
# Existing rows keep their data; they default to source='manual' / category_source='manual'
# (i.e. user-labelled), which is what makes them usable as ML training labels.
_NEW_RECORD_COLUMNS = [
    ("source", "TEXT DEFAULT 'manual'"),            # 'manual' | 'statement'
    ("raw_narration", "TEXT DEFAULT ''"),
    ("bank_ref", "TEXT DEFAULT ''"),
    ("balance_after", "REAL"),
    ("dedupe_key", "TEXT"),
    ("category_source", "TEXT DEFAULT 'manual'"),   # manual | user | ml | rule | default
    ("category_confidence", "REAL"),                # only set when category_source='ml'
]

def _migrate_records(conn):
    existing = {r[1] for r in conn.execute("PRAGMA table_info(records)")}
    for name, ddl in _NEW_RECORD_COLUMNS:
        if name not in existing:
            conn.execute(f"ALTER TABLE records ADD COLUMN {name} {ddl}")
    conn.execute("""CREATE UNIQUE INDEX IF NOT EXISTS idx_records_dedupe
                    ON records(user_id, dedupe_key) WHERE dedupe_key IS NOT NULL""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_records_user_date ON records(user_id, date)")

# ─── Users ────────────────────────────────────────────────────────────────────

def create_user(username, password_hash):
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, password_hash))
    conn.commit()
    user_id = c.lastrowid
    conn.close()
    return user_id

def get_user_by_username(username):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username = ?", (username,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

# ─── Masters ──────────────────────────────────────────────────────────────────

def has_masters(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM masters WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row is not None

def save_masters(user_id, categories, subcategories, receivers, payers, opening_balance):
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        INSERT INTO masters (user_id, categories, subcategories, receivers, payers, opening_balance)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        user_id,
        json.dumps(categories),
        json.dumps(subcategories),
        json.dumps(receivers),
        json.dumps(payers),
        opening_balance
    ))
    conn.commit()
    conn.close()

def update_masters(user_id, categories, subcategories, receivers, payers, opening_balance):
    """Update existing masters - allows editing after initial creation."""
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        UPDATE masters
        SET categories=?, subcategories=?, receivers=?, payers=?, opening_balance=?
        WHERE user_id=?
    """, (
        json.dumps(categories),
        json.dumps(subcategories),
        json.dumps(receivers),
        json.dumps(payers),
        opening_balance,
        user_id
    ))
    conn.commit()
    conn.close()

def get_masters(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM masters WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    return {
        "categories": json.loads(row["categories"]),
        "subcategories": json.loads(row["subcategories"]),
        "receivers": json.loads(row["receivers"]),
        "payers": json.loads(row["payers"]),
        "opening_balance": row["opening_balance"]
    }

# ─── Records ──────────────────────────────────────────────────────────────────

def add_record(user_id, record_type, amount, category, subcategory, receiver_payer, notes, date):
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        INSERT INTO records (user_id, type, amount, category, subcategory, receiver_payer, notes, date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (user_id, record_type, amount, category, subcategory, receiver_payer, notes, date))
    conn.commit()
    record_id = c.lastrowid
    conn.close()
    return record_id

def get_record_by_id(record_id, user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM records WHERE id = ? AND user_id = ?", (record_id, user_id))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def get_records(user_id, filters=None):
    conn = get_db()
    c = conn.cursor()
    query = "SELECT * FROM records WHERE user_id = ?"
    params = [user_id]

    if filters:
        if filters.get("min_amount"):
            try:
                query += " AND amount >= ?"
                params.append(float(filters["min_amount"]))
            except ValueError:
                pass
        if filters.get("max_amount"):
            try:
                query += " AND amount <= ?"
                params.append(float(filters["max_amount"]))
            except ValueError:
                pass
        if filters.get("receiver_payer"):
            query += " AND receiver_payer LIKE ?"
            params.append(f"%{filters['receiver_payer']}%")
        if filters.get("record_type"):
            query += " AND type = ?"
            params.append(filters["record_type"])
        if filters.get("category"):
            query += " AND category = ?"
            params.append(filters["category"])
        if filters.get("date_from"):
            query += " AND date >= ?"
            params.append(filters["date_from"])
        if filters.get("date_to"):
            query += " AND date <= ?"
            params.append(filters["date_to"])

    query += " ORDER BY date DESC, created_at DESC"
    c.execute(query, params)
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def update_record(record_id, user_id, record_type, amount, category, subcategory, receiver_payer, notes, date):
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        UPDATE records
        SET category_source = CASE WHEN category <> ? THEN 'user' ELSE category_source END,
            category_confidence = CASE WHEN category <> ? THEN NULL ELSE category_confidence END,
            type=?, amount=?, category=?, subcategory=?, receiver_payer=?, notes=?, date=?
        WHERE id=? AND user_id=?
    """, (category, category, record_type, amount, category, subcategory, receiver_payer, notes, date, record_id, user_id))
    conn.commit()
    conn.close()

def delete_record(record_id, user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM records WHERE id = ? AND user_id = ?", (record_id, user_id))
    conn.commit()
    conn.close()

# ─── Dashboard ────────────────────────────────────────────────────────────────

def get_dashboard_data(user_id):
    conn = get_db()
    c = conn.cursor()

    masters = get_masters(user_id)
    opening_balance = masters["opening_balance"] if masters else 0

    c.execute("SELECT COALESCE(SUM(amount),0) FROM records WHERE user_id=? AND type='earning'", (user_id,))
    total_earnings = c.fetchone()[0]

    c.execute("SELECT COALESCE(SUM(amount),0) FROM records WHERE user_id=? AND type='expense'", (user_id,))
    total_expenses = c.fetchone()[0]

    # Monthly breakdown for chart (last 6 months)
    c.execute("""
        SELECT strftime('%Y-%m', date) as month,
               SUM(CASE WHEN type='earning' THEN amount ELSE 0 END) as earnings,
               SUM(CASE WHEN type='expense' THEN amount ELSE 0 END) as expenses
        FROM records WHERE user_id=?
        GROUP BY month
        ORDER BY month DESC
        LIMIT 6
    """, (user_id,))
    monthly = [dict(r) for r in c.fetchall()]

    # Category breakdown for expenses
    c.execute("""
        SELECT category, SUM(amount) as total
        FROM records WHERE user_id=? AND type='expense'
        GROUP BY category
        ORDER BY total DESC
        LIMIT 8
    """, (user_id,))
    category_breakdown = [dict(r) for r in c.fetchall()]

    c.execute("""
        SELECT * FROM records WHERE user_id=?
        ORDER BY date DESC, created_at DESC
        LIMIT 10
    """, (user_id,))
    last_10 = [dict(r) for r in c.fetchall()]

    conn.close()

    return {
        "opening_balance": opening_balance,
        "total_earnings": total_earnings,
        "total_expenses": total_expenses,
        "balance": opening_balance + total_earnings - total_expenses,
        "monthly_breakdown": list(reversed(monthly)),
        "category_breakdown": category_breakdown,
        "recent_records": last_10
    }

# ─── Budgets ──────────────────────────────────────────────────────────────────

def set_budget(user_id, period, amount, category=''):
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        INSERT INTO budgets (user_id, period, amount, category)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id, period, category) DO UPDATE SET amount=excluded.amount
    """, (user_id, period, amount, category))
    conn.commit()
    conn.close()

def get_budgets(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM budgets WHERE user_id=? ORDER BY period, category", (user_id,))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def delete_budget(budget_id, user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM budgets WHERE id=? AND user_id=?", (budget_id, user_id))
    conn.commit()
    conn.close()

def _budget_bounds(period, ref):
    import datetime
    if period == 'monthly':
        start = ref.replace(day=1)
        end = (start.replace(day=28) + datetime.timedelta(days=4)).replace(day=1) - datetime.timedelta(days=1)
    else:
        start = ref - datetime.timedelta(days=ref.weekday())
        end = start + datetime.timedelta(days=6)
    return start, end

def _budget_usage(c, user_id, b):
    """Spend for a budget from ALL stored expense records (manual + imported) in the budget's
    period/category. Uses the current period; if it has no spend yet, uses the most recent
    period that does, so existing historical records are always counted."""
    import datetime
    today = datetime.date.today()
    cat_sql, cat_args = ("", [])
    if b['category']:
        cat_sql, cat_args = (" AND LOWER(category)=LOWER(?)", [b['category']])
    def spent_in(start, end):
        c.execute("SELECT COALESCE(SUM(amount),0) FROM records WHERE user_id=? AND type='expense'"
                  + cat_sql + " AND date>=? AND date<=?",
                  [user_id] + cat_args + [start.isoformat(), end.isoformat()])
        return c.fetchone()[0]
    start, end = _budget_bounds(b['period'], today)
    spent = spent_in(start, min(end, today))
    if spent == 0:
        c.execute("SELECT MAX(date) FROM records WHERE user_id=? AND type='expense'"
                  + cat_sql + " AND date<=?", [user_id] + cat_args + [today.isoformat()])
        row = c.fetchone()
        if row and row[0]:
            try:
                ref = datetime.date.fromisoformat(row[0][:10])
                start, end = _budget_bounds(b['period'], ref)
                spent = spent_in(start, min(end, today))
            except ValueError:
                pass
    if b['period'] == 'monthly':
        label = start.strftime("%b %Y")
    else:
        label = "week of " + start.isoformat()
    return spent, label

def get_budget_progress(user_id):
    """Every budget with its spent amount, percentage and period label."""
    conn = get_db()
    c = conn.cursor()
    out = []
    for b in get_budgets(user_id):
        spent, label = _budget_usage(c, user_id, b)
        b = dict(b)
        b.update(spent=spent, pct=round((spent / b['amount']) * 100) if b['amount'] > 0 else 0,
                 period_label=label)
        out.append(b)
    conn.close()
    return out

def check_budget_alerts(user_id):
    alerts = []
    for b in get_budget_progress(user_id):
        spent, pct = b['spent'], b['pct']
        cat_label = b['category'] or "Overall"
        if spent >= b['amount']:
            alerts.append({"status": "exceeded", "period": b['period'], "category": cat_label, "budget": b['amount'], "spent": spent, "pct": pct, "suggestion": f"Limit exceeded for {b['period']} {cat_label} budget. Spent ₹{spent:,.0f} vs ₹{b['amount']:,.0f}. Consider reducing discretionary spending."})
        elif pct >= 80:
            alerts.append({"status": "warning", "period": b['period'], "category": cat_label, "budget": b['amount'], "spent": spent, "pct": pct, "suggestion": f"{pct}% used of {b['period']} {cat_label} budget. Spent ₹{spent:,.0f} of ₹{b['amount']:,.0f}."})
    return alerts


# ─── Statement import / ML support ────────────────────────────────────────────

def insert_imported_records(user_id, rows):
    """Insert imported bank rows. Rows whose (user_id, dedupe_key) already exists are
    skipped. Returns (inserted, duplicates). Runs in one transaction."""
    conn = get_db()
    inserted = dup = 0
    try:
        for r in rows:
            cur = conn.execute(
                """INSERT OR IGNORE INTO records
                   (user_id, type, amount, category, subcategory, receiver_payer, notes, date,
                    source, raw_narration, bank_ref, balance_after, dedupe_key,
                    category_source, category_confidence)
                   VALUES (?,?,?,?,?,?,?,?, 'statement', ?,?,?,?, ?,?)""",
                (user_id, r["type"], r["amount"], r["category"], "", r["receiver_payer"], "",
                 r["date"], r["raw_narration"], r["bank_ref"], r["balance_after"],
                 r["dedupe_key"], r["category_source"], r["category_confidence"]))
            if cur.rowcount:
                inserted += 1
            else:
                dup += 1
        conn.commit()
    finally:
        conn.close()
    return inserted, dup

def get_labeled_records(user_id):
    """Records whose category was chosen by the user (manual entry or later edit)."""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM records WHERE user_id=? AND category_source IN ('manual','user')",
        (user_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_auto_categorized_records(user_id):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM records WHERE user_id=? AND category_source IN ('ml','rule','default')",
        (user_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def set_auto_category(record_id, user_id, category, source, confidence):
    conn = get_db()
    conn.execute(
        "UPDATE records SET category=?, category_source=?, category_confidence=? "
        "WHERE id=? AND user_id=? AND category_source IN ('ml','rule','default')",
        (category, source, confidence, record_id, user_id))
    conn.commit()
    conn.close()

def ensure_master_categories(user_id, categories):
    """Add categories to the user's masters list (so dropdowns/budgets can use them)."""
    m = get_masters(user_id)
    if m is None:
        return
    have = {c.lower() for c in m["categories"]}
    new = [c for c in categories if c and c.lower() not in have]
    if new:
        update_masters(user_id, m["categories"] + new, m["subcategories"],
                       m["receivers"], m["payers"], m["opening_balance"])
