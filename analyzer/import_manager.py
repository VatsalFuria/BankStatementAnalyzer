from analyzer.database import db_session
from analyzer.parsers import discover_parsers, get_parser_for_file, get_parser_by_name
from analyzer.models import StandardTransaction
from analyzer.config import DEFAULT_ACCOUNT, DEFAULT_BANK_OVERRIDE
from analyzer.exceptions import ParserNotFoundError
from analyzer.logging_config import logger
import uuid
from typing import List, Optional

_parsers_loaded = False

def import_file(filepath: str, bank_override: str | None = None, account: str | None = None,
                 parser_name: Optional[str] = None) -> str:
    """
    parser_name: explicit choice from the GUI dropdown (or CLI). When
    given, that parser is used regardless of auto-detection — the user's
    choice is authoritative. When None, falls back to column-based
    auto-detection (used by main.py / test_import.py / any script that
    hasn't been updated to pass a parser_name).
    """
    global _parsers_loaded
    if account is None:
        account = DEFAULT_ACCOUNT
    if bank_override is None:
        bank_override = DEFAULT_BANK_OVERRIDE
    if not _parsers_loaded:
        discover_parsers()
        _parsers_loaded = True

    with db_session(commit=False) as conn:
        existing = conn.execute(
            "SELECT import_id FROM import_log WHERE filename=? AND bank=? AND account=?",
            (filepath, bank_override or "", account),
        ).fetchone()
    if existing:
        logger.info(f"File {filepath} already imported (import_id={existing['import_id']}). Skipping.")
        return existing["import_id"]

    if parser_name:
        parser = get_parser_by_name(parser_name)
        if not parser.can_parse(filepath):
            logger.warning(
                f"Parser '{parser_name}' was explicitly selected but its own "
                f"can_parse() check failed for {filepath} — proceeding anyway "
                f"since the user chose it explicitly."
            )
    else:
        parser = get_parser_for_file(filepath)
        if parser is None:
            raise ParserNotFoundError(
                f"No parser auto-detected for {filepath}. Please select one manually."
            )

    transactions: List[StandardTransaction] = parser.parse(filepath)
    skipped_rows = getattr(parser, "last_skipped_rows", [])
    if skipped_rows:
        logger.warning(f"{filepath}: {len(skipped_rows)} row(s) skipped due to parse errors: {skipped_rows}")

    if bank_override:
        for txn in transactions:
            txn.bank = bank_override
    for txn in transactions:
        txn.account = account

    import_id = str(uuid.uuid4())
    with db_session() as conn:
        cursor = conn.cursor()
        for txn in transactions:
            cursor.execute("""
                INSERT INTO transactions
                (import_id, bank, account, txn_date, description, amount, dr_cr,
                 balance, reference, payment_mode, source_file, source_row)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (import_id, txn.bank, txn.account, txn.txn_date, txn.description,
                  txn.amount, txn.dr_cr, txn.balance, txn.reference, txn.payment_mode,
                  txn.source_file, txn.source_row))
        cursor.execute("""
            INSERT INTO import_log (import_id, filename, bank, account, row_count)
            VALUES (?, ?, ?, ?, ?)
        """, (import_id, filepath, transactions[0].bank if transactions else bank_override,
              account, len(transactions)))

    logger.info(f"Imported {len(transactions)} transaction(s) from {filepath} (import_id={import_id})")
    return import_id