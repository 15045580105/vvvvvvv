from PyQt5 import QtWidgets
from PyQt5.QtWidgets import QHeaderView
from PyQt5.QtCore import Qt as _Qt

from app.common.ui.widgets import ModernButton, TableButton
from app.presentation.views.base_view import BaseView

# Use Qt.AlignmentFlag (not raw int) so QLabel.setAlignment avoids TypeError in some PyQt builds.
# Also keep an integer alignment for QTableWidgetItem.setTextAlignment which expects an int.
if hasattr(_Qt, "AlignmentFlag"):
    ALIGN_CENTER_LABEL = _Qt.AlignmentFlag.AlignCenter
    ALIGN_LEFT_LABEL = _Qt.AlignmentFlag.AlignLeft | _Qt.AlignmentFlag.AlignVCenter
else:
    ALIGN_CENTER_LABEL = _Qt.AlignCenter
    ALIGN_LEFT_LABEL = _Qt.AlignLeft | _Qt.AlignVCenter
ALIGN_CENTER_ITEM = int(_Qt.AlignCenter)
ONLINE_ICON = "🟢"
OFFLINE_ICON = "🔴"


class DeviceView(BaseView):
    def setup_ui(self):
        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.setSpacing(16)

        # 输入区域
        input_group = QtWidgets.QGroupBox("添加设备")
        form_layout = QtWidgets.QHBoxLayout()
        form_layout.setSpacing(12)

        self.ip_input = QtWidgets.QLineEdit()
        self.ip_input.setPlaceholderText("IP地址")
        self.port_input = QtWidgets.QLineEdit()
        self.port_input.setPlaceholderText("SSH端口(默认22)")
        self.port_input.setText("22")  # 默认端口写上 22
        self.name_input = QtWidgets.QLineEdit()
        self.name_input.setPlaceholderText("设备名")
        self.user_input = QtWidgets.QLineEdit()
        self.user_input.setPlaceholderText("用户名")
        self.password_input = QtWidgets.QLineEdit()
        self.password_input.setPlaceholderText("密码")
        self.password_input.setEchoMode(QtWidgets.QLineEdit.Password)
        self.type_input = QtWidgets.QComboBox()
        self.type_input.addItems(["ECU", "网关", "域控", "其他"])
        self.add_btn = ModernButton("添加设备", "#0EA5E9", "➕")

        for w in [self.ip_input, self.port_input, self.user_input, self.password_input, self.name_input, self.type_input, self.add_btn]:
            form_layout.addWidget(w)
        form_layout.addStretch()
        input_group.setLayout(form_layout)
        self.layout.addWidget(input_group)

        # 设备表格
        # 列：序号 / 设备名 / 设备类型 / IP地址 / SSH端口 / 连接状态(3行) / 详情(3行) / 操作
        self.table = QtWidgets.QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(["序号", "设备名", "设备类型", "IP地址", "SSH端口", "连接状态", "详情", "操作"])
        self.table.verticalHeader().setVisible(False)
        self.table.setWordWrap(False)
        vheader = self.table.verticalHeader()
        vheader.setDefaultSectionSize(64)
        vheader.setMinimumSectionSize(56)
        hheader = self.table.horizontalHeader()

        hheader.setStretchLastSection(True)
        hheader.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # 序号
        hheader.setSectionResizeMode(1, QHeaderView.Interactive)       # 设备名
        hheader.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # 设备类型
        hheader.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # IP地址
        hheader.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # 端口
        hheader.setSectionResizeMode(5, QHeaderView.Interactive)       # 连接状态
        hheader.setSectionResizeMode(6, QHeaderView.Interactive)       # 详情
        hheader.setSectionResizeMode(7, QHeaderView.Stretch)           # 操作

        self.table.setColumnWidth(1, 150)
        self.table.setColumnWidth(2, 90)
        # 加宽连接状态和详情列，便于三行显示
        self.table.setColumnWidth(5, 170)
        self.table.setColumnWidth(6, 220)

        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setHorizontalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        # 右键菜单不再用于修改信息，改由操作列按钮承担，可视需要保留或关闭
        # Use enum if available to satisfy static checkers
        if hasattr(_Qt, "ContextMenuPolicy"):
            self.table.setContextMenuPolicy(_Qt.ContextMenuPolicy.DefaultContextMenu)
        else:
            self.table.setContextMenuPolicy(_Qt.DefaultContextMenu)
        self.layout.addWidget(self.table)

        # 操作日志区
        log_group = QtWidgets.QGroupBox("操作日志")
        log_layout = QtWidgets.QVBoxLayout()
        self.log_view = QtWidgets.QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setPlaceholderText("这里显示用户的操作日志...")
        log_layout.addWidget(self.log_view)
        log_group.setLayout(log_layout)
        self.layout.addWidget(log_group)

    def populate(self, devices):
        """devices: list of dict

        约定每个设备 dict 中可以包含（与 DeviceModel 对齐）：
        - ssh_connect_status / doip_connect_status / someip_connect_status:
            每种协议当前状态字符串，包含“在线”则视为在线
        - ssh_connect_info / doip_connect_info / someip_connect_info:
            每种协议最近一次连接/断开/失败的详情信息

        Service / Controller 在连接或断开时负责填充上述字段，
        此处仅负责展示。
        """
        self.table.setRowCount(len(devices))

        def _icon_for(status: str) -> str:
            # 简单规则：包含“在线”则为在线，否则离线
            return ONLINE_ICON if status and ("建链成功" in str(status)) else OFFLINE_ICON

        for row, dev in enumerate(devices):
            name = dev.get("name", "")
            dev_type = dev.get("type", "未知")
            ip = dev.get("ip", "")
            port = dev.get("port", dev.get("ssh_port", "22"))

            # 从 model 中新的字段读取各协议状态
            ssh_status = str(dev.get("ssh_connect_status", "离线"))
            doip_status = str(dev.get("doip_connect_status", "离线"))
            someip_status = str(dev.get("someip_connect_status", "离线"))

            # 序号
            index_item = QtWidgets.QTableWidgetItem(str(row + 1))
            index_item.setTextAlignment(ALIGN_CENTER_ITEM)
            self.table.setItem(row, 0, index_item)

            # 设备名
            name_item = QtWidgets.QTableWidgetItem(name)
            name_item.setTextAlignment(ALIGN_CENTER_ITEM)
            self.table.setItem(row, 1, name_item)

            # 设备类型
            type_item = QtWidgets.QTableWidgetItem(dev_type)
            type_item.setTextAlignment(ALIGN_CENTER_ITEM)
            self.table.setItem(row, 2, type_item)

            # IP
            ip_item = QtWidgets.QTableWidgetItem(ip)
            ip_item.setTextAlignment(ALIGN_CENTER_ITEM)
            self.table.setItem(row, 3, ip_item)

            # 端口
            port_item = QtWidgets.QTableWidgetItem(str(port))
            port_item.setTextAlignment(ALIGN_CENTER_ITEM)
            self.table.setItem(row, 4, port_item)

            # 连接状态列：3 行文字 + 在线/离线图标
            status_widget = QtWidgets.QWidget()
            status_layout = QtWidgets.QVBoxLayout(status_widget)
            status_layout.setContentsMargins(4, 2, 4, 2)
            status_layout.setSpacing(0)

            ssh_label = QtWidgets.QLabel(f"{_icon_for(ssh_status)} SSH: {ssh_status}")
            doip_label = QtWidgets.QLabel(f"{_icon_for(doip_status)} DoIP: {doip_status}")
            someip_label = QtWidgets.QLabel(f"{_icon_for(someip_status)} SomeIP: {someip_status}")
            for lbl in (ssh_label, doip_label, someip_label):
                lbl.setAlignment(ALIGN_LEFT_LABEL)
                status_layout.addWidget(lbl)

            self.table.setCellWidget(row, 5, status_widget)

            # 详情列：直接展示各协议的 *_connect_info 字段
            ssh_detail = dev.get("ssh_connect_info", "")
            doip_detail = dev.get("doip_connect_info", "")
            someip_detail = dev.get("someip_connect_info", "")

            detail_widget = QtWidgets.QWidget()
            detail_layout = QtWidgets.QVBoxLayout(detail_widget)
            detail_layout.setContentsMargins(4, 2, 4, 2)
            detail_layout.setSpacing(0)

            ssh_detail_label = QtWidgets.QLabel(f"SSH: {ssh_detail or '无'}")
            doip_detail_label = QtWidgets.QLabel(f"DoIP: {doip_detail or '无'}")
            someip_detail_label = QtWidgets.QLabel(f"SomeIP: {someip_detail or '无'}")
            for lbl in (ssh_detail_label, doip_detail_label, someip_detail_label):
                lbl.setAlignment(ALIGN_LEFT_LABEL)
                detail_layout.addWidget(lbl)

            self.table.setCellWidget(row, 6, detail_widget)

            # 操作列：连接 / 断开 / 修改信息 / 删除 / 软件升级 / 状态查询
            action_widget = QtWidgets.QWidget()
            ah = QtWidgets.QHBoxLayout(action_widget)
            ah.setContentsMargins(4, 4, 4, 4)
            ah.setSpacing(8)

            connect_btn = TableButton("连接设备", "#059669")
            disconnect_btn = TableButton("断开连接", "#F59E0B")
            edit_btn = TableButton("修改信息", "#3B82F6")
            delete_btn = TableButton("删除设备", "#EF4444")
            upgrade_btn = TableButton("软件升级", "#6366F1")
            query_btn = TableButton("状态查询", "#0EA5E9")

            for b in [connect_btn, disconnect_btn, edit_btn, delete_btn, upgrade_btn, query_btn]:
                b.setMinimumWidth(78)
                ah.addWidget(b)
            ah.addStretch(1)

            self.table.setCellWidget(row, 7, action_widget)

    def append_log(self, text: str):
        self.log_view.append(text)
