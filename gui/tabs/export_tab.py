from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFileDialog, QMessageBox

from analyzer.export import export_workbook, get_export_summary
from gui.widgets import make_button


class ExportTab(QWidget):
    """Extracted out of MainWindow.__init__, where it previously lived
    as an inline QWidget with no dedicated class."""
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        intro = QLabel("Export your categorized workbook when you're ready.")
        intro.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(intro)

        self.summary_label = QLabel()
        self.summary_label.setObjectName("exportSummary")
        self.summary_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.summary_label)

        button_row = QHBoxLayout()
        button_row.addStretch()
        self.export_btn = make_button("Export Workbook", width=220, height=40)
        self.export_btn.clicked.connect(self.export)
        button_row.addWidget(self.export_btn)
        button_row.addStretch()
        layout.addLayout(button_row)
        layout.addStretch()

        self.refresh()

    def refresh(self):
        summary = get_export_summary()
        self.summary_label.setText(
            f"{summary['total_transactions']} transactions • "
            f"{summary['uncategorized']} uncategorized • "
            f"{summary['accepted_transfers']} accepted transfers"
        )

    def export(self):
        summary = get_export_summary()
        if summary["total_transactions"] <= 0:
            QMessageBox.warning(self, "Export blocked", "Nothing to export yet. Import at least one statement first.")
            return

        filepath, _ = QFileDialog.getSaveFileName(self, "Save Excel", "", "Excel Files (*.xlsx)")
        if not filepath:
            return
        try:
            export_workbook(filepath)
            self.refresh()
            QMessageBox.information(self, "Export", "Workbook exported successfully.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))