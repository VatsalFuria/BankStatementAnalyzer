import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog, QTableWidget, QTableWidgetItem, QMessageBox
from analyzer.database import init_db, get_connection
from analyzer.import_manager import import_file
from analyzer.rule_engine import apply_rules, reapply_all_rules, add_rule
from analyzer.transfer_matcher import find_transfers
from analyzer.export import export_workbook
from analyzer.database import get_connection

class TransferTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout()

        self.refresh_btn = QPushButton("Refresh Transfer Suggestions")
        self.refresh_btn.clicked.connect(self.refresh)
        layout.addWidget(self.refresh_btn)

        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(
            ["Match ID", "Date", "Amount", "From Account", "To Account",
             "Confidence", "Action"]
        )
        layout.addWidget(self.table)

        self.setLayout(layout)
        self.refresh()

    def refresh(self):
        conn = get_connection()
        matches = conn.execute("""
            SELECT m.match_id, d.txn_date, d.amount,
                   d.account AS from_acc, c.account AS to_acc,
                   m.confidence, m.status
            FROM matches m
            JOIN transactions d ON m.debit_txn = d.txn_id
            JOIN transactions c ON m.credit_txn = c.txn_id
            WHERE m.status = 'suggested'
            ORDER BY d.txn_date DESC
        """).fetchall()
        self.table.setRowCount(len(matches))
        for i, match in enumerate(matches):
            self.table.setItem(i, 0, QTableWidgetItem(match["match_id"]))
            self.table.setItem(i, 1, QTableWidgetItem(match["txn_date"]))
            self.table.setItem(i, 2, QTableWidgetItem(str(match["amount"])))
            self.table.setItem(i, 3, QTableWidgetItem(match["from_acc"]))
            self.table.setItem(i, 4, QTableWidgetItem(match["to_acc"]))
            self.table.setItem(i, 5, QTableWidgetItem(str(match["confidence"]) + "%"))
            # Action buttons
            btn_accept = QPushButton("Accept")
            btn_reject = QPushButton("Reject")
            btn_accept.clicked.connect(lambda checked, m=match: self.accept_match(m["match_id"]))
            btn_reject.clicked.connect(lambda checked, m=match: self.reject_match(m["match_id"]))
            action_widget = QWidget()
            action_layout = QHBoxLayout()
            action_layout.addWidget(btn_accept)
            action_layout.addWidget(btn_reject)
            action_layout.setContentsMargins(0, 0, 0, 0)
            action_widget.setLayout(action_layout)
            self.table.setCellWidget(i, 6, action_widget)
        conn.close()

    def accept_match(self, match_id):
        conn = get_connection()
        conn.execute("UPDATE matches SET status='accepted' WHERE match_id=?", (match_id,))
        conn.commit()
        conn.close()
        self.refresh()

    def reject_match(self, match_id):
        conn = get_connection()
        conn.execute("UPDATE matches SET status='rejected' WHERE match_id=?", (match_id,))
        # Remove match_id from associated transactions so they can be matched later
        conn.execute("UPDATE transactions SET match_id=NULL WHERE match_id=?", (match_id,))
        conn.commit()
        conn.close()
        self.refresh()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Bank Statement Analyzer")
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.import_tab = ImportTab()
        self.tabs.addTab(self.import_tab, "Import")

        self.review_tab = ReviewTab()
        self.tabs.addTab(self.review_tab, "Review Uncategorized")

        self.transfer_tab = TransferTab()
        self.tabs.addTab(self.transfer_tab, "Transfers")

        self.export_btn = QPushButton("Export Workbook")
        self.export_btn.clicked.connect(self.export)
        self.tabs.addTab(self.export_btn, "Export")  # just a button in a tab

    def export(self):
        filepath, _ = QFileDialog.getSaveFileName(self, "Save Excel", "", "Excel Files (*.xlsx)")
        if filepath:
            export_workbook(filepath)
            QMessageBox.information(self, "Export", "Workbook exported successfully.")

class ImportTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout()
        self.btn = QPushButton("Import Statement File")
        self.btn.clicked.connect(self.import_file)
        layout.addWidget(self.btn)
        self.setLayout(layout)

    def import_file(self):
        filepath, _ = QFileDialog.getOpenFileName(self, "Select Statement", "", "Excel/CSV (*.xlsx *.csv)")
        if filepath:
            try:
                # For simplicity, assume bank name from file or user input; you can add dropdowns
                import_file(filepath, bank_override="HDFC", account="Savings")
                apply_rules()  # categorize after import
                QMessageBox.information(self, "Import", "File imported and categorized.")
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

class ReviewTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout()
        self.table = QTableWidget()
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh)
        layout.addWidget(self.refresh_btn)
        layout.addWidget(self.table)
        self.setLayout(layout)
        self.refresh()

    def refresh(self):
        conn = get_connection()
        rows = conn.execute("SELECT txn_id, bank, account, txn_date, description, amount, dr_cr FROM transactions WHERE category IS NULL ORDER BY txn_date DESC").fetchall()
        self.table.setRowCount(len(rows))
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(["ID", "Bank", "Account", "Date", "Description", "Amount", "DR/CR"])
        for i, row in enumerate(rows):
            for j, key in enumerate(row.keys()):
                self.table.setItem(i, j, QTableWidgetItem(str(row[key])))
        conn.close()

# Simplified TransferTab left as exercise; would show matches and allow Accept/Reject.

if __name__ == "__main__":
    init_db()
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())