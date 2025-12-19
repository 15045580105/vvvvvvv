from PyQt5 import QtWidgets, QtCore
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QStandardItemModel, QStandardItem

from app.common.ui.widgets import ModernButton
from app.modules.did_management.view.did_management_view import FullCellDelegate, ComboBoxDelegate


# Mapping English service/operation names to Chinese display names used by the view.
NAME_CN = {
    "DiagnosticSessionControl": "诊断会话控制",
    "DefaultSession": "默认会话",
    "ProgrammingSession": "编程会话",
    "ExtendedDiagnosticSession": "扩展诊断会话",
    "EcuReset": "ECU复位",
    "HardReset": "硬复位",
    "KeyOffOnReset": "钥匙关开复位",
    "SoftReset": "软复位",
    "ClearDiagnosticInformation": "清除诊断信息",
    "ReadDTCInformation": "读取DTC信息",
    "ReportNumberOfDTCByStatusMask": "按状态掩码报告DTC数量",
    "ReportDTCByStatusMask": "按状态掩码报告DTC",
    "ReportDTCSnapshotRecordByDTCNumber": "按DTC编号报告快照记录",
    "ReportDTCExtDataRecordByDTCNumber": "按DTC编号报告扩展数据",
    "ReportSupportedDTC": "报告支持的DTC",
    "ReportNumberOfEmissionsRelatedOBDDTCByStatusMask": "按状态掩码报告排放相关DTC数量",
    "ReportEmissionsRelatedOBDDTCByStatusMask": "按状态掩码报告排放相关DTC",
    "ReadDataByIdentifier": "按标识读数据",
    "ReadMemoryByAddress": "按地址读内存",
    "SecurityAccess": "安全访问",
    "RequestSeedLevel1": "请求Seed等级1",
    "SendKeyLevel1": "发送Key等级1",
    "RequestSeedLevel2": "请求Seed等级2",
    "SendKeyLevel2": "发送Key等级2",
    "RequestReprogrammingSeed": "请求重编程Seed",
    "SendReprogrammingKey": "发送重编程Key",
    "CommunicationControl": "通信控制",
    "EnableRxAndTx": "启用接收与发送",
    "EnableRxAndDisableTx": "启用接收并禁用发送",
    "DisableRxAndEnableTx": "禁用接收并启用发送",
    "DisableRxAndTx": "禁用接收与发送",
    "ReadDataByPeriodicIdentifier": "按周期标识读数据",
    "DynamicallyDefineDataIdentifier": "动态定义数据标识符",
    "DefineByIdentifier": "按标识符定义",
    "ClearDynamicallyDefinedDataIdentifier": "清除动态定义的数据标识符",
    "WriteDataByIdentifier": "按标识写数据",
    "InputOutputControlByIdentifier": "按标识IO控制",
    "RoutineControl": "例程控制",
    "StartRoutine": "开始例程",
    "StopRoutine": "停止例程",
    "RequestRoutineResults": "请求例程结果",
    "RequestDownload": "请求下载",
    "RequestUpload": "请求上传",
    "TransferData": "传输数据",
    "RequestTransferExit": "请求传输结束",
    "RequestFileTransfer": "请求文件传输",
    "WriteMemoryByAddress": "按地址写内存",
    "TesterPresent": "测试器存在",
    "ControlDTCSetting": "DTC设置控制",
    "DTCSettingType ON": "DTC设置: 打开",
    "DTCSettingType OFF": "DTC设置: 关闭",
}


