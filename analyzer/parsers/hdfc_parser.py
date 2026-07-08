import pandas as pd
from analyzer.parsers.base_parser import BaseParser
from analyzer.models import StandardTransaction

class HDFCParser(BaseParser):
    def can_parse(self, filepath: str) -> bool:
        # Heuristic: file name contains 'hdfc' or first sheet has column 'Narration'
        if not filepath.lower().endswith(('.xlsx', '.xls')):
            return False
        try:
            df = pd.read_excel(filepath, nrows=0)
            return 'Narration' in df.columns
        except:
            return False

    def parse(self, filepath: str) -> list[StandardTransaction]:
        df = pd.read_excel(filepath)
        transactions = []
        for idx, row in df.iterrows():
            
            date = pd.to_datetime(row['Date']).strftime('%Y-%m-%d')
            desc = str(row['Narration'])
            ref = str(row.get('Chq./Ref.No.', '')) if pd.notna(row.get('Chq./Ref.No.')) else ''
            withdraw = row.get('Withdrawal Amt.', 0) or 0
            deposit = row.get('Deposit Amt.', 0) or 0
            closing = row.get('Closing Balance', None) if pd.notna(row.get('Closing Balance')) else None

            if withdraw > 0:
                amount = withdraw
                dr_cr = 'DR'
            else:
                amount = deposit
                dr_cr = 'CR'

            # Attempt to extract payment mode from narration or reference
            mode = None
            desc_upper = desc.upper()
            if 'NEFT' in desc_upper or 'NEFT' in ref.upper():
                mode = 'NEFT'
            elif 'IMPS' in desc_upper or 'IMPS' in ref.upper():
                mode = 'IMPS'
            elif 'UPI' in desc_upper:
                mode = 'UPI'

            txn = StandardTransaction(
                bank='HDFC',
                account='Savings',  # you'll eventually let user specify per import
                txn_date=date,
                description=desc,
                amount=float(amount),
                dr_cr=dr_cr,
                balance=float(closing) if closing else None,
                reference=ref,
                payment_mode=mode,
                source_file=filepath,
                source_row=idx+2  # excel rows (header in row1)
            )
            transactions.append(txn)
        return transactions