from PyQt5 import QtWidgets, QtGui
from PyQt5.QtCore import Qt as _Qt

__all__ = ["ModernButton", "create_icon", "TableButton"]

# Qt compatibility constants for linters/type checkers
QT_TRANSPARENT = getattr(_Qt, "transparent", 0)
QT_NO_PEN = getattr(_Qt, "NoPen", 0)
QT_ALIGN_CENTER = getattr(_Qt, "AlignCenter", 0)
QT_CURSOR_POINTING = getattr(_Qt, "PointingHandCursor", 13)


def create_icon(emoji: str, color: str):
    pixmap = QtGui.QPixmap(20, 20)
    pixmap.fill(QT_TRANSPARENT)
    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.Antialiasing)
    painter.setPen(QT_NO_PEN)
    painter.setBrush(QtGui.QColor(color))
    painter.drawEllipse(pixmap.rect().adjusted(1, 1, -1, -1))
    painter.setPen(QtGui.QColor("white"))
    painter.setFont(QtGui.QFont("Segoe UI Emoji", 10))
    painter.drawText(pixmap.rect(), QT_ALIGN_CENTER, emoji)
    painter.end()
    return QtGui.QIcon(pixmap)


class ModernButton(QtWidgets.QPushButton):
    def __init__(self, text: str, color: str = "#3B82F6", icon_emoji: str = "", *, dense: bool = False):
        super().__init__()
        self.color = QtGui.QColor(color)
        self.dense = dense
        self.setCursor(QT_CURSOR_POINTING)
        # 高度根据密集模式调整
        self.setMinimumHeight(26 if self.dense else 32)
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
        # 密集模式下使用更小的内边距与圆角；移除最小宽度
        padding_v, padding_h = (4, 10) if self.dense else (8, 16)
        radius = 4 if self.dense else 6
        min_width = "0" if self.dense else "90px"
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.color.name()};
                color: white;
                border: none;
                padding: {padding_v}px {padding_h}px;
                border-radius: {radius}px;
                font-weight: 500;
                min-width: {min_width};
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


class TableButton(QtWidgets.QPushButton):
    """紧凑型按钮：用于表格单元格内，固定高度、无最小宽度，避免随列宽拉伸。"""

    def __init__(self, text: str, color: str = "#3B82F6", icon_emoji: str = ""):
        super().__init__()
        self._base_color = QtGui.QColor(color)
        self.setCursor(QT_CURSOR_POINTING)
        # 表格内按钮固定高度，小内边距，无最小宽度，固定尺寸策略
        self.setFixedHeight(28)
        self.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        font = QtGui.QFont("Segoe UI", 9)
        font.setStyleStrategy(QtGui.QFont.PreferAntialias)
        self.setFont(font)
        self.setText(f"{icon_emoji} {text}" if icon_emoji else text)
        self._apply_style()

    def _apply_style(self):
        hover = self._base_color.lighter(110).name()
        pressed = self._base_color.darker(110).name()
        base = self._base_color.name()
        # 注意：min-width: 0 以确保不会被拉伸；更小的 padding 和圆角
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {base};
                color: white;
                border: none;
                padding: 4px 10px;
                border-radius: 4px;
                font-weight: 500;
                min-width: 0;
                font-family: "Segoe UI", "Microsoft YaHei";
            }}
            QPushButton:hover {{
                background-color: {hover};
            }}
            QPushButton:pressed {{
                background-color: {pressed};
            }}
            QPushButton:disabled {{
                background-color: #E5E7EB;
                color: #9CA3AF;
            }}
        """)
