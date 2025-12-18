import sys
from PyQt5 import QtGui, QtWidgets
from PyQt5.QtCore import Qt, QSize, QPointF, QPropertyAnimation, QEasingCurve, QRectF, QPoint
from PyQt5.QtGui import QPainter, QPen, QBrush, QColor, QFont, QFontMetrics
from PyQt5.QtWidgets import (
    QWidget, QApplication, QVBoxLayout, QGraphicsView, QGraphicsScene,
    QGraphicsItem, QHBoxLayout, QPushButton, QLabel, QFrame, QScrollArea,
    QGridLayout, QFormLayout
)
from app.modules.device_topology.view.network_status import NetworkStatusPanel


# 将 status_text 作为独立函数定义在类之前
def status_text(status):
    """根据状态值返回中文文本"""
    STATUS_MAP = {
        "online": "在线",
        "offline": "离线",
    }
    return STATUS_MAP.get(status, "未知")


class TopologyNode:
    """节点数据类"""

    def __init__(self, node_id, node_name, connection_note):
        self.node_id = node_id
        self.node_name = node_name
        self.connection_note = connection_note
        self.status = "online"  # 默认在线
        self.position = QPoint(0, 0)  # 节点位置
        self.size = QSize(140, 70)  # 节点大小

    @property
    def color(self):
        """根据状态返回颜色"""
        if self.status == "online":
            return QColor("#10B981")  # 绿色 (Success)
        elif self.status == "offline":
            return QColor("#EF4444")  # 红色 (Error)
        else:
            return QColor("#9CA3AF")  # 灰色 (Disabled)

    @property
    def border_color(self):
        if self.status == "online":
            return QColor("#059669")
        elif self.status == "offline":
            return QColor("#DC2626")
        else:
            return QColor("#6B7280")


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

        # 阴影效果
        path = QtGui.QPainterPath()
        path.addRoundedRect(rect.translated(2, 2), 8, 8)
        painter.fillPath(path, QColor(0, 0, 0, 30))

        if self.is_main:
            brush_color = QColor("#3B82F6") # 主题蓝
            pen_color = QColor("#2563EB")
        else:
            brush_color = self.node.color
            pen_color = self.node.border_color

        # 绘制背景
        painter.setPen(QPen(pen_color, 1.5))
        painter.setBrush(QBrush(brush_color))
        painter.drawRoundedRect(rect, 8, 8)

        # 绘制文字
        painter.setPen(Qt.white)
        name_font = QFont("Segoe UI", 10, QFont.Bold)
        painter.setFont(name_font)

        # 节点名称可能有多行，居中绘制
        text_rect = rect.adjusted(5, 5, -5, -20 if not self.is_main else -5)
        painter.drawText(text_rect, Qt.AlignCenter | Qt.TextWordWrap, self.node.node_name)

        if not self.is_main:
            status_font = QFont("Segoe UI", 8)
            painter.setFont(status_font)
            status_rect = QRectF(rect.left(), rect.bottom() - 22, rect.width(), 20)

            # 状态背景条 (半透明)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(0, 0, 0, 40))
            path_status = QtGui.QPainterPath()
            path_status.addRoundedRect(rect.adjusted(0, rect.height()-22, 0, 0), 8, 8)
            # 只保留下半部分的圆角，这里简单处理，直接画矩形覆盖上半部分圆角
            painter.drawRoundedRect(rect.adjusted(0, rect.height()-22, 0, 0), 8, 8)

            painter.setPen(Qt.white)
            painter.drawText(status_rect, Qt.AlignCenter, f"{status_text(self.node.status)}")

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
        self.font = QFont("Segoe UI", 8)
        metrics = QFontMetrics(self.font)
        width = max(80, metrics.horizontalAdvance(self.text) + 16)
        height = metrics.height() + 8
        self.rect = QRectF(-width / 2, -height / 2, width, height)
        self.setPos(center_point)
        self.setZValue(2)

    def boundingRect(self):
        return self.rect.adjusted(-1, -1, 1, 1)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)

        # 背景
        painter.setPen(QPen(QColor("#E5E7EB"), 1))
        painter.setBrush(QBrush(QColor("#FFFFFF")))
        painter.drawRoundedRect(self.rect, 12, 12)

        # 文字
        painter.setFont(self.font)
        painter.setPen(QColor("#4B5563"))
        painter.drawText(self.rect, Qt.AlignCenter, self.text)


