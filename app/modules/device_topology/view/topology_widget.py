import sys
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from PyQt5 import QtGui, QtWidgets
from PyQt5.QtCore import Qt, QSize, QPointF, QPropertyAnimation, QEasingCurve, QRectF, QPoint, pyqtSignal
from PyQt5.QtGui import QPainter, QPen, QBrush, QColor, QFont, QFontMetrics
from PyQt5.QtWidgets import (
    QWidget, QApplication, QVBoxLayout, QGraphicsView, QGraphicsScene,
    QGraphicsItem, QHBoxLayout, QPushButton, QLabel, QFrame, QScrollArea,
    QGridLayout, QFormLayout, QTextEdit, QFileDialog, QMessageBox, QLineEdit
)
import json

from app.common.ui.widgets import ModernButton
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
        self.size = QSize(160, 80)  # 节点大小

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
        name_font = QFont("Segoe UI", 12, QFont.Bold)
        painter.setFont(name_font)

        # 节点名称可能有多行，居中绘制
        text_rect = rect.adjusted(5, 5, -5, -20 if not self.is_main else -5)
        painter.drawText(text_rect, Qt.AlignCenter | Qt.TextWordWrap, self.node.node_name)

        if not self.is_main:
            status_font = QFont("Segoe UI", 9)
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
        self.font = QFont("Segoe UI", 9)
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

    request_info_update = pyqtSignal(str)  # 新增信号：请求更新信息，参数为信息类型标识

    def __init__(self, node_data, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)

        self.main_node = None
        self.main_node_item = None
        self.child_nodes = []
        self.node_items = {}
        self.connection_items = []

        self.node_spacing = 220
        self.vertical_gap = 120
        self.padding = 50
        self.top_margin = 100
        self.bottom_margin = 150

        self._current_scale = 1.0
        self._min_scale = 0.3
        self._max_scale = 2.5
        self._panning = False
        self._pan_start = QPoint()
        self._auto_fit_enabled = True
        self._fit_padding = 12

        if not hasattr(self, '_fit_topology_to_view'):
            self._fit_topology_to_view = self._fallback_fit_topology_to_view

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
        # self.setMinimumSize(800, 500)

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

        self._add_tool_button("车辆信息", toolbar_layout, self.vehicle_info_widget, initial_size=(850, 500))
        self._add_tool_button("服务状态信息", toolbar_layout, self.service_status_widget, initial_size=(850, 500))
        self._add_tool_button("证书信息", toolbar_layout, self.security_info_widget, initial_size=(850, 500))
        self._add_tool_button("网络管理", toolbar_layout, self.network_mgmt_widget, initial_size=(850, 500))
        self._add_tool_button("储存信息", toolbar_layout, self.storage_info_widget, initial_size=(850, 500))
        self._add_tool_button("版本信息", toolbar_layout, self.version_info_widget, initial_size=(850, 500))
        self._add_tool_button("以太网网络诊断", toolbar_layout, self.network_diag_widget, initial_size=(850, 500))

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
                val_label.setWordWrap(True) # 允许长文本换行
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
        # 使用 QScrollArea 来支持长内容

        layout = QVBoxLayout(self.service_status_widget)
        # 移除默认的外边距，因为外层 FloatingPanel 已经有了
        layout.setContentsMargins(0, 0, 0, 0)

        # ---------------------
        # 新增 Search Bar
        # ---------------------
        search_widget = QWidget()
        search_layout = QHBoxLayout(search_widget)
        search_layout.setContentsMargins(0, 0, 0, 4)
        search_layout.setSpacing(6)

        self.status_search_input = QLineEdit()
        self.status_search_input.setPlaceholderText("查找内容...")
        self.status_search_input.setStyleSheet("""
            QLineEdit {
                border: 1px solid #D1D5DB;
                border-radius: 4px;
                padding: 4px 8px;
                background-color: #FFFFFF;
                color: #374151;
            }
            QLineEdit:focus {
                border: 1px solid #3B82F6;
            }
        """)
        self.status_search_input.textChanged.connect(self._on_service_status_search)

        self.status_search_label = QLabel("0/0")
        self.status_search_label.setStyleSheet("color: #6B7280; font-size: 12px;")
        self.status_search_label.setFixedWidth(50)
        self.status_search_label.setAlignment(Qt.AlignCenter)

        # 查找上一个
        btn_prev = QPushButton("▲")
        btn_prev.setFixedSize(24, 24)
        btn_prev.setCursor(Qt.PointingHandCursor)
        btn_prev.setToolTip("查找上一个")
        btn_prev.clicked.connect(lambda: self._find_service_status_text(backwards=True))
        btn_prev.setStyleSheet("QPushButton { border: 1px solid #E5E7EB; border-radius: 4px; color: #4B5563; } QPushButton:hover { background-color: #F3F4F6; }")

        # 查找下一个
        btn_next = QPushButton("▼")
        btn_next.setFixedSize(24, 24)
        btn_next.setCursor(Qt.PointingHandCursor)
        btn_next.setToolTip("查找下一个")
        btn_next.clicked.connect(lambda: self._find_service_status_text(backwards=False))
        btn_next.setStyleSheet("QPushButton { border: 1px solid #E5E7EB; border-radius: 4px; color: #4B5563; } QPushButton:hover { background-color: #F3F4F6; }")

        search_layout.addWidget(self.status_search_input)
        search_layout.addWidget(self.status_search_label)
        search_layout.addWidget(btn_prev)
        search_layout.addWidget(btn_next)

        layout.addWidget(search_widget)

        self.status_labels = {} # 保持字典结构兼容，虽然我们这里用 QTextEdit

        # 详细文本区域
        self.service_status_text = QTextEdit()
        self.service_status_text.setReadOnly(True)
        self.service_status_text.setStyleSheet("""
            QTextEdit {
                border: 1px solid #E5E7EB;
                border-radius: 6px;
                background-color: #F9FAFB;
                padding: 4px;
                font-family: "Consolas", "Courier New", monospace;
                font-size: 9pt;
            }
        """)
        layout.addWidget(self.service_status_text)
        self.status_labels["service_status_info"] = self.service_status_text # 映射到 key

        # 下载按钮区域
        download_layout = QHBoxLayout()
        download_layout.addStretch()

        self.download_btn = QPushButton("💾 下载数据(Excel)")
        self.download_btn.setCursor(Qt.PointingHandCursor)
        self.download_btn.setStyleSheet("""
                  QPushButton {
                      padding: 6px 12px;
                      background-color: #EFF6FF;
                      color: #2563EB;
                      border: 1px solid #BFDBFE;
                      border-radius: 6px;
                      font-weight: 600;
                  }
                  QPushButton:hover {
                      background-color: #DBEAFE;
                  }
              """)
        self.download_btn.clicked.connect(self._on_download_service_status)
        download_layout.addWidget(self.download_btn)

        layout.addLayout(download_layout)

        # 3. 证书信息
        self.security_info_widget = QWidget()
        self.sec_labels = {}
        setup_form_layout(self.security_info_widget, self.sec_labels, [
            ("cert_info", "证书信息："),
            ("key_slot_status", "密钥槽状态："),
            ("cms_env", "CMS环境信息：")
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
        self.storage_info_widget, self.storage_text, s_search_input, s_count_lbl, s_btn_prev, s_btn_next = \
            self._create_searchable_text_widget()
        s_search_input.textChanged.connect(
            lambda: self._perform_search(self.storage_text, s_search_input, s_count_lbl))
        s_btn_prev.clicked.connect(
            lambda: self._perform_find(self.storage_text, s_search_input, s_count_lbl, backwards=True))
        s_btn_next.clicked.connect(
            lambda: self._perform_find(self.storage_text, s_search_input, s_count_lbl, backwards=False))

        # 6. 版本信息
        self.version_info_widget, self.version_text, v_search_input, v_count_lbl, v_btn_prev, v_btn_next = \
            self._create_searchable_text_widget()
        v_search_input.textChanged.connect(
            lambda: self._perform_search(self.version_text, v_search_input, v_count_lbl))
        v_btn_prev.clicked.connect(
            lambda: self._perform_find(self.version_text, v_search_input, v_count_lbl, backwards=True))
        v_btn_next.clicked.connect(
            lambda: self._perform_find(self.version_text, v_search_input, v_count_lbl, backwards=False))

        # 7. 以太网网络诊断
        self.network_diag_widget = NetworkStatusPanel()

    def _on_download_service_status(self):
        """处理服务状态数据下载"""
        if not hasattr(self, 'service_status_text'):
            return

        text_content = self.service_status_text.toPlainText()
        if not text_content or text_content.strip() == "":
            return

        # 尝试提取 JSON 部分
        json_str = text_content
        prefix = "解析格式: "
        if prefix in text_content:
             parts = text_content.split(prefix)
             if len(parts) > 1:
                 json_str = parts[1]

        parsed_data = None
        try:
            parsed_data = json.loads(json_str)
        except json.JSONDecodeError:
            QMessageBox.critical(self, "错误", "无法解析数据格式，只能导出为 TXT")
            return

        if not isinstance(parsed_data, dict) or "services" not in parsed_data:
             QMessageBox.warning(self, "提示", "数据中未找到服务列表")
             return

        services = parsed_data["services"]
        if not services:
             QMessageBox.warning(self, "提示", "服务列表为空")
             return

        # 弹出保存文件对话框
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "保存服务状态数据",
            "service_status.xlsx",
            "Excel Files (*.xlsx);;All Files (*)"
        )

        if not file_path:
            return

        try:
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Service Status"

            # Headers
            headers = [
                "state_time", "service_ip", "ttl", "cycle_time", "service_id",
                "instance_id", "minor_version", "major_version",
                "phase", "reliable_flag", "unreliable_flag", "tcp_port", "udp_port", "eventgroup_ids"
            ]
            ws.append(headers)

            # --- Styling Headers ---
            # 1. 字体加粗，大小12，颜色白色(配合蓝色背景)
            header_font = Font(name='Arial', bold=True, size=12, color="FFFFFF")
            # 2. 蓝色填充 (使用标准蓝色，如 4472C4)
            header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
            # 居中对齐
            header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)

            # 3. 表头高度占两行 (约30)
            ws.row_dimensions[1].height = 30

            thin_border = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'))

            for cell in ws[1]:
                cell.font = header_font
                cell.fill = header_fill
                cell.alignment = header_align
                cell.border = thin_border

            # 初始化列宽字典 (基于表头长度)
            col_widths = {i: len(str(header)) + 4 for i, header in enumerate(headers, 1)}

            # Rows
            for service in services:
                row = []
                for idx, header in enumerate(headers, 1):
                    val = service.get(header, "")
                    # Convert list/dict to string if necessary
                    if isinstance(val, (list, dict)):
                        val = str(val)
                    row.append(val)

                    # 计算列宽：考虑中文字符可能占更宽，这里简单按长度估算
                    # 限制最大宽度以免过宽
                    length = len(str(val))
                    if length > col_widths[idx]:
                        col_widths[idx] = length

                ws.append(row)

                # Apply borders and alignment for the newly added row
                current_row = ws.max_row
                for col_idx in range(1, len(headers) + 1):
                    cell = ws.cell(row=current_row, column=col_idx)
                    cell.border = thin_border
                    # 除了最后一列靠左，其他居中
                    if col_idx == len(headers):
                        cell.alignment = Alignment(horizontal='left', vertical='center', wrap_text=True)
                    else:
                        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)

            # 设置列宽 (自动调整)
            from openpyxl.utils import get_column_letter
            for col_idx, width in col_widths.items():
                # 限制最大宽度 50，最小宽度 10
                adjusted_width = min(max(width * 1.2, 10), 60)
                ws.column_dimensions[get_column_letter(col_idx)].width = adjusted_width

            wb.save(file_path)
            QMessageBox.information(self, "下载成功", f"数据已保存到:\n{file_path}")

        except Exception as e:
            QMessageBox.critical(self, "下载失败", f"保存文件时出错:\n{str(e)}")

    def _add_tool_button(self, text, layout, content_widget=None, initial_size=None):
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

        panel = FloatingPanel(text, self.window(), content_widget, initial_size)
        self.panels[btn] = panel

        # 修改连接逻辑：点击时先触发信号，再显示面板
        btn.clicked.connect(lambda checked, b=btn, t=text: self._on_tool_btn_clicked(b, t))
        layout.addWidget(btn)

    def _on_tool_btn_clicked(self, button, text):
        """工具按钮点击处理"""
        if not button.isChecked():
            # 如果是取消选中（即关闭面板），不需要请求数据
            self._show_panel(button)
            return

        # 发送请求信号
        self.request_info_update.emit(text)
        self._show_panel(button)

    def _on_service_status_search(self):
        """服务状态信息搜索"""
        text = self.status_search_input.text()

        # 清除现有高亮
        cursor = self.service_status_text.textCursor()
        cursor.clearSelection()
        self.service_status_text.setTextCursor(cursor)

        # 重置额外选择
        self.service_status_text.setExtraSelections([])

        if not text:
            self.status_search_label.setText("0/0")
            return

        # 查找所有匹配
        extra_selections = []
        doc = self.service_status_text.document()
        highlight_cursor = QTextEdit.ExtraSelection()
        highlight_cursor.format.setBackground(QColor("#FFFF00"))
        # highlight_cursor.format.setForeground(QColor("#000000"))

        search_cursor = doc.find(text)
        count = 0
        while not search_cursor.isNull():
            count += 1
            highlight_selection = QTextEdit.ExtraSelection()
            highlight_selection.format.setBackground(QColor("#FFFF00"))
            highlight_selection.cursor = search_cursor
            extra_selections.append(highlight_selection)

            search_cursor = doc.find(text, search_cursor)

        self.service_status_text.setExtraSelections(extra_selections)
        self.status_search_label.setText(f"0/{count}")

    def _find_service_status_text(self, backwards=False):
        """查找下一个/上一个"""
        text = self.status_search_input.text()
        if not text:
            return

        # 设置查找标志
        flags = QtGui.QTextDocument.FindFlags()
        if backwards:
            flags |= QtGui.QTextDocument.FindBackward

        found = self.service_status_text.find(text, flags)

        # 如果没找到，尝试从头/尾开始循环查找
        if not found:
            cursor = self.service_status_text.textCursor()
            if backwards:
                cursor.movePosition(QtGui.QTextCursor.End)
            else:
                cursor.movePosition(QtGui.QTextCursor.Start)
            self.service_status_text.setTextCursor(cursor)
            found = self.service_status_text.find(text, flags)

        if found:
            # 更新计数显示逻辑需要知道当前是第几个
            # 这是一个优化的点，简单起见我们只更新总数，或者重新遍历计算索引
            self._update_search_index_display(text)

    def _update_search_index_display(self, text):
        """更新当前选中的索引显示"""
        if not text:
            return

        current_cursor = self.service_status_text.textCursor()
        current_pos = current_cursor.position()

        # 重新遍历计算当前是第几个
        doc = self.service_status_text.document()
        search_cursor = doc.find(text)
        index = 0
        total = 0

        while not search_cursor.isNull():
            total += 1
            # 判断 current_cursor 是否就在 search_cursor 的范围内
            # search_cursor.position() 是匹配文本的末尾
            if search_cursor.position() == current_pos:
                index = total
            search_cursor = doc.find(text, search_cursor)

        self.status_search_label.setText(f"{index}/{total}")

    def _create_searchable_text_widget(self, placeholder="查找内容..."):
        """创建一个带有搜索栏和文本编辑框的Widget"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        # ---------------------
        # Search Bar
        # ---------------------
        search_widget = QWidget()
        search_layout = QHBoxLayout(search_widget)
        search_layout.setContentsMargins(0, 0, 0, 4)
        search_layout.setSpacing(6)

        search_input = QLineEdit()
        search_input.setPlaceholderText(placeholder)
        search_input.setStyleSheet("""
            QLineEdit {
                border: 1px solid #D1D5DB;
                border-radius: 4px;
                padding: 4px 8px;
                background-color: #FFFFFF;
                color: #374151;
            }
            QLineEdit:focus {
                border: 1px solid #3B82F6;
            }
        """)

        count_label = QLabel("0/0")
        count_label.setStyleSheet("color: #6B7280; font-size: 12px;")
        count_label.setFixedWidth(50)
        count_label.setAlignment(Qt.AlignCenter)

        # 查找上一个
        btn_prev = QPushButton("▲")
        btn_prev.setFixedSize(24, 24)
        btn_prev.setCursor(Qt.PointingHandCursor)
        btn_prev.setToolTip("查找上一个")
        btn_prev.setStyleSheet("QPushButton { border: 1px solid #E5E7EB; border-radius: 4px; color: #4B5563; } QPushButton:hover { background-color: #F3F4F6; }")

        # 查找下一个
        btn_next = QPushButton("▼")
        btn_next.setFixedSize(24, 24)
        btn_next.setCursor(Qt.PointingHandCursor)
        btn_next.setToolTip("查找下一个")
        btn_next.setStyleSheet("QPushButton { border: 1px solid #E5E7EB; border-radius: 4px; color: #4B5563; } QPushButton:hover { background-color: #F3F4F6; }")

        search_layout.addWidget(search_input)
        search_layout.addWidget(count_label)
        search_layout.addWidget(btn_prev)
        search_layout.addWidget(btn_next)

        layout.addWidget(search_widget)

        # 详细文本区域
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet("""
            QTextEdit {
                border: 1px solid #E5E7EB;
                border-radius: 6px;
                background-color: #F9FAFB;
                padding: 4px;
                font-family: "Consolas", "Courier New", monospace;
                font-size: 9pt;
            }
        """)
        layout.addWidget(text_edit)

        return widget, text_edit, search_input, count_label, btn_prev, btn_next

    def _perform_search(self, text_edit, search_input, count_label):
        """通用搜索逻辑"""
        text = search_input.text()

        # 清除现有高亮
        cursor = text_edit.textCursor()
        cursor.clearSelection()
        text_edit.setTextCursor(cursor)

        # 重置额外选择
        text_edit.setExtraSelections([])

        if not text:
            count_label.setText("0/0")
            return

        # 查找所有匹配
        extra_selections = []
        doc = text_edit.document()

        search_cursor = doc.find(text)
        count = 0
        while not search_cursor.isNull():
            count += 1
            highlight_selection = QTextEdit.ExtraSelection()
            highlight_selection.format.setBackground(QColor("#FFFF00"))
            highlight_selection.cursor = search_cursor
            extra_selections.append(highlight_selection)

            search_cursor = doc.find(text, search_cursor)

        text_edit.setExtraSelections(extra_selections)
        count_label.setText(f"0/{count}")

    def _perform_find(self, text_edit, search_input, count_label, backwards=False):
        """通用查找上一个/下一个逻辑"""
        text = search_input.text()
        if not text:
            return

        # 设置查找标志
        flags = QtGui.QTextDocument.FindFlags()
        if backwards:
            flags |= QtGui.QTextDocument.FindBackward

        found = text_edit.find(text, flags)

        # 如果没找到，尝试从头/尾开始循环查找
        if not found:
            cursor = text_edit.textCursor()
            if backwards:
                cursor.movePosition(QtGui.QTextCursor.End)
            else:
                cursor.movePosition(QtGui.QTextCursor.Start)
            text_edit.setTextCursor(cursor)
            found = text_edit.find(text, flags)

        if found:
            self._update_search_index_display_generic(text_edit, search_input, count_label)

    def _update_search_index_display_generic(self, text_edit, search_input, count_label):
        """通用更新搜索索引显示"""
        text = search_input.text()
        if not text:
            return

        current_cursor = text_edit.textCursor()
        current_pos = current_cursor.position()

        # 重新遍历计算当前是第几个
        doc = text_edit.document()
        search_cursor = doc.find(text)
        index = 0
        total = 0

        while not search_cursor.isNull():
            total += 1
            # 判断 current_cursor 是否就在 search_cursor 的范围内
            if search_cursor.position() == current_pos:
                index = total
            search_cursor = doc.find(text, search_cursor)

        count_label.setText(f"{index}/{total}")

    def update_vehicle_info(self, info: dict):
        """
        更新车辆信息。
        支持增量更新：只更新 info 中存在的字段，保留其他字段。
        """
        if "vin" in info:
            self.vehicle_labels["vin"].setText(info.get("vin", "—"))
        if "vehicle_mode" in info:
            self.vehicle_labels["vehicle_mode"].setText(info.get("vehicle_mode", "—"))
        if "user_mode" in info:
            self.vehicle_labels["user_mode"].setText(info.get("user_mode", "—"))
        if "factory_mode" in info:
            self.vehicle_labels["factory_mode"].setText(info.get("factory_mode", "—"))
        if "voltage" in info:
            self.vehicle_labels["voltage"].setText(info.get("voltage", "—"))

    def update_service_status_info(self, info: dict):
        """
        更新服务状态信息显示。
        info 字典中 key='status_summary' 是从 topology_service 返回的 JSON 字符串。
        """
        raw_data = info.get("status_summary", "")
        if not raw_data:
            self.status_labels["service_status_info"].clear()
            return

        display_text = ""

        if isinstance(raw_data, str):
            try:
                # 如果是 JSON 字符串，尝试解析以便美化或提取统计信息
                parsed = json.loads(raw_data)
                # 重新美化格式化 JSON，使用4空格缩进
                display_text = json.dumps(parsed, indent=4, ensure_ascii=False)
            except Exception:
                # 解析失败，就是普通字符串
                display_text = raw_data
        elif isinstance(raw_data, (dict, list)):
            # 如果已经是对象，直接格式化
            try:
                display_text = json.dumps(raw_data, indent=4, ensure_ascii=False)
            except Exception:
                display_text = str(raw_data)
        else:
            display_text = str(raw_data)

        self.status_labels["service_status_info"].setText(display_text)

    def update_security_info(self, info: dict):
        """部分更新证书信息"""
        for key, value in info.items():
            if key in self.sec_labels:
                self.sec_labels[key].setText(str(value))

    def update_network_mgmt(self, info: dict):
        """部分更新网络管理信息"""
        for key, value in info.items():
            if key in self.net_labels:
                self.net_labels[key].setText(str(value))

    def update_storage_info(self, info: dict):
        """部分更新存储信息"""
        if not info:
             self.storage_text.clear()
             return

        content = info.get("a_core_storage", "")
        if not content and info:
             try:
                 content = json.dumps(info, indent=4, ensure_ascii=False)
             except:
                 content = str(info)

        if isinstance(content, str):
             stripped = content.strip()
             if (stripped.startswith("{") and stripped.endswith("}")) or \
                (stripped.startswith("[") and stripped.endswith("]")):
                 try:
                     parsed = json.loads(content)
                     content = json.dumps(parsed, indent=4, ensure_ascii=False)
                 except:
                     pass

        self.storage_text.setText(str(content))

    def update_version_info(self, info: dict):
        """更新版本信息面板"""
        if not info:
            self.version_text.clear()
            return

        val = info.get("m_core_storage", "")
        if not val and "version" in info:
             val = info.get("version", "")

        if not val and info:
             try:
                 val = json.dumps(info, indent=4, ensure_ascii=False)
             except:
                 val = str(info)

        self.version_text.setText(str(val))

    def _show_panel(self, button):
        """显示面板"""
        panel = self.panels[button]

        if panel.isVisible():
            panel.hide()
            button.setChecked(False)
        else:
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
        if hasattr(self, 'toolbar'):
            self.toolbar.setGeometry(10, 10, self.viewport().width() - 20, 46)
        self._fit_topology_to_view()

    def init_nodes(self, node_data):
        self.scene.clear()
        self.child_nodes.clear()
        self.node_items.clear()
        self.connection_items.clear()

        if not node_data:
            return
        # 解析节点数据
        # 假设第一个节点是中心节点 (ETH Switch)
        main_node_data = node_data[0]
        remaining_nodes = node_data[1:]

        # 处理中心节点
        if len(main_node_data) == 5:
            name, icon, status, x, y = main_node_data
            self.main_node = TopologyNode(0, name, "")
            self.main_node.status = status
        else:
            self.main_node = TopologyNode(0, "主交换机\nMAIN SWITCH", "")

        self.main_node_item = NodeGraphicsItem(self.main_node, is_main=True)
        self.scene.addItem(self.main_node_item)
        self.node_items[0] = self.main_node_item

        # 处理子节点
        for i, data in enumerate(remaining_nodes):
            # 兼容两种格式:
            # 1. (node_id, node_name, connection_note) - 旧格式
            # 2. (name, icon, status, x, y) - TopologySnapshot 格式

            if len(data) == 3:
                node_id, node_name, connection_note = data
                status = "online"
            elif len(data) == 5:
                node_name, icon, status_str, x, y = data
                node_id = i + 1
                connection_note = ""

                # 映射状态字符串到内部状态
                status = "online" if status_str in ["正常", "online", "Link up"] else "offline"
            else:
                continue

            node = TopologyNode(node_id, node_name, connection_note)
            node.status = status
            self.child_nodes.append(node)
            item = NodeGraphicsItem(node)
            self.node_items[node_id] = item
            self.scene.addItem(item)

        # 关键：初始化节点后必须重新布局
        self.layout_nodes()

    def layout_nodes(self):
        if not self.main_node_item:
            return

        self._clear_connections()
        main_size = self.calculate_main_node_size()
        self.main_node_item.set_size(main_size)

        center_x = 0.0
        # 主节点垂直居中，让场景矩形自适应
        main_node_y = 0
        self.main_node_item.setPos(center_x, main_node_y)

        child_count = len(self.child_nodes)
        if child_count == 0:
            self._update_scene_rect()
            self._fit_topology_to_view(force=True)
            return

        # 逻辑优化：超过10个节点才分两排
        if child_count >= 10:
            top_count = child_count // 2
            bottom_count = child_count - top_count
        else:
            top_count = 0
            bottom_count = child_count

        top_nodes = self.child_nodes[:top_count]
        bottom_nodes = self.child_nodes[top_count:]

        child_width = self.child_nodes[0].size.width()

        main_left = center_x - main_size.width() / 2
        main_right = center_x + main_size.width() / 2
        main_top_y = main_node_y - main_size.height() / 2
        main_bottom_y = main_node_y + main_size.height() / 2

        # 布局上方节点
        if top_count > 0:
            total_top_width = (top_count - 1) * self.node_spacing + child_width
            start_x_top = center_x - total_top_width / 2 + child_width / 2
            top_y = main_node_y - self.vertical_gap

            for index, node in enumerate(top_nodes):
                child_center_x = start_x_top + index * self.node_spacing

                # 计算连接点X坐标
                if child_center_x < main_left + self.padding:
                    connection_x = main_left + self.padding
                elif child_center_x > main_right - self.padding:
                    connection_x = main_right - self.padding
                else:
                    connection_x = child_center_x

                item = self.node_items[node.node_id]
                item.setPos(child_center_x, top_y)

                node_bottom_y = top_y + node.size.height() / 2
                self._add_connection(connection_x, main_top_y, node_bottom_y, node.connection_note)

        # 布局下方节点
        if bottom_count > 0:
            total_bottom_width = (bottom_count - 1) * self.node_spacing + child_width
            start_x_bottom = center_x - total_bottom_width / 2 + child_width / 2
            bottom_y = main_node_y + self.vertical_gap

            for index, node in enumerate(bottom_nodes):
                child_center_x = start_x_bottom + index * self.node_spacing

                # 计算连接点X坐标
                if child_center_x < main_left + self.padding:
                    connection_x = main_left + self.padding
                elif child_center_x > main_right - self.padding:
                    connection_x = main_right - self.padding
                else:
                    connection_x = child_center_x

                item = self.node_items[node.node_id]
                item.setPos(child_center_x, bottom_y)

                node_top_y = bottom_y - node.size.height() / 2
                self._add_connection(connection_x, main_bottom_y, node_top_y, node.connection_note)

        self._update_scene_rect()
        self._fit_topology_to_view(force=True)

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

    def _fit_topology_to_view(self, force=False):
        """根据当前视口尺寸自适应显示拓扑图，避免小屏幕下遮挡其他布局。"""
        if not force and not getattr(self, '_auto_fit_enabled', True):
            return
        if self.scene is None or not self.scene.items():
            return

        viewport_rect = self.viewport().rect()
        if viewport_rect.width() <= 0 or viewport_rect.height() <= 0:
            return

        fit_rect = self.sceneRect()
        if fit_rect.isEmpty() or fit_rect.width() <= 0 or fit_rect.height() <= 0:
            return

        top_offset = self._fit_padding
        if hasattr(self, 'toolbar') and self.toolbar and self.toolbar.isVisible():
            top_offset += self.toolbar.height() + 8

        available_width = viewport_rect.width() - self._fit_padding * 2
        available_height = viewport_rect.height() - top_offset - self._fit_padding
        if available_width <= 0 or available_height <= 0:
            return

        x_ratio = available_width / fit_rect.width()
        y_ratio = available_height / fit_rect.height()
        scale_factor = min(x_ratio, y_ratio)
        scale_factor = max(self._min_scale, min(scale_factor, self._max_scale))

        self.resetTransform()
        self.scale(scale_factor, scale_factor)
        self._current_scale = scale_factor

        center_y = fit_rect.center().y()
        if hasattr(self, 'toolbar') and self.toolbar and self.toolbar.isVisible():
            center_y += max(0, top_offset - self._fit_padding) / max(scale_factor, 0.001) / 2
        self.centerOn(QPointF(fit_rect.center().x(), center_y))

    def _fallback_fit_topology_to_view(self, force=False):
        """运行时兜底：在异常热更新/旧缓存场景下，至少保证拓扑图可显示。"""
        if self.scene is None or not self.scene.items():
            return
        rect = self.sceneRect()
        if rect.isEmpty():
            return
        try:
            self.fitInView(rect, Qt.KeepAspectRatio)
        except Exception:
            pass

    def calculate_main_node_size(self):
        child_count = len(self.child_nodes)
        if child_count == 0:
            return QSize(500, 80)

        # 逻辑优化：超过10个节点才分两排
        if child_count >= 10:
            top_count = child_count // 2
            bottom_count = child_count - top_count
        else:
            top_count = 0
            bottom_count = child_count

        max_row_count = max(top_count, bottom_count)

        total_child_width = (max_row_count - 1) * self.node_spacing + self.child_nodes[0].size.width()
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
        self._auto_fit_enabled = False
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
        return QSize(320, 160)


class FloatingPanel(QWidget):
    """浮动信息面板"""

    # 边缘常量
    EDGE_NONE = 0
    EDGE_LEFT = 1
    EDGE_TOP = 2
    EDGE_RIGHT = 4
    EDGE_BOTTOM = 8
    EDGE_MARGIN = 10

    def __init__(self, title, parent=None, content_widget=None, initial_size=None):
        super().__init__(parent)
        self.title = title
        self.animation = None
        self.custom_content = content_widget
        self.initial_size = initial_size if initial_size else (420, 380)

        # 拖拽和调整大小状态
        self._drag_pos = None
        self._resize_edge = self.EDGE_NONE
        self._is_resizing = False

        self.setMouseTracking(True)
        self.init_ui()

    def init_ui(self):
        """初始化面板UI"""
        self.setObjectName("FloatingPanel")
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("QWidget#FloatingPanel { background: transparent; border: none; }")

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
        self.title_bar = QWidget(main_frame)
        self.title_bar.setStyleSheet("""
            QWidget {
                background-color: #F9FAFB;
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
                border-bottom: 1px solid #E5E7EB;
            }
        """)

        title_layout = QHBoxLayout(self.title_bar)
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

        layout.addWidget(self.title_bar)
        layout.addWidget(content_area)

        main_layout.addWidget(main_frame)

        self.resize(*self.initial_size)
        # self.setMinimumSize(300, 200)
        self.hide()

    def add_panel_content(self, layout):
        """添加面板内容"""
        if self.custom_content:
            # 设置 stretch=1 让自定义内容（如文本框）随面板伸缩
            layout.addWidget(self.custom_content, 1)
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

    def _get_edge(self, pos):
        edge = self.EDGE_NONE
        r = self.rect()
        m = self.EDGE_MARGIN

        if pos.x() <= m:
            edge |= self.EDGE_LEFT
        elif pos.x() >= r.width() - m:
            edge |= self.EDGE_RIGHT

        if pos.y() <= m:
            edge |= self.EDGE_TOP
        elif pos.y() >= r.height() - m:
            edge |= self.EDGE_BOTTOM

        return edge

    def _update_cursor(self, edge):
        if edge == self.EDGE_LEFT | self.EDGE_TOP or edge == self.EDGE_RIGHT | self.EDGE_BOTTOM:
            self.setCursor(Qt.SizeFDiagCursor)
        elif edge == self.EDGE_RIGHT | self.EDGE_TOP or edge == self.EDGE_LEFT | self.EDGE_BOTTOM:
            self.setCursor(Qt.SizeBDiagCursor)
        elif edge & self.EDGE_LEFT or edge & self.EDGE_RIGHT:
            self.setCursor(Qt.SizeHorCursor)
        elif edge & self.EDGE_TOP or edge & self.EDGE_BOTTOM:
            self.setCursor(Qt.SizeVerCursor)
        else:
            self.setCursor(Qt.ArrowCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            edge = self._get_edge(event.pos())
            if edge != self.EDGE_NONE:
                self._is_resizing = True
                self._resize_edge = edge
                self._drag_pos = event.globalPos()
                event.accept()
            else:
                # 检查点击是否在标题栏区域
                local_pos = self.title_bar.mapFrom(self, event.pos())
                if self.title_bar.rect().contains(local_pos):
                    self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
                    self._is_resizing = False
                    event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            if self._is_resizing:
                delta = event.globalPos() - self._drag_pos
                self._drag_pos = event.globalPos()

                geo = self.geometry()
                # 使用 QRectF 进行计算，避免精度问题，最后转回 QRect
                new_geo = QRectF(geo)

                min_w = self.minimumWidth()
                min_h = self.minimumHeight()

                if self._resize_edge & self.EDGE_LEFT:
                    new_w = geo.width() - delta.x()
                    if new_w >= min_w:
                        new_geo.setLeft(geo.left() + delta.x())

                if self._resize_edge & self.EDGE_RIGHT:
                    new_w = geo.width() + delta.x()
                    if new_w >= min_w:
                        new_geo.setRight(geo.right() + delta.x())

                if self._resize_edge & self.EDGE_TOP:
                    new_h = geo.height() - delta.y()
                    if new_h >= min_h:
                        new_geo.setTop(geo.top() + delta.y())

                if self._resize_edge & self.EDGE_BOTTOM:
                    new_h = geo.height() + delta.y()
                    if new_h >= min_h:
                        new_geo.setBottom(geo.bottom() + delta.y())

                self.setGeometry(new_geo.toRect())
                event.accept()

            elif self._drag_pos: # 移动模式
                self.move(event.globalPos() - self._drag_pos)
                event.accept()
        else:
            # 更新鼠标光标
            self._update_cursor(self._get_edge(event.pos()))
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._is_resizing = False
        self._resize_edge = self.EDGE_NONE
        self._drag_pos = None
        self.setCursor(Qt.ArrowCursor)
        super().mouseReleaseEvent(event)

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
        self.setMinimumHeight(0)

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
        self.topology.setMinimumHeight(0)
        self.topology.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)

        # 主布局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.topology)

    def minimumSizeHint(self):
        return QSize(320, 220)

    def sizeHint(self):
        return QSize(760, 520)


class CanLinTopologyWidget(TopologyWidget):
    """CAN/LIN 网络拓扑图部件，不包含顶部信息栏"""

    def _init_transparent_toolbar(self):
        # 重写此方法，不初始化顶部工具栏
        pass


class CanLinTopologyWindow(QWidget):
    """CAN/LIN 网络拓扑图窗口"""

    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        self.setMinimumHeight(0)
        # 构造节点数据
        # 主节点 LLCE
        # 格式: (name, icon, status, x, y)
        node_data = [
            ("LLCE", "", "online", 0, 0)
        ]

        # 子节点 LIN1, LIN2
        node_data.append(("LIN1", "", "online", 0, 0))
        node_data.append(("LIN2", "", "online", 0, 0))

        # 子节点 CANFD1 ~ CANFD13
        for i in range(1, 14):
            node_data.append((f"CANFD{i}", "", "online", 0, 0))

        self.topology = CanLinTopologyWidget(node_data)
        self.topology.setMinimumHeight(0)
        self.topology.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.topology)

    def minimumSizeHint(self):
        return QSize(320, 220)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SimpleTopologyWindow()
    window.show()
    sys.exit(app.exec_())
