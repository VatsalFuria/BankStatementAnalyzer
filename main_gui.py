import sys, os
from PySide6.QtCore import Qt, Signal, QThread, QObject
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QTabWidget,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QPushButton,
    QFileDialog,
    QInputDialog,
    QTableWidget,
    QTableWidgetItem,
    QMessageBox,
    QLabel,
    QListWidget,
    QDialog,
    QComboBox,
    QLineEdit,
    QRadioButton,
    QButtonGroup,
    QDialogButtonBox,
    QAbstractItemView,
    QProgressDialog,
)
from analyzer.rule_engine import (
    apply_rules,
    add_rule,
    add_manual_override,
    get_override_priority,
    seed_default_rules,
    merge_default_rules,
)
from analyzer.database import init_db, get_connection, reset_database
from analyzer.transfer_matcher import find_transfers
from analyzer.import_manager import import_file
from analyzer.export import export_workbook, get_export_summary
from analyzer.categories import get_existing_categories
from analyzer.constants import CategoryType, MatchOp
from analyzer.config import DEFAULT_ACCOUNT
from analyzer.exceptions import BSAError
from analyzer.logging_config import logger
from analyzer.parsers import get_parser_choices
from analyzer import repository

AUTO_DETECT_LABEL = "Auto-detect (by column match)"

# --- logging -> GUI status bar -------------------------------------------
import logging

class QtLogHandler(QObject, logging.Handler):
    message_logged = Signal(str, str)  # level, message

    def __init__(self):
        QObject.__init__(self)
        logging.Handler.__init__(self)

    def emit(self, record): # type: ignore[override]
        self.message_logged.emit(record.levelname, self.format(record))


def make_button(text, width=None, height=34):
    button = QPushButton(text)
    button.setMinimumHeight(height)
    if width is not None:
        button.setMinimumWidth(width)
    return button


def ensure_ready():
    """Create tables and seed default rules on first run. Safe to call
    every launch — only seeds if the rules table is actually empty, so it
    replaces having to run setup_db.py by hand."""
    init_db()
    conn = get_connection()
    rule_count = conn.execute("SELECT COUNT(*) AS c FROM rules").fetchone()["c"]
    conn.close()
    if rule_count == 0:
        seed_default_rules()


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
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)

        self.refresh()

    def refresh(self):
        matches = repository.get_suggested_matches()
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

    def accept_match(self, match_id):
        repository.accept_match(match_id)
        self.refresh()

    def reject_match(self, match_id):
        repository.reject_match(match_id)
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
        export_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        export_layout.addWidget(export_label)

        self.summary_label = QLabel()
        self.summary_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
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

        self.import_tab.imported.connect(self.review_tab.refresh)
        self.import_tab.imported.connect(self.transfer_tab.refresh)
        self.import_tab.imported.connect(self.update_export_summary)

        self.tabs.currentChanged.connect(self._on_tab_changed)

        qt_log_handler = QtLogHandler()
        qt_log_handler.setLevel(logging.INFO)
        logger.addHandler(qt_log_handler)
        qt_log_handler.message_logged.connect(
            lambda level, msg: self.statusBar().showMessage(msg, 8000)
        )

    def _on_tab_changed(self, index):
        widget = self.tabs.widget(index)
        if widget is self.review_tab:
            self.review_tab.refresh()
        elif widget is self.transfer_tab:
            self.transfer_tab.refresh()
        elif widget is self.export_tab:
            self.update_export_summary()

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


