from PyQt5 import QtWidgets, QtCore
from PyQt5.QtChart import QChart, QChartView, QLineSeries, QValueAxis
from PyQt5.QtGui import QPainter
from app.common.ui.widgets import ModernButton


class PerformanceView(QtWidgets.QWidget):
    def __init__(self, model, parent=None):
        super().__init__(parent)
        self.model = model
        self.setWindowTitle("性能监控")
        self.resize(1000, 700)
        # chart related members
        self.chart = None
        self.chart_view = None
        self.cpu_series = None
        self.mem_series = None
        self.disk_usage_series = None
        self.disk_read_series = None
        self.disk_write_series = None
        self.x_axis = None
        self.y_axis = None
        self.y_axis_kb = None
        self._sample_index = 0
        # keep references for group labels (5 per row)
        self.group_labels = []
        self.setup_ui()

    def setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(12)
        layout.addWidget(self._build_control_group())
        layout.addWidget(self._build_chart_group(), stretch=2)
        layout.addWidget(self._build_process_group(), stretch=3)

        # Enable links in status label
        self.status_label.setOpenExternalLinks(True)

    def _build_control_group(self):
        control_group = QtWidgets.QGroupBox("监控设置")
        control_layout = QtWidgets.QHBoxLayout()
        control_layout.setSpacing(12)

        control_layout.addWidget(QtWidgets.QLabel("📊 监控周期:"))
        self.cycle_combo = QtWidgets.QComboBox()
        self.cycle_combo.addItems(["1秒", "2秒", "5秒", "10秒"])
        self.cycle_combo.setCurrentText("2秒")
        control_layout.addWidget(self.cycle_combo)

        self.export_btn = ModernButton("导出数据", "#2563EB", "💾")
        self.start_btn = ModernButton("开始", "#059669", "▶️")
        self.pause_btn = ModernButton("暂停", "#F59E0B", "⏸️")
        self.pause_btn.setEnabled(False) # Initially disabled
        self.reset_btn = ModernButton("重置", "#6B7280", "🔄")
        control_layout.addWidget(self.start_btn)
        control_layout.addWidget(self.pause_btn)
        control_layout.addWidget(self.reset_btn)
        control_layout.addWidget(self.export_btn)

        self.status_label = QtWidgets.QLabel("未开始监控")
        self.status_label.setStyleSheet("color: #6B7280;")
        control_layout.addWidget(self.status_label)
        control_layout.addStretch()

        control_group.setLayout(control_layout)
        return control_group

    def _build_chart_group(self):
        chart_group = QtWidgets.QGroupBox("性能查询")
        chart_layout = QtWidgets.QVBoxLayout()

        # Series Toggles
        toggles_layout = QtWidgets.QHBoxLayout()
        toggles_layout.setSpacing(15)

        self.cb_cpu = QtWidgets.QCheckBox("CPU (%)")
        self.cb_cpu.setChecked(True)

        self.cb_mem = QtWidgets.QCheckBox("Memory (%)")
        self.cb_mem.setChecked(True)

        self.cb_disk_usage = QtWidgets.QCheckBox("Disk Usage (%)")
        self.cb_disk_usage.setChecked(True)

        self.cb_disk_read = QtWidgets.QCheckBox("Disk Read (KB)")
        self.cb_disk_read.setChecked(True)

        self.cb_disk_write = QtWidgets.QCheckBox("Disk Write (KB)")
        self.cb_disk_write.setChecked(True)

        for cb in [self.cb_cpu, self.cb_mem, self.cb_disk_usage, self.cb_disk_read, self.cb_disk_write]:
            toggles_layout.addWidget(cb)
        toggles_layout.addStretch()

        chart_layout.addLayout(toggles_layout)

        self.init_chart()

        # Connect toggles
        self.cb_cpu.toggled.connect(self.cpu_series.setVisible)
        self.cb_mem.toggled.connect(self.mem_series.setVisible)
        self.cb_disk_usage.toggled.connect(self.disk_usage_series.setVisible)
        self.cb_disk_read.toggled.connect(self.disk_read_series.setVisible)
        self.cb_disk_write.toggled.connect(self.disk_write_series.setVisible)

        self.chart_view.setMinimumHeight(260)
        chart_layout.addWidget(self.chart_view)
        chart_group.setLayout(chart_layout)
        return chart_group

    def _build_process_group(self):
        process_group = QtWidgets.QGroupBox("进程查询")
        proc_layout = QtWidgets.QVBoxLayout()

        header_bar = QtWidgets.QHBoxLayout()
        self.group_info_label = QtWidgets.QLabel("Group Info: ")
        header_bar.addWidget(self.group_info_label)
        header_bar.addStretch()
        self.set_group_btn = ModernButton("Set Group Name", "#2563EB", "⚙")
        header_bar.addWidget(self.set_group_btn)
        proc_layout.addLayout(header_bar)

        group_container = QtWidgets.QWidget()
        self.group_grid = QtWidgets.QGridLayout(group_container)
        self.group_grid.setContentsMargins(4, 0, 4, 0)
        self.group_grid.setHorizontalSpacing(20)
        self.group_grid.setVerticalSpacing(4)

        self.group_labels = []
        for row in range(2):
            for col in range(5):
                lbl = QtWidgets.QLabel("")
                lbl.setTextFormat(QtCore.Qt.RichText)
                lbl.setWordWrap(False)
                lbl.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                                   QtWidgets.QSizePolicy.Preferred)
                self.group_grid.addWidget(lbl, row, col)
                self.group_labels.append(lbl)

        group_container.setFixedHeight(60)
        proc_layout.addWidget(group_container)

        bottom_bar = QtWidgets.QHBoxLayout()
        self.process_title_label = QtWidgets.QLabel("Processes")
        bottom_bar.addWidget(self.process_title_label)

        # --- 新增控件 ---
        bottom_bar.addSpacing(20)
        bottom_bar.addWidget(QtWidgets.QLabel("📊 监控周期:"))
        self.process_cycle_combo = QtWidgets.QComboBox()
        self.process_cycle_combo.addItems(["1s", "2s", "5s", "10s"])
        self.process_cycle_combo.setCurrentText("5s")
        bottom_bar.addWidget(self.process_cycle_combo)

        # ----------------

        bottom_bar.addStretch()

        self.search_edit = QtWidgets.QLineEdit()
        self.search_edit.setPlaceholderText("Search by user / PID / command / group ...")
        self.search_edit.setMaximumWidth(260)
        bottom_bar.addWidget(self.search_edit)

        self.search_btn = QtWidgets.QToolButton()
        self.search_btn.setText("🔍")
        bottom_bar.addWidget(self.search_btn)
        proc_layout.addLayout(bottom_bar)

        self.process_table = QtWidgets.QTableWidget(0, 13)
        self.process_table.setHorizontalHeaderLabels([
            "TYPE", "USER", "PID", "CPU%", "MEM%", "VSZ", "RSS", "TTY", "STAT", "START", "TIME", "CONTAINER", "PROCESS_NAME"
        ])
        self.process_table.verticalHeader().setVisible(False)
        self.process_table.setSortingEnabled(True)
        self.process_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.process_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        header = self.process_table.horizontalHeader()
        # 让表头占满屏幕，最后一列自适应，其他列根据内容调整但有最小宽度
        header.setSectionResizeMode(QtWidgets.QHeaderView.Interactive)
        header.setStretchLastSection(True)
        # 设置默认列宽，避免初始太窄
        for i in range(12):
             header.setSectionResizeMode(i, QtWidgets.QHeaderView.ResizeToContents)

        self.process_table.setHorizontalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        proc_layout.addWidget(self.process_table, 2)

        process_group.setLayout(proc_layout)
        return process_group

    def init_chart(self):
        """初始化性能曲线图（五条折线：CPU / 内存 / 磁盘使用率 / 磁盘读 / 磁盘写）。"""
        self.chart = QChart()
        self.chart.setTitle("System Performance")

        # 曲线
        self.cpu_series = QLineSeries()
        self.cpu_series.setName("CPU (%)")

        self.mem_series = QLineSeries()
        self.mem_series.setName("Memory (%)")

        self.disk_usage_series = QLineSeries()
        self.disk_usage_series.setName("Disk Usage (%)")

        self.disk_read_series = QLineSeries()
        self.disk_read_series.setName("Disk Read (KB)")

        self.disk_write_series = QLineSeries()
        self.disk_write_series.setName("Disk Write (KB)")

        self.chart.addSeries(self.cpu_series)
        self.chart.addSeries(self.mem_series)
        self.chart.addSeries(self.disk_usage_series)
        self.chart.addSeries(self.disk_read_series)
        self.chart.addSeries(self.disk_write_series)

        # X 轴：时间（秒），0~60
        self.x_axis = QValueAxis()
        self.x_axis.setRange(0, 60)
        self.x_axis.setTickCount(7)
        self.x_axis.setLabelFormat("%d s")

        # Y 轴1：百分比 0-100
        self.y_axis = QValueAxis()
        self.y_axis.setRange(0, 100)
        self.y_axis.setTickCount(6)
        self.y_axis.setLabelFormat("%d%%")
        self.y_axis.setLabelsAngle(0)

        # Y 轴2：KB
        self.y_axis_kb = QValueAxis()
        self.y_axis_kb.setRange(0, 1000) # Initial range, will auto-scale or fixed?
        self.y_axis_kb.setLabelFormat("%d KB")
        # self.y_axis_kb.setTitleText("Disk I/O (KB)")

        self.chart.setMargins(QtCore.QMargins(60, 10, 60, 10))

        self.chart.addAxis(self.x_axis, QtCore.Qt.AlignBottom)
        self.chart.addAxis(self.y_axis, QtCore.Qt.AlignLeft)
        self.chart.addAxis(self.y_axis_kb, QtCore.Qt.AlignRight)

        for series in (self.cpu_series, self.mem_series, self.disk_usage_series):
            series.attachAxis(self.x_axis)
            series.attachAxis(self.y_axis)

        for series in (self.disk_read_series, self.disk_write_series):
            series.attachAxis(self.x_axis)
            series.attachAxis(self.y_axis_kb)

        self.chart.legend().setVisible(True)
        self.chart.legend().setAlignment(QtCore.Qt.AlignBottom)

        self.chart_view = QChartView(self.chart)
        self.chart_view.setRenderHint(QPainter.Antialiasing)

    def reset_chart(self):
        """清空所有曲线数据并重置坐标轴。"""
        for series in (self.cpu_series, self.mem_series, self.disk_usage_series, self.disk_read_series, self.disk_write_series):
            series.clear()
        self._sample_index = 0
        self.x_axis.setRange(0, 60)
        self.y_axis_kb.setRange(0, 1000)

    def update_chart(self, x_value: float, cpu: float, mem: float, disk_usage: float, disk_read_kb: float, disk_write_kb: float, max_points: int = 60):
        """追加一个新的采样点到曲线中。"""
        # x_value is now passed from controller (elapsed time)

        self.cpu_series.append(x_value, cpu)
        self.mem_series.append(x_value, mem)
        self.disk_usage_series.append(x_value, disk_usage)
        self.disk_read_series.append(x_value, disk_read_kb)
        self.disk_write_series.append(x_value, disk_write_kb)

        # Auto-scale KB axis if needed
        current_max_kb = max(disk_read_kb, disk_write_kb)
        if current_max_kb > self.y_axis_kb.max():
             self.y_axis_kb.setMax(current_max_kb * 1.2)

        # 控制最大点数
        for series in (self.cpu_series, self.mem_series, self.disk_usage_series, self.disk_read_series, self.disk_write_series):
            if series.count() > max_points:
                remove_count = series.count() - max_points
                for _ in range(remove_count):
                    series.remove(0)

        self.x_axis.setRange(0, 60)

    def update_group_chart(self, group_stats):
        """根据分组统计信息刷新 Group Info 文本列表（每行 5 个 label）。"""
        self.group_info_label.setText("Group Info: ")

        # 先清空所有 label 文本
        for lbl in self.group_labels:
            lbl.clear()

        if not group_stats:
            if self.group_labels:
                self.group_labels[0].setText("无分组数据")
            return

        # 确保 label 数量足够
        needed = len(group_stats)
        if needed > len(self.group_labels):
            start_index = len(self.group_labels)
            extra = needed - len(self.group_labels)
            for i in range(extra):
                row = (start_index + i) // 5
                col = (start_index + i) % 5
                lbl = QtWidgets.QLabel("")
                lbl.setTextFormat(QtCore.Qt.RichText)
                lbl.setWordWrap(False)
                lbl.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                                   QtWidgets.QSizePolicy.Preferred)
                self.group_grid.addWidget(lbl, row, col)
                self.group_labels.append(lbl)

        # 填充数据：每行 5 个，name 加粗，CPU/Mem 百分比
        for idx, stat in enumerate(group_stats):
            text = f"<b>{stat.name}</b>:  CPU {stat.total_cpu_percent:.1f}%  | 内存 {stat.total_mem_percent:.1f}%"
            self.group_labels[idx].setText(text)

    def set_status(self, text: str, level: str = "info"):
        """更新状态标签颜色和文本。

        level: "info" | "warn" | "error"
        """
        color = {
            "info": "#059669",   # 绿色
            "warn": "#F59E0B",   # 橙色
            "error": "#DC2626",  # 红色
        }.get(level, "#6B7280")
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"color: {color};")

    def update_process_table(self, processes):
        """刷新进程表格，仅更新行数据，不影响表头。"""
        # 获取排序方式
        if hasattr(self, 'sort_combo'):
            sort_by = self.sort_combo.currentText()

            # 排序
            if sort_by == "CPU%":
                processes.sort(key=lambda x: x.cpu_percent, reverse=True)
            elif sort_by == "MEM%":
                processes.sort(key=lambda x: x.mem_percent, reverse=True)

        row_count = len(processes)
        self.process_table.setRowCount(row_count)
        self.process_table.setSortingEnabled(False) # 暂时禁用排序以提高性能

        for row, p in enumerate(processes):
            values = [
                str(p.type),
                str(p.user),
                str(p.pid),
                f"{p.cpu_percent:.1f}",
                f"{p.mem_percent:.1f}",
                str(p.vsz_kb),
                str(p.rss_kb),
                str(p.tty),
                str(p.stat),
                str(p.start_time),
                str(p.cpu_time),
                str(p.container),
                str(p.process_name)
            ]
            for col, val in enumerate(values):
                item = self.process_table.item(row, col)
                if item is None:
                    item = QtWidgets.QTableWidgetItem()
                    self.process_table.setItem(row, col, item)

                # 对于数值列，设置自定义数据以便正确排序（如果启用表格自带排序）
                if col in (2, 3, 4, 5, 6): # PID, CPU, MEM, VSZ, RSS
                    try:
                        item.setData(QtCore.Qt.DisplayRole, float(val))
                    except ValueError:
                        item.setText(val)
                else:
                    item.setText(val)

                if col in (2, 3, 4, 5, 6):
                    item.setTextAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
                else:
                    item.setTextAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)

        self.process_table.setSortingEnabled(True)