class CenteredCheckBoxDelegate(QtWidgets.QStyledItemDelegate):
    def paint(self, painter, option, index):
        # Draw standard background (selection, etc.)
        self.initStyleOption(option, index)
        style = option.widget.style() if option.widget else QtWidgets.QApplication.style()
        style.drawPrimitive(QtWidgets.QStyle.PE_PanelItemViewItem, option, painter, option.widget)

        # Get check state
        state = index.data(Qt.CheckStateRole)
        if state is None:
            return

        # Draw checkbox centered
        opt = QtWidgets.QStyleOptionButton()
        opt.state |= QtWidgets.QStyle.State_Enabled
        if state == Qt.Checked:
            opt.state |= QtWidgets.QStyle.State_On
        else:
            opt.state |= QtWidgets.QStyle.State_Off

        # Center logic
        indicator_width = style.pixelMetric(QtWidgets.QStyle.PM_IndicatorWidth)
        indicator_height = style.pixelMetric(QtWidgets.QStyle.PM_IndicatorHeight)
        rect = option.rect
        x = rect.x() + (rect.width() - indicator_width) // 2
        y = rect.y() + (rect.height() - indicator_height) // 2
        opt.rect = QtCore.QRect(x, y, indicator_width, indicator_height)

        style.drawPrimitive(QtWidgets.QStyle.PE_IndicatorCheckBox, opt, painter, option.widget)

    def editorEvent(self, event, model, option, index):
        # Handle click to toggle
        if event.type() == QtCore.QEvent.MouseButtonRelease:
            # Toggle
            state = index.data(Qt.CheckStateRole)
            new_state = Qt.Unchecked if state == Qt.Checked else Qt.Checked
            model.setData(index, new_state, Qt.CheckStateRole)
            return True
        return super().editorEvent(event, model, option, index)


