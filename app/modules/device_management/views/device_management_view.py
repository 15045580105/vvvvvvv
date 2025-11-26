from PyQt5 import QtWidgets, QtCore
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableView,
                             QPushButton, QLabel, QToolBar, QHeaderView)
from PyQt5.QtCore import Qt, pyqtSignal

from app.common.ui.widgets import ModernButton
from app.presentation.views.base_view import BaseView


class DeviceView(BaseView):
    def setup_ui(self):
        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.setSpacing(16)
        control_group = QtWidgets.QGroupBox("设备控制")
        control_layout = QtWidgets.QHBoxLayout()
        control_layout.setSpacing(12)
        control_layout.addWidget(QtWidgets.QLabel("📡 快速操作:"))
        self.scan_btn = ModernButton("扫描设备", "#0EA5E9", "🔍")
        self.connect_btn = ModernButton("连接选中", "#059669", "🔗")
        self.disconnect_btn = ModernButton("断开连接", "#F59E0B", "⏏️")
        self.delete_btn = ModernButton("删除设备", "#EF4444", "🗑️")
        for b in [self.scan_btn, self.connect_btn, self.disconnect_btn, self.delete_btn]:
            control_layout.addWidget(b)
        control_layout.addStretch()
        control_group.setLayout(control_layout)
        self.layout.addWidget(control_group)

        self.table = QtWidgets.QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["设备名称", "IP地址", "DoIP状态", "SSH状态", "连接时间", "操作"])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.verticalHeader().setDefaultSectionSize(44)
        self.layout.addWidget(self.table)

    def populate(self, devices):
        self.table.setRowCount(len(devices))
        for row, dev in enumerate(devices):
            for col, key in enumerate(["name", "ip", "doip", "ssh", "time"]):
                item = QtWidgets.QTableWidgetItem(dev[key])
                item.setTextAlignment(QtCore.Qt.AlignCenter)
                self.table.setItem(row, col, item)
            # action cell placeholder
            action_widget = QtWidgets.QWidget()
            h = QtWidgets.QHBoxLayout(action_widget)
            h.setContentsMargins(2,2,2,2)
            h.setSpacing(4)
            view_btn = ModernButton("详情", "#6B7280")
            h.addWidget(view_btn)
            h.addStretch()
            self.table.setCellWidget(row, 5, action_widget)

