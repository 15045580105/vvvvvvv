import json
from datetime import datetime
from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QStandardItemModel, QStandardItem

from app.common.log.operation_log_manager import OperationLogManager
from app.common.ui.widgets import ModernButton
from app.common.ui.log_splitter import LogAreaSplitter
from app.common.ui.log_panel import LogPanelBuilder
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


class CheckBoxHeader(QtWidgets.QHeaderView):
    checkBoxClicked = QtCore.pyqtSignal(int, bool)

    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self.checkBoxStates = {0: False}

    def paintSection(self, painter, rect, logicalIndex):
        painter.save()
        super().paintSection(painter, rect, logicalIndex)
        painter.restore()

        if logicalIndex in self.checkBoxStates:
            style = self.style()
            option = QtWidgets.QStyleOptionViewItem()
            option.initFrom(self)

            chk_width = style.pixelMetric(QtWidgets.QStyle.PM_IndicatorWidth, option, self)
            chk_height = style.pixelMetric(QtWidgets.QStyle.PM_IndicatorHeight, option, self)

            x = rect.x() + (rect.width() - chk_width) // 2
            y = rect.y() + (rect.height() - chk_height) // 2

            option.rect = QtCore.QRect(x, y, chk_width, chk_height)
            option.state = QtWidgets.QStyle.State_Enabled | QtWidgets.QStyle.State_Active
            if self.checkBoxStates[logicalIndex]:
                option.state |= QtWidgets.QStyle.State_On
                option.checkState = Qt.Checked
            else:
                option.state |= QtWidgets.QStyle.State_Off
                option.checkState = Qt.Unchecked
            
            style.drawPrimitive(QtWidgets.QStyle.PE_IndicatorCheckBox, option, painter, self)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            logicalIndex = self.logicalIndexAt(event.pos())
            if logicalIndex in self.checkBoxStates:
                x = self.sectionViewportPosition(logicalIndex)
                y = 0
                sec_width = self.sectionSize(logicalIndex)
                sec_height = self.height()

                style = self.style()
                option = QtWidgets.QStyleOptionViewItem()
                option.initFrom(self)
                chk_width = style.pixelMetric(QtWidgets.QStyle.PM_IndicatorWidth, option, self)
                chk_height = style.pixelMetric(QtWidgets.QStyle.PM_IndicatorHeight, option, self)

                chk_x = x + (sec_width - chk_width) // 2
                chk_y = y + (sec_height - chk_height) // 2

                checkRect = QtCore.QRect(chk_x - 4, chk_y - 4, chk_width + 8, chk_height + 8)

                if checkRect.contains(event.pos()):
                    self.checkBoxStates[logicalIndex] = not self.checkBoxStates[logicalIndex]
                    self.viewport().update()
                    self.checkBoxClicked.emit(logicalIndex, self.checkBoxStates[logicalIndex])
                    return
        super().mousePressEvent(event)


class ExportConfigDialog(QtWidgets.QDialog):
    def __init__(self, config_names, parent=None):
        super().__init__(parent)
        self.setWindowTitle("导出配置")
        self.resize(400, 300)
        self.selected_configs = []
        self.export_path = ""
        self.setup_ui(config_names)

    def setup_ui(self, config_names):
        layout = QtWidgets.QVBoxLayout(self)

        # Config List
        layout.addWidget(QtWidgets.QLabel("选择要导出的配置:"))
        self.list_widget = QtWidgets.QListWidget()
        for name in config_names:
            item = QtWidgets.QListWidgetItem(name)
            item.setCheckState(Qt.Unchecked)
            self.list_widget.addItem(item)
        layout.addWidget(self.list_widget)

        # Select All / Deselect All
        btn_layout = QtWidgets.QHBoxLayout()
        btn_all = QtWidgets.QPushButton("全选")
        btn_all.clicked.connect(self.select_all)
        btn_none = QtWidgets.QPushButton("全不选")
        btn_none.clicked.connect(self.deselect_all)
        btn_layout.addWidget(btn_all)
        btn_layout.addWidget(btn_none)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # Export Path
        layout.addWidget(QtWidgets.QLabel("导出路径:"))
        path_layout = QtWidgets.QHBoxLayout()
        self.path_edit = QtWidgets.QLineEdit()
        self.path_btn = QtWidgets.QPushButton("浏览...")
        self.path_btn.clicked.connect(self.browse_folder)
        path_layout.addWidget(self.path_edit)
        path_layout.addWidget(self.path_btn)
        layout.addLayout(path_layout)

        # Dialog Buttons
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def select_all(self):
        for i in range(self.list_widget.count()):
            self.list_widget.item(i).setCheckState(Qt.Checked)

    def deselect_all(self):
        for i in range(self.list_widget.count()):
            self.list_widget.item(i).setCheckState(Qt.Unchecked)

    def browse_folder(self):
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "选择导出目录")
        if folder:
            self.path_edit.setText(folder)

    def validate_and_accept(self):
        self.selected_configs = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.checkState() == Qt.Checked:
                self.selected_configs.append(item.text())

        self.export_path = self.path_edit.text()

        if not self.selected_configs:
            QtWidgets.QMessageBox.warning(self, "提示", "请至少选择一个配置")
            return
        if not self.export_path:
            QtWidgets.QMessageBox.warning(self, "提示", "请选择导出路径")
            return

        self.accept()


