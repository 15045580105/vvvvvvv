# python
from datetime import datetime
from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtCore import Qt

from app.common.log.operation_log_manager import OperationLogManager
from app.common.ui.widgets import ModernButton
from app.common.ui.log_splitter import LogAreaSplitter
from app.common.ui.log_panel import LogPanelBuilder
from app.presentation.views.base_view import BaseView


class DTCSortHeader(QtWidgets.QHeaderView):
    """自定义表头，绘制醒目的排序指示器（带背景圆角矩形 + 大箭头）"""

    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self._sort_logical_index = -1
        self._sort_order = Qt.AscendingOrder

    def setCustomSort(self, logical_index: int, order: Qt.SortOrder):
        """设置自定义排序状态并重绘表头。"""
        self._sort_logical_index = logical_index
        self._sort_order = order
        self.viewport().update()

    def paintSection(self, painter, rect, logicalIndex):
        painter.save()
        super().paintSection(painter, rect, logicalIndex)
        painter.restore()

        if logicalIndex == self._sort_logical_index:
            painter.save()
            painter.setRenderHint(QtGui.QPainter.Antialiasing)

            # 右侧绘制醒目的靛蓝色竖条作为排序标识
            bar_width = 4
            bar_margin = 6
            bar_rect = QtCore.QRect(
                rect.right() - bar_margin - bar_width,
                rect.top() + 4,
                bar_width,
                rect.height() - 8
            )
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(QtGui.QColor("#4338CA"))
            painter.drawRoundedRect(bar_rect, 2, 2)

            # 箭头配置
            arrow_size = 5
            margin_right = bar_margin + bar_width + 6

            cx = rect.right() - margin_right - arrow_size
            cy = rect.center().y()

            arrow_color = QtGui.QColor("#4338CA")
            painter.setBrush(arrow_color)
            painter.setPen(QtCore.Qt.NoPen)

            path = QtGui.QPainterPath()
            if self._sort_order == Qt.AscendingOrder:
                path.moveTo(cx, cy - arrow_size)
                path.lineTo(cx - arrow_size, cy + arrow_size)
                path.lineTo(cx + arrow_size, cy + arrow_size)
            else:
                path.moveTo(cx, cy + arrow_size)
                path.lineTo(cx - arrow_size, cy - arrow_size)
                path.lineTo(cx + arrow_size, cy - arrow_size)

            path.closeSubpath()
            painter.drawPath(path)
            painter.restore()


