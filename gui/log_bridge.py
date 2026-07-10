import logging
from PySide6.QtCore import QObject, Signal


class QtLogHandler(QObject, logging.Handler):
    """Bridges Python's logging module into a Qt signal, so nothing else
    in the GUI layer needs to subclass logging.Handler directly."""
    message_logged = Signal(str, str)  # level, message

    def __init__(self):
        QObject.__init__(self)
        logging.Handler.__init__(self)

    def emit(self, record):  # type: ignore[override]
        self.message_logged.emit(record.levelname, self.format(record))