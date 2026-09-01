# app/modules/ethernet_simulation/view/ethernet_simulation_view.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from PyQt5.QtCore import Qt, pyqtSignal, QModelIndex, QAbstractTableModel
from PyQt5.QtGui import QDoubleValidator, QIntValidator
from PyQt5.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFrame, QGroupBox,
    QHeaderView, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QSplitter, QSpinBox, QTableWidget, QTableWidgetItem,
    QTextEdit, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
    QFormLayout, QDoubleSpinBox, QMenu, QAction,
)

from app.modules.ethernet_simulation.model.ethernet_simulation_model import (
    EthernetSimulationModel, SimMessage, TransportProtocol,
)
from app.presentation.views.base_view import BaseView


# ---- 样式常量 ----
_PANEL_STYLE = (
    "QFrame#panel { background:#F8FAFC; border:1px solid #E2E8F0; border-radius:12px; }"
)
_INPUT_STYLE = (
    "QLineEdit { background:#FFFFFF; border:1px solid #CBD5E1; border-radius:6px; "
    "padding:5px 8px; font-size:12px; }"
    "QLineEdit:focus { border-color:#2563EB; }"
)
_BTN_PRIMARY = (
    "QPushButton { background:#2563EB; color:white; border:none; border-radius:8px; "
    "padding:8px 16px; font-weight:600; font-size:13px; }"
    "QPushButton:hover { background:#1D4ED8; }"
    "QPushButton:disabled { background:#94A3B8; }"
)
_BTN_DANGER = (
    "QPushButton { background:#DC2626; color:white; border:none; border-radius:8px; "
    "padding:8px 16px; font-weight:600; font-size:13px; }"
    "QPushButton:hover { background:#B91C1C; }"
    "QPushButton:disabled { background:#94A3B8; }"
)
_BTN_GHOST = (
    "QPushButton { background:#FFFFFF; color:#1E293B; border:1px solid #CBD5E1; "
    "border-radius:8px; padding:6px 12px; font-weight:600; font-size:12px; }"
    "QPushButton:hover { background:#F1F5F9; }"
    "QPushButton:disabled { background:#F1F5F9; color:#94A3B8; }"
)
_BTN_SUCCESS = (
    "QPushButton { background:#059669; color:white; border:none; border-radius:8px; "
    "padding:8px 16px; font-weight:600; font-size:13px; }"
    "QPushButton:hover { background:#047857; }"
    "QPushButton:disabled { background:#94A3B8; }"
)
_TABLE_STYLE = (
    "QTableWidget { background:white; alternate-background-color:#F8FAFC; "
    "border:1px solid #E2E8F0; border-radius:8px; gridline-color:#E2E8F0; }"
    "QHeaderView::section { background:#F1F5F9; border:none; "
    "border-bottom:1px solid #E2E8F0; padding:6px 8px; color:#334155; font-weight:700; font-size:12px; }"
)


class MessageTableModel(QAbstractTableModel):
    """报文列表的 Table Model。"""

    HEADERS = ["启用", "名称", "协议", "目标IP", "目标端口", "源端口", "周期(ms)", "发送数", "发送状态", "操作", "摘要"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._messages: List[SimMessage] = []

    def set_messages(self, messages: List[SimMessage]):
        self.beginResetModel()
        self._messages = list(messages)
        self.endResetModel()

    def get_message(self, row: int) -> Optional[SimMessage]:
        if 0 <= row < len(self._messages):
            return self._messages[row]
        return None

    def rowCount(self, parent=QModelIndex()):
        return len(self._messages)

    def columnCount(self, parent=QModelIndex()):
        return len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.HEADERS[section]
        return None

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self._messages):
            return None
        msg = self._messages[index.row()]
        col = index.column()
        if role == Qt.DisplayRole or role == Qt.ToolTipRole:
            if col == 0:
                return "✓" if msg.enabled else "✗"
            elif col == 1:
                return msg.name
            elif col == 2:
                return msg.protocol.value
            elif col == 3:
                return msg.dst_ip
            elif col == 4:
                return str(msg.dst_port)
            elif col == 5:
                return str(msg.src_port)
            elif col == 6:
                return str(msg.cycle_ms) if msg.cycle_ms > 0 else "单次"
            elif col == 7:
                return str(msg.tx_count)
            elif col == 8:
                return msg.summary()
        elif role == Qt.TextAlignmentRole:
            if col in (0, 4, 5, 6, 7):
                return int(Qt.AlignCenter)
        elif role == Qt.ForegroundRole:
            if col == 0 and not msg.enabled:
                from PyQt5.QtGui import QColor
                return QColor("#94A3B8")
        return None

    def flags(self, index):
        base_flags = super().flags(index)
        if index.column() == 0:
            return base_flags | Qt.ItemIsUserCheckable
        return base_flags

    def refresh_row(self, row: int):
        if 0 <= row < len(self._messages):
            top_left = self.index(row, 0)
            bottom_right = self.index(row, len(self.HEADERS) - 1)
            self.dataChanged.emit(top_left, bottom_right, [Qt.DisplayRole, Qt.ToolTipRole])


