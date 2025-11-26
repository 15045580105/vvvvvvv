from PyQt5 import QtWidgets, QtGui, QtCore

__all__ = ["ModernButton", "create_icon"]

def create_icon(emoji: str, color: str):
    pixmap = QtGui.QPixmap(20, 20)
    pixmap.fill(QtCore.Qt.transparent)
    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.Antialiasing)
    painter.setPen(QtCore.Qt.NoPen)
    painter.setBrush(QtGui.QColor(color))
    painter.drawEllipse(pixmap.rect().adjusted(1, 1, -1, -1))
    painter.setPen(QtGui.QColor("white"))
    painter.setFont(QtGui.QFont("Segoe UI Emoji", 10))
    painter.drawText(pixmap.rect(), QtCore.Qt.AlignCenter, emoji)
    painter.end()
    return QtGui.QIcon(pixmap)

class ModernButton(QtWidgets.QPushButton):
    def __init__(self, text: str, color: str = "#3B82F6", icon_emoji: str = ""):
        super().__init__()
        self.color = QtGui.QColor(color)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setMinimumHeight(32)
        font = QtGui.QFont("Segoe UI", 9)
        font.setStyleStrategy(QtGui.QFont.PreferAntialias)
        self.setFont(font)
        if icon_emoji:
            self.setText(f"{icon_emoji} {text}")
        else:
            self.setText(text)
        self.update_style()

    def update_style(self):
        hover_color = self.color.lighter(110).name()
        pressed_color = self.color.darker(110).name()
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.color.name()};
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 6px;
                font-weight: 500;
                min-width: 90px;
                font-family: "Segoe UI", "Microsoft YaHei";
            }}
            QPushButton:hover {{
                background-color: {hover_color};
            }}
            QPushButton:pressed {{
                background-color: {pressed_color};
            }}
            QPushButton:disabled {{
                background-color: #E5E7EB;
                color: #9CA3AF;
            }}
        """)

