from PyQt5 import QtWidgets
from PyQt5.QtCore import Qt, pyqtSignal

from app.common.ui.widgets import ModernButton


class UDSSequenceView(QtWidgets.QWidget):
    send_requested = pyqtSignal(str)
    insert_requested = pyqtSignal(str)
    table_operation_requested = pyqtSignal(str)
    command_selected = pyqtSignal(int)

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

        main_splitter = QtWidgets.QSplitter(Qt.Vertical)

        cmd_group = QtWidgets.QGroupBox("UDS服务序列")
        cmd_layout = QtWidgets.QHBoxLayout(cmd_group)
        cmd_layout.setSpacing(0)
        cmd_layout.setContentsMargins(0, 0, 0, 0)

        cmd_splitter = QtWidgets.QSplitter(Qt.Horizontal)

        self.cmd_list = QtWidgets.QListWidget()
        self.cmd_list.addItems(self.model.commands)
        self.cmd_list.currentRowChanged.connect(self._on_command_selected_internal)
        cmd_splitter.addWidget(self.cmd_list)

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

    def create_editor_widget(self):
        editor = QtWidgets.QWidget()
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
        btn_row_layout.setContentsMargins(0, 4, 0, 4)

        self.icon_btn_add = self.create_icon_button("➕", "添加参数", "#10B981", "添加")
        self.icon_btn_delete = self.create_icon_button("➖", "删除选中参数", "#EF4444", "删除")
        self.icon_btn_up = self.create_icon_button("↑", "上移", "#0EA5E9", "上移")
        self.icon_btn_down = self.create_icon_button("↓", "下移", "#0EA5E9", "下移")

        btn_row_layout.addWidget(self.icon_btn_add)
        btn_row_layout.addWidget(self.icon_btn_delete)
        btn_row_layout.addWidget(self.icon_btn_up)
        btn_row_layout.addWidget(self.icon_btn_down)
        btn_row_layout.addStretch()

        self.data_table = QtWidgets.QTableWidget()
        self.setup_table()
        self.data_table.setMinimumHeight(200)

        layout.addLayout(req_row_layout)
        layout.addLayout(resp_row_layout)
        layout.addLayout(btn_row_layout)
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
                padding: 6px 10px;
                font-size: 14px;
                min-width: 32px;
                min-height: 32px;
            }}
            QPushButton:hover {{
                background-color: {self.adjust_color(color, -10)};
            }}
            QPushButton:pressed {{
                background-color: {self.adjust_color(color, -20)};
                padding: 7px 10px 5px 10px;
            }}
        """)
        btn.clicked.connect(lambda checked, op=operation: self.table_operation_requested.emit(op))
        return btn

    def adjust_color(self, color, amount):
        hex_color = color.lstrip('#')
        r = max(0, min(255, int(hex_color[0:2], 16) + amount))
        g = max(0, min(255, int(hex_color[2:4], 16) + amount))
        b = max(0, min(255, int(hex_color[4:6], 16) + amount))
        return f"#{r:02X}{g:02X}{b:02X}"

    def setup_table(self):
        self.data_table.setColumnCount(3)
        self.data_table.setHorizontalHeaderLabels(["参数名", "参数值", "描述"])
        self.data_table.horizontalHeader().setStretchLastSection(True)
        self.data_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        self.data_table.verticalHeader().setVisible(False)
        self.data_table.setAlternatingRowColors(True)
        self.data_table.setSelectionBehavior(QtWidgets.QTableWidget.SelectRows)
        self.data_table.setStyleSheet("""
            QTableWidget {
                background-color: #FFFFFF;
                border: 1px solid #E5E7EB;
                border-radius: 6px;
                font-size: 9pt;
            }
            QTableWidget::item {
                padding: 6px;
            }
        """)

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
        row = self.data_table.rowCount()
        self.data_table.insertRow(row)
        self.data_table.setItem(row, 0, QtWidgets.QTableWidgetItem(param_name))
        self.data_table.setItem(row, 1, QtWidgets.QTableWidgetItem(param_value))
        self.data_table.setItem(row, 2, QtWidgets.QTableWidgetItem(description))

    def remove_table_row(self, row: int):
        if 0 <= row < self.data_table.rowCount():
            self.data_table.removeRow(row)

    def get_current_row(self) -> int:
        return self.data_table.currentRow()

    def swap_table_rows(self, row1: int, row2: int):
        for col in range(self.data_table.columnCount()):
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

    def _on_command_selected_internal(self, row: int):
        self.command_selected.emit(row)
