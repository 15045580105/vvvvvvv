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
        self.mem_bw_series = None
        self.x_axis = None
        self.y_axis = None
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

    def _build_control_group(self):
        control_group = QtWidgets.QGroupBox("监控设置")
        control_layout = QtWidgets.QHBoxLayout()
        control_layout.setSpacing(12)

        control_layout.addWidget(QtWidgets.QLabel("📊 监控周期:"))
        self.cycle_combo = QtWidgets.QComboBox()
        self.cycle_combo.addItems(["1秒", "2秒", "5秒", "10秒"])
        self.cycle_combo.setCurrentText("2秒")
        control_layout.addWidget(self.cycle_combo)

        self.start_btn = ModernButton("开始", "#059669", "▶️")
        self.pause_btn = ModernButton("暂停", "#F59E0B", "⏸️")
        self.reset_btn = ModernButton("重置", "#6B7280", "🔄")
        control_layout.addWidget(self.start_btn)
        control_layout.addWidget(self.pause_btn)
        control_layout.addWidget(self.reset_btn)

        self.status_label = QtWidgets.QLabel("未开始监控")
        self.status_label.setStyleSheet("color: #6B7280;")
        control_layout.addWidget(self.status_label)
        control_layout.addStretch()

        control_group.setLayout(control_layout)
        return control_group

    def _build_chart_group(self):
        chart_group = QtWidgets.QGroupBox("性能查询")
        chart_layout = QtWidgets.QVBoxLayout()
        self.init_chart()
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
        bottom_bar.addStretch()

        self.search_edit = QtWidgets.QLineEdit()
        self.search_edit.setPlaceholderText("Search by user / PID / command / group ...")
        self.search_edit.setMaximumWidth(260)
        bottom_bar.addWidget(self.search_edit)

        self.search_btn = QtWidgets.QToolButton()
        self.search_btn.setText("🔍")
        bottom_bar.addWidget(self.search_btn)
        proc_layout.addLayout(bottom_bar)

        self.process_table = QtWidgets.QTableWidget(0, 8)
        self.process_table.setHorizontalHeaderLabels([
            "User", "PID", "CPU%", "Mem%", "Virt", "Res", "Command", "Group"
        ])
        self.process_table.verticalHeader().setVisible(False)
        self.process_table.setSortingEnabled(True)
        self.process_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.process_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        header = self.process_table.horizontalHeader()
        header.setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        header.setMinimumSectionSize(90)
        self.process_table.setHorizontalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        initial_widths = [150, 120, 120, 120, 120, 120, 300, 200]
        for col, w in enumerate(initial_widths):
            self.process_table.setColumnWidth(col, w)
        proc_layout.addWidget(self.process_table, 2)

        process_group.setLayout(proc_layout)
        return process_group

    def init_chart(self):
        """初始化性能曲线图（三条折线：CPU / 内存 / 内存带宽）。"""
        self.chart = QChart()
        self.chart.setTitle("CPU Usage")

        # 三条曲线
        self.cpu_series = QLineSeries()
        self.cpu_series.setName("CPU 负载 (%)")

        self.mem_series = QLineSeries()
        self.mem_series.setName("内存使用率 (%)")

        self.mem_bw_series = QLineSeries()
        self.mem_bw_series.setName("内存带宽利用率 (%)")

        self.chart.addSeries(self.cpu_series)
        self.chart.addSeries(self.mem_series)
        self.chart.addSeries(self.mem_bw_series)

        # X 轴：时间（秒），0~60，每 10 秒一格
        self.x_axis = QValueAxis()
        # self.x_axis.setTitleText("时间 (s)")
        self.x_axis.setRange(0, 60)
        # 0,10,20,30,40,50,60 共 7 个刻度
        self.x_axis.setTickCount(7)
        self.x_axis.setLabelFormat("%d s")

        # Y 轴：百分比 0-100，每 10% 一格
        self.y_axis = QValueAxis()
        # self.y_axis.setTitleText("利用率 (%)")
        self.y_axis.setRange(0, 100)
        self.y_axis.setTickCount(5)
        self.y_axis.setLabelFormat("%d%%")
        # 避免标签被裁剪成 "..."：给左侧更多空间
        # 1) 保持水平显示
        self.y_axis.setLabelsAngle(0)
        # 2) 稍微增加 chart 的外边距（左 60 像素，可视情况再调）
        self.chart.setMargins(QtCore.QMargins(60, 10, 10, 10))

        self.chart.addAxis(self.x_axis, QtCore.Qt.AlignBottom)
        self.chart.addAxis(self.y_axis, QtCore.Qt.AlignLeft)

        for series in (self.cpu_series, self.mem_series, self.mem_bw_series):
            series.attachAxis(self.x_axis)
            series.attachAxis(self.y_axis)

        self.chart.legend().setVisible(True)
        self.chart.legend().setAlignment(QtCore.Qt.AlignBottom)

        self.chart_view = QChartView(self.chart)
        # 正确使用 PyQt5.QtGui.QPainter
        self.chart_view.setRenderHint(QPainter.Antialiasing)

    def reset_chart(self):
        """清空所有曲线数据并重置坐标轴。"""
        for series in (self.cpu_series, self.mem_series, self.mem_bw_series):
            series.clear()
        self._sample_index = 0
        # 重置为 0~60 秒范围
        self.x_axis.setRange(0, 60)

    def update_chart(self, cpu: float, mem: float, mem_bw: float, max_points: int = 60):
        """追加一个新的采样点到曲线中。

        :param cpu: CPU 利用率 0-100
        :param mem: 内存利用率 0-100
        :param mem_bw: 内存带宽利用率 0-100
        :param max_points: 曲线中保留的最大点数（��限制点数，但不再移动坐标轴）
        """
        x = self._sample_index
        self._sample_index += 1

        self.cpu_series.append(x, cpu)
        self.mem_series.append(x, mem)
        self.mem_bw_series.append(x, mem_bw)

        # 控制最大点数，防止无限增长
        for series in (self.cpu_series, self.mem_series, self.mem_bw_series):
            if series.count() > max_points:
                remove_count = series.count() - max_points
                for _ in range(remove_count):
                    series.remove(0)

        # 不再滚动 X 轴，保持 0~60 的时间坐标
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
        row_count = len(processes)
        self.process_table.setRowCount(row_count)

        for row, p in enumerate(processes):
            values = [
                str(p.user),
                str(p.pid),
                f"{p.cpu_percent:.1f}",
                f"{p.mem_percent:.1f}",
                str(p.virt),
                str(p.res),
                str(p.command),
                str(getattr(p, "group_name", "")),
            ]
            for col, val in enumerate(values):
                item = self.process_table.item(row, col)
                if item is None:
                    item = QtWidgets.QTableWidgetItem()
                    self.process_table.setItem(row, col, item)
                item.setText(val)
                if col in (1, 2, 3, 4, 5):
                    item.setTextAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
                else:
                    item.setTextAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
