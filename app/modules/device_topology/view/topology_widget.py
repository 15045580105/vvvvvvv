import sys
from PyQt5.QtWidgets import (
    QWidget,
    QApplication,
    QVBoxLayout,
    QGraphicsView,
    QGraphicsScene,
    QGraphicsItem,
)
from PyQt5.QtCore import Qt, QPoint, QRect, QSize, QPointF, QRectF
from PyQt5.QtGui import QPainter, QPen, QBrush, QColor, QFont, QFontMetrics


class TopologyNode:
    """节点数据类"""

    def __init__(self, node_id, node_name, connection_note):
        self.node_id = node_id
        self.node_name = node_name
        self.connection_note = connection_note
        self.status = "online"  # 默认在线
        self.position = QPoint(0, 0)  # 节点位置
        self.size = QSize(120, 60)  # 节点大小

    @property
    def color(self):
        """根据状态返回颜色"""
        if self.status == "online":
            return QColor(76, 175, 80)  # 绿色
        elif self.status == "offline":
            return QColor(244, 67, 54)  # 红色
        else:
            return QColor(158, 158, 158)  # 灰色


class NodeGraphicsItem(QGraphicsItem):
    """场景中的节点图元"""

    def __init__(self, node, is_main=False):
        super().__init__()
        self.node = node
        self.is_main = is_main
        self.setAcceptedMouseButtons(Qt.NoButton)

    def boundingRect(self):
        half_w = self.node.size.width() / 2
        half_h = self.node.size.height() / 2
        return QRectF(-half_w, -half_h, self.node.size.width(), self.node.size.height())

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.boundingRect()
        painter.setPen(QPen(QColor(33, 33, 33), 2))

        if self.is_main:
            brush_color = QColor(66, 165, 245)
        else:
            brush_color = self.node.color

        painter.setBrush(QBrush(brush_color))
        painter.drawRoundedRect(rect, 10, 10)

        painter.setPen(Qt.white)
        name_font = QFont("Arial", 12 if self.is_main else 10, QFont.Bold if self.is_main else QFont.Normal)
        painter.setFont(name_font)
        painter.drawText(rect, Qt.AlignCenter, self.node.node_name)

        if not self.is_main:
            status_font = QFont("Arial", 9)
            painter.setFont(status_font)
            status_rect = QRectF(rect.left(), rect.bottom() - 25, rect.width(), 25)
            painter.drawText(status_rect, Qt.AlignCenter, f"状态: {TopologyWidget.status_text(self.node.status)}")

    def set_size(self, size):
        if size != self.node.size:
            self.prepareGeometryChange()
            self.node.size = size

    def update_status(self, status):
        self.node.status = status
        self.update()