class DTCView(BaseView):
    read_dtc_signal = QtCore.pyqtSignal()
    read_freeze_frame_signal = QtCore.pyqtSignal(str)
    filter_changed_signal = QtCore.pyqtSignal(str)
    clear_dtc_signal = QtCore.pyqtSignal()
    search_changed_signal = QtCore.pyqtSignal(str)

    def setup_ui(self):
        # Main Layout
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Splitter
        self.splitter = LogAreaSplitter(self, min_log_height=150, max_log_ratio=0.8)
        main_layout.addWidget(self.splitter)

        content_widget = QtWidgets.QWidget()
        content_layout = QtWidgets.QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # Top Container
        self.top_widget = QtWidgets.QWidget()
        top_layout = QtWidgets.QVBoxLayout(self.top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(0)
        content_layout.addWidget(self.top_widget)

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
        self.clear_btn.clicked.connect(self.on_clear_dtc_clicked)

        # Log Window (Output)
        log_group = QtWidgets.QGroupBox("操作日志")
        log_layout = QtWidgets.QVBoxLayout(log_group)
        log_layout.setContentsMargins(8, 12, 8, 8)
        self.log_edit = QtWidgets.QPlainTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setMaximumBlockCount(500)
        self.log_edit.setMinimumHeight(0)
        LogPanelBuilder.attach_search(log_layout, self.log_edit)
        log_layout.addWidget(self.log_edit)

        self.splitter.set_panels(content_widget, log_group, initial_log_height=100)


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

        # Search Box Container
        search_container = QtWidgets.QWidget()
        search_container.setFixedSize(304, 36)
        search_layout = QtWidgets.QHBoxLayout(search_container)
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_layout.setSpacing(0)

        self.search_input = QtWidgets.QLineEdit()
        self.search_input.setPlaceholderText("在此搜索故障码或描述...")
        self.search_input.setFixedSize(260, 36)
        self.search_input.setStyleSheet("""
            QLineEdit {
                border: 1px solid #E5E7EB;
                border-right: none;
                border-top-left-radius: 4px;
                border-bottom-left-radius: 4px;
                border-top-right-radius: 0px;
                border-bottom-right-radius: 0px;
                padding: 4px 10px;
                background: white;
            }
            QLineEdit:focus {
                border-color: #3B82F6;
            }
        """)

        self.search_btn = ModernButton("🔍", "#6B7280", "")
        self.search_btn.setToolTip("执行搜索")
        self.search_btn.setFixedSize(44, 36)
        # 覆写按钮的圆角以实现右边圆左边平的紧贴效果
        self.search_btn.setStyleSheet(self.search_btn.styleSheet() + """
            QPushButton { 
                border-top-left-radius: 0px; 
                border-bottom-left-radius: 0px; 
                border-top-right-radius: 4px; 
                border-bottom-right-radius: 4px; 
            }
        """)

        search_layout.addWidget(self.search_input)
        search_layout.addWidget(self.search_btn)

        self.search_input.returnPressed.connect(self.on_search_triggered)
        self.search_btn.clicked.connect(self.on_search_triggered)

        header_layout.addWidget(search_container)

        header_layout.addSpacing(10)

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
        cols = ["序号", "故障码", "故障描述", "上报子系统", "状态码", "故障状态", "冻结帧状态", "冻结帧操作", "冻结帧数据"]
        self.fault_table.setColumnCount(len(cols))
        self.fault_table.setHorizontalHeaderLabels(cols)
        self.fault_table.verticalHeader().setVisible(False)
        self.fault_table.setAlternatingRowColors(True)
        self.fault_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        header = DTCSortHeader(Qt.Horizontal, self.fault_table)
        self.fault_table.setHorizontalHeader(header)
        header.setSectionResizeMode(QtWidgets.QHeaderView.Interactive)
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self.fault_table.columnCount() - 1, QtWidgets.QHeaderView.Stretch)
        # 冻结帧状态列（第6列）和操作列（第7列）设置初始宽度确保文字/按钮显示完整
        header.setMinimumSectionSize(50)
        header.resizeSection(6, 150)
        header.resizeSection(7, 110)
        header.setStretchLastSection(False)
        header.setSectionsClickable(True)
        header.setHighlightSections(True)
        header.setSectionsMovable(True)
        header.sectionResized.connect(lambda *_: self.adjust_column_widths())

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

        freeze_header = self.freeze_table.horizontalHeader()
        freeze_header.setSectionResizeMode(QtWidgets.QHeaderView.Interactive)
        freeze_header.setSectionsClickable(True)
        freeze_header.setHighlightSections(True)
        freeze_header.setSectionsMovable(True)
        freeze_header.setStretchLastSection(False)

        self._freeze_column_weights = {
            0: 12,  # 故障码
            1: 22,  # 故障描述
            2: 11,  # 类型
            3: 10,  # DID
            4: 7,   # 长度
            5: 7,   # Byte
            6: 7,   # Bit
            7: 22,  # 参数名称
            8: 16,  # 数值
            9: 5,   # 单位（最后一列填充）
        }
        self._freeze_min_widths = {
            0: 110,
            1: 200,
            2: 100,
            3: 90,
            4: 70,
            5: 70,
            6: 70,
            7: 200,
            8: 140,
            9: 60,
        }
        self._freeze_widths_initialized = False

        self.freeze_table.setShowGrid(True)
        self.freeze_table.setFrameShape(QtWidgets.QFrame.NoFrame)

        layout.addWidget(self.freeze_table)
        QtCore.QTimer.singleShot(0, lambda: self._apply_freeze_table_widths(force=True))

    def append_log(self, message: str):
        OperationLogManager.instance().append_log("DTC故障诊断", message)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        log_entry = f"[{ts}] {message}"

        if hasattr(self, 'log_edit'):
            color = "#374151"
            if "TX:" in message or "TX " in message:
                color = "#2563EB"
            elif "RX:" in message or "RX " in message:
                color = "#059669"
            elif "Error" in message or "失败" in message or "错误" in message or "Fail" in message:
                color = "#DC2626"
            elif "Warning" in message or "警告" in message:
                color = "#D97706"

            log_escaped = log_entry.replace("<", "&lt;").replace(">", "&gt;")
            html_msg = f'<span style="color: {color};">{log_escaped}</span>'

            self.log_edit.appendHtml(html_msg)
            # Scroll to bottom
            self.log_edit.moveCursor(QtGui.QTextCursor.End)
        else:
            print(log_entry)

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

        # Optimize GUI refresh
        self.fault_table.setUpdatesEnabled(False)
        self.fault_table.blockSignals(True)
        try:
            # Update Fault Table
            self.fault_table.setRowCount(len(dtcs))

            # Update Pagination Info (Mock)
            self.page_info_label.setText(f"每页显示10条，共1页，共{len(dtcs)}条")

            for r, row in enumerate(dtcs):
                if len(row) >= 7:
                    code, desc, subsystem, status_code, fault_state, freeze_state = row[:6]
                    freeze_data = row[6]
                elif len(row) == 6:
                    code, desc, subsystem, status_code, fault_state, freeze_state = row
                    freeze_data = ""
                else:
                    code, desc, subsystem, status_code, fault_state = row
                    freeze_state = "未读取"
                    freeze_data = ""

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

                # Freeze Status - 使用QTableWidgetItem自动裁剪避免溢出
                status_item = QtWidgets.QTableWidgetItem(f"● {freeze_state}")
                status_item.setTextAlignment(Qt.AlignCenter)
                status_item.setForeground(QtGui.QColor(self._get_status_color(freeze_state)))
                self.fault_table.setItem(r, 6, status_item)

                # Operation Button
                op_widget = QtWidgets.QWidget()
                op_layout = QtWidgets.QHBoxLayout(op_widget)
                op_layout.setContentsMargins(0, 0, 0, 0)
                op_layout.setAlignment(Qt.AlignCenter)

                btn = QtWidgets.QPushButton("读取冻结帧")
                btn.setCursor(QtGui.QCursor(Qt.PointingHandCursor))
                btn.setProperty("dtc_code", code)
                btn.setMinimumWidth(90)
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #3B82F6;
                        color: white;
                        border: none;
                        border-radius: 4px;
                        padding: 4px 10px;
                        font-size: 13px;
                        font-family: "Microsoft YaHei";
                    }
                    QPushButton:hover { background-color: #2563EB; }
                    QPushButton:pressed { background-color: #1D4ED8; }
                    QPushButton:disabled {
                        background-color: #CBD5E1;
                        color: #94A3B8;
                    }
                """)
                btn.clicked.connect(self.on_click_freeze_btn)

                op_layout.addWidget(btn)
                self.fault_table.setCellWidget(r, 7, op_widget)

                # Freeze Data
                data_item = make_center(freeze_data)
                data_item.setToolTip(freeze_data)
                self.fault_table.setItem(r, 8, data_item)

                self.fault_table.setRowHeight(r, 50)
        finally:
            self.fault_table.blockSignals(False)
            self.fault_table.setUpdatesEnabled(True)
            self.fault_table.viewport().update()

        # Trigger resize adjustment after data load to ensure layout is correct
        QtCore.QTimer.singleShot(0, self.adjust_column_widths)

    def populate_freeze_frame(self, data):
        """
        Populate the freeze frame table.
        """
        self.freeze_table.setUpdatesEnabled(False)
        self.freeze_table.blockSignals(True)
        try:
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
        finally:
            self.freeze_table.blockSignals(False)
            self.freeze_table.setUpdatesEnabled(True)
            self.freeze_table.viewport().update()

        # 数据加载后重新应用列宽
        QtCore.QTimer.singleShot(0, lambda: self._apply_freeze_table_widths(force=True))

    def _get_status_color(self, text):
        color_map = {
            "未读取": "#94A3B8",
            "读取中...": "#3B82F6",
            "读取成功解析成功": "#10B981",
            "读取成功解析失败": "#F59E0B",
            "读取失败": "#EF4444"
        }
        if text == "读取成功":
            return "#10B981"
        return color_map.get(text, "#94A3B8")

    def set_last_read_time(self, dt: datetime):
        txt = f"最后读取时间：{dt.strftime('%Y-%m-%d %H:%M:%S.%f')}"
        self.last_read_label.setText(txt)
        self.freeze_time_label.setText(txt)

    def showEvent(self, event):
        super().showEvent(event)
        QtCore.QTimer.singleShot(0, self.adjust_column_widths)
        QtCore.QTimer.singleShot(0, lambda: self._apply_freeze_table_widths(force=not self._freeze_widths_initialized))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.adjust_column_widths()

    def on_read_dtcs(self):
        # Emit signal instead of handling logic
        self.read_dtc_signal.emit()

    def on_clear_dtc_clicked(self):
        OperationLogManager.instance().append_log("UI", "点击清除故障码")
        self.clear_dtc_signal.emit()

    def on_search_triggered(self):
        text = self.search_input.text()
        self.search_changed_signal.emit(text)

    def on_filter_group_clicked(self, btn):
        # 根据点击的按钮发送对应的筛选标识
        if btn == self.btn_filter_all:
            filter_key = "all"
        elif btn == self.btn_filter_curr:
            filter_key = "current"
        elif btn == self.btn_filter_hist:
            filter_key = "history"
        elif btn == self.btn_filter_pend:
            filter_key = "pending"
        else:
            filter_key = "all"
        self.filter_changed_signal.emit(filter_key)

    def on_click_freeze_btn(self):
        btn = self.sender()
        if btn:
            dtc_code = btn.property("dtc_code")
            if dtc_code:
                self.read_freeze_frame_signal.emit(dtc_code)

    def update_freeze_read_status_by_code(self, dtc_code, status_str, freeze_data):
        """通过 DTC 码查找可视行并更新冻结帧状态和数据"""
        for row in range(self.fault_table.rowCount()):
            item = self.fault_table.item(row, 1)
            if item and item.text() == dtc_code:
                self.update_freeze_read_status(row, status_str, freeze_data)
                return

    def update_freeze_read_status(self, row_index, status_str, freeze_data):
        """更新指定行的冻结帧状态和数据"""
        if row_index < 0 or row_index >= self.fault_table.rowCount():
            return

        # 更新冻结帧状态（第6列）- QTableWidgetItem自动裁剪不会溢出
        status_item = self.fault_table.item(row_index, 6)
        if status_item:
            color = self._get_status_color(status_str)
            status_item.setText(f"● {status_str}")
            status_item.setForeground(QtGui.QColor(color))

        # 更新冻结帧数据（第8列）
        if freeze_data:
            data_item = QtWidgets.QTableWidgetItem(freeze_data)
            data_item.setTextAlignment(Qt.AlignCenter)
            data_item.setToolTip(freeze_data)
            self.fault_table.setItem(row_index, 8, data_item)

    def set_freeze_buttons_enabled(self, enabled):
        """启用/禁用所有冻结帧读取按钮"""
        for row in range(self.fault_table.rowCount()):
            op_widget = self.fault_table.cellWidget(row, 7)
            if op_widget:
                btn = op_widget.findChild(QtWidgets.QPushButton)
                if btn:
                    btn.setEnabled(enabled)

    def on_device_status_changed(self, is_connected):
        pass

    def adjust_column_widths(self):
        if not self.fault_table or self.fault_table.columnCount() == 0:
            return

        header = self.fault_table.horizontalHeader()
        total_width = self.fault_table.viewport().width()
        if total_width <= 0:
            return

        last_col = self.fault_table.columnCount() - 1

        try:
            header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
            for col in range(1, last_col):
                header.setSectionResizeMode(col, QtWidgets.QHeaderView.Interactive)
            header.setSectionResizeMode(last_col, QtWidgets.QHeaderView.Stretch)
        except Exception:
            pass

        # 确保冻结帧状态列（第6列）和操作列（第7列）有足够宽度
        if self.fault_table.columnCount() > 7:
            if self.fault_table.columnWidth(6) < 150:
                try:
                    header.resizeSection(6, 150)
                except Exception:
                    pass
            if self.fault_table.columnWidth(7) < 110:
                try:
                    header.resizeSection(7, 110)
                except Exception:
                    pass

    def _apply_freeze_table_widths(self, force: bool = False):
        if not hasattr(self, 'freeze_table') or not self.freeze_table:
            return
        header = self.freeze_table.horizontalHeader()
        column_count = self.freeze_table.columnCount()
        if column_count == 0:
            return

        total_width = self.freeze_table.viewport().width()
        if total_width <= 0:
            return

        if not force and self._freeze_widths_initialized:
            return

        # 参数名称列(col 7)做Stretch填充剩余空间，单位列(col 9)固定窄宽度
        stretch_col = 7   # 参数名称
        unit_col = 9      # 单位
        unit_width = 60   # 单位列固定宽度

        mins = self._freeze_min_widths

        try:
            # 所有列先设为Interactive
            for col in range(column_count):
                header.setSectionResizeMode(col, QtWidgets.QHeaderView.Interactive)
            # 参数名称列做Stretch
            header.setSectionResizeMode(stretch_col, QtWidgets.QHeaderView.Stretch)
        except Exception:
            pass

        # 计算除 stretch_col 和 unit_col 外的固定列宽
        # 使用简单的固定最小宽度分配
        fixed_widths = {
            0: mins.get(0, 110),   # 故障码
            1: mins.get(1, 200),   # 故障描述
            2: mins.get(2, 100),   # 类型
            3: mins.get(3, 90),    # DID
            4: mins.get(4, 70),    # 长度
            5: mins.get(5, 70),    # Byte
            6: mins.get(6, 70),    # Bit
            8: mins.get(8, 140),   # 数值
        }

        try:
            # 设置固定宽度列
            for col, width in fixed_widths.items():
                if col < column_count:
                    self.freeze_table.setColumnWidth(col, width)

            # 单位列固定窄宽度
            if unit_col < column_count:
                self.freeze_table.setColumnWidth(unit_col, unit_width)

            # stretch_col(参数名称)由Qt自动管理Stretch填充剩余空间，无需手动设置
            self._freeze_widths_initialized = True
        except Exception:
            pass
