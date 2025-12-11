from PyQt5 import QtWidgets
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
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


class UDSSequenceView(QtWidgets.QWidget):
    send_requested = pyqtSignal(str)
    insert_requested = pyqtSignal(str)
    table_operation_requested = pyqtSignal(str)
    delay_insert_requested = pyqtSignal(str)
    send_batch_requested = pyqtSignal(int)
    command_selected = pyqtSignal(str)  # emit code like '10' or '10.01'

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
        # ensure whole view background is white to match the table area
        try:
            # set a more global style for this widget so splitter handles, groupbox and tree view
            # use white backgrounds (fixes the left gray strip seen in the screenshot)
            self.setStyleSheet('''
                QWidget#uds_root { background: #FFFFFF; }
                QGroupBox { background: #FFFFFF; }
                QSplitter::handle { background: #FFFFFF; }
                QTreeView { background: #FFFFFF; }
                QHeaderView::section { background-color: #FFFFFF; }
                QTableCornerButton::section { background-color: #FFFFFF; }
            ''')
            # set objectName so the selector can target this instance if supported
            try:
                self.setObjectName('uds_root')
            except Exception:
                pass
        except Exception:
            pass

        # also force autoFillBackground so parent background applies in some styles
        try:
            self.setAutoFillBackground(True)
        except Exception:
            pass

        main_splitter = QtWidgets.QSplitter()
        main_splitter.setOrientation(Qt.Vertical)

        cmd_group = QtWidgets.QGroupBox("UDS服务序列")
        try:
            cmd_group.setStyleSheet('QGroupBox { background: #FFFFFF; border: none; }')
        except Exception:
            pass
        cmd_layout = QtWidgets.QHBoxLayout(cmd_group)
        cmd_layout.setSpacing(0)
        cmd_layout.setContentsMargins(0, 0, 0, 0)

        cmd_splitter = QtWidgets.QSplitter()
        cmd_splitter.setOrientation(Qt.Horizontal)
        try:
            cmd_splitter.setStyleSheet('background: #FFFFFF;')
        except Exception:
            pass
        # make splitter handle white so the long left strip isn't gray
        try:
            cmd_splitter.setStyleSheet(cmd_splitter.styleSheet() + ' QSplitter::handle { background: #FFFFFF; }')
        except Exception:
            pass

        # left side: tree view built from model.tree_data
        self.cmd_tree = QtWidgets.QTreeView()
        try:
            self.cmd_tree.setStyleSheet('background: #FFFFFF; border: none;')
        except Exception:
            pass
        self._build_tree_model()
        self.cmd_tree.clicked.connect(self._on_tree_item_clicked)
        cmd_splitter.addWidget(self.cmd_tree)

        self.editor_widget = self.create_editor_widget()
        cmd_splitter.addWidget(self.editor_widget)

        cmd_splitter.setStretchFactor(0, 1)
        cmd_splitter.setStretchFactor(1, 2)
        cmd_splitter.setSizes([300, 600])

        cmd_layout.addWidget(cmd_splitter)
        main_splitter.addWidget(cmd_group)

        log_group = QtWidgets.QGroupBox("执行日志")
        log_layout = QtWidgets.QVBoxLayout(log_group)
        log_layout.setContentsMargins(0, 0, 0, 0)

        self.exec_log = QtWidgets.QTextEdit()
        self.exec_log.setReadOnly(True)
        self.exec_log.setPlaceholderText("UDS指令执行日志将在这里显示...\n包含发送数据、响应数据、时间戳")
        log_layout.addWidget(self.exec_log)

        main_splitter.addWidget(log_group)

        main_splitter.setStretchFactor(0, 3)
        main_splitter.setStretchFactor(1, 1)
        main_splitter.setSizes([525, 175])

        layout.addWidget(main_splitter)

        self.clear_editor()

    def _build_tree_model(self):
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

    def create_editor_widget(self):
        editor = QtWidgets.QWidget()
        # make editor background white so left strip area matches table background
        try:
            editor.setStyleSheet('background: #FFFFFF;')
        except Exception:
            pass
        layout = QtWidgets.QVBoxLayout(editor)
        layout.setSpacing(8)
        layout.setContentsMargins(8, 8, 8, 8)

        req_row_layout = QtWidgets.QHBoxLayout()
        req_label = QtWidgets.QLabel("Request:")
        req_label.setStyleSheet("font-weight: 600; color: #374151;")
        req_label.setFixedWidth(70)

        self.request_edit = QtWidgets.QTextEdit()
        self.request_edit.setPlaceholderText("输入请求数据，如: 10 03")
        self.request_edit.setMaximumHeight(60)

        self.send_btn = ModernButton("发送", "#059669")
        self.send_btn.clicked.connect(self._on_send_clicked_internal)
        self.send_btn.setFixedWidth(80)

        req_row_layout.addWidget(req_label)
        req_row_layout.addWidget(self.request_edit)
        req_row_layout.addWidget(self.send_btn)

        resp_row_layout = QtWidgets.QHBoxLayout()
        resp_label = QtWidgets.QLabel("Response:")
        resp_label.setStyleSheet("font-weight: 600; color: #374151;")
        resp_label.setFixedWidth(70)

        self.response_edit = QtWidgets.QTextEdit()
        self.response_edit.setPlaceholderText("预期响应数据，如: 50 03")
        self.response_edit.setMaximumHeight(60)

        self.insert_btn = ModernButton("插入", "#3B82F6")
        self.insert_btn.clicked.connect(self._on_insert_clicked_internal)
        self.insert_btn.setFixedWidth(80)

        resp_row_layout.addWidget(resp_label)
        resp_row_layout.addWidget(self.response_edit)
        resp_row_layout.addWidget(self.insert_btn)

        btn_row_layout = QtWidgets.QHBoxLayout()
        btn_row_layout.setSpacing(6)
        # give symmetric small margins so the icon buttons sit centered vertically in the toolbar
        btn_row_layout.setContentsMargins(6, 6, 6, 6)
        btn_row_layout.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

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

        delay_color = "#10B981"
        self.delay_icon_btn = create_styled_button("⏱", "插入延迟指令 (默认 1000 ms)", delay_color)
        # clicking the styled button emits the default delay (1000 ms)
        self.delay_icon_btn.clicked.connect(lambda: self.delay_insert_requested.emit('1000'))

        # ensure all icon buttons have the same fixed size and are vertically centered
        for b in (self.icon_btn_add, self.icon_btn_delete, self.delay_icon_btn, self.icon_btn_up, self.icon_btn_down):
            try:
                b.setFixedSize(32, 32)
            except Exception:
                pass
            btn_row_layout.addWidget(b, 0, Qt.AlignVCenter)

        btn_row_layout.addStretch()

        # send-count and batch-send button on the far right of toolbar
        self.send_times_label = QtWidgets.QLabel("次数:")
        self.send_times_label.setStyleSheet("color: #374151; font-weight: 600;")
        self.send_times_label.setFixedWidth(36)

        self.send_times_spin = QtWidgets.QSpinBox()
        self.send_times_spin.setRange(1, 9999)
        self.send_times_spin.setValue(1)
        self.send_times_spin.setFixedWidth(70)
        self.send_times_spin.setFixedHeight(28)

        self.batch_send_btn = ModernButton("列表发送", "#3B82F6")
        self.batch_send_btn.setFixedHeight(32)
        self.batch_send_btn.setFixedWidth(90)
        # emit the configured number of sends (ms) when clicked
        self.batch_send_btn.clicked.connect(lambda: self.send_batch_requested.emit(self.send_times_spin.value()))

        btn_row_layout.addWidget(self.send_times_label)
        btn_row_layout.addWidget(self.send_times_spin)
        btn_row_layout.addWidget(self.batch_send_btn)

        # Wrap the button row into a fixed-height toolbar widget so icons stay vertically aligned
        toolbar_widget = QtWidgets.QWidget()
        toolbar_widget.setLayout(btn_row_layout)
        # slightly less than 44 gives tighter vertical centering for 32px buttons
        toolbar_widget.setFixedHeight(40)

        self.data_table = QtWidgets.QTableWidget()
        self.setup_table()
        self.data_table.setMinimumHeight(200)

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
        # use Fixed resize mode per-column — we compute widths to exactly fill the viewport
        header.setSectionResizeMode(QtWidgets.QHeaderView.Fixed)
        # ensure each column uses fixed mode so our computed widths are applied
        for col in range(self.data_table.columnCount()):
            header.setSectionResizeMode(col, QtWidgets.QHeaderView.Fixed)
        header.setSectionsClickable(True)
        header.setHighlightSections(True)
        # keep interactive resizing but we will control widths programmatically
        header.setStretchLastSection(False)
        self.data_table.setAlternatingRowColors(True)
        self.data_table.setSelectionBehavior(QtWidgets.QTableWidget.SelectRows)
        # show vertical header so rows are numbered (like the screenshot)
        self.data_table.verticalHeader().setVisible(True)
        # set default row height similar to DID
        try:
            self.data_table.verticalHeader().setDefaultSectionSize(34)
        except Exception:
            pass

        # Use delegates from DID view for full-cell editing and combo box for AddrType
        self._full_delegate = FullCellDelegate(self.data_table)
        self._addrtype_delegate = ComboBoxDelegate(items_provider=lambda idx: ["physical", "functional"], parent=self.data_table)
        # assign delegates to columns: Name(1), Request(2), AddrType(3), Response(4)
        self.data_table.setItemDelegateForColumn(1, self._full_delegate)
        self.data_table.setItemDelegateForColumn(2, self._full_delegate)
        self.data_table.setItemDelegateForColumn(3, self._addrtype_delegate)
        self.data_table.setItemDelegateForColumn(4, self._full_delegate)
        # allow editing by double click (consistent with DID behavior that uses controller to open editors)
        self.data_table.setEditTriggers(QtWidgets.QAbstractItemView.DoubleClicked)

        # ensure vertical header shows row numbers and a comfortable width
        try:
            vh = self.data_table.verticalHeader()
            vh.setDefaultSectionSize(34)
            vh.setVisible(True)
            vh.setFixedWidth(36)
            vh.setSectionResizeMode(QtWidgets.QHeaderView.Fixed)
            # style vertical header to match table background and center numbers
            try:
                vh.setStyleSheet('QHeaderView::section { background-color: #FFFFFF; border: none; }')
            except Exception:
                pass
        except Exception:
            pass

        # style header sections, corner and viewport so left strip and header look white like screenshot
        self.data_table.setStyleSheet("""
            QTableWidget {
                background-color: #FFFFFF;
                border: 1px solid #E5E7EB;
                border-radius: 6px;
                font-size: 9pt;
            }
            QHeaderView::section { background-color: #FFFFFF; border: 1px solid #F1F5F9; padding: 6px; }
            QTableCornerButton::section { background-color: #FFFFFF; border: none; }
            QTableWidget::item { padding: 6px; }
            /* ensure vertical header sections match white background */
            QHeaderView::section:vertical { background-color: #FFFFFF; }
        """)
        try:
            # also ensure the viewport background is white
            self.data_table.viewport().setStyleSheet('background: #FFFFFF;')
        except Exception:
            pass
        # set initial column widths after layout
        QtWidgets.QApplication.instance().processEvents()
        QTimer.singleShot(0, self._apply_column_widths)

    def _apply_column_widths(self, force: bool = False):
        """Apply relative column widths to match the screenshot proportions.

        Column layout: [checkbox (fixed), Name (largest), Request, AddrType (small), Response]
        """
        try:
            # compute available width using the table viewport so columns fill visible area
            total = max(1, self.data_table.viewport().width())
            chk_w = 36
            remaining = max(0, total - chk_w)
            # weights for Name, Request, AddrType, Response — tuned to match screenshot (image 10)
            weights = [0.46, 0.20, 0.12, 0.22]
            # compute initial widths
            w1 = int(remaining * weights[0])
            w2 = int(remaining * weights[1])
            w3 = int(remaining * weights[2])
            # ensure last column fills any rounding gap so total columns fill remaining area
            w4 = max(80, remaining - (w1 + w2 + w3))
            # ensure non-negative
            if w4 < 80:
                # redistribute proportionally if too small
                total_weight = sum(weights)
                w1 = int(remaining * (weights[0] / total_weight))
                w2 = int(remaining * (weights[1] / total_weight))
                w3 = int(remaining * (weights[2] / total_weight))
                w4 = max(80, remaining - (w1 + w2 + w3))
            self.data_table.setColumnWidth(0, chk_w)
            self.data_table.setColumnWidth(1, w1)
            self.data_table.setColumnWidth(2, w2)
            self.data_table.setColumnWidth(3, w3)
            self.data_table.setColumnWidth(4, w4)
            # ensure header visual sections use same widths
            try:
                header = self.data_table.horizontalHeader()
                header.resizeSection(0, chk_w)
                header.resizeSection(1, w1)
                header.resizeSection(2, w2)
                header.resizeSection(3, w3)
                header.resizeSection(4, w4)
            except Exception:
                pass
            # final adjustment: if tiny gap remains, increase last column
            try:
                sumw = chk_w + w1 + w2 + w3 + w4
                gap = total - sumw
                if gap > 0:
                    header = self.data_table.horizontalHeader()
                    header.resizeSection(4, w4 + gap)
                    self.data_table.setColumnWidth(4, w4 + gap)
            except Exception:
                pass
        except Exception:
            pass

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # reapply column widths on resize to maintain proportions
        try:
            self._apply_column_widths()
        except Exception:
            pass

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

        # first column: use a centered QCheckBox widget so background matches the row
        chk_widget = QtWidgets.QWidget()
        chk_layout = QtWidgets.QHBoxLayout(chk_widget)
        chk_layout.setContentsMargins(6, 0, 6, 0)
        chk_layout.setAlignment(Qt.AlignCenter)
        cb = QtWidgets.QCheckBox()
        cb.setChecked(True)
        # minimal indicator size so it looks consistent and transparent background
        cb.setStyleSheet('QCheckBox::indicator { width: 16px; height: 16px; } QCheckBox { background: transparent; }')
        chk_layout.addWidget(cb)
        # ensure the cell widget is transparent so alternating row colors remain visible
        chk_widget.setStyleSheet('background: transparent;')
        # make cell widget truly transparent so alternating row colors show through
        try:
            chk_widget.setAutoFillBackground(False)
            chk_widget.setAttribute(Qt.WA_TranslucentBackground, True)
        except Exception:
            pass
        self.data_table.setCellWidget(row, 0, chk_widget)

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
        # swap widget contents and item texts to preserve widgets and avoid invalid setItem(None)
        cols = self.data_table.columnCount()
        widgets_row1 = [self.data_table.cellWidget(row1, c) for c in range(cols)]
        widgets_row2 = [self.data_table.cellWidget(row2, c) for c in range(cols)]
        for col in range(cols):
            w1 = widgets_row1[col]
            w2 = widgets_row2[col]
            if w1 is not None or w2 is not None:
                # swap widgets
                if w1 is not None:
                    self.data_table.removeCellWidget(row1, col)
                if w2 is not None:
                    self.data_table.removeCellWidget(row2, col)
                if w2 is not None:
                    self.data_table.setCellWidget(row1, col, w2)
                if w1 is not None:
                    self.data_table.setCellWidget(row2, col, w1)
            else:
                # swap item texts
                item1 = self.data_table.item(row1, col)
                item2 = self.data_table.item(row2, col)
                t1 = item1.text() if item1 is not None else ''
                t2 = item2.text() if item2 is not None else ''
                # ensure there is an item to set text into
                if item1 is None:
                    self.data_table.setItem(row1, col, QtWidgets.QTableWidgetItem(t2))
                else:
                    item1.setText(t2)
                if item2 is None:
                    self.data_table.setItem(row2, col, QtWidgets.QTableWidgetItem(t1))
                else:
                    item2.setText(t1)

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
