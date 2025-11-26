from PyQt5 import QtWidgets


class BaseView(QtWidgets.QWidget):
    """Base view class. Subclasses should implement setup_ui()."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        pass
