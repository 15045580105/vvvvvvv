from PyQt5 import QtWidgets, QtCore

from app.common.ui.widgets import ModernButton


class PerformanceView(QtWidgets.QWidget):
    def __init__(self, model, parent=None):
        super().__init__(parent)
        self.model = model
        self.setWindowTitle("性能监控")
        self.resize(1000, 700)
        self.setup_ui()

    def setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(16)
        control_group = QtWidgets.QGroupBox("监控设置")
        control_layout = QtWidgets.QHBoxLayout()
        control_layout.setSpacing(12)
        control_layout.addWidget(QtWidgets.QLabel("📊 监控周期:"))
        self.cycle_combo = QtWidgets.QComboBox()
        self.cycle_combo.addItems(["1秒", "2秒", "5秒", "10秒"])
        self.cycle_combo.setCurrentText("2秒")
        control_layout.addWidget(self.cycle_combo)
        control_layout.addWidget(ModernButton("开始", "#059669", "▶️"))
        control_layout.addWidget(ModernButton("暂停", "#F59E0B", "⏸️"))
        control_layout.addWidget(ModernButton("重置", "#6B7280", "🔄"))
        control_layout.addStretch()
        control_group.setLayout(control_layout)
        layout.addWidget(control_group)
        self.metrics_table = QtWidgets.QTableWidget(0, 3)
        self.metrics_table.setHorizontalHeaderLabels(["指标名称", "当前值", "状态"])
        self.metrics_table.verticalHeader().setVisible(False)
        layout.addWidget(self.metrics_table)
        process_group = QtWidgets.QGroupBox("进程监控")
        proc_layout = QtWidgets.QVBoxLayout()
        self.process_table = QtWidgets.QTableWidget(0, 5)
        self.process_table.setHorizontalHeaderLabels(["进程名", "PID", "CPU%", "内存(MB)", "用户"])
        self.process_table.verticalHeader().setVisible(False)
        proc_layout.addWidget(self.process_table)
        process_group.setLayout(proc_layout)
        layout.addWidget(process_group)

    def populate(self):
        self.metrics_table.setRowCount(len(self.model.metrics))
        for i, (metric, val, status) in enumerate(self.model.metrics):
            for c, data in enumerate([metric, val, status]):
                it = QtWidgets.QTableWidgetItem(data)
                it.setTextAlignment(QtCore.Qt.AlignCenter)
                self.metrics_table.setItem(i, c, it)
        self.process_table.setRowCount(len(self.model.processes))
        for r, row in enumerate(self.model.processes):
            for c, val in enumerate(row):
                it = QtWidgets.QTableWidgetItem(val)
                it.setTextAlignment(QtCore.Qt.AlignCenter)
                self.process_table.setItem(r, c, it)
