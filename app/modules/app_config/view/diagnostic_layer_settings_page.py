from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QComboBox, QLineEdit, QPushButton,
                             QGroupBox, QFormLayout, QFileDialog,
                             QRadioButton, QButtonGroup)
from PyQt5.QtCore import Qt, QRegExp, pyqtSignal
from PyQt5.QtGui import QRegExpValidator, QFont, QIntValidator


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
        title_label = QLabel("诊断层设置")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setStyleSheet("color: #2c3e50;")
        main_layout.addWidget(title_label)

        # ECU目标设置组
        ecu_group = self._create_group_box("ECU (目标)", "#e74c3c")

        ecu_layout = QFormLayout()
        ecu_layout.setSpacing(12)

        # ECU Config File
        file_layout = QHBoxLayout()
        self.ecu_file_edit = QLineEdit()
        self.ecu_file_edit.setReadOnly(True)
        self.browse_ecu_btn = QPushButton("浏览")
        self.browse_ecu_btn.setStyleSheet(self._get_button_style("#3498db", "#5dade2", "#2980b9"))
        self.browse_ecu_btn.clicked.connect(self.browse_ecu_file)
        file_layout.addWidget(self.ecu_file_edit)
        file_layout.addWidget(self.browse_ecu_btn)
        ecu_layout.addRow("ECU 配置文件:", file_layout)

        # Target ECU
        self.target_ecu_combo = QComboBox()
        self.target_ecu_combo.currentIndexChanged.connect(self.on_target_ecu_changed)
        ecu_layout.addRow("目标 ECU:", self.target_ecu_combo)

        hex_validator = QRegExpValidator(QRegExp("0x[0-9A-Fa-f]{1,4}"))

        # 物理逻辑地址
        phy_layout = QHBoxLayout()
        self.physical_addr_edit = QLineEdit("0x004F")
        self.physical_addr_edit.setMaximumWidth(150)
        self.physical_addr_edit.setValidator(hex_validator)
        self.phy_radio = QRadioButton("使用")
        self.phy_radio.setChecked(True)
        phy_layout.addWidget(self.physical_addr_edit)
        phy_layout.addWidget(self.phy_radio)
        ecu_layout.addRow("逻辑地址(物理):", phy_layout)

        # 功能逻辑地址
        fun_layout = QHBoxLayout()
        self.functional_addr_edit = QLineEdit("0x07DF")
        self.functional_addr_edit.setMaximumWidth(150)
        self.functional_addr_edit.setValidator(hex_validator)
        self.fun_radio = QRadioButton("使用")
        fun_layout.addWidget(self.functional_addr_edit)
        fun_layout.addWidget(self.fun_radio)
        ecu_layout.addRow("逻辑地址(功能):", fun_layout)

        self.addr_group = QButtonGroup(self)
        self.addr_group.addButton(self.phy_radio, 1)
        self.addr_group.addButton(self.fun_radio, 2)


        ecu_group.setLayout(ecu_layout)
        main_layout.addWidget(ecu_group)

        # S3时间参数组
        s3_group = self._create_group_box("S3 时间参数", "#3498db")

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
        s3_layout.addRow("S3 客户端时间:", client_time_layout)

        # S3 Server Time (带单位显示)
        server_time_layout = QHBoxLayout()
        self.s3_server_edit = QLineEdit("5000")
        self.s3_server_edit.setMaximumWidth(150)
        self.s3_server_edit.setValidator(int_validator)
        server_time_layout.addWidget(self.s3_server_edit)
        server_time_layout.addWidget(QLabel("ms"))
        server_time_layout.addStretch()
        s3_layout.addRow("S3 服务器时间:", server_time_layout)

        s3_group.setLayout(s3_layout)
        main_layout.addWidget(s3_group)

        # Security Access组
        security_group = self._create_group_box("安全访问", "#e74c3c")

        security_layout = QFormLayout()
        security_layout.setSpacing(12)

        # Seed & Key DLL路径
        dll_path_layout = QHBoxLayout()

        self.dll_path_edit = QLineEdit("")
        self.dll_path_edit.setReadOnly(True)
        self.dll_path_edit.setMinimumWidth(300)
        dll_path_layout.addWidget(self.dll_path_edit)

        self.browse_button = QPushButton("浏览")
        self.browse_button.setFixedWidth(80)
        self.browse_button.setStyleSheet(self._get_button_style("#3498db", "#5dade2", "#2980b9"))
        self.browse_button.clicked.connect(self.browse_dll)
        dll_path_layout.addWidget(self.browse_button)

        security_layout.addRow("种子密钥 DLL:", dll_path_layout)

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
            "选择 种子密钥 DLL",
            "D:/",
            "DLL 文件 (*.dll);;所有文件 (*.*)"
        )
        if file_path:
            self.dll_path_edit.setText(file_path)

    def browse_ecu_file(self):
        """浏览ECU配置文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 ECU 配置",
            "",
            "JSON 文件 (*.json);;所有文件 (*.*)"
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

