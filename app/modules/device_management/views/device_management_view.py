from PyQt5 import QtWidgets, QtGui
from PyQt5.QtWidgets import QHeaderView
from PyQt5.QtCore import Qt as _Qt
from PyQt5.QtCore import QDateTime, QEvent, QTimer, QSettings, pyqtSignal

from app.common.ui.widgets import ModernButton, TableButton, LoadingSpinner, ResponsiveButtonFlowPanel
from app.common.log.operation_log_manager import OperationLogManager
from app.modules.device_management.models.device_model import CONNECTING
from app.presentation.views.base_view import BaseView
from app.common.ui.log_splitter import LogAreaSplitter
from app.common.ui.log_panel import LogPanelBuilder

# QLabel 需要使用 Qt.AlignmentFlag；QTableWidgetItem 则继续使用 int 对齐值。
if hasattr(_Qt, "AlignmentFlag"):
    ALIGN_LEFT_LABEL = _Qt.AlignmentFlag.AlignLeft | _Qt.AlignmentFlag.AlignVCenter
else:
    ALIGN_LEFT_LABEL = _Qt.AlignLeft | _Qt.AlignVCenter
ALIGN_CENTER_ITEM = int(_Qt.AlignCenter)
ELIDE_RIGHT = _Qt.ElideRight if hasattr(_Qt, "ElideRight") else getattr(_Qt.TextElideMode, "ElideRight", 1)
CONTEXT_MENU_POLICY = _Qt.DefaultContextMenu if hasattr(_Qt, "DefaultContextMenu") else _Qt.ContextMenuPolicy.DefaultContextMenu
HEADER_INTERACTIVE_MODE = QHeaderView.Interactive if hasattr(QHeaderView, "Interactive") else QHeaderView.ResizeMode.Interactive
SCROLLBAR_ALWAYS_OFF = _Qt.ScrollBarAlwaysOff if hasattr(_Qt, "ScrollBarAlwaysOff") else _Qt.ScrollBarPolicy.ScrollBarAlwaysOff
ONLINE_ICON = "🟩"
OFFLINE_ICON = "🟥"


