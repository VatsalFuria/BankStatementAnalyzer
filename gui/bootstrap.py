from analyzer.database import init_db, get_connection
from analyzer.rule_engine import seed_default_rules


def ensure_ready():
    """Create tables and seed default rules on first run. Safe to call
    every launch — only seeds if the rules table is actually empty."""
    init_db()
    conn = get_connection()
    rule_count = conn.execute("SELECT COUNT(*) AS c FROM rules").fetchone()["c"]
    conn.close()
    if rule_count == 0:
        seed_default_rules()