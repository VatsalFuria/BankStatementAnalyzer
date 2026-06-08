import uuid
from analyzer.database import get_connection

def find_transfers(new_import_id: str = None, amount_tolerance: float = 1.0):
    """
    Find self-transfer pairs across different accounts.
    Matches: same date, same amount (within tolerance), opposite sign (DR vs CR),
    optional payment_mode match (if both present).
    A debit can match at most one credit.
    """
    conn = get_connection()
    # Select debits and credits from all transactions (or only from latest import if specified)
    if new_import_id:
        debits = conn.execute("""
            SELECT txn_id, account, txn_date, amount, payment_mode, description
            FROM transactions
            WHERE dr_cr='DR' AND import_id=?
        """, (new_import_id,)).fetchall()
        credits = conn.execute("""
            SELECT txn_id, account, txn_date, amount, payment_mode, description
            FROM transactions
            WHERE dr_cr='CR' AND import_id=?
        """, (new_import_id,)).fetchall()
    else:
        debits = conn.execute("SELECT txn_id, account, txn_date, amount, payment_mode, description FROM transactions WHERE dr_cr='DR'").fetchall()
        credits = conn.execute("SELECT txn_id, account, txn_date, amount, payment_mode, description FROM transactions WHERE dr_cr='CR'").fetchall()

    matched_credits = set()
    candidates = []

    for d in debits:
        if d['txn_id'] in matched_credits:
            continue
        for c in credits:
            if c['txn_id'] in matched_credits:
                continue
            if d['account'] == c['account']:
                continue  # must be different accounts

            if d['txn_date'] != c['txn_date']:
                continue
            if abs(d['amount'] - c['amount']) > amount_tolerance:
                continue

            # Payment mode: if both have a mode and they differ, skip
            if d['payment_mode'] and c['payment_mode'] and d['payment_mode'] != c['payment_mode']:
                continue

            confidence = 100
            if not (d['payment_mode'] and c['payment_mode']):
                confidence = 90  # mode missing on one side

            match_id = str(uuid.uuid4())
            # Insert into matches
            conn.execute("""
                INSERT INTO matches (match_id, debit_txn, credit_txn, confidence, status)
                VALUES (?, ?, ?, ?, 'suggested')
            """, (match_id, d['txn_id'], c['txn_id'], confidence))

            # Update transactions with match_id
            conn.execute("UPDATE transactions SET match_id=? WHERE txn_id=?", (match_id, d['txn_id']))
            conn.execute("UPDATE transactions SET match_id=? WHERE txn_id=?", (match_id, c['txn_id']))

            matched_credits.add(c['txn_id'])
            candidates.append({
                'match_id': match_id,
                'debit': d,
                'credit': c,
                'confidence': confidence
            })
            break  # debit matched, move to next debit

    conn.commit()
    conn.close()
    return candidates