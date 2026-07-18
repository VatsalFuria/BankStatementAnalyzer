import json
import os
import re

from analyzer.database import get_connection, db_session
from analyzer.config import DEFAULT_RULES_FILE, RULES_FILE
from analyzer.constants import MatchOp, CategorySource, CategoryType
from analyzer.categories import set_category_type
from analyzer.exceptions import BSAError
from analyzer.logging_config import logger


def load_rules():
    with db_session(commit=False) as conn:
        rows = conn.execute("SELECT * FROM rules ORDER BY priority ASC").fetchall()
    rules = []
    for r in rows:
        rule = dict(r)
        if(rule["match_op"]==MatchOp.REGEX.value):
            try:
                re.compile(r["match_value"])
            except re.error:
                logger.error("Invalid regex: %r", r["match_value"])
                continue
        else: 
            rule['match_value'] = rule['match_value'].upper()
            
        rules.append(rule)
    return rules


def get_all_rules():
    """Full rule rows for the GUI's Rules tab. Unlike load_rules(), this
    doesn't upper-case match_value (editing should show what was typed)
    and doesn't drop invalid-regex rows (the GUI should surface those,
    not silently hide them)."""
    with db_session(commit=False) as conn:
        return conn.execute("SELECT * FROM rules ORDER BY priority ASC, id ASC").fetchall()


def get_rule(rule_id: int):
    with db_session(commit=False) as conn:
        return conn.execute("SELECT * FROM rules WHERE id=?", (rule_id,)).fetchone()


def test_rule(rule: dict, transaction: dict) -> bool:
    """Check if a single rule matches a transaction (row from DB)."""
    rule_dr_cr = rule['dr_cr']
    if rule_dr_cr and transaction['dr_cr'] != rule_dr_cr:
        return False

    match_field = rule['match_field']
    match_op = rule['match_op']
    match_value = rule['match_value']

    if match_field == 'description':
        text = transaction['description'] or ''
    elif match_field == 'bank':
        text = transaction['bank'] or ''
    elif match_field == 'reference':
        text = transaction['reference'] or ''
    else:
        return False

    text = str(text).upper()

    if match_op == MatchOp.CONTAINS.value:
        return match_value in text
    elif match_op == MatchOp.STARTSWITH.value:
        return text.startswith(match_value)
    elif match_op == MatchOp.REGEX.value:
        try:
            return bool(re.search(match_value, text, re.IGNORECASE))
        except re.error:
            return False
    elif match_op == MatchOp.EQUALS.value:
        return text == match_value
    return False


def apply_rules(transaction_list=None):
    rules = load_rules()
    with db_session(commit=True) as conn:

        if transaction_list is not None and not transaction_list:
            return 0

        if transaction_list is None:
            txns = conn.execute("""
                SELECT txn_id, description, bank, reference, dr_cr FROM transactions
                WHERE category IS NULL OR category_src != ?
            """, (CategorySource.MANUAL.value,)).fetchall()
        else:
            placeholders = ",".join("?" * len(transaction_list))
            txns = conn.execute(
                f"""
                SELECT txn_id, description, bank, reference, dr_cr
                FROM transactions
                WHERE txn_id IN ({placeholders})
                AND (category IS NULL OR category_src != ?)
                """,
                (*transaction_list, CategorySource.MANUAL.value),
            ).fetchall()

        count = 0
        for txn in txns:
            for rule in rules:
                if test_rule(rule, txn):
                    conn.execute("""
                        UPDATE transactions
                        SET category = ?, category_src = ?, rule_id = ?
                        WHERE txn_id = ?
                    """, (rule['category'], CategorySource.RULE.value, rule['id'], txn['txn_id']))
                    count += 1
                    break
    logger.info(f"apply_rules: categorized {count} transaction(s) using {len(rules)} rule(s)")
    return count


def reapply_all_rules():
    with db_session() as conn:
        conn.execute(
            "UPDATE transactions SET category=NULL, category_src=NULL, rule_id=NULL WHERE category_src=?",
            (CategorySource.RULE.value,),
        )
    apply_rules()
    apply_manual_overrides()


def apply_manual_overrides():
    with db_session() as conn:
        overrides = conn.execute("SELECT txn_id, category FROM manual_overrides").fetchall()
        for ov in overrides:
            conn.execute("""
                UPDATE transactions
                SET category = ?, category_src = ?, rule_id = NULL
                WHERE txn_id = ?
            """, (ov['category'], CategorySource.MANUAL.value, ov['txn_id']))


def add_manual_override(txn_id: int, category: str,
                         category_type: str = CategoryType.UNSPECIFIED.value,
                         reason: str | None = None):
    with db_session() as conn:
        conn.execute("""
            INSERT INTO manual_overrides (txn_id, category, reason)
            VALUES (?, ?, ?)
            ON CONFLICT(txn_id) DO UPDATE SET category=excluded.category, reason=excluded.reason
        """, (txn_id, category, reason))
    apply_manual_overrides()

    if category_type:
        set_category_type(category, category_type)


