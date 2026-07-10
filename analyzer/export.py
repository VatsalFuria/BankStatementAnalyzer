import openpyxl
from openpyxl.utils import get_column_letter
from analyzer.database import db_session
from analyzer.constants import MatchStatus, CategoryType
from analyzer.logging_config import logger
from analyzer import repository


def get_export_summary():
    with db_session(commit=False) as conn:
        total_transactions = conn.execute("SELECT COUNT(*) AS count FROM transactions").fetchone()["count"]
        uncategorized = conn.execute(
            "SELECT COUNT(*) AS count FROM transactions WHERE category IS NULL OR category=''"
        ).fetchone()["count"]
        accepted_transfers = conn.execute(
            "SELECT COUNT(*) AS count FROM matches m JOIN transactions d ON m.debit_txn = d.txn_id JOIN transactions c ON m.credit_txn = c.txn_id WHERE m.status = ?",
            (MatchStatus.ACCEPTED.value,),
        ).fetchone()["count"]
        return {
            "total_transactions": total_transactions,
            "uncategorized": uncategorized,
            "accepted_transfers": accepted_transfers,
        }


def export_workbook(output_path: str):
    with db_session(commit=False) as conn:
        total_transactions = conn.execute("SELECT COUNT(*) AS count FROM transactions").fetchone()["count"]
        if total_transactions <= 0:
            raise ValueError("Nothing to export. Import at least one transaction first.")
        
    with db_session(commit=False) as conn:
        wb = openpyxl.Workbook()
        default_sheet = wb.active
        if default_sheet is not None:
            wb.remove(default_sheet)

        def add_sheet(title, query, params=None):
            ws = wb.create_sheet(title=title)
            rows = conn.execute(query, params or []).fetchall()
            if not rows:
                logger.warning(f"No data for sheet {title}. Skipping.")
                return
            headers = list(rows[0].keys())
            ws.append(headers)
            for row in rows:
                ws.append([row[h] for h in headers])

            # for col_idx, _ in enumerate(headers, 1):
            #     col_letter = get_column_letter(col_idx)
            #     max_length = max(len(str(row[col_idx-1])) for row in ws.iter_rows(min_row=1, values_only=True))
            #     ws.column_dimensions[col_letter].width = min(max_length + 2, 40)
            # ws.auto_filter.ref = ws.dimensions
            return ws

        add_sheet("Consolidated",
                "SELECT txn_id, import_id, bank, account, txn_date, description, amount, dr_cr, category, category_src, match_id " \
                "   FROM transactions ORDER BY txn_date DESC")

        banks = [row[0] for row in conn.execute("SELECT DISTINCT bank FROM transactions").fetchall()]
        for bank in banks:
            add_sheet(f"Bank - {bank}",
                    "SELECT *, " \
                    "CASE WHEN dr_cr='DR' THEN amount END AS debit, " \
                    "CASE WHEN dr_cr='CR' THEN amount END AS credit " \
                    "FROM transactions WHERE bank=? ORDER BY txn_date DESC",
                    (bank,))

        add_sheet("Self Transfers",
                """SELECT m.match_id, d.txn_date, d.amount, d.account AS from_account, c.account AS to_account,
                            d.description AS debit_desc, c.description AS credit_desc
                    FROM matches m
                    JOIN transactions d ON m.debit_txn = d.txn_id
                    JOIN transactions c ON m.credit_txn = c.txn_id
                    WHERE m.status = ?""",
                (MatchStatus.ACCEPTED.value,))

        # Income Summary now driven by rules.category_type instead of a
        # hardcoded category-name tuple: any rule tagged category_type='income'
        # is automatically included, no edit to this file needed.
        # add_sheet("Income Summary",
        #         """SELECT t.category, SUM(t.amount) as total
        #             FROM transactions t
        #             JOIN category_types ct ON t.category = ct.category
        #             WHERE t.dr_cr = 'CR' AND ct.category_type = ?
        #             GROUP BY t.category""",
        #         (CategoryType.INCOME_DEFAULT.value,))

        add_sheet("Uncategorized",
                "SELECT txn_id, bank, account, txn_date, description, amount, dr_cr " \
                "   FROM transactions " \
                "   WHERE category IS NULL OR category=''")

        add_sheet("Category Summary",
                "SELECT category, dr_cr, COUNT(*) as count, SUM(amount) as total " \
                "   FROM transactions " \
                "   WHERE category IS NOT NULL GROUP BY category, dr_cr")
        
        add_sheet("Category Type Summary",
                """SELECT ct.category_type, t.dr_cr, COUNT(*) as count, SUM(t.amount) as total
                    FROM transactions t
                    JOIN category_types ct ON t.category = ct.category
                    WHERE t.category IS NOT NULL AND t.category != ''
                    GROUP BY ct.category_type, t.dr_cr
                    ORDER BY ct.category_type, t.dr_cr""")

        wb.save(output_path)
        
        logger.info(f"Workbook saved to {output_path}")
        