from PyQt5 import QtWidgets, QtCore, QtGui
import warnings

from app.common.log.operation_log_manager import OperationLogManager

# 忽略 PyQt5/sip 在 Python 3.11+ 下的 DeprecationWarning
warnings.filterwarnings("ignore", category=DeprecationWarning, message=".*sipPyTypeDict.*")

from app.common.ui.widgets import ModernButton, MultiSelectComboBox
from app.presentation.views.base_view import BaseView
from app.common.ui.modern_widgets import MessageToast


class LogConfigView(BaseView):
    modify_requested = QtCore.pyqtSignal(int)

    def setup_ui(self):
        # 使用 TabWidget 布局
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        self.tab_widget = QtWidgets.QTabWidget()
        # 移除局部样式，使用全局样式
        main_layout.addWidget(self.tab_widget)

        # 初始化三个标签页
        self._init_ecu_tab()
        self._init_app_tab()
        self._init_restore_tab()

    def _init_ecu_tab(self):
        self.ecu_tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(self.ecu_tab)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

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
        # 移除局部样式，使用全局样式以保持一致
        log_layout.addWidget(self.ecu_log_text)
        log_group.setLayout(log_layout)
        layout.addWidget(log_group, stretch=1)

        self.tab_widget.addTab(self.ecu_tab, "ECU配置")

    def _init_app_tab(self):
        self.app_tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(self.app_tab)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        # 筛选行
        filter_layout = QtWidgets.QHBoxLayout()
        filter_layout.addWidget(QtWidgets.QLabel("ECUID:"))
        self.app_filter_ecu_combo = QtWidgets.QComboBox()
        self.app_filter_ecu_combo.setMinimumWidth(100)
        filter_layout.addWidget(self.app_filter_ecu_combo)

        filter_layout.addWidget(QtWidgets.QLabel("APPID:"))
        self.app_filter_appid_combo = QtWidgets.QComboBox()
        self.app_filter_appid_combo.setMinimumWidth(100)
        filter_layout.addWidget(self.app_filter_appid_combo)

        filter_layout.addWidget(QtWidgets.QLabel("LOGLevel:"))
        self.app_filter_loglevel_combo = QtWidgets.QComboBox()
        self.app_filter_loglevel_combo.setMinimumWidth(100)
        self.app_filter_loglevel_combo.addItems(["", "OFF", "FATAL", "ERROR", "WARN", "INFO", "DEBUG", "VERBOSE"])
        filter_layout.addWidget(self.app_filter_loglevel_combo)

        filter_layout.addStretch()

        self.app_search_btn = ModernButton("搜索", "#3B82F6", "🔍")
        filter_layout.addWidget(self.app_search_btn)
        self.app_refresh_btn = ModernButton("更新", "#0EA5E9", "🔄")
        filter_layout.addWidget(self.app_refresh_btn)

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
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.Stretch)
        header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(7, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(8, QtWidgets.QHeaderView.ResizeToContents)

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
        page_size_layout.addWidget(self.page_size_combo)
        page_size_layout.addWidget(QtWidgets.QLabel("条"))
        bottom_layout.addLayout(page_size_layout)

        bottom_layout.addSpacing(20)

        self.export_logs_btn = ModernButton("导出日志", "#10B981", "⬇")
        bottom_layout.addWidget(self.export_logs_btn)
        self.delete_selected_btn = ModernButton("删除选中", "#EF4444", "🗑")
        bottom_layout.addWidget(self.delete_selected_btn)
        self.refresh_logs_btn = ModernButton("刷新", "#0EA5E9", "🔄")
        bottom_layout.addWidget(self.refresh_logs_btn)

        layout.addLayout(bottom_layout)

        # 操作日志区
        log_group = QtWidgets.QGroupBox("操作日志")
        log_layout = QtWidgets.QVBoxLayout()
        log_layout.setContentsMargins(10, 20, 10, 10)
        self.app_log_text = QtWidgets.QTextEdit()
        self.app_log_text.setReadOnly(True)
        self.app_log_text.setPlaceholderText("这里显示用户的操作日志...")
        self.app_log_text.setMaximumHeight(150) # 保留高度限制，避免挤压表格
        log_layout.addWidget(self.app_log_text)
        log_group.setLayout(log_layout)
        layout.addWidget(log_group)

        self.tab_widget.addTab(self.app_tab, "APP配置")

    def _init_restore_tab(self):
        self.restore_tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(self.restore_tab)
        layout.setSpacing(20)
        layout.setContentsMargins(30, 30, 30, 30)

        options_group = QtWidgets.QWidget()
        options_layout = QtWidgets.QVBoxLayout(options_group)
        options_layout.setSpacing(15)

        self.restore_ccua = QtWidgets.QCheckBox("恢复CCUA默认配置")
        self.restore_ccu0 = QtWidgets.QCheckBox("恢复CCU0默认配置")
        self.restore_ccu1 = QtWidgets.QCheckBox("恢复CCU1默认配置")
        self.delete_logs = QtWidgets.QCheckBox("同时删除所有日志文件")

        # 加大字体
        font = self.restore_ccua.font()
        font.setPointSize(10)
        for chk in [self.restore_ccua, self.restore_ccu0, self.restore_ccu1, self.delete_logs]:
            chk.setFont(font)
            options_layout.addWidget(chk)

        layout.addWidget(options_group)

        btn_layout = QtWidgets.QHBoxLayout()
        self.restore_btn = ModernButton("执行恢复操作", "#EF4444", "⚠️")
        self.restore_btn.setMinimumWidth(150)
        btn_layout.addWidget(self.restore_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        layout.addStretch()

        # 操作日志区
        log_group = QtWidgets.QGroupBox("操作日志")
        log_layout = QtWidgets.QVBoxLayout()
        log_layout.setContentsMargins(10, 20, 10, 10)
        self.restore_log_text = QtWidgets.QTextEdit()
        self.restore_log_text.setReadOnly(True)
        self.restore_log_text.setPlaceholderText("这里显示用户的操作日志...")
        log_layout.addWidget(self.restore_log_text)
        log_group.setLayout(log_layout)
        layout.addWidget(log_group, stretch=1)

        self.tab_widget.addTab(self.restore_tab, "恢复默认配置")

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
        # super().show_message(message, type) # 移除弹框
        self.append_log(f"[{type.upper()}] {message}")

        # 使用 Toast 提示
        msg_type = 2 # info
        if type == "success":
            msg_type = 0
        elif type == "error":
            msg_type = 1
        elif type == "warning":
            msg_type = 1 # warning 也用红色或自定义

        MessageToast(self).show_toast(message, msg_type)

    def populate(self, apps):
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
            index_item = QtWidgets.QTableWidgetItem(str(i + 1))
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
