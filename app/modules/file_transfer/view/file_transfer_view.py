from PyQt5 import QtWidgets, QtCore

from app.common.ui.widgets import ModernButton, TableButton
from app.presentation.views.base_view import BaseView

# Qt orientation compatibility constants
QT_HORIZONTAL = getattr(QtCore.Qt, "Horizontal", 1)
QT_VERTICAL = getattr(QtCore.Qt, "Vertical", 2)
ALIGN_CENTER = int(getattr(QtCore.Qt, "AlignCenter", 132))


class FileTransferView(BaseView):
    def setup_ui(self):
        layout = QtWidgets.QHBoxLayout(self)
        layout.setSpacing(8)
        local_panel = QtWidgets.QGroupBox("本地文件")
        local_layout = QtWidgets.QVBoxLayout()
        local_header = QtWidgets.QHBoxLayout()
        local_header.addWidget(QtWidgets.QLabel("📁 路径:"))
        self.local_path = QtWidgets.QLineEdit("C:/Diagnostics/Logs")
        local_header.addWidget(self.local_path)
        local_header.addWidget(ModernButton("浏览...", "#0EA5E9", "📂"))
        local_layout.addLayout(local_header)
        self.local_tree = QtWidgets.QTreeWidget()
        self.local_tree.setHeaderLabels(["名称","大小","修改时间"])
        self.local_tree.setColumnCount(3)
        local_layout.addWidget(self.local_tree)
        local_panel.setLayout(local_layout)
        btn_panel = QtWidgets.QVBoxLayout()
        btn_panel.setSpacing(14)
        btn_panel.setContentsMargins(0, 0, 0, 0)
        btn_panel.addStretch(1)
        # 上传按钮居中
        self.upload_btn = TableButton("上传", "#059669", "➡")
        self.upload_btn.setFixedWidth(120)
        upload_row = QtWidgets.QHBoxLayout()
        upload_row.setSpacing(0)
        upload_row.addStretch(1)
        upload_row.addWidget(self.upload_btn)
        upload_row.addStretch(1)
        btn_panel.addLayout(upload_row)
        # 下载按钮居中
        self.download_btn = TableButton("下载", "#F59E0B", "⬅")
        self.download_btn.setFixedWidth(120)
        download_row = QtWidgets.QHBoxLayout()
        download_row.setSpacing(0)
        download_row.addStretch(1)
        download_row.addWidget(self.download_btn)
        download_row.addStretch(1)
        btn_panel.addLayout(download_row)
        btn_panel.addStretch(1)
        remote_panel = QtWidgets.QGroupBox("远程设备文件 (/log)")
        remote_layout = QtWidgets.QVBoxLayout()
        remote_header = QtWidgets.QHBoxLayout()
        remote_header.addWidget(QtWidgets.QLabel("🔍 搜索:"))
        self.remote_filter = QtWidgets.QLineEdit()
        self.remote_filter.setPlaceholderText("APPID或路径...")
        remote_header.addWidget(self.remote_filter)
        remote_header.addWidget(ModernButton("刷新", "#0EA5E9", "🔄"))
        remote_layout.addLayout(remote_header)
        self.remote_tree = QtWidgets.QTreeWidget()
        self.remote_tree.setHeaderLabels(["文件路径","APPID","大小(KB)","创建时间","修改时间"])
        self.remote_tree.setColumnCount(5)
        remote_layout.addWidget(self.remote_tree)
        remote_panel.setLayout(remote_layout)
        task_panel = QtWidgets.QGroupBox("传输任务队列")
        task_layout = QtWidgets.QVBoxLayout()
        self.task_table = QtWidgets.QTableWidget(0,4)
        self.task_table.setHorizontalHeaderLabels(["文件名","进度","状态","操作"])
        # 优化任务表格视觉与行为
        self.task_table.verticalHeader().setVisible(False)
        self.task_table.setAlternatingRowColors(True)
        self.task_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.task_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.task_table.setWordWrap(False)
        vh = self.task_table.verticalHeader()
        vh.setDefaultSectionSize(42)
        vh.setMinimumSectionSize(38)
        hh = self.task_table.horizontalHeader()
        hh.setStretchLastSection(False)
        hh.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)  # 文件名
        hh.setSectionResizeMode(1, QtWidgets.QHeaderView.Fixed)    # 进度
        self.task_table.setColumnWidth(1, 180)
        hh.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)  # 状态
        hh.setSectionResizeMode(3, QtWidgets.QHeaderView.Fixed)    # 操作
        self.task_table.setColumnWidth(3, 150)
        task_layout.addWidget(self.task_table)
        task_panel.setLayout(task_layout)
        file_splitter = QtWidgets.QSplitter(QT_HORIZONTAL)
        file_splitter.addWidget(local_panel)
        btn_widget = QtWidgets.QWidget()
        btn_widget.setLayout(btn_panel)
        btn_widget.setMaximumWidth(170)
        file_splitter.addWidget(btn_widget)
        file_splitter.addWidget(remote_panel)
        file_splitter.setSizes([380,140,420])
        main_splitter = QtWidgets.QSplitter(QT_VERTICAL)
        main_splitter.addWidget(file_splitter)
        main_splitter.addWidget(task_panel)
        main_splitter.setSizes([560,180])
        layout.addWidget(main_splitter)
        # 初始化进度条引用存储
        self._task_progress_bars = {}

    # --- Helper methods for task table ---
    def populate_tasks(self, tasks):
        """tasks: List[Dict{name:str, progress:int, status:str}]"""
        # 清空旧引用
        self._task_progress_bars.clear()
        self.task_table.setRowCount(len(tasks))
        for row, t in enumerate(tasks):
            # 文件名
            name_item = QtWidgets.QTableWidgetItem(t.get("name", ""))
            name_item.setToolTip(t.get("name", ""))
            self.task_table.setItem(row, 0, name_item)
            # 进度（进度条 + 取消按钮）
            progress_widget = QtWidgets.QWidget()
            pw_layout = QtWidgets.QHBoxLayout(progress_widget)
            pw_layout.setContentsMargins(6,4,6,4)
            pw_layout.setSpacing(8)
            bar = QtWidgets.QProgressBar()
            bar.setRange(0,100)
            bar.setValue(int(t.get("progress", 0)))
            bar.setFormat(f"{int(t.get('progress',0))}%")
            bar.setTextVisible(True)
            bar.setMinimumWidth(110)
            pw_layout.addWidget(bar)
            cancel_btn = TableButton("取消", "#EF4444", "✕")
            cancel_btn.setFixedWidth(50)
            pw_layout.addWidget(cancel_btn)
            pw_layout.addStretch(1)
            self.task_table.setCellWidget(row, 1, progress_widget)
            # 状态
            status_item = QtWidgets.QTableWidgetItem(t.get("status", "等待"))
            status_item.setTextAlignment(ALIGN_CENTER)
            self.task_table.setItem(row, 2, status_item)
            # 操作（重试 / 删除）
            action_widget = QtWidgets.QWidget()
            aw_layout = QtWidgets.QHBoxLayout(action_widget)
            aw_layout.setContentsMargins(6,4,6,4)
            aw_layout.setSpacing(8)
            retry_btn = TableButton("重试", "#0EA5E9", "🔄")
            retry_btn.setFixedWidth(60)
            delete_btn = TableButton("删除", "#6B7280", "🗑")
            delete_btn.setFixedWidth(60)
            aw_layout.addStretch(1)
            aw_layout.addWidget(retry_btn)
            aw_layout.addWidget(delete_btn)
            aw_layout.addStretch(1)
            self.task_table.setCellWidget(row, 3, action_widget)
            # 存储进度条引用
            self._task_progress_bars[row] = bar

    def update_task_progress(self, row: int, progress: int):
        if row not in self._task_progress_bars:
            return
        bar = self._task_progress_bars[row]
        clamped = max(0, min(100, int(progress)))
        bar.setValue(clamped)
        bar.setFormat(f"{clamped}%")
        status_item = self.task_table.item(row, 2)
        if status_item:
            status_item.setText("完成" if clamped >= 100 else "进行中")

if __name__ == '__main__':
    app = QtWidgets.QApplication([])
    view = FileTransferView()
    view.setup_ui()
    # 示例填充任务
    demo_tasks = [
        {"name": "log_2025_11_26.txt", "progress": 25, "status": "进行中"},
        {"name": "ecu_dump.bin", "progress": 90, "status": "进行中"},
        {"name": "session_trace.pcap", "progress": 100, "status": "完成"},
    ]
    view.populate_tasks(demo_tasks)
    view.show()
    app.exec_()