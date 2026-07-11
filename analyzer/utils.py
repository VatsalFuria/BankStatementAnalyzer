import os
import re
from analyzer.exceptions import ParseError

_AMOUNT_CLEAN_RE = re.compile(r"[^\d.\-]")

def parse_amount(raw, *, filepath=None, row=None, column=None) -> float:
    """
    Coerce a spreadsheet cell into a float, tolerating the messy formats
    real bank exports use: currency symbols (₹, Rs., $), thousands
    separators ("1,200.00"), accounting-style negatives "(500.00)",
    blank/NaN cells, and stray whitespace.

    Raises ParseError (with file/row/column context) instead of letting
    a bare TypeError/ValueError escape to a generic QMessageBox.
    """
    if raw is None:
        return 0.0
    if isinstance(raw, (int, float)):
        return 0.0 if raw != raw else float(raw)  # `raw != raw` catches NaN

    text = str(raw).strip()
    if text == "" or text.lower() in ("nan", "none", "-"):
        return 0.0

    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]

    cleaned = _AMOUNT_CLEAN_RE.sub("", text)
    if cleaned in ("", "-", "."):
        raise ParseError(f"Could not interpret '{raw}' as a number",
                          filepath=filepath, row=row, column=column)
    try:
        value = float(cleaned)
    except ValueError as e:
        raise ParseError(f"Could not interpret '{raw}' as a number",
                          filepath=filepath, row=row, column=column) from e

    return -value if negative else value


def guess_import_defaults(filepath: str, parser_names: list[str]):
    """Guess account and parser for file, based on filename. (filepath)
    Assume default format to be AccountHolderName_BankName_FY25-26.xlsx
    AccountHolderName -> default_account
    BankName for parser, if in parser list."""

    filename = os.path.splitext(os.path.basename(filepath))[0]
    parts = filename.split("_")
    if len(parts) < 2:
        return None, None
    account = parts[0].strip()
    bank_lower = parts[1].strip().lower()
    parser = None
    for name in parser_names:
        if bank_lower in name.lower() or name.lower() in bank_lower:
            parser = name
            break
    return account, parser