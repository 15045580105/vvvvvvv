from PyQt5 import QtWidgets, QtCore, QtGui
import warnings

from app.common.log.operation_log_manager import OperationLogManager

# 忽略 PyQt5/sip 在 Python 3.11+ 下的 DeprecationWarning
warnings.filterwarnings("ignore", category=DeprecationWarning, message=".*sipPyTypeDict.*")

from app.common.ui.widgets import ModernButton, MultiSelectComboBox
from app.presentation.views.base_view import BaseView
from app.common.ui.modern_widgets import MessageToast
from app.common.ui.log_splitter import LogAreaSplitter
from app.common.ui.log_panel import LogPanelBuilder


class LogConfigEditDialog(QtWidgets.QDialog):
    """
    自定义编辑对话框：展示应用全量信息，但仅允许修改日志等级。
    """
    def __init__(self, parent, app_info):
        super().__init__(parent)
        self.setWindowTitle("修改日志配置")
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint)
        self.resize(400, 350)

        # 解析数据：(app_id, ecu_id, log_level, file_no, file_size, total_size)
        # 注意适配数据长度，防止越界
        self.app_id = app_info[0] if len(app_info) > 0 else ""
        self.ecu_id = app_info[1] if len(app_info) > 1 else ""
        self.current_level = app_info[2] if len(app_info) > 2 else ""
        # 其他信息可能在 app_info 中，也可能没有，做容错
        file_no = app_info[3] if len(app_info) > 3 else "-"
        file_size = app_info[4] if len(app_info) > 4 else "-"
        total_size = app_info[5] if len(app_info) > 5 else "-"

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        form_layout = QtWidgets.QFormLayout()
        form_layout.setSpacing(10)

        # 统一定义只读样式：灰色背景，灰色文字
        readonly_style = """
            QLineEdit {
                background-color: #F3F4F6;
                color: #6B7280;
                border: 1px solid #E5E7EB;
                border-radius: 4px;
                padding: 6px;
            }
        """

        # 按照表头顺序展示信息字段
        self._add_readonly_field(form_layout, "APPID:", self.app_id, readonly_style)
        self._add_readonly_field(form_layout, "ECUID:", self.ecu_id, readonly_style)

        # 日志等级（可修改 - 重点高亮）
        self.level_combo = QtWidgets.QComboBox()
        self.level_combo.addItems(["OFF", "FATAL", "ERROR", "WARN", "INFO", "DEBUG", "VERBOSE"])
        self.level_combo.setCurrentText(self.current_level)
        _setup_searchable_combo(self.level_combo)
        self.level_combo.setStyleSheet("""
            QComboBox {
                background-color: #FFFFFF;
                color: #111827;
                border: 1px solid #3B82F6;
                border-radius: 4px;
                padding: 6px;
                font-weight: bold;
            }
            QComboBox::drop-down {
                border: none;
            }
        """)

        level_label = QtWidgets.QLabel("LOGLevel:")
        level_label.setStyleSheet("font-weight: bold; color: #111827;")
        form_layout.addRow(level_label, self.level_combo)

        # 继续展示剩余只读信息
        self._add_readonly_field(form_layout, "FileNo:", str(file_no), readonly_style)
        self._add_readonly_field(form_layout, "FileSize:", str(file_size), readonly_style)
        self._add_readonly_field(form_layout, "TotalSize(MB):", str(total_size), readonly_style)

        layout.addLayout(form_layout)
        layout.addStretch()

        # 4. 按钮区
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QtWidgets.QPushButton("取消")
        cancel_btn.setFixedSize(80, 32)
        cancel_btn.clicked.connect(self.reject)

        confirm_btn = QtWidgets.QPushButton("确定修改")
        confirm_btn.setFixedSize(100, 32)
        confirm_btn.setStyleSheet("background-color: #3B82F6; color: white; border-radius: 4px; font-weight: bold;")
        confirm_btn.clicked.connect(self.accept)

        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(confirm_btn)

        layout.addLayout(btn_layout)

    def _add_readonly_field(self, layout, label_text, value, style):
        field = QtWidgets.QLineEdit(str(value))
        field.setReadOnly(True)
        field.setStyleSheet(style)
        layout.addRow(label_text, field)

    def get_new_level(self):
        return self.level_combo.currentText()