class TopologyWidget(QGraphicsView):
    """支持缩放和滚动的拓扑图视图，内置透明悬浮工具栏"""

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
        self.top_margin = 180
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

        # 创建透明悬浮工具栏
        self._init_transparent_toolbar()

        self.init_nodes(node_data)
        self.layout_nodes()
        self.setMinimumSize(800, 500)

    def _init_transparent_toolbar(self):
        """初始化透明悬浮工具栏"""
        # 工具栏容器 - 完全随移再看拓扑图
        self.toolbar = QWidget(self)

        # 关键：启用背景透明
        self.toolbar.setAttribute(Qt.WA_TranslucentBackground)

        # 现代风格工具栏：白色背景，轻微阴影，圆角
        self.toolbar.setStyleSheet("""
            QWidget {
                background-color: rgba(255, 255, 255, 0.95);
                border: 1px solid #E5E7EB;
                border-radius: 12px;
            }
        """)

        # 添加阴影
        shadow = QtWidgets.QGraphicsDropShadowEffect(self.toolbar)
        shadow.setBlurRadius(15)
        shadow.setColor(QColor(0, 0, 0, 20))
        shadow.setOffset(0, 2)
        self.toolbar.setGraphicsEffect(shadow)

        # 工具栏布局
        toolbar_layout = QHBoxLayout(self.toolbar)
        toolbar_layout.setContentsMargins(8, 6, 8, 6)
        toolbar_layout.setSpacing(8)

        # 存储面板映射
        self.panels = {}

        # 初始化各个信息面板的内容 Widget
        self._init_info_widgets()

        # 添加工具按钮 - 使用更紧凑的设计
        self._add_tool_button("车辆信息", toolbar_layout, self.vehicle_info_widget)
        self._add_tool_button("服务状态信息", toolbar_layout, self.service_status_widget)
        self._add_tool_button("证书信息", toolbar_layout, self.security_info_widget)
        self._add_tool_button("网络管理", toolbar_layout, self.network_mgmt_widget)
        self._add_tool_button("储存信息", toolbar_layout, self.storage_info_widget)
        self._add_tool_button("以太网网络诊断", toolbar_layout, self.network_diag_widget)

        toolbar_layout.addStretch()

        # 关闭所有按钮
        close_all_btn = QPushButton("✕")
        close_all_btn.setToolTip("关闭所有面板")
        close_all_btn.clicked.connect(self.hide_all_panels)
        close_all_btn.setFixedSize(28, 28)
        close_all_btn.setCursor(Qt.PointingHandCursor)
        close_all_btn.setStyleSheet("""
            QPushButton {
                background-color: #FEE2E2;
                color: #EF4444;
                border: none;
                border-radius: 14px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #FECACA;
                color: #DC2626;
            }
            QPushButton:pressed {
                background-color: #FCA5A5;
            }
        """)
        toolbar_layout.addWidget(close_all_btn)

        # 初始位置和大小 - 在resizeEvent中会调整
        self.toolbar.setGeometry(10, 10, 200, 50)

    def _init_info_widgets(self):
        """初始化各个信息面板的内容 Widget"""

        def create_styled_label(text, is_value=False):
            lbl = QLabel(text)
            if is_value:
                lbl.setStyleSheet("color: #111827; font-weight: 500;")
            else:
                lbl.setStyleSheet("color: #6B7280; font-weight: 600;")
            return lbl

        def setup_form_layout(widget, labels_dict, rows):
            layout = QFormLayout(widget)
            layout.setSpacing(12)
            layout.setLabelAlignment(Qt.AlignRight)

            for key, label_text in rows:
                val_label = create_styled_label("—", is_value=True)
                labels_dict[key] = val_label
                layout.addRow(create_styled_label(label_text), val_label)

        # 1. 车辆信息
        self.vehicle_info_widget = QWidget()
        self.vehicle_labels = {}
        setup_form_layout(self.vehicle_info_widget, self.vehicle_labels, [
            ("vin", "VIN码："),
            ("vehicle_mode", "车辆模式："),
            ("user_mode", "用户模式："),
            ("factory_mode", "工厂模式："),
            ("voltage", "电压值：")
        ])

        # 2. 服务状态信息
        self.service_status_widget = QWidget()
        self.status_labels = {}
        setup_form_layout(self.service_status_widget, self.status_labels, [
            ("srv_id01", "SrvID01："),
            ("srv_id02", "SrvID02："),
            ("srv_id03", "SrvID03：")
        ])

        # 3. 证书信息
        self.security_info_widget = QWidget()
        self.sec_labels = {}
        setup_form_layout(self.security_info_widget, self.sec_labels, [
            ("cert_server", "证书服务器："),
            ("pki_status", "PKI服务状态："),
            ("cert_valid_date", "证书有效日期："),
            ("key_slot_status", "密钥槽状态："),
            ("tls_switch", "TLS开关状态："),
            ("secoc_switch", "SecOC开关状态："),
            ("cms_env", "CMS环境：")
        ])

        # 4. 网络管理
        self.network_mgmt_widget = QWidget()
        self.net_labels = {}
        setup_form_layout(self.network_mgmt_widget, self.net_labels, [
            ("power_wake_source", "电源唤醒源："),
            ("pnc", "PNC："),
            ("rt1_net_source", "RT1网络维持源："),
            ("rt2_net_source", "RT2网络维持源："),
            ("rt1_ext_msg", "RT1外网报文情况："),
            ("rt2_ext_msg", "RT2外网报文情况："),
            ("a_core_net_req", "A核应用网络请求："),
            ("obd_can_net", "OBD_CAN网络情况：")
        ])

        # 5. 存储信息
        self.storage_info_widget = QWidget()
        self.storage_labels = {}
        setup_form_layout(self.storage_info_widget, self.storage_labels, [
            ("a_core_storage", "A核存储情况："),
            ("m_core_storage", "M核存储情况：")
        ])

        # 6. 以太网网络诊断
        self.network_diag_widget = NetworkStatusPanel()

    def _add_tool_button(self, text, layout, content_widget=None):
        """添加透明工具按钮"""
        btn = QPushButton(text)
        btn.setCheckable(True)
        btn.setCursor(Qt.PointingHandCursor)

        # 按钮样式 - 扁平化设计
        btn.setStyleSheet("""
            QPushButton {
                padding: 6px 16px;
                background-color: transparent;
                color: #4B5563;
                border: 1px solid transparent;
                border-radius: 6px;
                font-family: "Segoe UI", "Microsoft YaHei";
                font-weight: 600;
                font-size: 10pt;
            }
            QPushButton:hover {
                background-color: #F3F4F6;
                color: #1F2937;
            }
            QPushButton:checked {
                background-color: #EFF6FF;
                color: #2563EB;
                border: 1px solid #BFDBFE;
            }
        """)

        panel = FloatingPanel(text, self.window(), content_widget)
        self.panels[btn] = panel

        btn.clicked.connect(lambda checked, b=btn: self._show_panel(b))
        layout.addWidget(btn)

    def update_vehicle_info(self, info: dict):
        self.vehicle_labels["vin"].setText(info.get("vin", "—"))
        self.vehicle_labels["vehicle_mode"].setText(info.get("vehicle_mode", "—"))
        self.vehicle_labels["user_mode"].setText(info.get("user_mode", "—"))
        self.vehicle_labels["factory_mode"].setText(info.get("factory_mode", "—"))
        self.vehicle_labels["voltage"].setText(info.get("voltage", "—"))

    def update_service_status_info(self, info: dict):
        self.status_labels["srv_id01"].setText(info.get("srv_id01", "—"))
        self.status_labels["srv_id02"].setText(info.get("srv_id02", "—"))
        self.status_labels["srv_id03"].setText(info.get("srv_id03", "—"))

    def update_security_info(self, info: dict):
        self.sec_labels["cert_server"].setText(info.get("cert_server", "—"))
        self.sec_labels["pki_status"].setText(info.get("pki_status", "—"))
        self.sec_labels["cert_valid_date"].setText(info.get("cert_valid_date", "—"))
        self.sec_labels["key_slot_status"].setText(info.get("key_slot_status", "—"))
        self.sec_labels["tls_switch"].setText(info.get("tls_switch", "—"))
        self.sec_labels["secoc_switch"].setText(info.get("secoc_switch", "—"))
        self.sec_labels["cms_env"].setText(info.get("cms_env", "—"))

    def update_network_mgmt(self, info: dict):
        self.net_labels["power_wake_source"].setText(info.get("power_wake_source", "—"))
        self.net_labels["pnc"].setText(info.get("pnc", "—"))
        self.net_labels["rt1_net_source"].setText(info.get("rt1_net_source", "—"))
        self.net_labels["rt2_net_source"].setText(info.get("rt2_net_source", "—"))
        self.net_labels["rt1_ext_msg"].setText(info.get("rt1_ext_msg", "—"))
        self.net_labels["rt2_ext_msg"].setText(info.get("rt2_ext_msg", "—"))
        self.net_labels["a_core_net_req"].setText(info.get("a_core_net_req", "—"))
        self.net_labels["obd_can_net"].setText(info.get("obd_can_net", "—"))

    def update_storage_info(self, info: dict):
        self.storage_labels["a_core_storage"].setText(info.get("a_core_storage", "—"))
        self.storage_labels["m_core_storage"].setText(info.get("m_core_storage", "—"))

    def _show_panel(self, button):
        """显示面板"""
        panel = self.panels[button]

        if panel.isVisible():
            panel.hide()
            button.setChecked(False)
        else:
            self.hide_all_panels()

            # 计算面位位置：相对于按钮
            global_pos = button.mapToGlobal(button.rect().bottomLeft())
            global_pos.setY(global_pos.y() + 8)
            panel.show_at(global_pos)
            button.setChecked(True)

    def hide_all_panels(self):
        """隐藏所有面板"""
        if hasattr(self, 'panels'):
            for btn, panel in self.panels.items():
                panel.hide()
                btn.setChecked(False)

    def resizeEvent(self, event):
        """调整工具栏大小和位置"""
        super().resizeEvent(event)
        # 工具栏宽度比视图小20px（左右各10px边距）
        self.toolbar.setGeometry(10, 10, self.viewport().width() - 20, 46)
        self.hide_all_panels()

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
        main_node_y = self.top_margin + main_size.height() / 2 + 60  # 为工具栏留空间
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
        self.setSceneRect(rect)

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
        delta = event.angleDelta().y() if event.angleDelta().y() else event.pixelDelta().y()
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


