from PyQt5 import QtWidgets
from PyQt5.QtWidgets import QHeaderView
from PyQt5.QtCore import Qt as _Qt

from app.common.ui.widgets import ModernButton, TableButton
from app.presentation.views.base_view import BaseView

# Compatibility constants
ALIGN_CENTER = int(getattr(_Qt, "AlignCenter", 132))


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
        # 表格布局优化：提高行高、关闭自动换行、设置列宽策略
        self.table.setWordWrap(False)
        vheader = self.table.verticalHeader()
        vheader.setDefaultSectionSize(48)
        vheader.setMinimumSectionSize(44)
        hheader = self.table.horizontalHeader()
        hheader.setStretchLastSection(False)
        # 使用 QHeaderView 的枚举，避免类型检查问题
        hheader.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hheader.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hheader.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hheader.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hheader.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        hheader.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        # 操作列固定宽度，适配两个 TableButton
        action_col_width = 160
        self.table.setColumnWidth(5, action_col_width)
        # 交替行色、按行选择
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.layout.addWidget(self.table)

    def populate(self, devices):
        self.table.setRowCount(len(devices))
        for row, dev in enumerate(devices):
            for col, key in enumerate(["name", "ip", "doip", "ssh", "time"]):
                item = QtWidgets.QTableWidgetItem(dev[key])
                item.setTextAlignment(ALIGN_CENTER)
                self.table.setItem(row, col, item)
            # 操作列：居中显示 TableButton
            action_widget = QtWidgets.QWidget()
            h = QtWidgets.QHBoxLayout(action_widget)
            h.setContentsMargins(8,4,8,4)
            h.setSpacing(8)
            view_btn = TableButton("详情", "#6B7280")
            h.addStretch(1)
            h.addWidget(view_btn)
            h.addStretch(1)
            self.table.setCellWidget(row, 5, action_widget)

if __name__ == '__main__':
    import sys
    app = QtWidgets.QApplication(sys.argv)
    w = DeviceView()
    w.populate([
        {"name": "设备1", "ip": "192.168.1.1", "doip": "已连接", "ssh": "已连接", "time": "2023-05-01 12:34:56"},
        {"name": "设备2", "ip": "192.168.1.2", "doip": "已连接", "ssh": "已连接", "time": "2023-05-01 12:34:56"},
    ])
    w.show()
    sys.exit(app.exec_())