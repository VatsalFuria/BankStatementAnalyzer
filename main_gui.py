import sys
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QTabWidget,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QFileDialog,
    QTableWidget,
    QTableWidgetItem,
    QMessageBox,
    QLabel,
    QListWidget,
)
from analyzer.database import init_db, get_connection, reset_database
from analyzer.import_manager import import_file
from analyzer.rule_engine import apply_rules
from analyzer.export import export_workbook, get_export_summary


def make_button(text, width=None, height=34):
    button = QPushButton(text)
    button.setMinimumHeight(height)
    if width is not None:
        button.setMinimumWidth(width)
    return button


class TransferTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        top_row = QHBoxLayout()
        top_row.addStretch()
        self.refresh_btn = make_button("Refresh Transfer Suggestions", width=220)
        self.refresh_btn.clicked.connect(self.refresh)
        top_row.addWidget(self.refresh_btn)
        layout.addLayout(top_row)

        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(
            ["Match ID", "Date", "Amount", "From Account", "To Account", "Confidence", "Action"]
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.table)

        self.refresh()

    def refresh(self):
        conn = get_connection()
        matches = conn.execute(
            """
            SELECT m.match_id, d.txn_date, d.amount,
                   d.account AS from_acc, c.account AS to_acc,
                   m.confidence, m.status
            FROM matches m
            JOIN transactions d ON m.debit_txn = d.txn_id
            JOIN transactions c ON m.credit_txn = c.txn_id
            WHERE m.status = 'suggested'
            ORDER BY d.txn_date DESC
            """
        ).fetchall()
        self.table.setRowCount(len(matches))
        for i, match in enumerate(matches):
            self.table.setItem(i, 0, QTableWidgetItem(match["match_id"]))
            self.table.setItem(i, 1, QTableWidgetItem(match["txn_date"]))
            self.table.setItem(i, 2, QTableWidgetItem(str(match["amount"])))
            self.table.setItem(i, 3, QTableWidgetItem(match["from_acc"]))
            self.table.setItem(i, 4, QTableWidgetItem(match["to_acc"]))
            self.table.setItem(i, 5, QTableWidgetItem(str(match["confidence"]) + "%"))

            btn_accept = make_button("Accept", width=80, height=28)
            btn_reject = make_button("Reject", width=80, height=28)
            btn_accept.clicked.connect(lambda checked, m=match: self.accept_match(m["match_id"]))
            btn_reject.clicked.connect(lambda checked, m=match: self.reject_match(m["match_id"]))

            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(0, 0, 0, 0)
            action_layout.setSpacing(6)
            action_layout.addWidget(btn_accept)
            action_layout.addWidget(btn_reject)
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
        conn.execute("UPDATE transactions SET match_id=NULL WHERE match_id=?", (match_id,))
        conn.commit()
        conn.close()
        self.refresh()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Bank Statement Analyzer")
        self.resize(1100, 700)
        self.setMinimumSize(900, 600)

        self.setStyleSheet(
            """
            QPushButton {
                min-height: 34px;
                min-width: 140px;
                padding: 6px 12px;
                color: #1f2937;
                border: 1px solid #bfc8d3;
                border-radius: 6px;
                background-color: #f3f4f6;
            }
            QPushButton:hover {
                background-color: #e0ebff;
                color: #111827;
            }
            QPushButton:pressed {
                background-color: #cfe0ff;
            }
            QTabBar::tab {
                min-height: 28px;
                padding: 6px 12px;
            }
            QTableWidget {
                gridline-color: #d0d0d0;
            }
            """
        )

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        self.import_tab = ImportTab()
        self.tabs.addTab(self.import_tab, "Import")

        self.review_tab = ReviewTab()
        self.tabs.addTab(self.review_tab, "Review Uncategorized")

        self.transfer_tab = TransferTab()
        self.tabs.addTab(self.transfer_tab, "Transfers")

        self.export_tab = QWidget()
        export_layout = QVBoxLayout(self.export_tab)
        export_layout.setContentsMargins(16, 16, 16, 16)
        export_layout.setSpacing(16)
        export_label = QLabel("Export your categorized workbook when you're ready.")
        export_label.setAlignment(Qt.AlignCenter)
        export_layout.addWidget(export_label)

        self.summary_label = QLabel()
        self.summary_label.setAlignment(Qt.AlignCenter)
        self.summary_label.setStyleSheet("font-weight: 600;")
        export_layout.addWidget(self.summary_label)
        self.update_export_summary()

        button_row = QHBoxLayout()
        button_row.addStretch()
        self.export_btn = make_button("Export Workbook", width=220, height=40)
        self.export_btn.clicked.connect(self.export)
        button_row.addWidget(self.export_btn)
        button_row.addStretch()
        export_layout.addLayout(button_row)
        export_layout.addStretch()
        self.tabs.addTab(self.export_tab, "Export")

    def export(self):
        summary = get_export_summary()
        if summary["total_transactions"] <= 0:
            QMessageBox.warning(self, "Export blocked", "Nothing to export yet. Import at least one statement first.")
            return

        filepath, _ = QFileDialog.getSaveFileName(self, "Save Excel", "", "Excel Files (*.xlsx)")
        if filepath:
            try:
                export_workbook(filepath)
                self.update_export_summary()
                QMessageBox.information(self, "Export", "Workbook exported successfully.")
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def update_export_summary(self):
        summary = get_export_summary()
        self.summary_label.setText(
            f"{summary['total_transactions']} transactions • {summary['uncategorized']} uncategorized • {summary['accepted_transfers']} accepted transfers"
        )


class ImportTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        intro = QLabel("Import one or more bank statement files and categorize them automatically.")
        intro.setAlignment(Qt.AlignCenter)
        layout.addWidget(intro)

        button_row = QHBoxLayout()
        button_row.addStretch()
        self.btn = make_button("Import Statement Files", width=240, height=40)
        self.btn.clicked.connect(self.import_file)
        button_row.addWidget(self.btn)
        button_row.addStretch()
        layout.addLayout(button_row)

        action_row = QHBoxLayout()
        self.reset_btn = make_button("Reset Database", width=180, height=34)
        self.reset_btn.clicked.connect(self.reset_database)
        action_row.addStretch()
        action_row.addWidget(self.reset_btn)
        action_row.addStretch()
        layout.addLayout(action_row)

        self.file_list_label = QLabel("Imported files")
        self.file_list_label.setStyleSheet("font-weight: 600;")
        layout.addWidget(self.file_list_label)

        self.file_list = QListWidget()
        self.file_list.setMaximumHeight(180)
        self.file_list.setAlternatingRowColors(True)
        layout.addWidget(self.file_list)
        layout.addStretch()

        self.refresh_imported_files()

    def import_file(self):
        filepaths, _ = QFileDialog.getOpenFileNames(self, "Select Statements", "", "Excel/CSV (*.xlsx *.csv)")
        if not filepaths:
            return

        try:
            for filepath in filepaths:
                import_file(filepath, bank_override="HDFC", account="Savings")
            apply_rules()
            self.refresh_imported_files()
            QMessageBox.information(self, "Import", f"Imported {len(filepaths)} file(s) and categorized them.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def refresh_imported_files(self):
        self.file_list.clear()
        conn = get_connection()
        rows = conn.execute("SELECT filename FROM import_log ORDER BY imported_at DESC").fetchall()
        conn.close()

        if not rows:
            self.file_list.addItem("No files imported yet")
            return

        for row in rows:
            self.file_list.addItem(row["filename"])

    def reset_database(self):
        confirm = QMessageBox.question(
            self,
            "Reset database",
            "This will remove all imported transactions, import history, matches, and rules. Continue?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return

        remove_files = QMessageBox.question(
            self,
            "Remove input files",
            "Also delete Excel/CSV files from the InputStatements folder?",
            QMessageBox.Yes | QMessageBox.No,
        ) == QMessageBox.Yes

        try:
            reset_database(remove_files=remove_files)
            self.refresh_imported_files()
            QMessageBox.information(self, "Reset complete", "Database cleared successfully.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))


class ReviewTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        header_row = QHBoxLayout()
        title = QLabel("Uncategorized Transactions")
        title.setStyleSheet("font-size: 11pt; font-weight: 600;")
        header_row.addWidget(title)
        header_row.addStretch()
        self.refresh_btn = make_button("Refresh", width=100)
        self.refresh_btn.clicked.connect(self.refresh)
        header_row.addWidget(self.refresh_btn)
        layout.addLayout(header_row)

        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.table)
        self.refresh()

    def refresh(self):
        conn = get_connection()
        rows = conn.execute(
            "SELECT txn_id, bank, account, txn_date, description, amount, dr_cr FROM transactions WHERE category IS NULL ORDER BY txn_date DESC"
        ).fetchall()
        self.table.setRowCount(len(rows))
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(["ID", "Bank", "Account", "Date", "Description", "Amount", "DR/CR"])
        self.table.horizontalHeader().setStretchLastSection(True)
        for i, row in enumerate(rows):
            for j, key in enumerate(row.keys()):
                self.table.setItem(i, j, QTableWidgetItem(str(row[key])))
        conn.close()


if __name__ == "__main__":
    init_db()
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())