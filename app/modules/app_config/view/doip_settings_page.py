from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QComboBox, QLineEdit, QCheckBox, QPushButton,
                             QGroupBox, QFormLayout, QFileDialog,
                             QRadioButton, QButtonGroup)
from PyQt5.QtCore import Qt, QRegExp, pyqtSignal
from PyQt5 import QtCore
from PyQt5.QtGui import QRegExpValidator, QFont


class DoIPSettingsPage(QWidget):
    """DoIP协议设置页面"""
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
        title_label = QLabel("DoIP 协议设置")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setStyleSheet("color: #2c3e50;")
        main_layout.addWidget(title_label)

        # 协议栈设置组
        protocol_group = self._create_group_box("协议栈", "#3498db")

        protocol_layout = QFormLayout()
        protocol_layout.setSpacing(12)
        protocol_layout.setLabelAlignment(Qt.AlignLeft)

        # 协议版本
        self.protocol_version_combo = QComboBox()
        self.protocol_version_combo.addItem("DoIP V2(ISO 13400-2:2012)")
        self.protocol_version_combo.addItem("DoIP V3(ISO 13400-2:2019)")
        protocol_layout.addRow("协议版本:", self.protocol_version_combo)

        protocol_group.setLayout(protocol_layout)
        main_layout.addWidget(protocol_group)

        # 工具设置组
        tool_group = self._create_group_box("工具设置", "#3498db")

        tool_layout = QFormLayout()
        tool_layout.setSpacing(12)

        # 逻辑地址
        self.logical_addr_edit = QLineEdit("0x0E80")
        self.logical_addr_edit.setMaximumWidth(150)
        hex_validator = QRegExpValidator(QRegExp("0x[0-9A-Fa-f]{1,4}"))
        self.logical_addr_edit.setValidator(hex_validator)
        tool_layout.addRow("逻辑地址:", self.logical_addr_edit)

        # 路由激活类型
        self.routing_type_edit = QLineEdit("0x00")
        self.routing_type_edit.setMaximumWidth(150)
        self.routing_type_edit.setValidator(hex_validator)
        tool_layout.addRow("路由激活类型:", self.routing_type_edit)

        # 路由激活请求
        self.routing_request_check = QCheckBox("启用")
        self.routing_request_check.setChecked(True)
        tool_layout.addRow("路由激活请求:", self.routing_request_check)

        # 网络接口
        self.network_combo = QComboBox()
        # Delay loading network interfaces to avoid blocking UI on startup
        QtCore.QTimer.singleShot(100, self._load_network_interfaces)
        tool_layout.addRow("网络接口:", self.network_combo)

        # Target Logical Addresses
        # Physical
        phy_layout = QHBoxLayout()
        self.phy_addr_edit = QLineEdit("0x004F")
        self.phy_addr_edit.setMaximumWidth(150)
        hex_validator = QRegExpValidator(QRegExp("0x[0-9A-Fa-f]{1,4}"))
        self.phy_addr_edit.setValidator(hex_validator)
        self.phy_radio = QRadioButton("使用")
        self.phy_radio.setChecked(True)
        phy_layout.addWidget(self.phy_addr_edit)
        phy_layout.addWidget(self.phy_radio)
        tool_layout.addRow("逻辑地址(物理):", phy_layout)

        # Functional
        fun_layout = QHBoxLayout()
        self.fun_addr_edit = QLineEdit("0x07DF")
        self.fun_addr_edit.setMaximumWidth(150)
        self.fun_addr_edit.setValidator(hex_validator)
        self.fun_radio = QRadioButton("使用")
        fun_layout.addWidget(self.fun_addr_edit)
        fun_layout.addWidget(self.fun_radio)
        tool_layout.addRow("逻辑地址(功能):", fun_layout)

        # Group them
        self.addr_group = QButtonGroup(self)
        self.addr_group.addButton(self.phy_radio, 1)
        self.addr_group.addButton(self.fun_radio, 2)

        tool_group.setLayout(tool_layout)
        main_layout.addWidget(tool_group)

        # DPT Configuration Group
        dpt_group = self._create_group_box("DPT 配置", "#22C55E")

        dpt_layout = QFormLayout()
        dpt_layout.setSpacing(12)

        dpt_path_layout = QHBoxLayout()
        self.dpt_path_edit = QLineEdit("")
        self.dpt_path_edit.setReadOnly(True)
        self.browse_dpt_btn = QPushButton("浏览")
        self.browse_dpt_btn.setStyleSheet(self._get_button_style("#3498db", "#5dade2", "#2980b9"))
        self.browse_dpt_btn.clicked.connect(self.browse_dpt)

        dpt_path_layout.addWidget(self.dpt_path_edit)
        dpt_path_layout.addWidget(self.browse_dpt_btn)

        dpt_layout.addRow("DPT 文件:", dpt_path_layout)
        dpt_group.setLayout(dpt_layout)
        main_layout.addWidget(dpt_group)

        # DPT Status Label
        self.dpt_status_label = QLabel("")
        self.dpt_status_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.dpt_status_label)

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

    def browse_dpt(self):
        """浏览DPT文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 DPT 文件",
            "",
            "Excel 文件 (*.xlsx)"
        )
        if file_path:
            self.dpt_path_edit.setText(file_path)

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

    def update_ui(self, settings):
        """更新界面显示"""
        self.protocol_version_combo.setCurrentIndex(settings.get("protocol_version", 0))
        self.logical_addr_edit.setText(settings.get("logical_addr", "0x0E80"))
        self.routing_type_edit.setText(settings.get("routing_type", "0x00"))
        self.routing_request_check.setChecked(settings.get("routing_request", True))

        # Try to match by IP first
        saved_ip = settings.get("network_interface_ip")
        if saved_ip:
            index = self.network_combo.findData(saved_ip)
            if index >= 0:
                self.network_combo.setCurrentIndex(index)
            else:
                self.network_combo.setCurrentIndex(settings.get("network_interface", 0))
        else:
            self.network_combo.setCurrentIndex(settings.get("network_interface", 0))

        self.phy_addr_edit.setText(settings.get("target_phy_addr", "0x004F"))
        self.fun_addr_edit.setText(settings.get("target_fun_addr", "0x07DF"))

        selected_mode = settings.get("target_addr_mode", 1) # 1=Phy, 2=Fun
        if selected_mode == 2:
            self.fun_radio.setChecked(True)
        else:
            self.phy_radio.setChecked(True)

        # DPT File
        self.dpt_path_edit.setText(settings.get("dpt_file", ""))

    def set_dpt_status(self, status, message):
        """设置DPT状态信息"""
        if status == "loading":
            self.dpt_status_label.setText(f"正在加载: {message}")
            self.dpt_status_label.setStyleSheet("color: blue;")
        elif status == "completed":
            self.dpt_status_label.setText("DPT 加载成功.")
            self.dpt_status_label.setStyleSheet("color: green;")
        elif status == "error":
            self.dpt_status_label.setText(f"错误: {message}")
            self.dpt_status_label.setStyleSheet("color: red;")
        else:
            self.dpt_status_label.setText(message)

    def save_settings(self):
        """保存设置"""
        ip_data = self.network_combo.currentData()
        # Ensure data is serializable
        if ip_data is not None and not isinstance(ip_data, (str, int, float, bool)):
            ip_data = str(ip_data)

        settings = {
            "protocol_version": self.protocol_version_combo.currentIndex(),
            "logical_addr": self.logical_addr_edit.text(),
            "routing_type": self.routing_type_edit.text(),
            "routing_request": self.routing_request_check.isChecked(),
            "network_interface": self.network_combo.currentIndex(),
            "network_interface_ip": ip_data,
            "target_phy_addr": self.phy_addr_edit.text(),
            "target_fun_addr": self.fun_addr_edit.text(),
            "target_addr_mode": self.addr_group.checkedId(),
            "dpt_file": self.dpt_path_edit.text()
        }
        self.save_signal.emit(settings)

    def reset_to_defaults(self):
        """重置为默认值"""
        self.reset_signal.emit()

    def _get_button_style(self, bg_color, hover_color, pressed_color):
        """获取按钮样式"""
        return f"""
            QPushButton {{
                background-color: {bg_color};
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 4px;
                font-weight: 600;
                font-family: "Segoe UI", "Microsoft YaHei";
            }}
            QPushButton:hover {{
                background-color: {hover_color};
            }}
            QPushButton:pressed {{
                background-color: {pressed_color};
            }}
        """
