from PyQt5 import QtWidgets
import json
import os
import re
from app.common.ui.modern_widgets import MessageToast

class NoScrollComboBox(QtWidgets.QComboBox):
    def wheelEvent(self, event):
        # Ignore wheel event to prevent accidental value change while scrolling the form
        event.ignore()

class ServiceConfigDialog(QtWidgets.QDialog):
    def __init__(self, parent=None, config_type="2E"):
        super().__init__(parent)
        self.setWindowTitle(f"添加服务配置 ({config_type})")
        self.resize(1100, 760)
        self.config_type = config_type
        self.result_json = None

        self.setup_ui()
        self.update_preview()

    def setup_ui(self):
        main_layout = QtWidgets.QHBoxLayout(self)

        # 左侧滚动区域：表单
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        form_widget = QtWidgets.QWidget()
        self.form_layout = QtWidgets.QVBoxLayout(form_widget)

        # 1. 基本信息
        basic_group = QtWidgets.QGroupBox("基本信息")
        basic_layout = QtWidgets.QFormLayout(basic_group)

        self.content_edit = QtWidgets.QLineEdit()
        self.content_edit.setPlaceholderText("例如: VIN码写入(0xF190) / $31_使用模式切换(0x34D1)")
        self.content_edit.textChanged.connect(self.update_preview)

        self.service_id_edit = QtWidgets.QLineEdit()
        self.service_id_edit.setPlaceholderText("例如: 0xF190 / 0xBEE7")
        self.service_id_edit.textChanged.connect(self.update_preview)

        self.help_edit = QtWidgets.QLineEdit()
        self.help_edit.setPlaceholderText("可选，帮助说明文字")
        self.help_edit.textChanged.connect(self.update_preview)

        self.help_image_edit = QtWidgets.QLineEdit()
        self.help_image_edit.setPlaceholderText("可选，图片绝对路径")
        self.help_image_edit.textChanged.connect(self.update_preview)

        basic_layout.addRow("内容描述 (content):", self.content_edit)
        basic_layout.addRow("DID (did):", self.service_id_edit)
        basic_layout.addRow("帮助说明 (help):", self.help_edit)
        basic_layout.addRow("图片路径 (helpImage):", self.help_image_edit)

        self.form_layout.addWidget(basic_group)

        # 2. 参数对象 (paramObject)
        self.param_obj_group = self.create_param_group("选择参数对象 (paramObject)")
        self.form_layout.addWidget(self.param_obj_group)

        # 3. 参数状态 (paramState)
        self.param_state_group = self.create_param_group("选择参数状态 (paramState)")
        self.form_layout.addWidget(self.param_state_group)

        # 4. 例程控制类型 (routineControlType) - Only for 31_2F
        self.routine_control_group = None
        if self.config_type == "31_2F":
            self.routine_control_group = self.create_param_group("例程控制类型 (routineControlType)", default_type="dropdown")
            self.form_layout.addWidget(self.routine_control_group)

        # 5. 请求元数据（扁平字段）
        req_group = QtWidgets.QGroupBox("请求元数据（Root Fields）")
        req_layout = QtWidgets.QFormLayout(req_group)

        self.req_service_edit = QtWidgets.QLineEdit("0x2E" if self.config_type == "2E" else "0x31")
        self.req_service_edit.textChanged.connect(self.update_preview)

        self.req_subfunc_edit = QtWidgets.QLineEdit("00" if self.config_type == "2E" else "0x01")
        self.req_subfunc_edit.setPlaceholderText("例如: 0x01")
        self.req_subfunc_edit.textChanged.connect(self.update_preview)

        self.req_param_len_spin = QtWidgets.QSpinBox()
        self.req_param_len_spin.setRange(0, 4096)
        self.req_param_len_spin.setValue(1)
        self.req_param_len_spin.valueChanged.connect(self.update_preview)

        self.req_source_combo = NoScrollComboBox()
        self.req_source_combo.addItems(["calculated", "ascii", "fixed", "manual"])
        self.req_source_combo.currentTextChanged.connect(self.update_preview)

        req_layout.addRow("Service:", self.req_service_edit)
        req_layout.addRow("SubFunction:", self.req_subfunc_edit)
        req_layout.addRow("paramByteLength:", self.req_param_len_spin)
        req_layout.addRow("source:", self.req_source_combo)

        self.form_layout.addWidget(req_group)
        self.form_layout.addStretch()

        scroll.setWidget(form_widget)
        main_layout.addWidget(scroll, stretch=3)

        # 右侧：预览与操作
        right_panel = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right_panel)

        right_layout.addWidget(QtWidgets.QLabel("实时预览 (JSON):"))
        self.preview_edit = QtWidgets.QTextEdit()
        self.preview_edit.setReadOnly(True)
        self.preview_edit.setStyleSheet("font-family: Consolas, monospace;")
        right_layout.addWidget(self.preview_edit)

        btn_layout = QtWidgets.QHBoxLayout()
        self.insert_btn = QtWidgets.QPushButton("插入配置")
        self.insert_btn.setStyleSheet("background-color: #22C55E; color: white; padding: 10px; font-weight: bold;")
        self.insert_btn.clicked.connect(self.on_insert)

        cancel_btn = QtWidgets.QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)

        btn_layout.addWidget(self.insert_btn)
        btn_layout.addWidget(cancel_btn)
        right_layout.addLayout(btn_layout)

        main_layout.addWidget(right_panel, stretch=2)

    def create_param_group(self, title, default_type="fixed"):
        group = QtWidgets.QGroupBox(title)
        layout = QtWidgets.QFormLayout(group)
        widgets = {}

        # Type Dropdown
        type_combo = NoScrollComboBox()
        type_combo.addItems(["fixed", "input", "dropdown", "checkabledropdown"])
        type_combo.setCurrentText(default_type)
        layout.addRow("类型 (Type):", type_combo)
        widgets["type"] = type_combo

        # Default Value
        default_edit = QtWidgets.QLineEdit("---")
        layout.addRow("默认值 (default):", default_edit)
        widgets["default"] = default_edit

        # Options (for dropdown)
        options_edit = QtWidgets.QPlainTextEdit()
        options_edit.setPlaceholderText("选项列表，每行一个")
        options_edit.setFixedHeight(80)
        options_label = QtWidgets.QLabel("选项 (options):")
        layout.addRow(options_label, options_edit)
        widgets["options"] = options_edit
        widgets["options_label"] = options_label

        # Placeholder (for input)
        placeholder_edit = QtWidgets.QLineEdit()
        placeholder_edit.setPlaceholderText("输入框提示文字")
        placeholder_label = QtWidgets.QLabel("提示 (placeholder):")
        layout.addRow(placeholder_label, placeholder_edit)
        widgets["placeholder"] = placeholder_edit
        widgets["placeholder_label"] = placeholder_label

        # Validation (for input)
        validation_combo = NoScrollComboBox()
        validation_combo.addItems(["", "ip", "port", "string"])
        validation_label = QtWidgets.QLabel("校验 (validation):")
        layout.addRow(validation_label, validation_combo)
        widgets["validation"] = validation_combo
        widgets["validation_label"] = validation_label

        # Value (for fixed)
        value_edit = QtWidgets.QLineEdit()
        value_edit.setPlaceholderText("固定显示的值")
        value_label = QtWidgets.QLabel("固定值 (value):")
        layout.addRow(value_label, value_edit)
        widgets["value"] = value_edit
        widgets["value_label"] = value_edit

        # Dynamic Visibility logic
        def update_visibility(text):
            is_dropdown = "dropdown" in text
            is_input = text == "input"
            is_fixed = text == "fixed"

            options_edit.setVisible(is_dropdown)
            options_label.setVisible(is_dropdown)

            placeholder_edit.setVisible(is_input)
            placeholder_label.setVisible(is_input)

            validation_combo.setVisible(is_input)
            validation_label.setVisible(is_input)

            value_edit.setVisible(is_fixed)
            value_label.setVisible(is_fixed)

            if is_fixed:
                if not value_edit.text():
                    value_edit.setText("N/A")
            elif value_edit.text() == "N/A":
                value_edit.clear()

            self.update_preview()

        type_combo.currentTextChanged.connect(update_visibility)
        default_edit.textChanged.connect(self.update_preview)
        options_edit.textChanged.connect(self.update_preview)
        placeholder_edit.textChanged.connect(self.update_preview)
        validation_combo.currentTextChanged.connect(self.update_preview)
        value_edit.textChanged.connect(self.update_preview)

        # Init visibility
        update_visibility(default_type)

        # Store widgets in group property to access later
        group.widgets = widgets
        return group

    def get_param_data(self, group_box):
        if not group_box:
            return {}
        widgets = getattr(group_box, "widgets", {})
        ptype = widgets["type"].currentText()
        data = {"type": ptype}

        if ptype in {"dropdown", "checkabledropdown"}:
            opts = [line.strip() for line in widgets["options"].toPlainText().splitlines() if line.strip()]
            data["options"] = opts
            if widgets["default"].text().strip():
                data["default"] = widgets["default"].text().strip()
        elif ptype == "input":
            if widgets["placeholder"].text().strip():
                data["placeholder"] = widgets["placeholder"].text().strip()
            if widgets["validation"].currentText().strip():
                data["validation"] = widgets["validation"].currentText().strip()
        else:
            data["value"] = widgets["value"].text().strip() or "N/A"

        return data

    def get_current_data(self):
        data = {
            "content": self.content_edit.text().strip() or "新建服务",
            "did": self.service_id_edit.text().strip(),
            "service": self.req_service_edit.text().strip(),
            "subFunction": self.req_subfunc_edit.text().strip(),
            "paramByteLength": int(self.req_param_len_spin.value()),
            "help": self.help_edit.text().strip(),
            "helpImage": self.help_image_edit.text().strip(),
            "paramObject": self.get_param_data(self.param_obj_group),
            "paramState": self.get_param_data(self.param_state_group),
        }
        selected_source = self.req_source_combo.currentText().strip().lower()
        if selected_source == "manual":
            data["source"] = "manual"
            data["rawRequest"] = True
        if self.config_type == "31_2F" and self.routine_control_group is not None:
            data["routineControlType"] = self.get_param_data(self.routine_control_group)
        return data

    def update_preview(self):
        if not hasattr(self, 'preview_edit'):
            return
        try:
            data = self.get_current_data()
        except Exception as e:
            data = {"previewError": str(e)}
        self.preview_edit.setText(json.dumps(data, indent=2, ensure_ascii=False))

    def on_insert(self):
        # Validation
        service_id = self.service_id_edit.text().strip()
        if not service_id:
             self.show_toast("校验失败: DID不能为空", "error")
             return

        # 1. Hex validation for DID
        if not re.match(r'^0x[0-9A-Fa-f]+$', service_id):
             self.show_toast("校验失败: DID必须是十六进制 (如 0xF190)", "error")
             return

        try:
             val = int(service_id, 16)
             if val < 0 or val > 0xFFFF:
                 self.show_toast("校验失败: DID超出有效范围 (0x0000 - 0xFFFF)", "error")
                 return
        except ValueError:
             self.show_toast("校验失败: DID无效", "error")
             return

        # 2. Help Image validation
        help_img = self.help_image_edit.text().strip()
        if help_img:
            if not os.path.isabs(help_img):
                 self.show_toast("校验失败: 图片路径必须是完整路径", "error")
                 return
            if not os.path.exists(help_img) or not os.path.isfile(help_img):
                 self.show_toast("校验失败: 图片文件不存在", "error")
                 return

        self.result_json = self.get_current_data()
        self.accept()

    def show_toast(self, message, type_):
        level = 3 if type_ == "error" else 1
        try:
            MessageToast(self).show_toast(message, level)
        except Exception:
            QtWidgets.QMessageBox.warning(self, "提示", message)
