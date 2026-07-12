from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QDialog,
    QComboBox, QLineEdit, QRadioButton, QButtonGroup, QDialogButtonBox,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QMessageBox
)

from analyzer.rule_engine import add_rule, add_manual_override, get_override_priority, apply_rules
from analyzer.categories import get_existing_categories
from analyzer.constants import CategoryType, MatchOp, DrCr
from analyzer import repository
from gui.widgets import make_button


class CategorizeDialog(QDialog):
    """
    Lets the user categorize a single uncategorized transaction, either
    as a one-off (manual_overrides) or as a new rule (rules table).
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

        self.dr_cr_combo = QComboBox()
        self.dr_cr_combo.addItems(["Any", "DR only (debit)", "CR only (credit)"])
        default_label = "DR only (debit)" if txn_row["dr_cr"] == DrCr.DEBIT.value else "CR only (credit)"
        self.dr_cr_combo.setCurrentText(default_label)
        rule_form.addRow("Applies to:", self.dr_cr_combo)

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
        self.dr_cr_combo.setEnabled(is_rule_scope)
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
        
        dr_cr_map = {
            "Any": None,
            "DR only (debit)": DrCr.DEBIT.value,
            "CR only (credit)": DrCr.CREDIT.value,
        }

        self.result_data = {
            "category": category,
            "category_type": self.category_type_combo.currentText(),
            "scope": "rule" if is_rule_scope else "single",
            "match_value": self.match_value_edit.text().strip(),
            "match_op": self.match_op_combo.currentText(),
            "dr_cr": dr_cr_map[self.dr_cr_combo.currentText()] if is_rule_scope else None,
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
        # self.table.horizontalHeader().setStretchLastSection(True)

        for i, row in enumerate(rows):
            for j, key in enumerate(row.keys()):
                self.table.setItem(i, j, QTableWidgetItem(str(row[key])))

            btn = make_button("Categorize...", width=110, height=24, compact=True)
            btn.clicked.connect(lambda checked, r=row: self.open_categorize_dialog(r))
            self.table.setCellWidget(i, 7, btn)

        self.table.resizeColumnsToContents()
        self.table.resizeRowsToContents()

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
                    dr_cr=result["dr_cr"],
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