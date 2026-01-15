from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                             QTreeWidget, QTreeWidgetItem, QStackedWidget,
                             QLabel, QComboBox, QLineEdit, QCheckBox, QPushButton,
                             QGroupBox, QFormLayout, QGridLayout, QSplitter,
                             QMessageBox, QFileDialog,
                             QRadioButton, QButtonGroup)
from PyQt5.QtCore import Qt, QRegExp, pyqtSignal
from PyQt5.QtGui import QRegExpValidator, QFont, QIntValidator
from app.common.ui.style import APP_STYLE
from PyQt5 import QtWidgets, QtCore
from app.common.ui.widgets import ModernButton


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
        title_label = QLabel("DoIP Protocol Settings")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setStyleSheet("color: #2c3e50;")
        main_layout.addWidget(title_label)

        # 协议栈设置组
        protocol_group = self._create_group_box("Protocol Stack", "#3498db")

        protocol_layout = QFormLayout()
        protocol_layout.setSpacing(12)
        protocol_layout.setLabelAlignment(Qt.AlignLeft)

        # 协议版本
        self.protocol_version_combo = QComboBox()
        self.protocol_version_combo.addItem("DoIP V2(ISO 13400-2:2012)")
        self.protocol_version_combo.addItem("DoIP V3(ISO 13400-2:2019)")
        protocol_layout.addRow("Protocol version:", self.protocol_version_combo)

        protocol_group.setLayout(protocol_layout)
        main_layout.addWidget(protocol_group)

        # 工具设置组
        tool_group = self._create_group_box("Tool Settings", "#3498db")

        tool_layout = QFormLayout()
        tool_layout.setSpacing(12)

        # 逻辑地址
        self.logical_addr_edit = QLineEdit("0x0E80")
        self.logical_addr_edit.setMaximumWidth(150)
        hex_validator = QRegExpValidator(QRegExp("0x[0-9A-Fa-f]{1,4}"))
        self.logical_addr_edit.setValidator(hex_validator)
        tool_layout.addRow("Logical address:", self.logical_addr_edit)

        # 路由激活类型
        self.routing_type_edit = QLineEdit("0x00")
        self.routing_type_edit.setMaximumWidth(150)
        self.routing_type_edit.setValidator(hex_validator)
        tool_layout.addRow("Routing activation type:", self.routing_type_edit)

        # 路由激活请求
        self.routing_request_check = QCheckBox("Enable")
        self.routing_request_check.setChecked(True)
        tool_layout.addRow("Routing activation request:", self.routing_request_check)

        # 网络接口
        self.network_combo = QComboBox()
        # Delay loading network interfaces to avoid blocking UI on startup
        QtCore.QTimer.singleShot(100, self._load_network_interfaces)
        tool_layout.addRow("Network interface:", self.network_combo)

        # Target Logical Addresses
        # Physical
        phy_layout = QHBoxLayout()
        self.phy_addr_edit = QLineEdit("0x004F")
        self.phy_addr_edit.setMaximumWidth(150)
        hex_validator = QRegExpValidator(QRegExp("0x[0-9A-Fa-f]{1,4}"))
        self.phy_addr_edit.setValidator(hex_validator)
        self.phy_radio = QRadioButton("Use")
        self.phy_radio.setChecked(True)
        phy_layout.addWidget(self.phy_addr_edit)
        phy_layout.addWidget(self.phy_radio)
        tool_layout.addRow("Logical address(physical):", phy_layout)

        # Functional
        fun_layout = QHBoxLayout()
        self.fun_addr_edit = QLineEdit("0x07DF")
        self.fun_addr_edit.setMaximumWidth(150)
        self.fun_addr_edit.setValidator(hex_validator)
        self.fun_radio = QRadioButton("Use")
        fun_layout.addWidget(self.fun_addr_edit)
        fun_layout.addWidget(self.fun_radio)
        tool_layout.addRow("Logical address(functional):", fun_layout)

        # Group them
        self.addr_group = QButtonGroup(self)
        self.addr_group.addButton(self.phy_radio, 1)
        self.addr_group.addButton(self.fun_radio, 2)

        tool_group.setLayout(tool_layout)
        main_layout.addWidget(tool_group)

        # DPT Configuration Group
        dpt_group = self._create_group_box("DPT Configuration", "#22C55E")

        dpt_layout = QFormLayout()
        dpt_layout.setSpacing(12)

        dpt_path_layout = QHBoxLayout()
        self.dpt_path_edit = QLineEdit("")
        self.dpt_path_edit.setReadOnly(True)
        self.browse_dpt_btn = QPushButton("Browse")
        self.browse_dpt_btn.setStyleSheet(self._get_button_style("#3498db", "#5dade2", "#2980b9"))
        self.browse_dpt_btn.clicked.connect(self.browse_dpt)

        dpt_path_layout.addWidget(self.dpt_path_edit)
        dpt_path_layout.addWidget(self.browse_dpt_btn)

        dpt_layout.addRow("DPT File:", dpt_path_layout)
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
            "Select DPT File",
            "",
            "Encrypted DPT Files (*.dat);;JSON Files (*.json)"
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
            self.dpt_status_label.setText(f"Loading: {message}")
            self.dpt_status_label.setStyleSheet("color: blue;")
        elif status == "completed":
            self.dpt_status_label.setText("DPT loaded successfully.")
            self.dpt_status_label.setStyleSheet("color: green;")
        elif status == "error":
            self.dpt_status_label.setText(f"Error: {message}")
            self.dpt_status_label.setStyleSheet("color: red;")
        else:
            self.dpt_status_label.setText(message)

    def save_settings(self):
        """保存设置"""
        settings = {
            "protocol_version": self.protocol_version_combo.currentIndex(),
            "logical_addr": self.logical_addr_edit.text(),
            "routing_type": self.routing_type_edit.text(),
            "routing_request": self.routing_request_check.isChecked(),
            "network_interface": self.network_combo.currentIndex(),
            "network_interface_ip": self.network_combo.currentData(),
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



class DiagnosticLayerSettingsPage(QWidget):
    """Diagnostic Layer设置页面"""
    save_signal = pyqtSignal(dict)
    reset_signal = pyqtSignal()
    ecu_file_changed_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        """初始化界面"""
        main_layout = QVBoxLayout()
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # 标题
        title_label = QLabel("Diagnostic Layer Settings")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setStyleSheet("color: #2c3e50;")
        main_layout.addWidget(title_label)

        # ECU目标设置组
        ecu_group = self._create_group_box("ECU (Target)", "#e74c3c")

        ecu_layout = QFormLayout()
        ecu_layout.setSpacing(12)

        # ECU Config File
        file_layout = QHBoxLayout()
        self.ecu_file_edit = QLineEdit()
        self.ecu_file_edit.setReadOnly(True)
        self.browse_ecu_btn = QPushButton("Browse")
        self.browse_ecu_btn.setStyleSheet(self._get_button_style("#3498db", "#5dade2", "#2980b9"))
        self.browse_ecu_btn.clicked.connect(self.browse_ecu_file)
        file_layout.addWidget(self.ecu_file_edit)
        file_layout.addWidget(self.browse_ecu_btn)
        ecu_layout.addRow("ECU Config File:", file_layout)

        # Target ECU
        self.target_ecu_combo = QComboBox()
        self.target_ecu_combo.currentIndexChanged.connect(self.on_target_ecu_changed)
        ecu_layout.addRow("Target ECU:", self.target_ecu_combo)

        hex_validator = QRegExpValidator(QRegExp("0x[0-9A-Fa-f]{1,4}"))

        # 物理逻辑地址
        phy_layout = QHBoxLayout()
        self.physical_addr_edit = QLineEdit("0x004F")
        self.physical_addr_edit.setMaximumWidth(150)
        self.physical_addr_edit.setValidator(hex_validator)
        self.phy_radio = QRadioButton("Use")
        self.phy_radio.setChecked(True)
        phy_layout.addWidget(self.physical_addr_edit)
        phy_layout.addWidget(self.phy_radio)
        ecu_layout.addRow("Logical address(physical):", phy_layout)

        # 功能逻辑地址
        fun_layout = QHBoxLayout()
        self.functional_addr_edit = QLineEdit("0x07DF")
        self.functional_addr_edit.setMaximumWidth(150)
        self.functional_addr_edit.setValidator(hex_validator)
        self.fun_radio = QRadioButton("Use")
        fun_layout.addWidget(self.functional_addr_edit)
        fun_layout.addWidget(self.fun_radio)
        ecu_layout.addRow("Logical address(functional):", fun_layout)

        self.addr_group = QButtonGroup(self)
        self.addr_group.addButton(self.phy_radio, 1)
        self.addr_group.addButton(self.fun_radio, 2)


        ecu_group.setLayout(ecu_layout)
        main_layout.addWidget(ecu_group)

        # S3时间参数组
        s3_group = self._create_group_box("S3 Timing Parameters", "#3498db")

        s3_layout = QFormLayout()
        s3_layout.setSpacing(12)
        s3_layout.setLabelAlignment(Qt.AlignLeft)

        # S3 Client Time (带单位显示)
        client_time_layout = QHBoxLayout()
        self.s3_client_edit = QLineEdit("3000")
        self.s3_client_edit.setMaximumWidth(150)
        int_validator = QIntValidator(0, 60000)
        self.s3_client_edit.setValidator(int_validator)
        client_time_layout.addWidget(self.s3_client_edit)
        client_time_layout.addWidget(QLabel("ms"))
        client_time_layout.addStretch()
        s3_layout.addRow("S3 Client Time:", client_time_layout)

        # S3 Server Time (带单位显示)
        server_time_layout = QHBoxLayout()
        self.s3_server_edit = QLineEdit("5000")
        self.s3_server_edit.setMaximumWidth(150)
        self.s3_server_edit.setValidator(int_validator)
        server_time_layout.addWidget(self.s3_server_edit)
        server_time_layout.addWidget(QLabel("ms"))
        server_time_layout.addStretch()
        s3_layout.addRow("S3 Server Time:", server_time_layout)

        s3_group.setLayout(s3_layout)
        main_layout.addWidget(s3_group)

        # Security Access组
        security_group = self._create_group_box("Security Access", "#e74c3c")

        security_layout = QFormLayout()
        security_layout.setSpacing(12)

        # Seed & Key DLL路径
        dll_path_layout = QHBoxLayout()

        self.dll_path_edit = QLineEdit("")
        self.dll_path_edit.setReadOnly(True)
        self.dll_path_edit.setMinimumWidth(300)
        dll_path_layout.addWidget(self.dll_path_edit)

        self.browse_button = QPushButton("Browse")
        self.browse_button.setFixedWidth(80)
        self.browse_button.setStyleSheet(self._get_button_style("#3498db", "#5dade2", "#2980b9"))
        self.browse_button.clicked.connect(self.browse_dll)
        dll_path_layout.addWidget(self.browse_button)

        security_layout.addRow("Seed & Key DLL:", dll_path_layout)

        security_group.setLayout(security_layout)
        main_layout.addWidget(security_group)

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

    def browse_dll(self):
        """浏览DLL文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Seed & Key DLL",
            "D:/",
            "DLL Files (*.dll);;All Files (*.*)"
        )
        if file_path:
            self.dll_path_edit.setText(file_path)

    def browse_ecu_file(self):
        """浏览ECU配置文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select ECU Config",
            "",
            "JSON Files (*.json);;All Files (*.*)"
        )
        if file_path:
            self.ecu_file_edit.setText(file_path)
            self.ecu_file_changed_signal.emit(file_path)

    def on_target_ecu_changed(self, index):
        """ECU选择变更"""
        data = self.target_ecu_combo.currentData()
        if isinstance(data, dict):
            # Assuming data contains 'physical_addr' and 'functional_addr'
            # If not, fallback to what we have
            if 'physical_addr' in data:
                self.physical_addr_edit.setText(data['physical_addr'])
            elif 'address' in data: # Fallback for simple format
                self.physical_addr_edit.setText(data['address'])

            if 'functional_addr' in data:
                self.functional_addr_edit.setText(data['functional_addr'])
        elif isinstance(data, str):
             self.physical_addr_edit.setText(data)

    def update_ecu_combo(self, ecu_data):
        """更新ECU下拉框"""
        self.target_ecu_combo.blockSignals(True)
        self.target_ecu_combo.clear()

        if isinstance(ecu_data, dict):
            for name, info in ecu_data.items():
                self.target_ecu_combo.addItem(name, info)
        elif isinstance(ecu_data, list):
             for item in ecu_data:
                 if isinstance(item, dict) and "name" in item:
                     self.target_ecu_combo.addItem(item["name"], item)

        self.target_ecu_combo.blockSignals(False)

    def update_ui(self, settings):
        """更新界面显示"""
        self.s3_client_edit.setText(settings.get("s3_client_time", "3000"))
        self.s3_server_edit.setText(settings.get("s3_server_time", "5000"))
        self.dll_path_edit.setText(settings.get("dll_path", ""))
        self.physical_addr_edit.setText(settings.get("physical_addr", "0x004F"))
        self.functional_addr_edit.setText(settings.get("functional_addr", "0x07DF"))
        self.ecu_file_edit.setText(settings.get("ecu_config_path", ""))

        # Restore selected ECU if possible
        target_ecu = settings.get("target_ecu_name")
        if target_ecu:
            index = self.target_ecu_combo.findText(target_ecu)
            if index >= 0:
                self.target_ecu_combo.setCurrentIndex(index)

        selected_mode = settings.get("diag_addr_mode", 1) # 1=Phy, 2=Fun
        if selected_mode == 2:
            self.fun_radio.setChecked(True)
        else:
            self.phy_radio.setChecked(True)

    def save_settings(self):
        """保存设置"""
        settings = {
            "s3_client_time": self.s3_client_edit.text(),
            "s3_server_time": self.s3_server_edit.text(),
            "dll_path": self.dll_path_edit.text(),
            "physical_addr": self.physical_addr_edit.text(),
            "functional_addr": self.functional_addr_edit.text(),
            "ecu_config_path": self.ecu_file_edit.text(),
            "target_ecu_name": self.target_ecu_combo.currentText(),
            "diag_addr_mode": self.addr_group.checkedId()
        }
        self.save_signal.emit(settings)

    def reset_to_defaults(self):
        """重置为默认值"""
        self.reset_signal.emit()


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
        title_label = QLabel("Domain Software Update Settings")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setStyleSheet("color: #2c3e50;")
        main_layout.addWidget(title_label)

        # Stress Test组
        stress_group = self._create_group_box("Stress Test", "#9b59b6")

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
        stress_layout.addRow("Start delay after success:", success_delay_layout)

        # 失败后启动延迟
        failure_delay_layout = QHBoxLayout()
        self.failure_delay_edit = QLineEdit("20")
        self.failure_delay_edit.setMaximumWidth(150)
        self.failure_delay_edit.setValidator(int_validator)
        failure_delay_layout.addWidget(self.failure_delay_edit)
        failure_delay_layout.addWidget(QLabel("s"))
        failure_delay_layout.addStretch()
        stress_layout.addRow("Start delay after failure:", failure_delay_layout)

        # Send EcuReset after failure
        self.ecu_reset_check = QCheckBox("Enable")
        self.ecu_reset_check.setChecked(False)
        stress_layout.addRow("Send EcuReset after failure:", self.ecu_reset_check)

        # Stop stress test on failure
        self.stop_on_failure_check = QCheckBox("Enable")
        self.stop_on_failure_check.setChecked(False)
        stress_layout.addRow("Stop stress test on failure:", self.stop_on_failure_check)

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


