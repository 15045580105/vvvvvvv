from PyQt5 import QtWidgets, QtGui

from app.common.ui.widgets import ModernButton
from app.presentation.views.base_view import BaseView


class UpgradeView(BaseView):
    def setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(16)
        file_group = QtWidgets.QGroupBox("升级文件配置")
        file_layout = QtWidgets.QHBoxLayout()
        file_layout.setSpacing(12)
        file_layout.addWidget(QtWidgets.QLabel("📦 升级包:"))
        self.upgrade_file = QtWidgets.QLineEdit()
        file_layout.addWidget(self.upgrade_file)
        file_layout.addWidget(ModernButton("浏览...", "#0EA5E9", "📂"))
        file_layout.addWidget(QtWidgets.QLabel("⚙️ 配置:"))
        self.config_file = QtWidgets.QLineEdit()
        file_layout.addWidget(self.config_file)
        file_layout.addWidget(ModernButton("浏览...", "#0EA5E9", "📂"))
        file_group.setLayout(file_layout)
        layout.addWidget(file_group)
        progress_group = QtWidgets.QGroupBox("升级进度监控")
        progress_layout = QtWidgets.QVBoxLayout()
        self.progress_bars = {}
        for device in ["CCUA", "CCU0", "CCU1"]:
            device_layout = QtWidgets.QHBoxLayout()
            device_layout.addWidget(QtWidgets.QLabel(f"📡 {device}:"))
            bar = QtWidgets.QProgressBar()
            bar.setValue(0)
            bar.setFormat("等待中")
            bar.setMaximumWidth(500)
            device_layout.addWidget(bar)
            device_layout.addWidget(QtWidgets.QLabel("状态: 未开始"))
            device_layout.addStretch()
            progress_layout.addLayout(device_layout)
            self.progress_bars[device] = bar
        progress_group.setLayout(progress_layout)
        layout.addWidget(progress_group)
        log_group = QtWidgets.QGroupBox("升级日志")
        log_layout = QtWidgets.QVBoxLayout()
        self.upgrade_log = QtWidgets.QTextEdit()
        self.upgrade_log.setReadOnly(True)
        self.upgrade_log.setMaximumHeight(200)
        self.upgrade_log.setFont(QtGui.QFont("Consolas", 9))
        log_layout.addWidget(self.upgrade_log)
        log_group.setLayout(log_layout)
        layout.addWidget(log_group)
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addStretch()
        self.start_btn = ModernButton("开始升级", "#059669", "🚀")
        self.stop_btn = ModernButton("停止", "#EF4444", "⏹️")
        btn_layout.addWidget(self.start_btn)
        btn_layout.addWidget(self.stop_btn)
        layout.addLayout(btn_layout)
