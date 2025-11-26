from PyQt5 import QtWidgets, QtCore, QtGui

from app.common.ui.widgets import ModernButton, TableButton
from app.presentation.views.base_view import BaseView

ALIGN_CENTER = int(getattr(QtCore.Qt, "AlignCenter", 132))


class UpgradeView(BaseView):
    """纯 UI 升级页面：仅负责界面布局，不包含业务逻辑或信号。"""

    def setup_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(12, 12, 12, 12)

        # --- File / configuration group ---
        config_group = QtWidgets.QGroupBox("升级文件与配置")
        config_layout = QtWidgets.QGridLayout()
        config_layout.setHorizontalSpacing(10)
        config_layout.setVerticalSpacing(8)

        # Upgrade package
        config_layout.addWidget(QtWidgets.QLabel("📦 升级包:"), 0, 0)
        self.upgrade_file = QtWidgets.QLineEdit()
        self.upgrade_file.setPlaceholderText("选择升级包 (.zip / .bin)")
        config_layout.addWidget(self.upgrade_file, 0, 1)
        config_layout.addWidget(ModernButton("浏览", "#0EA5E9", "📂"), 0, 2)

        # Config file
        config_layout.addWidget(QtWidgets.QLabel("⚙️ 配置文件:"), 1, 0)
        self.config_file = QtWidgets.QLineEdit()
        self.config_file.setPlaceholderText("选择升级配置 (.json / .yaml)")
        config_layout.addWidget(self.config_file, 1, 1)
        config_layout.addWidget(ModernButton("浏览", "#0EA5E9", "📂"), 1, 2)

        # Checksum / size info
        config_layout.addWidget(QtWidgets.QLabel("🔐 校验信息:"), 2, 0)
        self.checksum_label = QtWidgets.QLabel("未解析")
        self.checksum_label.setStyleSheet("color:#6B7280;")
        config_layout.addWidget(self.checksum_label, 2, 1)
        config_layout.addWidget(TableButton("重新解析", "#6B7280", "🔄"), 2, 2)

        # Global progress
        config_layout.addWidget(QtWidgets.QLabel("📊 全局进度:"), 3, 0)
        self.global_progress = QtWidgets.QProgressBar()
        self.global_progress.setRange(0, 100)
        self.global_progress.setValue(0)
        self.global_progress.setFormat("0%")
        self.global_progress.setMinimumHeight(22)
        config_layout.addWidget(self.global_progress, 3, 1, 1, 2)

        # Action buttons row
        action_row = QtWidgets.QHBoxLayout()
        action_row.setSpacing(12)
        action_row.addStretch(1)
        self.start_btn = ModernButton("开始升级", "#059669", "🚀")
        self.stop_btn = ModernButton("停止升级", "#EF4444", "⏹️")
        self.start_btn.setEnabled(False)  # 需选择文件后启用
        self.stop_btn.setEnabled(False)
        action_row.addWidget(self.start_btn)
        action_row.addWidget(self.stop_btn)
        config_layout.addLayout(action_row, 4, 0, 1, 3)

        config_group.setLayout(config_layout)
        main_layout.addWidget(config_group)

        # --- Device progress table ---
        device_group = QtWidgets.QGroupBox("设备升级进度")
        device_layout = QtWidgets.QVBoxLayout()
        self.device_table = QtWidgets.QTableWidget(0, 5)
        self.device_table.setHorizontalHeaderLabels(["设备", "阶段", "进度", "状态", "操作"])
        self.device_table.verticalHeader().setVisible(False)
        self.device_table.setAlternatingRowColors(True)
        self.device_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.device_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.device_table.setWordWrap(False)
        vheader = self.device_table.verticalHeader()
        vheader.setDefaultSectionSize(44)
        vheader.setMinimumSectionSize(40)
        hheader = self.device_table.horizontalHeader()
        hheader.setStretchLastSection(False)
        hheader.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        hheader.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        hheader.setSectionResizeMode(2, QtWidgets.QHeaderView.Fixed)
        self.device_table.setColumnWidth(2, 200)  # Progress column
        hheader.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeToContents)
        hheader.setSectionResizeMode(4, QtWidgets.QHeaderView.Fixed)
        self.device_table.setColumnWidth(4, 180)
        device_layout.addWidget(self.device_table)

        # Helper buttons under table
        table_actions = QtWidgets.QHBoxLayout()
        table_actions.addStretch(1)
        table_actions.addWidget(TableButton("重试失败设备", "#0EA5E9", "🔄"))
        table_actions.addWidget(TableButton("取消全部", "#EF4444", "✕"))
        table_actions.addStretch(1)
        device_layout.addLayout(table_actions)

        device_group.setLayout(device_layout)
        main_layout.addWidget(device_group, 1)

        # --- Log panel ---
        log_group = QtWidgets.QGroupBox("升级日志")
        log_layout = QtWidgets.QVBoxLayout()
        filter_row = QtWidgets.QHBoxLayout()
        filter_row.addWidget(QtWidgets.QLabel("🔍 过滤:"))
        self.log_filter = QtWidgets.QLineEdit()
        self.log_filter.setPlaceholderText("输入关键字过滤日志")
        filter_row.addWidget(self.log_filter)
        self.auto_scroll_chk = QtWidgets.QCheckBox("自动滚动")
        self.auto_scroll_chk.setChecked(True)
        filter_row.addWidget(self.auto_scroll_chk)
        filter_row.addWidget(TableButton("清空", "#6B7280", "🧹"))
        filter_row.addStretch(1)
        log_layout.addLayout(filter_row)
        self.upgrade_log = QtWidgets.QTextEdit()
        self.upgrade_log.setReadOnly(True)
        self.upgrade_log.setFont(QtGui.QFont("Consolas", 9))
        self.upgrade_log.setMinimumHeight(180)
        log_layout.addWidget(self.upgrade_log)
        log_group.setLayout(log_layout)
        main_layout.addWidget(log_group, 1)

        # Demo 设备展示（UI 预览用途）
        self._render_demo_rows(["CCUA", "CCU0", "CCU1"])

    def _render_demo_rows(self, devices):
        self.device_table.setRowCount(len(devices))
        for row, dev in enumerate(devices):
            self.device_table.setItem(row, 0, QtWidgets.QTableWidgetItem(dev))
            stage = QtWidgets.QTableWidgetItem("未开始")
            stage.setTextAlignment(ALIGN_CENTER)
            self.device_table.setItem(row, 1, stage)
            progress_widget = QtWidgets.QWidget()
            pw_layout = QtWidgets.QHBoxLayout(progress_widget)
            pw_layout.setContentsMargins(6, 4, 6, 4)
            pw_layout.setSpacing(8)
            bar = QtWidgets.QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(0)
            bar.setFormat("0%")
            bar.setMinimumWidth(120)
            pw_layout.addWidget(bar)
            pw_layout.addWidget(TableButton("取消", "#EF4444", "✕"))
            pw_layout.addStretch(1)
            self.device_table.setCellWidget(row, 2, progress_widget)
            status_item = QtWidgets.QTableWidgetItem("等待")
            status_item.setTextAlignment(ALIGN_CENTER)
            self.device_table.setItem(row, 3, status_item)
            action_widget = QtWidgets.QWidget()
            aw_layout = QtWidgets.QHBoxLayout(action_widget)
            aw_layout.setContentsMargins(6, 4, 6, 4)
            aw_layout.setSpacing(8)
            aw_layout.addStretch(1)
            aw_layout.addWidget(TableButton("重试", "#0EA5E9", "🔄"))
            aw_layout.addStretch(1)
            action_widget.setLayout(aw_layout)
            self.device_table.setCellWidget(row, 4, action_widget)


if __name__ == "__main__":
    app = QtWidgets.QApplication([])
    w = UpgradeView()
    w.setup_ui()
    w.show()
    app.exec_()
