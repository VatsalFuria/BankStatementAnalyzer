import os

from analyzer.database import init_db, get_connection
from analyzer.config import RULES_FILE
from analyzer.rule_engine import seed_default_rules, import_rules_from_json


def ensure_ready():
    """Create tables and seed rules on first run. Safe to call every
    launch — only seeds if the rules table is actually empty.
    If a tracked rules.json is already present (e.g. a fresh clone of a
    repo that already had a customized rule set), that's loaded instead
    of the factory default_rules.json, so committing/sharing rules.json
    reproduces someone's full rule set, not just the shipped defaults."""
    init_db()
    conn = get_connection()
    rule_count = conn.execute("SELECT COUNT(*) AS c FROM rules").fetchone()["c"]
    conn.close()
    if rule_count == 0:
        if os.path.exists(RULES_FILE):
            import_rules_from_json(RULES_FILE, mode="replace")
        else:
            seed_default_rules()