class UDSSequenceView(QtWidgets.QWidget):
    send_requested = pyqtSignal(str)
    insert_requested = pyqtSignal(str)
    table_operation_requested = pyqtSignal(str)
    delay_insert_requested = pyqtSignal(str)
    send_batch_requested = pyqtSignal(int)
    run_sequence_requested = pyqtSignal(int)  # New signal for running the sequence
    config_save_requested = pyqtSignal(str)
    config_load_requested = pyqtSignal(str)
    config_delete_requested = pyqtSignal(str)
    config_import_requested = pyqtSignal()
    config_export_requested = pyqtSignal()
    add_command_requested = pyqtSignal(str)
    insert_command_requested = pyqtSignal(str)
    command_selected = pyqtSignal(str)

    def __init__(self, model, parent=None):
        super().__init__(parent)
        self.model = model
        self.current_edit_index = -1
        self.setWindowTitle("UDS指令编排")
        self.resize(900, 700)
        self.setup_ui()

    def setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Global style optimization
        self.setStyleSheet('''
            QWidget#uds_root { background: #FFFFFF; }
            QGroupBox { 
                background: #FFFFFF; 
                font-weight: bold;
                border: 1px solid #D1D5DB;
                border-radius: 6px;
                margin-top: 6px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px 0 3px;
            }
            QSplitter::handle { 
                background-color: #E5E7EB; 
                border: 1px solid #D1D5DB;
            }
            QSplitter::handle:horizontal {
                width: 4px;
            }
            QSplitter::handle:vertical {
                height: 4px;
            }
            QTreeView { 
                background: #FFFFFF; 
                border: 1px solid #9CA3AF; 
                border-radius: 4px;
            }
            QHeaderView::section { 
                background-color: #F3F4F6; 
                border: 1px solid #D1D5DB; 
                padding: 4px; 
                font-weight: bold; 
                color: #374151; 
            }
            QTableCornerButton::section { 
                background-color: #F3F4F6; 
                border: 1px solid #D1D5DB; 
            }
            /* Ensure the first column header looks the same */
            QHeaderView::section:first {
                background-color: #F3F4F6;
            }
        ''')
        try:
            self.setObjectName('uds_root')
        except Exception:
            pass

        # ... (rest of setup_ui logic remains similar but simplified for brevity in edit)

        main_splitter = QtWidgets.QSplitter()
        main_splitter.setOrientation(Qt.Vertical)
        main_splitter.setHandleWidth(4)

        cmd_group = QtWidgets.QGroupBox("UDS服务序列")
        cmd_layout = QtWidgets.QHBoxLayout(cmd_group)
        cmd_layout.setSpacing(0)
        cmd_layout.setContentsMargins(4, 12, 4, 4)

        cmd_splitter = QtWidgets.QSplitter()
        cmd_splitter.setOrientation(Qt.Horizontal)
        cmd_splitter.setHandleWidth(4)

        # left side: tree view
        self.cmd_tree = QtWidgets.QTreeView()
        self._build_tree_model()
        self.cmd_tree.clicked.connect(self._on_tree_item_clicked)
        self.cmd_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.cmd_tree.customContextMenuRequested.connect(self._on_tree_context_menu)
        cmd_splitter.addWidget(self.cmd_tree)

        self.editor_widget = self.create_editor_widget()
        cmd_splitter.addWidget(self.editor_widget)

        cmd_splitter.setStretchFactor(0, 1)
        cmd_splitter.setStretchFactor(1, 3)
        cmd_splitter.setSizes([250, 650])

        cmd_layout.addWidget(cmd_splitter)
        main_splitter.addWidget(cmd_group)

        log_group = QtWidgets.QGroupBox("执行日志")
        log_layout = QtWidgets.QVBoxLayout(log_group)
        log_layout.setContentsMargins(4, 12, 4, 4)

        self.exec_log = QtWidgets.QTextEdit()
        self.exec_log.setReadOnly(True)
        self.exec_log.setPlaceholderText("UDS指令执行日志将在这里显示...\n包含发送数据、响应数据、时间戳")
        self.exec_log.setStyleSheet("border: 1px solid #E5E7EB; border-radius: 4px;")
        log_layout.addWidget(self.exec_log)

        main_splitter.addWidget(log_group)

        main_splitter.setStretchFactor(0, 3)
        main_splitter.setStretchFactor(1, 1)

        layout.addWidget(main_splitter)

        self.clear_editor()

    def _build_tree_model(self):
        # ...existing code...
        tree = QStandardItemModel()
        root_item = QStandardItem("CustomRequest")
        root_item.setEditable(False)
        tree.appendRow(root_item)

        def add_children(parent_qitem, nodes, parent_code=None):
            for n in nodes:
                # show English name and append Chinese in parentheses when available
                eng_name = n.get('name') or ''
                cn = NAME_CN.get(eng_name)
                if cn:
                    label = f"{n.get('code')} {eng_name} ({cn})"
                else:
                    label = f"{n.get('code')} {eng_name}"
                item = QStandardItem(label)
                item.setEditable(False)
                full_code = n.get('code') if not parent_code else f"{parent_code}.{n.get('code')}"
                item.setData(full_code, Qt.UserRole)
                parent_qitem.appendRow(item)
                add_children(item, n.get('children', []), full_code)

        try:
            tree_data = self.model.get_tree_data()
        except Exception:
            tree_data = []

        add_children(root_item, tree_data)
        self.cmd_tree.setModel(tree)
        self.cmd_tree.expandAll()
        self.cmd_tree.header().setVisible(False)

    def refresh_tree(self):
        """Public: rebuild the tree from the model's current data."""
        self._build_tree_model()

    def _on_tree_item_clicked(self, index):
        # directly read stored code from the model index to avoid itemFromIndex static warnings
        code = index.data(Qt.UserRole)
        if code:
            self.command_selected.emit(code)

    def _on_tree_context_menu(self, pos):
        index = self.cmd_tree.indexAt(pos)
        if not index.isValid():
            return

        code = index.data(Qt.UserRole)
        if not code:
            return

        menu = QtWidgets.QMenu(self)

        action_add = menu.addAction("添加到末尾")
        action_add.triggered.connect(lambda: self.add_command_requested.emit(code))

        action_insert = menu.addAction("插入到选中位置")
        action_insert.triggered.connect(lambda: self.insert_command_requested.emit(code))

        menu.exec_(self.cmd_tree.viewport().mapToGlobal(pos))

    def _on_table_context_menu(self, pos):
        item = self.data_table.itemAt(pos)
        # Show menu even if no item is clicked (for "Check All" etc.)

        menu = QtWidgets.QMenu(self)

        act_check_all = menu.addAction("勾选全部")
        act_check_all.triggered.connect(lambda _: self._set_all_check_state(Qt.Checked))

        act_uncheck_all = menu.addAction("取消勾选全部")
        act_uncheck_all.triggered.connect(lambda _: self._set_all_check_state(Qt.Unchecked))

        menu.addSeparator()

        act_check_sel = menu.addAction("勾选选择")
        act_check_sel.triggered.connect(lambda _: self._set_selected_check_state(Qt.Checked))

        act_uncheck_sel = menu.addAction("取消勾选选择")
        act_uncheck_sel.triggered.connect(lambda _: self._set_selected_check_state(Qt.Unchecked))

        menu.addSeparator()

        act_del_sel = menu.addAction("删除选中")
        act_del_sel.triggered.connect(lambda _: self.delete_selected_rows())

        act_del_all = menu.addAction("删除所有")
        act_del_all.triggered.connect(self.reset_table)

        menu.exec_(self.data_table.viewport().mapToGlobal(pos))

    def _set_all_check_state(self, state):
        for row in range(self.data_table.rowCount()):
            item = self.data_table.item(row, 0)
            if item:
                item.setData(Qt.CheckStateRole, state)

    def _set_selected_check_state(self, state):
        selected_rows = set()
        for item in self.data_table.selectedItems():
            selected_rows.add(item.row())

        for row in selected_rows:
            item = self.data_table.item(row, 0)
            if item:
                item.setData(Qt.CheckStateRole, state)

    def delete_selected_rows(self):
        """Delete selected rows safely."""
        try:
            selected = self.data_table.selectedItems()
            rows = set()
            if selected:
                rows = set(item.row() for item in selected)

            # If no selection (or empty), try current row
            if not rows:
                current = self.data_table.currentRow()
                if current >= 0:
                    rows.add(current)

            # Sort reverse to delete from bottom up
            for row in sorted(list(rows), reverse=True):
                self.data_table.removeRow(row)

        except Exception as e:
            print(f"Error deleting rows: {e}")

    def create_editor_widget(self):
        editor = QtWidgets.QWidget()
        try:
            editor.setStyleSheet('background: #FFFFFF;')
        except Exception:
            pass
        layout = QtWidgets.QVBoxLayout(editor)
        layout.setSpacing(8)
        layout.setContentsMargins(8, 0, 0, 0)

        # Request Row
        req_row_layout = QtWidgets.QHBoxLayout()
        req_label = QtWidgets.QLabel("Request:")
        req_label.setStyleSheet("font-weight: 600; color: #374151;")
        req_label.setFixedWidth(70)

        self.request_edit = QtWidgets.QTextEdit()
        self.request_edit.setPlaceholderText("输入请求数据，如: 10 03")
        self.request_edit.setMaximumHeight(50)
        self.request_edit.setStyleSheet("border: 1px solid #D1D5DB; border-radius: 4px;")

        self.send_btn = ModernButton("发送", "#059669")
        self.send_btn.clicked.connect(self._on_send_clicked_internal)
        self.send_btn.setFixedWidth(80)
        self.send_btn.setFixedHeight(50)

        req_row_layout.addWidget(req_label)
        req_row_layout.addWidget(self.request_edit)
        req_row_layout.addWidget(self.send_btn)

        # Response Row
        resp_row_layout = QtWidgets.QHBoxLayout()
        resp_label = QtWidgets.QLabel("Response:")
        resp_label.setStyleSheet("font-weight: 600; color: #374151;")
        resp_label.setFixedWidth(70)

        self.response_edit = QtWidgets.QTextEdit()
        self.response_edit.setPlaceholderText("预期响应数据，如: 50 03")
        self.response_edit.setMaximumHeight(50)
        self.response_edit.setStyleSheet("border: 1px solid #D1D5DB; border-radius: 4px;")

        self.insert_btn = ModernButton("插入", "#3B82F6")
        self.insert_btn.clicked.connect(self._on_insert_clicked_internal)
        self.insert_btn.setFixedWidth(80)
        self.insert_btn.setFixedHeight(50)

        resp_row_layout.addWidget(resp_label)
        resp_row_layout.addWidget(self.response_edit)
        resp_row_layout.addWidget(self.insert_btn)

        # Toolbar Row (Config + Operations + Run)
        btn_row_layout = QtWidgets.QHBoxLayout()
        btn_row_layout.setSpacing(6)
        btn_row_layout.setContentsMargins(0, 6, 0, 6)
        btn_row_layout.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        # --- Config Section ---
        self.config_combo = QtWidgets.QComboBox()
        self.config_combo.setEditable(False)
        self.config_combo.setMinimumWidth(120)
        self.config_combo.setFixedHeight(32)
        self.config_combo.currentTextChanged.connect(lambda text: self.config_load_requested.emit(text) if text else None)

        self.save_config_btn = ModernButton("保存", "#3B82F6")
        self.save_config_btn.setFixedWidth(60)
        self.save_config_btn.setFixedHeight(32)
        self.save_config_btn.clicked.connect(self._on_save_config_clicked)

        self.del_config_btn = ModernButton("删除", "#EF4444")
        self.del_config_btn.setFixedWidth(60)
        self.del_config_btn.setFixedHeight(32)
        self.del_config_btn.clicked.connect(self._on_del_config_clicked)

        self.import_config_btn = ModernButton("导入", "#10B981")
        self.import_config_btn.setFixedWidth(60)
        self.import_config_btn.setFixedHeight(32)
        self.import_config_btn.clicked.connect(self.config_import_requested.emit)

        self.export_config_btn = ModernButton("导出", "#8B5CF6")
        self.export_config_btn.setFixedWidth(60)
        self.export_config_btn.setFixedHeight(32)
        self.export_config_btn.clicked.connect(self.config_export_requested.emit)

        btn_row_layout.addWidget(self.config_combo)
        btn_row_layout.addWidget(self.save_config_btn)
        btn_row_layout.addWidget(self.del_config_btn)
        btn_row_layout.addWidget(self.import_config_btn)
        btn_row_layout.addWidget(self.export_config_btn)

        # Separator
        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.VLine)
        line.setFrameShadow(QtWidgets.QFrame.Sunken)
        line.setStyleSheet("color: #E5E7EB;")
        btn_row_layout.addWidget(line)

        # --- Operation Buttons ---
        self.icon_btn_add = self.create_icon_button("➕", "添加参数", "#10B981", "添加")
        self.icon_btn_delete = self.create_icon_button("➖", "删除选中参数", "#EF4444", "删除")
        self.icon_btn_up = self.create_icon_button("↑", "上移", "#0EA5E9", "上移")
        self.icon_btn_down = self.create_icon_button("↓", "下移", "#0EA5E9", "下移")

        # styled icon button similar to create_icon_button
        def create_styled_button(icon_text: str, tooltip: str, color: str) -> QtWidgets.QPushButton:
            btn = QtWidgets.QPushButton(icon_text)
            btn.setToolTip(tooltip)
            # minimal padding so text/icon is centered in fixedSize
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {color};
                    color: white;
                    border: none;
                    border-radius: 6px;
                    padding: 0px;
                    font-size: 14px;
                    min-width: 32px;
                    min-height: 32px;
                }}
                QPushButton:hover {{
                    background-color: {self.adjust_color(color, -10)};
                }}
                QPushButton:pressed {{
                    background-color: {self.adjust_color(color, -20)};
                }}
            """)
            btn.setFixedSize(32, 32)
            return btn

        delay_color = "#F59E0B"
        self.delay_icon_btn = create_styled_button("⏱", "插入延迟指令 (默认 1000 ms)", delay_color)
        self.delay_icon_btn.clicked.connect(lambda: self.delay_insert_requested.emit('1000'))

        for b in (self.icon_btn_add, self.icon_btn_delete, self.delay_icon_btn, self.icon_btn_up, self.icon_btn_down):
            btn_row_layout.addWidget(b, 0, Qt.AlignVCenter)

        # Separator 2
        line2 = QtWidgets.QFrame()
        line2.setFrameShape(QtWidgets.QFrame.VLine)
        line2.setFrameShadow(QtWidgets.QFrame.Sunken)
        line2.setStyleSheet("color: #E5E7EB;")
        btn_row_layout.addWidget(line2)

        # 3E Toggle
        self.btn_3e = QtWidgets.QPushButton("💓")
        self.btn_3e.setCheckable(True)
        self.btn_3e.setToolTip("Tester Present: 3E 80 (点击切换 3E 00)")
        self.btn_3e.setFixedSize(32, 32)
        self._apply_toggle_style(self.btn_3e, "#6366F1") # Indigo
        btn_row_layout.addWidget(self.btn_3e)

        # Stop on Fail Toggle
        self.btn_stop_fail = QtWidgets.QPushButton("🛑")
        self.btn_stop_fail.setCheckable(True)
        self.btn_stop_fail.setToolTip("遇错停止: 选中后遇到错误将停止执行")
        self.btn_stop_fail.setFixedSize(32, 32)
        self.btn_stop_fail.setChecked(True)
        self._apply_toggle_style(self.btn_stop_fail, "#EF4444") # Red
        btn_row_layout.addWidget(self.btn_stop_fail)

        btn_row_layout.addStretch()

        # --- Run Section ---
        self.send_times_label = QtWidgets.QLabel("次数:")
        self.send_times_label.setStyleSheet("color: #374151; font-weight: 600;")

        self.send_times_spin = QtWidgets.QSpinBox()
        self.send_times_spin.setRange(1, 9999)
        self.send_times_spin.setValue(1)
        self.send_times_spin.setFixedWidth(60)
        self.send_times_spin.setFixedHeight(32)

        self.run_sequence_btn = ModernButton("执行序列", "#8B5CF6")
        self.run_sequence_btn.setFixedHeight(32)
        self.run_sequence_btn.setFixedWidth(90)
        self.run_sequence_btn.clicked.connect(lambda: self.run_sequence_requested.emit(self.send_times_spin.value()))

        btn_row_layout.addWidget(self.send_times_label)
        btn_row_layout.addWidget(self.send_times_spin)
        btn_row_layout.addWidget(self.run_sequence_btn)

        # Wrap the button row into a fixed-height toolbar widget
        toolbar_widget = QtWidgets.QWidget()
        toolbar_widget.setLayout(btn_row_layout)
        toolbar_widget.setFixedHeight(44)

        self.data_table = QtWidgets.QTableWidget()
        self.setup_table()
        # self.data_table.setMinimumHeight(200)

        layout.addLayout(req_row_layout)
        layout.addLayout(resp_row_layout)
        layout.addWidget(toolbar_widget)
        layout.addWidget(self.data_table)

        return editor

    def create_icon_button(self, icon_text, tooltip, color, operation):
        btn = QtWidgets.QPushButton(icon_text)
        btn.setToolTip(tooltip)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {color};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 0px;
                font-size: 14px;
                min-width: 32px;
                min-height: 32px;
            }}
            QPushButton:hover {{
                background-color: {self.adjust_color(color, -10)};
            }}
            QPushButton:pressed {{
                background-color: {self.adjust_color(color, -20)};
            }}
        """)
        btn.setFixedSize(32, 32)
        btn.clicked.connect(lambda checked, op=operation: self.table_operation_requested.emit(op))
        return btn

    def adjust_color(self, color, amount):
        hex_color = color.lstrip('#')
        r = max(0, min(255, int(hex_color[0:2], 16) + amount))
        g = max(0, min(255, int(hex_color[2:4], 16) + amount))
        b = max(0, min(255, int(hex_color[4:6], 16) + amount))
        return f"#{r:02X}{g:02X}{b:02X}"

    def setup_table(self):
        # Table layout: checkbox, Name, Request, AddrType (combo), Response
        self.data_table.setColumnCount(5)
        self.data_table.setHorizontalHeaderLabels(["", "Name", "Request", "AddrType", "Response"])
        header = self.data_table.horizontalHeader()

        # Allow user to resize columns
        header.setSectionResizeMode(QtWidgets.QHeaderView.Interactive)
        header.setStretchLastSection(True)

        header.setSectionsClickable(True)
        header.setHighlightSections(True)
        header.setSectionsMovable(True)  # Enable draggable columns

        self.data_table.setAlternatingRowColors(True)
        self.data_table.setSelectionBehavior(QtWidgets.QTableWidget.SelectRows)
        self.data_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.data_table.customContextMenuRequested.connect(self._on_table_context_menu)
        # show vertical header so rows are numbered (like the screenshot)
        self.data_table.verticalHeader().setVisible(True)
        # set default row height similar to DID
        try:
            self.data_table.verticalHeader().setDefaultSectionSize(42)
        except Exception:
            pass

        # Use delegates from DID view for full-cell editing and combo box for AddrType
        self._full_delegate = FullCellDelegate(self.data_table)
        self._addrtype_delegate = ComboBoxDelegate(items_provider=lambda idx: ["physical", "functional"], parent=self.data_table)
        self._checkbox_delegate = CenteredCheckBoxDelegate(self.data_table)

        # assign delegates to columns: Checkbox(0), Name(1), Request(2), AddrType(3), Response(4)
        self.data_table.setItemDelegateForColumn(0, self._checkbox_delegate)
        self.data_table.setItemDelegateForColumn(1, self._full_delegate)
        self.data_table.setItemDelegateForColumn(2, self._full_delegate)
        self.data_table.setItemDelegateForColumn(3, self._addrtype_delegate)
        self.data_table.setItemDelegateForColumn(4, self._full_delegate)
        # allow editing by double click (consistent with DID behavior that uses controller to open editors)
        self.data_table.setEditTriggers(QtWidgets.QAbstractItemView.DoubleClicked)

        # ensure vertical header shows row numbers and a comfortable width
        try:
            vh = self.data_table.verticalHeader()
            vh.setDefaultSectionSize(42)  # Increased row height
            vh.setVisible(True)
            vh.setFixedWidth(36)
            vh.setSectionResizeMode(QtWidgets.QHeaderView.Fixed)
        except Exception:
            pass

        # style header sections, corner and viewport so left strip and header look white like screenshot
        self.data_table.setStyleSheet("""
            QTableWidget {
                background-color: #FFFFFF;
                border: 1px solid #D1D5DB;
                border-radius: 6px;
                font-size: 9pt;
            }
            QHeaderView::section { background-color: #F3F4F6; border: 1px solid #D1D5DB; padding: 6px; font-weight: bold; color: #374151; }
            QTableCornerButton::section { background-color: #F3F4F6; border: 1px solid #D1D5DB; }
            QTableWidget::item { padding: 6px; }
        """)
        try:
            # also ensure the viewport background is white
            self.data_table.viewport().setStyleSheet('background: #FFFFFF;')
        except Exception:
            pass

        # Set initial column widths
        self.data_table.setColumnWidth(0, 40)   # Checkbox - slightly narrower
        self.data_table.setColumnWidth(1, 350)  # Name
        self.data_table.setColumnWidth(2, 150)  # Request
        self.data_table.setColumnWidth(3, 100)  # AddrType
        # Last column (Response) will stretch

    def _apply_column_widths(self, force: bool = False):
        # Deprecated: we use Interactive mode now
        pass

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # No longer forcing column widths on resize


    # --- View API for controller ---
    def clear_editor(self):
        self.request_edit.clear()
        self.response_edit.clear()
        self.data_table.setRowCount(0)
        self.request_edit.setEnabled(False)
        self.response_edit.setEnabled(False)
        self.send_btn.setEnabled(False)
        self.insert_btn.setEnabled(False)
        self.current_edit_index = -1

    def set_editor_enabled(self, enabled: bool):
        self.request_edit.setEnabled(enabled)
        self.response_edit.setEnabled(enabled)
        self.send_btn.setEnabled(enabled)
        self.insert_btn.setEnabled(enabled)

    def set_placeholders(self, command: str):
        self.request_edit.setPlaceholderText(f"配置 {command} 的请求...")
        self.response_edit.setPlaceholderText(f"配置 {command} 的响应...")

    def reset_table(self):
        self.data_table.setRowCount(0)

    def append_table_row(self, param_name: str, param_value: str, description: str):
        """Append a row to the table.

        Backwards-compatible API: older calls used (param_name, param_value, description).
        New table has 5 columns: checkbox, Name, Request, AddrType, Response.
        If called with 3 args, map them as Name=param_name, Request=param_value, Response=description, AddrType defaults to 'physical'.
        New callers can pass keyword args or call with 5 args via a tuple: append_table_row(name, request, addrtype, response, checked=True)
        """
        row = self.data_table.rowCount()
        self.data_table.insertRow(row)

        # Determine mapping based on types/values
        # If description looks like addr/desc we treat as response
        name = param_name
        request = param_value
        addrtype = 'physical'
        response = description

        # first column: use QTableWidgetItem with CheckStateRole, rendered by CenteredCheckBoxDelegate
        chk_item = QtWidgets.QTableWidgetItem()
        chk_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
        chk_item.setData(Qt.CheckStateRole, Qt.Checked)
        self.data_table.setItem(row, 0, chk_item)

        # Name
        self.data_table.setItem(row, 1, QtWidgets.QTableWidgetItem(name))
        # Request
        self.data_table.setItem(row, 2, QtWidgets.QTableWidgetItem(request))
        # AddrType default
        self.data_table.setItem(row, 3, QtWidgets.QTableWidgetItem(addrtype))
        # Response
        self.data_table.setItem(row, 4, QtWidgets.QTableWidgetItem(response))
        # After adding a row, ensure column widths remain proportional
        try:
            self._apply_column_widths()
        except Exception:
            pass

    def remove_table_row(self, row: int):
        if 0 <= row < self.data_table.rowCount():
            self.data_table.removeRow(row)

    def get_current_row(self) -> int:
        return self.data_table.currentRow()

    def swap_table_rows(self, row1: int, row2: int):
        cols = self.data_table.columnCount()
        for col in range(cols):
            # Swap QTableWidgetItem for all columns (including checkbox column 0)
            item1 = self.data_table.takeItem(row1, col)
            item2 = self.data_table.takeItem(row2, col)
            self.data_table.setItem(row1, col, item2)
            self.data_table.setItem(row2, col, item1)

    def get_request_text(self) -> str:
        return self.request_edit.toPlainText().strip()

    def get_response_text(self) -> str:
        return self.response_edit.toPlainText().strip()

    def log_message(self, message: str):
        self.exec_log.append(message)

    # --- Internal slots to emit signals ---
    def _on_send_clicked_internal(self):
        self.send_requested.emit(self.get_request_text())

    def _on_insert_clicked_internal(self):
        self.insert_requested.emit(self.get_response_text())

    def _on_save_config_clicked(self):
        current_name = self.config_combo.currentText()
        name, ok = QtWidgets.QInputDialog.getText(self, "保存配置", "请输入配置名称:", text=current_name)
        if ok and name:
            self.config_save_requested.emit(name)

    def _on_del_config_clicked(self):
        current = self.config_combo.currentText()
        if current and current != "默认":
            reply = QtWidgets.QMessageBox.question(self, "确认删除", f"确定要删除配置 '{current}' 吗?",
                                                 QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
            if reply == QtWidgets.QMessageBox.Yes:
                self.config_delete_requested.emit(current)

    def get_table_data(self):
        """Return list of dicts representing the table rows."""
        data = []
        for row in range(self.data_table.rowCount()):
            # Checkbox
            chk_item = self.data_table.item(row, 0)
            checked = True
            if chk_item:
                checked = (chk_item.data(Qt.CheckStateRole) == Qt.Checked)

            name = self.data_table.item(row, 1).text() if self.data_table.item(row, 1) else ""
            request = self.data_table.item(row, 2).text() if self.data_table.item(row, 2) else ""
            addrtype = self.data_table.item(row, 3).text() if self.data_table.item(row, 3) else "physical"
            response = self.data_table.item(row, 4).text() if self.data_table.item(row, 4) else ""

            data.append({
                "checked": checked,
                "name": name,
                "request": request,
                "addrtype": addrtype,
                "response": response
            })
        return data

    def set_table_data(self, data):
        """Populate table from list of dicts."""
        self.data_table.setRowCount(0)
        if not data or not isinstance(data, list):
            return
        for item in data:
            if not isinstance(item, dict):
                continue
            self.append_table_row(item.get("name", ""), item.get("request", ""), item.get("response", ""))
            # Update addrtype and checked state
            row = self.data_table.rowCount() - 1

            # AddrType
            self.data_table.setItem(row, 3, QtWidgets.QTableWidgetItem(item.get("addrtype", "physical")))

            # Checked
            chk_item = self.data_table.item(row, 0)
            if chk_item:
                state = Qt.Checked if item.get("checked", True) else Qt.Unchecked
                chk_item.setData(Qt.CheckStateRole, state)

    def update_config_list(self, names, current=None):
        self.config_combo.blockSignals(True)
        self.config_combo.clear()
        # Ensure "默认" is first
        combo_items = ["默认"] + [n for n in names if n != "默认"]
        self.config_combo.addItems(combo_items)

        if current and current in combo_items:
            self.config_combo.setCurrentText(current)
        else:
            self.config_combo.setCurrentIndex(0)
        self.config_combo.blockSignals(False)

    def _update_3e_text(self, checked):
        self.btn_3e.setText("3E 00" if checked else "3E 80")

    def _apply_toggle_style(self, btn, active_color):
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #F3F4F6;
                color: #374151;
                border: 1px solid #D1D5DB;
                border-radius: 6px;
                font-weight: bold;
            }}
            QPushButton:checked {{
                background-color: {active_color};
                color: white;
                border: 2px solid {active_color};
            }}
            QPushButton:hover:!checked {{
                background-color: #E5E7EB;
            }}
        """)
