from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QAbstractItemView, QFileDialog, QMessageBox, QDialog
)

from analyzer.rule_engine import (
    get_all_rules, update_rule, delete_rule, move_rule, add_rule,
    reapply_all_rules, export_rules_to_json, import_rules_from_json,
    get_override_priority,
)
from analyzer.rule_suggester import suggest_rules
from analyzer.exceptions import BSAError
from gui.widgets import make_button
from gui.rule_widgets import RuleEditDialog

RULE_COLUMNS = ["Priority", "Field", "Op", "Match Value", "Category",
                "Category Type", "Applies To", "Source", "Actions"]
APPLIES_TO_LABELS = {None: "Any", "DR": "Debit", "CR": "Credit"}


class RulesTab(QWidget):
    rules_applied = Signal()

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        header_row = QHBoxLayout()
        title = QLabel("Categorization Rules")
        title.setStyleSheet("font-size: 11pt; font-weight: 600;")
        header_row.addWidget(title)
        header_row.addStretch()

        self.add_btn = make_button("Add Rule", width=110)
        self.add_btn.clicked.connect(self.add_rule_dialog)
        header_row.addWidget(self.add_btn)

        self.suggest_btn = make_button("Suggest Rules", width=130)
        self.suggest_btn.clicked.connect(self.show_suggestions)
        header_row.addWidget(self.suggest_btn)

        self.import_btn = make_button("Import...", width=100)
        self.import_btn.clicked.connect(self.import_rules)
        header_row.addWidget(self.import_btn)

        self.export_btn = make_button("Export...", width=100)
        self.export_btn.clicked.connect(self.export_rules)
        header_row.addWidget(self.export_btn)

        self.apply_btn = make_button("Apply Rules Now", width=150)
        self.apply_btn.clicked.connect(self.apply_rules_now)
        header_row.addWidget(self.apply_btn)

        layout.addLayout(header_row)

        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.setColumnCount(len(RULE_COLUMNS))
        self.table.setHorizontalHeaderLabels(RULE_COLUMNS)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        layout.addWidget(self.table)

        self.suggestions_label = QLabel("Suggested Rules (from uncategorized transactions)")
        self.suggestions_label.setStyleSheet("font-weight: 600; margin-top: 8px;")
        self.suggestions_label.hide()
        layout.addWidget(self.suggestions_label)

        self.suggestions_table = QTableWidget()
        self.suggestions_table.setAlternatingRowColors(True)
        self.suggestions_table.setColumnCount(5)
        self.suggestions_table.setHorizontalHeaderLabels(
            ["Match Text", "Covers", "Applies To", "Sample", "Action"]
        )
        self.suggestions_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.suggestions_table.hide()
        layout.addWidget(self.suggestions_table)

        self.refresh()

    # ------------------------------------------------------------------
    # Main rules table
    # ------------------------------------------------------------------
    def refresh(self):
        rows = get_all_rules()
        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            self.table.setItem(i, 0, QTableWidgetItem(str(row["priority"])))
            self.table.setItem(i, 1, QTableWidgetItem(row["match_field"]))
            self.table.setItem(i, 2, QTableWidgetItem(row["match_op"]))
            self.table.setItem(i, 3, QTableWidgetItem(row["match_value"]))
            self.table.setItem(i, 4, QTableWidgetItem(row["category"]))
            self.table.setItem(i, 5, QTableWidgetItem(row["category_type"]))
            self.table.setItem(i, 6, QTableWidgetItem(APPLIES_TO_LABELS.get(row["dr_cr"], row["dr_cr"] or "Any")))
            self.table.setItem(i, 7, QTableWidgetItem(row["source"]))
            self.table.setCellWidget(i, 8, self._build_action_widget(row, i, len(rows)))
        self.table.resizeColumnsToContents()
        self.table.resizeRowsToContents()

    def _build_action_widget(self, row, index, total):
        widget = QWidget()
        actions = QHBoxLayout(widget)
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(4)

        up_btn = make_button("▲", width=32, height=26, compact=True)
        up_btn.setEnabled(index > 0)
        up_btn.clicked.connect(lambda checked, rid=row["id"]: self._move(rid, "up"))
        actions.addWidget(up_btn)

        down_btn = make_button("▼", width=32, height=26, compact=True)
        down_btn.setEnabled(index < total - 1)
        down_btn.clicked.connect(lambda checked, rid=row["id"]: self._move(rid, "down"))
        actions.addWidget(down_btn)

        edit_btn = make_button("Edit", width=60, height=26, compact=True)
        edit_btn.clicked.connect(lambda checked, r=row: self.edit_rule_dialog(r))
        actions.addWidget(edit_btn)

        delete_btn = make_button("Delete", width=70, height=26, destructive=True, compact=True)
        delete_btn.clicked.connect(lambda checked, rid=row["id"]: self._delete(rid))
        actions.addWidget(delete_btn)

        return widget

    def _move(self, rule_id, direction):
        move_rule(rule_id, direction)
        self.refresh()

    def _delete(self, rule_id):
        confirm = QMessageBox.question(
            self, "Delete rule",
            "Delete this rule? Transactions already categorized by it keep "
            "their category — only the rule itself, and its link from "
            "those rows, is removed.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            delete_rule(rule_id)
            self.refresh()

    def add_rule_dialog(self):
        dialog = RuleEditDialog(initial_values={
            "category": "", "category_type": "unspecified",
            "match_value": "", "match_op": "contains", "dr_cr": None,
        }, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.result_data:
            data = dialog.result_data
            add_rule(
                priority=get_override_priority(), match_field="description",
                match_op=data["match_op"], match_value=data["match_value"],
                category=data["category"], category_type=data["category_type"],
                source="manual", dr_cr=data["dr_cr"],
            )
            self.refresh()

    def edit_rule_dialog(self, row):
        dialog = RuleEditDialog(rule_row=row, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.result_data:
            update_rule(row["id"], **dialog.result_data)
            self.refresh()

    def apply_rules_now(self):
        reapply_all_rules()
        self.rules_applied.emit()
        QMessageBox.information(self, "Rules applied", "Categorization rules re-applied to all transactions.")

    # ------------------------------------------------------------------
    # Import / export
    # ------------------------------------------------------------------
    def import_rules(self):
        filepath, _ = QFileDialog.getOpenFileName(self, "Import Rules", "", "JSON Files (*.json)")
        if not filepath:
            return

        box = QMessageBox(self)
        box.setWindowTitle("Import rules")
        box.setText(
            "Merge keeps your existing rules and adds any new ones from "
            "this file. Replace erases all current rules first."
        )
        merge_btn = box.addButton("Merge", QMessageBox.ButtonRole.AcceptRole)
        replace_btn = box.addButton("Replace All", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()

        clicked = box.clickedButton()
        if clicked not in (merge_btn, replace_btn):
            return
        mode = "replace" if clicked is replace_btn else "merge"

        try:
            count = import_rules_from_json(filepath, mode=mode)
            self.refresh()
            QMessageBox.information(self, "Import complete", f"{count} rule(s) imported.")
        except BSAError as e:
            QMessageBox.critical(self, "Import failed", str(e))

    def export_rules(self):
        filepath, _ = QFileDialog.getSaveFileName(self, "Export Rules", "rules.json", "JSON Files (*.json)")
        if not filepath:
            return
        try:
            export_rules_to_json(filepath)
            QMessageBox.information(self, "Export complete", f"Rules exported to {filepath}")
        except Exception as e:
            QMessageBox.critical(self, "Export failed", str(e))

    # ------------------------------------------------------------------
    # Suggestions (from uncategorized transactions)
    # ------------------------------------------------------------------
    def show_suggestions(self):
        suggestions = suggest_rules()
        self.suggestions_label.show()
        self.suggestions_table.show()

        if not suggestions:
            self.suggestions_table.setRowCount(0)
            QMessageBox.information(self, "No suggestions",
                                     "No repeated, unmatched keywords found in the uncategorized transactions.")
            return

        self.suggestions_table.setRowCount(len(suggestions))
        for i, s in enumerate(suggestions):
            self.suggestions_table.setItem(i, 0, QTableWidgetItem(s["token"]))
            self.suggestions_table.setItem(i, 1, QTableWidgetItem(f"{s['count']} txns"))
            self.suggestions_table.setItem(i, 2, QTableWidgetItem(APPLIES_TO_LABELS.get(s["dr_cr"], "Any")))
            self.suggestions_table.setItem(i, 3, QTableWidgetItem(s["samples"][0] if s["samples"] else ""))

            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(0, 0, 0, 0)
            action_layout.setSpacing(4)
            approve_btn = make_button("Approve...", width=90, height=26, compact=True)
            approve_btn.clicked.connect(lambda checked, s=s: self._approve_suggestion(s))
            dismiss_btn = make_button("Dismiss", width=70, height=26, destructive=True, compact=True)
            dismiss_btn.clicked.connect(lambda checked, i=i: self.suggestions_table.hideRow(i))
            action_layout.addWidget(approve_btn)
            action_layout.addWidget(dismiss_btn)
            self.suggestions_table.setCellWidget(i, 4, action_widget)
        self.suggestions_table.resizeColumnsToContents()

    def _approve_suggestion(self, suggestion):
        """Approving never auto-inserts a rule — it opens the same
        add/edit dialog, pre-filled, so a human confirms (or corrects)
        the category before anything is written. Same suggest-then-
        approve shape as the Transfers tab, just for rules."""
        dialog = RuleEditDialog(initial_values={
            "category": suggestion["suggested_category"],
            "category_type": "unspecified",
            "match_value": suggestion["token"],
            "match_op": "contains",
            "dr_cr": suggestion["dr_cr"],
        }, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.result_data:
            data = dialog.result_data
            add_rule(
                priority=get_override_priority(), match_field="description",
                match_op=data["match_op"], match_value=data["match_value"],
                category=data["category"], category_type=data["category_type"],
                source="manual", dr_cr=data["dr_cr"],
            )
            self.refresh()