import os
from PySide6.QtWidgets import QApplication

_STYLE_PATH = os.path.join(os.path.dirname(__file__), "..", "resources", "style.qss")


def apply_app_style(app: QApplication):
    """Applied once, at the QApplication level (not per-window), so
    dialogs — FileImportSettingsDialog, CategorizeDialog — inherit it
    automatically instead of looking unstyled."""
    try:
        with open(_STYLE_PATH, "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())
    except FileNotFoundError:
        pass  # app still works, just unstyled