from PySide6.QtWidgets import QMainWindow, QLabel


class StatusBar:
    """
    Wraps QMainWindow.statusBar() with a permanent, color-coded state
    label (Ready / Busy / Error) that never times out — separate from
    the transient log messages, which still auto-clear after 8s for
    routine INFO lines but stay up indefinitely for warnings/errors.
    This is what answers "is something running right now?" at a glance,
    without having to catch a message before it disappears.
    """
    def __init__(self, window: QMainWindow):
        self._bar = window.statusBar()
        self._state_label = QLabel("Ready")
        self._state_label.setObjectName("statusOk")
        self._bar.addPermanentWidget(self._state_label)

    def set_busy(self, message: str):
        self._update(message, "statusBusy")

    def set_ready(self, message: str = "Ready"):
        self._update(message, "statusOk")

    def set_error(self, message: str):
        self._update(f"Error: {message}", "statusError")

    def show_log_message(self, level: str, message: str):
        timeout = 8000 if level in ("INFO", "DEBUG") else 0
        self._bar.showMessage(message, timeout)

    def _update(self, text: str, object_name: str):
        self._state_label.setText(text)
        self._state_label.setObjectName(object_name)
        # QSS selectors don't re-evaluate on setObjectName alone
        self._state_label.style().unpolish(self._state_label)
        self._state_label.style().polish(self._state_label)