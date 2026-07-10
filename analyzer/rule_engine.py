import json
import re

from analyzer.database import get_connection, db_session
from analyzer.config import DEFAULT_RULES_FILE
from analyzer.constants import MatchOp, CategorySource, CategoryType, PAYMENT_MODE_KEYWORDS
from analyzer.categories import set_category_type
from analyzer.logging_config import logger

"""
Inefficiencies, identified.. should be corrected if an easy fix, ignored till now.
"""

def load_rules():
    """Return rules sorted by priority."""
    conn = get_connection()
    rows = conn.execute("SELECT * FROM rules ORDER BY priority ASC").fetchall()
    conn.close()
    return rows

def test_rule(rule: dict, transaction: dict) -> bool:
    """Check if a single rule matches a transaction (row from DB)."""
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
    value = match_value.upper()

    if match_op == MatchOp.CONTAINS.value:
        return value in text
    elif match_op == MatchOp.STARTSWITH.value:
        return text.startswith(value)
    elif match_op == MatchOp.REGEX.value:
        try:
            return bool(re.search(match_value, text, re.IGNORECASE))
        except re.error:
            return False
    elif match_op == MatchOp.EQUALS.value:
        return text == value
    return False

def apply_rules(transaction_list=None):
    """
    Apply rules to all transactions (or a given list) and update categories.
    Only updates rows where category_src != 'manual'.
    Returns number of newly categorized rows.
    """
    rules = load_rules()
    with db_session(commit=True) as conn:
        if transaction_list is None:
            txns = conn.execute("""
                SELECT txn_id, description, bank, reference FROM transactions
                WHERE category IS NULL OR category_src != ?
            """, (CategorySource.MANUAL.value,)).fetchall()
        else:
            txns = transaction_list

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
    """Resets rule-assigned categories and re-applies all rules, then re-applies manual overrides."""
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
    """
    Categorize a single transaction, independent of any rule. Used by the
    Review tab's "just this transaction" option. Unlike a rule, this never
    applies to any other transaction, even one with an identical description.
    """
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
             category_type=None, source='manual'):
    with db_session() as conn:
        conn.execute("""
            INSERT INTO rules (priority, match_field, match_op, match_value, category, category_type, source)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (priority, match_field, match_op, match_value, category,
              category_type or CategoryType.UNSPECIFIED.value, source))
    # category_types remains the authoritative lookup used by export.py's
    # Income Summary (see the earlier discussion) — this INSERT just keeps
    # rules.category_type from silently sitting at its default too.
    if category_type:
        set_category_type(category, category_type)


def merge_default_rules():
    """
    Insert any rule from default_rules.json not already present (matched
    on match_field+match_op+match_value), leaving existing rules and
    manual edits untouched. Lets a non-technical user treat the JSON file
    as a living document: edit it, click 'Reload Defaults', and only new
    or changed entries get added.
    Returns the count of newly inserted rules.
    """
    definitions = _load_seed_rule_definitions()
    with db_session(commit=False) as conn:
        existing = conn.execute("SELECT match_field, match_op, match_value FROM rules").fetchall()
    existing_keys = {(r["match_field"], r["match_op"], r["match_value"].upper()) for r in existing}

    inserted = 0
    for r in definitions:
        key = (r["match_field"], r["match_op"], r["match_value"].upper())
        if key in existing_keys:
            continue
        add_rule(r["priority"], r["match_field"], r["match_op"], r["match_value"],
                  r["category"], category_type=r.get("category_type"), source='manual')
        inserted += 1
    logger.info(f"merge_default_rules: inserted {inserted} new rule(s)")
    return inserted

def get_override_priority():
    """
    Returns a priority number lower than every existing rule, so a rule
    created from the Review tab — which represents a specific, manually
    confirmed match on a real transaction — always outranks broader
    seeded rules (e.g. the generic NEFT/IMPS/UPI -> "Transfer" catch-alls).
    Appending at MAX(priority)+1 instead would put new rules *after* those
    catch-alls, where they'd never actually fire.
    """
    conn = get_connection()
    row = conn.execute("SELECT MIN(priority) as min_priority FROM rules").fetchone()
    conn.close()
    current_min = row["min_priority"] if row["min_priority"] is not None else 1
    return current_min - 1


def _load_seed_rule_definitions():
    """
    Load the base rule set from JSON instead of hardcoding it in Python, so
    non-developers can extend/localize merchant categorization without a
    code change.
    """
    try:
        with open(DEFAULT_RULES_FILE, "r", encoding="utf-8") as f:
            rules = json.load(f)
    except FileNotFoundError:
        logger.warning(
            f"Default rules file not found at {DEFAULT_RULES_FILE}; "
            "seeding only the payment-mode Transfer rules."
        )
        rules = []

    next_priority = max((r["priority"] for r in rules), default=0) + 1
    for i, mode in enumerate(PAYMENT_MODE_KEYWORDS):
        rules.append({
            "priority": next_priority + i,
            "match_field": "description",
            "match_op": MatchOp.CONTAINS.value,
            "match_value": mode,
            "category": "Transfer",
            "category_type": CategoryType.TRANSFER.value,
        })
    return rules


def seed_default_rules():
    for r in _load_seed_rule_definitions():
        add_rule(
            r["priority"], r["match_field"], r["match_op"], r["match_value"],
            r["category"], category_type=r.get("category_type"),
            source='manual',
        )