import os
import sqlite3
from datetime import datetime, timezone


_SCHEMA = """
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
