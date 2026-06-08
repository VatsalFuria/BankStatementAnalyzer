import re
from analyzer.database import get_connection

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
    # Get the field value from transaction
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

    if match_op == 'contains':
        return value in text
    elif match_op == 'startswith':
        return text.startswith(value)
    elif match_op == 'regex':
        try:
            return bool(re.search(match_value, text, re.IGNORECASE))
        except:
            return False
    elif match_op == 'equals':
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
        # apply to all uncategorized/rule-based
        txns = conn.execute("""
            SELECT txn_id, description, bank, reference FROM transactions
            WHERE category IS NULL OR category_src != 'manual'
        """).fetchall()
    else:
        txns = transaction_list  # expects list of dict-like with txn_id

    count = 0
    for txn in txns:
        for rule in rules:
            if test_rule(rule, txn):
                conn.execute("""
                    UPDATE transactions
                    SET category = ?, category_src = 'rule', rule_id = ?
                    WHERE txn_id = ?
                """, (rule['category'], rule['id'], txn['txn_id']))
                count += 1
                break  # first match wins
    conn.commit()
    conn.close()
    return count

def reapply_all_rules():
    """Resets rule-assigned categories and re-applies all rules, then re-applies manual overrides."""
    conn = get_connection()
    # reset rule-based categories
    conn.execute("UPDATE transactions SET category=NULL, category_src=NULL, rule_id=NULL WHERE category_src='rule'")
    conn.commit()
    conn.close()
    # re-apply rules
    apply_rules()
    # re-apply manual overrides
    apply_manual_overrides()

def apply_manual_overrides():
    conn = get_connection()
    overrides = conn.execute("SELECT txn_id, category FROM manual_overrides").fetchall()
    for ov in overrides:
        conn.execute("""
            UPDATE transactions
            SET category = ?, category_src = 'manual', rule_id = NULL
            WHERE txn_id = ?
        """, (ov['category'], ov['txn_id']))
    conn.commit()
    conn.close()

def add_rule(priority, match_field, match_op, match_value, category, source='manual'):
    conn = get_connection()
    conn.execute("""
        INSERT INTO rules (priority, match_field, match_op, match_value, category, source)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (priority, match_field, match_op, match_value, category, source))
    conn.commit()
    conn.close()

from analyzer.rule_engine import add_rule

def seed_default_rules():
    rules = [
        (1, 'description', 'contains', 'SALARY', 'Salary'),
        (2, 'description', 'contains', 'INT.PD', 'Savings Interest'),
        (3, 'description', 'contains', 'FD INT', 'FD Interest'),
        (4, 'description', 'contains', 'SWIGGY', 'Food'),
        (5, 'description', 'contains', 'ZOMATO', 'Food'),
        (6, 'description', 'contains', 'AMAZON', 'Shopping'),
        (7, 'description', 'contains', 'FLIPKART', 'Shopping'),
        (8, 'description', 'contains', 'NEFT', 'Transfer'),  # will be refined later
        (9, 'description', 'contains', 'IMPS', 'Transfer'),
        (10, 'description', 'contains', 'UPI', 'Transfer'),
    ]
    for r in rules:
        add_rule(*r, source='manual')