def add_rule(priority, match_field, match_op, match_value, category,
             category_type=None, source='manual', dr_cr=None):
    """dr_cr: None/'' = matches either direction, 'DR' or 'CR' scopes the
    rule to only that direction (see constants.DrCr). Every insert is
    followed by export_rules_to_json() so the tracked JSON file is always
    an up-to-date mirror of the DB — callers never need to remember to
    export separately."""
    with db_session() as conn:
        conn.execute("""
            INSERT INTO rules (priority, match_field, match_op, match_value, category, category_type, source, dr_cr)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (priority, match_field, match_op, match_value, category,
              category_type or CategoryType.UNSPECIFIED.value, source, dr_cr or None))
    if category_type:
        set_category_type(category, category_type)
    export_rules_to_json()


def update_rule(rule_id: int, **fields):
    """Partial update of a rule's editable columns. Unknown keys are
    ignored, so callers can pass a dialog's result dict straight through
    (match_field is intentionally never touched by the GUI dialogs, so a
    rule someone hand-authored against 'bank' or 'reference' in the JSON
    doesn't silently get flipped to 'description' on edit)."""
    editable = {"priority", "match_field", "match_op", "match_value",
                "category", "category_type", "dr_cr"}
    updates = {k: v for k, v in fields.items() if k in editable}
    if not updates:
        return
    set_clause = ", ".join(f"{k}=?" for k in updates)
    with db_session() as conn:
        conn.execute(f"UPDATE rules SET {set_clause} WHERE id=?",
                     (*updates.values(), rule_id))
    if "category" in updates and "category_type" in updates:
        set_category_type(updates["category"], updates["category_type"])
    export_rules_to_json()


def delete_rule(rule_id: int):
    """Clears the FK from any transaction that was categorized by this
    rule (their category stays, only the rule provenance link goes) —
    the same approach reject_match() uses for match_id."""
    with db_session() as conn:
        conn.execute("UPDATE transactions SET rule_id=NULL WHERE rule_id=?", (rule_id,))
        conn.execute("DELETE FROM rules WHERE id=?", (rule_id,))
    export_rules_to_json()


def move_rule(rule_id: int, direction: str):
    """direction: 'up' moves a rule earlier (higher precedence), 'down'
    later. Swaps priority with the adjacent rule in the currently
    displayed order rather than assuming priorities are unique/gapless
    (they aren't, in the shipped default_rules.json)."""
    with db_session() as conn:
        rows = conn.execute("SELECT id, priority FROM rules ORDER BY priority ASC, id ASC").fetchall()
        ids = [r["id"] for r in rows]
        if rule_id not in ids:
            return
        idx = ids.index(rule_id)
        neighbor_idx = idx - 1 if direction == "up" else idx + 1
        if neighbor_idx < 0 or neighbor_idx >= len(ids):
            return
        this_priority = rows[idx]["priority"]
        neighbor_priority = rows[neighbor_idx]["priority"]
        conn.execute("UPDATE rules SET priority=? WHERE id=?", (neighbor_priority, rule_id))
        conn.execute("UPDATE rules SET priority=? WHERE id=?", (this_priority, ids[neighbor_idx]))
    export_rules_to_json()


def export_rules_to_json(filepath: str | None = None):
    """Dump the current rules table to JSON in the same shape as
    default_rules.json, so the live rule set is diffable/trackable/
    shareable independent of the DB file. Called automatically by every
    mutation above — the Rules tab's explicit 'Export...' just points
    this at a different path for a one-off copy."""
    filepath = filepath or RULES_FILE
    with db_session(commit=False) as conn:
        rows = conn.execute("SELECT * FROM rules ORDER BY priority ASC, id ASC").fetchall()
    definitions = [{
        "priority": r["priority"],
        "match_field": r["match_field"],
        "match_op": r["match_op"],
        "match_value": r["match_value"],
        "category": r["category"],
        "category_type": r["category_type"],
        "dr_cr": r["dr_cr"],
    } for r in rows]
    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(definitions, f, indent=2)
    logger.info(f"Exported {len(definitions)} rule(s) to {filepath}")


def import_rules_from_json(filepath: str, mode: str = "merge") -> int:
    """
    mode='merge' (default): only inserts rules not already present, keyed
    on (match_field, match_op, upper-cased match_value) — the same dedup
    key default_rules.json's seeding uses, so importing a shared file
    twice, or over an already-customized rule set, is safe and idempotent.
    mode='replace': wipes all existing rules first (used for the very
    first launch when a tracked rules.json is already present, and for
    the GUI's explicit "Replace All").
    Returns the number of rules inserted.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            definitions = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        raise BSAError(f"Could not read rules file: {e}") from e

    if mode == "replace":
        with db_session() as conn:
            conn.execute("UPDATE transactions SET rule_id=NULL")
            conn.execute("DELETE FROM rules")
        existing_keys = set()
    else:
        with db_session(commit=False) as conn:
            existing = conn.execute("SELECT match_field, match_op, match_value FROM rules").fetchall()
        existing_keys = {(r["match_field"], r["match_op"], r["match_value"].upper()) for r in existing}

    inserted = 0
    for r in definitions:
        key = (r["match_field"], r["match_op"], r["match_value"].upper())
        if key in existing_keys:
            continue
        add_rule(
            r["priority"], r["match_field"], r["match_op"], r["match_value"],
            r["category"], category_type=r.get("category_type"),
            source="manual", dr_cr=r.get("dr_cr"),
        )
        existing_keys.add(key)
        inserted += 1
    logger.info(f"import_rules_from_json({mode}): inserted {inserted} rule(s) from {filepath}")
    return inserted


def get_override_priority():
    conn = get_connection()
    row = conn.execute("SELECT MIN(priority) as min_priority FROM rules").fetchone()
    conn.close()
    current_min = row["min_priority"] if row["min_priority"] is not None else 1
    return current_min - 1


def _load_seed_rule_definitions():
    try:
        with open(DEFAULT_RULES_FILE, "r", encoding="utf-8") as f:
            rules = json.load(f)
    except FileNotFoundError:
        logger.warning(
            f"Default rules file not found at {DEFAULT_RULES_FILE}; "
            "seeding only the payment-mode Transfer rules."
        )
        rules = []

    return rules


def seed_default_rules():
    for r in _load_seed_rule_definitions():
        add_rule(
            r["priority"], r["match_field"], r["match_op"], r["match_value"],
            r["category"], category_type=r.get("category_type"),
            source='manual', dr_cr=r.get("dr_cr"),
        )