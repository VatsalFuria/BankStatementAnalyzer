import os
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QFileDialog,
    QDialog, QTableWidget, QTableWidgetItem, QLineEdit, QComboBox,
    QDialogButtonBox, QAbstractItemView, QListWidget, QMessageBox, QProgressDialog
)

from analyzer.rule_engine import apply_rules, merge_default_rules, seed_default_rules
from analyzer.database import reset_database
from analyzer.transfer_matcher import find_transfers
from analyzer.import_manager import import_file
from analyzer.config import DEFAULT_ACCOUNT
from analyzer.exceptions import BSAError
from analyzer.logging_config import logger
from analyzer.parsers import get_parser_choices
from analyzer import repository
from gui.widgets import make_button

AUTO_DETECT_LABEL = "Auto-detect (by column match)"


class FileImportSettingsDialog(QDialog):
    """
    Lets the user assign a bank-format parser and an account name to each
    selected file individually — needed once you're importing several
    different banks'/accounts' statements in a single batch.
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
        super().__init__()
        self.file_settings = file_settings

    def run(self):
        try:
            txn_ids = []
            import_ids = []
            for i, item in enumerate(self.file_settings, start=1):
                filepath = item["filepath"]
                self.progress.emit(f"Importing {os.path.basename(filepath)} ({i}/{len(self.file_settings)})...")
                fileImportId, fileTxnIds = import_file(filepath, account=item["account"], parser_name=item["parser_name"])
                txn_ids.extend(fileTxnIds)
                import_ids.extend(fileImportId)

            self.progress.emit("Applying categorization rules...")
            categorized = apply_rules(txn_ids)

            self.progress.emit("Detecting self-transfers...")
            transfers = find_transfers()
            # fileImportId not being passed to enable cross import transfer matching

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

    def __init__(self, status_bar=None):
        super().__init__()
        self.status_bar = status_bar  # optional — tab still works standalone/in tests
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        # Grid instead of a manually-stretched QHBoxLayout — stays aligned
        # if a third/fourth action button gets added later.
        action_grid = QGridLayout()
        action_grid.setHorizontalSpacing(12)
        self.reset_btn = make_button("Reset Database", width=180, height=34, destructive=True)
        self.reset_btn.clicked.connect(self.reset_database)
        self.merge_rules_btn = make_button("Reload/Merge Default Rules", width=220, height=34)
        self.merge_rules_btn.clicked.connect(self.merge_default_rules)
        action_grid.addWidget(self.reset_btn, 0, 0)
        action_grid.addWidget(self.merge_rules_btn, 0, 1)
        action_grid.setColumnStretch(2, 1)
        layout.addLayout(action_grid)

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



        self.file_list_label = QLabel("Imported files")
        self.file_list_label.setStyleSheet("font-weight: 600;")
        layout.addWidget(self.file_list_label)
        self.file_list = QListWidget()
        self.file_list.setMaximumHeight(180)
        self.file_list.setAlternatingRowColors(True)
        layout.addWidget(self.file_list)
        layout.addStretch()

        self.refresh_imported_files()

    def _set_actions_enabled(self, enabled: bool):
        # Blocks a second import/reset/merge from starting mid-operation,
        # and doubles as a visible "something is running" cue.
        self.btn.setEnabled(enabled)
        self.reset_btn.setEnabled(enabled)
        self.merge_rules_btn.setEnabled(enabled)

    def import_file(self):

        if self.status_bar:
            self.status_bar.set_busy("Importing...")

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
        self._set_actions_enabled(False)

        self.worker = ImportWorker(file_settings)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished_ok.connect(self._on_import_success)
        self.worker.failed.connect(self._on_import_failed)
        self.worker.start()

    def _on_progress(self, message):
        self.progress_dialog.setLabelText(message)
        if self.status_bar:
            self.status_bar.set_busy(message)

    def _on_import_success(self, summary):
        self.progress_dialog.close()
        self._set_actions_enabled(True)
        self.refresh_imported_files()
        self.imported.emit()
        if self.status_bar:
            self.status_bar.set_ready(f"Imported {summary['imported_files']} file(s)")
        QMessageBox.information(self, "Import complete",
            f"Imported {summary['imported_files']} file(s)\n"
            f"Categorized {summary['categorized']} transaction(s)\n"
            f"Found {summary['transfers_found']} possible transfer(s)")

    def _on_import_failed(self, message):
        self.progress_dialog.close()
        self._set_actions_enabled(True)
        if self.status_bar:
            self.status_bar.set_error(message)
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
            if self.status_bar:
                self.status_bar.set_error(str(e))
            QMessageBox.critical(self, "Error", str(e))

    def reset_database(self):
        confirm = QMessageBox.question(
            self, "Reset for new year",
            "This clears imported transactions, import history, and transfer matches. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        wipe_rules = QMessageBox.question(
            self, "Categorization rules",
            "Also erase your categorization rules and categories?\n"
            "Choose No to keep what you've built up so far.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes

        remove_files = QMessageBox.question(
            self, "Remove input files",
            "Also delete Excel/CSV files from the InputStatements folder?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes

        try:
            reset_database(remove_files=remove_files, wipe_rules=wipe_rules)
            if wipe_rules:
                seed_default_rules()
            self.refresh_imported_files()
            self.imported.emit()  # NOTE: original didn't refresh other tabs after reset — added, see note below
            if self.status_bar:
                self.status_bar.set_ready("Database reset")
            QMessageBox.information(self, "Reset complete", "Database cleared successfully.")
        except Exception as e:
            if self.status_bar:
                self.status_bar.set_error(str(e))
            QMessageBox.critical(self, "Error", str(e))