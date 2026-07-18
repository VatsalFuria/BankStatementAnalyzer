"""Shared rule-editing UI, used by both the Rules tab (add/edit any rule)
and the Review tab's Categorize dialog (create a rule from an
uncategorized transaction) — one place for the match/category fields so
the two can't drift out of sync."""
from PySide6.QtWidgets import (
    QWidget, QFormLayout, QComboBox, QLineEdit, QDialog, QVBoxLayout,
    QDialogButtonBox, QMessageBox
)

from analyzer.categories import get_existing_categories
from analyzer.constants import CategoryType, MatchOp, DrCr

DR_CR_LABELS = {
    "Any": None,
    "DR only (debit)": DrCr.DEBIT.value,
    "CR only (credit)": DrCr.CREDIT.value,
}
DR_CR_LABELS_REVERSE = {v: k for k, v in DR_CR_LABELS.items()}


class RuleFieldsWidget(QWidget):
    """Match text/op/direction + category/category-type. No priority
    field — priority is either inherited (get_override_priority()) or
    managed separately by the Rules tab's reorder controls."""
    def __init__(self, parent=None):
        super().__init__(parent)
        form = QFormLayout(self)
        form.setContentsMargins(0, 0, 0, 0)

        self.category_combo = QComboBox()
        self.category_combo.setEditable(True)
        self.category_combo.addItems(get_existing_categories())
        self.category_combo.setCurrentText("")
        form.addRow("Category:", self.category_combo)

        self.category_type_combo = QComboBox()
        self.category_type_combo.addItems([t.value for t in CategoryType])
        self.category_type_combo.setCurrentText(CategoryType.UNSPECIFIED.value)
        form.addRow("Category type (for reports):", self.category_type_combo)

        self.match_value_edit = QLineEdit()
        form.addRow("Match text:", self.match_value_edit)

        self.match_op_combo = QComboBox()
        self.match_op_combo.addItems([op.value for op in MatchOp])
        self.match_op_combo.setCurrentText(MatchOp.CONTAINS.value)
        form.addRow("Match type:", self.match_op_combo)

        self.dr_cr_combo = QComboBox()
        self.dr_cr_combo.addItems(list(DR_CR_LABELS))
        form.addRow("Applies to:", self.dr_cr_combo)

    def load(self, rule_row):
        """Populate fields from an existing rule row (dict-like — a
        sqlite3.Row or a plain dict) for editing or pre-filling."""
        self.category_combo.setCurrentText(rule_row["category"])
        self.category_type_combo.setCurrentText(rule_row["category_type"])
        self.match_value_edit.setText(rule_row["match_value"])
        self.match_op_combo.setCurrentText(rule_row["match_op"])
        self.dr_cr_combo.setCurrentText(DR_CR_LABELS_REVERSE.get(rule_row["dr_cr"], "Any"))

    def validate(self) -> str | None:
        if not self.category_combo.currentText().strip():
            return "Please enter a category name."
        if not self.match_value_edit.text().strip():
            return "Please enter text to match on."
        return None

    def to_dict(self) -> dict:
        return {
            "category": self.category_combo.currentText().strip(),
            "category_type": self.category_type_combo.currentText(),
            "match_value": self.match_value_edit.text().strip(),
            "match_op": self.match_op_combo.currentText(),
            "dr_cr": DR_CR_LABELS[self.dr_cr_combo.currentText()],
        }


class RuleEditDialog(QDialog):
    """Add or edit a single rule. Pass an existing rule row to edit it,
    or initial_values (e.g. from a suggestion) to pre-fill a new one."""
    def __init__(self, rule_row=None, initial_values: dict | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Rule" if rule_row else "Add Rule")
        self.setMinimumWidth(420)
        self.result_data = None

        layout = QVBoxLayout(self)
        self.fields = RuleFieldsWidget()
        layout.addWidget(self.fields)

        if rule_row is not None:
            self.fields.load(rule_row)
        elif initial_values:
            self.fields.load(initial_values)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_accept(self):
        error = self.fields.validate()
        if error:
            QMessageBox.warning(self, "Missing information", error)
            return
        self.result_data = self.fields.to_dict()
        self.accept()