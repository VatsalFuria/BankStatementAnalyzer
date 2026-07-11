from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem, QAbstractItemView
)
from analyzer import repository
from gui.widgets import make_button


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
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels(
            ["Date", "Amount", "From Account", "To Account",
             "Debit Description", "Credit Description", "Confidence", "Reason", "Action"]
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
            self.table.setItem(i, 0, QTableWidgetItem(match["txn_date"]))
            self.table.setItem(i, 1, QTableWidgetItem(str(match["amount"])))
            self.table.setItem(i, 2, QTableWidgetItem(match["from_acc"]))
            self.table.setItem(i, 3, QTableWidgetItem(match["to_acc"]))
            self.table.setItem(i, 4, QTableWidgetItem(match["debit_desc"]))
            self.table.setItem(i, 5, QTableWidgetItem(match["credit_desc"]))
            self.table.setItem(i, 6, QTableWidgetItem(str(match["confidence"]) + "%"))
            self.table.setItem(i, 7, QTableWidgetItem(match["reason"] or ""))

            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(0, 0, 0, 0)
            action_layout.setSpacing(6)

            btn_accept = make_button("Accept", width=80, height=28, compact=True)
            btn_reject = make_button("Reject", width=80, height=28, destructive=True, compact=True)
            btn_accept.clicked.connect(lambda checked, m=match: self.accept_match(m["match_id"]))
            btn_reject.clicked.connect(lambda checked, m=match: self.reject_match(m["match_id"]))

            action_layout.addWidget(btn_accept)
            action_layout.addWidget(btn_reject)
            self.table.setCellWidget(i, 8, action_widget)
        self.table.resizeRowsToContents()

    def accept_match(self, match_id):
        repository.accept_match(match_id)
        self.refresh()

    def reject_match(self, match_id):
        repository.reject_match(match_id)
        self.refresh()