from PySide6.QtWidgets import QPushButton


def make_button(text, width=None, height=34, destructive=False):
    button = QPushButton(text)
    button.setMinimumHeight(height)
    if width is not None:
        button.setMinimumWidth(width)
    if destructive:
        button.setProperty("destructive", True)
    return button