class FileImportSettingsDialog(QDialog):
    """
    Lets the user assign a bank-format parser and an account name to each
    selected file individually. Needed as soon as you're importing several
    different banks' (or accounts') statements in a single batch — the old
    flow forced one parser/account onto every file in the batch.
    """
    def __init__(self, filepaths, default_account, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Assign Parser & Account per File")
        self.setMinimumWidth(680)
        self.filepaths = filepaths
        self.result_rows = None

        layout = QVBoxLayout(self)

        hint = QLabel(
            "Set the bank format and account for each file below. Leave "
            "'Bank format' on Auto-detect to let the app guess from the "
            "file's columns."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.table = QTableWidget()
        self.table.setRowCount(len(filepaths))
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["File", "Account", "Bank format"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)

        self.account_edits = []
        self.parser_combos = []
        parser_names = list(get_parser_choices())

        for i, filepath in enumerate(filepaths):
            name_item = QTableWidgetItem(os.path.basename(filepath))
            name_item.setToolTip(filepath)
            self.table.setItem(i, 0, name_item)

            account_edit = QLineEdit(default_account)
            self.table.setCellWidget(i, 1, account_edit)
            self.account_edits.append(account_edit)

            combo = QComboBox()
            combo.addItem(AUTO_DETECT_LABEL)
            for name in parser_names:
                combo.addItem(name)
            self.table.setCellWidget(i, 2, combo)
            self.parser_combos.append(combo)

        layout.addWidget(self.table)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_accept(self):
        rows = []
        for filepath, account_edit, combo in zip(self.filepaths, self.account_edits, self.parser_combos):
            account = account_edit.text().strip()
            if not account:
                QMessageBox.warning(self, "Missing account",
                                     f"Please enter an account name for {os.path.basename(filepath)}.")
                return
            selected = combo.currentText()
            parser_name = None if selected == AUTO_DETECT_LABEL else selected
            rows.append({"filepath": filepath, "account": account, "parser_name": parser_name})
        self.result_rows = rows
        self.accept()


class ImportWorker(QThread):
    progress = Signal(str)
    finished_ok = Signal(dict)
    failed = Signal(str)

    def __init__(self, file_settings):
        """file_settings: list of {"filepath", "account", "parser_name"}."""
        super().__init__()
        self.file_settings = file_settings

    def run(self):
        try:
            for i, item in enumerate(self.file_settings, start=1):
                filepath = item["filepath"]
                self.progress.emit(f"Importing {os.path.basename(filepath)} ({i}/{len(self.file_settings)})...")
                import_file(filepath, account=item["account"], parser_name=item["parser_name"])

            self.progress.emit("Applying categorization rules...")
            categorized = apply_rules()

            self.progress.emit("Detecting self-transfers...")
            transfers = find_transfers()

            self.finished_ok.emit({
                "imported_files": len(self.file_settings),
                "categorized": categorized,
                "transfers_found": len(transfers),
            })
        except BSAError as e:
            logger.warning(f"Import failed: {e}")
            self.failed.emit(str(e))
        except Exception as e:
            logger.exception("Unexpected error during import")
            self.failed.emit(f"Unexpected error: {e}")


class ImportTab(QWidget):
    imported = Signal()

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        intro = QLabel(
            "Import one or more bank statement files. You'll choose the "
            "bank format and account for each file on the next screen."
        )
        intro.setAlignment(Qt.AlignmentFlag.AlignCenter)
        intro.setWordWrap(True)
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
        self.merge_rules_btn = make_button("Reload/Merge Default Rules", width=220, height=34)
        self.merge_rules_btn.clicked.connect(self.merge_default_rules)
        action_row.addStretch()
        action_row.addWidget(self.reset_btn)
        action_row.addWidget(self.merge_rules_btn)
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
        filepaths, _ = QFileDialog.getOpenFileNames(
            self, "Select Statements", "", "Excel Files (*.xlsx *.xls)"
        )
        if not filepaths:
            return

        dialog = FileImportSettingsDialog(filepaths, DEFAULT_ACCOUNT, self)
        if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.result_rows:
            return
        file_settings = dialog.result_rows

        self.progress_dialog = QProgressDialog("Starting import...", None, 0, 0, self)  # type: ignore
        self.progress_dialog.setWindowTitle("Importing")
        self.progress_dialog.setCancelButton(None)
        self.progress_dialog.setMinimumDuration(0)
        self.progress_dialog.show()
        self.btn.setEnabled(False)

        self.worker = ImportWorker(file_settings)
        self.worker.progress.connect(self.progress_dialog.setLabelText)
        self.worker.finished_ok.connect(self._on_import_success)
        self.worker.failed.connect(self._on_import_failed)
        self.worker.start()

    def _on_import_success(self, summary):
        self.progress_dialog.close()
        self.btn.setEnabled(True)
        self.refresh_imported_files()
        self.imported.emit()
        QMessageBox.information(self, "Import complete",
            f"Imported {summary['imported_files']} file(s)\n"
            f"Categorized {summary['categorized']} transaction(s)\n"
            f"Found {summary['transfers_found']} possible transfer(s)")

    def _on_import_failed(self, message):
        self.progress_dialog.close()
        self.btn.setEnabled(True)
        QMessageBox.critical(self, "Import failed", message)

    def refresh_imported_files(self):
        self.file_list.clear()
        rows = repository.get_imported_files()
        if not rows:
            self.file_list.addItem("No files imported yet")
            return
        for row in rows:
            self.file_list.addItem(row["filename"])

    def merge_default_rules(self):
        try:
            count = merge_default_rules()
            QMessageBox.information(self, "Rules reloaded",
                f"{count} new rule(s) added from default_rules.json." if count
                else "No new rules found — everything in the file is already loaded.")
        except Exception as e:
            logger.exception("merge_default_rules failed")
            QMessageBox.critical(self, "Error", str(e))

    # main_gui.py — ImportTab.reset_database
    def reset_database(self):
        confirm = QMessageBox.question(
            self,
            "Reset for new year",
            "This clears imported transactions, import history, and transfer matches. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        wipe_rules = QMessageBox.question(
            self,
            "Categorization rules",
            "Also erase your categorization rules and categories?\n"
            "Choose No to keep what you've built up so far.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes

        remove_files = QMessageBox.question(
            self,
            "Remove input files",
            "Also delete Excel/CSV files from the InputStatements folder?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes

        try:
            reset_database(remove_files=remove_files, wipe_rules=wipe_rules)
            if wipe_rules:
                seed_default_rules()
            self.refresh_imported_files()
            QMessageBox.information(self, "Reset complete", "Database cleared successfully.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))



class CategorizeDialog(QDialog):
    """
    Lets the user categorize a single uncategorized transaction, either
    as a one-off (manual_overrides — affects only this transaction) or
    as a new rule (rules table — affects this and every future matching
    transaction). This is the bridge between the Review tab and the
    rule engine that was previously only reachable from a Python shell.
    """
    def __init__(self, txn_row, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Categorize Transaction")
        self.setMinimumWidth(420)
        self.txn_row = txn_row
        self.result_data = None

        layout = QVBoxLayout(self)

        desc_label = QLabel(f"Description:\n{txn_row['description']}")
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("font-weight: 600;")
        layout.addWidget(desc_label)

        form = QFormLayout()

        self.category_combo = QComboBox()
        self.category_combo.setEditable(True)
        self.category_combo.addItems(get_existing_categories())
        self.category_combo.setCurrentText("")
        form.addRow("Category:", self.category_combo)

        self.category_type_combo = QComboBox()
        self.category_type_combo.addItems([t.value for t in CategoryType])
        self.category_type_combo.setCurrentText(CategoryType.UNSPECIFIED.value)
        form.addRow("Category type (for reports):", self.category_type_combo)

        layout.addLayout(form)

        scope_label = QLabel("Apply to:")
        scope_label.setStyleSheet("font-weight: 600; margin-top: 8px;")
        layout.addWidget(scope_label)

        self.scope_group = QButtonGroup(self)
        self.radio_single = QRadioButton("Just this transaction")
        self.radio_rule = QRadioButton("This and all future matching transactions (creates a rule)")
        self.radio_rule.setChecked(True)
        self.scope_group.addButton(self.radio_single)
        self.scope_group.addButton(self.radio_rule)
        layout.addWidget(self.radio_single)
        layout.addWidget(self.radio_rule)

        rule_form = QFormLayout()
        self.match_value_edit = QLineEdit(txn_row["description"])
        rule_form.addRow("Match text:", self.match_value_edit)

        self.match_op_combo = QComboBox()
        self.match_op_combo.addItems([op.value for op in MatchOp])
        self.match_op_combo.setCurrentText(MatchOp.CONTAINS.value)
        rule_form.addRow("Match type:", self.match_op_combo)
        layout.addLayout(rule_form)

        hint = QLabel(
            "Tip: trim the match text down to a stable keyword (e.g. the "
            "merchant name) — the full description often includes a "
            "one-time reference number that won't repeat."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #6b7280; font-size: 9pt;")
        layout.addWidget(hint)

        self.reason_edit = QLineEdit()
        reason_form = QFormLayout()
        reason_form.addRow("Note (optional):", self.reason_edit)
        layout.addLayout(reason_form)

        self.radio_single.toggled.connect(self._update_rule_fields_enabled)
        self._update_rule_fields_enabled()

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _update_rule_fields_enabled(self):
        is_rule_scope = self.radio_rule.isChecked()
        self.match_value_edit.setEnabled(is_rule_scope)
        self.match_op_combo.setEnabled(is_rule_scope)
        self.reason_edit.setEnabled(not is_rule_scope)

    def _on_accept(self):
        category = self.category_combo.currentText().strip()
        if not category:
            QMessageBox.warning(self, "Missing category", "Please enter a category name.")
            return

        is_rule_scope = self.radio_rule.isChecked()
        if is_rule_scope and not self.match_value_edit.text().strip():
            QMessageBox.warning(self, "Missing match text", "Please enter text to match on.")
            return

        self.result_data = {
            "category": category,
            "category_type": self.category_type_combo.currentText(),
            "scope": "rule" if is_rule_scope else "single",
            "match_value": self.match_value_edit.text().strip(),
            "match_op": self.match_op_combo.currentText(),
            "reason": self.reason_edit.text().strip() or None,
        }
        self.accept()


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
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)
        self.refresh()

    def refresh(self):
        rows = repository.get_uncategorized_transactions()

        self.table.setRowCount(len(rows))
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels(
            ["ID", "Bank", "Account", "Date", "Description", "Amount", "DR/CR", "Action"]
        )
        self.table.horizontalHeader().setStretchLastSection(True)

        for i, row in enumerate(rows):
            for j, key in enumerate(row.keys()):
                self.table.setItem(i, j, QTableWidgetItem(str(row[key])))

            btn = make_button("Categorize...", width=110, height=28)
            btn.clicked.connect(lambda checked, r=row: self.open_categorize_dialog(r))
            self.table.setCellWidget(i, 7, btn)

    def open_categorize_dialog(self, row):
        dialog = CategorizeDialog(row, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        result = dialog.result_data or {}
        if not result:
            return
        try:
            if result["scope"] == "rule":
                priority = get_override_priority()
                add_rule(
                    priority=priority,
                    match_field="description",
                    match_op=result["match_op"],
                    match_value=result["match_value"],
                    category=result["category"],
                    category_type=result["category_type"],
                    source="manual",
                )
                apply_rules()
            else:
                add_manual_override(
                    row["txn_id"],
                    result["category"],
                    category_type=result["category_type"],
                    reason=result["reason"],
                )
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
            return

        self.refresh()


if __name__ == "__main__":
    ensure_ready()
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())