class AppLogSettingsPage(QWidget):
    """APP Log Settings Page"""
    save_signal = pyqtSignal(dict)
    reset_signal = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        """Initialize UI"""
        main_layout = QVBoxLayout()
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # Title
        title_label = QLabel("APP Log Settings")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setStyleSheet("color: #2c3e50;")
        main_layout.addWidget(title_label)

        # Export APP settings group
        export_group = self._create_group_box("Export APP Logs", "#10B981")
        export_layout = QGridLayout()
        export_layout.setHorizontalSpacing(12)
        export_layout.setVerticalSpacing(12)

        row = 0
        # Row 0: export path selector
        export_layout.addWidget(QLabel("Export Path:"), row, 0)
        self.export_path_edit = QLineEdit()
        self.export_path_edit.setPlaceholderText("Select export folder")
        self.export_path_edit.setReadOnly(True)
        export_layout.addWidget(self.export_path_edit, row, 1)
        self.export_path_btn = ModernButton("Browse", "#3B82F6", "📁")
        self.export_path_btn.clicked.connect(self.browse_export_path)
        export_layout.addWidget(self.export_path_btn, row, 2)

        row += 1
        # Row 1: module/page dropdown selector
        export_layout.addWidget(QLabel("Export Module:"), row, 0)
        self.export_module_combo = QComboBox()
        self.export_module_combo.setMinimumWidth(200)
        self.export_module_combo.setEditable(False)
        # Add some dummy items or populate later
        self.export_module_combo.addItems(["All Modules", "Module A", "Module B"])
        export_layout.addWidget(self.export_module_combo, row, 1, 1, 2)

        row += 1
        # Row 2: start/end datetime
        export_layout.addWidget(QLabel("Start Time:"), row, 0)

        datetime_row_layout = QHBoxLayout()
        self.export_start_datetime = QtWidgets.QDateTimeEdit(QtCore.QDateTime.currentDateTime())
        self.export_start_datetime.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.export_start_datetime.setCalendarPopup(True)
        datetime_row_layout.addWidget(self.export_start_datetime)

        datetime_row_layout.addWidget(QLabel("End Time:"))
        self.export_end_datetime = QtWidgets.QDateTimeEdit(QtCore.QDateTime.currentDateTime())
        self.export_end_datetime.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.export_end_datetime.setCalendarPopup(True)
        datetime_row_layout.addWidget(self.export_end_datetime)

        datetime_row_layout.addStretch()
        export_layout.addLayout(datetime_row_layout, row, 1, 1, 2)

        row += 1
        # Row 3: Export Button
        self.export_start_btn = ModernButton("Export Logs", "#3B82F6", "⬇")
        # Connect signal in controller or here if it's a direct action
        # For settings page, usually we save config, but this looks like an action.
        # Assuming we just configure defaults here, or maybe trigger export?
        # The user said "move Export APP Logs here", so likely the action too.
        # But this is a settings dialog. Let's keep the button but maybe it should just save the config?
        # Or if it's an action, it might not belong in a "Settings" dialog which usually has OK/Cancel.
        export_layout.addWidget(self.export_start_btn, row, 1, 1, 2, Qt.AlignRight)

        export_group.setLayout(export_layout)
        main_layout.addWidget(export_group)

        main_layout.addStretch()
        self.setLayout(main_layout)

    def _create_group_box(self, title, border_color):
        """Create styled GroupBox"""
        group = QGroupBox(title)
        # Use theme colors
        if border_color == "#10B981": # Green
            border_color = "#10B981"
            title_color = "#065F46"
            bg_color = "#ECFDF5"
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

    def browse_export_path(self):
        path = QFileDialog.getExistingDirectory(self, "Select Export Directory")
        if path:
            self.export_path_edit.setText(path)

    def update_ui(self, settings):
        """Update UI from settings"""
        self.export_path_edit.setText(settings.get("export_path", ""))
        self.export_module_combo.setCurrentText(settings.get("export_module", "All Modules"))
        # Date times might not be stored in settings usually, but if they are:
        # self.export_start_datetime.setDateTime(...)
        pass

    def save_settings(self):
        """Save settings"""
        settings = {
            "export_path": self.export_path_edit.text(),
            "export_module": self.export_module_combo.currentText(),
            # "start_time": ...
        }
        self.save_signal.emit(settings)

    def reset_to_defaults(self):
        """Reset to defaults"""
        self.reset_signal.emit()


