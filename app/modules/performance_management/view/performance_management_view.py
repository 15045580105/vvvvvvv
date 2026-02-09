from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtChart import QChart, QChartView, QLineSeries, QValueAxis, QAreaSeries
from PyQt5.QtGui import QPainter, QColor, QLinearGradient, QGradient
from app.common.ui.widgets import ModernButton


class MetricCard(QtWidgets.QFrame):
    clicked = QtCore.pyqtSignal(str)

    def __init__(self, title, identifier, color="#333333", parent=None):
        super().__init__(parent)
        self.identifier = identifier
        self.base_color = color # Store the base color for the value
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.selected = False

        # Main layout is Horizontal: Left (Title/Sub) | Right (Value)
        self.layout = QtWidgets.QHBoxLayout(self)
        self.layout.setContentsMargins(15, 10, 15, 10)
        self.layout.setSpacing(10)

        # Left Container for Title and Subtitle
        left_container = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(2)

        self.title_lbl = QtWidgets.QLabel(title)
        self.title_lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #555;")
        self.title_lbl.setWordWrap(True) # Allow title to wrap if needed

        self.sub_lbl = QtWidgets.QLabel("Waiting...")
        self.sub_lbl.setStyleSheet("font-size: 12px; color: #888;")

        left_layout.addWidget(self.title_lbl)
        left_layout.addWidget(self.sub_lbl)
        left_layout.addStretch()

        # Right Label for Value
        self.value_lbl = QtWidgets.QLabel("-")
        self.value_lbl.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
        # Adjust font size slightly if needed to fit, but horizontal layout gives more space
        self.value_lbl.setStyleSheet(f"font-size: 24px; font-weight: bold; color: {self.base_color};")

        self.layout.addWidget(left_container, stretch=1)
        self.layout.addWidget(self.value_lbl, stretch=0)

        self.update_style()

    def mousePressEvent(self, event):
        self.clicked.emit(self.identifier)
        super().mousePressEvent(event)

    def set_selected(self, selected):
        self.selected = selected
        self.update_style()

    def update_style(self):
        if self.selected:
            self.setStyleSheet("""
                MetricCard {
                    background-color: #EFF6FF;
                    border: 2px solid #3B82F6;
                    border-radius: 8px;
                }
                QLabel { background-color: transparent; }
            """)
        else:
            self.setStyleSheet("""
                MetricCard {
                    background-color: #FFFFFF;
                    border: 1px solid #E5E7EB;
                    border-radius: 8px;
                }
                MetricCard:hover {
                    background-color: #F9FAFB;
                }
                QLabel { background-color: transparent; }
            """)

    def update_data(self, value_text, sub_text, level="info"):
        self.value_lbl.setText(value_text)
        self.sub_lbl.setText(sub_text)

        color = self.base_color # Default to base color
        if level == "warn": color = "#F59E0B"
        elif level == "error": color = "#EF4444"
        elif level == "success": color = "#10B981"

        self.value_lbl.setStyleSheet(f"font-size: 24px; font-weight: bold; color: {color};")


