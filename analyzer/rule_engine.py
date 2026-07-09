import json
import re

from analyzer.database import get_connection
from analyzer.config import DEFAULT_RULES_FILE
from analyzer.constants import MatchOp, CategorySource, CategoryType, PAYMENT_MODE_KEYWORDS
from analyzer.categories import set_category_type


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
    conn = get_connection()
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
    conn.commit()
    conn.close()
    return count

def reapply_all_rules():
    """Resets rule-assigned categories and re-applies all rules, then re-applies manual overrides."""
    conn = get_connection()
    conn.execute(
        "UPDATE transactions SET category=NULL, category_src=NULL, rule_id=NULL WHERE category_src=?",
        (CategorySource.RULE.value,),
    )
    conn.commit()
    conn.close()
    apply_rules()
    apply_manual_overrides()

def apply_manual_overrides():
    conn = get_connection()
    overrides = conn.execute("SELECT txn_id, category FROM manual_overrides").fetchall()
    for ov in overrides:
        conn.execute("""
            UPDATE transactions
            SET category = ?, category_src = ?, rule_id = NULL
            WHERE txn_id = ?
        """, (ov['category'], CategorySource.MANUAL.value, ov['txn_id']))
    conn.commit()
    conn.close()

def add_manual_override(txn_id: int, category: str, category_type: str = None, reason: str = None):
    """
    Categorize a single transaction, independent of any rule. Used by the
    Review tab's "just this transaction" option. Unlike a rule, this never
    applies to any other transaction, even one with an identical description.
    """
    conn = get_connection()
    conn.execute("""
        INSERT INTO manual_overrides (txn_id, category, reason)
        VALUES (?, ?, ?)
        ON CONFLICT(txn_id) DO UPDATE SET category=excluded.category, reason=excluded.reason
    """, (txn_id, category, reason))
    conn.commit()
    conn.close()
    apply_manual_overrides()

    if category_type:
        set_category_type(category, category_type)

def add_rule(priority, match_field, match_op, match_value, category,
             category_type=None, source='manual'):
    """
    category_type is optional: when given, it also (up)sets the category's
    entry in category_types (analyzer/categories.py), so reporting (e.g.
    Income Summary) recognizes this category regardless of whether future
    transactions reach it via this rule or via a manual override.
    """
    conn = get_connection()
    conn.execute("""
        INSERT INTO rules (priority, match_field, match_op, match_value, category, source)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (priority, match_field, match_op, match_value, category, source))
    conn.commit()
    conn.close()

    if category_type:
        set_category_type(category, category_type)

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