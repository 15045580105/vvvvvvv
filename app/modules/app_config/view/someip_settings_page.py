from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QComboBox, QGroupBox, QFormLayout, QLabel,
                             QHBoxLayout, QLineEdit, QPushButton, QFileDialog, QProgressBar)
from PyQt5.QtCore import pyqtSignal
from PyQt5 import QtCore
from PyQt5.QtGui import QFont

class SomeIPSettingsPage(QWidget):
    """SomeIP Protocol Settings Page"""
    save_signal = pyqtSignal(dict)
    reset_signal = pyqtSignal()
    import_matrix_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._importing = False
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

        matrix_file_layout = QHBoxLayout()
        self.matrix_file_edit = QLineEdit("")
        self.matrix_file_edit.setReadOnly(True)
        self.browse_matrix_btn = QPushButton("浏览")
        self.browse_matrix_btn.setStyleSheet(self._get_button_style("#3498db", "#5dade2", "#2980b9"))
        self.browse_matrix_btn.clicked.connect(self.browse_matrix_file)
        self.import_matrix_btn = QPushButton("导入")
        self.import_matrix_btn.setStyleSheet(self._get_button_style("#22c55e", "#4ade80", "#16a34a"))
        self.import_matrix_btn.clicked.connect(self.import_matrix_file)
        matrix_file_layout.addWidget(self.matrix_file_edit)
        matrix_file_layout.addWidget(self.browse_matrix_btn)
        matrix_file_layout.addWidget(self.import_matrix_btn)
        someip_layout.addRow("SomeIP 矩阵表:", matrix_file_layout)

        self.import_progress_bar = QProgressBar()
        self.import_progress_bar.setRange(0, 100)
        self.import_progress_bar.setValue(0)
        self.import_progress_bar.setVisible(False)
        someip_layout.addRow("导入进度:", self.import_progress_bar)

        self.import_status_label = QLabel("未导入矩阵")
        self.import_status_label.setStyleSheet("color: #6b7280;")
        someip_layout.addRow("导入状态:", self.import_status_label)

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

    def _get_button_style(self, bg_color, hover_color, pressed_color):
        """Get button stylesheet"""
        return f"""
            QPushButton {{
                background-color: {bg_color};
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 4px;
                font-weight: 600;
                font-family: \"Segoe UI\", \"Microsoft YaHei\";
            }}
            QPushButton:hover {{
                background-color: {hover_color};
            }}
            QPushButton:pressed {{
                background-color: {pressed_color};
            }}
        """

    def import_matrix_file(self):
        """Import selected SomeIP matrix file asynchronously."""
        file_path = self.matrix_file_edit.text().strip()
        if file_path and not self._importing:
            self.import_matrix_signal.emit(file_path)

    def browse_matrix_file(self):
        """Browse SomeIP matrix Excel file"""
        if self._importing:
            return
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 SomeIP 矩阵表",
            "",
            "Excel 文件 (*.xlsx *.xls);;所有文件 (*.*)"
        )
        if file_path:
            self.matrix_file_edit.setText(file_path)
            self.import_status_label.setText("已选择矩阵文件，等待导入")
            self.import_status_label.setStyleSheet("color: #2563eb;")

    def load_settings(self, settings):
        """Load settings into UI"""
        local_ip = settings.get("local_ip", "")
        if local_ip:
            index = self.network_combo.findData(local_ip)
            if index >= 0:
                self.network_combo.setCurrentIndex(index)
        matrix_file = settings.get("matrix_file", "")
        self.matrix_file_edit.setText(matrix_file)
        if matrix_file:
            self.import_status_label.setText("已保存矩阵文件路径")
            self.import_status_label.setStyleSheet("color: #16a34a;")
        else:
            self.import_status_label.setText("未导入矩阵")
            self.import_status_label.setStyleSheet("color: #6b7280;")

    def set_import_in_progress(self, in_progress: bool, message: str = ""):
        self._importing = in_progress
        self.browse_matrix_btn.setEnabled(not in_progress)
        self.import_matrix_btn.setEnabled(not in_progress and bool(self.matrix_file_edit.text().strip()))
        self.import_progress_bar.setVisible(in_progress)
        if in_progress:
            self.import_progress_bar.setValue(0)
            self.import_status_label.setText(message or "正在导入矩阵...")
            self.import_status_label.setStyleSheet("color: #2563eb;")

    def update_import_progress(self, progress: int, message: str = ""):
        self.import_progress_bar.setVisible(True)
        self.import_progress_bar.setValue(max(0, min(100, progress)))
        if message:
            self.import_status_label.setText(message)
            self.import_status_label.setStyleSheet("color: #2563eb;")

    def handle_import_finished(self, success: bool, message: str):
        self._importing = False
        self.import_progress_bar.setVisible(False)
        self.browse_matrix_btn.setEnabled(True)
        self.import_matrix_btn.setEnabled(bool(self.matrix_file_edit.text().strip()))
        self.import_status_label.setText(message)
        self.import_status_label.setStyleSheet("color: #16a34a;" if success else "color: #dc2626;")

    def save_settings(self):
        """Save settings"""
        ip_data = self.network_combo.currentData()
        # Ensure data is serializable (convert to str if it's not None)
        if ip_data is not None and not isinstance(ip_data, (str, int, float, bool)):
            ip_data = str(ip_data)

        settings = {
            "local_ip": ip_data,
            "matrix_file": self.matrix_file_edit.text().strip()
        }
        self.save_signal.emit(settings)

    def reset_to_defaults(self):
        """Reset to defaults"""
        self.matrix_file_edit.clear()
        self.import_progress_bar.setVisible(False)
        self.import_progress_bar.setValue(0)
        self.import_status_label.setText("未导入矩阵")
        self.import_status_label.setStyleSheet("color: #6b7280;")
        self.reset_signal.emit()