class ProcessTableModel(QtCore.QAbstractTableModel):
    """高性能进程数据模型"""
    def __init__(self, processes=None, parent=None):
        super().__init__(parent)
        self._processes = processes or []
        self._headers = [
            "TYPE", "USER", "PID", "CPU%", "MEM%", "VSZ", "RSS", "TTY", "STAT", "START", "TIME", "CONTAINER", "PROCESS_NAME"
        ]

    def rowCount(self, parent=QtCore.QModelIndex()):
        return len(self._processes)

    def columnCount(self, parent=QtCore.QModelIndex()):
        return len(self._headers)

    def data(self, index, role=QtCore.Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._processes)):
            return None

        p = self._processes[index.row()]
        col = index.column()

        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            if col == 0: return str(p.type)
            elif col == 1: return str(p.user)
            elif col == 2: return str(p.pid)
            elif col == 3: return f"{p.cpu_percent:.1f}"
            elif col == 4: return f"{p.mem_percent:.1f}"
            elif col == 5: return str(p.vsz_kb)
            elif col == 6: return str(p.rss_kb)
            elif col == 7: return str(p.tty)
            elif col == 8: return str(p.stat)
            elif col == 9: return str(p.start_time)
            elif col == 10: return str(p.cpu_time)
            elif col == 11: return str(p.container)
            elif col == 12: return str(p.process_name)

        elif role == QtCore.Qt.ItemDataRole.TextAlignmentRole:
            # 数值列右对齐
            if col in (2, 3, 4, 5, 6):
                return QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter
            return QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter

        return None

    def headerData(self, section, orientation, role=QtCore.Qt.ItemDataRole.DisplayRole):
        if orientation == QtCore.Qt.Orientation.Horizontal and role == QtCore.Qt.ItemDataRole.DisplayRole:
            return self._headers[section]
        return None

    def update_data(self, new_processes):
        """全量更新数据，使用 resetModel 确保视图刷新"""
        self.beginResetModel()
        self._processes = new_processes
        self.endResetModel()

    def sort(self, column, order):
        """支持排序"""
        self.layoutAboutToBeChanged.emit()
        try:
            reverse = (order == QtCore.Qt.SortOrder.DescendingOrder)
            if column == 2: # PID
                self._processes.sort(key=lambda p: p.pid, reverse=reverse)
            elif column == 3: # CPU
                self._processes.sort(key=lambda p: p.cpu_percent, reverse=reverse)
            elif column == 4: # MEM
                self._processes.sort(key=lambda p: p.mem_percent, reverse=reverse)
            elif column == 5: # VSZ
                self._processes.sort(key=lambda p: p.vsz_kb, reverse=reverse)
            elif column == 6: # RSS
                self._processes.sort(key=lambda p: p.rss_kb, reverse=reverse)
            else:
                # 其他列按字符串排序
                # 为了简单，这里只实现主要数值列的排序，或者全部转字符串排序
                # 实际需求中 CPU/MEM 排序最重要
                pass
        except Exception as e:
            print(f"Sort error: {e}")
        finally:
            self.layoutChanged.emit()


