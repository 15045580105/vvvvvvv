from PyQt5 import QtWidgets, QtCore, QtGui

from app.common.log.operation_log_manager import OperationLogManager
from app.presentation.views.base_view import BaseView
from app.common.ui.widgets import ModernButton, CheckableComboBox
from app.common.ui.modern_widgets import MessageToast
from app.common.ui.log_splitter import LogAreaSplitter
from app.common.ui.log_panel import LogPanelBuilder

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

    def _create_file_import_layout(self, line_edit, button, label_text, add_form_btn=None):
        """
        创建一个标准的文件导入布局：[Label] [LineEdit] [BrowseButton] [Optional: AddFormButton]
        """
        layout = QtWidgets.QHBoxLayout()
        layout.setSpacing(10)

        label = QtWidgets.QLabel(label_text)
        label.setFixedWidth(120)  # 统一标签宽度
        layout.addWidget(label)

        layout.addWidget(line_edit)

        button.setFixedWidth(160)
        layout.addWidget(button)

        if add_form_btn:
            add_form_btn.setFixedWidth(140)
            layout.addWidget(add_form_btn)

        return layout

    def _init_param_config_tab(self):
        self.param_tab = QtWidgets.QWidget()
        root_layout = QtWidgets.QVBoxLayout(self.param_tab)
        root_layout.setSpacing(0)
        root_layout.setContentsMargins(0, 0, 0, 0)
        self.param_splitter = LogAreaSplitter(self.param_tab, min_log_height=150, max_log_ratio=0.6)
        root_layout.addWidget(self.param_splitter)
        content_widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(content_widget)
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

        # 2. 文件导入区域
        self.config_path_input = QtWidgets.QLineEdit()
        self.config_path_input.setFixedHeight(36)
        self.config_path_input.setPlaceholderText("选择或输入服务JSON配置文件路径")
        self.config_path_input.setReadOnly(True)
        self.import_json_btn = ModernButton("导入JSON配置文件", "#22C55E", "📂")

        self.add_json_form_btn = ModernButton("增加json表单", "#8B5CF6", "➕")


        import_layout = self._create_file_import_layout(
            self.config_path_input,
            self.import_json_btn,
            "服务配置JSON路径：",
            add_form_btn=self.add_json_form_btn
        )
        layout.addLayout(import_layout)

        # DPT文件导入区域
        self.dpt_path_input_2e = QtWidgets.QLineEdit()
        self.dpt_path_input_2e.setFixedHeight(36)
        self.dpt_path_input_2e.setPlaceholderText("选择或输入DPT定义JSON文件路径")
        self.dpt_path_input_2e.setReadOnly(True)
        self.dpt_import_btn_2e = ModernButton("导入DPT JSON文件", "#0EA5E9", "📂")

        dpt_import_layout = self._create_file_import_layout(
            self.dpt_path_input_2e,
            self.dpt_import_btn_2e,
            "DPT JSON路径："
        )
        layout.addLayout(dpt_import_layout)

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
        LogPanelBuilder.attach_search(log_layout, self.param_log_text)
        log_layout.addWidget(self.param_log_text)
        log_group.setLayout(log_layout)
        self.param_splitter.set_panels(content_widget, log_group, initial_log_height=220)

        self.tab_widget.addTab(self.param_tab, "常用$2E服务")

    def _init_routine_control_tab(self):
        self.routine_tab = QtWidgets.QWidget()
        root_layout = QtWidgets.QVBoxLayout(self.routine_tab)
        root_layout.setSpacing(0)
        root_layout.setContentsMargins(0, 0, 0, 0)
        self.routine_splitter = LogAreaSplitter(self.routine_tab, min_log_height=150, max_log_ratio=0.6)
        root_layout.addWidget(self.routine_splitter)
        content_widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(content_widget)
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

        # 2. 文件导入区域
        self.routine_config_path_input = QtWidgets.QLineEdit()
        self.routine_config_path_input.setFixedHeight(36)
        self.routine_config_path_input.setPlaceholderText("选择或输入服务JSON配置文件路径")
        self.routine_config_path_input.setReadOnly(True)
        self.routine_config_import_btn = ModernButton("导入JSON配置文件", "#22C55E", "📂")

        self.add_json_form_btn_routine = ModernButton("增加json表单", "#8B5CF6", "➕")

        import_layout = self._create_file_import_layout(
            self.routine_config_path_input,
            self.routine_config_import_btn,
            "ConfigJSON路径：",
            add_form_btn=self.add_json_form_btn_routine
        )
        layout.addLayout(import_layout)

        # DPT文件导入区域 - Routine
        self.dpt_path_input_routine = QtWidgets.QLineEdit()
        self.dpt_path_input_routine.setFixedHeight(36)
        self.dpt_path_input_routine.setPlaceholderText("选择或输入DPT定义JSON文件路径")
        self.dpt_path_input_routine.setReadOnly(True)
        self.dpt_import_btn_routine = ModernButton("导入DPT JSON文件", "#0EA5E9", "📂")

        routine_dpt_import_layout = self._create_file_import_layout(
            self.dpt_path_input_routine,
            self.dpt_import_btn_routine,
            "DPT JSON路径："
        )
        layout.addLayout(routine_dpt_import_layout)

        # 3. 表格区域
        self.routine_table = QtWidgets.QTableWidget(0, 6)
        self.routine_table.setHorizontalHeaderLabels(["序号", "内容", "选择参数对象", "选择参数状态", "例程控制类型", "执行操作"])

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
        LogPanelBuilder.attach_search(log_layout, self.routine_log_text)
        log_layout.addWidget(self.routine_log_text)
        log_group.setLayout(log_layout)
        self.routine_splitter.set_panels(content_widget, log_group, initial_log_height=220)

        self.tab_widget.addTab(self.routine_tab, "常用$31&$2F服务")

    def append_param_log(self, message: str):
        """向常用$2E服务日志窗口添加日志"""
        self._append_log(self.param_log_text, message)

    def append_routine_log(self, message: str):
        """向常用例程控制日志窗口添加日志"""
        self._append_log(self.routine_log_text, message)

    def _append_log(self, text_edit, message: str):
        # Record to OperationLogManager
        OperationLogManager.instance().append_log("通用配置", message)
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
            if hasattr(QtCore.Qt, "AlignmentFlag"):
                index_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            else:
                index_item.setTextAlignment(getattr(QtCore.Qt, "AlignCenter", 0x0084))
            self.routine_table.setItem(row_idx, 0, index_item)

            # 2. 内容
            content_widget = QtWidgets.QWidget()
            content_layout = QtWidgets.QHBoxLayout(content_widget)
            content_layout.setContentsMargins(5, 5, 5, 5)
            content_layout.setSpacing(10)

            align_left = getattr(QtCore.Qt, "AlignLeft", 0x0001)
            align_vcenter = getattr(QtCore.Qt, "AlignVCenter", 0x0080)
            if hasattr(QtCore.Qt, "AlignLeft"):
                align_left = QtCore.Qt.AlignLeft
            if hasattr(QtCore.Qt, "AlignVCenter"):
                align_vcenter = QtCore.Qt.AlignVCenter
            content_layout.setAlignment(align_left | align_vcenter)

            content_label = QtWidgets.QLabel(str(service.get("content", "")))
            content_layout.addWidget(content_label)

            help_text = service.get("help", "")
            if isinstance(help_text, (dict, list)):
                help_text = str(help_text)

            help_image_path = service.get("helpImage", "")

            if help_text and help_image_path:
                help_label = QtWidgets.QLabel(str(help_text))
                help_label.setStyleSheet("color: blue; text-decoration: underline; cursor: pointer;")
                cursor_shape = getattr(QtCore.Qt, "PointingHandCursor", 13)
                help_label.setCursor(QtGui.QCursor(cursor_shape))
                help_label.mousePressEvent = lambda event, path=help_image_path: self._show_help_image(path)
                content_layout.addWidget(help_label)

            content_layout.addStretch()
            self.routine_table.setCellWidget(row_idx, 1, content_widget)

            # 3. 参数对象
            param_obj = service.get("paramObject", {})
            self._create_cell_control(self.routine_table, row_idx, 2, param_obj, service, "paramObject_val")

            # 4. 参数状态
            param_state = service.get("paramState", {})
            self._create_cell_control(self.routine_table, row_idx, 3, param_state, service, "paramState_val")

            # 5. Start Routine
            # Priority: Try "routineControlType" first (as per user request), then "startRoutine"
            routine_control = service.get("routineControlType")
            if not routine_control:
                routine_control = service.get("startRoutine", {})

            self._create_cell_control(self.routine_table, row_idx, 4, routine_control, service, "routineControlType_val")

            # 6. 执行操作
            btn_widget = QtWidgets.QWidget()
            btn_layout = QtWidgets.QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(4, 2, 4, 2)
            if hasattr(QtCore.Qt, "AlignmentFlag"):
                btn_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            else:
                btn_layout.setAlignment(getattr(QtCore.Qt, "AlignCenter", 0x0084))

            btn_color = "#9CA3AF"
            exec_btn = ModernButton("执行", btn_color, "▶", dense=True)
            exec_btn.setMinimumWidth(100)
            exec_btn.clicked.connect(lambda checked, s=service, r=row_idx: execute_callback(s, r))

            # 状态标签
            status_label = QtWidgets.QLabel("")
            status_label.setStyleSheet("font-weight: bold; margin-left: 5px;")
            status_label.setFixedWidth(80)
            status_label.setAlignment(QtCore.Qt.AlignCenter)

            btn_layout.addWidget(exec_btn)
            btn_layout.addWidget(status_label) # Add label next to button

            self.routine_table.setCellWidget(row_idx, 5, btn_widget)

            service["_exec_btn"] = exec_btn

    def update_2e_table(self, services, execute_callback):
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
            self._create_cell_control(self.param_table, i, 2, service.get("paramObject", {}), service, "paramObject_val")

            # 参数状态 (Column 3)
            self._create_cell_control(self.param_table, i, 3, service.get("paramState", {}), service, "paramState_val")

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

            # 状态标签
            status_label = QtWidgets.QLabel("")
            status_label.setStyleSheet("font-weight: bold; margin-left: 5px;")
            status_label.setFixedWidth(80)
            status_label.setAlignment(QtCore.Qt.AlignCenter)

            btn_layout.addWidget(exec_btn)
            btn_layout.addWidget(status_label)

            btn_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter if hasattr(QtCore.Qt, "AlignmentFlag") else getattr(QtCore.Qt, "AlignCenter", 0x0084))
            self.param_table.setCellWidget(i, 4, btn_widget)


    def set_last_read_time(self, time_str):
        self.last_read_time_label.setText(f"最后读取时间: {time_str}")

    def set_page_info(self, current, total_pages, total_items):
        self.page_info_label.setText(f"第 {current}/{total_pages} 页，共 {total_items} 条")

    def set_routine_page_info(self, current, total_pages, total_items):
        self.routine_page_info_label.setText(f"第 {current}/{total_pages} 页，共 {total_items} 条")

    def set_routine_last_read_time(self, time_str):
        self.routine_last_read_label.setText(f"最后读取时间: {time_str}")

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
                ratios = [1, 6, 5, 5, 5, 3]
                total = sum(ratios)
                used_width = 0
                for i in range(5):
                    w = int(width * ratios[i] / total)
                    self.routine_table.setColumnWidth(i, w)
                    used_width += w
                self.routine_table.setColumnWidth(5, width - used_width)

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

    def _create_cell_control(self, table, row, col, config, service_data, data_key):
        """根据配置创建单元格控件"""
        c_type = config.get("type", "fixed")

        if c_type == "checkabledropdown":
            combo = CheckableComboBox()

            # 禁止鼠标滚动改变选项
            combo.wheelEvent = lambda event: event.ignore()

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

            table.setCellWidget(row, col, combo)

        elif c_type == "dropdown":
            combo = QtWidgets.QComboBox()
            # Disable mouse wheel to prevent accidental changes
            combo.wheelEvent = lambda event: event.ignore()

            # 过滤掉 "---" 选项
            options = config.get("options", [])
            # options = [opt for opt in raw_options if opt != "---"]
            combo.addItems(options)

            default = config.get("default", "")

            if default:
                combo.setCurrentText(default)
            else:
                combo.setCurrentIndex(-1)
                # 尝试设置占位符
                # QComboBox normally doesn't have placeholder unless editable
                pass

            # 绑定数据更新
            # 如果 index 为 -1，text 可能为空
            def update_dropdown_data(text, s=service_data, k=data_key):
                val = text if text else "---"
                s.update({k: val})

            combo.currentTextChanged.connect(lambda text, s=service_data, k=data_key: update_dropdown_data(text, s, k))
            # 初始化数据
            curr_text = combo.currentText()
            service_data[data_key] = curr_text if curr_text else "---"

            table.setCellWidget(row, col, combo)

        elif c_type == "input":
            line_edit = QtWidgets.QLineEdit()
            line_edit.setPlaceholderText(config.get("placeholder", ""))



            # 绑定数据更新
            line_edit.textChanged.connect(lambda text, s=service_data, k=data_key: s.update({k: text}))
            # 初始化数据
            service_data[data_key] = line_edit.text()

            table.setCellWidget(row, col, line_edit)

        else: # fixed
            value = config.get("value", "")
            item = QtWidgets.QTableWidgetItem(value)
            # item.setTextAlignment(QtCore.Qt.AlignCenter)
            item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter if hasattr(QtCore.Qt, "AlignmentFlag") else getattr(QtCore.Qt, "AlignCenter", 0x0084))
            # 初始化数据
            service_data[data_key] = value
            table.setItem(row, col, item)

    def _reset_routine_btn(self, btn):
        """重置例程控制按钮样式"""
        if btn is None:
             return

        # 恢复默认样式
        btn.setStyleSheet("")
        btn.setText("执行")

    def _reset_2e_btn(self, btn):
        """重置 $2E 服务按钮样式"""
        if btn is None:
             return

        # 恢复默认样式
        btn.setStyleSheet("")
        btn.setText("执行")

    def set_button_status(self, table: QtWidgets.QTableWidget, row: int, status: str):
        """
        设置执行状态 (修改为更新旁边的QLabel)
        status: "normal", "success", "failed", "executing"
        """
        if row < 0 or row >= table.rowCount():
            return

        col = 4
        widget = table.cellWidget(row, col)
        if not widget:
            return

        btn = widget.findChild(QtWidgets.QPushButton)
        label = widget.findChild(QtWidgets.QLabel)

        if not label:
            # Try to find again if layout structure is tricky, but we added it directly to layout
            return

        if status == "executing":
            label.setText("执行中...")
            label.setStyleSheet("color: blue; font-weight: bold; margin-left: 5px;")
            if btn: btn.setEnabled(False)

        elif status == "success":
            label.setText("执行成功")
            label.setStyleSheet("color: #22C55E; font-weight: bold; margin-left: 5px;")
            if btn: btn.setEnabled(True)
            # 3秒后清除文字
            QtCore.QTimer.singleShot(3000, lambda: label.setText(""))

        elif status == "failed":
            label.setText("执行失败")
            label.setStyleSheet("color: #EF4444; font-weight: bold; margin-left: 5px;")
            if btn: btn.setEnabled(True)

        elif status == "normal":
            label.setText("")
            if btn: btn.setEnabled(True)

    def _reset_btn_style(self, btn):
        # No longer needed to change color, just ensure enabled
        if btn:
            btn.setEnabled(True)

    def update_row_status(self, row_index: int, success: bool, is_2e: bool = True):
        table = self.param_table if is_2e else self.routine_table
        status = "success" if success else "failed"
        self.set_button_status(table, row_index, status)
