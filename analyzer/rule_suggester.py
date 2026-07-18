"""
Mines uncategorized transactions for repeated keywords not covered by any
existing rule, and proposes candidate rules for the user to approve — the
same suggest-then-approve shape as transfer_matcher.find_transfers() /
the Transfers tab, but for rules. Nothing here writes to the rules table;
every suggestion goes through the same add_rule() the Rules tab and
Review tab already use, only after a human confirms the category.
"""
import re
from collections import Counter

from analyzer.database import db_session
from analyzer.config import RULE_SUGGESTION_MIN_OCCURRENCES
from analyzer.rule_engine import load_rules, test_rule

# Merchant-like words only — numbers and short reference fragments aren't
# useful rule anchors on their own.
_TOKEN_RE = re.compile(r"[A-Z]{3,}")
_STOPWORDS = {
    "THE", "AND", "FOR", "FROM", "WITH", "PAYMENT", "PAYMENTS",
    "TRANSACTION", "TRANSFER", "ORDER", "PURCHASE", "AMT", "REF", "TEST",
}


def _get_uncategorized():
    with db_session(commit=False) as conn:
        return conn.execute("""
            SELECT txn_id, description, dr_cr FROM transactions
            WHERE category IS NULL OR category=''
        """).fetchall()


def suggest_rules(min_occurrences: int = RULE_SUGGESTION_MIN_OCCURRENCES):
    """Returns suggestion dicts — {token, count, dr_cr, samples,
    suggested_category} — sorted by how many uncategorized transactions
    each would cover. dr_cr is None ('Any') unless one direction
    overwhelmingly dominates."""
    txns = _get_uncategorized()
    if not txns:
        return []

    rules = load_rules()
    token_hits = {}

    for txn in txns:
        text = (txn["description"] or "").upper()
        for token in set(_TOKEN_RE.findall(text)) - _STOPWORDS:
            entry = token_hits.setdefault(token, {"count": 0, "dr_cr": Counter(), "samples": []})
            entry["count"] += 1
            entry["dr_cr"][txn["dr_cr"]] += 1
            if len(entry["samples"]) < 3:
                entry["samples"].append(txn["description"])

    suggestions = []
    for token, info in token_hits.items():
        if info["count"] < min_occurrences:
            continue

        dominant_dr_cr, dominant_count = info["dr_cr"].most_common(1)[0]
        # Skip tokens an existing rule would already catch under this
        # dr_cr — avoids suggesting near-duplicates of a rule that's
        # simply scoped to the other direction or already broader.
        probe = {"description": token, "bank": "", "reference": "", "dr_cr": dominant_dr_cr}
        if any(test_rule(rule, probe) for rule in rules):
            continue

        dr_cr = dominant_dr_cr if dominant_count / info["count"] >= 0.9 else None
        suggestions.append({
            "token": token,
            "count": info["count"],
            "dr_cr": dr_cr,
            "samples": info["samples"],
            "suggested_category": token.title(),
        })

    suggestions.sort(key=lambda s: s["count"], reverse=True)
    return suggestions