class PerformanceView(QtWidgets.QWidget):
    def __init__(self, model, parent=None):
        super().__init__(parent)
        self.model = model
        self.setWindowTitle("性能监控")
        self.resize(1200, 800)
        # chart related members
        self.chart = None
        self.chart_view = None
        self.series_map = {} # identifier -> QLineSeries
        self.x_axis = None
        self.y_axis = None
        self.current_metric = "cpu"
        self.cards = []
        self.setup_ui()

    def setup_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)

        self.tabs = QtWidgets.QTabWidget()

        # --- Metrics Tab ---
        self.metrics_tab = QtWidgets.QWidget()
        metrics_layout = QtWidgets.QVBoxLayout(self.metrics_tab)
        metrics_layout.addWidget(self._build_metrics_controls())
        metrics_layout.addWidget(self._build_metrics_content(), stretch=1)
        self.tabs.addTab(self.metrics_tab, "性能监控")

        # --- Process Tab ---
        self.process_tab = QtWidgets.QWidget()
        process_layout = QtWidgets.QVBoxLayout(self.process_tab)
        process_layout.addWidget(self._build_process_controls())
        process_layout.addWidget(self._build_process_group(), stretch=1)
        self.tabs.addTab(self.process_tab, "进程监控")

        main_layout.addWidget(self.tabs)

        # Enable links in status labels
        self.metrics_status_label.setOpenExternalLinks(True)
        self.process_status_label.setOpenExternalLinks(True)

    def _build_metrics_controls(self):
        group = QtWidgets.QGroupBox("性能监控设置")
        layout = QtWidgets.QHBoxLayout()
        layout.setSpacing(12)

        layout.addWidget(QtWidgets.QLabel("📊 监控周期:"))
        self.metrics_cycle_combo = QtWidgets.QComboBox()
        self.metrics_cycle_combo.addItems(["1s", "2s", "5s", "10s", "30s"])
        self.metrics_cycle_combo.setCurrentText("2s")
        layout.addWidget(self.metrics_cycle_combo)

        self.metrics_start_btn = ModernButton("开始", "#059669", "▶️")
        self.metrics_stop_btn = ModernButton("结束", "#F59E0B", "⏹️")
        self.metrics_stop_btn.setEnabled(False)
        self.metrics_export_btn = ModernButton("导出数据", "#2563EB", "💾")

        layout.addWidget(self.metrics_start_btn)
        layout.addWidget(self.metrics_stop_btn)
        layout.addWidget(self.metrics_export_btn)

        self.metrics_status_label = QtWidgets.QLabel("未开始监控")
        self.metrics_status_label.setStyleSheet("color: #6B7280;")
        layout.addWidget(self.metrics_status_label)
        layout.addStretch()

        group.setLayout(layout)
        return group

    def _build_process_controls(self):
        group = QtWidgets.QGroupBox("进程监控设置")
        layout = QtWidgets.QHBoxLayout()
        layout.setSpacing(12)

        layout.addWidget(QtWidgets.QLabel("📊 监控周期:"))
        self.process_cycle_combo = QtWidgets.QComboBox()
        self.process_cycle_combo.addItems(["1s", "2s", "5s", "10s", "30s"])
        self.process_cycle_combo.setCurrentText("5s")
        layout.addWidget(self.process_cycle_combo)

        self.process_start_btn = ModernButton("开始", "#059669", "▶️")
        self.process_stop_btn = ModernButton("结束", "#F59E0B", "⏹️")
        self.process_stop_btn.setEnabled(False)
        self.process_export_btn = ModernButton("导出数据", "#2563EB", "💾")

        layout.addWidget(self.process_start_btn)
        layout.addWidget(self.process_stop_btn)
        layout.addWidget(self.process_export_btn)

        self.process_status_label = QtWidgets.QLabel("未开始监控")
        self.process_status_label.setStyleSheet("color: #6B7280;")
        layout.addWidget(self.process_status_label)
        layout.addStretch()

        group.setLayout(layout)
        return group

    def _build_process_group(self):
        # process_group = QtWidgets.QGroupBox("进程查询") # Removed GroupBox
        process_container = QtWidgets.QWidget()
        proc_layout = QtWidgets.QVBoxLayout(process_container)
        proc_layout.setContentsMargins(0, 0, 0, 0)

        # Search Bar Layout
        search_bar_layout = QtWidgets.QHBoxLayout()

        self.search_edit = QtWidgets.QLineEdit()
        self.search_edit.setPlaceholderText("Search by user / PID / command / group ...")

        self.search_btn = QtWidgets.QToolButton()
        self.search_btn.setText("🔍")

        search_bar_layout.addWidget(self.search_edit)
        search_bar_layout.addWidget(self.search_btn)

        proc_layout.addLayout(search_bar_layout)

        self.process_table = QtWidgets.QTableView()
        self.process_model = ProcessTableModel()
        self.process_table.setModel(self.process_model)

        self.process_table.verticalHeader().setVisible(False)
        self.process_table.setSortingEnabled(True)
        self.process_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.process_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)

        header = self.process_table.horizontalHeader()
        header.setSectionResizeMode(QtWidgets.QHeaderView.Interactive)
        header.setStretchLastSection(True)
        # Initial resize to contents (optional, can be expensive if done frequently, but okay once)
        # for i in range(12):
        #      header.setSectionResizeMode(i, QtWidgets.QHeaderView.ResizeToContents)

        self.process_table.setHorizontalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        proc_layout.addWidget(self.process_table, 2)

        return process_container

    def _build_metrics_content(self):
        container = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(container)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(20)

        # Left Panel: Cards
        left_panel = QtWidgets.QWidget()
        left_panel.setMaximumWidth(300) # Increased width for horizontal layout
        left_layout = QtWidgets.QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)

        self.card_cpu = MetricCard("CPU (%)", "cpu", "#3B82F6")
        self.card_mem = MetricCard("Memory (%)", "mem", "#8B5CF6")
        self.card_mem_used = MetricCard("Mem Used (KB)", "mem_used", "#EC4899")
        self.card_mem_avail = MetricCard("Mem Available (KB)", "mem_avail", "#14B8A6")
        self.card_disk_usage = MetricCard("Disk Usage (%)", "disk_usage", "#10B981")
        self.card_disk_read = MetricCard("Disk Read (KB)", "disk_read", "#F59E0B")
        self.card_disk_write = MetricCard("Disk Write (KB)", "disk_write", "#EF4444")

        self.cards = [
            self.card_cpu,
            self.card_mem,
            self.card_mem_used,
            self.card_mem_avail,
            self.card_disk_usage,
            self.card_disk_read,
            self.card_disk_write
        ]
        for card in self.cards:
            left_layout.addWidget(card)
            card.clicked.connect(self.on_card_clicked)

        left_layout.addStretch()

        # Right Panel: Chart
        right_panel = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.chart_title = QtWidgets.QLabel("CPU Usage (%)")
        self.chart_title.setStyleSheet("font-size: 13.5pt; font-weight: bold; color: #333; margin-bottom: 10px;")
        right_layout.addWidget(self.chart_title)

        self.init_chart()
        right_layout.addWidget(self.chart_view)

        layout.addWidget(left_panel, 1)
        layout.addWidget(right_panel, 3)

        # Default selection
        self.on_card_clicked("cpu")

        return container

    def init_chart(self):
        """初始化性能曲线图"""
        self.chart = QChart()
        self.chart.setBackgroundVisible(True)
        self.chart.setBackgroundBrush(QtGui.QBrush(QtCore.Qt.white))
        self.chart.layout().setContentsMargins(0, 0, 0, 0)
        self.chart.legend().setVisible(False)

        # Create Series
        self.cpu_series = QLineSeries()
        self.cpu_series.setName("CPU (%)")
        self.mem_series = QLineSeries()
        self.mem_series.setName("Memory (%)")
        self.mem_used_series = QLineSeries()
        self.mem_used_series.setName("Mem Used (KB)")
        self.mem_avail_series = QLineSeries()
        self.mem_avail_series.setName("Mem Available (KB)")
        self.disk_usage_series = QLineSeries()
        self.disk_usage_series.setName("Disk Usage (%)")
        self.disk_read_series = QLineSeries()
        self.disk_read_series.setName("Disk Read (KB)")
        self.disk_write_series = QLineSeries()
        self.disk_write_series.setName("Disk Write (KB)")

        self.series_map = {
            "cpu": self.cpu_series,
            "mem": self.mem_series,
            "mem_used": self.mem_used_series,
            "mem_avail": self.mem_avail_series,
            "disk_usage": self.disk_usage_series,
            "disk_read": self.disk_read_series,
            "disk_write": self.disk_write_series
        }

        # Area Series Map for shadows
        self.area_series_map = {}

        for key, series in self.series_map.items():
            # Style the lines
            pen = series.pen()
            pen.setWidth(2)

            # Set specific colors for each metric if desired, or use default theme colors
            # For now, let's pick some nice colors
            color_map = {
                "cpu": QColor("#3B82F6"), # Blue
                "mem": QColor("#8B5CF6"), # Purple
                "mem_used": QColor("#EC4899"), # Pink
                "mem_avail": QColor("#14B8A6"), # Teal
                "disk_usage": QColor("#10B981"), # Green
                "disk_read": QColor("#F59E0B"), # Orange
                "disk_write": QColor("#EF4444") # Red
            }
            color = color_map.get(key, QColor("#3B82F6"))
            pen.setColor(color)
            series.setPen(pen)

            self.chart.addSeries(series)

            # Create Area Series for shadow effect
            # We need a baseline series (y=0) for the area
            # But QAreaSeries takes two line series. The lower one can be 0.
            # However, dynamically updating QAreaSeries is tricky because we need to update the underlying line series.
            # A common trick is to have a "lower" series that always has y=0 for the same x points.
            # Let's try to implement this.

            # For simplicity in dynamic updates, we might just use the line series for now.
            # But user asked for "shadow color".
            # To do this properly with QAreaSeries:
            # 1. Create a lower_series that mirrors the x values of the main series but y is always 0.
            # 2. Create QAreaSeries(main_series, lower_series).
            # 3. Set brush with gradient or transparent color.

            lower_series = QLineSeries()
            area_series = QAreaSeries(series, lower_series)

            # Gradient for the area
            gradient = QLinearGradient(0, 0, 0, 1)
            gradient.setCoordinateMode(QGradient.ObjectBoundingMode)
            gradient.setColorAt(0.0, QColor(color.red(), color.green(), color.blue(), 100)) # Semi-transparent
            gradient.setColorAt(1.0, QColor(color.red(), color.green(), color.blue(), 10))  # Very transparent

            area_series.setBrush(gradient)
            area_series.setPen(QtGui.QPen(QtCore.Qt.NoPen)) # No border for area

            self.chart.addSeries(area_series)

            # Store references
            # We need to update lower_series when we update main series
            # We can attach lower_series to the series object dynamically or store in a map
            series.lower_series = lower_series
            series.area_series = area_series

            # Ensure area is behind line (addSeries order matters, but we added line first? No, area should be added first usually)
            # Let's re-add line series to be on top
            self.chart.removeSeries(series)
            self.chart.addSeries(series)

        # Axes
        self.x_axis = QValueAxis()
        self.x_axis.setRange(0, 60)
        # User said: "横坐标原点是60s，从左往右边依次是60s...0s"
        # Normal: Min->Max. Reverse: Max->Min.
        # So Range(0, 60) with Reverse(True) -> 60 (Left) ... 0 (Right)
        self.x_axis.setReverse(True)
        self.x_axis.setTickCount(7)
        self.x_axis.setLabelFormat("%d s")
        self.chart.addAxis(self.x_axis, QtCore.Qt.AlignmentFlag.AlignBottom)

        self.y_axis = QValueAxis()
        self.y_axis.setRange(0, 100)
        self.y_axis.setTickCount(6)
        self.y_axis.setLabelFormat("%d")
        self.chart.addAxis(self.y_axis, QtCore.Qt.AlignmentFlag.AlignLeft)

        for series in self.series_map.values():
            series.attachAxis(self.x_axis)
            series.attachAxis(self.y_axis)
            # Attach area series too
            series.area_series.attachAxis(self.x_axis)
            series.area_series.attachAxis(self.y_axis)

        self.chart_view = QChartView(self.chart)
        self.chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)

    def on_card_clicked(self, identifier):
        self.current_metric = identifier

        # Update Cards Selection
        for card in self.cards:
            card.set_selected(card.identifier == identifier)

        # Update Chart Title and Visibility
        titles = {
            "cpu": "CPU Usage (%)",
            "mem": "Memory Usage (%)",
            "mem_used": "Memory Used (KB)",
            "mem_avail": "Memory Available (KB)",
            "disk_usage": "Disk Usage (%)",
            "disk_read": "Disk Read Speed (KB/s)",
            "disk_write": "Disk Write Speed (KB/s)"
        }
        self.chart_title.setText(titles.get(identifier, "Metric"))

        # Show only selected series
        for key, series in self.series_map.items():
            is_visible = (key == identifier)
            series.setVisible(is_visible)
            series.area_series.setVisible(is_visible)

        # Update Y Axis Range/Format
        if identifier in ["cpu", "mem", "disk_usage"]:
            self.y_axis.setRange(0, 100)
            self.y_axis.setLabelFormat("%d%%")
        elif identifier in ["mem_used", "mem_avail"]:
            # Default range, will be auto-scaled
            self.y_axis.setRange(0, 1000)
            self.y_axis.setLabelFormat("%d KB")
        else:
            # For speed, we need dynamic range, but for now reset to a default or auto
            # We will handle dynamic scaling in update_chart
            self.y_axis.setRange(0, 1000)
            self.y_axis.setLabelFormat("%d")

    def reset_chart(self):
        """清空所有曲线数据并重置坐标轴。"""
        for series in self.series_map.values():
            series.clear()
            series.lower_series.clear()
        self._sample_index = 0
        # Reset X axis to default view
        self.x_axis.setRange(0, 60)
        if self.current_metric in ["disk_read", "disk_write"]:
            self.y_axis.setRange(0, 1000)

    def update_chart(self, x_value: float, cpu: float, mem: float, mem_used_kb: int, mem_total_kb: int, mem_available_kb: int, disk_usage: float, disk_read_kb: float, disk_write_kb: float, max_points: int = 60):
        """追加一个新的采样点到曲线中，并更新卡片。"""

        # ... (comments omitted) ...

        # 1. Update Cards (same as before)
        cpu_level = "info"
        if cpu > 80: cpu_level = "error"
        elif cpu > 50: cpu_level = "warn"
        self.card_cpu.update_data(f"{cpu:.1f}%", "Load", cpu_level)

        mem_level = "info"
        if mem > 80: mem_level = "error"
        elif mem > 50: mem_level = "warn"
        self.card_mem.update_data(f"{mem:.1f}%", "Used", mem_level)

        # Update new memory cards
        self.card_mem_used.update_data(f"{mem_used_kb / 1024:.1f}", "MB Used", "info")
        self.card_mem_avail.update_data(f"{mem_available_kb / 1024:.1f}", "MB Avail", "info")

        du_level = "info"
        if disk_usage > 80: du_level = "error"
        elif disk_usage > 50: du_level = "warn"
        self.card_disk_usage.update_data(f"{disk_usage:.1f}%", "Used", du_level)

        self.card_disk_read.update_data(f"{disk_read_kb:.0f}", "KB/s", "info")
        self.card_disk_write.update_data(f"{disk_write_kb:.0f}", "KB/s", "info")

        # 2. Manage Data Buffer
        if not hasattr(self, 'data_buffer'):
            self.data_buffer = []

        current_time = x_value # This is actually elapsed time passed from controller

        # Store tuple: (elapsed_time, cpu, mem, mem_used, mem_avail, disk_usage, read, write)
        self.data_buffer.append((current_time, cpu, mem, mem_used_kb, mem_available_kb, disk_usage, disk_read_kb, disk_write_kb))

        # Remove old data (> 60s ago)
        while self.data_buffer and (current_time - self.data_buffer[0][0] > 60):
            self.data_buffer.pop(0)

        # 3. Re-plot Series
        # We need to clear and replace points to create the "scrolling" effect where X represents "Time Ago"
        # X axis range is fixed [0, 60] (reversed).
        # Newest point (current_time) should be at X=0.
        # Oldest point (current_time - 60) should be at X=60.

        # Prepare point lists
        points_map = {k: [] for k in self.series_map.keys()}
        lower_points_map = {k: [] for k in self.series_map.keys()} # For area series baseline

        for entry in self.data_buffer:
            t, c, m, mu, ma, du, dr, dw = entry
            time_ago = current_time - t

            points_map["cpu"].append(QtCore.QPointF(time_ago, c))
            points_map["mem"].append(QtCore.QPointF(time_ago, m))
            points_map["mem_used"].append(QtCore.QPointF(time_ago, mu))
            points_map["mem_avail"].append(QtCore.QPointF(time_ago, ma))
            points_map["disk_usage"].append(QtCore.QPointF(time_ago, du))
            points_map["disk_read"].append(QtCore.QPointF(time_ago, dr))
            points_map["disk_write"].append(QtCore.QPointF(time_ago, dw))

            # Lower points are always y=0
            for k in points_map.keys():
                lower_points_map[k].append(QtCore.QPointF(time_ago, 0))

        # Update Series
        for key, series in self.series_map.items():
            series.replace(points_map[key])
            series.lower_series.replace(lower_points_map[key])

        # 4. Auto-scale Y Axis for speed/size metrics
        if self.current_metric in ["disk_read", "disk_write", "mem_used", "mem_avail"]:
            if self.current_metric == "disk_read": current_val = disk_read_kb
            elif self.current_metric == "disk_write": current_val = disk_write_kb
            elif self.current_metric == "mem_used": current_val = mem_used_kb
            elif self.current_metric == "mem_avail": current_val = mem_available_kb
            else: current_val = 0

            if current_val > self.y_axis.max():
                self.y_axis.setMax(current_val * 1.2)
            elif self.y_axis.max() > 1000 and current_val < self.y_axis.max() * 0.5:
                 pass


    def set_metrics_status(self, text: str, level: str = "info"):
        """更新性能监控状态标签颜色和文本。"""
        color = self._get_status_color(level)
        self.metrics_status_label.setText(text)
        self.metrics_status_label.setStyleSheet(f"color: {color};")

    def set_process_status(self, text: str, level: str = "info"):
        """更新进程监控状态标签颜色和文本。"""
        color = self._get_status_color(level)
        self.process_status_label.setText(text)
        self.process_status_label.setStyleSheet(f"color: {color};")

    def _get_status_color(self, level: str) -> str:
        return {
            "info": "#059669",   # 绿色
            "warn": "#F59E0B",   # 橙色
            "error": "#DC2626",  # 红色
        }.get(level, "#6B7280")


    def update_process_table(self, processes):
        """刷新进程表格，仅更新行数据，不影响表头。"""
        # 默认按 CPU% 降序排序
        processes.sort(key=lambda x: x.cpu_percent, reverse=True)

        # 使用模型更新数据，极大提高性能
        self.process_model.update_data(processes)
