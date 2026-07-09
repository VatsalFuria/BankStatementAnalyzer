import uuid

from analyzer.database import get_connection
from analyzer.config import DEFAULT_AMOUNT_TOLERANCE, CONFIDENCE_FULL_MATCH, CONFIDENCE_PARTIAL_MATCH
from analyzer.constants import DrCr, MatchStatus


def find_transfers(new_import_id: str = None, amount_tolerance: float = None):
    """
    Find self-transfer pairs across different accounts.
    Matches: same date, same amount (within tolerance), opposite sign (DR vs CR),
    optional payment_mode match (if both present).
    A debit can match at most one credit.
    """
    if amount_tolerance is None:
        amount_tolerance = DEFAULT_AMOUNT_TOLERANCE

    conn = get_connection()
    if new_import_id:
        debits = conn.execute("""
            SELECT txn_id, account, txn_date, amount, payment_mode, description
            FROM transactions
            WHERE dr_cr=? AND import_id=? AND match_id IS NULL
        """, (DrCr.DEBIT.value, new_import_id)).fetchall()
        credits = conn.execute("""
            SELECT txn_id, account, txn_date, amount, payment_mode, description
            FROM transactions
            WHERE dr_cr=? AND import_id=? AND match_id IS NULL
        """, (DrCr.CREDIT.value, new_import_id)).fetchall()
    else:
        debits = conn.execute(
            "SELECT txn_id, account, txn_date, amount, payment_mode, description FROM transactions WHERE dr_cr=? AND match_id IS NULL",
            (DrCr.DEBIT.value,),
        ).fetchall()
        credits = conn.execute(
            "SELECT txn_id, account, txn_date, amount, payment_mode, description FROM transactions WHERE dr_cr=? AND match_id IS NULL",
            (DrCr.CREDIT.value,),
        ).fetchall()

    matched_credits = set()
    candidates = []

    for d in debits:
        if d['txn_id'] in matched_credits:
            continue
        for c in credits:
            if c['txn_id'] in matched_credits:
                continue
            if d['account'] == c['account']:
                continue

            if d['txn_date'] != c['txn_date']:
                continue
            if abs(d['amount'] - c['amount']) > amount_tolerance:
                continue

            if d['payment_mode'] and c['payment_mode'] and d['payment_mode'] != c['payment_mode']:
                continue

            confidence = CONFIDENCE_FULL_MATCH
            if not (d['payment_mode'] and c['payment_mode']):
                confidence = CONFIDENCE_PARTIAL_MATCH

            match_id = str(uuid.uuid4())
            conn.execute("""
                INSERT INTO matches (match_id, debit_txn, credit_txn, confidence, status)
                VALUES (?, ?, ?, ?, ?)
            """, (match_id, d['txn_id'], c['txn_id'], confidence, MatchStatus.SUGGESTED.value))

            conn.execute("UPDATE transactions SET match_id=? WHERE txn_id=?", (match_id, d['txn_id']))
            conn.execute("UPDATE transactions SET match_id=? WHERE txn_id=?", (match_id, c['txn_id']))

            matched_credits.add(c['txn_id'])
            candidates.append({
                'match_id': match_id,
                'debit': d,
                'credit': c,
                'confidence': confidence
            })
            break

    conn.commit()
    conn.close()
    return candidates