class UDSSequenceView(QtWidgets.QWidget):
    send_requested = pyqtSignal(str)
    insert_requested = pyqtSignal(str)
    table_operation_requested = pyqtSignal(str)
    delay_insert_requested = pyqtSignal(str)
    send_batch_requested = pyqtSignal(int)
    send_single_requested = pyqtSignal(str)  # New signal for right-click send
    run_sequence_requested = pyqtSignal(int)  # New signal for running the sequence (-1 = infinite)
    stop_sequence_requested = pyqtSignal()      # Signal to stop running sequence
    config_save_requested = pyqtSignal(str)
    config_load_requested = pyqtSignal(str)
    config_delete_requested = pyqtSignal(str)
    config_import_requested = pyqtSignal()
    config_export_requested = pyqtSignal()
    add_command_requested = pyqtSignal(str)
    insert_command_requested = pyqtSignal(str)
    command_selected = pyqtSignal(str)
    table_data_changed = pyqtSignal()
    tp_toggled = pyqtSignal(bool)           # 3E 心跳启用/禁用
    tp_mode_changed = pyqtSignal(str)       # 3E 模式切换 ("00" / "80")

    def __init__(self, model, parent=None):
        super().__init__(parent)
        self.model = model
        self.current_edit_index = -1
        self._last_resize_bucket = None
        self._preferred_splitter_ratio = 0.20
        self._user_resized_splitter = False
        self.setWindowTitle("UDS指令编排")
        self.resize(900, 700)
        self.setup_ui()

    def setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        main_splitter = LogAreaSplitter(self, min_log_height=150, max_log_ratio=0.6)
        main_splitter.setOrientation(Qt.Vertical)
        main_splitter.setHandleWidth(4)

        cmd_group = QtWidgets.QGroupBox("UDS服务序列")
        cmd_layout = QtWidgets.QHBoxLayout(cmd_group)
        cmd_layout.setSpacing(0)
        cmd_layout.setContentsMargins(4, 12, 4, 4)

        self.cmd_splitter = QtWidgets.QSplitter()
        self.cmd_splitter.setOrientation(Qt.Horizontal)
        self.cmd_splitter.setHandleWidth(4)

        # left side: tree view
        self.cmd_tree = QtWidgets.QTreeView()
        self.cmd_tree.setMinimumWidth(180)
        self._build_tree_model()
        self.cmd_tree.clicked.connect(self._on_tree_item_clicked)
        self.cmd_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.cmd_tree.customContextMenuRequested.connect(self._on_tree_context_menu)
        self.cmd_splitter.addWidget(self.cmd_tree)

        self.editor_widget = self.create_editor_widget()
        self.editor_widget.setMinimumWidth(0)
        self.cmd_splitter.addWidget(self.editor_widget)

        self.cmd_splitter.setStretchFactor(0, 1)
        self.cmd_splitter.setStretchFactor(1, 4)
        self.cmd_splitter.setSizes([220, 980])
        self.cmd_splitter.setCollapsible(0, False)
        self.cmd_splitter.setCollapsible(1, False)
        self.cmd_splitter.splitterMoved.connect(self._on_splitter_moved)

        cmd_layout.addWidget(self.cmd_splitter)
        main_splitter.addWidget(cmd_group)

        log_group = QtWidgets.QGroupBox("操作日志")
        log_layout = QtWidgets.QVBoxLayout(log_group)
        log_layout.setContentsMargins(4, 12, 4, 4)

        self.exec_log = QtWidgets.QTextEdit()
        self.exec_log.setReadOnly(True)
        self.exec_log.setPlaceholderText("UDS指令执行日志将在这里显示...\n包含发送数据、响应数据、时间戳")
        self.exec_log.setStyleSheet("border: 1px solid #E5E7EB; border-radius: 4px;")
        LogPanelBuilder.attach_search(log_layout, self.exec_log)
        log_layout.addWidget(self.exec_log)

        main_splitter.set_panels(cmd_group, log_group, initial_log_height=230)

        layout.addWidget(main_splitter)

        self.clear_editor()
        QtCore.QTimer.singleShot(0, self._apply_responsive_layout)

    def format_hex_string(self, text: str) -> str:
        if not text:
            return text
        clean_text = ''.join(str(text).split())
        if clean_text and len(clean_text) % 2 == 0 and all(c in "0123456789ABCDEFabcdef" for c in clean_text):
            return ' '.join(clean_text[i:i+2] for i in range(0, len(clean_text), 2)).upper()
        return text

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

        # Add Send action
        action_send = menu.addAction("发送此指令")
        # Format code (e.g. 10.01 -> 10 01) and emit signal
        req_text = ' '.join(code.split('.'))
        action_send.triggered.connect(lambda: self.send_single_requested.emit(req_text))

        menu.addSeparator()

        action_add = menu.addAction("添加到末尾")
        action_add.triggered.connect(lambda: self.add_command_requested.emit(code))

        action_insert = menu.addAction("插入到选中位置")
        action_insert.triggered.connect(lambda: self.insert_command_requested.emit(code))

        menu.exec_(self.cmd_tree.viewport().mapToGlobal(pos))

    def _on_table_context_menu(self, pos):
        item = self.data_table.itemAt(pos)
        # Show menu even if no item is clicked (for "Check All" etc.)

        menu = QtWidgets.QMenu(self)

        # Add "Send" action if a row is selected or clicked
        if item:
            row = item.row()
            req_item = self.data_table.item(row, 2)
            if req_item:
                req_text = req_item.text()
                act_send = menu.addAction("发送此指令")
                act_send.triggered.connect(lambda: self.send_single_requested.emit(req_text))
                menu.addSeparator()

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

    def _on_header_checkbox_clicked(self, logicalIndex, state):
        if logicalIndex == 0:
            check_state = Qt.Checked if state else Qt.Unchecked
            self._set_all_check_state(check_state)

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
        editor.setMinimumWidth(0)
        editor.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        self.editor_layout = QtWidgets.QVBoxLayout(editor)
        self.editor_layout.setSpacing(8)
        self.editor_layout.setContentsMargins(8, 0, 0, 0)

        # Request Row
        self.req_row_layout = QtWidgets.QHBoxLayout()
        self.req_label = QtWidgets.QLabel("Request:")
        self.req_label.setStyleSheet("font-weight: 600; color: #374151;")
        self.req_label.setMinimumWidth(70)

        self.request_edit = QtWidgets.QTextEdit()
        original_req_setPlainText = self.request_edit.setPlainText
        def custom_req_setPlainText(text):
            original_req_setPlainText(self.format_hex_string(text))
        self.request_edit.setPlainText = custom_req_setPlainText
        self.request_edit.setPlaceholderText("输入请求数据，如: 10 03")
        self.request_edit.setMaximumHeight(50)
        self.request_edit.setMinimumHeight(50)
        self.request_edit.setMinimumWidth(260)
        self.request_edit.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.request_edit.setStyleSheet("border: 1px solid #D1D5DB; border-radius: 4px;")

        self.send_btn = ModernButton("发送", "#059669")
        self.send_btn.setToolTip("发送请求数据")
        self.send_btn.clicked.connect(self._on_send_clicked_internal)
        self.send_btn.setMinimumWidth(80)
        self.send_btn.setFixedHeight(50)
        self.send_btn.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)

        self.req_row_layout.addWidget(self.req_label)
        self.req_row_layout.addWidget(self.request_edit, 1)
        self.req_row_layout.addWidget(self.send_btn, 0)

        # Response Row
        self.resp_row_layout = QtWidgets.QHBoxLayout()
        self.resp_label = QtWidgets.QLabel("Response:")
        self.resp_label.setStyleSheet("font-weight: 600; color: #374151;")
        self.resp_label.setMinimumWidth(70)

        self.response_edit = QtWidgets.QTextEdit()
        original_res_setPlainText = self.response_edit.setPlainText
        def custom_res_setPlainText(text):
            original_res_setPlainText(self.format_hex_string(text))
        self.response_edit.setPlainText = custom_res_setPlainText
        self.response_edit.setPlaceholderText("预期响应数据，如: 50 03")
        self.response_edit.setMaximumHeight(50)
        self.response_edit.setMinimumHeight(50)
        self.response_edit.setMinimumWidth(260)
        self.response_edit.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.response_edit.setStyleSheet("border: 1px solid #D1D5DB; border-radius: 4px;")

        self.insert_btn = ModernButton("插入", "#3B82F6")
        self.insert_btn.setToolTip("将响应数据插入到下方表格")
        self.insert_btn.clicked.connect(self._on_insert_clicked_internal)
        self.insert_btn.setMinimumWidth(80)
        self.insert_btn.setFixedHeight(50)
        self.insert_btn.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)

        self.resp_row_layout.addWidget(self.resp_label)
        self.resp_row_layout.addWidget(self.response_edit, 1)
        self.resp_row_layout.addWidget(self.insert_btn, 0)

        # Toolbar Row (two-line layout to avoid squeezing)
        self.toolbar_widget = QtWidgets.QWidget()
        self.toolbar_widget.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.toolbar_widget.setStyleSheet(
            "QWidget { background-color: #FAFBFC; border: 1px solid #E5E7EB; border-radius: 6px; }"
        )
        self.toolbar_layout = QtWidgets.QVBoxLayout(self.toolbar_widget)
        self.toolbar_layout.setContentsMargins(10, 6, 10, 6)
        self.toolbar_layout.setSpacing(6)

        # --- Row 1: Template Management ---
        self.toolbar_row1 = QtWidgets.QHBoxLayout()
        self.toolbar_row1.setSpacing(6)

        # --- Row 2: Single Template Operations ---
        self.toolbar_row2 = QtWidgets.QHBoxLayout()
        self.toolbar_row2.setSpacing(4)

        # --- Config Section (no GroupBox, use label to avoid extra padding) ---
        self.config_group = QtWidgets.QWidget()
        self.config_group.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.config_group_layout = QtWidgets.QHBoxLayout(self.config_group)
        self.config_group_layout.setContentsMargins(0, 0, 0, 0)
        self.config_group_layout.setSpacing(4)

        config_label = QtWidgets.QLabel("模板:")
        config_label.setStyleSheet("color: #4B5563; font-weight: 600; font-size: 11px;")
        config_label.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.config_group_layout.addWidget(config_label, 0)

        self.config_combo = QtWidgets.QComboBox()
        self.config_combo.setEditable(False)
        self.config_combo.setMinimumWidth(96)
        self.config_combo.setMaximumWidth(180)
        self.config_combo.setFixedHeight(32)
        self.config_combo.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.config_combo.currentTextChanged.connect(lambda text: self.config_load_requested.emit(text) if text else None)

        self.save_config_btn = ModernButton("保存", "#3B82F6")
        self.save_config_btn.setToolTip("保存当前的指令序列为配置模板")
        self.save_config_btn.setMinimumWidth(60)
        self.save_config_btn.setFixedHeight(32)
        self.save_config_btn.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.save_config_btn.clicked.connect(self._on_save_config_clicked)

        self.del_config_btn = ModernButton("删除", "#EF4444")
        self.del_config_btn.setToolTip("删除当前选中的配置模板 (不影响下方表格内容)")
        self.del_config_btn.setMinimumWidth(60)
        self.del_config_btn.setFixedHeight(32)
        self.del_config_btn.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.del_config_btn.clicked.connect(self._on_del_config_clicked)

        self.import_config_btn = ModernButton("导入", "#10B981")
        self.import_config_btn.setToolTip("导入外部配置文件")
        self.import_config_btn.setMinimumWidth(60)
        self.import_config_btn.setFixedHeight(32)
        self.import_config_btn.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.import_config_btn.clicked.connect(self.config_import_requested.emit)

        self.export_config_btn = ModernButton("导出", "#8B5CF6")
        self.export_config_btn.setToolTip("导出配置到文件")
        self.export_config_btn.setMinimumWidth(60)

        self.export_config_btn.setFixedHeight(32)
        self.export_config_btn.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.export_config_btn.clicked.connect(self.config_export_requested.emit)

        self.config_group_layout.addWidget(self.config_combo, 0)
        self.config_group_layout.addWidget(self.save_config_btn, 0)
        self.config_group_layout.addWidget(self.del_config_btn, 0)
        self.config_group_layout.addWidget(self.import_config_btn, 0)
        self.config_group_layout.addWidget(self.export_config_btn, 0)

        self.toolbar_row1.addWidget(self.config_group, 0)
        self.toolbar_row1.addStretch(1)

        # Separator line between Row 1 and Row 2
        h_sep = QtWidgets.QFrame()
        h_sep.setFrameShape(QtWidgets.QFrame.HLine)
        h_sep.setStyleSheet("color: #E5E7EB;")
        h_sep.setFixedHeight(1)

        # --- Operation Buttons ---
        self.icon_btn_add = self.create_icon_button("➕", "添加参数", "#10B981", "添加")
        self.icon_btn_delete = self.create_icon_button("➖", "删除选中参数", "#EF4444", "删除")
        self.icon_btn_up = self.create_icon_button("↑", "上移", "#0EA5E9", "上移")
        self.icon_btn_down = self.create_icon_button("↓", "下移", "#0EA5E9", "上移")

        def create_styled_button(icon_text: str, tooltip: str, color: str) -> QtWidgets.QPushButton:
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
                QToolTip {{
                    background-color: #1F2937;
                    color: white;
                    border: 1px solid #1F2937;
                    border-radius: 4px;
                    padding: 4px;
                    opacity: 230;
                }}
            """)
            btn.setFixedSize(32, 32)
            btn.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
            return btn

        delay_color = "#F59E0B"
        self.delay_icon_btn = create_styled_button("⏱", "插入延迟指令 (默认 1000 ms)", delay_color)
        self.delay_icon_btn.clicked.connect(lambda: self.delay_insert_requested.emit('1000'))

        self.btn_3e = QtWidgets.QPushButton("3E")
        self.btn_3e.setCheckable(True)
        self.btn_3e.setToolTip("TesterPresent 心跳开关 (按 S3/2 间隔自动发送)")
        self.btn_3e.setFixedSize(40, 32)
        self.btn_3e.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self._apply_toggle_style(self.btn_3e, "#6366F1")
        self.btn_3e.toggled.connect(self._on_3e_toggled)

        # 3E 模式下拉框：独立选择 3E 80（抑制正响应）或 3E 00（正常响应）
        self.combo_3e_mode = QtWidgets.QComboBox()
        self.combo_3e_mode.addItems(["3E 80", "3E 00"])
        self.combo_3e_mode.setToolTip(
            "TesterPresent 模式:\n"
            "• 3E 80 = 抑制正响应 (SuppressPosRspMsg), 适合高频心跳, 无需等待响应\n"
            "• 3E 00 = 正常请求, ECU 返回 7E 00 正响应"
        )
        self.combo_3e_mode.setFixedHeight(32)
        self.combo_3e_mode.setFixedWidth(80)
        self.combo_3e_mode.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.combo_3e_mode.setStyleSheet(
            "QComboBox { border: 1px solid #D1D5DB; border-radius: 4px; padding: 2px 4px; }"
        )
        self.combo_3e_mode.currentTextChanged.connect(self._on_3e_mode_changed)

        self.btn_stop_fail = QtWidgets.QPushButton("⚠")
        self.btn_stop_fail.setCheckable(True)
        self.btn_stop_fail.setToolTip("遇错停止: 选中后遇到错误将停止执行")
        self.btn_stop_fail.setFixedSize(40, 32)
        self.btn_stop_fail.setChecked(True)
        self.btn_stop_fail.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self._apply_toggle_style(self.btn_stop_fail, "#EF4444")

        # --- Execution Controls ---
        self.send_times_label = QtWidgets.QLabel("次数:")
        self.send_times_label.setStyleSheet("color: #374151; font-weight: 600; font-size: 12px;")
        self.send_times_label.setFixedHeight(32)
        self.send_times_label.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)

        self.send_times_spin = QtWidgets.QSpinBox()
        self.send_times_spin.setRange(1, 2147483647)
        self.send_times_spin.setValue(1)
        self.send_times_spin.setToolTip("序列循环执行次数")
        self.send_times_spin.setFixedHeight(32)
        self.send_times_spin.setMinimumWidth(100)
        self.send_times_spin.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)

        self.infinite_checkbox = QtWidgets.QCheckBox("无限")
        self.infinite_checkbox.setToolTip("勾选后循环次数不限，直到手动停止")
        self.infinite_checkbox.setFixedHeight(32)
        self.infinite_checkbox.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.infinite_checkbox.stateChanged.connect(self._on_infinite_toggled)

        self.run_sequence_btn = ModernButton("执行序列", "#3B82F6")
        self.run_sequence_btn.setToolTip("按指定次数执行当前指令序列")
        self.run_sequence_btn.setFixedHeight(32)
        self.run_sequence_btn.setMinimumWidth(90)
        self.run_sequence_btn.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.run_sequence_btn.clicked.connect(lambda: self._on_run_btn_clicked())

        self.stop_sequence_btn = ModernButton("停止", "#EF4444")
        self.stop_sequence_btn.setToolTip("停止当前正在执行的序列")
        self.stop_sequence_btn.setFixedHeight(32)
        self.stop_sequence_btn.setMinimumWidth(60)
        self.stop_sequence_btn.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.stop_sequence_btn.setEnabled(False)
        self.stop_sequence_btn.clicked.connect(lambda: self.stop_sequence_requested.emit())

        # --- Search ---
        self.search_input = QtWidgets.QLineEdit()
        self.search_input.setPlaceholderText("搜索...")
        self.search_input.setFixedHeight(32)
        self.search_input.setFixedWidth(140)
        self.search_input.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)

        self.search_btn = QtWidgets.QPushButton("🔍")
        self.search_btn.setToolTip("搜索表格内容")
        self.search_btn.setFixedSize(40, 32)
        self.search_btn.setStyleSheet(
            "QPushButton { background-color: #F3F4F6; border: 1px solid #D1D5DB; border-radius: 4px;"
            " font-size: 14px; padding: 0 4px; }"
            "QPushButton:hover { background-color: #E5E7EB; }"
        )
        self.search_btn.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)

        # Helper: vertical separator
        def _vsep():
            sep = QtWidgets.QFrame()
            sep.setFrameShape(QtWidgets.QFrame.VLine)
            sep.setStyleSheet("color: #D1D5DB;")
            sep.setFixedHeight(22)
            return sep

        # Group 1: Edit operations
        self.toolbar_row2.addWidget(self.icon_btn_add, 0)
        self.toolbar_row2.addWidget(self.icon_btn_delete, 0)
        self.toolbar_row2.addWidget(self.delay_icon_btn, 0)
        self.toolbar_row2.addWidget(self.icon_btn_up, 0)
        self.toolbar_row2.addWidget(self.icon_btn_down, 0)

        self.toolbar_row2.addSpacing(8)
        self.toolbar_row2.addWidget(_vsep(), 0)
        self.toolbar_row2.addSpacing(8)

        # Group 2: 3E controls
        self.toolbar_row2.addWidget(self.btn_3e, 0)
        self.toolbar_row2.addWidget(self.combo_3e_mode, 0)
        self.toolbar_row2.addWidget(self.btn_stop_fail, 0)

        self.toolbar_row2.addSpacing(8)
        self.toolbar_row2.addWidget(_vsep(), 0)
        self.toolbar_row2.addSpacing(8)

        # Group 3: Execution controls
        self.toolbar_row2.addWidget(self.send_times_label, 0)
        self.toolbar_row2.addWidget(self.send_times_spin, 0)
        self.toolbar_row2.addWidget(self.infinite_checkbox, 0)
        self.toolbar_row2.addSpacing(4)
        self.toolbar_row2.addWidget(self.run_sequence_btn, 0)
        self.toolbar_row2.addWidget(self.stop_sequence_btn, 0)

        self.toolbar_row2.addStretch(1)

        # Group 4: Search
        self.toolbar_row2.addWidget(self.search_input, 0)
        self.toolbar_row2.addWidget(self.search_btn, 0)

        # Assemble two-row toolbar
        self.toolbar_layout.addLayout(self.toolbar_row1)
        self.toolbar_layout.addWidget(h_sep)
        self.toolbar_layout.addLayout(self.toolbar_row2)

        self.data_table = QtWidgets.QTableWidget()
        self.data_table.setMinimumWidth(0)
        self.data_table.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.setup_table()

        self.editor_layout.addLayout(self.req_row_layout)
        self.editor_layout.addLayout(self.resp_row_layout)
        self.editor_layout.addWidget(self.toolbar_widget)
        self.editor_layout.addWidget(self.data_table)

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
                font-size: 10.5pt;
                min-width: 32px;
                min-height: 32px;
            }}
            QPushButton:hover {{
                background-color: {self.adjust_color(color, -10)};
            }}
            QPushButton:pressed {{
                background-color: {self.adjust_color(color, -20)};
            }}
            QToolTip {{
                background-color: #1F2937;
                color: white;
                border: 1px solid #1F2937;
                border-radius: 4px;
                padding: 4px;
                opacity: 230;
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

        header = CheckBoxHeader(Qt.Horizontal, self.data_table)
        self.data_table.setHorizontalHeader(header)
        header.checkBoxClicked.connect(self._on_header_checkbox_clicked)

        self.data_table.setHorizontalHeaderLabels(["", "Name", "Request", "AddrType", "Response"])

        # Allow user to resize columns
        header.setSectionResizeMode(QtWidgets.QHeaderView.Interactive)
        header.setStretchLastSection(False)

        header.setSectionsClickable(True)
        header.setHighlightSections(True)
        header.setSectionsMovable(True)  # Enable draggable columns

        self.data_table.setSelectionBehavior(QtWidgets.QTableWidget.SelectRows)

        self.data_table.setAlternatingRowColors(True)
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

        self.data_table.itemChanged.connect(lambda _: self.table_data_changed.emit())

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
        self._apply_column_widths(force=True)

    def _apply_column_widths(self, force: bool = False):
        if not hasattr(self, 'data_table') or not self.data_table:
            return

        viewport_width = self.data_table.viewport().width()
        if viewport_width <= 0:
            return

        bucket = viewport_width // 80
        if not force and bucket == self._last_resize_bucket:
            return
        self._last_resize_bucket = bucket

        header = self.data_table.horizontalHeader()
        fixed_widths = {
            0: 40,
            2: 140,
            3: 96,
        }
        for col, width in fixed_widths.items():
            header.setSectionResizeMode(col, QtWidgets.QHeaderView.Interactive)
            self.data_table.setColumnWidth(col, width)

        available = max(260, viewport_width - sum(fixed_widths.values()))
        name_width = max(180, int(available * 0.42))
        response_width = max(220, available - name_width)

        self.data_table.setColumnWidth(1, name_width)
        header.setSectionResizeMode(4, QtWidgets.QHeaderView.Stretch)
        self.data_table.setColumnWidth(4, response_width)

    def _on_splitter_moved(self, pos, index):
        self._user_resized_splitter = True
        total_width = max(1, self.cmd_splitter.size().width())
        self._preferred_splitter_ratio = max(0.16, min(0.32, pos / total_width))
        self._apply_responsive_layout(update_splitter=False)

    def _apply_responsive_layout(self, update_splitter=True):
        # Guard: skip if underlying C++ objects have been deleted (e.g. widget closing)
        try:
            if not hasattr(self, 'editor_layout') or self.editor_layout is None:
                return
            self.editor_layout.spacing()  # probe C++ object validity
        except RuntimeError:
            return

        if hasattr(self, 'cmd_splitter') and self.cmd_splitter and update_splitter:
            total_width = max(0, self.cmd_splitter.size().width())
            if total_width > 0:
                ratio = self._preferred_splitter_ratio if self._user_resized_splitter else 0.20
                tree_width = max(180, min(300, int(total_width * ratio)))
                editor_width = max(420, total_width - tree_width)
                self.cmd_splitter.setSizes([tree_width, editor_width])

        editor_width = self.editor_widget.width() if hasattr(self, 'editor_widget') else 0
        if editor_width <= 0 and hasattr(self, 'cmd_splitter'):
            sizes = self.cmd_splitter.sizes()
            if len(sizes) > 1:
                editor_width = sizes[1]
        if editor_width <= 0:
            editor_width = self.width()

        ratio = max(0.78, min(1.08, editor_width / 1100.0))
        spacing = max(4, min(8, int(6 * ratio)))
        side_margin = max(4, min(8, int(8 * ratio)))
        row_height = max(40, min(50, int(50 * ratio)))
        tool_height = max(28, min(32, int(32 * ratio)))
        icon_size = max(28, min(32, int(32 * ratio)))
        toggle_width = max(34, min(40, int(40 * ratio)))
        label_width = max(60, min(70, int(70 * ratio)))

        self.editor_layout.setSpacing(max(6, spacing))
        self.editor_layout.setContentsMargins(side_margin, 0, 0, 0)
        self.req_row_layout.setSpacing(spacing)
        self.resp_row_layout.setSpacing(spacing)
        self.toolbar_layout.setSpacing(6)
        self.toolbar_layout.setContentsMargins(10, max(4, int(6 * ratio)), 10, max(4, int(6 * ratio)))
        self.toolbar_row1.setSpacing(spacing)
        self.toolbar_row2.setSpacing(max(3, min(4, int(4 * ratio))))

        self.req_label.setFixedWidth(label_width)
        self.resp_label.setFixedWidth(label_width)
        self.request_edit.setMinimumWidth(max(220, int(260 * ratio)))
        self.response_edit.setMinimumWidth(max(220, int(260 * ratio)))

        self._scale_widget_width(self.send_btn, 80, ratio, 72, 88)
        self._scale_widget_height(self.send_btn, 50, ratio, 40, 50)
        self._scale_widget_width(self.insert_btn, 80, ratio, 72, 88)
        self._scale_widget_height(self.insert_btn, 50, ratio, 40, 50)

        self._scale_widget_width(self.config_combo, 120, ratio, 88, 180)
        self._scale_widget_height(self.config_combo, 32, ratio, 28, 32)
        for btn in (self.save_config_btn, self.del_config_btn, self.import_config_btn, self.export_config_btn):
            self._scale_widget_width(btn, 72, ratio, 56, 80)
            self._scale_widget_height(btn, 32, ratio, 28, 32)

        for btn in (self.icon_btn_add, self.icon_btn_delete, self.delay_icon_btn, self.icon_btn_up, self.icon_btn_down):
            btn.setFixedSize(icon_size, icon_size)

        self.btn_3e.setFixedSize(toggle_width, tool_height)
        self.combo_3e_mode.setFixedSize(int(72 * ratio), tool_height)
        self.btn_stop_fail.setFixedSize(toggle_width, tool_height)
        self.send_times_label.setStyleSheet(f"color: #374151; font-weight: 600; font-size: {max(10, min(12, int(12 * ratio)))}px;")
        self._scale_widget_width(self.send_times_spin, 110, ratio, 90, 130)
        self._scale_widget_height(self.send_times_spin, 32, ratio, 28, 32)
        self._scale_widget_width(self.run_sequence_btn, 110, ratio, 88, 120)
        self._scale_widget_height(self.run_sequence_btn, 32, ratio, 28, 32)
        self._scale_widget_width(self.stop_sequence_btn, 70, ratio, 56, 80)
        self._scale_widget_height(self.stop_sequence_btn, 32, ratio, 28, 32)

        self.search_btn.setMinimumSize(40, 32)
        self.search_btn.setFixedSize(max(40, int(44 * ratio)), max(32, int(32 * ratio)))
        self.search_input.setFixedWidth(max(130, int(140 * ratio)) if self.width() < 1500 else max(160, int(180 * ratio)))

        self._apply_column_widths(force=True)

    def _scale_widget_width(self, widget, base_width, ratio, min_width, max_width=None):
        width = max(min_width, int(base_width * ratio))
        if max_width is not None:
            width = min(max_width, width)
        widget.setFixedWidth(width)

    def _scale_widget_height(self, widget, base_height, ratio, min_height, max_height=None):
        height = max(min_height, int(base_height * ratio))
        if max_height is not None:
            height = min(max_height, height)
        widget.setFixedHeight(height)

    def resizeEvent(self, event):
        try:
            super().resizeEvent(event)
            # Avoid unnecessary relayouts when height changes or typing happens (which might trigger spurious resize events)
            if event.oldSize().width() == event.size().width():
                return
            self._apply_responsive_layout(update_splitter=not self._user_resized_splitter)
        except RuntimeError:
            pass  # C++ object already deleted (widget being destroyed)


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
        self.data_table.setEnabled(enabled)
        for btn in (self.icon_btn_add, self.icon_btn_delete, self.delay_icon_btn, self.icon_btn_up, self.icon_btn_down):
            btn.setEnabled(enabled)

    def set_placeholders(self, command: str):
        self.request_edit.setPlaceholderText(f"配置 {command} 的请求...")
        self.response_edit.setPlaceholderText(f"配置 {command} 的响应...")

    def reset_table(self):
        self.data_table.setRowCount(0)
        self.table_data_changed.emit()

    def insert_table_row(self, row: int, param_name: str, param_value: str, description: str, addrtype: str = 'physical', checked: bool = True):
        """Insert a row at the specified index."""
        self.data_table.blockSignals(True)
        self.data_table.insertRow(row)

        # first column: use QTableWidgetItem with CheckStateRole
        chk_item = QtWidgets.QTableWidgetItem()
        chk_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
        chk_item.setData(Qt.CheckStateRole, Qt.Checked if checked else Qt.Unchecked)
        self.data_table.setItem(row, 0, chk_item)

        # Name
        self.data_table.setItem(row, 1, QtWidgets.QTableWidgetItem(param_name))
        # Request
        self.data_table.setItem(row, 2, QtWidgets.QTableWidgetItem(self.format_hex_string(param_value)))
        # AddrType default
        self.data_table.setItem(row, 3, QtWidgets.QTableWidgetItem(addrtype))
        # Response
        self.data_table.setItem(row, 4, QtWidgets.QTableWidgetItem(self.format_hex_string(description)))

        try:
            self._apply_column_widths()
        except Exception:
            pass
        self.data_table.blockSignals(False)
        self.table_data_changed.emit()

    def append_table_row(self, param_name: str, param_value: str, description: str):
        """Append a row to the table."""
        self.insert_table_row(self.data_table.rowCount(), param_name, param_value, description)

    def remove_table_row(self, row: int):
        if 0 <= row < self.data_table.rowCount():
            self.data_table.removeRow(row)
            self.table_data_changed.emit()

    def get_current_row(self) -> int:
        return self.data_table.currentRow()

    def swap_table_rows(self, row1: int, row2: int):
        cols = self.data_table.columnCount()
        self.data_table.blockSignals(True)
        for col in range(cols):
            # Swap QTableWidgetItem for all columns (including checkbox column 0)
            item1 = self.data_table.takeItem(row1, col)
            item2 = self.data_table.takeItem(row2, col)
            self.data_table.setItem(row1, col, item2)
            self.data_table.setItem(row2, col, item1)
        self.data_table.blockSignals(False)
        self.table_data_changed.emit()

    def get_request_text(self) -> str:
        return self.request_edit.toPlainText().strip()

    def get_response_text(self) -> str:
        return self.response_edit.toPlainText().strip()

    def log_message(self, message: str):
        OperationLogManager.instance().append_log("UDS指令编排", message)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")

        if message.startswith("TX: "):
            message = "TX: " + self.format_hex_string(message[4:])
        elif message.startswith("RX: "):
            message = "RX: " + self.format_hex_string(message[4:])

        # Colorize based on content
        color = "#374151" # Default dark gray
        if "TX:" in message:
            color = "#2563EB" # Blue
        elif "RX:" in message:
            color = "#059669" # Green
        elif "Error" in message or "错误" in message or "Fail" in message:
            color = "#DC2626" # Red
        elif "Warning" in message or "警告" in message:
            color = "#D97706" # Orange

        html_msg = f'<span style="color: {color};">[{timestamp}] {message}</span>'
        self.exec_log.append(html_msg)
        self.exec_log.moveCursor(QtGui.QTextCursor.End)

    def highlight_row(self, row_index: int):
        """Scroll to and highlight the specified row."""
        if 0 <= row_index < self.data_table.rowCount():
             item = self.data_table.item(row_index, 1) # Use Name column item for positioning
             if item:
                 self.data_table.scrollToItem(item, QtWidgets.QAbstractItemView.PositionAtCenter)
                 self.data_table.selectRow(row_index)
                 # Optional: Explicitly set focus or visual feedback?
                 # selectRow is usually enough for visual feedback in standard themes.

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
            reply = QtWidgets.QMessageBox.question(self, "确认删除配置模板",
                                                 f"确定要删除配置模板 '{current}' 吗?\n(注: 此操作不会删除下方列表中当前的指令内容)",
                                                 QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
            if reply == QtWidgets.QMessageBox.Yes:
                self.config_delete_requested.emit(current)

    def update_row_response(self, row: int, response: str):
        """Update the response column for a specific row."""
        if 0 <= row < self.data_table.rowCount():
            self.data_table.blockSignals(True)
            self.data_table.setItem(row, 4, QtWidgets.QTableWidgetItem(self.format_hex_string(response)))
            self.data_table.blockSignals(False)

    def update_row_request(self, row: int, request: str):
        """Update the request column for a specific row."""
        if 0 <= row < self.data_table.rowCount():
            self.data_table.blockSignals(True)
            self.data_table.setItem(row, 2, QtWidgets.QTableWidgetItem(self.format_hex_string(request)))
            self.data_table.blockSignals(False)

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

    def _on_3e_toggled(self, checked):
        """3E 按钮切换：仅控制心跳启停，模式由独立下拉框选择。"""
        self.tp_toggled.emit(checked)

    def _on_3e_mode_changed(self, text):
        """3E 模式下拉框切换：独立切换 3E 80 / 3E 00 模式。"""
        mode = "00" if "00" in text else "80"
        self.tp_mode_changed.emit(mode)

    def _on_infinite_toggled(self, state):
        """无限复选框切换：勾选时禁用次数输入框。"""
        self.send_times_spin.setEnabled(state != QtCore.Qt.Checked)

    def _on_run_btn_clicked(self):
        """执行序列按钮点击：根据无限复选框状态发送 -1（无限）或具体次数。"""
        if self.infinite_checkbox.isChecked():
            self.run_sequence_requested.emit(-1)
        else:
            self.run_sequence_requested.emit(self.send_times_spin.value())

    def _apply_toggle_style(self, btn, active_color):
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #F3F4F6;
                color: #374151;
                border: 1px solid #D1D5DB;
                border-radius: 6px;
                font-weight: bold;
                padding: 0px;
            }}
            QPushButton:checked {{
                background-color: {active_color};
                color: white;
                border: 2px solid {active_color};
            }}
            QPushButton:hover:!checked {{
                background-color: #E5E7EB;
            }}
            QToolTip {{
                background-color: #1F2937;
                color: white;
                border: 1px solid #1F2937;
                border-radius: 4px;
                padding: 4px;
                opacity: 230;
            }}
        """)
