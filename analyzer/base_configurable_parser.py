import pandas as pd
import json
from analyzer.parsers.base_parser import BaseParser
from analyzer.models import StandardTransaction
from analyzer.constants import DrCr
from analyzer.utils import parse_amount
from analyzer.exceptions import ParseError
from analyzer.logging_config import logger

class ConfigurableExcelParser(BaseParser):
    config_path: str | None = None

    def __init__(self):
        if self.config_path is None:
            raise NotImplementedError("Subclasses must set config_path")
        with open(self.config_path, "r", encoding="utf-8") as f:
            self.config = json.load(f)
        self.display_name = self.config.get("bank_name", type(self).__name__)
        # Most banks have a clean header at row 0 (default=1, i.e. only
        # look at row 0). Some export a logo/address/statement-period
        # block above the real header — set this higher in the JSON
        # config (e.g. 25) to scan further down for it.
        self.header_search_rows = self.config.get("header_search_rows", 1)
        # Indian bank exports commonly give dates as DD-MM-YYYY, which
        # pandas' default (US-style) parsing will silently swap for any
        # day <= 12. Set true in config when the source dates need it.
        self.date_dayfirst = self.config.get("date_dayfirst", False)

    def _find_header_row(self, filepath: str):
        """Return the 0-based row index (as pd.read_excel's `header=` arg
        expects) of the row containing detect_column, scanning up to
        header_search_rows rows. None if not found."""
        detect_column = self.config["detect_column"]
        preview = pd.read_excel(filepath, header=None, nrows=self.header_search_rows)
        for row_idx, row in preview.iterrows():
            values = [str(v).strip() if pd.notna(v) else "" for v in row]
            if detect_column in values:
                return row_idx
        return None

    def can_parse(self, filepath: str) -> bool:
        exts = tuple(self.config.get("file_extensions", [".xlsx"]))
        if not filepath.lower().endswith(exts):
            return False
        try:
            return self._find_header_row(filepath) is not None
        except Exception:
            logger.exception(f"can_parse failed for {filepath} using {self.display_name}")
            return False

    def parse(self, filepath: str) -> list[StandardTransaction]:
        cols = self.config["columns"]
        bank_name = self.config["bank_name"]

        header_row = self._find_header_row(filepath)
        if header_row is None:
            raise ParseError(
                f"Could not locate header row (looking for '{self.config['detect_column']}')",
                filepath=filepath,
            )

        df = pd.read_excel(filepath, header=header_row)
        # If the sheet repeats a header label (e.g. "Dr / Cr" for both the
        # transaction and the balance), pandas auto-suffixes the later
        # ones ("Dr / Cr", "Dr / Cr.1") — cols["dr_cr"] naturally binds to
        # the first (transaction) occurrence.

        use_amount_mode = "amount" in cols and "dr_cr" in cols
        transactions, skipped = [], []

        for idx, row in df.iterrows():
            row_num = header_row + idx + 2  # +1 header row, +1 for 1-indexing
            try:
                date_kwargs = {"dayfirst": True} if self.date_dayfirst else {}
                date = pd.to_datetime(row[cols["date"]], **date_kwargs).strftime('%Y-%m-%d')
                desc = str(row[cols["description"]])
                ref_raw = row.get(cols.get("reference", ""), None)
                ref = str(ref_raw) if pd.notna(ref_raw) else ''

                if use_amount_mode:
                    amount = parse_amount(row.get(cols["amount"]), filepath=filepath, row=row_num, column=cols["amount"])
                    dr_cr_raw = str(row.get(cols["dr_cr"], "")).strip().upper()

                    if amount == 0:
                        logger.info(f"Skipping row {row_num} in {filepath}: zero amount")
                        skipped.append((row_num, "Zero amount"))
                        continue
                    if dr_cr_raw not in (DrCr.DEBIT.value, DrCr.CREDIT.value):
                        logger.warning(f"Skipping row {row_num} in {filepath}: unrecognized Dr/Cr value '{dr_cr_raw}'")
                        skipped.append((row_num, f"Unrecognized Dr/Cr value '{dr_cr_raw}'"))
                        continue
                    dr_cr = dr_cr_raw
                else:
                    withdraw = parse_amount(row.get(cols["withdrawal"]), filepath=filepath, row=row_num, column=cols["withdrawal"])
                    deposit = parse_amount(row.get(cols["deposit"]), filepath=filepath, row=row_num, column=cols["deposit"])

                    if withdraw == 0 and deposit == 0:
                        # Likely an opening-balance / heading row, not a real
                        # transaction. Importing it as a 0.0 CR pollutes reports.
                        logger.info(f"Skipping row {row_num} in {filepath}: no withdrawal or deposit amount")
                        skipped.append((row_num, "No withdrawal or deposit amount"))
                        continue

                    amount = withdraw if withdraw > 0 else deposit
                    dr_cr = DrCr.DEBIT.value if withdraw > 0 else DrCr.CREDIT.value

                closing_raw = row.get(cols.get("balance", ""), None)
                closing = (parse_amount(closing_raw, filepath=filepath, row=row_num, column=cols.get("balance"))
                           if pd.notna(closing_raw) else None)

                mode = None
                transactions.append(StandardTransaction(
                    bank=bank_name, account="", txn_date=date, description=desc,
                    amount=float(amount), dr_cr=dr_cr,
                    balance=closing,
                    reference=ref, payment_mode=mode,
                    source_file=filepath, source_row=row_num,
                ))
            except ParseError as e:
                logger.warning(str(e))
                skipped.append((row_num, str(e)))
            except Exception as e:
                # Anything unexpected (bad date, missing column) is now
                # caught per-row instead of aborting the whole file.
                logger.warning(f"Skipping row {row_num} in {filepath}: {e}")
                skipped.append((row_num, str(e)))

        self.last_skipped_rows = skipped
        return transactions