# python
from datetime import datetime
from random import random
from PyQt5 import QtWidgets, QtGui, QtCore

from app.common.ui.widgets import ModernButton, create_icon, TableButton
from app.presentation.views.base_view import BaseView


class DTCView(BaseView):
    def setup_ui(self):
        root_layout = QtWidgets.QVBoxLayout(self)
        root_layout.setSpacing(8)
        root_layout.setContentsMargins(4, 4, 4, 4)

        # 顶部工具栏
        toolbar_frame = QtWidgets.QFrame()
        toolbar_frame.setFixedHeight(46)
        toolbar_layout = QtWidgets.QHBoxLayout(toolbar_frame)
        toolbar_layout.setContentsMargins(8, 4, 8, 4)
        toolbar_layout.setSpacing(8)

        btn_font = QtGui.QFont()
        btn_font.setPointSize(10)

        self.read_btn = ModernButton("读取故障码", "#0EA5E9", "🔍")
        self.read_btn.setMinimumHeight(30)
        self.read_btn.setFont(btn_font)

        self.clear_btn = ModernButton("清除故障", "#EF4444", "🗑️")
        self.clear_btn.setMinimumHeight(30)
        self.clear_btn.setFont(btn_font)

        self.last_read_label = QtWidgets.QLabel("最后读取时间：—")
        self.last_read_label.setStyleSheet("color:#475569; font-size:12px;")
        self.last_read_label.setAlignment(QtCore.Qt.AlignVCenter)

        toolbar_layout.addWidget(self.read_btn)
        toolbar_layout.addWidget(self.clear_btn)
        toolbar_layout.addSpacing(12)
        toolbar_layout.addWidget(self.last_read_label)
        toolbar_layout.addStretch()
        root_layout.addWidget(toolbar_frame)

        # 中部两栏分隔
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)

        self.left_panel = QtWidgets.QFrame()
        left_layout = QtWidgets.QVBoxLayout(self.left_panel)
        left_layout.setContentsMargins(4, 4, 4, 4)
        left_layout.setSpacing(4)
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabel("故障分类")
        self.tree.setIndentation(14)
        left_layout.addWidget(self.tree)

        self.center_panel = QtWidgets.QFrame()
        center_layout = QtWidgets.QVBoxLayout(self.center_panel)
        center_layout.setContentsMargins(4, 4, 4, 4)
        center_layout.setSpacing(4)
        self.table = QtWidgets.QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels([
            "序号", "故障码", "故障描述", "上报子系统", "状态码", "故障状态", "冻结帧状态", "冻结帧操作"
        ])
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        # 行高
        self.table.verticalHeader().setDefaultSectionSize(50)
        center_layout.addWidget(self.table)

        splitter.addWidget(self.left_panel)
        splitter.addWidget(self.center_panel)
        splitter.setSizes([240, 800])
        root_layout.addWidget(splitter, 1)

        # 底部日志模块
        log_group = QtWidgets.QGroupBox("操作日志")
        log_layout = QtWidgets.QVBoxLayout(log_group)
        log_layout.setContentsMargins(6, 6, 6, 6)
        self.log_edit = QtWidgets.QPlainTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setMaximumBlockCount(500)
        self.log_edit.setStyleSheet("font-family:Consolas; font-size:12px;")
        self.log_edit.setMinimumHeight(110)
        log_layout.addWidget(self.log_edit)
        root_layout.addWidget(log_group)

        # 信号
        self.read_btn.clicked.connect(self.on_read_dtcs)
        self.clear_btn.clicked.connect(self.on_clear_dtcs)

    def append_log(self, message: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_edit.appendPlainText(f"[{ts}] {message}")

    def populate(self, categories, dtcs):
        """
        dtcs: List[Tuple(code, desc, subsystem, status_code, fault_state, freeze_state?)]
        """
        self.tree.clear()
        for cat in categories:
            item = QtWidgets.QTreeWidgetItem(self.tree)
            item.setText(0, cat)
            item.setIcon(0, create_icon("⚠️", "#EF4444"))
        self.tree.expandAll()

        self.table.setRowCount(len(dtcs))
        for r, row in enumerate(dtcs):
            if len(row) == 6:
                code, desc, subsystem, status_code, fault_state, freeze_state = row
            else:
                code, desc, subsystem, status_code, fault_state = row
                freeze_state = "未读取"

            seq_item = QtWidgets.QTableWidgetItem(str(r + 1))
            seq_item.setTextAlignment(QtCore.Qt.AlignCenter)
            self.table.setItem(r, 0, seq_item)

            def make_center(text):
                it = QtWidgets.QTableWidgetItem(text)
                it.setTextAlignment(QtCore.Qt.AlignCenter)
                return it

            self.table.setItem(r, 1, make_center(code))
            self.table.setItem(r, 2, make_center(desc))
            self.table.setItem(r, 3, make_center(subsystem))
            self.table.setItem(r, 4, make_center(status_code))
            self.table.setItem(r, 5, make_center(fault_state))

            status_item = make_center(freeze_state or "未读取")
            self.table.setItem(r, 6, status_item)
            self._apply_freeze_status_style(status_item.text(), status_item)

            op_widget = QtWidgets.QWidget()
            op_layout = QtWidgets.QHBoxLayout(op_widget)
            op_layout.setContentsMargins(0, 0, 0, 0)
            op_layout.setSpacing(0)
            btn = TableButton("读取冻结帧", "#6366F1", "🧊")
            btn.setMinimumHeight(28)
            btn.setFont(QtGui.QFont("", 9))
            btn.setProperty("row", r)
            btn.clicked.connect(self.on_click_freeze_btn)
            op_layout.addWidget(btn, 0, QtCore.Qt.AlignCenter)
            self.table.setCellWidget(r, 7, op_widget)

            # 保险再次设定单行高度
            self.table.setRowHeight(r, 50)

        self.append_log(f"载入DTC记录 共{len(dtcs)}条")

    def _apply_freeze_status_style(self, text: str, item: QtWidgets.QTableWidgetItem):
        color_map = {
            "未读取": "#64748B",
            "读取中...": "#0EA5E9",
            "读取成功": "#059669",
            "读取失败": "#DC2626"
        }
        item.setForeground(QtGui.QBrush(QtGui.QColor(color_map.get(text, "#64748B"))))

    def set_last_read_time(self, dt: datetime):
        self.last_read_label.setText(f"最后读取时间：{dt.strftime('%Y-%m-%d %H:%M:%S')}")

    def on_read_dtcs(self):
        now = datetime.now()
        self.set_last_read_time(now)
        self.append_log("执行读取故障码")

    def on_clear_dtcs(self):
        self.table.setRowCount(0)
        self.append_log("清除故障码表格内容")

    def on_click_freeze_btn(self):
        btn = self.sender()
        if not btn:
            return
        row = btn.property("row")
        status_item = self.table.item(row, 6)
        if not status_item:
            return
        status_item.setText("读取中...")
        self._apply_freeze_status_style("读取中...", status_item)
        self.append_log(f"开始读取冻结帧 Row={row + 1}")
        QtCore.QTimer.singleShot(600, lambda: self._finish_freeze_read(row))

    def _finish_freeze_read(self, row: int):
        status_item = self.table.item(row, 6)
        if not status_item:
            return
        success = random() > 0.15
        new_text = "读取成功" if success else "读取失败"
        status_item.setText(new_text)
        self._apply_freeze_status_style(new_text, status_item)
        self.append_log(f"冻结帧读取结果 Row={row + 1} -> {new_text}")
