from dataclasses import dataclass
from typing import Optional
import sqlite3

@dataclass
class StandardTransaction:
    """Canonical transaction format produced by all parsers."""
    bank: str
    account: str
    txn_date: str           # YYYY-MM-DD
    description: str
    amount: float           # always positive
    dr_cr: str              # 'DR' or 'CR'
    balance: Optional[float] = None
    reference: Optional[str] = None
    payment_mode: Optional[str] = None  # e.g., NEFT, IMPS, UPI
    source_file: Optional[str] = None
    source_row: Optional[int] = None
    # These will be set later during processing
    category: Optional[str] = None
    category_src: Optional[str] = None  # 'rule' or 'manual'
    rule_id: Optional[int] = None
    match_id: Optional[str] = None
    import_id: Optional[str] = None