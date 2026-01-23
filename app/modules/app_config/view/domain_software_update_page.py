from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QLineEdit, QCheckBox,
                             QGroupBox, QFormLayout)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QIntValidator


class DomainSoftwareUpdatePage(QWidget):
    """Domain Software Update设置页面"""
    save_signal = pyqtSignal(dict)
    reset_signal = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        """初始化界面"""
        main_layout = QVBoxLayout()
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # 标题
        title_label = QLabel("域软件升级设置")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setStyleSheet("color: #2c3e50;")
        main_layout.addWidget(title_label)

        # Stress Test组
        stress_group = self._create_group_box("压力测试", "#9b59b6")

        stress_layout = QFormLayout()
        stress_layout.setSpacing(12)
        stress_layout.setLabelAlignment(Qt.AlignLeft)

        # 成功后启动延迟
        success_delay_layout = QHBoxLayout()
        self.success_delay_edit = QLineEdit("20")
        self.success_delay_edit.setMaximumWidth(150)
        int_validator = QIntValidator(0, 3600)
        self.success_delay_edit.setValidator(int_validator)
        success_delay_layout.addWidget(self.success_delay_edit)
        success_delay_layout.addWidget(QLabel("s"))
        success_delay_layout.addStretch()
        stress_layout.addRow("成功后启动延迟:", success_delay_layout)

        # 失败后启动延迟
        failure_delay_layout = QHBoxLayout()
        self.failure_delay_edit = QLineEdit("20")
        self.failure_delay_edit.setMaximumWidth(150)
        self.failure_delay_edit.setValidator(int_validator)
        failure_delay_layout.addWidget(self.failure_delay_edit)
        failure_delay_layout.addWidget(QLabel("s"))
        failure_delay_layout.addStretch()
        stress_layout.addRow("失败后启动延迟:", failure_delay_layout)

        # Send EcuReset after failure
        self.ecu_reset_check = QCheckBox("启用")
        self.ecu_reset_check.setChecked(False)
        stress_layout.addRow("失败后发送 EcuReset:", self.ecu_reset_check)

        # Stop stress test on failure
        self.stop_on_failure_check = QCheckBox("启用")
        self.stop_on_failure_check.setChecked(False)
        stress_layout.addRow("失败时停止测试:", self.stop_on_failure_check)

        stress_group.setLayout(stress_layout)
        main_layout.addWidget(stress_group)

        main_layout.addStretch()
        self.setLayout(main_layout)

    def _create_group_box(self, title, border_color):
        """创建统一风格的GroupBox"""
        group = QGroupBox(title)
        # 使用主题颜色替换硬编码颜色
        if border_color == "#3498db": # Blue
            border_color = "#3B82F6"
            title_color = "#1E40AF"
            bg_color = "#EFF6FF"
        elif border_color == "#e74c3c": # Red
            border_color = "#EF4444"
            title_color = "#991B1B"
            bg_color = "#FEF2F2"
        elif border_color == "#9b59b6": # Purple
            border_color = "#8B5CF6"
            title_color = "#5B21B6"
            bg_color = "#F5F3FF"
        else:
            title_color = "#374151"
            bg_color = "#F9FAFB"

        group.setStyleSheet(f"""
            QGroupBox {{
                font-weight: 600;
                border: 1px solid {border_color};
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 16px;
                font-family: "Segoe UI", "Microsoft YaHei";
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 12px;
                padding: 4px 8px;
                color: {title_color};
                background-color: {bg_color};
                border-radius: 4px;
            }}
        """)
        return group

    def update_ui(self, settings):
        """更新界面显示"""
        self.success_delay_edit.setText(settings.get("success_delay", "20"))
        self.failure_delay_edit.setText(settings.get("failure_delay", "20"))
        self.ecu_reset_check.setChecked(settings.get("ecu_reset", False))
        self.stop_on_failure_check.setChecked(settings.get("stop_on_failure", False))

    def save_settings(self):
        """保存设置"""
        settings = {
            "success_delay": self.success_delay_edit.text(),
            "failure_delay": self.failure_delay_edit.text(),
            "ecu_reset": self.ecu_reset_check.isChecked(),
            "stop_on_failure": self.stop_on_failure_check.isChecked()
        }
        self.save_signal.emit(settings)

    def reset_to_defaults(self):
        """重置为默认值"""
        self.reset_signal.emit()
