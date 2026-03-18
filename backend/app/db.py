import os
import sqlite3
from datetime import datetime, timezone


_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL,
    is_confirmed  INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS email_confirmation_tokens (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token      TEXT    NOT NULL UNIQUE,
    expires_at TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS deals (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id   TEXT NOT NULL,
    name         TEXT,
    brand        TEXT,
    qty          TEXT,
    source       TEXT NOT NULL DEFAULT 'web',
    category     TEXT NOT NULL,
    price        REAL NOT NULL,
    old_price    REAL,
    discount_pct INTEGER,
    promo_label  TEXT,
    image_url    TEXT,
    product_url  TEXT,
    scraped_at   TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_deals_product_category
    ON deals (product_id, category);

CREATE TABLE IF NOT EXISTS grocery_items (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name      TEXT    NOT NULL,
    quantity  TEXT,
    added_at  TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_grocery_items_user
    ON grocery_items (user_id);
"""

# Columns added after initial release — applied to existing DBs via migration
_MIGRATIONS = [
    "ALTER TABLE deals ADD COLUMN brand       TEXT",
    "ALTER TABLE deals ADD COLUMN qty         TEXT",
    "ALTER TABLE deals ADD COLUMN source      TEXT NOT NULL DEFAULT 'web'",
    "ALTER TABLE deals ADD COLUMN promo_label TEXT",
]


def init_db(app):
    os.makedirs(app.instance_path, exist_ok=True)
    db_path = os.path.join(app.instance_path, "food_chaser.db")
    app.config["DATABASE"] = db_path
    with sqlite3.connect(db_path) as conn:
        conn.executescript(_SCHEMA)
        for sql in _MIGRATIONS:
            try:
                conn.execute(sql)
            except sqlite3.OperationalError:
                pass  # column already exists


def _connect(app):
    return sqlite3.connect(app.config["DATABASE"])


def save_deals(app, deals: list) -> int:
    if not deals:
        return 0
    now = datetime.now(timezone.utc).isoformat()
    rows = [
        (
            d["product_id"],
            d.get("name"),
            d.get("brand"),
            d.get("qty"),
            d.get("source", "web"),
            d["category"],
            d["price"],
            d.get("old_price"),
            d.get("discount_pct"),
            d.get("promo_label"),
            d.get("image_url"),
            d.get("product_url"),
            now,
        )
        for d in deals
    ]
    with _connect(app) as conn:
        conn.executemany(
            """INSERT OR REPLACE INTO deals
               (product_id, name, brand, qty, source, category, price,
                old_price, discount_pct, promo_label, image_url, product_url, scraped_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
    return len(rows)


def get_deals(app, category: str = None) -> list:
    with _connect(app) as conn:
        conn.row_factory = sqlite3.Row
        if category:
            rows = conn.execute(
                "SELECT * FROM deals WHERE category = ? ORDER BY discount_pct DESC NULLS LAST",
                (category,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM deals ORDER BY discount_pct DESC NULLS LAST"
            ).fetchall()
    return [dict(r) for r in rows]


def get_categories(app) -> list:
    with _connect(app) as conn:
        rows = conn.execute(
            "SELECT DISTINCT category FROM deals ORDER BY category"
        ).fetchall()
    return [r[0] for r in rows]


# ── Grocery list helpers ──────────────────────────────────────────


def get_grocery_items(app, user_id: int) -> list:
    with _connect(app) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM grocery_items WHERE user_id = ? ORDER BY added_at DESC",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def add_grocery_item(app, user_id: int, name: str, quantity: str = None) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    with _connect(app) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "INSERT INTO grocery_items (user_id, name, quantity, added_at) VALUES (?, ?, ?, ?)",
            (user_id, name, quantity, now),
        )
        row = conn.execute(
            "SELECT * FROM grocery_items WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
    return dict(row)


def update_grocery_item(app, item_id: int, user_id: int, name: str, quantity: str = None) -> dict | None:
    with _connect(app) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "UPDATE grocery_items SET name = ?, quantity = ? WHERE id = ? AND user_id = ?",
            (name, quantity, item_id, user_id),
        )
        if cur.rowcount == 0:
            return None
        row = conn.execute(
            "SELECT * FROM grocery_items WHERE id = ?", (item_id,)
        ).fetchone()
    return dict(row)


def delete_grocery_item(app, item_id: int, user_id: int) -> bool:
    with _connect(app) as conn:
        cur = conn.execute(
            "DELETE FROM grocery_items WHERE id = ? AND user_id = ?",
            (item_id, user_id),
        )
    return cur.rowcount > 0
