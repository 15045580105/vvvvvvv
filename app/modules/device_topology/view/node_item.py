"""
@FileName：node_item.py
@Description：
@Author：QinHao
@Time：2025/11/26 13:23
@Department：PTV_AT
"""
from PyQt5 import QtWidgets, QtGui, QtCore


class NodeItem(QtWidgets.QGraphicsItem):
    def __init__(self, name, icon, status, x, y, parent=None):
        super().__init__(parent)
        self.name = name
        self.icon = icon
        self.status = status
        self.setPos(x, y)
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.color_map = {"正常": QtGui.QColor("#10B981"), "离线": QtGui.QColor("#6B7280"),
                          "警告": QtGui.QColor("#F59E0B"), "错误": QtGui.QColor("#EF4444")}
        self.node_color = self.color_map.get(status, QtGui.QColor("#6B7280"))

    def boundingRect(self):
        return QtCore.QRectF(-70, -45, 140, 90)

    def paint(self, painter, option, widget):
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        shadow_rect = QtCore.QRectF(-68, -43, 136, 86)
        shadow_rect.translate(2, 2)
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(QtGui.QColor(0, 0, 0, 20))
        painter.drawRoundedRect(shadow_rect, 12, 12)
        painter.setBrush(QtGui.QColor("#FFFFFF"))
        painter.drawRoundedRect(-68, -43, 136, 86, 12, 12)
        pen = QtGui.QPen(self.node_color, 2)
        pen.setJoinStyle(QtCore.Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(QtCore.Qt.NoBrush)
        painter.drawRoundedRect(-68, -43, 136, 86, 12, 12)
        painter.setFont(QtGui.QFont("Segoe UI Emoji", 22))
        painter.setPen(QtGui.QColor("#374151"))
        painter.drawText(-20, -8, self.icon)
        painter.setFont(QtGui.QFont("Segoe UI", 9, QtGui.QFont.Medium))
        painter.setPen(QtGui.QColor("#111827"))
        text_rect = QtCore.QRectF(-60, 25, 120, 20)
        painter.drawText(text_rect, QtCore.Qt.AlignCenter, self.name)
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(self.node_color)
        painter.drawEllipse(40, -35, 10, 10)
        painter.setFont(QtGui.QFont("Segoe UI", 8))
        painter.setPen(self.node_color)
        painter.drawText(35, 15, self.status)
        if option.state & QtWidgets.QStyle.State_Selected:
            painter.setPen(QtGui.QPen(QtGui.QColor("#3B82F6"), 2, QtCore.Qt.DashLine))
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.drawRoundedRect(-70, -45, 140, 90, 14, 14)
