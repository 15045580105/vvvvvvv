from PyQt5 import QtWidgets, QtCore, QtGui

from app.common.log.operation_log_manager import OperationLogManager
from app.presentation.views.base_view import BaseView
from app.common.ui.widgets import ModernButton, CheckableComboBox, ResponsiveButtonFlowPanel
from app.common.ui.modern_widgets import MessageToast
from app.common.ui.log_splitter import LogAreaSplitter
from app.common.ui.log_panel import LogPanelBuilder

class CommonConfigView(BaseView):
    def setup_ui(self):
        # Main layout
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)
        self._shared_log_document = QtGui.QTextDocument(self)

        self._action_status_min_width = 72
        self._action_compact_threshold = 210

        # 顶部统一配置入口：后续两个标签页共用同一份 JSON 数据源。
        self._init_shared_config_import_area(main_layout)

        self.tab_widget = QtWidgets.QTabWidget()
        main_layout.addWidget(self.tab_widget)

        # Initialize tabs
        self._init_param_config_tab()
        self._init_routine_control_tab()

        # 监听 Tab 切换以调整列宽
        self.tab_widget.currentChanged.connect(lambda: self._adjust_column_widths())

    def _init_shared_config_import_area(self, parent_layout):
        card = QtWidgets.QGroupBox("统一服务配置")
        layout = QtWidgets.QVBoxLayout(card)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        self.config_path_input = QtWidgets.QLineEdit()
        self.config_path_input.setFixedHeight(36)
        self.config_path_input.setPlaceholderText("选择或输入常用服务JSON配置文件路径")
        self.config_path_input.setReadOnly(True)

        self.import_json_btn = ModernButton("导入JSON文件", "#22C55E", "📂")

        layout.addLayout(
            self._create_file_import_layout(
                self.config_path_input,
                self.import_json_btn,
                "常用服务JSON文件路径：",
            )
        )

        parent_layout.addWidget(card)

    def _create_file_import_layout(self, line_edit, button, label_text, add_form_btn=None):
        """创建标准文件导入布局。"""
        layout = QtWidgets.QHBoxLayout()
        layout.setSpacing(10)

        label = QtWidgets.QLabel(label_text)
        label.setFixedWidth(120)  # 统一标签宽度
        layout.addWidget(label)

        layout.addWidget(line_edit)

        button.setFixedWidth(160)
        layout.addWidget(button)

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

        # 2. 表格区域
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

        # 3. 分页控件 (仿照 bus_data_download_view)
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

        # 4. 日志区域
        log_group = QtWidgets.QGroupBox("操作日志")
        log_layout = QtWidgets.QVBoxLayout()
        log_layout.setContentsMargins(10, 20, 10, 10)
        self.param_log_text = QtWidgets.QTextEdit()
        self.param_log_text.setReadOnly(True)
        self.param_log_text.setDocument(self._shared_log_document)
        self.param_log_text.setPlaceholderText("这里显示常用服务的统一操作日志...")
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

        # 2. 表格区域
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

        # 3. 分页控件 (仿照 bus_data_download_view)
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

        # 4. 日志区域
        log_group = QtWidgets.QGroupBox("操作日志")
        log_layout = QtWidgets.QVBoxLayout()
        log_layout.setContentsMargins(10, 20, 10, 10)
        self.routine_log_text = QtWidgets.QTextEdit()
        self.routine_log_text.setReadOnly(True)
        self.routine_log_text.setDocument(self._shared_log_document)
        self.routine_log_text.setPlaceholderText("这里显示常用服务的统一操作日志...")
        LogPanelBuilder.attach_search(log_layout, self.routine_log_text)
        log_layout.addWidget(self.routine_log_text)
        log_group.setLayout(log_layout)
        self.routine_splitter.set_panels(content_widget, log_group, initial_log_height=220)

        self.tab_widget.addTab(self.routine_tab, "常用$31&$2F服务")

    def append_param_log(self, message: str):
        """向常用$2E服务日志窗口添加日志"""
        self.append_common_log(message)

    def append_routine_log(self, message: str):
        """向常用例程控制日志窗口添加日志"""
        self.append_common_log(message)

    def append_common_log(self, message: str):
        self._append_log(self.param_log_text, message)

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
        log_msg = f"[{type.upper()}] {message}"
        self.append_common_log(log_msg)

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
        """更新常用 `$31/$2F` 服务表格。

        这里消费的是 service 层已经标准化后的 JSON 数据：
        - `paramObject/paramState/routineControlType` 决定这一列渲染成什么控件；
        - 用户在控件上的选择会直接写回当前 `service` dict；
        - 点击执行时 controller 再把这个 `service` dict 传回 service 层生成 UDS。
        """
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
            param_obj = service.get("paramObject") or {"type": "fixed", "value": "N/A"}
            self._create_cell_control(self.routine_table, row_idx, 2, param_obj, service, "paramObject_val")

            # 4. 参数状态
            param_state = service.get("paramState") or {"type": "fixed", "value": "N/A"}
            self._create_cell_control(self.routine_table, row_idx, 3, param_state, service, "paramState_val")

            # 5. Start Routine
            routine_control = service.get("routineControlType") or service.get("startRoutine") or {"type": "fixed", "value": "N/A"}
            self._create_cell_control(self.routine_table, row_idx, 4, routine_control, service, "routineControlType_val")
            self._apply_routine_control_dependency(row_idx, service)

            # 6. 执行操作
            action_widget = self._create_action_cell(
                self.routine_table,
                row_idx,
                5,
                lambda checked=False, s=service, r=row_idx: execute_callback(s, r),
            )
            self.routine_table.setCellWidget(row_idx, 5, action_widget)

            service["_exec_btn"] = action_widget.findChild(QtWidgets.QPushButton, "action_exec_btn")

        self._adjust_table_action_cells(self.routine_table, 5)

    def update_2e_table(self, services, execute_callback):
        """
        更新 $2E 服务表格

        `services` 中每个元素都是标准化后的 service_info：
        - `content` 渲染描述列
        - `paramObject` / `paramState` 决定控件类型与选项
        - 控件的当前值会回写到 `paramObject_val` / `paramState_val`
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
            action_widget = self._create_action_cell(
                self.param_table,
                i,
                4,
                lambda checked=False, s=service, r=i: execute_callback(s, r),
            )
            self.param_table.setCellWidget(i, 4, action_widget)

        self._adjust_table_action_cells(self.param_table, 4)

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
        """根据可用空间动态调整列宽。

        目标不是让用户靠横向滚动查看，而是在大小屏幕切换时：
        - 保证每列最小可用宽度；
        - 尽量按比例分配空间；
        - 始终给“执行操作”列预留按钮+状态文本所需宽度。
        """
        if hasattr(self, 'param_table'):
            self._adjust_table_columns(
                self.param_table,
                ratios=[1, 7, 6, 6, 3],
                action_col=4,
                base_min_widths={0: 56, 1: 180, 2: 150, 3: 150},
            )

        if hasattr(self, 'routine_table'):
            self._adjust_table_columns(
                self.routine_table,
                ratios=[1, 6, 5, 5, 5, 3],
                action_col=5,
                base_min_widths={0: 56, 1: 180, 2: 140, 3: 140, 4: 140},
            )

    def _adjust_table_columns(self, table, ratios, action_col, base_min_widths):
        """按比例 + 最小宽度约束重分配表格列宽。"""
        width = table.viewport().width()
        if width <= 0:
            return

        action_min_width = self._calc_action_column_min_width(table, action_col)
        other_cols = [col for col in range(len(ratios)) if col != action_col]
        other_ratio_total = sum(ratios[col] for col in other_cols) or 1
        remaining_width = max(0, width - action_min_width)

        used_width = 0
        assigned = {}
        for col in other_cols:
            proportional = int(remaining_width * ratios[col] / other_ratio_total)
            assigned[col] = max(base_min_widths.get(col, 80), proportional)
            used_width += assigned[col]

        total_required = used_width + action_min_width
        if total_required > width:
            overflow = total_required - width
            shrinkable = [col for col in other_cols if assigned[col] > base_min_widths.get(col, 80)]
            while overflow > 0 and shrinkable:
                changed = False
                for col in list(shrinkable):
                    min_w = base_min_widths.get(col, 80)
                    if assigned[col] > min_w:
                        assigned[col] -= 1
                        overflow -= 1
                        changed = True
                        if overflow <= 0:
                            break
                    else:
                        shrinkable.remove(col)
                if not changed:
                    break

        for col in other_cols:
            table.setColumnWidth(col, assigned[col])

        used_except_action = sum(table.columnWidth(col) for col in other_cols)
        table.setColumnWidth(action_col, max(action_min_width, width - used_except_action))
        self._adjust_table_action_cells(table, action_col)

    def _calc_action_column_min_width(self, table, action_col):
        min_width = 160
        for row in range(table.rowCount()):
            widget = table.cellWidget(row, action_col)
            if widget:
                min_width = max(min_width, self._action_widget_preferred_width(widget, compact=False))
                min_width = max(min_width, self._action_widget_preferred_width(widget, compact=True))
        return min_width + 8

    def _action_widget_preferred_width(self, widget, compact=False):
        button = widget.findChild(QtWidgets.QPushButton, "action_exec_btn")
        label = widget.findChild(QtWidgets.QLabel, "action_status_label")
        if not button or not label:
            return 160

        spacing = 4 if compact else 8
        margins = (2, 2, 2, 2) if compact else (4, 2, 4, 2)
        left, _, right, _ = margins

        btn_text = button.property("compact_text") if compact else button.property("full_text")
        btn_text = btn_text or button.text() or "执行"
        font_metrics = button.fontMetrics()
        button_width = font_metrics.horizontalAdvance(str(btn_text)) + 28
        label_width = max(self._action_status_min_width, label.fontMetrics().horizontalAdvance("执行成功") + 18)
        return left + right + button_width + spacing + label_width

    def _create_action_cell(self, table, row, action_col, callback):
        widget = QtWidgets.QWidget()
        widget.setObjectName("action_cell_widget")
        layout = QtWidgets.QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        panel = ResponsiveButtonFlowPanel(widget, spacing=8, margins=(4, 2, 4, 2), row_spacing=4)
        panel.setObjectName("action_panel")
        panel.heightChanged.connect(lambda t=table, r=row, p=panel: self._sync_action_row_height(t, r, p))

        exec_btn = ModernButton("执行", "#9CA3AF", "▶", dense=True)
        exec_btn.setObjectName("action_exec_btn")
        exec_btn.setProperty("full_text", exec_btn.text())
        exec_btn.setProperty("compact_text", "执行")
        exec_btn.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        exec_btn.clicked.connect(callback)

        status_label = QtWidgets.QLabel("")
        status_label.setObjectName("action_status_label")
        align_center = getattr(QtCore.Qt, "AlignCenter", 0x0084)
        status_label.setAlignment(align_center)
        status_label.setMinimumWidth(self._action_status_min_width)
        status_label.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        status_label.setStyleSheet("font-weight: bold; margin-left: 2px; color: transparent;")

        panel.add_button(exec_btn)
        panel.layout = None
        status_label.setParent(panel)
        status_label.show()

        original_relayout = panel._relayout_buttons
        def relayout_with_label():
            original_relayout()
            self._layout_action_status(panel, status_label)
        panel._relayout_buttons = relayout_with_label
        panel._relayout_buttons()

        layout.addWidget(panel)
        widget.setProperty("action_col", action_col)
        widget.setProperty("action_exec_btn_ref", exec_btn)
        widget.setProperty("action_status_label_ref", status_label)
        return widget

    def _layout_action_status(self, panel, label):
        visible_buttons = [btn for btn in panel.buttons() if btn.isVisible()]
        left, top, right, bottom = getattr(panel, '_margins', (4, 2, 4, 2))
        usable_right = max(left, panel.width() - right)
        spacing = getattr(panel, '_spacing', 8)
        row_spacing = getattr(panel, '_row_spacing', 4)

        if visible_buttons:
            last_btn = visible_buttons[-1]
            btn_geo = last_btn.geometry()
            label_hint = label.sizeHint()
            label_w = max(label.minimumWidth(), label_hint.width())
            label_h = max(last_btn.height(), label_hint.height())

            inline_x = btn_geo.right() + 1 + spacing
            inline_fits = inline_x + label_w <= usable_right
            if inline_fits:
                label.setGeometry(inline_x, btn_geo.y(), label_w, label_h)
                total_height = max(36, max(btn_geo.bottom() + 1, label.y() + label_h) + bottom)
            else:
                new_y = btn_geo.y() + btn_geo.height() + row_spacing
                label.setGeometry(left, new_y, max(label.minimumWidth(), usable_right - left), label_h)
                total_height = max(36, label.y() + label_h + bottom)
        else:
            label_h = label.sizeHint().height()
            label.setGeometry(left, top, max(label.minimumWidth(), usable_right - left), label_h)
            total_height = max(36, top + label_h + bottom)

        panel.setMinimumHeight(total_height)
        if getattr(panel, '_last_height', None) != total_height:
            panel._last_height = total_height
            panel.heightChanged.emit()
        panel.updateGeometry()

    def _adjust_table_action_cells(self, table, action_col):
        for row in range(table.rowCount()):
            widget = table.cellWidget(row, action_col)
            if not widget:
                continue
            panel = widget.findChild(QtWidgets.QWidget, "action_panel")
            if not panel:
                continue
            available_width = max(0, table.columnWidth(action_col) - 8)
            panel.resize(available_width, panel.height())
            panel.set_compact_mode(available_width < self._action_compact_threshold)
            if hasattr(panel, '_relayout_buttons'):
                panel._relayout_buttons()
            self._sync_action_row_height(table, row, panel)

    def _sync_action_row_height(self, table, row, panel):
        if row < 0 or row >= table.rowCount():
            return
        desired_height = max(table.verticalHeader().defaultSectionSize(), panel.minimumHeight() + 6)
        if table.rowHeight(row) != desired_height:
            table.setRowHeight(row, desired_height)

    def _get_action_status_widgets(self, table: QtWidgets.QTableWidget, row: int):
        """返回操作列中的执行按钮和状态标签。"""
        if row < 0 or row >= table.rowCount():
            return None, None, -1

        col = table.columnCount() - 1
        # noinspection PyUnreachableCode
        widget = table.cellWidget(row, col)
        if not widget:
            return None, None, col

        btn = widget.property("action_exec_btn_ref")
        label = widget.property("action_status_label_ref")
        if not isinstance(btn, QtWidgets.QPushButton):
            btn = None
        if not isinstance(label, QtWidgets.QLabel):
            label = None
        return btn, label, col

    # noinspection PyUnreachableCode
    def set_button_status(self, table: QtWidgets.QTableWidget, row: int, status: str):
        """
        设置执行状态 (修改为更新旁边的QLabel)
        status: "normal", "success", "failed", "executing"
        """
        btn, label, col = self._get_action_status_widgets(table, row)
        if label is None or col < 0:
            return

        if status == "executing":
            label.setText("执行中...")
            label.setStyleSheet("color: blue; font-weight: bold; margin-left: 2px;")
            if btn:
                btn.setEnabled(False)

        elif status == "success":
            label.setText("执行成功")
            label.setStyleSheet("color: #22C55E; font-weight: bold; margin-left: 2px;")
            if btn:
                btn.setEnabled(True)
            QtCore.QTimer.singleShot(3000, lambda l=label, t=table, r=row, c=col: self._clear_action_status(l, t, r, c))

        elif status == "failed":
            label.setText("执行失败")
            label.setStyleSheet("color: #EF4444; font-weight: bold; margin-left: 2px;")
            if btn:
                btn.setEnabled(True)

        elif status == "normal":
            self._clear_action_status(label, table, row, col)
            if btn:
                btn.setEnabled(True)

        self._adjust_table_action_cells(table, col)

    def _clear_action_status(self, label, table=None, row=None, col=None):
        label.setText("")
        label.setStyleSheet("font-weight: bold; margin-left: 2px; color: transparent;")
        if table is not None and row is not None and col is not None:
            self._adjust_table_action_cells(table, col)

    def update_row_status(self, row_index: int, success: bool, is_2e: bool = True):
        table = self.param_table if is_2e else self.routine_table
        status = "success" if success else "failed"
        self.set_button_status(table, row_index, status)

    def update_routine_status(self, row_index: int, status_text: str, success: bool):
        """兼容 controller 的例程状态更新调用。"""
        self.set_button_status(self.routine_table, row_index, "success" if success else "failed")

    def _show_help_image(self, img_path="img.png"):
        """显示帮助图片"""
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("帮助信息")

        close_hint = getattr(QtCore.Qt, "WindowCloseButtonHint", 0x08000000)
        dialog.setWindowFlags(dialog.windowFlags() | close_hint)

        layout = QtWidgets.QVBoxLayout(dialog)
        label = QtWidgets.QLabel(dialog)
        align_center = getattr(QtCore.Qt, "AlignCenter", 0x0084)
        label.setAlignment(align_center)

        import os
        if not os.path.exists(img_path):
            cwd_path = os.path.join(os.getcwd(), img_path)
            if os.path.exists(cwd_path):
                img_path = cwd_path

        pixmap = QtGui.QPixmap(img_path)
        if not pixmap.isNull():
            label.setPixmap(pixmap)
            screen = QtWidgets.QApplication.primaryScreen()
            if screen:
                screen_size = screen.size()
                max_w, max_h = int(screen_size.width() * 0.8), int(screen_size.height() * 0.8)
                img_w = pixmap.width()
                img_h = pixmap.height()
                if img_w > max_w or img_h > max_h:
                    pixmap = pixmap.scaled(
                        max_w,
                        max_h,
                        QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                        QtCore.Qt.TransformationMode.SmoothTransformation,
                    )
                    label.setPixmap(pixmap)
            dialog.resize(label.pixmap().size())
        else:
            label.setText(f"未找到图片:\n{img_path}")
            dialog.resize(400, 200)

        layout.addWidget(label)
        dialog.exec_()

    def _should_disable_routine_param_selectors(self, value) -> bool:
        text = str(value or "").strip().lower()
        if not text:
            return False
        if ("执行00" in text) or ("00 return" in text) or (text in {"00", "0x00"}):
            return True
        if ("执行03 start" in text) or ("03 start" in text):
            return True
        return False

    def _set_table_cell_interaction_enabled(self, table, row, col, enabled: bool):
        widget = table.cellWidget(row, col)
        if widget is not None:
            widget.setEnabled(enabled)
            return

        item = table.item(row, col)
        if item is None:
            return

        flags = item.flags()
        editable_flag = getattr(QtCore.Qt, "ItemIsEditable", 0x0002)
        selectable_flag = getattr(QtCore.Qt, "ItemIsSelectable", 0x0001)
        enabled_flag = getattr(QtCore.Qt, "ItemIsEnabled", 0x0020)
        if enabled:
            item.setFlags(flags | editable_flag | selectable_flag | enabled_flag)
        else:
            item.setFlags(flags & ~editable_flag & ~selectable_flag)

    def _clear_table_cell_selection(self, table, row, col):
        widget = table.cellWidget(row, col)
        if isinstance(widget, CheckableComboBox):
            widget.blockSignals(True)
            for i in range(1, widget.model.rowCount()):
                item = widget.model.item(i)
                if hasattr(QtCore.Qt, "CheckState"):
                    item.setCheckState(QtCore.Qt.CheckState.Unchecked)
                else:
                    item.setCheckState(getattr(QtCore.Qt, "Unchecked", 0))
            widget.blockSignals(False)
            widget.updateText()
            return

        if isinstance(widget, QtWidgets.QComboBox):
            idx = widget.findText("---")
            widget.blockSignals(True)
            widget.setCurrentIndex(idx if idx >= 0 else -1)
            widget.blockSignals(False)
            return

        if isinstance(widget, QtWidgets.QLineEdit):
            widget.blockSignals(True)
            widget.clear()
            widget.blockSignals(False)
            return

        item = table.item(row, col)
        if item is not None:
            item.setText("N/A")

    def _apply_routine_control_dependency(self, row, service_data):
        """根据例程控制类型联动启用/禁用“参数对象 / 参数状态”。

        例如执行 `00 Return` 或 `03 Start` 时，当前业务要求这两列显示但不可编辑；
        切回其它控制类型后，再恢复可选状态。
        """
        if not hasattr(self, "routine_table") or row < 0 or row >= self.routine_table.rowCount():
            return
        control_value = service_data.get("routineControlType_val") or service_data.get("subFunction") or ""
        enabled = not self._should_disable_routine_param_selectors(control_value)
        if not enabled:
            service_data["paramObject_val"] = "---"
            service_data["paramState_val"] = "---"
            self._clear_table_cell_selection(self.routine_table, row, 2)
            self._clear_table_cell_selection(self.routine_table, row, 3)
        self._set_table_cell_interaction_enabled(self.routine_table, row, 2, enabled)
        self._set_table_cell_interaction_enabled(self.routine_table, row, 3, enabled)

    def _create_cell_control(self, table, row, col, config, service_data, data_key):
        """根据字段配置创建单元格控件，并把用户值回写到 `service_data`。

        这是 JSON -> 表格控件 的真正落点：
        - `fixed`：显示只读文本
        - `dropdown`：普通下拉框
        - `checkabledropdown`：多选复选下拉
        - `input`：输入框

        `data_key` 一般是 `paramObject_val` / `paramState_val` / `routineControlType_val`，
        后续 service 层会直接读取这些值来拼 payload。
        """
        if not isinstance(config, dict):
            config = {"type": "fixed", "value": "" if config is None else str(config)}

        c_type = config.get("type", "fixed")
        options = [str(opt) for opt in (config.get("options", []) or []) if str(opt).strip()]

        if c_type in {"dropdown", "checkabledropdown"} and not options:
            # 当 JSON 中 options 是空数组时，界面显示 N/A，且不创建可编辑控件。
            value = "N/A"
            item = QtWidgets.QTableWidgetItem(value)
            align_center = QtCore.Qt.AlignmentFlag.AlignCenter if hasattr(QtCore.Qt, "AlignmentFlag") else getattr(QtCore.Qt, "AlignCenter", 0x0084)
            item.setTextAlignment(align_center)
            service_data[data_key] = value
            table.setItem(row, col, item)
            return

        if c_type == "checkabledropdown":
            combo = CheckableComboBox()
            combo.wheelEvent = lambda event: event.ignore()

            combo.addItems(options)

            default = config.get("default", "")
            defaults = [d.strip() for d in default.split(",")] if default else []
            if defaults:
                combo.setCheckedItems(defaults)
            else:
                combo.updateText()

            # 复选下拉把用户勾选结果直接写回 service_data，执行时不再额外查表格控件。
            combo.checkedItemsChanged.connect(lambda _items, text, s=service_data, k=data_key: s.update({k: text or "---"}))
            service_data[data_key] = combo.lineEdit().text().strip() or "---"
            table.setCellWidget(row, col, combo)

        elif c_type == "dropdown":
            combo = QtWidgets.QComboBox()
            combo.wheelEvent = lambda event: event.ignore()
            default = config.get("default", "")
            if default == "---" and "---" not in options:
                options = ["---"] + options
            combo.addItems(options)

            if default and default in options:
                combo.setCurrentText(default)
            elif options:
                combo.setCurrentIndex(0)
            else:
                combo.setCurrentIndex(-1)

            def update_dropdown_data(text, s=service_data, k=data_key):
                val = text if text else "---"
                s.update({k: val})

            combo.currentTextChanged.connect(lambda text, s=service_data, k=data_key: update_dropdown_data(text, s, k))
            if table is getattr(self, "routine_table", None) and data_key == "routineControlType_val":
                # 例程控制类型一旦改变，需要立即联动本行其它两个选择器的可编辑状态。
                combo.currentTextChanged.connect(lambda _text, r=row, s=service_data: self._apply_routine_control_dependency(r, s))
            curr_text = combo.currentText()
            service_data[data_key] = curr_text if curr_text else "---"
            table.setCellWidget(row, col, combo)

        elif c_type == "input":
            line_edit = QtWidgets.QLineEdit()
            line_edit.setPlaceholderText(config.get("placeholder", ""))
            line_edit.textChanged.connect(lambda text, s=service_data, k=data_key: s.update({k: text}))
            service_data[data_key] = line_edit.text()
            table.setCellWidget(row, col, line_edit)

        else:
            value = str(config.get("value", ""))
            item = QtWidgets.QTableWidgetItem(value)
            align_center = QtCore.Qt.AlignmentFlag.AlignCenter if hasattr(QtCore.Qt, "AlignmentFlag") else getattr(QtCore.Qt, "AlignCenter", 0x0084)
            item.setTextAlignment(align_center)
            service_data[data_key] = value if value else "N/A"
            table.setItem(row, col, item)
            if table is getattr(self, "routine_table", None) and data_key == "routineControlType_val":
                self._apply_routine_control_dependency(row, service_data)

    def _reset_routine_btn(self, btn):
        """重置例程控制按钮样式"""
        if btn is None:
            return
        btn.setStyleSheet("")
        btn.setText("执行")

    def _reset_2e_btn(self, btn):
        """重置 $2E 服务按钮样式"""
        if btn is None:
            return
        btn.setStyleSheet("")
        btn.setText("执行")

    def _reset_btn_style(self, btn):
        if btn:
            btn.setEnabled(True)
