from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QComboBox, QGroupBox, QFormLayout, QLabel)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5 import QtCore
from PyQt5.QtGui import QFont

class SomeIPSettingsPage(QWidget):
    """SomeIP Protocol Settings Page"""
    save_signal = pyqtSignal(dict)
    reset_signal = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout()
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # Title
        title_label = QLabel("SomeIP 协议设置")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setStyleSheet("color: #2c3e50;")
        main_layout.addWidget(title_label)

        # someip group
        someip_group = self._create_group_box("SomeIP 配置", "#3498db")
        someip_layout = QFormLayout()
        someip_layout.setSpacing(12)

        # Network Interface
        self.network_combo = QComboBox()
        QtCore.QTimer.singleShot(100, self._load_network_interfaces)
        someip_layout.addRow("网络接口:", self.network_combo)

        someip_group.setLayout(someip_layout)
        main_layout.addWidget(someip_group)
        main_layout.addStretch()
        self.setLayout(main_layout)

    def _create_group_box(self, title, border_color):
        """Create styled GroupBox"""
        group = QGroupBox(title)
        # Simplified style logic
        if border_color == "#3498db":
            border_color = "#3B82F6"
            title_color = "#1E40AF"
            bg_color = "#EFF6FF"
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

    def _load_network_interfaces(self):
        self.network_combo.clear()
        try:
            from app.common.communication.clients.Doip_Client import DoIPClientHandler
            handler = DoIPClientHandler()
            interfaces = handler.get_network_interfaces()
            for name, ip in interfaces:
                self.network_combo.addItem(f"[{name}] {ip}", ip)
        except Exception as e:
            self.network_combo.addItem(f"Error loading interfaces: {e}")

    def load_settings(self, settings):
        """Load settings into UI"""
        local_ip = settings.get("local_ip", "")
        if local_ip:
            index = self.network_combo.findData(local_ip)
            if index >= 0:
                self.network_combo.setCurrentIndex(index)

    def save_settings(self):
        """Save settings"""
        settings = {
            "local_ip": self.network_combo.currentData()
        }
        self.save_signal.emit(settings)

    def reset_to_defaults(self):
        """Reset to defaults"""
        self.reset_signal.emit()