class LogConfigView(BaseView):
    modify_requested = QtCore.pyqtSignal(int)

    def setup_ui(self):
        # 使用 TabWidget 布局
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # 新增日志配置文件导入区域
        import_layout = QtWidgets.QHBoxLayout()
        import_label = QtWidgets.QLabel("日志配置文件路径:")
        import_layout.addWidget(import_label)

        self.map_path_edit = QtWidgets.QLineEdit()
        self.map_path_edit.setPlaceholderText("请导入 process_log_config_map.json")
        self.map_path_edit.setReadOnly(True)
        import_layout.addWidget(self.map_path_edit)

        self.import_map_btn = ModernButton("导入json文件", "#0EA5E9", "📂")
        import_layout.addWidget(self.import_map_btn)

        main_layout.addLayout(import_layout)

        self.tab_widget = QtWidgets.QTabWidget()
        # 移除局部样式，使用全局样式
        main_layout.addWidget(self.tab_widget)

        # 初始化三个标签页
        self._init_ecu_tab()
        self._init_app_tab()
        self._init_restore_tab()

    def _init_ecu_tab(self):
        self.ecu_tab = QtWidgets.QWidget()
        root_layout = QtWidgets.QVBoxLayout(self.ecu_tab)
        root_layout.setSpacing(0)
        root_layout.setContentsMargins(0, 0, 0, 0)
        self.ecu_splitter = LogAreaSplitter(self.ecu_tab, min_log_height=150, max_log_ratio=0.6)
        root_layout.addWidget(self.ecu_splitter)
        content_widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(content_widget)

        # 控制区域
        controls_layout = QtWidgets.QGridLayout()
        controls_layout.setHorizontalSpacing(12)
        controls_layout.setVerticalSpacing(12)

        # Row 0: ECU select
        controls_layout.addWidget(QtWidgets.QLabel("请选择ECU:"), 0, 0)
        self.ecu_select_combo = MultiSelectComboBox()
        self.ecu_select_combo.setMinimumWidth(250)
        self.ecu_select_combo.addItems(["CCUA", "CCU0", "CCU1"])
        controls_layout.addWidget(self.ecu_select_combo, 0, 1)

        # Row 1: Log level select
        controls_layout.addWidget(QtWidgets.QLabel("请选择日志等级:"), 1, 0)
        self.ecu_log_level_combo = QtWidgets.QComboBox()
        self.ecu_log_level_combo.setMinimumWidth(250)
        self.ecu_log_level_combo.addItems(["OFF", "FATAL", "ERROR", "WARN", "INFO", "DEBUG", "VERBOSE"])
        _setup_searchable_combo(self.ecu_log_level_combo)
        controls_layout.addWidget(self.ecu_log_level_combo, 1, 1)

        # Row 2: Execute button
        self.ecu_execute_btn = ModernButton("执行配置", "#3B82F6", "✔")
        self.ecu_execute_btn.setFixedWidth(120)
        controls_layout.addWidget(self.ecu_execute_btn, 2, 1, QtCore.Qt.AlignmentFlag.AlignLeft)

        controls_layout.setColumnStretch(2, 1)
        layout.addLayout(controls_layout)

        layout.addStretch()

        # 操作日志区
        log_group = QtWidgets.QGroupBox("操作日志")
        log_layout = QtWidgets.QVBoxLayout()
        log_layout.setContentsMargins(10, 20, 10, 10)  # 调整边距以适应 GroupBox 标题
        self.ecu_log_text = QtWidgets.QTextEdit()
        self.ecu_log_text.setReadOnly(True)
        self.ecu_log_text.setPlaceholderText("这里显示用户的操作日志...")
        LogPanelBuilder.attach_search(log_layout, self.ecu_log_text)
        log_layout.addWidget(self.ecu_log_text)
        log_group.setLayout(log_layout)
        self.ecu_splitter.set_panels(content_widget, log_group, initial_log_height=180)

        self.tab_widget.addTab(self.ecu_tab, "ECU配置")

    def _init_app_tab(self):
        self.app_tab = QtWidgets.QWidget()
        root_layout = QtWidgets.QVBoxLayout(self.app_tab)
        root_layout.setSpacing(0)
        root_layout.setContentsMargins(0, 0, 0, 0)
        self.app_splitter = LogAreaSplitter(self.app_tab, min_log_height=150, max_log_ratio=0.6)
        root_layout.addWidget(self.app_splitter)
        content_widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(content_widget)

        # 筛选行
        filter_layout = QtWidgets.QHBoxLayout()
        filter_layout.addWidget(QtWidgets.QLabel("ECUID:"))
        self.app_filter_ecu_combo = QtWidgets.QComboBox()
        self.app_filter_ecu_combo.setMinimumWidth(100)
        _setup_searchable_combo(self.app_filter_ecu_combo)
        filter_layout.addWidget(self.app_filter_ecu_combo)

        filter_layout.addWidget(QtWidgets.QLabel("APPID:"))
        self.app_filter_appid_combo = QtWidgets.QComboBox()
        self.app_filter_appid_combo.setMinimumWidth(100)
        _setup_searchable_combo(self.app_filter_appid_combo)
        filter_layout.addWidget(self.app_filter_appid_combo)

        filter_layout.addWidget(QtWidgets.QLabel("LOGLevel:"))
        self.app_filter_loglevel_combo = QtWidgets.QComboBox()
        self.app_filter_loglevel_combo.setMinimumWidth(100)
        self.app_filter_loglevel_combo.addItems(["全部", "OFF", "FATAL", "ERROR", "WARN", "INFO", "DEBUG", "VERBOSE"])
        _setup_searchable_combo(self.app_filter_loglevel_combo)
        filter_layout.addWidget(self.app_filter_loglevel_combo)

        filter_layout.addStretch()

        self.app_search_btn = ModernButton("搜索", "#3B82F6", "🔍")
        filter_layout.addWidget(self.app_search_btn)
        self.app_refresh_btn = ModernButton("更新", "#0EA5E9", "🔄")
        filter_layout.addWidget(self.app_refresh_btn)

        self.batch_modify_btn = ModernButton("批量修改日志等级", "#F59E0B", "✎")
        self.batch_modify_btn.setToolTip("批量修改选中APP的日志等级")
        filter_layout.addWidget(self.batch_modify_btn)

        layout.addLayout(filter_layout)

        # APP table
        self.app_table = QtWidgets.QTableWidget(0, 9)
        self.app_table.setHorizontalHeaderLabels([
            "", "序号", "APPID", "ECUID", "LOGLevel", "FileNo", "FileSize", "TotalSize(MB)", "操作"
        ])
        self.app_table.verticalHeader().setVisible(False)
        self.app_table.setAlternatingRowColors(True)
        self.app_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.app_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.app_table.verticalHeader().setDefaultSectionSize(40)

        header = self.app_table.horizontalHeader()

        # 1. 设置所有列为 Interactive (完全允许用户手动调整宽度)
        for i in range(9):
            header.setSectionResizeMode(i, QtWidgets.QHeaderView.Interactive)

        # 2. 关键修改：开启“最后一列自动拉伸”
        # 这样既保证了表格始终铺满整个宽度（无右侧留白），又不锁定任何列的宽度（保留调整权）
        header.setStretchLastSection(True)

        # 3. 设置各列的初始宽度 (适度调整，留出空间给最后一列拉伸)
        self.app_table.setColumnWidth(0, 50)  # 复选框
        self.app_table.setColumnWidth(1, 50)  # 序号
        self.app_table.setColumnWidth(2, 200) # APPID
        self.app_table.setColumnWidth(3, 200) # ECUID
        self.app_table.setColumnWidth(4, 200) # LOGLevel
        self.app_table.setColumnWidth(5, 200)  # FileNo
        self.app_table.setColumnWidth(6, 200) # FileSize
        self.app_table.setColumnWidth(7, 200) # TotalSize

        layout.addWidget(self.app_table, stretch=2)

        # 底部控制: 分页 + 页码 + 导出/删除
        bottom_layout = QtWidgets.QHBoxLayout()

        self.prev_page_btn = ModernButton("上一页", "#6B7280", "←")
        bottom_layout.addWidget(self.prev_page_btn)
        self.page_info_label = QtWidgets.QLabel("第 1 / 1 页")
        bottom_layout.addWidget(self.page_info_label)
        self.next_page_btn = ModernButton("下一页", "#6B7280", "→")
        bottom_layout.addWidget(self.next_page_btn)

        bottom_layout.addStretch()

        page_size_layout = QtWidgets.QHBoxLayout()
        page_size_layout.addWidget(QtWidgets.QLabel("每页显示"))
        self.page_size_combo = QtWidgets.QComboBox()
        self.page_size_combo.addItems(["10", "20", "50"])
        self.page_size_combo.setCurrentText("20")
        page_size_layout.addWidget(self.page_size_combo)
        page_size_layout.addWidget(QtWidgets.QLabel("条"))
        bottom_layout.addLayout(page_size_layout)

        bottom_layout.addSpacing(20)

        layout.addLayout(bottom_layout)

        # 操作日志区
        log_group = QtWidgets.QGroupBox("操作日志")
        log_layout = QtWidgets.QVBoxLayout()
        log_layout.setContentsMargins(10, 20, 10, 10)
        self.app_log_text = QtWidgets.QTextEdit()
        self.app_log_text.setReadOnly(True)
        self.app_log_text.setPlaceholderText("这里显示用户的操作日志...")
        self.app_log_text.setMaximumHeight(16777215) # 保留高度限制，避免挤压表格
        LogPanelBuilder.attach_search(log_layout, self.app_log_text)
        log_layout.addWidget(self.app_log_text)
        log_group.setLayout(log_layout)
        self.app_splitter.set_panels(content_widget, log_group, initial_log_height=150)

        self.tab_widget.addTab(self.app_tab, "APP配置")

    def _init_restore_tab(self):
        self.restore_tab = QtWidgets.QWidget()
        root_layout = QtWidgets.QVBoxLayout(self.restore_tab)
        root_layout.setSpacing(0)
        root_layout.setContentsMargins(0, 0, 0, 0)
        self.restore_splitter = LogAreaSplitter(self.restore_tab, min_log_height=150, max_log_ratio=0.6)
        root_layout.addWidget(self.restore_splitter)
        content_widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(content_widget)

        options_group = QtWidgets.QWidget()
        options_layout = QtWidgets.QVBoxLayout(options_group)
        options_layout.setSpacing(15)

        self.restore_ccua = QtWidgets.QCheckBox("恢复CCUA默认配置")
        self.restore_ccu0 = QtWidgets.QCheckBox("恢复CCU0默认配置")
        self.restore_ccu1 = QtWidgets.QCheckBox("恢复CCU1默认配置")
        self.delete_logs = QtWidgets.QCheckBox("删除DLT日志文件")

        # 加大字体
        font = self.restore_ccua.font()
        font.setPointSize(10)
        for chk in [self.restore_ccua, self.restore_ccu0, self.restore_ccu1, self.delete_logs]:
            chk.setFont(font)
            options_layout.addWidget(chk)

        layout.addWidget(options_group)

        btn_layout = QtWidgets.QHBoxLayout()
        self.restore_btn = ModernButton("执行", "#EF4444", "⚠️")
        self.restore_btn.setMinimumWidth(150)
        btn_layout.addWidget(self.restore_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self.restore_progress_label = QtWidgets.QLabel("")
        self.restore_progress_label.setStyleSheet("color: #6B7280;")
        self.restore_progress_label.hide()
        layout.addWidget(self.restore_progress_label)

        self.restore_progress_bar = QtWidgets.QProgressBar()
        self.restore_progress_bar.setTextVisible(False)
        self.restore_progress_bar.setRange(0, 1)
        self.restore_progress_bar.setValue(0)
        self.restore_progress_bar.hide()
        layout.addWidget(self.restore_progress_bar)

        layout.addStretch()

        # 操作日志区
        log_group = QtWidgets.QGroupBox("操作日志")
        log_layout = QtWidgets.QVBoxLayout()
        log_layout.setContentsMargins(10, 20, 10, 10)
        self.restore_log_text = QtWidgets.QTextEdit()
        self.restore_log_text.setReadOnly(True)
        self.restore_log_text.setPlaceholderText("这里显示用户的操作日志...")
        LogPanelBuilder.attach_search(log_layout, self.restore_log_text)
        log_layout.addWidget(self.restore_log_text)
        log_group.setLayout(log_layout)
        self.restore_splitter.set_panels(content_widget, log_group, initial_log_height=180)

        self.tab_widget.addTab(self.restore_tab, "恢复默认配置")

    def show_confirm(self, message: str) -> bool:
        """显式展示模态确认弹窗"""
        reply = QtWidgets.QMessageBox.question(
            self,
            "确认操作",
            message,
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No
        )
        return reply == QtWidgets.QMessageBox.StandardButton.Yes

    def update_filter_combos(self, ecu_items: list, app_items: list):
        """Update the ECU and APPID filter comboboxes dynamically."""
        # Block signals to prevent triggering search during update
        self.app_filter_ecu_combo.blockSignals(True)
        self.app_filter_appid_combo.blockSignals(True)

        current_ecu = self.app_filter_ecu_combo.currentText()
        current_app = self.app_filter_appid_combo.currentText()

        # Update ECU Combo
        self.app_filter_ecu_combo.clear()
        self.app_filter_ecu_combo.addItem("全部")  # "All" option
        self.app_filter_ecu_combo.addItems(ecu_items)

        # Restore selection if still valid
        idx = self.app_filter_ecu_combo.findText(current_ecu)
        if idx >= 0:
            self.app_filter_ecu_combo.setCurrentIndex(idx)
        else:
            self.app_filter_ecu_combo.setCurrentIndex(0)

        # Update APPID Combo
        self.app_filter_appid_combo.clear()
        self.app_filter_appid_combo.addItem("全部") # "All" option
        self.app_filter_appid_combo.addItems(app_items)

        idx = self.app_filter_appid_combo.findText(current_app)
        if idx >= 0:
            self.app_filter_appid_combo.setCurrentIndex(idx)
        else:
            self.app_filter_appid_combo.setCurrentIndex(0)

        self.app_filter_ecu_combo.blockSignals(False)
        self.app_filter_appid_combo.blockSignals(False)

    def get_selected_apps(self):
        """获取当前选中的所有APP信息"""
        selected = []
        for row in range(self.app_table.rowCount()):
            # 检查 CheckBox 状态 (第0列)
            item = self.app_table.item(row, 0)
            if item.checkState() == QtCore.Qt.CheckState.Checked:
                # 获取该行数据
                app_data = {
                    "app_id": self.app_table.item(row, 2).text(),
                    "ecu_id": self.app_table.item(row, 3).text(),
                    "log_level": self.app_table.item(row, 4).text()
                }
                selected.append(app_data)
        return selected

    def append_log(self, message: str):
        """向所有日志窗口添加日志"""
        timestamp = QtCore.QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss")
        log_msg = f"[{timestamp}] {message}"

        # Record to OperationLogManager
        OperationLogManager.instance().append_log("日志配置", message)

        # 滚动到底部
        for text_edit in [self.ecu_log_text, self.app_log_text, self.restore_log_text]:
            text_edit.append(log_msg)
            cursor = text_edit.textCursor()
            cursor.movePosition(QtGui.QTextCursor.End)
            text_edit.setTextCursor(cursor)

    def show_message(self, message, type="info"):
        """重写 show_message 以同时记录到日志"""
        self.append_log(f"[{type.upper()}] {message}")
        # 使用 Toast 提示
        msg_type = 2 # info
        if type == "info":
            msg_type = 0
        elif type == "error":
            msg_type = 1
        elif type == "warning":
            msg_type = 1 # warning 也用红色或自定义

        MessageToast(self).show_toast(message, msg_type)

    def set_restore_progress(self, visible: bool, text: str = "", busy: bool = True):
        self.restore_progress_label.setText(text or "")
        self.restore_progress_label.setVisible(visible)
        self.restore_progress_bar.setVisible(visible)

        if not visible:
            self.restore_progress_bar.setRange(0, 1)
            self.restore_progress_bar.setValue(0)
            return

        if busy:
            self.restore_progress_bar.setRange(0, 0)
        else:
            self.restore_progress_bar.setRange(0, 1)
            self.restore_progress_bar.setValue(1)

    def populate(self, apps, start_index=1):
        """Populate the APP table.

        Supports legacy 3-field data and new 6-field data.

        Accepted formats per item in ``apps``:
        - (app_id, ecu_id, log_level)
        - (app_id, ecu_id, log_level, file_no, file_size, total_size_mb)
        """
        self.app_table.setRowCount(len(apps))
        for i, app_info in enumerate(apps):
            # Normalize to 6 values, with placeholders for missing file info
            if len(app_info) == 3:
                app_id, ecu_id, log_level = app_info
                file_no, file_size, total_size_mb = "-", "-", "-"
            else:
                app_id, ecu_id, log_level, file_no, file_size, total_size_mb = app_info

            # Column 0: checkbox
            check_item = QtWidgets.QTableWidgetItem()
            flags = check_item.flags()
            flags |= QtCore.Qt.ItemFlag.ItemIsUserCheckable
            flags |= QtCore.Qt.ItemFlag.ItemIsEnabled
            check_item.setFlags(flags)
            check_item.setCheckState(QtCore.Qt.CheckState.Unchecked)
            self.app_table.setItem(i, 0, check_item)

            # Column 1: index
            index_item = QtWidgets.QTableWidgetItem(str(start_index + i))
            index_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            self.app_table.setItem(i, 1, index_item)

            # Column 2: APPID
            app_item = QtWidgets.QTableWidgetItem(str(app_id))
            app_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            self.app_table.setItem(i, 2, app_item)

            # Column 3: ECUID
            ecu_item = QtWidgets.QTableWidgetItem(str(ecu_id))
            ecu_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            self.app_table.setItem(i, 3, ecu_item)

            # Column 4: LOGLevel
            level_item = QtWidgets.QTableWidgetItem(str(log_level))
            level_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            self.app_table.setItem(i, 4, level_item)

            # Column 5: FileNo
            file_no_item = QtWidgets.QTableWidgetItem(str(file_no))
            file_no_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            self.app_table.setItem(i, 5, file_no_item)

            # Column 6: FileSize
            file_size_item = QtWidgets.QTableWidgetItem(str(file_size))
            file_size_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            self.app_table.setItem(i, 6, file_size_item)

            # Column 7: TotalSize(MB)
            total_size_item = QtWidgets.QTableWidgetItem(str(total_size_mb))
            total_size_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            self.app_table.setItem(i, 7, total_size_item)

            # Column 8: 操作 - modify button placeholder (can be connected in controller)
            modify_btn = ModernButton("修改", "#3B82F6", "✎")
            modify_btn.clicked.connect(lambda _, r=i: self.modify_requested.emit(r))
            self.app_table.setCellWidget(i, 8, modify_btn)

def _setup_searchable_combo(combo):
    """
    辅助函数：配置 QComboBox 支持输入关键词模糊匹配（包含匹配）。
    """
    combo.setEditable(True)
    combo.setInsertPolicy(QtWidgets.QComboBox.NoInsert)
    # 使用 combo 当前的 model 作为补全源
    completer = QtWidgets.QCompleter(combo.model(), combo)
    completer.setFilterMode(QtCore.Qt.MatchContains)      # 包含模式
    completer.setCaseSensitivity(QtCore.Qt.CaseInsensitive) # 忽略大小写
    combo.setCompleter(completer)
