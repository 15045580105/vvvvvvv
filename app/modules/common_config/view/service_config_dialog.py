from PyQt5 import QtWidgets
import json

class NoScrollComboBox(QtWidgets.QComboBox):
    def wheelEvent(self, event):
        # Ignore wheel event to prevent accidental value change while scrolling the form
        event.ignore()

class ServiceConfigDialog(QtWidgets.QDialog):
    def __init__(self, parent=None, config_type="2E"):
        super().__init__(parent)
        self.setWindowTitle(f"添加服务配置 ({config_type})")
        self.resize(1000, 700)
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
        self.content_edit.setPlaceholderText("例如: VIN码写入(0xF190)")
        self.content_edit.textChanged.connect(self.update_preview)

        self.service_id_edit = QtWidgets.QLineEdit()
        self.service_id_edit.setPlaceholderText("例如: 0xF190")
        self.service_id_edit.textChanged.connect(self.update_preview)

        self.help_edit = QtWidgets.QLineEdit()
        self.help_edit.setPlaceholderText("可选，帮助说明文字")
        self.help_edit.textChanged.connect(self.update_preview)

        self.help_image_edit = QtWidgets.QLineEdit()
        self.help_image_edit.setPlaceholderText("可选，图片路径")
        self.help_image_edit.textChanged.connect(self.update_preview)

        basic_layout.addRow("内容描述 (content):", self.content_edit)
        basic_layout.addRow("服务ID (serviceId):", self.service_id_edit)
        basic_layout.addRow("帮助说明 (help):", self.help_edit)
        basic_layout.addRow("图片路径 (helpImage):", self.help_image_edit)

        self.form_layout.addWidget(basic_group)

        # 2. 参数对象 (paramObject)
        self.param_obj_group = self.create_param_group("选择参数对象 (paramObject)")
        self.form_layout.addWidget(self.param_obj_group)

        # 3. 参数状态 (paramState)
        self.param_state_group = self.create_param_group("选择参数状态 (paramState)")
        self.form_layout.addWidget(self.param_state_group)

        # 4. Start Routine (startRoutine) - Only for 31_2F
        if self.config_type == "31_2F":
            self.start_routine_group = self.create_param_group("Start Routine (startRoutine)")
            self.form_layout.addWidget(self.start_routine_group)

        # 5. 请求配置 (requestConfig)
        req_group = QtWidgets.QGroupBox("请求配置 (requestConfig)")
        req_layout = QtWidgets.QFormLayout(req_group)

        self.req_service_edit = QtWidgets.QLineEdit()
        if self.config_type == "2E":
            self.req_service_edit.setText("0x2E")
        elif self.config_type == "31_2F":
            self.req_service_edit.setText("0x31")
        self.req_service_edit.textChanged.connect(self.update_preview)

        self.req_subfunc_edit = QtWidgets.QLineEdit()
        self.req_subfunc_edit.setPlaceholderText("例如: 0x01 (可选)")
        self.req_subfunc_edit.textChanged.connect(self.update_preview)

        self.req_did_edit = QtWidgets.QLineEdit()
        self.req_did_edit.setPlaceholderText("例如: 0xF190")
        self.req_did_edit.textChanged.connect(self.update_preview)

        self.req_source_combo = NoScrollComboBox()
        self.req_source_combo.addItems(["raw", "ascii", "calculated", "DPT/ODX"])
        self.req_source_combo.currentTextChanged.connect(self.update_preview)

        self.req_conversion_combo = NoScrollComboBox()
        self.req_conversion_combo.addItems(["none", "ip_le", "u32_le", "u16_le"])
        self.req_conversion_combo.currentTextChanged.connect(self.update_preview)

        req_layout.addRow("Service:", self.req_service_edit)
        req_layout.addRow("SubFunction:", self.req_subfunc_edit)
        req_layout.addRow("DataIdentifier:", self.req_did_edit)
        req_layout.addRow("Value Source:", self.req_source_combo)
        req_layout.addRow("Conversion:", self.req_conversion_combo)

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

    def create_param_group(self, title):
        group = QtWidgets.QGroupBox(title)
        layout = QtWidgets.QFormLayout(group)
        widgets = {}

        # Type Dropdown
        type_combo = NoScrollComboBox()
        type_combo.addItems(["fixed", "input", "dropdown", "checkabledropdown", "dynamic"])
        layout.addRow("类型 (Type):", type_combo)
        widgets["type"] = type_combo

        # Default Value
        default_edit = QtWidgets.QLineEdit()
        default_edit.setPlaceholderText("默认值")
        default_edit.setText("---")  # Set default value to '---'
        layout.addRow("默认值 (default):", default_edit)
        widgets["default"] = default_edit

        # Options (for dropdown)
        options_edit = QtWidgets.QPlainTextEdit()
        options_edit.setPlaceholderText("选项列表，每行一个\n例如:\n选项A\n选项B")
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

            value_edit.setVisible(is_fixed)
            value_label.setVisible(is_fixed)

            # Only update preview if UI setup is complete (or roughly complete)
            # Simplest check: check if attributes exist if they are needed in get_current_data
            if hasattr(self, 'param_obj_group') and hasattr(self, 'param_state_group'):
                # For 31_2F, start_routine_group might be needed if setup is done
                if self.config_type != "31_2F" or hasattr(self, 'start_routine_group'):
                    self.update_preview()

        type_combo.currentTextChanged.connect(update_visibility)
        default_edit.textChanged.connect(self.update_preview)
        options_edit.textChanged.connect(self.update_preview)
        placeholder_edit.textChanged.connect(self.update_preview)
        value_edit.textChanged.connect(self.update_preview)

        # Init visibility
        # Temporarily disconnect or just don't call update_preview inside update_visibility if not ready
        # But update_visibility logic above handles it with the hasattr check.
        # However, update_preview also gets called by textChanged signals which are connected above.
        # But those signals won't fire during init.

        # Manually set visibility without triggering preview update loop during init
        update_visibility("fixed")

        # Store widgets in group property to access later
        group.widgets = widgets
        return group

    def get_param_data(self, group_box):
        if not group_box:
            return {}
        widgets = getattr(group_box, "widgets", {})
        data = {}

        ptype = widgets["type"].currentText()
        data["type"] = ptype

        default_val = widgets["default"].text()
        if default_val:
            data["default"] = default_val

        if "dropdown" in ptype:
            raw_opts = widgets["options"].toPlainText()
            opts = [line.strip() for line in raw_opts.split('\n') if line.strip()]
            data["options"] = opts
        elif ptype == "input":
            ph = widgets["placeholder"].text()
            if ph:
                data["placeholder"] = ph
        elif ptype == "fixed":
            val = widgets["value"].text()
            if val:
                data["value"] = val

        return data

    def get_current_data(self):
        # Safety check for early calls
        if not hasattr(self, 'param_obj_group') or not hasattr(self, 'param_state_group'):
            return {}

        data = {
            # Index will be determined by controller
            "content": self.content_edit.text() or "新建服务",
            "serviceId": self.service_id_edit.text(),
            "paramObject": self.get_param_data(self.param_obj_group),
            "paramState": self.get_param_data(self.param_state_group),
            "requestConfig": {
                "service": self.req_service_edit.text(),
                "dataIdentifier": self.req_did_edit.text()
            }
        }

        # Optional fields
        if self.help_edit.text():
            data["help"] = self.help_edit.text()
        if self.help_image_edit.text():
            data["helpImage"] = self.help_image_edit.text()

        sub_func = self.req_subfunc_edit.text()
        if sub_func:
            data["requestConfig"]["subFunction"] = sub_func

        source = self.req_source_combo.currentText()
        if source != "raw":
             data["requestConfig"]["paramValueSource"] = source

        conversion = self.req_conversion_combo.currentText()
        if conversion != "none":
             data["requestConfig"]["conversion"] = conversion

        return data

    def update_preview(self):
        data = self.get_current_data()
        self.preview_edit.setText(json.dumps(data, indent=2, ensure_ascii=False))

    def on_insert(self):
        # Validation
        if not self.service_id_edit.text():
             QtWidgets.QMessageBox.warning(self, "校验失败", "服务ID不能为空")
             return
        if not self.req_did_edit.text():
             QtWidgets.QMessageBox.warning(self, "校验失败", "DataIdentifier不能为空")
             return

        self.result_json = self.get_current_data()
        self.accept()
