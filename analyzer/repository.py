"""
Single place any UI (this GUI, a future CLI, a web view) goes for read
queries and simple status writes. Schema changes now only need updates
here, not hunted down across GUI files.
"""
from analyzer.database import db_session

def get_imported_files():
    with db_session(commit=False) as conn:
        return conn.execute("SELECT filename FROM import_log ORDER BY imported_at DESC").fetchall()

def get_uncategorized_transactions():
    with db_session(commit=False) as conn:
        return conn.execute("""
            SELECT txn_id, bank, account, txn_date, description, amount, dr_cr
            FROM transactions WHERE category IS NULL ORDER BY txn_date DESC
        """).fetchall()

def get_suggested_matches():
    with db_session(commit=False) as conn:
        return conn.execute("""
            SELECT m.match_id, d.txn_date, d.amount,
                   d.account AS from_acc, c.account AS to_acc,
                   d.description AS debit_desc, c.description AS credit_desc,
                   m.confidence, m.status, m.reason
            FROM matches m
            JOIN transactions d ON m.debit_txn = d.txn_id
            JOIN transactions c ON m.credit_txn = c.txn_id
            WHERE m.status = 'suggested'
            ORDER BY d.txn_date DESC
        """).fetchall()

def accept_match(match_id):
    with db_session() as conn:
        conn.execute("UPDATE matches SET status='accepted' WHERE match_id=?", (match_id,))

def reject_match(match_id):
    with db_session() as conn:
        conn.execute("UPDATE matches SET status='rejected' WHERE match_id=?", (match_id,))
        conn.execute("UPDATE transactions SET match_id=NULL WHERE match_id=?", (match_id,))

def get_transactions_display(limit=None):
    """Debit/Credit as two separate columns for display — see §6 below."""
    query = """
        SELECT txn_id, bank, account, txn_date, description,
               CASE WHEN dr_cr='DR' THEN amount END AS debit,
               CASE WHEN dr_cr='CR' THEN amount END AS credit,
               category
        FROM transactions ORDER BY txn_date DESC
    """
    if limit:
        query += f" LIMIT {int(limit)}"
    with db_session(commit=False) as conn:
        return conn.execute(query).fetchall()
    
def get_import_by_filename_and_account(filename, account):
    with db_session(commit=False) as conn:
        return conn.execute(
            "SELECT import_id FROM import_log WHERE filename=? AND account=?",
            (filename, account),
        ).fetchone()
    
def put_transactions(import_id, filename, account, transactions):
    with db_session() as conn:
        cursor = conn.cursor()
        txn_ids = []
        for txn in transactions:
            cursor.execute("""
                INSERT INTO transactions
                (import_id, bank, account, txn_date, description, amount, dr_cr,
                 balance, reference, payment_mode, source_file, source_row)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (import_id, txn.bank, txn.account, txn.txn_date, txn.description,
                  txn.amount, txn.dr_cr, txn.balance, txn.reference, txn.payment_mode,
                  txn.source_file, txn.source_row))
            txn_ids.append(cursor.lastrowid)
        cursor.execute("""
            INSERT INTO import_log (import_id, filename, bank, account, row_count)
            VALUES (?, ?, ?, ?, ?)
        """, (import_id, filename, transactions[0].bank, account, len(transactions)))
    return txn_ids