class DeviceView(BaseView):
    log_link_clicked = pyqtSignal(str)

    def _open_settings(self, page_id: str):
        main_win = self.window()
        if main_win and hasattr(main_win, "show_settings_dialog"):
            main_win.show_settings_dialog(page_id)
            if hasattr(main_win, "settings_controller") and main_win.settings_controller:
                from PyQt5 import QtCore
                view = main_win.settings_controller.view
                view.setWindowModality(QtCore.Qt.ApplicationModal)
                view.setWindowFlags(view.windowFlags() | QtCore.Qt.WindowStaysOnTopHint)
                view.show()
                view.raise_()
                view.activateWindow()

    def _create_help_button(self, tooltip_text: str, btn_text: str):
        btn = QtWidgets.QPushButton(btn_text)
        btn.setToolTip(tooltip_text)
        btn.setFixedHeight(24)
        btn.setStyleSheet("""
            QPushButton {
                background-color: #E5E7EB;
                color: #4B5563;
                border-radius: 12px;
                font-weight: bold;
                font-size: 12px;
                padding: 0px 10px;
                border: none;
            }
            QPushButton:hover {
                background-color: #D1D5DB;
            }
            QPushButton:pressed {
                background-color: #9CA3AF;
            }
        """)
        return btn

    def setup_ui(self):
        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.setSpacing(16)

        # 防止程序性 setColumnWidth 再次触发表头回调造成递归。
        self._table_layout_updating = False

        # 统一维护设备表列索引与尺寸阈值，方便后期扩展。
        self._status_column = 7
        self._detail_column = 8
        self._column_ids = tuple(range(9))
        self._compact_action_threshold = 236
        self._compact_viewport_threshold = 1366
        self._input_widgets = []
        # 小屏下优先压缩详情，再压缩一般信息列；连接状态最后压缩，保证可读性。
        self._column_shrink_priority = [8, 5, 6, 1, 3, 2, 4, 0, 7]
        # 有额外空间时优先补给连接状态与操作列，让关键操作更突出。
        self._column_grow_priority = [7, 8, 5, 3, 1, 6, 2, 4, 0]

        self._settings = QSettings("oneboxforgac", "device_management")
        self._column_settings_key = "device_table/column_widths_v1"
        self._user_column_widths = {}
        self._pending_width_persist = False
        self._column_persist_timer = QTimer(self)
        self._column_persist_timer.setSingleShot(True)
        self._column_persist_timer.setInterval(240)
        self._column_persist_timer.timeout.connect(self._persist_column_widths)

        self._column_profiles = [
            {
                "min_viewport": 1680,
                "preferred_widths": {0: 56, 1: 140, 2: 96, 3: 150, 4: 82, 5: 160, 6: 124, 7: 176, 8: 300},
                "min_widths": {0: 48, 1: 112, 2: 76, 3: 118, 4: 66, 5: 126, 6: 96, 7: 128, 8: 150},
            },
            {
                "min_viewport": 1440,
                "preferred_widths": {0: 52, 1: 126, 2: 88, 3: 136, 4: 76, 5: 146, 6: 114, 7: 160, 8: 250},
                "min_widths": {0: 46, 1: 104, 2: 72, 3: 112, 4: 64, 5: 118, 6: 92, 7: 124, 8: 140},
            },
            {
                "min_viewport": 1320,
                "preferred_widths": {0: 46, 1: 110, 2: 76, 3: 118, 4: 68, 5: 126, 6: 94, 7: 170, 8: 200},
                "min_widths": {0: 40, 1: 90, 2: 62, 3: 100, 4: 56, 5: 102, 6: 74, 7: 136, 8: 102},
            },
            {
                "min_viewport": 1200,
                "preferred_widths": {0: 46, 1: 108, 2: 76, 3: 116, 4: 68, 5: 126, 6: 96, 7: 156, 8: 180},
                "min_widths": {0: 40, 1: 88, 2: 62, 3: 98, 4: 56, 5: 100, 6: 76, 7: 128, 8: 100},
            },
            {
                "min_viewport": 0,
                "preferred_widths": {0: 42, 1: 98, 2: 70, 3: 108, 4: 62, 5: 116, 6: 88, 7: 144, 8: 150},
                "min_widths": {0: 38, 1: 82, 2: 60, 3: 92, 4: 52, 5: 94, 6: 72, 7: 120, 8: 96},
            },
        ]

        self.log_splitter = LogAreaSplitter(self, min_log_height=150, max_log_ratio=0.8)
        self.layout.addWidget(self.log_splitter)
        content_widget = QtWidgets.QWidget()
        content_layout = QtWidgets.QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(16)

        # 输入区根据可用宽度自动分栏，小屏也不会挤压到不可见。
        input_group = QtWidgets.QGroupBox("添加设备")
        input_vlayout = QtWidgets.QVBoxLayout(input_group)
        input_vlayout.setSpacing(12)

        # 基本信息布局
        base_info_layout = QtWidgets.QFormLayout()
        self.name_input = QtWidgets.QLineEdit()
        self.type_input = QtWidgets.QComboBox()
        self.type_input.addItems(["ECU", "网关", "域控", "其他"])
        base_info_layout.addRow("设备名：", self.name_input)
        base_info_layout.addRow("设备类型：", self.type_input)

        # 协议配置Tabs
        self.protocol_tabs = QtWidgets.QTabWidget()
        
        # DoIP Tab
        self.doip_tab = QtWidgets.QWidget()
        doip_layout = QtWidgets.QFormLayout(self.doip_tab)
        doip_layout.setContentsMargins(16, 16, 16, 16)
        self.doip_ip_input = QtWidgets.QLineEdit()
        self.doip_ip_input.setPlaceholderText("例: 192.168.1.100")
        self.doip_port_input = QtWidgets.QLineEdit("13400")
        doip_layout.addRow("DoIP IP：", self.doip_ip_input)
        doip_layout.addRow("DoIP 端口：", self.doip_port_input)

        self.btn_doip_adv = self._create_help_button("Doip层高级配置", "DoIP ⚙")
        self.btn_diag_adv = self._create_help_button("诊断层高级配置", "诊断 ⚙")
        self.btn_doip_adv.clicked.connect(lambda: self._open_settings("doip"))
        self.btn_diag_adv.clicked.connect(lambda: self._open_settings("diag_layer"))
        doip_btn_layout = QtWidgets.QHBoxLayout()
        doip_btn_layout.addWidget(QtWidgets.QLabel("高级配置："))
        doip_btn_layout.addWidget(self.btn_doip_adv)
        doip_btn_layout.addWidget(self.btn_diag_adv)
        doip_btn_layout.addStretch()
        doip_layout.addRow(doip_btn_layout)

        # SomeIP Tab
        self.someip_tab = QtWidgets.QWidget()
        someip_layout = QtWidgets.QFormLayout(self.someip_tab)
        someip_layout.setContentsMargins(16, 16, 16, 16)
        self.someip_ip_input = QtWidgets.QLineEdit()
        self.someip_ip_input.setPlaceholderText("选填，SomeIP 目标 IP")
        self.multicast_ip_input = QtWidgets.QLineEdit("239.71.0.2")
        self.multicast_port_input = QtWidgets.QLineEdit("30490")
        self.vlan_id_input = QtWidgets.QLineEdit("4")
        self.client_port_input = QtWidgets.QLineEdit("30813")
        self.client_id_input = QtWidgets.QLineEdit("30813")
        someip_layout.addRow("SomeIP IP：", self.someip_ip_input)
        someip_layout.addRow("标准组播 IP：", self.multicast_ip_input)
        someip_layout.addRow("标准组播端口：", self.multicast_port_input)
        someip_layout.addRow("VLAN ID：", self.vlan_id_input)
        someip_layout.addRow("客户端端口：", self.client_port_input)
        someip_layout.addRow("客户端 ID：", self.client_id_input)

        self.btn_someip_adv = self._create_help_button("someip高级配置", "SomeIP ⚙")
        self.btn_someip_adv.clicked.connect(lambda: self._open_settings("someip"))
        someip_btn_layout = QtWidgets.QHBoxLayout()
        someip_btn_layout.addWidget(QtWidgets.QLabel("高级配置："))
        someip_btn_layout.addWidget(self.btn_someip_adv)
        someip_btn_layout.addStretch()
        someip_layout.addRow(someip_btn_layout)

        # SSH Tab
        self.ssh_tab = QtWidgets.QWidget()
        ssh_layout = QtWidgets.QFormLayout(self.ssh_tab)
        ssh_layout.setContentsMargins(16, 16, 16, 16)
        self.ssh_ip_input = QtWidgets.QLineEdit()
        self.ssh_ip_input.setPlaceholderText("选填，若为空则同 DoIP IP")
        self.ssh_port_input = QtWidgets.QLineEdit("22")
        self.user_input = QtWidgets.QLineEdit()
        self.password_input = QtWidgets.QLineEdit()
        self.password_input.setEchoMode(QtWidgets.QLineEdit.Password)
        ssh_layout.addRow("SSH IP：", self.ssh_ip_input)
        ssh_layout.addRow("SSH 端口：", self.ssh_port_input)
        ssh_layout.addRow("用户名：", self.user_input)
        ssh_layout.addRow("密码：", self.password_input)

        self.protocol_tabs.addTab(self.doip_tab, "DoIP")
        self.protocol_tabs.addTab(self.someip_tab, "SomeIP")
        self.protocol_tabs.addTab(self.ssh_tab, "SSH")

        self.add_btn = ModernButton("添加设备", "#0EA5E9", "➕")
        self.add_btn.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

        input_vlayout.addLayout(base_info_layout)
        input_vlayout.addWidget(self.protocol_tabs)
        input_vlayout.addWidget(self.add_btn)
        input_vlayout.addStretch()

        self.main_h_splitter = QtWidgets.QSplitter(_Qt.Horizontal)
        input_group.setMinimumWidth(320)
        self.main_h_splitter.addWidget(input_group)

        right_panel = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        # 顶部操作工具栏 (Toolbar)
        toolbar_layout = QtWidgets.QHBoxLayout()
        self.toolbar_doip_btn = ModernButton("连接 DoIP", "#10B981", "🔌")
        self.toolbar_ssh_btn = ModernButton("连接 SSH", "#10B981", "🔌")
        self.toolbar_someip_btn = ModernButton("连接 SomeIP", "#10B981", "🔌")

        toolbar_layout.addWidget(self.toolbar_doip_btn)
        toolbar_layout.addWidget(self.toolbar_ssh_btn)
        toolbar_layout.addWidget(self.toolbar_someip_btn)
        toolbar_layout.addSpacing(16)

        self.toolbar_edit_btn = ModernButton("修改信息", "#3B82F6", "✏️")
        self.toolbar_delete_btn = ModernButton("删除设备", "#EF4444", "🗑️")
        self.toolbar_upgrade_btn = ModernButton("软件升级", "#6366F1", "⏫")
        self.toolbar_query_btn = ModernButton("状态查询", "#0EA5E9", "🔍")

        toolbar_layout.addWidget(self.toolbar_edit_btn)
        toolbar_layout.addWidget(self.toolbar_upgrade_btn)
        toolbar_layout.addWidget(self.toolbar_query_btn)
        toolbar_layout.addWidget(self.toolbar_delete_btn)
        toolbar_layout.addStretch()

        self.toolbar_btns = (self.toolbar_doip_btn, self.toolbar_ssh_btn, self.toolbar_someip_btn,
                             self.toolbar_edit_btn, self.toolbar_delete_btn, self.toolbar_upgrade_btn, self.toolbar_query_btn)
        for btn in self.toolbar_btns:
            btn.setEnabled(False)
            btn.setFixedHeight(32)

        right_layout.addLayout(toolbar_layout)

        # 表格宽度始终与视口一致，不依赖水平滚动条。
        self.table = QtWidgets.QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels([
            "序号", "设备名", "设备类型", "IP地址", "SSH端口",
            "标准组播 IP", "标准组播端口", "连接状态", "详情"
        ])
        self.table.verticalHeader().setVisible(False)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(ELIDE_RIGHT)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setHorizontalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        self.table.setHorizontalScrollBarPolicy(SCROLLBAR_ALWAYS_OFF)
        self.table.setContextMenuPolicy(CONTEXT_MENU_POLICY)

        vheader = self.table.verticalHeader()
        vheader.setDefaultSectionSize(64)
        vheader.setMinimumSectionSize(56)

        hheader = self.table.horizontalHeader()
        hheader.setSectionResizeMode(HEADER_INTERACTIVE_MODE)
        hheader.setStretchLastSection(True)
        hheader.setMinimumSectionSize(56)

        for column, width in self._default_column_widths(max(1280, self.width())).items():
            if column < 9:
                self.table.setColumnWidth(column, width)

        self._restore_user_column_widths()

        right_layout.addWidget(self.table)
        self.main_h_splitter.addWidget(right_panel)
        self.main_h_splitter.setSizes([380, 1200])
        self.main_h_splitter.setStretchFactor(0, 0)
        self.main_h_splitter.setStretchFactor(1, 1)

        content_layout.addWidget(self.main_h_splitter)

        self.table.horizontalHeader().sectionResized.connect(self._on_header_section_resized)
        self.table.viewport().installEventFilter(self)
        self.table.itemSelectionChanged.connect(self._on_table_selection)

        log_group = QtWidgets.QGroupBox("操作日志")
        log_layout = QtWidgets.QVBoxLayout()
        self.log_view = QtWidgets.QTextBrowser()
        self.log_view.setReadOnly(True)
        self.log_view.setOpenLinks(False)
        self.log_view.setOpenExternalLinks(False)
        self.log_view.setPlaceholderText("这里显示用户的操作日志...")
        self.log_view.anchorClicked.connect(self._on_log_anchor_clicked)
        LogPanelBuilder.attach_search(log_layout, self.log_view)
        log_layout.addWidget(self.log_view)
        log_group.setLayout(log_layout)
        self.log_splitter.set_panels(content_widget, log_group, initial_log_height=100)

        self._refresh_table_layout()

    def eventFilter(self, watched, event):
        if watched is self.table.viewport() and event.type() == QEvent.Resize:
            self._refresh_table_layout()
        return super().eventFilter(watched, event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._refresh_table_layout()

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh_table_layout()

    def _on_header_section_resized(self, column, _old_size, _new_size):
        if self._table_layout_updating:
            return
        self._refresh_table_layout(resized_column=column)
        self._schedule_column_width_persist()

    def _should_use_compact_actions(self):
        return False

    def _should_use_compact_actions_for_width(self, viewport_width, action_width):
        return False

    def _is_small_screen_layout(self, viewport_width):
        return viewport_width <= 1366

    def _on_table_selection(self):
        row = self.table.currentRow()
        if not hasattr(self, "_current_devices") or row < 0 or row >= len(self._current_devices):
            for btn in self.toolbar_btns:
                btn.setEnabled(False)
            return

        for btn in self.toolbar_btns:
            btn.setEnabled(True)

        dev = self._current_devices[row]
        doip_status = str(dev.get("doip_connect_status", "离线"))
        ssh_status = str(dev.get("ssh_connect_status", "离线"))
        someip_status = str(dev.get("someip_connect_status", "离线"))

        doip_connected = "建链成功" in doip_status or "在线" in doip_status
        ssh_connected = "建链成功" in ssh_status or "在线" in ssh_status
        someip_connected = "建链成功" in someip_status or "在线" in someip_status

        self.toolbar_doip_btn.setText("断开 DoIP" if doip_connected else "连接 DoIP")
        self.toolbar_ssh_btn.setText("断开 SSH" if ssh_connected else "连接 SSH")
        self.toolbar_someip_btn.setText("断开 SomeIP" if someip_connected else "连接 SomeIP")

        # 根据状态更改按钮颜色
        def _set_btn_color(btn, connected):
            color = "#F59E0B" if connected else "#10B981"
            # ModernButton 的颜色属性只在创建时生效，如需动态变色，可以重新设置 StyleSheet，但为了简单起见，文本已足够区分

    def _refresh_table_layout(self, resized_column=None):
        if not hasattr(self, "table") or self._table_layout_updating:
            return
        self._table_layout_updating = True
        try:
            self._apply_responsive_column_hints(resized_column)
            self._refresh_row_widgets()
        finally:
            self._table_layout_updating = False

    def _relayout_input_grid(self):
        """已改用Tab布局，无需动态调整grid。"""
        pass

    def _apply_responsive_column_hints(self, resized_column=None):
        viewport_width = self.table.viewport().width()
        if viewport_width <= 0:
            return

        if resized_column is None:
            target_widths = self._target_column_widths(viewport_width)
            fitted_widths = self._fit_widths_to_viewport(target_widths, viewport_width)
        else:
            target_widths = {column: self.table.columnWidth(column) for column in self._column_ids}
            fitted_widths = self._fit_widths_to_viewport(target_widths, viewport_width, preserve_column=resized_column)
            self._user_column_widths = dict(fitted_widths)

        for column, width in fitted_widths.items():
            if self.table.columnWidth(column) != width:
                self.table.setColumnWidth(column, width)

    def _current_column_profile(self, viewport_width):
        for profile in self._column_profiles:
            if viewport_width >= profile["min_viewport"]:
                return profile
        return self._column_profiles[-1]

    def _default_column_widths(self, viewport_width):
        profile = self._current_column_profile(viewport_width)
        preferred_widths = dict(profile["preferred_widths"])
        return preferred_widths

    def _column_min_widths_for_viewport(self, viewport_width):
        profile = self._current_column_profile(viewport_width)
        min_widths = dict(profile["min_widths"])
        return min_widths

    def _target_column_widths(self, viewport_width):
        default_widths = self._default_column_widths(viewport_width)
        if not self._user_column_widths:
            return default_widths
        return {column: self._user_column_widths.get(column, default_widths[column]) for column in self._column_ids}

    def _schedule_column_width_persist(self):
        self._pending_width_persist = True
        self._column_persist_timer.start()

    def _persist_column_widths(self):
        if not self._pending_width_persist:
            return
        self._pending_width_persist = False
        self._user_column_widths = {column: self.table.columnWidth(column) for column in self._column_ids}
        serializable = {str(column): width for column, width in self._user_column_widths.items()}
        self._settings.setValue(self._column_settings_key, serializable)
        self._settings.sync()

    def _restore_user_column_widths(self):
        saved = self._settings.value(self._column_settings_key, {})
        if not saved:
            self._user_column_widths = {}
            return

        restored = {}
        items = saved.items() if isinstance(saved, dict) else []
        for key, value in items:
            try:
                restored[int(key)] = int(value)
            except (TypeError, ValueError):
                continue
        self._user_column_widths = restored

    def _fit_widths_to_viewport(self, target_widths, viewport_width, preserve_column=None):
        min_widths = self._column_min_widths_for_viewport(viewport_width)
        widths = {
            column: max(min_widths[column], int(target_widths.get(column, min_widths[column])))
            for column in self._column_ids
        }
        total_width = sum(widths.values())

        if total_width > viewport_width:
            overflow = total_width - viewport_width
            shrink_order = [column for column in self._column_shrink_priority if column != preserve_column]
            overflow = self._consume_width_delta(widths, min_widths, overflow, shrink_order, grow=False)
            if overflow > 0 and preserve_column is not None:
                self._consume_width_delta(widths, min_widths, overflow, [preserve_column], grow=False)
        elif total_width < viewport_width:
            extra = viewport_width - total_width
            grow_order = [column for column in self._column_grow_priority if column != preserve_column]
            if preserve_column is not None:
                grow_order = [preserve_column] + grow_order
            self._consume_width_delta(widths, min_widths, extra, grow_order, grow=True)

        return widths

    def _consume_width_delta(self, widths, min_widths, delta, order, *, grow):
        if delta <= 0 or not order:
            return delta

        while delta > 0:
            changed = False
            for column in order:
                if grow:
                    widths[column] += 1
                    delta -= 1
                    changed = True
                elif widths[column] > min_widths[column]:
                    widths[column] -= 1
                    delta -= 1
                    changed = True

                if delta <= 0:
                    break
            if not changed:
                break
        return delta

    def _refresh_row_widgets(self):
        compact = self._should_use_compact_actions()
        for row in range(self.table.rowCount()):
            detail_widget = self.table.cellWidget(row, self._detail_column)
            if isinstance(detail_widget, QtWidgets.QWidget):
                detail_widget.updateGeometry()

            heights = []
            for col in (self._status_column, self._detail_column):
                widget = self.table.cellWidget(row, col)
                if isinstance(widget, QtWidgets.QWidget):
                    heights.append(widget.sizeHint().height())
                    heights.append(widget.minimumSizeHint().height())
            min_height = max(70, max(heights, default=62) + 8)
            if self.table.rowHeight(row) != min_height:
                self.table.setRowHeight(row, min_height)

    def populate(self, devices):
        """刷新设备列表展示。

        设备字典中的连接状态与详情字段由上层逻辑填充，此处仅负责视图渲染。
        """
        self._current_devices = devices
        self.table.setRowCount(len(devices))
        compact_layout = self._should_use_compact_actions_for_width(self.table.viewport().width(), 100)
        detail_word_wrap = not self._is_small_screen_layout(self.table.viewport().width()) and not compact_layout

        def _create_status_row(protocol_name, status):
            """创建单条协议状态展示行。"""
            row_widget = QtWidgets.QWidget()
            row_layout = QtWidgets.QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(4)

            if status == CONNECTING:
                row_layout.addWidget(LoadingSpinner(size=14, color="#3B82F6"))
            else:
                icon_char = ONLINE_ICON if status and ("建链成功" in str(status)) else OFFLINE_ICON
                if "连接失败" in str(status):
                    icon_char = OFFLINE_ICON
                lbl_icon = QtWidgets.QLabel(icon_char)
                lbl_icon.setFixedWidth(16)
                row_layout.addWidget(lbl_icon)

            lbl_text = QtWidgets.QLabel(f"{protocol_name}: {status if status != 'connecting' else '连接中...'}")
            lbl_text.setAlignment(ALIGN_LEFT_LABEL)
            lbl_text.setToolTip(lbl_text.text())
            row_layout.addWidget(lbl_text)
            row_layout.addStretch()
            return row_widget

        for row, dev in enumerate(devices):
            name = dev.get("name", "")
            dev_type = dev.get("type", "未知")
            
            ip = dev.get("doip_ip") or dev.get("ip") or dev.get("ssh_ip") or dev.get("someip_ip", "")
            port = dev.get("ssh_port", dev.get("port", "22"))

            ssh_status = str(dev.get("ssh_connect_status", "离线"))
            doip_status = str(dev.get("doip_connect_status", "离线"))
            someip_status = str(dev.get("someip_connect_status", "离线"))

            index_item = QtWidgets.QTableWidgetItem(str(row + 1))
            index_item.setTextAlignment(ALIGN_CENTER_ITEM)
            self.table.setItem(row, 0, index_item)

            name_item = QtWidgets.QTableWidgetItem(name)
            name_item.setTextAlignment(ALIGN_CENTER_ITEM)
            name_item.setToolTip(name)
            self.table.setItem(row, 1, name_item)

            type_item = QtWidgets.QTableWidgetItem(dev_type)
            type_item.setTextAlignment(ALIGN_CENTER_ITEM)
            type_item.setToolTip(dev_type)
            self.table.setItem(row, 2, type_item)

            ip_item = QtWidgets.QTableWidgetItem(ip)
            ip_item.setTextAlignment(ALIGN_CENTER_ITEM)
            ip_item.setToolTip(ip)
            self.table.setItem(row, 3, ip_item)

            port_item = QtWidgets.QTableWidgetItem(str(port))
            port_item.setTextAlignment(ALIGN_CENTER_ITEM)
            port_item.setToolTip(str(port))
            self.table.setItem(row, 4, port_item)

            mcast_ip = str(dev.get("multicast_ip", "239.71.0.2"))
            mcast_ip_item = QtWidgets.QTableWidgetItem(mcast_ip)
            mcast_ip_item.setTextAlignment(ALIGN_CENTER_ITEM)
            mcast_ip_item.setToolTip(mcast_ip)
            self.table.setItem(row, 5, mcast_ip_item)

            mcast_port = str(dev.get("multicast_port", ""))
            if mcast_port == "None":
                mcast_port = ""
            mcast_port_item = QtWidgets.QTableWidgetItem(mcast_port)
            mcast_port_item.setTextAlignment(ALIGN_CENTER_ITEM)
            mcast_port_item.setToolTip(mcast_port)
            self.table.setItem(row, 6, mcast_port_item)

            status_widget = QtWidgets.QWidget()
            status_layout = QtWidgets.QVBoxLayout(status_widget)
            status_layout.setContentsMargins(4, 2, 4, 2)
            status_layout.setSpacing(0)
            status_layout.addWidget(_create_status_row("SSH", ssh_status))
            status_layout.addWidget(_create_status_row("DoIP", doip_status))
            status_layout.addWidget(_create_status_row("SomeIP", someip_status))
            self.table.setCellWidget(row, self._status_column, status_widget)

            ssh_detail = dev.get("ssh_connect_info", "")
            doip_detail = dev.get("doip_connect_info", "")
            someip_detail = dev.get("someip_connect_info", "")

            detail_widget = QtWidgets.QWidget()
            detail_layout = QtWidgets.QVBoxLayout(detail_widget)
            detail_layout.setContentsMargins(4, 2, 4, 2)
            detail_layout.setSpacing(0)

            ssh_detail_label = QtWidgets.QLabel(f"SSH: {ssh_detail or '无'}")
            doip_detail_label = QtWidgets.QLabel(f"DoIP: {doip_detail or '无'}")
            someip_detail_label = QtWidgets.QLabel(f"SomeIP: {someip_detail or '无'}")

            for lbl in (ssh_detail_label, doip_detail_label, someip_detail_label):
                lbl.setAlignment(ALIGN_LEFT_LABEL)
                lbl.setWordWrap(detail_word_wrap)
                lbl.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Minimum)
                lbl.setToolTip(lbl.text())
                detail_layout.addWidget(lbl)

            self.table.setCellWidget(row, self._detail_column, detail_widget)

            # 操作列已移除，所有按钮在顶部工具栏中统一控制

        self._on_table_selection()
        self._refresh_table_layout()

    def _append_log_entry(self, text: str, *, link_text: str | None = None, link_target: str | None = None):
        timestamp = QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss")
        doc = self.log_view.document()
        cursor = QtGui.QTextCursor(doc)
        cursor.movePosition(QtGui.QTextCursor.End)
        if not doc.isEmpty():
            cursor.insertBlock()

        timestamp_format = QtGui.QTextCharFormat()
        timestamp_format.setForeground(QtGui.QColor("#6B7280"))
        timestamp_format.setAnchor(False)
        timestamp_format.setFontUnderline(False)

        text_format = QtGui.QTextCharFormat()
        text_format.setForeground(QtGui.QColor("#111827"))
        text_format.setAnchor(False)
        text_format.setFontUnderline(False)

        link_format = QtGui.QTextCharFormat()
        link_format.setForeground(QtGui.QColor("#2563EB"))
        link_format.setAnchor(True)
        link_format.setFontUnderline(True)
        if link_target:
            link_format.setAnchorHref(link_target)

        cursor.insertText(f"[{timestamp}] ", timestamp_format)
        cursor.insertText(text, text_format)
        if link_text and link_target:
            if text and not text.endswith(" "):
                cursor.insertText(" ", text_format)
            cursor.insertText(link_text, link_format)

        self.log_view.setTextCursor(cursor)
        self.log_view.ensureCursorVisible()

    def append_log(self, text: str):
        self._append_log_entry(text)
        OperationLogManager.instance().append_log("设备管理", text)

    def append_link_log(self, text: str, link_text: str, link_target: str):
        self._append_log_entry(text, link_text=link_text, link_target=link_target)
        OperationLogManager.instance().append_log("设备管理", f"{text} {link_text}")

    def _on_log_anchor_clicked(self, url):
        if url is None:
            return
        self.log_link_clicked.emit(url.toString())



