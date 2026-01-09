# python
from datetime import datetime
from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtCore import Qt

from app.common.ui.widgets import ModernButton
from app.presentation.views.base_view import BaseView


class DTCView(BaseView):
    read_dtc_signal = QtCore.pyqtSignal()
    read_freeze_frame_signal = QtCore.pyqtSignal(int)
    filter_changed_signal = QtCore.pyqtSignal(str)
    clear_dtc_signal = QtCore.pyqtSignal()

    def setup_ui(self):
        # Main Layout
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Splitter
        self.splitter = QtWidgets.QSplitter(Qt.Vertical)
        main_layout.addWidget(self.splitter)

        # Top Container
        self.top_widget = QtWidgets.QWidget()
        top_layout = QtWidgets.QVBoxLayout(self.top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(0)
        self.splitter.addWidget(self.top_widget)

        # Global Action Buttons
        self.read_btn = ModernButton("读取故障码", "#3B82F6")
        self.read_btn.setMinimumWidth(120)

        self.clear_btn = QtWidgets.QPushButton("清除故障码")
        self.clear_btn.setCursor(QtGui.QCursor(Qt.PointingHandCursor))
        self.clear_btn.setMinimumHeight(32)
        self.clear_btn.setMinimumWidth(120)
        self.clear_btn.setStyleSheet("""
            QPushButton { 
                background-color: white; 
                color: #333; 
                border: 1px solid #CBD5E1; 
                border-radius: 6px; 
                font-family: "Microsoft YaHei";
                font-size: 14px;
            }
            QPushButton:hover { background-color: #F1F5F9; }
            QPushButton:pressed { background-color: #E2E8F0; }
        """)

        # Tab Widget
        self.tab_widget = QtWidgets.QTabWidget()
        self.tab_widget.setStyleSheet("""
            QTabBar::tab {
                min-width: 120px;
                height: 20px;
                font-family: "Microsoft YaHei";
                font-size: 14px;
            }
        """)
        top_layout.addWidget(self.tab_widget)

        # --- Page 1: Fault List ---
        self.page_faults = QtWidgets.QWidget()
        self.setup_fault_page(self.page_faults)
        self.tab_widget.addTab(self.page_faults, "故障信息")

        # --- Page 2: Freeze Frame ---
        self.page_freeze = QtWidgets.QWidget()
        self.setup_freeze_page(self.page_freeze)
        self.tab_widget.addTab(self.page_freeze, "冻结帧信息")

        # Corner Buttons (Moved back to CornerWidget to save vertical space)
        corner_widget = QtWidgets.QWidget()
        corner_layout = QtWidgets.QHBoxLayout(corner_widget)
        corner_layout.setContentsMargins(0, 0, 10, 0)
        corner_layout.setSpacing(10)
        corner_layout.addWidget(self.read_btn)
        corner_layout.addWidget(self.clear_btn)
        self.tab_widget.setCornerWidget(corner_widget, Qt.TopRightCorner)

        # Connect Actions
        self.read_btn.clicked.connect(self.on_read_dtcs)
        self.clear_btn.clicked.connect(self.on_clear_dtcs)

        # Log Window (Output)
        log_group = QtWidgets.QGroupBox("操作日志")
        log_layout = QtWidgets.QVBoxLayout(log_group)
        log_layout.setContentsMargins(6, 6, 6, 6)
        self.log_edit = QtWidgets.QPlainTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setMaximumBlockCount(500)
        self.log_edit.setMinimumHeight(100)
        log_layout.addWidget(self.log_edit)

        self.splitter.addWidget(log_group)
        self.splitter.setStretchFactor(0, 2)
        self.splitter.setStretchFactor(1, 1)


    def setup_fault_page(self, parent):
        layout = QtWidgets.QVBoxLayout(parent)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Header Row: Title + Last Read Time + Filter Buttons
        header_layout = QtWidgets.QHBoxLayout()

        title = QtWidgets.QLabel("故障列表")
        title.setStyleSheet("font-size: 18px; font-weight: bold; font-family: 'Microsoft YaHei'; color: #1E293B;")
        header_layout.addWidget(title)

        self.last_read_label = QtWidgets.QLabel("最后读取时间：—")
        self.last_read_label.setStyleSheet("color: #64748B; margin-left: 15px; font-size: 14px;")
        header_layout.addWidget(self.last_read_label)

        header_layout.addStretch()

        # Filter Buttons
        self.filter_group = QtWidgets.QButtonGroup(self)
        self.filter_group.buttonClicked.connect(self.on_filter_group_clicked)
        self.btn_filter_all = self._create_filter_btn("全部故障", True)
        self.btn_filter_curr = self._create_filter_btn("当前故障")
        self.btn_filter_hist = self._create_filter_btn("历史故障")
        self.btn_filter_pend = self._create_filter_btn("未决故障")

        # Container for filter buttons to handle spacing/grouping look
        filter_container = QtWidgets.QWidget()
        filter_layout = QtWidgets.QHBoxLayout(filter_container)
        filter_layout.setContentsMargins(0, 0, 0, 0)
        filter_layout.setSpacing(0) # Connected buttons

        buttons = [self.btn_filter_all, self.btn_filter_curr, self.btn_filter_hist, self.btn_filter_pend]
        for i, btn in enumerate(buttons):
            filter_layout.addWidget(btn)
            self.filter_group.addButton(btn)
            # Add border radius to first and last
            radius_style = ""
            if i == 0:
                radius_style = "border-top-left-radius: 4px; border-bottom-left-radius: 4px;"
            elif i == len(buttons) - 1:
                radius_style = "border-top-right-radius: 4px; border-bottom-right-radius: 4px;"

            # Append radius style to existing stylesheet
            # Note: This is a bit hacky, better to set full stylesheet here or in _create_filter_btn
            # But _create_filter_btn sets the base style.
            # Let's just rely on the base style for now, maybe add a specific property.
            btn.setProperty("position", "first" if i==0 else ("last" if i==len(buttons)-1 else "middle"))

        header_layout.addWidget(filter_container)
        layout.addLayout(header_layout)

        # Table
        self.fault_table = QtWidgets.QTableWidget()
        cols = ["序号", "故障码", "故障描述", "上报子系统", "状态码", "故障状态", "冻结帧状态", "冻结帧操作"]
        self.fault_table.setColumnCount(len(cols))
        self.fault_table.setHorizontalHeaderLabels(cols)
        self.fault_table.verticalHeader().setVisible(False)
        self.fault_table.setAlternatingRowColors(True)
        self.fault_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.fault_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Interactive)
        self.fault_table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)

        # Install event filter for adaptive column resizing
        self.fault_table.installEventFilter(self)

        self.fault_table.setShowGrid(False)
        self.fault_table.setFrameShape(QtWidgets.QFrame.NoFrame)
        layout.addWidget(self.fault_table)

        # Pagination
        page_layout = QtWidgets.QHBoxLayout()
        self.page_info_label = QtWidgets.QLabel("每页显示10条，共1页，共0条")
        self.page_info_label.setStyleSheet("color: #64748B;")
        page_layout.addWidget(self.page_info_label)
        page_layout.addStretch()

        self.btn_prev = QtWidgets.QPushButton("上一页")
        self.btn_next = QtWidgets.QPushButton("下一页")
        self.lbl_page_num = QtWidgets.QLabel("1/1")
        self.lbl_page_num.setStyleSheet("color: #3B82F6; font-weight: bold; padding: 0 10px;")

        for btn in [self.btn_prev, self.btn_next]:
            btn.setCursor(QtGui.QCursor(Qt.PointingHandCursor))
            btn.setStyleSheet("""
                QPushButton {
                    border: 1px solid #E2E8F0; 
                    background: white; 
                    padding: 6px 16px; 
                    border-radius: 4px;
                    color: #64748B;
                }
                QPushButton:hover { background: #F8FAFC; color: #333; }
            """)

        page_layout.addWidget(self.btn_prev)
        page_layout.addWidget(self.lbl_page_num)
        page_layout.addWidget(self.btn_next)

        layout.addLayout(page_layout)

    def _create_filter_btn(self, text, checked=False):
        btn = QtWidgets.QPushButton(text)
        btn.setCheckable(True)
        btn.setChecked(checked)
        btn.setCursor(QtGui.QCursor(Qt.PointingHandCursor))
        btn.setStyleSheet("""
            QPushButton {
                background-color: white;
                border: 1px solid #E2E8F0;
                color: #64748B;
                padding: 8px 20px;
                font-family: "Microsoft YaHei";
                margin: 0px;
            }
            QPushButton:checked {
                background-color: #3B82F6;
                color: white;
                border-color: #3B82F6;
            }
            QPushButton:hover:!checked {
                background-color: #F8FAFC;
                color: #3B82F6;
            }
            /* Radius handling based on position property would require re-applying stylesheet or separate classes. 
               Simplifying for now by not rounding corners perfectly or just rounding all slightly if not grouped perfectly.
               Let's try to make them look connected. */
        """)
        return btn

    def setup_freeze_page(self, parent):
        layout = QtWidgets.QVBoxLayout(parent)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        header_layout = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("冻结帧数据")
        title.setStyleSheet("font-size: 18px; font-weight: bold; font-family: 'Microsoft YaHei'; color: #1E293B;")
        header_layout.addWidget(title)

        self.freeze_time_label = QtWidgets.QLabel("最后读取时间：—")
        self.freeze_time_label.setStyleSheet("color: #64748B; margin-left: 15px; font-size: 14px;")
        header_layout.addWidget(self.freeze_time_label)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        self.freeze_table = QtWidgets.QTableWidget()
        cols = ["故障码", "故障描述", "类型", "DID", "长度", "Byte", "Bit", "参数名称", "数值", "单位"]
        self.freeze_table.setColumnCount(len(cols))
        self.freeze_table.setHorizontalHeaderLabels(cols)
        self.freeze_table.verticalHeader().setVisible(False)
        self.freeze_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        self.freeze_table.horizontalHeader().setSectionResizeMode(5, QtWidgets.QHeaderView.ResizeToContents) # Byte
        self.freeze_table.horizontalHeader().setSectionResizeMode(6, QtWidgets.QHeaderView.ResizeToContents) # Bit
        self.freeze_table.horizontalHeader().setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeToContents) # Length

        self.freeze_table.setShowGrid(True)
        self.freeze_table.setFrameShape(QtWidgets.QFrame.NoFrame)

        layout.addWidget(self.freeze_table)

    def append_log(self, message: str):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        if hasattr(self, 'log_edit'):
            self.log_edit.appendPlainText(f"[{ts}] {message}")
            # Scroll to bottom
            scrollbar = self.log_edit.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
        else:
            print(f"[{ts}] {message}")

    def populate(self, categories, dtcs):
        """
        dtcs: List[Tuple(code, desc, subsystem, status_code, fault_state, freeze_state?)]
        """
        # Update Filter Button Texts
        if categories and len(categories) >= 4:
            self.btn_filter_all.setText(categories[0])
            self.btn_filter_curr.setText(categories[1])
            self.btn_filter_hist.setText(categories[2])
            self.btn_filter_pend.setText(categories[3])

        # Update Fault Table
        self.fault_table.setRowCount(len(dtcs))

        # Update Pagination Info (Mock)
        self.page_info_label.setText(f"每页显示10条，共1页，共{len(dtcs)}条")

        for r, row in enumerate(dtcs):
            if len(row) == 6:
                code, desc, subsystem, status_code, fault_state, freeze_state = row
            else:
                code, desc, subsystem, status_code, fault_state = row
                freeze_state = "未读取"

            seq_item = QtWidgets.QTableWidgetItem(str(r + 1))
            seq_item.setTextAlignment(Qt.AlignCenter)
            self.fault_table.setItem(r, 0, seq_item)

            def make_center(text):
                it = QtWidgets.QTableWidgetItem(text)
                it.setTextAlignment(Qt.AlignCenter)
                return it

            self.fault_table.setItem(r, 1, make_center(code))
            self.fault_table.setItem(r, 2, make_center(desc))
            self.fault_table.setItem(r, 3, make_center(subsystem))
            self.fault_table.setItem(r, 4, make_center(status_code))
            self.fault_table.setItem(r, 5, make_center(fault_state))

            # Freeze Status with Dot
            status_widget = QtWidgets.QWidget()
            status_layout = QtWidgets.QHBoxLayout(status_widget)
            status_layout.setContentsMargins(5, 0, 5, 0)
            status_layout.setAlignment(Qt.AlignCenter)

            dot = QtWidgets.QLabel()
            dot.setFixedSize(10, 10)
            dot.setStyleSheet(f"background-color: {self._get_status_color(freeze_state)}; border-radius: 5px;")

            lbl = QtWidgets.QLabel(freeze_state)
            lbl.setStyleSheet("margin-left: 5px;")

            status_layout.addWidget(dot)
            status_layout.addWidget(lbl)
            self.fault_table.setCellWidget(r, 6, status_widget)

            # Operation Button
            op_widget = QtWidgets.QWidget()
            op_layout = QtWidgets.QHBoxLayout(op_widget)
            op_layout.setContentsMargins(0, 0, 0, 0)
            op_layout.setAlignment(Qt.AlignCenter)

            btn = QtWidgets.QPushButton("读取冻结帧")
            btn.setCursor(QtGui.QCursor(Qt.PointingHandCursor))
            btn.setProperty("row", r)
            btn.clicked.connect(self.on_click_freeze_btn)

            op_layout.addWidget(btn)
            self.fault_table.setCellWidget(r, 7, op_widget)

            self.fault_table.setRowHeight(r, 50)

        # Trigger resize adjustment after data load to ensure layout is correct
        QtCore.QTimer.singleShot(0, self.adjust_column_widths)

    def populate_freeze_frame(self, data):
        """
        Populate the freeze frame table.
        data: List of freeze frame records.
        Each record structure:
        {
            "code": "P31AE87",
            "desc": "...",
            "type": "Type A",
            "did": "0x0501",
            "length": 8,
            "params": [
                {"byte": "0~1", "bit": "All", "name": "Speed", "value": "100", "unit": "km/h"},
                ...
            ]
        }
        """
        self.freeze_table.setRowCount(0)
        row_idx = 0

        for item in data:
            params = item.get("params", [])
            start_row = row_idx
            count = len(params)

            self.freeze_table.setRowCount(start_row + count)

            # Common columns (merged)
            # 0: Code, 1: Desc, 2: Type, 3: DID, 4: Length
            common_vals = [item["code"], item["desc"], item["type"], item["did"], str(item["length"])]

            for i, val in enumerate(common_vals):
                it = QtWidgets.QTableWidgetItem(val)
                it.setTextAlignment(Qt.AlignCenter)
                self.freeze_table.setItem(start_row, i, it)
                if count > 1:
                    self.freeze_table.setSpan(start_row, i, count, 1)

            # Param columns
            for p_idx, param in enumerate(params):
                r = start_row + p_idx

                def set_item(c, txt):
                    it = QtWidgets.QTableWidgetItem(str(txt))
                    it.setTextAlignment(Qt.AlignCenter)
                    self.freeze_table.setItem(r, c, it)

                set_item(5, param["byte"])
                set_item(6, param["bit"])
                set_item(7, param["name"])
                set_item(8, param["value"])
                set_item(9, param["unit"])

                self.freeze_table.setRowHeight(r, 40)

            row_idx += count

    def _get_status_color(self, text):
        color_map = {
            "未读取": "#94A3B8",
            "读取中...": "#3B82F6",
            "读取成功": "#10B981",
            "读取失败": "#EF4444"
        }
        return color_map.get(text, "#94A3B8")

    def set_last_read_time(self, dt: datetime):
        txt = f"最后读取时间：{dt.strftime('%Y-%m-%d %H:%M:%S.%f')}"
        self.last_read_label.setText(txt)
        self.freeze_time_label.setText(txt)

    def showEvent(self, event):
        super().showEvent(event)
        QtCore.QTimer.singleShot(0, self.adjust_column_widths)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.adjust_column_widths()

    def on_read_dtcs(self):
        # Emit signal instead of handling logic
        self.read_dtc_signal.emit()

    def on_clear_dtcs(self):
        self.clear_dtc_signal.emit()

    def on_click_freeze_btn(self):
        btn = self.sender()
        if not btn:
            return
        row = btn.property("row")
        self.read_freeze_frame_signal.emit(row)

    def on_filter_group_clicked(self, btn):
        if btn == self.btn_filter_all:
            self.filter_changed_signal.emit("all")
        elif btn == self.btn_filter_curr:
            self.filter_changed_signal.emit("current")
        elif btn == self.btn_filter_hist:
            self.filter_changed_signal.emit("history")
        elif btn == self.btn_filter_pend:
            self.filter_changed_signal.emit("pending")

    def update_freeze_read_status(self, row: int, success: bool):
        # Update status dot
        status_widget = self.fault_table.cellWidget(row, 6)
        if status_widget:
            # Rebuild the widget content
            # Clear layout
            layout = status_widget.layout()
            while layout.count():
                child = layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()

            new_text = "读取成功" if success else "读取失败"

            dot = QtWidgets.QLabel()
            dot.setFixedSize(10, 10)
            dot.setStyleSheet(f"background-color: {self._get_status_color(new_text)}; border-radius: 5px;")

            lbl = QtWidgets.QLabel(new_text)
            lbl.setStyleSheet("margin-left: 5px;")

            layout.addWidget(dot)
            layout.addWidget(lbl)

            if success:
                # Switch to freeze tab and show mock data
                # In real app, controller would call populate_freeze_frame
                self.tab_widget.setCurrentIndex(1)

    def eventFilter(self, source, event):
        if source == self.fault_table and event.type() == QtCore.QEvent.Resize:
            self.adjust_column_widths()
        return super().eventFilter(source, event)

    def adjust_column_widths(self):
        if not self.fault_table or self.fault_table.columnCount() == 0:
            return

        # Total available width
        total_width = self.fault_table.viewport().width()
        if total_width <= 0:
            return

        # Column 0 is ResizeToContents, get its current width
        col0_width = self.fault_table.columnWidth(0)

        # Remaining width to distribute
        # Subtract a small buffer (2px) to prevent horizontal scrollbar flickering
        available = total_width - col0_width - 2
        if available <= 0:
            return

        # Ratios (approximate based on users fixed widths: 300, 700, 300...)
        # 1: 3, 2: 7, 3: 3, 4: 3, 5: 3, 6: 3, 7: 3
        # Total parts = 25
        parts = {1: 3, 2: 7, 3: 3, 4: 3, 5: 3, 6: 3, 7: 3}
        total_parts = sum(parts.values())

        used_width = 0

        # Set all except description (Col 2) first
        cols_to_set = [1, 3, 4, 5, 6, 7]
        for col in cols_to_set:
            part = parts.get(col, 0)
            if part > 0:
                width = int((part / total_parts) * available)
                self.fault_table.setColumnWidth(col, width)
                used_width += width

        # Give remaining to Description (Col 2)
        desc_width = available - used_width
        # Ensure it's not negative
        if desc_width > 0:
            self.fault_table.setColumnWidth(2, desc_width)
