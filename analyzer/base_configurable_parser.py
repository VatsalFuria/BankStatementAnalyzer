import json
import pandas as pd

from analyzer.parsers.base_parser import BaseParser
from analyzer.models import StandardTransaction
from analyzer.constants import DrCr, PAYMENT_MODE_KEYWORDS


class ConfigurableExcelParser(BaseParser):
    """
    A parser driven entirely by a JSON column-mapping file. Adding a new
    bank, or handling a bank changing its column headers, becomes a matter
    of adding/editing a JSON file under analyzer/parsers/bank_formats/,
    not writing a new Python class.

    Subclasses just set `config_path` to their bank's JSON file.
    """
    config_path: str = None  # set by subclas

    def __init__(self):
        if self.config_path is None:
            raise NotImplementedError("Subclasses must set config_path")
        with open(self.config_path, "r", encoding="utf-8") as f:
            self.config = json.load(f)

    def can_parse(self, filepath: str) -> bool:
        exts = tuple(self.config.get("file_extensions", [".xlsx", ".xls"]))
        if not filepath.lower().endswith(exts):
            return False
        try:
            df = pd.read_excel(filepath, nrows=0)
            return self.config["detect_column"] in df.columns
        except Exception:
            return False

    def parse(self, filepath: str) -> list[StandardTransaction]:
        cols = self.config["columns"]
        bank_name = self.config["bank_name"]
        df = pd.read_excel(filepath)
        transactions = []
        for idx, row in df.iterrows():
            date = pd.to_datetime(row[cols["date"]]).strftime('%Y-%m-%d')
            desc = str(row[cols["description"]])

            ref_raw = row.get(cols.get("reference", ""), None)
            ref = str(ref_raw) if pd.notna(ref_raw) else ''

            withdraw = row.get(cols["withdrawal"], 0) or 0
            deposit = row.get(cols["deposit"], 0) or 0

            closing_raw = row.get(cols.get("balance", ""), None)
            closing = closing_raw if pd.notna(closing_raw) else None

            if withdraw > 0:
                amount = withdraw
                dr_cr = DrCr.DEBIT.value
            else:
                amount = deposit
                dr_cr = DrCr.CREDIT.value

            mode = None
            desc_upper = desc.upper()
            ref_upper = ref.upper()
            for keyword in PAYMENT_MODE_KEYWORDS:
                if keyword in desc_upper or keyword in ref_upper:
                    mode = keyword
                    break

            txn = StandardTransaction(
                bank=bank_name,
                account="",  # set later by import_manager from user input
                txn_date=date,
                description=desc,
                amount=float(amount),
                dr_cr=dr_cr,
                balance=float(closing) if closing else None,
                reference=ref,
                payment_mode=mode,
                source_file=filepath,
                source_row=idx + 2
            )
            transactions.append(txn)
        return transactions