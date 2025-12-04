from PyQt5.QtCore import QRectF, Qt, QPointF
from PyQt5.QtGui import QPainter, QPen, QFont, QColor
from PyQt5.QtWidgets import QWidget, QSizePolicy


class NetworkTopologyWidget(QWidget):
    """
    非自适应节点大小的拓扑图QWidget：
    - 中间一个大矩形，文字："请选择诊断端口"
    - 上方水平排列四个节点：VM1, RT1, RT2, 与PFE相连的端口（固定大小、均匀分布）
    - 下方水平排列五个节点：OBD, IDC, ADC, TBOX, FL（固定大小、均匀分布）
    - 上下节点通过垂直连线连接到中间的大矩形
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding))
        self.setMinimumSize(400, 300)
        self._top_labels = ["VM1", "RT1", "RT2", "与PFE相连的端口"]
        self._bottom_labels = ["OBD", "IDC", "ADC", "TBOX", "FL"]
        # 样式颜色
        self._bg_color = QColor(250, 250, 250)
        self._border_color = QColor(60, 120, 200)
        self._node_border = QColor(90, 90, 90)
        self._line_color = QColor(110, 110, 110)
        self._text_color = QColor(30, 30, 30)

    def sizeHint(self):
        return self.minimumSize()

    def _compute_layout(self, w: int, h: int):
        """根据控件大小计算中心矩形与固定节点块布局。"""
        margin = int(min(w, h) * 0.06)  # 周边留白
        spacing = int(min(w, h) * 0.02)  # 行间距
        node_height = int(h * 0.10)
        node_width = int(w * 0.16)  # 固定节点块宽度

        # 中间大矩形更大，宽度超过上/下行跨度（但不超出控件）
        row_span = w - margin * 2
        center_w = int(min(w - margin * 0.5, row_span + margin))
        center_h = int(h * 0.35)
        center_x = (w - center_w) // 2
        center_y = (h - center_h) // 2
        center_rect = QRectF(center_x, center_y, center_w, center_h)

        # 上方行：均匀分布固定宽度块
        top_row_y = max(margin, center_y - spacing - node_height)
        top_count = len(self._top_labels)
        top_available_w = w - margin * 2
        top_slot_w = top_available_w / top_count
        top_nodes = []
        for i, label in enumerate(self._top_labels):
            x = margin + i * top_slot_w + (top_slot_w - node_width) / 2
            rect = QRectF(x, top_row_y, node_width, node_height)
            top_nodes.append((label, rect))

        # 下方行：均匀分布固定宽度块
        bottom_row_y = min(h - margin - node_height, center_y + center_h + spacing)
        bottom_count = len(self._bottom_labels)
        bottom_available_w = w - margin * 2
        bottom_slot_w = bottom_available_w / bottom_count
        bottom_nodes = []
        for i, label in enumerate(self._bottom_labels):
            x = margin + i * bottom_slot_w + (bottom_slot_w - node_width) / 2
            rect = QRectF(x, bottom_row_y, node_width, node_height)
            bottom_nodes.append((label, rect))

        # 垂直连接：每个节点中心X到中心矩形对应边上的同X点
        connections = []
        for _, rect in top_nodes:
            cx = rect.center().x()
            connections.append((QPointF(cx, rect.bottom()), QPointF(cx, center_rect.top())))
        for _, rect in bottom_nodes:
            cx = rect.center().x()
            connections.append((QPointF(cx, rect.top()), QPointF(cx, center_rect.bottom())))

        return center_rect, top_nodes, bottom_nodes, connections

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)

        # 背景
        painter.fillRect(self.rect(), self._bg_color)

        w = self.width()
        h = self.height()
        center_rect, top_nodes, bottom_nodes, connections = self._compute_layout(w, h)

        # 绘制连接线（垂直线段）
        pen = QPen(self._line_color, 2)
        painter.setPen(pen)
        for start, end in connections:
            painter.drawLine(start, end)

        # 绘制中心大矩形
        center_pen = QPen(self._border_color, 3)
        painter.setPen(center_pen)
        painter.setBrush(QColor(230, 240, 255))
        painter.drawRoundedRect(center_rect, 8, 8)

        # 文本："请选择诊断端口"
        painter.setPen(self._text_color)
        font = QFont(self.font())
        font.setPointSize(max(10, int(h * 0.035)))
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(center_rect, Qt.AlignCenter, "请选择诊断端口")

        # 绘制节点矩形与标签（固定大小）
        node_pen = QPen(self._node_border, 2)
        painter.setPen(node_pen)
        painter.setBrush(QColor(245, 245, 245))

        node_font = QFont(self.font())
        node_font.setPointSize(max(9, int(h * 0.025)))
        node_font.setBold(False)
        painter.setFont(node_font)

        def draw_node(label: str, rect: QRectF):
            painter.drawRoundedRect(rect, 6, 6)
            painter.drawText(rect, Qt.AlignCenter, label)

        for label, rect in top_nodes:
            draw_node(label, rect)
        for label, rect in bottom_nodes:
            draw_node(label, rect)

    def setLabels(self, top_labels=None, bottom_labels=None):
        if top_labels is not None:
            self._top_labels = list(top_labels)
        if bottom_labels is not None:
            self._bottom_labels = list(bottom_labels)
        self.update()


if __name__ == "__main__":
    from PyQt5.QtWidgets import QApplication
    import sys
    app = QApplication(sys.argv)
    w = NetworkTopologyWidget()
    w.resize(900, 600)
    w.setWindowTitle("拓扑图预览")
    w.show()
    sys.exit(app.exec_())

