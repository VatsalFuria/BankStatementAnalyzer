import json
import re

from analyzer.database import get_connection, db_session
from analyzer.config import DEFAULT_RULES_FILE
from analyzer.constants import MatchOp, CategorySource, CategoryType
from analyzer.categories import set_category_type
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

def test_rule(rule: dict, transaction: dict) -> bool:
    """Check if a single rule matches a transaction (row from DB)."""
    # dr_cr is checked first: a rule scoped to DR or CR shouldn't even
    # look at description/reference text if the direction doesn't match.
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
    rule to only that direction (see constants.DrCr)."""
    with db_session() as conn:
        conn.execute("""
            INSERT INTO rules (priority, match_field, match_op, match_value, category, category_type, source, dr_cr)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (priority, match_field, match_op, match_value, category,
              category_type or CategoryType.UNSPECIFIED.value, source, dr_cr or None))
    if category_type:
        set_category_type(category, category_type)


# def merge_default_rules():
#     """
#     NOTE: dedup key intentionally stays (match_field, match_op, match_value)
#     — NOT including dr_cr. If it included dr_cr, tightening an existing
#     default rule's dr_cr in default_rules.json would create a *second*,
#     near-duplicate rule alongside the old one already in someone's DB,
#     rather than just being skipped. This keeps the existing "leave
#     existing rules untouched" guarantee intact.
#     """
#     definitions = _load_seed_rule_definitions()
#     with db_session(commit=False) as conn:
#         existing = conn.execute("SELECT match_field, match_op, match_value FROM rules").fetchall()
#     existing_keys = {(r["match_field"], r["match_op"], r["match_value"].upper()) for r in existing}

#     inserted = 0
#     for r in definitions:
#         key = (r["match_field"], r["match_op"], r["match_value"].upper())
#         if key in existing_keys:
#             continue
#         add_rule(r["priority"], r["match_field"], r["match_op"], r["match_value"],
#                   r["category"], category_type=r.get("category_type"),
#                   source='manual', dr_cr=r.get("dr_cr"))
#         inserted += 1
#     logger.info(f"merge_default_rules: inserted {inserted} new rule(s)")
#     return inserted

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