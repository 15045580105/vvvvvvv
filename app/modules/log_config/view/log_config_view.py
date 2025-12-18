from PyQt5 import QtWidgets, QtCore

from app.common.ui.widgets import ModernButton
from app.presentation.views.base_view import BaseView


class LogConfigView(BaseView):
    def setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(16)

        # ECU configuration group
        ecu_group = QtWidgets.QGroupBox("ECU配置")
        ecu_layout = QtWidgets.QGridLayout()
        ecu_layout.setHorizontalSpacing(12)
        ecu_layout.setVerticalSpacing(8)

        # Row 1: ECU select
        ecu_layout.addWidget(QtWidgets.QLabel("请选择ECU"), 0, 0)
        self.ecu_select_combo = QtWidgets.QComboBox()
        self.ecu_select_combo.setMinimumWidth(160)
        # Default ECU list, can be updated by controller
        self.ecu_select_combo.addItems(["CCUA", "CCU0", "CCU1"])
        ecu_layout.addWidget(self.ecu_select_combo, 0, 1)

        # Row 2: Log level select + execute button
        ecu_layout.addWidget(QtWidgets.QLabel("请选择日志等级"), 1, 0)
        self.ecu_log_level_combo = QtWidgets.QComboBox()
        self.ecu_log_level_combo.setMinimumWidth(160)
        self.ecu_log_level_combo.addItems(["OFF", "FATAL", "ERROR", "WARN", "INFO", "DEBUG", "VERBOSE"])
        ecu_layout.addWidget(self.ecu_log_level_combo, 1, 1)

        self.ecu_execute_btn = ModernButton("执行", "#3B82F6", "✔")
        ecu_layout.addWidget(self.ecu_execute_btn, 1, 2)

        ecu_layout.setColumnStretch(3, 1)
        ecu_group.setLayout(ecu_layout)
        layout.addWidget(ecu_group)

        # APP configuration group
        app_group = QtWidgets.QGroupBox("APP配置")
        app_layout = QtWidgets.QVBoxLayout()

        # Filter row
        filter_layout = QtWidgets.QHBoxLayout()
        filter_layout.addWidget(QtWidgets.QLabel("ECUID"))
        self.app_filter_ecu_combo = QtWidgets.QComboBox()
        self.app_filter_ecu_combo.setMinimumWidth(120)
        filter_layout.addWidget(self.app_filter_ecu_combo)

        filter_layout.addWidget(QtWidgets.QLabel("APPID"))
        self.app_filter_appid_combo = QtWidgets.QComboBox()
        self.app_filter_appid_combo.setMinimumWidth(120)
        filter_layout.addWidget(self.app_filter_appid_combo)

        filter_layout.addWidget(QtWidgets.QLabel("LOGLevel"))
        self.app_filter_loglevel_combo = QtWidgets.QComboBox()
        self.app_filter_loglevel_combo.setMinimumWidth(120)
        self.app_filter_loglevel_combo.addItems(["", "OFF", "FATAL", "ERROR", "WARN", "INFO", "DEBUG", "VERBOSE"])
        filter_layout.addWidget(self.app_filter_loglevel_combo)

        filter_layout.addStretch()

        self.app_search_btn = ModernButton("搜索", "#3B82F6", "🔍")
        filter_layout.addWidget(self.app_search_btn)
        self.app_refresh_btn = ModernButton("更新", "#0EA5E9", "🔄")
        filter_layout.addWidget(self.app_refresh_btn)

        app_layout.addLayout(filter_layout)

        # APP table
        self.app_table = QtWidgets.QTableWidget(0, 9)
        self.app_table.setHorizontalHeaderLabels([
            "", "序号", "APPID", "ECUID", "LOGLevel", "FileNo", "FileSize", "TotalSize(MB)", "操作"
        ])
        self.app_table.verticalHeader().setVisible(False)
        self.app_table.setAlternatingRowColors(True)
        self.app_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.app_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        # 设置表格默认行高
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

        app_layout.addWidget(self.app_table)

        # Bottom controls: pagination + page size + log operations
        bottom_layout = QtWidgets.QHBoxLayout()

        # Pagination controls
        self.prev_page_btn = ModernButton("上一页", "#6B7280", "←")
        bottom_layout.addWidget(self.prev_page_btn)
        self.page_info_label = QtWidgets.QLabel("第 1 / 1 页")
        bottom_layout.addWidget(self.page_info_label)
        self.next_page_btn = ModernButton("下一页", "#6B7280", "→")
        bottom_layout.addWidget(self.next_page_btn)

        bottom_layout.addStretch()

        # Page size selector
        page_size_layout = QtWidgets.QHBoxLayout()
        page_size_layout.addWidget(QtWidgets.QLabel("每页显示"))
        self.page_size_combo = QtWidgets.QComboBox()
        self.page_size_combo.addItems(["10", "20", "50"])
        page_size_layout.addWidget(self.page_size_combo)
        page_size_layout.addWidget(QtWidgets.QLabel("条"))
        bottom_layout.addLayout(page_size_layout)

        # Log operation buttons
        self.export_logs_btn = ModernButton("导出日志", "#10B981", "⬇")
        bottom_layout.addWidget(self.export_logs_btn)
        self.delete_selected_btn = ModernButton("删除选中", "#EF4444", "🗑")
        bottom_layout.addWidget(self.delete_selected_btn)
        self.refresh_logs_btn = ModernButton("刷新", "#0EA5E9", "🔄")
        bottom_layout.addWidget(self.refresh_logs_btn)

        app_layout.addLayout(bottom_layout)
        app_group.setLayout(app_layout)
        layout.addWidget(app_group)


        # Keep restore group as-is for now
        restore_group = QtWidgets.QGroupBox("恢复默认配置")
        restore_layout = QtWidgets.QHBoxLayout()
        restore_layout.setSpacing(15)
        self.restore_ccua = QtWidgets.QCheckBox("恢复CCUA默认")
        self.restore_ccu0 = QtWidgets.QCheckBox("恢复CCU0默认")
        self.restore_ccu1 = QtWidgets.QCheckBox("恢复CCU1默认")
        self.delete_logs = QtWidgets.QCheckBox("删除日志文件")
        for chk in [self.restore_ccua, self.restore_ccu0, self.restore_ccu1, self.delete_logs]:
            restore_layout.addWidget(chk)
        restore_layout.addStretch()
        self.restore_btn = ModernButton("执行恢复", "#EF4444", "⚠️")
        restore_layout.addWidget(self.restore_btn)
        restore_group.setLayout(restore_layout)
        layout.addWidget(restore_group)

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
            self.app_table.setCellWidget(i, 8, modify_btn)
