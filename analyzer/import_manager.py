import uuid
import pandas as pd
from analyzer.database import get_connection
from analyzer.parsers import discover_parsers, get_parser_for_file
from analyzer.models import StandardTransaction
from typing import List

def import_file(filepath: str, bank_override: str = None, account: str = "Default") -> str:
    """
    Imports a statement file. Returns import_id.
    Raises ValueError if no parser found.
    """
    # Ensure parsers are discovered
    if not hasattr(import_file, "_parsers_loaded"):
        discover_parsers()
        import_file._parsers_loaded = True

    conn = get_connection()
    # Check if file already imported (by exact filename)
    existing = conn.execute("SELECT import_id FROM import_log WHERE filename=? AND bank=? AND account=?",
                            (filepath, bank_override or "", account)).fetchone()
    if existing:
        print(f"File {filepath} already imported. Skipping.")
        return existing["import_id"]

    parser = get_parser_for_file(filepath)
    if parser is None:
        raise ValueError(f"No parser found for file: {filepath}")

    transactions: List[StandardTransaction] = parser.parse(filepath)
    if bank_override:
        for txn in transactions:
            txn.bank = bank_override
    for txn in transactions:
        txn.account = account

    import_id = str(uuid.uuid4())
    cursor = conn.cursor()
    # Insert into DB
    for txn in transactions:
        cursor.execute("""
            INSERT INTO transactions
            (import_id, bank, account, txn_date, description, amount, dr_cr,
             balance, reference, payment_mode, source_file, source_row)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            import_id, txn.bank, txn.account, txn.txn_date, txn.description,
            txn.amount, txn.dr_cr, txn.balance, txn.reference, txn.payment_mode,
            txn.source_file, txn.source_row
        ))

    # Log import
    cursor.execute("""
        INSERT INTO import_log (import_id, filename, bank, account, row_count)
        VALUES (?, ?, ?, ?, ?)
    """, (import_id, filepath, transactions[0].bank if transactions else bank_override, account, len(transactions)))

    conn.commit()
    conn.close()
    print(f"Imported {len(transactions)} transactions from {filepath} (import_id: {import_id})")
    return import_id