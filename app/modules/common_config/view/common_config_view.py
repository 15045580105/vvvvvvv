from PyQt5 import QtWidgets, QtCore, QtGui
from app.presentation.views.base_view import BaseView
from app.common.ui.widgets import ModernButton, CheckableComboBox
from app.common.ui.modern_widgets import MessageToast

class CommonConfigView(BaseView):
    def setup_ui(self):
        # Main layout
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        self.tab_widget = QtWidgets.QTabWidget()
        main_layout.addWidget(self.tab_widget)

        # Initialize tabs
        self._init_param_config_tab()
        self._init_routine_control_tab()

        # 监听 Tab 切换以调整列宽
        self.tab_widget.currentChanged.connect(lambda: self._adjust_column_widths())

    def _init_param_config_tab(self):
        self.param_tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(self.param_tab)
        layout.setSpacing(14)
        layout.setContentsMargins(14, 14, 14, 14)

        # 1. 标题与时间
        title_layout = QtWidgets.QHBoxLayout()
        title_label = QtWidgets.QLabel("常用$2E服务")
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; font-family: 'Microsoft YaHei'; color: #1E293B;")
        title_layout.addWidget(title_label)

        title_layout.addSpacing(20)

        self.last_read_time_label = QtWidgets.QLabel("最后读取时间: -")
        self.last_read_time_label.setStyleSheet("color: #64748B; margin-left: 15px; font-size: 14px;")
        title_layout.addWidget(self.last_read_time_label)

        title_layout.addStretch()
        layout.addLayout(title_layout)

        # 2. 导入配置
        import_layout = QtWidgets.QHBoxLayout()
        self.import_json_btn = ModernButton("导入JSON配置文件", "#22C55E", "📂")
        self.import_json_btn.setFixedWidth(160)
        import_layout.addWidget(self.import_json_btn)

        self.json_path_edit = QtWidgets.QLineEdit()
        self.json_path_edit.setPlaceholderText("配置文件路径...")
        self.json_path_edit.setReadOnly(True)

        import_layout.addWidget(self.json_path_edit)
        layout.addLayout(import_layout)

        # 3. 表格区域
        self.param_table = QtWidgets.QTableWidget(0, 5)
        self.param_table.setHorizontalHeaderLabels(["序号", "内容", "选择参数对象", "选择参数状态", "执行操作"])

        # --- 优化表格样式 (参考 bus_data_download_view) ---
        self.param_table.verticalHeader().setVisible(False)
        self.param_table.setAlternatingRowColors(True)
        pal = self.param_table.palette()
        pal.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor("#F9FAFB"))
        self.param_table.setPalette(pal)
        self.param_table.setWordWrap(False)

        # 行高设置 (仿照 bus_data_download_view)
        vheader = self.param_table.verticalHeader()
        vheader.setDefaultSectionSize(55)
        vheader.setMinimumSectionSize(40)
        vheader.setSectionResizeMode(QtWidgets.QHeaderView.Fixed)

        # 列宽设置 (比例 1:7:6:6:3)
        hheader = self.param_table.horizontalHeader()
        hheader.setSectionResizeMode(QtWidgets.QHeaderView.Interactive)
        hheader.setStretchLastSection(True) # 确保最后一列占满剩余空间

        # 初始列宽将在 resizeEvent 中动态调整

        layout.addWidget(self.param_table, stretch=2)

        # 4. 分页控件 (仿照 bus_data_download_view)
        pager_card = QtWidgets.QGroupBox()
        pager_card.setTitle("")

        pc = QtWidgets.QHBoxLayout(pager_card)
        pc.setContentsMargins(12, 8, 12, 8)
        pc.setSpacing(10)

        self.prev_page_btn = ModernButton("上一页", "#6366F1", "◀")
        self.next_page_btn = ModernButton("下一页", "#6366F1", "▶")
        self.page_info_label = QtWidgets.QLabel("第 1/1 页，共 0 条")
        self.page_info_label.setObjectName("muted")

        # 添加每页条数下拉框
        self.page_size_combo = QtWidgets.QComboBox()
        self.page_size_combo.addItems(["10", "20", "50", "100"])
        self.page_size_combo.setCurrentText("10")

        pc.addWidget(self.prev_page_btn)
        pc.addWidget(self.next_page_btn)
        pc.addSpacing(8)
        pc.addWidget(QtWidgets.QLabel("每页条数"))
        pc.addWidget(self.page_size_combo)
        pc.addStretch(1)
        pc.addWidget(self.page_info_label)

        layout.addWidget(pager_card)

        # 5. 日志区域
        log_group = QtWidgets.QGroupBox("操作日志")
        log_layout = QtWidgets.QVBoxLayout()
        log_layout.setContentsMargins(10, 20, 10, 10)
        self.param_log_text = QtWidgets.QTextEdit()
        self.param_log_text.setReadOnly(True)
        self.param_log_text.setPlaceholderText("这里显示常用$2E服务的操作日志...")
        log_layout.addWidget(self.param_log_text)
        log_group.setLayout(log_layout)
        layout.addWidget(log_group, stretch=1)

        self.tab_widget.addTab(self.param_tab, "常用$2E服务")

    def _init_routine_control_tab(self):
        self.routine_tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(self.routine_tab)
        layout.setSpacing(14)
        layout.setContentsMargins(14, 14, 14, 14)

        # 1. 标题与时间
        title_layout = QtWidgets.QHBoxLayout()
        title_label = QtWidgets.QLabel("常用$31&$2F服务")
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; font-family: 'Microsoft YaHei'; color: #1E293B;")
        title_layout.addWidget(title_label)

        title_layout.addSpacing(20)

        self.routine_last_read_label = QtWidgets.QLabel("最后读取时间: -")
        self.routine_last_read_label.setStyleSheet("color: #64748B; margin-left: 15px; font-size: 14px;")
        title_layout.addWidget(self.routine_last_read_label)

        title_layout.addStretch()
        layout.addLayout(title_layout)

        # 2. 导入配置
        import_layout = QtWidgets.QHBoxLayout()
        self.routine_import_btn = ModernButton("导入JSON配置文件", "#22C55E", "📂")
        self.routine_import_btn.setFixedWidth(160)
        import_layout.addWidget(self.routine_import_btn)

        self.routine_json_path_edit = QtWidgets.QLineEdit()
        self.routine_json_path_edit.setPlaceholderText("配置文件路径...")
        self.routine_json_path_edit.setReadOnly(True)

        import_layout.addWidget(self.routine_json_path_edit)
        layout.addLayout(import_layout)

        # 3. 表格区域
        self.routine_table = QtWidgets.QTableWidget(0, 5)
        self.routine_table.setHorizontalHeaderLabels(["序号", "内容", "选择参数对象", "选择参数状态", "执行操作"])

        # --- 优化表格样式 (参考 bus_data_download_view) ---
        self.routine_table.verticalHeader().setVisible(False)
        self.routine_table.setAlternatingRowColors(True)
        pal = self.routine_table.palette()
        pal.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor("#F9FAFB"))
        self.routine_table.setPalette(pal)
        self.routine_table.setWordWrap(False)

        # 行高设置 (仿照 bus_data_download_view)
        vheader = self.routine_table.verticalHeader()
        vheader.setDefaultSectionSize(55)
        vheader.setMinimumSectionSize(40)
        vheader.setSectionResizeMode(QtWidgets.QHeaderView.Fixed)

        # 列宽设置 (比例 1:7:6:6:3)
        hheader = self.routine_table.horizontalHeader()
        hheader.setSectionResizeMode(QtWidgets.QHeaderView.Interactive)
        hheader.setStretchLastSection(True) # 确保最后一列占满剩余空间

        layout.addWidget(self.routine_table, stretch=2)

        # 4. 分页控件 (仿照 bus_data_download_view)
        pager_card = QtWidgets.QGroupBox()
        pager_card.setTitle("")

        pc = QtWidgets.QHBoxLayout(pager_card)
        pc.setContentsMargins(12, 8, 12, 8)
        pc.setSpacing(10)

        self.routine_prev_page_btn = ModernButton("上一页", "#6366F1", "◀")
        self.routine_next_page_btn = ModernButton("下一页", "#6366F1", "▶")
        self.routine_page_info_label = QtWidgets.QLabel("第 1/1 页，共 0 条")
        self.routine_page_info_label.setObjectName("muted")

        # 添加每页条数下拉框
        self.routine_page_size_combo = QtWidgets.QComboBox()
        self.routine_page_size_combo.addItems(["10", "20", "50", "100"])
        self.routine_page_size_combo.setCurrentText("10")

        pc.addWidget(self.routine_prev_page_btn)
        pc.addWidget(self.routine_next_page_btn)
        pc.addSpacing(8)
        pc.addWidget(QtWidgets.QLabel("每页条数"))
        pc.addWidget(self.routine_page_size_combo)
        pc.addStretch(1)
        pc.addWidget(self.routine_page_info_label)

        layout.addWidget(pager_card)

        # 5. 日志区域
        log_group = QtWidgets.QGroupBox("操作日志")
        log_layout = QtWidgets.QVBoxLayout()
        log_layout.setContentsMargins(10, 20, 10, 10)
        self.routine_log_text = QtWidgets.QTextEdit()
        self.routine_log_text.setReadOnly(True)
        self.routine_log_text.setPlaceholderText("这里显示常用$31&$2F服务的操作日志...")
        log_layout.addWidget(self.routine_log_text)
        log_group.setLayout(log_layout)
        layout.addWidget(log_group, stretch=1)

        self.tab_widget.addTab(self.routine_tab, "常用$31&$2F服务")

    def append_param_log(self, message: str):
        """向常用$2E服务日志窗口添加日志"""
        self._append_log(self.param_log_text, message)

    def append_routine_log(self, message: str):
        """向常用例程控制日志窗口添加日志"""
        self._append_log(self.routine_log_text, message)

    def _append_log(self, text_edit, message: str):
        timestamp = QtCore.QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss")
        log_msg = f"[{timestamp}] {message}"
        text_edit.append(log_msg)
        cursor = text_edit.textCursor()
        cursor.movePosition(QtGui.QTextCursor.End)
        text_edit.setTextCursor(cursor)

    def show_message(self, message, type="info"):
        # 根据当前显示的标签页记录日志
        current_index = self.tab_widget.currentIndex()
        log_msg = f"[{type.upper()}] {message}"
        if current_index == 0:
            self.append_param_log(log_msg)
        else:
            self.append_routine_log(log_msg)

        msg_type = 2  # info
        if type == "success":
            msg_type = 0
        elif type == "error":
            msg_type = 1
        elif type == "warning":
            msg_type = 1
        # 确保 MessageToast 接收的是 QWidget 类型的 parent
        MessageToast(self).show_toast(message, msg_type)

    def update_param_table(self, params, read_callback, write_callback):
        """更新参数表格"""
        self.param_table.setRowCount(len(params))
        for i, param in enumerate(params):
            # 序号
            self.param_table.setItem(i, 0, QtWidgets.QTableWidgetItem(str(i + 1)))
            # 参数名称
            self.param_table.setItem(i, 1, QtWidgets.QTableWidgetItem(param["name"]))
            # DID
            self.param_table.setItem(i, 2, QtWidgets.QTableWidgetItem(param["did"]))
            # 当前值
            self.param_table.setItem(i, 3, QtWidgets.QTableWidgetItem(param["value"]))

            # 操作按钮
            btn_widget = QtWidgets.QWidget()
            btn_layout = QtWidgets.QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(4, 2, 4, 2)
            btn_layout.setSpacing(8)

            read_btn = ModernButton("读取", "#3B82F6", "📥", dense=True)
            read_btn.clicked.connect(lambda _, did=param["did"], r=i: read_callback(did, r))

            write_btn = ModernButton("写入", "#10B981", "📤", dense=True)
            write_btn.clicked.connect(lambda _, did=param["did"], r=i: write_callback(did, r))

            btn_layout.addWidget(read_btn)
            btn_layout.addWidget(write_btn)
            btn_layout.addStretch()

            self.param_table.setCellWidget(i, 4, btn_widget)

    def update_param_value(self, row, value):
        """更新参数值"""
        if 0 <= row < self.param_table.rowCount():
            self.param_table.setItem(row, 3, QtWidgets.QTableWidgetItem(value))

    def update_routine_table(self, services, execute_callback):
        """更新常用例程表格"""
        self.routine_table.setRowCount(0)

        for row_idx, service in enumerate(services):
            self.routine_table.insertRow(row_idx)
            self.routine_table.setRowHeight(row_idx, 50)

            # 1. 序号
            index_item = QtWidgets.QTableWidgetItem(str(service.get("index", "")))
            index_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter if hasattr(QtCore.Qt, "AlignmentFlag") else getattr(QtCore.Qt, "AlignCenter", 0x0084))
            self.routine_table.setItem(row_idx, 0, index_item)

            # 2. 内容
            # --- 新增：处理 "help" 字段展示 ---
            content_widget = QtWidgets.QWidget()
            content_layout = QtWidgets.QHBoxLayout(content_widget)
            content_layout.setContentsMargins(5, 5, 5, 5)
            content_layout.setSpacing(10)

            # 使用 align_left | align_vcenter 确保内容居中偏左
            align_left = getattr(QtCore.Qt, "AlignLeft", 0x0001)
            align_vcenter = getattr(QtCore.Qt, "AlignVCenter", 0x0080)
            if hasattr(QtCore.Qt, "AlignLeft"):
                align_left = QtCore.Qt.AlignLeft
            if hasattr(QtCore.Qt, "AlignVCenter"):
                align_vcenter = QtCore.Qt.AlignVCenter
            content_layout.setAlignment(align_left | align_vcenter)

            content_label = QtWidgets.QLabel(service.get("content", ""))
            content_layout.addWidget(content_label)

            help_text = service.get("help", "")
            help_image_path = service.get("helpImage", "app/resources/images/img.png") # Default to img.png if not specified

            if help_text:
                help_label = QtWidgets.QLabel(help_text)
                # 蓝色字体，类似超链接样式
                help_label.setStyleSheet("color: blue; text-decoration: underline; cursor: pointer;")

                # Check for PointingHandCursor existence (PyQt5/PySide differences)
                cursor_shape = getattr(QtCore.Qt, "PointingHandCursor", 13)
                help_label.setCursor(QtGui.QCursor(cursor_shape))

                # 点击事件处理
                help_label.mousePressEvent = lambda event: self._show_help_image(help_image_path)
                content_layout.addWidget(help_label)

            content_layout.addStretch()

            self.routine_table.setCellWidget(row_idx, 1, content_widget)

            # 3. 参数对象
            param_obj = service.get("paramObject", {})
            obj_widget = self._create_param_widget(param_obj, service, "paramObject_val")
            if obj_widget:
                self.routine_table.setCellWidget(row_idx, 2, obj_widget)
            else:
                self.routine_table.setItem(row_idx, 2, QtWidgets.QTableWidgetItem("/"))

            # 4. 参数状态
            param_state = service.get("paramState", {})
            state_widget = self._create_param_widget(param_state, service, "paramState_val")
            if state_widget:
                self.routine_table.setCellWidget(row_idx, 3, state_widget)
            else:
                self.routine_table.setItem(row_idx, 3, QtWidgets.QTableWidgetItem("/"))

            # 5. 执行操作
            btn_widget = QtWidgets.QWidget()
            btn_layout = QtWidgets.QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(4, 2, 4, 2)
            # btn_layout.setAlignment(QtCore.Qt.AlignCenter)
            btn_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter if hasattr(QtCore.Qt, "AlignmentFlag") else getattr(QtCore.Qt, "AlignCenter", 0x0084))

            # 统一使用灰色作为初始颜色
            btn_color = "#9CA3AF"

            exec_btn = ModernButton("执行", btn_color, "▶", dense=True)
            exec_btn.setMinimumWidth(100)

            # 使用闭包捕获当前行的数据
            exec_btn.clicked.connect(lambda checked, s=service, r=row_idx: execute_callback(s, r))

            btn_layout.addWidget(exec_btn)
            self.routine_table.setCellWidget(row_idx, 4, btn_widget)

            # 保存按钮引用以便后续更新状态
            service["_exec_btn"] = exec_btn

    def update_routine_status(self, row_index, status, success=True):
        """更新例程执行状态"""
        # 获取按钮
        widget = self.routine_table.cellWidget(row_index, 4)
        if widget:
            btn = widget.findChild(QtWidgets.QPushButton)
            if btn:
                color = "#22C55E" if success else "#EF4444" # 统一颜色: 成功绿 失败红
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {color};
                        color: white;
                        border: none;
                        border-radius: 4px;
                        font-weight: bold;
                    }}
                """)
                # ModernButton的setText应该也可以
                btn.setText(status)

                # 3秒后恢复
                QtCore.QTimer.singleShot(3000, lambda: self._reset_routine_btn(btn))

    def _reset_routine_btn(self, btn):
        if not btn: return
        btn.setText("执行")
        # 恢复灰色
        btn.setStyleSheet("""
            QPushButton {
                background-color: #9CA3AF; 
                color: white;
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #6B7280;
            }
        """)

    def set_routine_page_info(self, current, total, total_items):
        self.routine_page_info_label.setText(f"第 {current} / {total} 页 (共 {total_items} 条)")

    def set_routine_last_read_time(self, time_str):
        self.routine_last_read_label.setText(f"最后读取时间: {time_str}")



    def update_2e_table(self, services, execute_callback, custom_execute_callback):
        """
        更新 $2E 服务表格
        services: list of dict, 每个元素包含 content, paramObject, paramState 等配置
        """
        self.param_table.setRowCount(len(services))

        for i, service in enumerate(services):
            # 序号
            self.param_table.setItem(i, 0, QtWidgets.QTableWidgetItem(str(service.get("index", i + 1))))

            # 内容
            self.param_table.setItem(i, 1, QtWidgets.QTableWidgetItem(service.get("content", "")))

            # 参数对象 (Column 2)
            self._create_cell_control(i, 2, service.get("paramObject", {}), service, "paramObject_val")

            # 参数状态 (Column 3)
            self._create_cell_control(i, 3, service.get("paramState", {}), service, "paramState_val")

            # 执行操作 (Column 4)
            btn_widget = QtWidgets.QWidget()
            btn_layout = QtWidgets.QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(4, 2, 4, 2)

            # 统一使用灰色作为初始颜色
            btn_color = "#9CA3AF"

            exec_btn = ModernButton("执行", btn_color, "▶", dense=True)
            exec_btn.setMinimumWidth(100) # 加长宽度

            # 连接信号
            try:
                exec_btn.clicked.connect(lambda _, s=service, r=i: execute_callback(s, r))
            except Exception as e:
                pass


            btn_layout.addWidget(exec_btn)
            btn_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter if hasattr(QtCore.Qt, "AlignmentFlag") else getattr(QtCore.Qt, "AlignCenter", 0x0084))
            self.param_table.setCellWidget(i, 4, btn_widget)

    def _create_cell_control(self, row, col, config, service_data, data_key):
        """根据配置创建单元格控件"""
        c_type = config.get("type", "fixed")

        if c_type == "checkabledropdown":
            combo = CheckableComboBox()

            # 定制 updateText: 无选中项时显示 "---", 有项时正常显示
            def custom_updateText():
                texts = []
                model = combo.model
                for i in range(1, model.rowCount()): # Skip Select All
                    item = model.item(i)
                    is_checked = False
                    if hasattr(QtCore.Qt, "CheckState"):
                         is_checked = (item.checkState() == QtCore.Qt.CheckState.Checked)
                    else:
                         is_checked = (item.checkState() == getattr(QtCore.Qt, "Checked", 2))

                    if is_checked:
                        texts.append(item.text())

                if len(texts) == model.rowCount() - 1 and len(texts) > 0:
                     text_str = "已全选"
                elif len(texts) == 0:
                     text_str = "---"
                else:
                     text_str = ", ".join(texts)

                combo.lineEdit().setText(text_str)

            combo.updateText = custom_updateText

            options = config.get("options", [])
            # CheckableComboBox也保留"---"
            combo.addItems(options)

            default = config.get("default", "")

            # 初始化选中项
            model = combo.model
            defaults = [d.strip() for d in default.split(",")] if default else []
            for i in range(1, model.rowCount()): # Skip global checkbox
                item = model.item(i)
                if item.text() in defaults:
                     if hasattr(QtCore.Qt, "CheckState"):
                        item.setCheckState(QtCore.Qt.CheckState.Checked)
                     else:
                        item.setCheckState(getattr(QtCore.Qt, "Checked", 2))
            combo.updateText()

            # 绑定数据更新
            # CheckableComboBox 使用文本变化来更新数据，因为它将选中的项以逗号分隔显示
            combo.lineEdit().textChanged.connect(lambda text, s=service_data, k=data_key: s.update({k: text}))
            # 初始化数据
            service_data[data_key] = combo.lineEdit().text()

            self.param_table.setCellWidget(row, col, combo)

        elif c_type == "dropdown":
            combo = QtWidgets.QComboBox()
            # 过滤掉 "---" 选项
            options = config.get("options", [])
            # options = [opt for opt in raw_options if opt != "---"]
            combo.addItems(options)

            default = config.get("default", "")

            if default:
                combo.setCurrentText(default)
            else:
                combo.setCurrentIndex(-1)
                # 尝试设置占位符 (Qt 5.15+ 支持)
                if hasattr(combo, "setPlaceholderText"):
                    combo.setPlaceholderText("---")

            # 绑定数据更新
            # 如果 index 为 -1，text 可能为空
            def update_dropdown_data(text, s=service_data, k=data_key):
                val = text if text else "---"
                s.update({k: val})

            combo.currentTextChanged.connect(lambda text, s=service_data, k=data_key: update_dropdown_data(text, s, k))
            # 初始化数据
            curr_text = combo.currentText()
            service_data[data_key] = curr_text if curr_text else "---"

            self.param_table.setCellWidget(row, col, combo)

        elif c_type == "input":
            line_edit = QtWidgets.QLineEdit()
            line_edit.setPlaceholderText(config.get("placeholder", ""))



            # 绑定数据更新
            line_edit.textChanged.connect(lambda text, s=service_data, k=data_key: s.update({k: text}))
            # 初始化数据
            service_data[data_key] = line_edit.text()

            self.param_table.setCellWidget(row, col, line_edit)

        else: # fixed
            value = config.get("value", "")
            item = QtWidgets.QTableWidgetItem(value)
            # item.setTextAlignment(QtCore.Qt.AlignCenter)
            item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter if hasattr(QtCore.Qt, "AlignmentFlag") else getattr(QtCore.Qt, "AlignCenter", 0x0084))
            # 初始化数据
            service_data[data_key] = value
            self.param_table.setItem(row, col, item)

    def _create_param_widget(self, config, service_data, data_key):
        """创建参数控件"""
        c_type = config.get("type", "fixed")
        if c_type == "checkabledropdown":
            combo = CheckableComboBox()

            # 定制 updateText: 无选中项时显示 "---", 有项时正常显示
            def custom_updateText():
                texts = []
                model = combo.model
                for i in range(1, model.rowCount()): # Skip Select All
                    item = model.item(i)
                    is_checked = False
                    if hasattr(QtCore.Qt, "CheckState"):
                         is_checked = (item.checkState() == QtCore.Qt.CheckState.Checked)
                    else:
                         is_checked = (item.checkState() == getattr(QtCore.Qt, "Checked", 2))

                    if is_checked:
                        texts.append(item.text())

                if len(texts) == model.rowCount() - 1 and len(texts) > 0:
                     text_str = "已全选"
                elif len(texts) == 0:
                     text_str = "---"
                else:
                     text_str = ", ".join(texts)

                combo.lineEdit().setText(text_str)

            combo.updateText = custom_updateText

            options = config.get("options", [])
            # CheckableComboBox也保留"---"
            combo.addItems(options)

            default = config.get("default", "")

            # 初始化选中项
            model = combo.model
            defaults = [d.strip() for d in default.split(",")] if default else []
            for i in range(1, model.rowCount()):
                 item = model.item(i)
                 if item.text() in defaults:
                     if hasattr(QtCore.Qt, "CheckState"):
                        item.setCheckState(QtCore.Qt.CheckState.Checked)
                     else:
                         item.setCheckState(getattr(QtCore.Qt, "Checked", 2))
            combo.updateText()

            # 绑定数据更新
            combo.lineEdit().textChanged.connect(lambda text, s=service_data, k=data_key: s.update({k: text}))
            # 初始化数据
            service_data[data_key] = combo.lineEdit().text()
            return combo

        elif c_type == "dropdown":
            combo = QtWidgets.QComboBox()
            # 过滤掉 "---" 选项
            options = config.get("options", [])
            # options = [opt for opt in raw_options if opt != "---"]
            combo.addItems(options)

            default = config.get("default", "")

            if default:
                combo.setCurrentText(default)
            else:
                combo.setCurrentIndex(-1)
                if hasattr(combo, "setPlaceholderText"):
                    combo.setPlaceholderText("---")

            # 绑定数据更新
            def update_dropdown_data(text, s=service_data, k=data_key):
                val = text if text else "---"
                s.update({k: val})

            combo.currentTextChanged.connect(lambda text, s=service_data, k=data_key: update_dropdown_data(text, s, k))
            # 初始化数据
            curr_text = combo.currentText()
            service_data[data_key] = curr_text if curr_text else "---"
            return combo

        elif c_type == "input":
            line_edit = QtWidgets.QLineEdit()
            line_edit.setPlaceholderText(config.get("placeholder", ""))

            # 绑定数据更新
            line_edit.textChanged.connect(lambda text, s=service_data, k=data_key: s.update({k: text}))
            # 初始化数据
            service_data[data_key] = line_edit.text()
            return line_edit

        elif c_type == "dynamic":
            # 动态类型，通常用于关联其他操作，这里暂时显示为文本
            label = QtWidgets.QLabel("动态参数")
            # label.setAlignment(QtCore.Qt.AlignCenter)
            label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter if hasattr(QtCore.Qt, "AlignmentFlag") else getattr(QtCore.Qt, "AlignCenter", 0x0084))
            service_data[data_key] = ""
            return label

        return None

    def update_2e_status(self, row, status, is_success=True):
        """更新指定行的状态"""
        widget = self.param_table.cellWidget(row, 4)

    def set_last_read_time(self, time_str):
        self.last_read_time_label.setText(f"最后读取时间: {time_str}")

    def set_page_info(self, current, total_pages, total_items):
        self.page_info_label.setText(f"第 {current}/{total_pages} 页，共 {total_items} 条")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._adjust_column_widths()

    def showEvent(self, event):
        super().showEvent(event)
        self._adjust_column_widths()

    def _adjust_column_widths(self):
        """根据比例 1:7:6:6:3 动态调整列宽"""
        # 调整 param_table
        if hasattr(self, 'param_table'):
            width = self.param_table.viewport().width()
            if width > 0:
                ratios = [1, 7, 6, 6, 3]
                total = sum(ratios)
                used_width = 0
                for i in range(4):
                    w = int(width * ratios[i] / total)
                    self.param_table.setColumnWidth(i, w)
                    used_width += w
                self.param_table.setColumnWidth(4, width - used_width)

        # 调整 routine_table
        if hasattr(self, 'routine_table'):
            width = self.routine_table.viewport().width()
            if width > 0:
                ratios = [1, 7, 6, 6, 3]
                total = sum(ratios)
                used_width = 0
                for i in range(4):
                    w = int(width * ratios[i] / total)
                    self.routine_table.setColumnWidth(i, w)
                    used_width += w
                self.routine_table.setColumnWidth(4, width - used_width)

    def _show_help_image(self, img_path="img.png"):
        """显示帮助图片"""
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("帮助信息")

        # Enable close button safely
        close_hint = getattr(QtCore.Qt, "WindowCloseButtonHint", 0x08000000)
        dialog.setWindowFlags(dialog.windowFlags() | close_hint)

        layout = QtWidgets.QVBoxLayout(dialog)

        label = QtWidgets.QLabel(dialog)
        align_center = getattr(QtCore.Qt, "AlignCenter", 0x0084)
        label.setAlignment(align_center)

        # Load image
        import os
        # Basic relative path check
        if not os.path.exists(img_path):
             # Try appending to current working directory if it's relative
             cwd_path = os.path.join(os.getcwd(), img_path)
             if os.path.exists(cwd_path):
                 img_path = cwd_path

        pixmap = QtGui.QPixmap(img_path)
        if not pixmap.isNull():
            label.setPixmap(pixmap)
            # 限制图片最大尺寸，防止占用屏幕过大
            screen = QtWidgets.QApplication.primaryScreen()
            if screen:
                screen_size = screen.size()
                max_w, max_h = int(screen_size.width() * 0.8), int(screen_size.height() * 0.8)

                img_w = pixmap.width()
                img_h = pixmap.height()

                if img_w > max_w or img_h > max_h:
                     pixmap = pixmap.scaled(max_w, max_h, QtCore.Qt.AspectRatioMode.KeepAspectRatio, QtCore.Qt.TransformationMode.SmoothTransformation)
                     label.setPixmap(pixmap)

            dialog.resize(label.pixmap().size())
        else:
            label.setText(f"未找到图片:\n{img_path}")
            dialog.resize(400, 200)

        layout.addWidget(label)
        dialog.exec_()