class FloatingPanel(QWidget):
    """浮动信息面板"""

    def __init__(self, title, parent=None, content_widget=None):
        super().__init__(parent)
        self.title = title
        self.animation = None
        self.custom_content = content_widget
        self.init_ui()

    def init_ui(self):
        """初始化面板UI"""
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # 主容器，用于绘制阴影
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10) # 留出阴影空间

        main_frame = QFrame(self)
        main_frame.setObjectName("FloatingPanelFrame")
        main_frame.setStyleSheet("""
            QFrame#FloatingPanelFrame {
                background-color: #FFFFFF;
                border: 1px solid #E5E7EB;
                border-radius: 12px;
            }
        """)

        # 添加阴影效果
        shadow = QtWidgets.QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 40))
        shadow.setOffset(0, 4)
        main_frame.setGraphicsEffect(shadow)

        layout = QVBoxLayout(main_frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 标题栏
        title_bar = QWidget(main_frame)
        title_bar.setStyleSheet("""
            QWidget {
                background-color: #F9FAFB;
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
                border-bottom: 1px solid #E5E7EB;
            }
        """)

        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(16, 12, 12, 12)

        title_label = QLabel(self.title)
        title_label.setStyleSheet("""
            color: #1F2937; 
            font-family: "Segoe UI", "Microsoft YaHei";
            font-size: 11pt; 
            font-weight: 600;
        """)
        title_layout.addWidget(title_label)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #9CA3AF;
                border: none;
                border-radius: 12px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #FEE2E2;
                color: #EF4444;
            }
        """)
        close_btn.clicked.connect(self.hide)
        title_layout.addWidget(close_btn)

        # 内容区域
        content_area = QScrollArea(main_frame)
        content_area.setWidgetResizable(True)
        content_area.setFrameShape(QFrame.NoFrame)
        content_area.setStyleSheet("""
            QScrollArea {
                background-color: transparent;
                border: none;
            }
            QWidget {
                background-color: transparent;
            }
            QScrollBar:vertical {
                border: none;
                background: #F3F4F6;
                width: 8px;
                margin: 0px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: #D1D5DB;
                min-height: 20px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical:hover {
                background: #9CA3AF;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(20, 20, 20, 20)
        content_layout.setSpacing(16)

        self.add_panel_content(content_layout)

        content_area.setWidget(content_widget)

        layout.addWidget(title_bar)
        layout.addWidget(content_area)

        main_layout.addWidget(main_frame)

        self.setFixedSize(420, 380)
        self.hide()

    def add_panel_content(self, layout):
        """添加面板内容"""
        if self.custom_content:
            layout.addWidget(self.custom_content)
        else:
            label = QLabel(
                f"这里是 {self.title} 的详细内容。\n\n您可以在此添加：\n• 设备详细信息\n• 实时状态监控\n• 配置参数\n• 统计数据\n• 操作按钮等")
            label.setWordWrap(True)
            label.setStyleSheet("color: #333; line-height: 1.5;")
            layout.addWidget(label)

            grid_layout = QGridLayout()
            grid_layout.setSpacing(10)

            data = [("设备ID", "STATUS-001"), ("类型", "网络交换机"), ("IP地址", "192.168.1.1"),
                    ("固件版本", "v2.5.1"), ("运行时间", "45天3小时")]

            for i, (key, value) in enumerate(data):
                key_label = QLabel(key + ":")
                key_label.setStyleSheet("font-weight: bold; color: #666;")
                value_label = QLabel(value)
                value_label.setStyleSheet("color: #333;")
                grid_layout.addWidget(key_label, i, 0)
                grid_layout.addWidget(value_label, i, 1)

            layout.addLayout(grid_layout)
        layout.addStretch()

    def show_at(self, pos):
        """在指定位置显示面板"""
        self.move(pos)

        self.animation = QPropertyAnimation(self, b"windowOpacity")
        self.animation.setDuration(200)
        self.animation.setStartValue(0)
        self.animation.setEndValue(1)
        self.animation.setEasingCurve(QEasingCurve.OutQuad)

        self.show()
        self.animation.start()

    def hide(self):
        """隐藏面板"""
        if hasattr(self, 'animation') and self.animation and self.animation.state() == QPropertyAnimation.Running:
            self.animation.stop()

        self.animation = QPropertyAnimation(self, b"windowOpacity")
        self.animation.setDuration(150)
        self.animation.setStartValue(1)
        self.animation.setEndValue(0)
        self.animation.setEasingCurve(QEasingCurve.InQuad)
        self.animation.finished.connect(super().hide)
        self.animation.start()


class SimpleTopologyWindow(QWidget):
    """拓扑图主窗口"""

    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        """初始化UI"""
        self.setWindowTitle("网络拓扑图 - 网络管理系统")
        self.setGeometry(10, 10, 1400, 800)
        self.setStyleSheet("background-color: #F9FAFB;")

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
    app.setStyle('Fusion')

    # 设置全局样式
    app.setStyleSheet("""
        QMainWindow, QWidget {
            background-color: #ecf0f1;
        }
        QLabel {
            color: #2c3e50;
        }
    """)

    window = SimpleTopologyWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()