class SettingsWindow(QWidget):
    """主设置窗口"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Settings")
        self.resize(1000, 750)
        self.current_page = None
        self.init_ui()

    def init_ui(self):
        """初始化界面"""
        # 应用全局样式
        self.setStyleSheet(APP_STYLE)

        # 主布局
        main_layout = QVBoxLayout()
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # 分割器（树和页面）
        splitter = QSplitter(Qt.Horizontal)

        # 左侧树形导航
        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderLabel("Settings Categories")
        self.tree_widget.setMaximumWidth(280)
        self.tree_widget.setMinimumWidth(220)
        # 样式已由 APP_STYLE 覆盖，这里只需微调
        self.tree_widget.setStyleSheet("""
            QTreeWidget {
                border-right: 1px solid #E5E7EB;
            }
        """)

        # 创建树形结构
        self.create_tree_structure()

        # 右侧堆叠窗口
        self.stacked_widget = QStackedWidget()
        self.stacked_widget.setStyleSheet("background-color: #FFFFFF;")

        # 创建并添加设置页面
        self.create_pages()

        # 将树和堆叠窗口添加到分割器
        splitter.addWidget(self.tree_widget)
        splitter.addWidget(self.stacked_widget)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #E5E7EB;
            }
        """)

        # 按钮布局
        button_layout = QHBoxLayout()
        button_layout.setSpacing(12)
        button_layout.setContentsMargins(20, 15, 20, 15)

        button_layout.addStretch()

        self.ok_button = QPushButton("OK")
        self.ok_button.setFixedWidth(90)
        self.ok_button.setCursor(Qt.PointingHandCursor)
        # 使用主题蓝色
        self.ok_button.setStyleSheet(self._get_button_style("#3B82F6", "#2563EB", "#1D4ED8"))
        self.ok_button.clicked.connect(self.on_ok_clicked)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setFixedWidth(90)
        self.cancel_button.setCursor(Qt.PointingHandCursor)
        # 使用主题灰色
        self.cancel_button.setStyleSheet(self._get_button_style("#9CA3AF", "#6B7280", "#4B5563"))
        self.cancel_button.clicked.connect(self.on_cancel_clicked)

        button_layout.addWidget(self.ok_button)
        button_layout.addWidget(self.cancel_button)

        # 底部按钮容器背景
        button_container = QWidget()
        button_container.setStyleSheet("background-color: #F9FAFB; border-top: 1px solid #E5E7EB;")
        button_container.setLayout(button_layout)

        # 组装主布局
        main_layout.addWidget(splitter)
        main_layout.addWidget(button_container)

        self.setLayout(main_layout)

        # 连接树形结构点击事件
        self.tree_widget.itemClicked.connect(self.on_tree_item_clicked)

        # 默认选中第一个页面
        self.tree_widget.setCurrentItem(self.tree_widget.topLevelItem(0).child(0))
        self.stacked_widget.setCurrentIndex(0)
        self.current_page = self.doip_page

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

    def create_tree_structure(self):
        """创建树形结构"""
        # Protocol Stack节点
        protocol_item = QTreeWidgetItem(self.tree_widget)
        protocol_item.setText(0, "Protocol Stack")

        # Protocol Stack子节点
        doip_item = QTreeWidgetItem(protocol_item)
        doip_item.setText(0, "DoIP Settings")
        doip_item.setData(0, Qt.UserRole, "doip")

        diag_layer_item = QTreeWidgetItem(protocol_item)
        diag_layer_item.setText(0, "Diagnostic Layer")
        diag_layer_item.setData(0, Qt.UserRole, "diag_layer")

        # Tool Settings节点
        tool_settings_item = QTreeWidgetItem(self.tree_widget)
        tool_settings_item.setText(0, "Tool Settings")

        # Tool Settings子节点
        domain_update_item = QTreeWidgetItem(tool_settings_item)
        domain_update_item.setText(0, "Domain Software Update")
        domain_update_item.setData(0, Qt.UserRole, "domain_update")

        # APP Log Settings节点
        app_log_item = QTreeWidgetItem(self.tree_widget)
        app_log_item.setText(0, "APP Log Settings")
        app_log_item.setData(0, Qt.UserRole, "app_log")

        # 展开所有节点
        self.tree_widget.expandAll()

    def create_pages(self):
        """创建各个设置页面"""
        # DoIP设置页面
        self.doip_page = DoIPSettingsPage()
        self.stacked_widget.addWidget(self.doip_page)

        # Diagnostic Layer设置页面
        self.diag_layer_page = DiagnosticLayerSettingsPage()
        self.stacked_widget.addWidget(self.diag_layer_page)

        # Domain Software Update设置页面
        self.domain_update_page = DomainSoftwareUpdatePage()
        self.stacked_widget.addWidget(self.domain_update_page)

        # APP Log Settings页面
        self.app_log_page = AppLogSettingsPage()
        self.stacked_widget.addWidget(self.app_log_page)

    def on_tree_item_clicked(self, item, column):
        """树形结构点击事件"""
        page_id = item.data(0, Qt.UserRole)

        # 根据page_id切换到对应页面
        page_mapping = {
            "doip": self.doip_page,
            "diag_layer": self.diag_layer_page,
            "domain_update": self.domain_update_page,
            "app_log": self.app_log_page
        }

        if page_id in page_mapping:
            self.current_page = page_mapping[page_id]
            self.stacked_widget.setCurrentWidget(self.current_page)

    def on_ok_clicked(self):
        """OK按钮点击事件 - 保存所有页面设置并关闭窗口"""
        # 保存所有页面的设置
        if hasattr(self, 'doip_page'):
            self.doip_page.save_settings()
        if hasattr(self, 'diag_layer_page'):
            self.diag_layer_page.save_settings()
        if hasattr(self, 'domain_update_page'):
            self.domain_update_page.save_settings()
        if hasattr(self, 'app_log_page'):
            self.app_log_page.save_settings()

        self.close()

    def on_cancel_clicked(self):
        """Cancel按钮点击事件 - 不保存直接关闭窗口"""
        self.close()
