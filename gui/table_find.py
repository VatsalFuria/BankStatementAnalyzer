"""
Reusable Ctrl+F "find in table" bar — one implementation shared by every
QTableWidget in the app (Review, Transfers, Rules, ...) instead of each
tab hand-rolling its own search/highlight/navigate logic.

Usage (3 lines per tab):

    from gui.table_find import attach_find_bar

    self.finder = attach_find_bar(self, layout, self.table)
    ...
    # at the end of that tab's refresh():
    self.finder.refresh_search()
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut, QColor, QBrush
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLineEdit, QLabel, QAbstractItemView

from gui.widgets import make_button

_MATCH_HIGHLIGHT = QColor("#5c4a13")


class _FindLineEdit(QLineEdit):
    """Enter -> next match, Shift+Enter -> previous, Escape -> close —
    QLineEdit.returnPressed alone can't see modifier state."""
    def __init__(self, on_next, on_prev, on_escape, parent=None):
        super().__init__(parent)
        self._on_next, self._on_prev, self._on_escape = on_next, on_prev, on_escape

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            (self._on_prev if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else self._on_next)()
            return
        if event.key() == Qt.Key.Key_Escape:
            self._on_escape()
            return
        super().keyPressEvent(event)


class TableFindBar(QWidget):
    """A hidden-until-Ctrl+F search bar bound to one QTableWidget."""
    def __init__(self, table, search_columns=None, parent=None):
        super().__init__(parent)
        self.table = table
        self.search_columns = search_columns  # None = auto-detect item columns
        self._matches = []
        self._current = -1

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 4)
        layout.setSpacing(6)

        self.edit = _FindLineEdit(self._next, self._prev, self.close_bar)
        self.edit.setPlaceholderText("Find in table...")
        self.edit.textChanged.connect(self._search)
        layout.addWidget(self.edit)

        self.count_label = QLabel("")
        self.count_label.setStyleSheet("color: #9aa0a6;")
        layout.addWidget(self.count_label)

        for symbol, handler in (("▲", self._prev), ("▼", self._next), ("✕", self.close_bar)):
            btn = make_button(symbol, width=32, height=28, compact=True)
            btn.clicked.connect(handler)
            layout.addWidget(btn)

        self.hide()

    # -- public API --------------------------------------------------------
    def open_bar(self):
        self.show()
        self.edit.setFocus()
        self.edit.selectAll()
        if self.edit.text():
            self._search()

    def close_bar(self):
        self.hide()
        self._clear_highlights()
        self.table.setFocus()

    def refresh_search(self):
        """Call after repopulating the table so highlights/positions
        don't point at stale rows."""
        if self.isVisible() and self.edit.text():
            self._search()

    # -- internals -----------------------------------------------------------
    def _columns(self):
        if self.search_columns is not None:
            return self.search_columns
        # Auto mode: skip columns that hold cell widgets (e.g. an Action
        # column of buttons) rather than QTableWidgetItems.
        cols = []
        for col in range(self.table.columnCount()):
            probe_rows = range(min(self.table.rowCount(), 5))
            if not any(self.table.cellWidget(row, col) is not None for row in probe_rows):
                cols.append(col)
        return cols

    def _search(self):
        query = self.edit.text().strip().upper()
        self._clear_highlights()
        self._matches, self._current = [], -1

        if query:
            cols = self._columns()
            for row in range(self.table.rowCount()):
                matched = False
                for col in cols:
                    item = self.table.item(row, col)
                    if item and query in item.text().upper():
                        item.setBackground(_MATCH_HIGHLIGHT)
                        matched = True
                if matched:
                    self._matches.append(row)

        if self._matches:
            self._current = 0
            self._goto()
        self._update_count()

    def _clear_highlights(self):
        for row in range(self.table.rowCount()):
            for col in range(self.table.columnCount()):
                item = self.table.item(row, col)
                if item:
                    item.setBackground(QBrush())

    def _update_count(self):
        if not self.edit.text():
            self.count_label.setText("")
        elif not self._matches:
            self.count_label.setText("No results")
        else:
            self.count_label.setText(f"{self._current + 1}/{len(self._matches)}")

    def _goto(self):
        row = self._matches[self._current]
        self.table.selectRow(row)
        cols = self._columns()
        item = self.table.item(row, cols[0]) if cols else None
        if item:
            self.table.scrollToItem(item, QAbstractItemView.ScrollHint.PositionAtCenter)

    def _next(self):
        if not self._matches:
            return
        self._current = (self._current + 1) % len(self._matches)
        self._goto()
        self._update_count()

    def _prev(self):
        if not self._matches:
            return
        self._current = (self._current - 1) % len(self._matches)
        self._goto()
        self._update_count()


def attach_find_bar(shortcut_owner, layout, table, index=None, search_columns=None):
    """
    One-call setup: builds a TableFindBar for `table`, inserts it into
    `layout` (right before the table, or at `index`), and wires
    Ctrl+F/Cmd+F — scoped to `shortcut_owner` (normally the tab itself) —
    to open it. Returns the bar so the caller can invoke
    `.refresh_search()` after repopulating the table.
    """
    bar = TableFindBar(table, search_columns=search_columns, parent=shortcut_owner)
    (layout.addWidget if index is None else lambda w: layout.insertWidget(index, w))(bar)

    shortcut = QShortcut(QKeySequence.StandardKey.Find, shortcut_owner)
    shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
    shortcut.activated.connect(bar.open_bar)
    bar._shortcut = shortcut  # keep a reference so it isn't garbage-collected

    return bar