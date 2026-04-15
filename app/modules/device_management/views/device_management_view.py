from PyQt5 import QtWidgets
from PyQt5.QtWidgets import QHeaderView
from PyQt5.QtCore import Qt as _Qt
from PyQt5.QtCore import QDateTime, QEvent, QTimer, QSettings

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
    def setup_ui(self):
        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.setSpacing(16)

        # 防止程序性 setColumnWidth 再次触发表头回调造成递归。
        self._table_layout_updating = False

        # 统一维护设备表列索引与尺寸阈值，方便后期扩展。
        self._status_column = 7
        self._detail_column = 8
        self._action_column = 9
        self._column_ids = tuple(range(10))
        self._compact_action_threshold = 236
        self._compact_viewport_threshold = 1366
        self._input_widgets = []
        # 小屏下优先压缩详情，再压缩一般信息列；连接状态最后压缩，保证可读性。
        self._column_shrink_priority = [8, 5, 6, 1, 3, 2, 4, 0, 9, 7]
        # 有额外空间时优先补给连接状态与操作列，让关键操作更突出。
        self._column_grow_priority = [7, 9, 8, 5, 3, 1, 6, 2, 4, 0]

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
                "preferred_widths": {0: 56, 1: 140, 2: 96, 3: 150, 4: 82, 5: 160, 6: 124, 7: 176, 8: 240, 9: 286},
                "min_widths": {0: 48, 1: 112, 2: 76, 3: 118, 4: 66, 5: 126, 6: 96, 7: 128, 8: 150, 9: 150},
            },
            {
                "min_viewport": 1440,
                "preferred_widths": {0: 52, 1: 126, 2: 88, 3: 136, 4: 76, 5: 146, 6: 114, 7: 160, 8: 208, 9: 244},
                "min_widths": {0: 46, 1: 104, 2: 72, 3: 112, 4: 64, 5: 118, 6: 92, 7: 124, 8: 140, 9: 142},
            },
            {
                "min_viewport": 1320,
                "preferred_widths": {0: 46, 1: 110, 2: 76, 3: 118, 4: 68, 5: 126, 6: 94, 7: 170, 8: 128, 9: 180},
                "min_widths": {0: 40, 1: 90, 2: 62, 3: 100, 4: 56, 5: 102, 6: 74, 7: 136, 8: 102, 9: 146},
            },
            {
                "min_viewport": 1200,
                "preferred_widths": {0: 46, 1: 108, 2: 76, 3: 116, 4: 68, 5: 126, 6: 96, 7: 156, 8: 126, 9: 170},
                "min_widths": {0: 40, 1: 88, 2: 62, 3: 98, 4: 56, 5: 100, 6: 76, 7: 128, 8: 100, 9: 138},
            },
            {
                "min_viewport": 0,
                "preferred_widths": {0: 42, 1: 98, 2: 70, 3: 108, 4: 62, 5: 116, 6: 88, 7: 144, 8: 116, 9: 162},
                "min_widths": {0: 38, 1: 82, 2: 60, 3: 92, 4: 52, 5: 94, 6: 72, 7: 120, 8: 96, 9: 132},
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
        self._input_grid = QtWidgets.QGridLayout()
        self._input_grid.setSpacing(12)

        def _create_input_field(label_text: str, widget: QtWidgets.QWidget):
            container = QtWidgets.QWidget()
            layout = QtWidgets.QHBoxLayout(container)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(8)
            label = QtWidgets.QLabel(label_text + "：")
            label.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
            widget.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
            layout.addWidget(label)
            layout.addWidget(widget)
            return container

        self.ip_input = QtWidgets.QLineEdit()
        self.port_input = QtWidgets.QLineEdit()
        self.port_input.setText("22")
        self.name_input = QtWidgets.QLineEdit()
        self.user_input = QtWidgets.QLineEdit()
        self.password_input = QtWidgets.QLineEdit()
        self.password_input.setEchoMode(QtWidgets.QLineEdit.Password)
        self.type_input = QtWidgets.QComboBox()
        self.type_input.addItems(["ECU", "网关", "域控", "其他"])

        self.multicast_ip_input = QtWidgets.QLineEdit()
        self.multicast_ip_input.setText("239.71.0.2")
        self.multicast_port_input = QtWidgets.QLineEdit()
        self.multicast_port_input.setText("30490")
        self.vlan_id_input = QtWidgets.QLineEdit()
        self.vlan_id_input.setText("4")
        self.client_port_input = QtWidgets.QLineEdit()
        self.client_port_input.setText("30813")
        self.client_id_input = QtWidgets.QLineEdit()
        self.client_id_input.setText("30813")
        self.add_btn = ModernButton("添加设备", "#0EA5E9", "➕")
        self.add_btn.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

        self._input_widgets = [
            _create_input_field("IP地址", self.ip_input),
            _create_input_field("SSH端口", self.port_input),
            _create_input_field("用户名", self.user_input),
            _create_input_field("密码", self.password_input),
            _create_input_field("设备名", self.name_input),
            _create_input_field("设备类型", self.type_input),
            _create_input_field("标准组播 IP", self.multicast_ip_input),
            _create_input_field("标准组播端口", self.multicast_port_input),
            _create_input_field("VLAN ID", self.vlan_id_input),
            _create_input_field("客户端端口", self.client_port_input),
            _create_input_field("客户端 ID", self.client_id_input),
            self.add_btn,
        ]
        input_group.setLayout(self._input_grid)
        content_layout.addWidget(input_group)

        # 表格宽度始终与视口一致，不依赖水平滚动条。
        self.table = QtWidgets.QTableWidget(0, 10)
        self.table.setHorizontalHeaderLabels([
            "序号", "设备名", "设备类型", "IP地址", "SSH端口",
            "标准组播 IP", "标准组播端口", "连接状态", "详情", "操作"
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
        hheader.setStretchLastSection(False)
        hheader.setMinimumSectionSize(56)

        for column, width in self._default_column_widths(max(1280, self.width())).items():
            self.table.setColumnWidth(column, width)

        self._restore_user_column_widths()

        content_layout.addWidget(self.table)
        self.table.horizontalHeader().sectionResized.connect(self._on_header_section_resized)
        self.table.viewport().installEventFilter(self)

        log_group = QtWidgets.QGroupBox("操作日志")
        log_layout = QtWidgets.QVBoxLayout()
        self.log_view = QtWidgets.QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setPlaceholderText("这里显示用户的操作日志...")
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
        return self._should_use_compact_actions_for_width(self.table.viewport().width(), self.table.columnWidth(self._action_column))

    def _should_use_compact_actions_for_width(self, viewport_width, action_width):
        if not hasattr(self, "table"):
            return False
        return viewport_width <= self._compact_viewport_threshold or action_width <= self._compact_action_threshold

    def _is_small_screen_layout(self, viewport_width):
        return viewport_width <= 1366

    def _refresh_table_layout(self, resized_column=None):
        if not hasattr(self, "table") or self._table_layout_updating:
            return
        self._table_layout_updating = True
        try:
            self._relayout_input_grid()
            self._apply_responsive_column_hints(resized_column)
            self._refresh_row_widgets()
        finally:
            self._table_layout_updating = False

    def _relayout_input_grid(self):
        """根据当前可用宽度重排输入区，避免小屏幕下控件被压得不可见。"""
        if not hasattr(self, "_input_grid") or not self._input_widgets:
            return

        width = max(self.width(), self.table.viewport().width(), 1)
        if width >= 1780:
            columns = 6
        elif width >= 1480:
            columns = 5
        elif width >= 1260:
            columns = 4
        elif width >= 920:
            columns = 3
        elif width >= 720:
            columns = 2
        else:
            columns = 1

        while self._input_grid.count():
            self._input_grid.takeAt(0)

        for column in range(columns):
            self._input_grid.setColumnStretch(column, 1)

        for index, widget in enumerate(self._input_widgets):
            row = index // columns
            column = index % columns
            self._input_grid.addWidget(widget, row, column)

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
        compact = self._should_use_compact_actions_for_width(viewport_width, preferred_widths[self._action_column])
        if compact:
            preferred_widths[self._action_column] = min(preferred_widths[self._action_column], 176)
            preferred_widths[self._detail_column] = min(preferred_widths[self._detail_column], 132)
            preferred_widths[self._status_column] = max(preferred_widths[self._status_column], 150)
        return preferred_widths

    def _column_min_widths_for_viewport(self, viewport_width):
        profile = self._current_column_profile(viewport_width)
        min_widths = dict(profile["min_widths"])
        compact = self._should_use_compact_actions_for_width(viewport_width, min_widths[self._action_column])
        if compact:
            min_widths[self._action_column] = max(136, min(min_widths[self._action_column], 148))
            min_widths[self._detail_column] = min(min_widths[self._detail_column], 104)
            min_widths[self._status_column] = max(min_widths[self._status_column], 128)
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
        action_min_width = self._column_min_widths_for_viewport(self.table.viewport().width())[self._action_column]
        for row in range(self.table.rowCount()):
            action_widget = self.table.cellWidget(row, self._action_column)
            if isinstance(action_widget, QtWidgets.QWidget):
                if hasattr(action_widget, "set_compact_mode"):
                    action_widget.set_compact_mode(compact)
                target_width = max(112 if compact else action_min_width, self.table.columnWidth(self._action_column) - 8)
                action_widget.resize(target_width, action_widget.height())
                action_widget.updateGeometry()

            detail_widget = self.table.cellWidget(row, self._detail_column)
            if isinstance(detail_widget, QtWidgets.QWidget):
                detail_widget.updateGeometry()

            heights = []
            for col in (self._status_column, self._detail_column, self._action_column):
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
        self.table.setRowCount(len(devices))
        compact_layout = self._should_use_compact_actions_for_width(self.table.viewport().width(), self.table.columnWidth(self._action_column))
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
            ip = dev.get("ip", "")
            port = dev.get("port", dev.get("ssh_port", "22"))

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

            action_widget = ResponsiveButtonFlowPanel(spacing=8, row_spacing=6, margins=(4, 4, 4, 4))
            connect_btn = TableButton("连接设备", "#059669")
            disconnect_btn = TableButton("断开连接", "#F59E0B")
            edit_btn = TableButton("修改信息", "#3B82F6")
            delete_btn = TableButton("删除设备", "#EF4444")
            upgrade_btn = TableButton("软件升级", "#6366F1")
            query_btn = TableButton("状态查询", "#0EA5E9")

            button_text_pairs = [
                (connect_btn, "连接设备", "连接", "connect"),
                (disconnect_btn, "断开连接", "断开", "disconnect"),
                (edit_btn, "修改信息", "修改", "edit"),
                (delete_btn, "删除设备", "删除", "delete"),
                (upgrade_btn, "软件升级", "升级", "upgrade"),
                (query_btn, "状态查询", "查询", "query"),
            ]
            for btn, full_text, compact_text, action_key in button_text_pairs:
                btn.setProperty("full_text", full_text)
                btn.setProperty("compact_text", compact_text)
                btn.setProperty("action_key", action_key)
                btn.setObjectName(action_key)
                btn.setToolTip(full_text)


            for btn in (connect_btn, disconnect_btn, edit_btn, delete_btn, upgrade_btn, query_btn):
                action_widget.add_button(btn)

            action_widget.set_compact_mode(self._should_use_compact_actions())
            action_widget.heightChanged.connect(self._refresh_table_layout)
            self.table.setCellWidget(row, self._action_column, action_widget)
            self.table.setRowHeight(row, max(70, action_widget.minimumSizeHint().height() + 8))

        self._refresh_table_layout()

    def append_log(self, text: str):
        timestamp = QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss")
        log_msg = f"[{timestamp}] {text}"
        self.log_view.append(log_msg)
        OperationLogManager.instance().append_log("设备管理", text)
