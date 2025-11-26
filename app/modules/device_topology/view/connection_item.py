"""
@FileName：connection_item.py
@Description：
@Author：QinHao
@Time：2025/11/26 13:24
@Department：PTV_AT
"""
from PyQt5 import QtCore, QtGui, QtWidgets


class ConnectionItem(QtWidgets.QGraphicsItem):
    def __init__(self, start_point, end_point, status, parent=None):
        super().__init__(parent)
        self.start_point = start_point
        self.end_point = end_point
        self.status = status
        self.color_map = {"正常": QtGui.QColor("#10B981"), "离线": QtGui.QColor("#6B7280"),
                          "警告": QtGui.QColor("#F59E0B"), "错误": QtGui.QColor("#EF4444")}
        self.line_color = self.color_map.get(status, QtGui.QColor("#6B7280"))
        self.opacity = 1.0
        if status == "正常":
            self.timer = QtCore.QTimer()
            self.timer.timeout.connect(self.animate)
            self.timer.start(2000)

    def boundingRect(self):
        return QtCore.QRectF(self.start_point, self.end_point).normalized().adjusted(-5, -5, 5, 5)

    def paint(self, painter, option, widget):
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        pen = QtGui.QPen(self.line_color, 2, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin)
        painter.setPen(pen)
        painter.drawLine(self.start_point, self.end_point)
        angle = QtCore.QLineF(self.start_point, self.end_point).angle()
        arrow_size = 8
        import math
        arrow_p1 = self.end_point + QtCore.QPointF(-arrow_size * 2 * (1 + 0.5 * (self.opacity - 1)),
                                                   -arrow_size * math.sin((angle - 30) * math.pi / 180))
        arrow_p2 = self.end_point + QtCore.QPointF(-arrow_size * 2 * (1 + 0.5 * (self.opacity - 1)),
                                                   -arrow_size * math.sin((angle + 30) * math.pi / 180))
        painter.setBrush(self.line_color)
        painter.drawPolygon(QtGui.QPolygonF([self.end_point, arrow_p1, arrow_p2]))
        if self.status == "正常":
            painter.setOpacity(self.opacity)
            pen.setWidth(4)
            painter.setPen(pen)
            painter.drawLine(self.start_point, self.end_point)
            painter.setOpacity(1.0)

    def animate(self):
        self.opacity = 1.0 if self.opacity < 0.3 else 0.3
        self.update()