class ConnectionLabelItem(QGraphicsItem):
    """连接线上方的备注标签"""

    def __init__(self, text, center_point):
        super().__init__()
        self.text = text
        self.font = QFont("Arial", 9)
        metrics = QFontMetrics(self.font)
        width = max(120, metrics.horizontalAdvance(self.text) + 20)
        height = metrics.height() + 12
        self.rect = QRectF(-width / 2, -height / 2, width, height)
        self.setPos(center_point)
        self.setZValue(2)

    def boundingRect(self):
        return self.rect.adjusted(-2, -2, 2, 2)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setFont(self.font)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(255, 255, 255, 220)))
        painter.drawRoundedRect(self.rect, 5, 5)
        painter.setPen(QPen(QColor(200, 200, 200), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(self.rect, 5, 5)
        painter.setPen(QColor(0, 0, 0))
        painter.drawText(self.rect, Qt.AlignCenter, self.text)


class TopologyWidget(QGraphicsView):
    """支持缩放和滚动的拓扑图视图"""

    STATUS_MAP = {
        "online": "在线",
        "offline": "离线",
    }

    def __init__(self, node_data, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)

        self.main_node = None
        self.main_node_item = None
        self.child_nodes = []
        self.node_items = {}
        self.connection_items = []

        self.node_spacing = 180
        self.vertical_gap = 250
        self.padding = 100
        self.top_margin = 20
        self.bottom_margin = 350

        self._current_scale = 1.0
        self._min_scale = 0.3
        self._max_scale = 2.5
        self._panning = False
        self._pan_start = QPoint()

        self.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setDragMode(QGraphicsView.NoDrag)

        self.init_nodes(node_data)
        self.layout_nodes()
        self.setMinimumSize(800, 500)

    @staticmethod
    def status_text(status):
        return TopologyWidget.STATUS_MAP.get(status, "未知")

    def init_nodes(self, node_data):
        self.main_node = TopologyNode(0, "主交换机\nMAIN SWITCH", "")
        self.main_node_item = NodeGraphicsItem(self.main_node, is_main=True)
        self.scene.addItem(self.main_node_item)
        self.node_items[0] = self.main_node_item

        for node_id, node_name, connection_note in node_data:
            node = TopologyNode(node_id, node_name, connection_note)
            self.child_nodes.append(node)
            item = NodeGraphicsItem(node)
            self.node_items[node_id] = item
            self.scene.addItem(item)

    def layout_nodes(self):
        if not self.main_node_item:
            return

        self._clear_connections()
        main_size = self.calculate_main_node_size()
        self.main_node_item.set_size(main_size)

        center_x = 0.0
        # 主节点紧贴上方显示，仅保留很小的顶部空白
        main_node_y = self.top_margin + main_size.height() / 2
        self.main_node_item.setPos(center_x, main_node_y)

        child_count = len(self.child_nodes)
        if child_count == 0:
            self._update_scene_rect()
            return

        child_width = self.child_nodes[0].size.width()
        total_child_width = (child_count - 1) * self.node_spacing + child_width
        start_x = center_x - total_child_width / 2 + child_width / 2
        child_y = main_node_y + self.vertical_gap

        main_left = center_x - main_size.width() / 2
        main_right = center_x + main_size.width() / 2
        main_bottom_y = main_node_y + main_size.height() / 2

        for index, node in enumerate(self.child_nodes):
            child_center_x = start_x + index * self.node_spacing
            if child_center_x < main_left + self.padding:
                connection_x = main_left + self.padding
            elif child_center_x > main_right - self.padding:
                connection_x = main_right - self.padding
            else:
                connection_x = child_center_x

            item = self.node_items[node.node_id]
            item.setPos(child_center_x, child_y)

            node_top_y = child_y - node.size.height() / 2
            self._add_connection(connection_x, main_bottom_y, node_top_y, node.connection_note)

        self._update_scene_rect()
        self.centerOn(self.main_node_item)

    def _add_connection(self, connection_x, main_bottom_y, node_top_y, note):
        pen = QPen(QColor(100, 100, 100), 2)
        line_item = self.scene.addLine(connection_x, main_bottom_y, connection_x, node_top_y, pen)
        line_item.setZValue(0)
        self.connection_items.append(line_item)

        if note:
            mid_point = QPointF(connection_x, (main_bottom_y + node_top_y) / 2)
            label_item = ConnectionLabelItem(note, mid_point)
            self.scene.addItem(label_item)
            self.connection_items.append(label_item)

    def _clear_connections(self):
        for item in self.connection_items:
            self.scene.removeItem(item)
        self.connection_items.clear()

    def _update_scene_rect(self):
        if self.scene.items():
            rect = self.scene.itemsBoundingRect().adjusted(
                -self.padding,
                -self.top_margin,
                self.padding,
                self.bottom_margin,
            )
        else:
            rect = QRectF(-500, -350, 1000, 700)
        self.scene.setSceneRect(rect)

    def calculate_main_node_size(self):
        child_count = len(self.child_nodes)
        if child_count == 0:
            return QSize(500, 80)

        total_child_width = (child_count - 1) * self.node_spacing + self.child_nodes[0].size.width()
        main_width = total_child_width + 2 * self.padding
        min_width = 600
        main_width = max(main_width, min_width)
        extra_width = int(total_child_width * 0.1)
        main_width = max(main_width, total_child_width + extra_width)
        main_height = 80
        return QSize(main_width, main_height)

    def update_node_status(self, node_id, status):
        item = self.node_items.get(node_id)
        if not item:
            return
        item.update_status(status)

    def wheelEvent(self, event):
        delta = event.angleDelta().y() or event.pixelDelta().y()
        if delta == 0:
            return
        zoom_factor = 1.15 if delta > 0 else 1 / 1.15
        new_scale = self._current_scale * zoom_factor
        if new_scale < self._min_scale or new_scale > self._max_scale:
            return
        self._current_scale = new_scale
        self.scale(zoom_factor, zoom_factor)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._panning = True
            self._pan_start = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._panning:
            delta = event.pos() - self._pan_start
            self._pan_start = event.pos()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._panning:
            self._panning = False
            self.setCursor(Qt.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event):
        if self._panning:
            self._panning = False
            self.setCursor(Qt.ArrowCursor)
        super().leaveEvent(event)

    def sizeHint(self):
        return QSize(1000, 700)

    def minimumSizeHint(self):
        return QSize(600, 400)


class SimpleTopologyWindow(QWidget):
    """简单的拓扑图窗口，只显示拓扑图"""

    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        """初始化UI"""
        self.setWindowTitle("网络拓扑图")
        self.setGeometry(10, 10, 1400, 800)

        # 创建示例数据
        node_data = [
            (1, "激光雷达\nLidar", "100M"),
            (2, "调试口", "100M"),
            (3, "IFC", "100M"),
            (4, "ADC_MCU", "SGMII(1G)"),
            (5, "ADC_SOC", "SGMII(2.5G)"),
            (6, "DLP(预留)", "100M"),
            (7, "DLP(预留)", "100M"),
            (8, "预留", "100M"),
            (9, "OBD", "TX"),
            (10, "IDC/8538", "PCIe"),
            (11, "IDC/8838", "SGMII"),
        ]

        # 创建拓扑图
        self.topology = TopologyWidget(node_data)

        # 主布局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.topology)


def main():
    """主函数"""
    app = QApplication(sys.argv)

    # 设置应用程序样式
    app.setStyle('Fusion')

    # 创建测试窗口
    window = SimpleTopologyWindow()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()