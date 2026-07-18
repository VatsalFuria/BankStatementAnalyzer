import logging
from PySide6.QtWidgets import QMainWindow, QTabWidget, QWidget, QVBoxLayout

from analyzer.logging_config import logger
from gui.log_bridge import QtLogHandler
from gui.status_bar import StatusBar
from gui.tabs.import_tab import ImportTab
from gui.tabs.review_tab import ReviewTab
from gui.tabs.transfer_tab import TransferTab
from gui.tabs.export_tab import ExportTab
from gui.tabs.rules_tab import RulesTab


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Bank Statement Analyzer")
        self.resize(1100, 700)
        self.setMinimumSize(900, 600)

        self.status = StatusBar(self)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        self.import_tab = ImportTab(self.status)
        self.rules_tab = RulesTab()
        self.review_tab = ReviewTab()
        self.transfer_tab = TransferTab()
        self.export_tab = ExportTab()

        self.tabs.addTab(self.import_tab, "Import")
        self.tabs.addTab(self.rules_tab, "Rules")
        self.tabs.addTab(self.review_tab, "Review Uncategorized")
        self.tabs.addTab(self.transfer_tab, "Transfers")
        self.tabs.addTab(self.export_tab, "Export")

        self.import_tab.imported.connect(self.review_tab.refresh)
        self.import_tab.imported.connect(self.transfer_tab.refresh)
        self.import_tab.imported.connect(self.export_tab.refresh)

        self.rules_tab.rules_applied.connect(self.review_tab.refresh)
        self.rules_tab.rules_applied.connect(self.transfer_tab.refresh)
        self.rules_tab.rules_applied.connect(self.export_tab.refresh)

        self.tabs.currentChanged.connect(self._on_tab_changed)

        log_handler = QtLogHandler()
        log_handler.setLevel(logging.INFO)
        logger.addHandler(log_handler)
        log_handler.message_logged.connect(self.status.show_log_message)

    def _on_tab_changed(self, index):
        widget = self.tabs.widget(index)
        if hasattr(widget, "refresh"):
            widget.refresh()  # type: ignore[attr-defined]