class EthernetSimulationView(BaseView):
    """CANOE 风格以太网仿真界面。"""

    # 信号
    start_requested = pyqtSignal()
    stop_requested = pyqtSignal()
    send_once_requested = pyqtSignal(int)  # message index
    add_message_requested = pyqtSignal(str)  # protocol name: UDP/TCP/SOME/IP
    remove_message_requested = pyqtSignal(int)
    duplicate_message_requested = pyqtSignal(int)
    clear_messages_requested = pyqtSignal()
    message_selected = pyqtSignal(int)
    config_changed = pyqtSignal(dict)
    import_requested = pyqtSignal()
    export_requested = pyqtSignal()
    toggle_send_requested = pyqtSignal(int)  # 单条报文开始/停止周期发送
    select_all_requested = pyqtSignal(bool)  # 全选/取消全选
    message_enabled_changed = pyqtSignal(int, bool)  # row, enabled

    def setup_ui(self):
        self._building = False
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(12, 8, 12, 8)
        root_layout.setSpacing(6)

        # 1. 顶部工具栏：网络配置 + 仿真控制
        root_layout.addWidget(self._create_toolbar())

        # 2. 主区域：报文列表 + 报文编辑器（占满剩余空间）
        root_layout.addWidget(self._create_message_area(), 1)

        # 3. 底部状态栏
        root_layout.addWidget(self._create_status_bar())

    # ================================================================
    # 顶部工具栏
    # ================================================================
    def _create_toolbar(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("panel")
        frame.setFixedHeight(42)
        frame.setStyleSheet(
            "QFrame#panel { background:#F8FAFC; border:1px solid #E2E8F0; border-radius:8px; }"
        )

        layout = QHBoxLayout(frame)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(6)

        # ---- 紧凑标签样式 ----
        lbl_style = "font-size:11px; font-weight:600; color:#475569;"
        ctrl_w = 110  # 输入框统一宽度

        # -- 网络配置（全部横向一行） --
        layout.addWidget(self._make_label("VLAN", lbl_style))
        self.vlan_spin = QSpinBox()
        self.vlan_spin.setRange(0, 4095)
        self.vlan_spin.setValue(62)
        self.vlan_spin.setFixedWidth(60)
        self.vlan_spin.setStyleSheet(_INPUT_STYLE)
        layout.addWidget(self.vlan_spin)

        # 分隔线
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.VLine)
        sep1.setStyleSheet("color:#E2E8F0;")
        sep1.setFixedHeight(24)
        layout.addWidget(sep1)

        # -- 仿真控制 --
        self.start_btn = QPushButton("▶ 开始")
        self.start_btn.setStyleSheet(_BTN_SUCCESS)
        self.start_btn.setCursor(Qt.PointingHandCursor)
        self.start_btn.setFixedHeight(28)
        self.start_btn.clicked.connect(lambda: self.start_requested.emit())
        layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton("■ 停止")
        self.stop_btn.setStyleSheet(_BTN_DANGER)
        self.stop_btn.setCursor(Qt.PointingHandCursor)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setFixedHeight(28)
        self.stop_btn.clicked.connect(lambda: self.stop_requested.emit())
        layout.addWidget(self.stop_btn)

        # 分隔线
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.VLine)
        sep2.setStyleSheet("color:#E2E8F0;")
        sep2.setFixedHeight(24)
        layout.addWidget(sep2)

        # -- 导入/导出 --
        self.import_btn = QPushButton("📂 导入")
        self.import_btn.setStyleSheet(_BTN_GHOST)
        self.import_btn.setCursor(Qt.PointingHandCursor)
        self.import_btn.setFixedHeight(28)
        self.import_btn.clicked.connect(lambda: self.import_requested.emit())
        layout.addWidget(self.import_btn)

        self.export_btn = QPushButton("💾 导出")
        self.export_btn.setStyleSheet(_BTN_GHOST)
        self.export_btn.setCursor(Qt.PointingHandCursor)
        self.export_btn.setFixedHeight(28)
        self.export_btn.clicked.connect(lambda: self.export_requested.emit())
        layout.addWidget(self.export_btn)

        # 弹性空间
        layout.addStretch()

        return frame

    @staticmethod
    def _make_label(text: str, style: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(style)
        lbl.setFixedWidth(36)
        lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        return lbl

    # ================================================================
    # 报文编辑区 (左侧: 报文列表, 右侧: 报文编辑器)
    # ================================================================
    def _create_message_area(self) -> QWidget:
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._create_message_list())
        splitter.addWidget(self._create_message_editor())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([520, 380])
        return splitter

    def _create_message_list(self) -> QWidget:
        container = QFrame()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # 标题栏
        header = QHBoxLayout()
        title = QLabel("📋 仿真报文列表")
        title.setStyleSheet("font-size:14px; font-weight:700; color:#0F172A;")
        header.addWidget(title)
        header.addStretch()

        self.add_msg_btn = QPushButton("添加")
        self.add_msg_btn.setStyleSheet(
            "QPushButton { background:#2563EB; color:white; border:none; border-radius:8px; "
            "padding:6px 12px; font-weight:600; font-size:12px; }"
            "QPushButton:hover { background:#1D4ED8; }"
        )
        self.add_msg_btn.setCursor(Qt.PointingHandCursor)
        add_menu = QMenu(self.add_msg_btn)
        for proto in ["UDP", "TCP", "SOME/IP"]:
            act = QAction(proto, add_menu)
            act.triggered.connect(lambda checked, p=proto: self.add_message_requested.emit(p))
            add_menu.addAction(act)
        self.add_msg_btn.setMenu(add_menu)
        header.addWidget(self.add_msg_btn)

        # 全选/取消全选
        self.select_all_btn = QPushButton("☑ 全选")
        self.select_all_btn.setStyleSheet(_BTN_GHOST)
        self.select_all_btn.setCursor(Qt.PointingHandCursor)
        self.select_all_btn.setFixedHeight(26)
        self.select_all_btn.clicked.connect(lambda: self.select_all_requested.emit(True))
        header.addWidget(self.select_all_btn)

        self.deselect_all_btn = QPushButton("☐ 取消")
        self.deselect_all_btn.setStyleSheet(_BTN_GHOST)
        self.deselect_all_btn.setCursor(Qt.PointingHandCursor)
        self.deselect_all_btn.setFixedHeight(26)
        self.deselect_all_btn.clicked.connect(lambda: self.select_all_requested.emit(False))
        header.addWidget(self.deselect_all_btn)

        self.dup_msg_btn = QPushButton("📋 复制")
        self.dup_msg_btn.setStyleSheet(_BTN_GHOST)
        self.dup_msg_btn.setCursor(Qt.PointingHandCursor)
        self.dup_msg_btn.clicked.connect(self._on_duplicate_clicked)
        header.addWidget(self.dup_msg_btn)

        self.del_msg_btn = QPushButton("🗑 删除")
        self.del_msg_btn.setStyleSheet(_BTN_GHOST)
        self.del_msg_btn.setCursor(Qt.PointingHandCursor)
        self.del_msg_btn.clicked.connect(self._on_remove_clicked)
        header.addWidget(self.del_msg_btn)

        layout.addLayout(header)

        # 报文表格
        self.msg_table = QTableWidget()
        self.msg_table_model = MessageTableModel(self.msg_table)
        self.msg_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.msg_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.msg_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.msg_table.setAlternatingRowColors(True)
        self.msg_table.verticalHeader().setVisible(False)
        self.msg_table.setStyleSheet(_TABLE_STYLE)
        self.msg_table.selectionModel().selectionChanged.connect(self._on_msg_selection_changed)

        # 使用 QTableWidget 兼容模式
        self.msg_table.setColumnCount(len(MessageTableModel.HEADERS))
        self.msg_table.setHorizontalHeaderLabels(MessageTableModel.HEADERS)
        self._refresh_msg_table()

        layout.addWidget(self.msg_table, 1)
        return container

    def _create_message_editor(self) -> QWidget:
        container = QFrame()
        container.setStyleSheet(
            "QFrame { background:#FFFFFF; border:1px solid #E2E8F0; border-radius:10px; }"
        )
        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        title = QLabel("✏️ 报文编辑器")
        title.setStyleSheet("font-size:14px; font-weight:700; color:#0F172A;")
        layout.addWidget(title)

        # 基本信息
        basic_group = QGroupBox("基本信息")
        basic_group.setStyleSheet(
            "QGroupBox { font-weight:600; font-size:12px; color:#475569; "
            "border:1px solid #E2E8F0; border-radius:8px; margin-top:8px; padding-top:16px; }"
            "QGroupBox::title { subcontrol-origin: margin; left:10px; padding:0 4px; }"
        )
        basic_layout = QFormLayout(basic_group)
        basic_layout.setSpacing(6)

        self.edit_name = QLineEdit()
        self.edit_name.setPlaceholderText("报文名称")
        self.edit_name.setStyleSheet(_INPUT_STYLE)
        basic_layout.addRow("名称:", self.edit_name)

        self.edit_protocol = QComboBox()
        self.edit_protocol.addItems(["UDP", "TCP", "SOME/IP"])
        self.edit_protocol.setStyleSheet(_INPUT_STYLE)
        self.edit_protocol.currentTextChanged.connect(self._on_protocol_changed)
        basic_layout.addRow("协议:", self.edit_protocol)

        self.edit_src_ip = QLineEdit()
        self.edit_src_ip.setPlaceholderText("源IP地址")
        self.edit_src_ip.setStyleSheet(_INPUT_STYLE)
        basic_layout.addRow("源IP:", self.edit_src_ip)

        self.edit_dst_ip = QLineEdit()
        self.edit_dst_ip.setPlaceholderText("目标IP地址")
        self.edit_dst_ip.setStyleSheet(_INPUT_STYLE)
        basic_layout.addRow("目标IP:", self.edit_dst_ip)

        self.edit_dst_port = QLineEdit()
        self.edit_dst_port.setPlaceholderText("目标端口")
        self.edit_dst_port.setStyleSheet(_INPUT_STYLE)
        basic_layout.addRow("目标端口:", self.edit_dst_port)

        self.edit_src_port = QLineEdit()
        self.edit_src_port.setPlaceholderText("源端口")
        self.edit_src_port.setStyleSheet(_INPUT_STYLE)
        basic_layout.addRow("源端口:", self.edit_src_port)

        self.edit_cycle = QLineEdit()
        self.edit_cycle.setPlaceholderText("0=单次发送")
        self.edit_cycle.setStyleSheet(_INPUT_STYLE)
        basic_layout.addRow("周期(ms):", self.edit_cycle)

        layout.addWidget(basic_group)

        # SOME/IP 专用字段
        self.someip_group = QGroupBox("SOME/IP 参数")
        self.someip_group.setStyleSheet(basic_group.styleSheet())
        someip_layout = QFormLayout(self.someip_group)
        someip_layout.setSpacing(6)

        self.edit_service_id = QLineEdit()
        self.edit_service_id.setPlaceholderText("0x0000")
        self.edit_service_id.setStyleSheet(_INPUT_STYLE)
        someip_layout.addRow("Service ID:", self.edit_service_id)

        self.edit_method_id = QLineEdit()
        self.edit_method_id.setPlaceholderText("0x0000")
        self.edit_method_id.setStyleSheet(_INPUT_STYLE)
        someip_layout.addRow("Method ID:", self.edit_method_id)

        self.edit_client_id = QLineEdit()
        self.edit_client_id.setPlaceholderText("0x0000")
        self.edit_client_id.setStyleSheet(_INPUT_STYLE)
        someip_layout.addRow("Client ID:", self.edit_client_id)

        self.edit_msg_type = QComboBox()
        self.edit_msg_type.addItems([
            "0x00 - Request",
            "0x80 - Response",
            "0x02 - Notification",
            "0x81 - Error",
        ])
        self.edit_msg_type.setStyleSheet(_INPUT_STYLE)
        someip_layout.addRow("Msg Type:", self.edit_msg_type)

        layout.addWidget(self.someip_group)

        # 负载编辑器
        payload_group = QGroupBox("负载数据 (Hex)")
        payload_group.setStyleSheet(basic_group.styleSheet())
        payload_layout = QVBoxLayout(payload_group)

        self.edit_payload = QTextEdit()
        self.edit_payload.setPlaceholderText("输入十六进制数据，例如: DE AD BE EF 01 02 03 04")
        self.edit_payload.setMaximumHeight(80)
        self.edit_payload.setStyleSheet(
            "QTextEdit { background:#F8FAFC; color:#0F172A; border:1px solid #CBD5E1; "
            "border-radius:6px; padding:6px; font-family:'Consolas','Courier New',monospace; "
            "font-size:12px; }"
        )
        payload_layout.addWidget(self.edit_payload)

        layout.addWidget(payload_group)

        # 发送按钮
        btn_layout = QHBoxLayout()
        self.send_once_btn = QPushButton("📤 单次发送")
        self.send_once_btn.setStyleSheet(_BTN_PRIMARY)
        self.send_once_btn.setCursor(Qt.PointingHandCursor)
        self.send_once_btn.clicked.connect(self._on_send_once_clicked)
        btn_layout.addWidget(self.send_once_btn)

        self.apply_edit_btn = QPushButton("✅ 应用修改")
        self.apply_edit_btn.setStyleSheet(_BTN_GHOST)
        self.apply_edit_btn.setCursor(Qt.PointingHandCursor)
        self.apply_edit_btn.clicked.connect(self._on_apply_edit_clicked)
        btn_layout.addWidget(self.apply_edit_btn)

        layout.addLayout(btn_layout)
        layout.addStretch()

        # 初始隐藏 SOME/IP 参数
        self.someip_group.setVisible(False)
        self._current_edit_index = -1

        return container

    # ================================================================
    # 底部状态栏
    # ================================================================
    def _create_status_bar(self) -> QWidget:
        frame = QFrame()
        frame.setStyleSheet(
            "QFrame { background:#F1F5F9; border:1px solid #E2E8F0; border-radius:8px; }"
        )
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(12, 4, 12, 4)

        self.status_label = QLabel("就绪 - 以太网仿真未启动")
        self.status_label.setStyleSheet("font-size:12px; color:#64748B;")
        layout.addWidget(self.status_label)

        layout.addStretch()

        self.msg_count_label = QLabel("报文: 0")
        self.msg_count_label.setStyleSheet("font-size:11px; color:#64748B;")
        layout.addWidget(self.msg_count_label)

        return frame

    # ================================================================
    # 公共接口
    # ================================================================

    def set_simulation_running(self, running: bool):
        """更新仿真运行状态。"""
        self._building = True
        self.start_btn.setEnabled(not running)
        self.stop_btn.setEnabled(running)
        if running:
            self.status_label.setText("🟢 仿真运行中...")
            self.status_label.setStyleSheet("font-size:12px; color:#059669; font-weight:600;")
        else:
            self.status_label.setText("⏸️ 仿真已停止")
            self.status_label.setStyleSheet("font-size:12px; color:#64748B;")
        self._building = False

    def update_message_table(self, messages: List[SimMessage]):
        """更新报文列表。"""
        self.msg_table.setRowCount(0)
        self.msg_table.setRowCount(len(messages))
        for row, msg in enumerate(messages):
            # 启用复选框
            cb = QCheckBox()
            cb.setChecked(msg.enabled)
            cb.stateChanged.connect(lambda state, r=row: self._on_msg_enabled_changed(r, state))
            cb_widget = QWidget()
            cb_layout = QHBoxLayout(cb_widget)
            cb_layout.addWidget(cb)
            cb_layout.setAlignment(Qt.AlignCenter)
            cb_layout.setContentsMargins(0, 0, 0, 0)
            self.msg_table.setCellWidget(row, 0, cb_widget)

            self.msg_table.setItem(row, 1, QTableWidgetItem(msg.name))
            self.msg_table.setItem(row, 2, QTableWidgetItem(msg.protocol.value))
            self.msg_table.setItem(row, 3, QTableWidgetItem(msg.dst_ip))
            self.msg_table.setItem(row, 4, QTableWidgetItem(str(msg.dst_port)))
            self.msg_table.setItem(row, 5, QTableWidgetItem(str(msg.src_port)))
            cycle_text = str(msg.cycle_ms) if msg.cycle_ms > 0 else "单次"
            self.msg_table.setItem(row, 6, QTableWidgetItem(cycle_text))
            self.msg_table.setItem(row, 7, QTableWidgetItem(str(msg.tx_count)))

            # 发送状态列
            status_item = QTableWidgetItem("🟢 发送中" if msg.sending else "⚪ 已停止")
            status_item.setTextAlignment(Qt.AlignCenter)
            if msg.sending:
                status_item.setForeground(Qt.green)
            else:
                from PyQt5.QtGui import QColor
                status_item.setForeground(QColor("#94A3B8"))
            self.msg_table.setItem(row, 8, status_item)

            # 操作列: 开始/停止按钮（嵌入容器避免溢出）
            toggle_btn = QPushButton("停止" if msg.sending else "开始")
            toggle_btn.setCursor(Qt.PointingHandCursor)
            if msg.sending:
                toggle_btn.setStyleSheet(
                    "QPushButton { background:#DC2626; color:white; border:none; border-radius:4px; "
                    "padding:2px 6px; font-size:11px; font-weight:600; }"
                    "QPushButton:hover { background:#B91C1C; }"
                )
            else:
                toggle_btn.setStyleSheet(
                    "QPushButton { background:#059669; color:white; border:none; border-radius:4px; "
                    "padding:2px 6px; font-size:11px; font-weight:600; }"
                    "QPushButton:hover { background:#047857; }"
                )
            toggle_btn.clicked.connect(lambda checked, r=row: self.toggle_send_requested.emit(r))
            btn_container = QWidget()
            btn_layout = QHBoxLayout(btn_container)
            btn_layout.addWidget(toggle_btn)
            btn_layout.setAlignment(Qt.AlignCenter)
            btn_layout.setContentsMargins(2, 2, 2, 2)
            self.msg_table.setCellWidget(row, 9, btn_container)

            self.msg_table.setItem(row, 10, QTableWidgetItem(msg.summary()))

            # 居中对齐
            for col in (0, 4, 5, 6, 7):
                item = self.msg_table.item(row, col)
                if item:
                    item.setTextAlignment(Qt.AlignCenter)

        # 设置操作列宽度
        self.msg_table.setColumnWidth(8, 80)
        self.msg_table.setColumnWidth(9, 70)

        # 确保表格内容不溢出
        self.msg_table.verticalHeader().setDefaultSectionSize(32)

        self.msg_count_label.setText(f"报文: {len(messages)}")

    def update_row_sending_status(self, row: int, sending: bool):
        """更新单行的发送状态显示。"""
        if row < 0 or row >= self.msg_table.rowCount():
            return
        # 更新状态文本
        status_item = self.msg_table.item(row, 8)
        if status_item:
            status_item.setText("🟢 发送中" if sending else "⚪ 已停止")
            from PyQt5.QtGui import QColor
            status_item.setForeground(Qt.green if sending else QColor("#94A3B8"))
        # 更新按钮（按钮嵌入在容器中）
        container = self.msg_table.cellWidget(row, 9)
        if container:
            toggle_btn = container.findChild(QPushButton)
            if toggle_btn:
                toggle_btn.setText("停止" if sending else "开始")
                if sending:
                    toggle_btn.setStyleSheet(
                        "QPushButton { background:#DC2626; color:white; border:none; border-radius:4px; "
                        "padding:2px 6px; font-size:11px; font-weight:600; }"
                        "QPushButton:hover { background:#B91C1C; }"
                    )
                else:
                    toggle_btn.setStyleSheet(
                        "QPushButton { background:#059669; color:white; border:none; border-radius:4px; "
                        "padding:2px 6px; font-size:11px; font-weight:600; }"
                        "QPushButton:hover { background:#047857; }"
                    )

    def get_network_config(self) -> dict:
        """获取当前网络配置。"""
        return {
            "vlan_id": self.vlan_spin.value(),
            "src_port": int(self.edit_src_port.text()) if self.edit_src_port.text().isdigit() else 30500,
            "dst_port": int(self.edit_dst_port.text()) if self.edit_dst_port.text().isdigit() else 30500,
        }

    def get_editor_values(self) -> Optional[SimMessage]:
        """获取编辑器当前值。"""
        proto_map = {"UDP": TransportProtocol.UDP, "TCP": TransportProtocol.TCP,
                     "SOME/IP": TransportProtocol.SOMEIP}
        try:
            msg = SimMessage(
                name=self.edit_name.text().strip(),
                src_ip=self.edit_src_ip.text().strip(),
                dst_ip=self.edit_dst_ip.text().strip(),
                dst_port=int(self.edit_dst_port.text()) if self.edit_dst_port.text().isdigit() else 30500,
                src_port=int(self.edit_src_port.text()) if self.edit_src_port.text().isdigit() else 30500,
                protocol=proto_map.get(self.edit_protocol.currentText(), TransportProtocol.UDP),
                service_id=int(self.edit_service_id.text(), 0) if self.edit_service_id.text() else 0,
                method_id=int(self.edit_method_id.text(), 0) if self.edit_method_id.text() else 0,
                client_id=int(self.edit_client_id.text(), 0) if self.edit_client_id.text() else 0,
                msg_type=[0x00, 0x80, 0x02, 0x81][self.edit_msg_type.currentIndex()],
                payload_hex=self.edit_payload.toPlainText().strip(),
                cycle_ms=int(self.edit_cycle.text()) if self.edit_cycle.text().isdigit() else 0,
            )
            return msg
        except (ValueError, IndexError):
            return None

    def load_editor_from_message(self, msg: SimMessage):
        """将报文数据加载到编辑器。"""
        self._building = True
        self.edit_name.setText(msg.name)
        idx = self.edit_protocol.findText(msg.protocol.value)
        if idx >= 0:
            self.edit_protocol.setCurrentIndex(idx)
        self.edit_src_ip.setText(msg.src_ip)
        self.edit_dst_ip.setText(msg.dst_ip)
        self.edit_dst_port.setText(str(msg.dst_port))
        self.edit_src_port.setText(str(msg.src_port))
        self.edit_cycle.setText(str(msg.cycle_ms) if msg.cycle_ms > 0 else "0")
        self.edit_service_id.setText(f"0x{msg.service_id:04X}" if msg.service_id else "0x0000")
        self.edit_method_id.setText(f"0x{msg.method_id:04X}" if msg.method_id else "0x0000")
        self.edit_client_id.setText(f"0x{msg.client_id:04X}" if msg.client_id else "0x0000")
        type_map = {0x00: 0, 0x80: 1, 0x02: 2, 0x81: 3}
        self.edit_msg_type.setCurrentIndex(type_map.get(msg.msg_type, 0))
        self.edit_payload.setPlainText(msg.payload_hex)
        self.someip_group.setVisible(msg.protocol == TransportProtocol.SOMEIP)
        self._building = False

    # ================================================================
    # 内部槽函数
    # ================================================================

    def _refresh_msg_table(self):
        """刷新报文表格（使用 QTableWidget 模式）。"""
        pass  # 由 update_message_table 处理

    def _on_msg_selection_changed(self):
        """报文选择变更。"""
        if self._building:
            return
        row = self.msg_table.currentRow()
        if row >= 0:
            self.message_selected.emit(row)

    def _on_duplicate_clicked(self):
        row = self.msg_table.currentRow()
        if row >= 0:
            self.duplicate_message_requested.emit(row)

    def _on_remove_clicked(self):
        row = self.msg_table.currentRow()
        if row >= 0:
            self.remove_message_requested.emit(row)

    def _on_send_once_clicked(self):
        row = self.msg_table.currentRow()
        if row >= 0:
            self.send_once_requested.emit(row)

    def _on_apply_edit_clicked(self):
        """应用编辑器修改到当前选中的报文。"""
        if self._building:
            return
        row = self.msg_table.currentRow()
        if row >= 0:
            self.duplicate_message_requested.emit(row)  # 触发更新

    def _on_msg_enabled_changed(self, row: int, state: int):
        """报文启用状态变更。"""
        self.message_enabled_changed.emit(row, state == Qt.Checked)

    def _on_protocol_changed(self, text: str):
        """协议类型变更时显示/隐藏 SOME/IP 参数。"""
        if not self._building:
            self.someip_group.setVisible(text == "SOME/IP")
