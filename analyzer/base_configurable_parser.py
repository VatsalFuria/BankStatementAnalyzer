import pandas as pd
import json
from analyzer.parsers.base_parser import BaseParser
from analyzer.models import StandardTransaction
from analyzer.constants import DrCr, PAYMENT_MODE_KEYWORDS
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

    def can_parse(self, filepath: str) -> bool:
        exts = tuple(self.config.get("file_extensions", [".xlsx"]))
        if not filepath.lower().endswith(exts):
            return False
        try:
            df = pd.read_excel(filepath, nrows=0)
            return self.config["detect_column"] in df.columns
        except Exception:
            logger.exception(f"can_parse failed for {filepath} using {self.display_name}")
            return False

    def parse(self, filepath: str) -> list[StandardTransaction]:
        cols = self.config["columns"]
        bank_name = self.config["bank_name"]
        df = pd.read_excel(filepath)
        transactions, skipped = [], []

        for idx, row in df.iterrows():
            row_num = idx + 2
            try:
                date = pd.to_datetime(row[cols["date"]]).strftime('%Y-%m-%d')
                desc = str(row[cols["description"]])
                ref_raw = row.get(cols.get("reference", ""), None)
                ref = str(ref_raw) if pd.notna(ref_raw) else ''

                withdraw = parse_amount(row.get(cols["withdrawal"]), filepath=filepath, row=row_num, column=cols["withdrawal"])
                deposit = parse_amount(row.get(cols["deposit"]), filepath=filepath, row=row_num, column=cols["deposit"])

                if withdraw == 0 and deposit == 0:
                    # Likely an opening-balance / heading row, not a real
                    # transaction. Importing it as a 0.0 CR pollutes reports.
                    logger.info(f"Skipping row {row_num} in {filepath}: no withdrawal or deposit amount")
                    skipped.append((row_num, "No withdrawal or deposit amount"))
                    continue

                closing_raw = row.get(cols.get("balance", ""), None)
                closing = closing_raw if pd.notna(closing_raw) else None

                amount = withdraw if withdraw > 0 else deposit
                dr_cr = DrCr.DEBIT.value if withdraw > 0 else DrCr.CREDIT.value

                mode = None
                desc_upper, ref_upper = desc.upper(), ref.upper()
                for keyword in PAYMENT_MODE_KEYWORDS:
                    if keyword in desc_upper or keyword in ref_upper:
                        mode = keyword
                        break

                transactions.append(StandardTransaction(
                    bank=bank_name, account="", txn_date=date, description=desc,
                    amount=float(amount), dr_cr=dr_cr,
                    balance=float(closing) if closing else None,
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