from PyQt5 import QtWidgets
from PyQt5.QtWidgets import QHeaderView
from PyQt5.QtCore import Qt as _Qt

from app.common.ui.widgets import ModernButton, TableButton
from app.presentation.views.base_view import BaseView

ALIGN_CENTER = int(getattr(_Qt, "AlignCenter", 132))


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
        self.port_input.setPlaceholderText("SSH端口")
        self.user_input = QtWidgets.QLineEdit()
        self.user_input.setPlaceholderText("用户名")
        self.name_input = QtWidgets.QLineEdit()
        self.name_input.setPlaceholderText("设备名")

        self.add_btn = ModernButton("添加设备", "#0EA5E9", "➕")

        for w in [self.ip_input, self.port_input, self.user_input, self.name_input, self.add_btn]:
            form_layout.addWidget(w)
        form_layout.addStretch()
        input_group.setLayout(form_layout)
        self.layout.addWidget(input_group)

        # 设备表格
        self.table = QtWidgets.QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["序号", "设备名", "IP地址", "SSH端口", "连接状态", "详情", "操作"])
        self.table.verticalHeader().setVisible(False)
        self.table.setWordWrap(False)
        vheader = self.table.verticalHeader()
        vheader.setDefaultSectionSize(52)
        vheader.setMinimumSectionSize(44)
        hheader = self.table.horizontalHeader()

        # 列宽策略：操作列 Stretch，设备名列 Interactive，详情列 Fixed
        hheader.setStretchLastSection(True)
        hheader.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # 序号
        hheader.setSectionResizeMode(1, QHeaderView.Interactive)       # 设备名
        hheader.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # IP地址
        hheader.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # 端口
        hheader.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # 状态
        hheader.setSectionResizeMode(5, QHeaderView.Fixed)             # 详情
        hheader.setSectionResizeMode(6, QHeaderView.Stretch)           # 操作

        # 初始列宽
        self.table.setColumnWidth(1, 220)   # 设备名
        self.table.setColumnWidth(5, 90)    # 详情按钮列

        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setHorizontalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
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
        """
        devices: list of dict
        期望字段：
          name, ip, port, status
        若不存在则尝试从旧字段映射（兼容旧模型）
        """
        self.table.setRowCount(len(devices))
        for row, dev in enumerate(devices):
            name = dev.get("name", "")
            ip = dev.get("ip", "")
            port = dev.get("port", dev.get("ssh_port", "22"))
            status = dev.get("status") or dev.get("ssh") or dev.get("doip") or "未知"

            # 序号
            index_item = QtWidgets.QTableWidgetItem(str(row + 1))
            index_item.setTextAlignment(ALIGN_CENTER)
            self.table.setItem(row, 0, index_item)
            # 设备名
            name_item = QtWidgets.QTableWidgetItem(name)
            name_item.setTextAlignment(ALIGN_CENTER)
            self.table.setItem(row, 1, name_item)
            # IP
            ip_item = QtWidgets.QTableWidgetItem(ip)
            ip_item.setTextAlignment(ALIGN_CENTER)
            self.table.setItem(row, 2, ip_item)
            # 端口
            port_item = QtWidgets.QTableWidgetItem(str(port))
            port_item.setTextAlignment(ALIGN_CENTER)
            self.table.setItem(row, 3, port_item)
            # 状态
            status_item = QtWidgets.QTableWidgetItem(status)
            status_item.setTextAlignment(ALIGN_CENTER)
            self.table.setItem(row, 4, status_item)

            # 详情列
            detail_widget = QtWidgets.QWidget()
            dh = QtWidgets.QHBoxLayout(detail_widget)
            dh.setContentsMargins(4, 4, 4, 4)
            dh.setSpacing(4)
            detail_label = QtWidgets.QLabel("详情")
            dh.addStretch(1)
            dh.addWidget(detail_label)
            dh.addStretch(1)
            self.table.setCellWidget(row, 5, detail_widget)

            # 操作列
            action_widget = QtWidgets.QWidget()
            ah = QtWidgets.QHBoxLayout(action_widget)
            ah.setContentsMargins(4, 4, 4, 4)
            ah.setSpacing(8)

            connect_btn = TableButton("连接设备", "#059669")
            disconnect_btn = TableButton("断开连接", "#F59E0B")
            delete_btn = TableButton("删除设备", "#EF4444")
            upgrade_btn = TableButton("软件升级", "#6366F1")
            query_btn = TableButton("状态查询", "#0EA5E9")

            # 给按钮设置最小宽度，避免列压缩过小时文本被挤压重叠
            for b in [connect_btn, disconnect_btn, delete_btn, upgrade_btn, query_btn]:
                b.setMinimumWidth(84)
                ah.addWidget(b)
            ah.addStretch(1)

            self.table.setCellWidget(row, 6, action_widget)

    def append_log(self, text: str):
        self.log_view.append(text)
