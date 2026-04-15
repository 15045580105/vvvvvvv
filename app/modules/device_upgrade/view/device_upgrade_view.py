# python
from PyQt5 import QtWidgets, QtGui
from PyQt5.QtCore import pyqtSignal, Qt
from datetime import datetime

from app.common.ui.widgets import ModernButton, TableButton
from app.common.ui.log_splitter import LogAreaSplitter
from app.common.ui.log_panel import LogPanelBuilder
from app.presentation.views.base_view import BaseView


class DragDropLineEdit(QtWidgets.QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            self.setText(path)


class UpgradeView(BaseView):
    """纯 UI 升级页面：仅负责界面布局，不包含业务逻辑或信号。"""

    browse_file_signal = pyqtSignal(QtWidgets.QLineEdit, str)
    stress_pkg_changed = pyqtSignal()

    def setup_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        splitter = LogAreaSplitter(self, min_log_height=300, max_log_ratio=0.9)
        main_layout.addWidget(splitter)

        content_widget = QtWidgets.QWidget()
        content_layout = QtWidgets.QVBoxLayout(content_widget)
        content_layout.setContentsMargins(12, 12, 12, 12)
        content_layout.setSpacing(12)

        # --- Tab widget 包含：常规升级 / 升级压测 ---
        self.tab = QtWidgets.QTabWidget()
        self._init_normal_upgrade_tab()
        self._init_stress_tab()
        content_layout.addWidget(self.tab)

        log_group = QtWidgets.QGroupBox("操作日志")
        log_layout = QtWidgets.QVBoxLayout(log_group)
        log_layout.setContentsMargins(8, 12, 8, 8)

        self.clear_btn = TableButton("清空日志", "#6B7280", "🧹")

        self.upgrade_log = QtWidgets.QTextEdit()
        self.upgrade_log.setReadOnly(True)
        self.upgrade_log.setFont(QtGui.QFont("Consolas", 9))
        self.upgrade_log.setMinimumHeight(0)
        LogPanelBuilder.attach_search(log_layout, self.upgrade_log, trailing_widgets=[self.clear_btn])
        log_layout.addWidget(self.upgrade_log)

        splitter.set_panels(content_widget, log_group, initial_log_height=800)

        # Set initial sizes (Tab minimum, Log maximum)
        splitter.setStretchFactor(0, 0) # Tab
        splitter.setStretchFactor(1, 1) # Log
        splitter.setCollapsible(1, False)

    # -------------------- 常规升级 Tab --------------------
    def _init_normal_upgrade_tab(self):
        """常规升级：保持原来的单升级包 + 配置 + 校验 UI，不含循环次数和 +/-。"""
        normal_page = QtWidgets.QWidget()
        layout = QtWidgets.QGridLayout(normal_page)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(8)

        # 升级包（单行，无 +/-）
        layout.addWidget(QtWidgets.QLabel("📦 升级包:"), 0, 0)
        self.upgrade_file = DragDropLineEdit()
        self.upgrade_file.setPlaceholderText("选择升级包 (.zip) - 支持拖入文件")
        layout.addWidget(self.upgrade_file, 0, 1)
        self.upgrade_file_browse_btn = ModernButton("浏览", "#0EA5E9", "📂")
        self.upgrade_file_browse_btn.clicked.connect(lambda: self.browse_file_signal.emit(self.upgrade_file, "选择升级包 (*.zip)"))
        layout.addWidget(self.upgrade_file_browse_btn, 0, 2)

        # Config file
        layout.addWidget(QtWidgets.QLabel("⚙️ 配置文件:"), 1, 0)
        self.config_file = DragDropLineEdit()
        self.config_file.setPlaceholderText("选择升级配置 (.json) - 支持拖入文件")
        layout.addWidget(self.config_file, 1, 1)
        self.config_file_browse_btn = ModernButton("浏览", "#0EA5E9", "📂")
        self.config_file_browse_btn.clicked.connect(lambda: self.browse_file_signal.emit(self.config_file, "选择升级配置 (*.json)"))
        layout.addWidget(self.config_file_browse_btn, 1, 2)

        # 进度条
        layout.addWidget(QtWidgets.QLabel("⏳ 进度:"), 2, 0)
        self.normal_progress = QtWidgets.QProgressBar()
        self.normal_progress.setRange(0, 100)
        self.normal_progress.setValue(0)
        self.normal_progress.setTextVisible(True)
        layout.addWidget(self.normal_progress, 2, 1, 1, 2)

        # Action buttons row（沿用原来的开始/停止按钮）
        action_row = QtWidgets.QHBoxLayout()
        action_row.setSpacing(12)
        action_row.addStretch(1)
        self.start_btn = ModernButton("开始升级", "#059669", "🚀")
        self.stop_btn = ModernButton("停止升级", "#EF4444", "⏹️")
        self.start_btn.setEnabled(False)  # 需选择文件后启用
        self.stop_btn.setEnabled(False)
        action_row.addWidget(self.start_btn)
        action_row.addWidget(self.stop_btn)

        layout.addLayout(action_row, 3, 0, 1, 3)

        self.tab.addTab(normal_page, "常规升级")

    # -------------------- 升级压测 Tab --------------------
    def _init_stress_tab(self):
        """升级压测：支持多升级包、循环次数、配置文件和校验信息。"""
        stress_page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(stress_page)

        # 1. Top Toolbar for Table
        top_bar = QtWidgets.QHBoxLayout()
        top_bar.addWidget(QtWidgets.QLabel("📋 压测任务列表"))
        top_bar.addStretch()

        self.add_task_btn = ModernButton("添加任务", "#10B981", "➕")
        self.add_task_btn.setFixedHeight(30)
        self.add_task_btn.clicked.connect(self._add_stress_pkg_row)

        self.del_task_btn = ModernButton("删除选中", "#EF4444", "➖")
        self.del_task_btn.setFixedHeight(30)
        self.del_task_btn.clicked.connect(self._remove_selected_stress_row)

        top_bar.addWidget(self.add_task_btn)
        top_bar.addWidget(self.del_task_btn)

        layout.addLayout(top_bar)

        # 2. Files Table
        self.stress_table = QtWidgets.QTableWidget()
        self.stress_table.setColumnCount(2)
        self.stress_table.setHorizontalHeaderLabels(["📦 升级包路径 (.zip / .bin)", "⚙️ 配置文件路径 (.json)"])
        self.stress_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.stress_table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)

        # Column setup
        header = self.stress_table.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)

        self.stress_table.verticalHeader().setVisible(True)
        self.stress_table.verticalHeader().setDefaultSectionSize(55)
        self.stress_table.setAlternatingRowColors(True)
        layout.addWidget(self.stress_table)

        # 3. Bottom Controls Panel
        bottom_panel = QtWidgets.QFrame()
        bottom_panel.setStyleSheet(".QFrame { background-color: #F9FAFB; border-top: 1px solid #E5E7EB; }")
        bottom_layout = QtWidgets.QGridLayout(bottom_panel)
        bottom_layout.setContentsMargins(10, 10, 10, 10)
        bottom_layout.setHorizontalSpacing(20)

        # Loop Count
        loop_container = QtWidgets.QHBoxLayout()
        loop_container.addWidget(QtWidgets.QLabel("🔁 压测循环次数:"))
        self.stress_loop_spin = QtWidgets.QSpinBox()
        self.stress_loop_spin.setRange(1, 1_000_000)
        self.stress_loop_spin.setValue(100)
        self.stress_loop_spin.setFixedWidth(120)
        self.stress_loop_spin.setFixedHeight(35)
        loop_container.addWidget(self.stress_loop_spin)
        bottom_layout.addLayout(loop_container, 0, 0)

        # Progress
        progress_container = QtWidgets.QHBoxLayout()
        progress_container.addWidget(QtWidgets.QLabel("⏳ 总体进度:"))
        self.stress_progress = QtWidgets.QProgressBar()
        self.stress_progress.setRange(0, 100)
        self.stress_progress.setFixedHeight(25)
        progress_container.addWidget(self.stress_progress)
        bottom_layout.addLayout(progress_container, 0, 1)

        # Buttons
        btn_container = QtWidgets.QHBoxLayout()
        btn_container.addStretch()
        self.stress_start_btn = ModernButton("开始压测", "#0F766E", "🔥")
        self.stress_stop_btn = ModernButton("停止压测", "#DC2626", "⏹️")
        self.stress_start_btn.setFixedHeight(36)
        self.stress_stop_btn.setFixedHeight(36)
        self.stress_start_btn.setEnabled(False)
        self.stress_stop_btn.setEnabled(False)

        btn_container.addWidget(self.stress_start_btn)
        btn_container.addWidget(self.stress_stop_btn)

        bottom_layout.addLayout(btn_container, 1, 0, 1, 2)

        layout.addWidget(bottom_panel)

        self.tab.addTab(stress_page, "升级压测")

        # Initialize with one empty row
        self._add_stress_pkg_row()

    # -------------------- 升级压测：多包行管理 --------------------
    def _create_file_selector(self, placeholder, filter_str):
        """Helper to create a cell widget with QLineEdit + Browse Button"""
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(widget)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(6)

        line_edit = DragDropLineEdit()
        line_edit.setPlaceholderText(placeholder)
        line_edit.setStyleSheet("QLineEdit { border: 1px solid #D1D5DB; border-radius: 3px; padding: 2px; }")

        # Optimization: Select row when clicking/focusing the editable line edit
        orig_focus_in = line_edit.focusInEvent
        def focus_handler(event):
            orig_focus_in(event)
            container = line_edit.parent()
            for r in range(self.stress_table.rowCount()):
                if self.stress_table.cellWidget(r, 0) == container or \
                   self.stress_table.cellWidget(r, 1) == container:
                    self.stress_table.selectRow(r)
                    break
        line_edit.focusInEvent = focus_handler

        browse_btn = ModernButton("📂", "#0EA5E9") # Icon only for compactness
        browse_btn.setFixedSize(32, 30)
        browse_btn.setToolTip("浏览文件")

        browse_btn.clicked.connect(lambda: self.browse_file_signal.emit(line_edit, filter_str))
        line_edit.textChanged.connect(lambda: self.stress_pkg_changed.emit())

        layout.addWidget(line_edit, 1) # Edit stretches
        layout.addWidget(browse_btn)

        return widget

    def _add_stress_pkg_row(self):
        row_idx = self.stress_table.rowCount()
        self.stress_table.insertRow(row_idx)

        # 1. Package Selector
        pkg_widget = self._create_file_selector("选择升级包...", "选择升级包 (*.zip *.bin)")
        self.stress_table.setCellWidget(row_idx, 0, pkg_widget)

        # 2. Config Selector
        cfg_widget = self._create_file_selector("选择配置...", "选择升级配置 (*.json)")
        self.stress_table.setCellWidget(row_idx, 1, cfg_widget)

        # Emit change signal to update start button state
        self.stress_pkg_changed.emit()

    def _remove_selected_stress_row(self):
        """删除选中行，至少保留一行（或允许删光由业务决定，这里尽量保留一行空行如果是初始状态）。"""
        # Get selected rows
        selected_rows = sorted(set(index.row() for index in self.stress_table.selectedIndexes()), reverse=True)

        # If no selection, remove the last one? Or do nothing?
        # User expectation might be delete last added if nothing selected
        if not selected_rows:
            if self.stress_table.rowCount() > 0:
                selected_rows = [self.stress_table.rowCount() - 1]

        if not selected_rows:
            return

        for row in selected_rows:
            # Prevent removing the last remaining row ?
            # Or just remove it and if empty, maybe add a new empty one?
            # Current logic: keep at least 1 row?
            if self.stress_table.rowCount() <= 1:
                # If it's the last one, maybe just clear contents?
                # But simplify: just don't delete if it's the only one
                return

            self.stress_table.removeRow(row)

        self.stress_pkg_changed.emit()

    def get_stress_task_list(self):
        """Retrieve list of tasks from table. Returns list of dicts {'pkg': path, 'cfg': path}."""
        tasks = []
        for i in range(self.stress_table.rowCount()):
            pkg_container = self.stress_table.cellWidget(i, 0)
            cfg_container = self.stress_table.cellWidget(i, 1)

            p_edit = pkg_container.findChild(QtWidgets.QLineEdit) if pkg_container else None
            c_edit = cfg_container.findChild(QtWidgets.QLineEdit) if cfg_container else None

            if p_edit and c_edit:
                tasks.append({
                    'pkg': p_edit.text().strip(),
                    'cfg': c_edit.text().strip()
                })
        return tasks

    def set_stress_task_list(self, tasks):
        """Populate table from list of dicts."""
        self.stress_table.setRowCount(0)
        for t in tasks:
            self._add_stress_pkg_row() # Adds an empty row at end
            last_row = self.stress_table.rowCount() - 1

            pkg_container = self.stress_table.cellWidget(last_row, 0)
            cfg_container = self.stress_table.cellWidget(last_row, 1)

            p_edit = pkg_container.findChild(QtWidgets.QLineEdit)
            c_edit = cfg_container.findChild(QtWidgets.QLineEdit)

            if p_edit: p_edit.setText(t.get('pkg', ''))
            if c_edit: c_edit.setText(t.get('cfg', ''))


        self.stress_pkg_changed.emit()

    def clear_stress_pkg_rows(self):
        """Clears all dynamic package rows, resetting to a single empty row."""
        # Remove all existing widgets in layout
        while self.stress_pkg_layout.count():
            item = self.stress_pkg_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)

        self.stress_pkg_rows = []
        self._add_stress_pkg_row() # Add one initial row

    def set_stress_pkg_paths(self, paths):
        """Reconstructs the UI with the given list of file paths."""
        if not paths:
            return

        # Clear existing except logic is tricky because we need at least one row
        # So we clear all, then add specific ones
        while self.stress_pkg_layout.count():
            item = self.stress_pkg_layout.takeAt(0)
            w = item.widget()
            if w: w.setParent(None)
        self.stress_pkg_rows = []

        for p in paths:
            self._add_stress_pkg_row()
            # Last added is at end
            last_edit = self.stress_pkg_rows[-1][0]
            last_edit.setText(p)

    def show_device_targets(self, devices):
        """在升级界面显示目标设备信息（如设备名/IP等）"""
        # 功能已裁剪：仅保留接口以避免其他模块引用报错
        # 如果未来需要重新展示设备信息，可在此补充 UI 元素
        pass

    def log_message(self, message: str, is_info: bool = True):
        timestamp = datetime.now().strftime("%H:%M:%S")
        color = "#1F2937"

        # Heuristic coloring
        if "失败" in message or "异常" in message or "警告" in message or "Error" in message:
            color = "#DC2626"
        elif "成功" in message or "通过" in message:
            color = "#059669"
        elif "开始" in message or "结束" in message:
            color = "#2563EB"

        html_msg = f'<span style="color: {color};">[{timestamp}] {message}</span>'
        self.upgrade_log.append(html_msg)
        # Scroll to bottom
        self.upgrade_log.moveCursor(QtGui.QTextCursor.End)


if __name__ == "__main__":
    app = QtWidgets.QApplication([])
    w = UpgradeView()
    w.setup_ui()
    w.show()
    app.exec_()
