"""Application entry point. Bootstraps the database, applies styling,
and shows the main window. UI logic lives in gui/, business logic in
analyzer/ — this file does exactly one thing: start the app."""
import sys
from PySide6.QtWidgets import QApplication

from gui.bootstrap import ensure_ready
from gui.style import apply_app_style
from gui.main_window import MainWindow


def main():
    ensure_ready()
    app = QApplication(sys.argv)
    apply_app_style(app)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()