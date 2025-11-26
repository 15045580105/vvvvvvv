from PyQt5 import QtWidgets
from PyQt5.QtCore import Qt as _Qt

from app.common.ui.widgets import ModernButton, TableButton
from app.presentation.views.base_view import BaseView

# Compatibility constants to avoid linter false-positives and keep PyQt5 behavior
ALIGN_CENTER = int(getattr(_Qt, "AlignCenter", 132))  # 0x0004 | 0x0080
USER_ROLE = int(getattr(_Qt, "UserRole", 256))

# Action column sizing (user-friendly, consistent across rows)
ACTION_BTN_W = 80
ACTION_BTN_H = 28
ACTION_BTN_SPACING = 8
ACTION_COL_HMARGIN = 8  # left/right margins inside the cell widget layout
ACTION_COL_WIDTH = ACTION_BTN_W * 2 + ACTION_BTN_SPACING + ACTION_COL_HMARGIN * 2


class LogDownloadView(BaseView):
    def setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(16)
        toolbar_group = QtWidgets.QGroupBox("下载控制")
        toolbar_layout = QtWidgets.QHBoxLayout()
        toolbar_layout.setSpacing(12)
        toolbar_layout.addWidget(QtWidgets.QLabel("📁 日志路径:"))
        self.path_input = QtWidgets.QLineEdit("/var/log/diagnostics")
        self.path_input.setMinimumWidth(300)
        toolbar_layout.addWidget(self.path_input)
        self.connect_btn = ModernButton("连接设备", "#059669", "🔗")
        self.refresh_btn = ModernButton("刷新列表", "#0EA5E9", "🔄")
        self.stop_all_btn = ModernButton("全部停止", "#F59E0B", "⏹️")
        for b in [self.connect_btn, self.refresh_btn, self.stop_all_btn]:
            toolbar_layout.addWidget(b)
        search_layout = QtWidgets.QHBoxLayout()
        search_layout.addWidget(QtWidgets.QLabel("🔍 搜索:"))
        self.search_input = QtWidgets.QLineEdit()
        self.search_input.setPlaceholderText("输入文件名、APPID或关键词...")
        search_layout.addWidget(self.search_input)
        toolbar_layout.addLayout(search_layout)
        toolbar_group.setLayout(toolbar_layout)
        layout.addWidget(toolbar_group)
        self.table = QtWidgets.QTableWidget(0,7)
        self.table.setHorizontalHeaderLabels(["文件名","文件大小","修改时间","下载进度","状态","传输速度","操作"])
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        # --- UI optimizations: height and column sizing ---
        self.table.setMinimumHeight(420)  # 增加表格整体高度，避免文字被裁剪
        self.table.setWordWrap(False)
        vheader = self.table.verticalHeader()
        vheader.setDefaultSectionSize(50)    # 默认行高稍微更高，留出按钮与文字空间
        vheader.setMinimumSectionSize(38)
        hheader = self.table.horizontalHeader()
        hheader.setStretchLastSection(False)
        # 列宽策略：文件名/进度可伸展；尺寸/时间/状态/速度自适应；操作列固定宽度
        hheader.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        hheader.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        hheader.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
        hheader.setSectionResizeMode(3, QtWidgets.QHeaderView.Stretch)
        hheader.setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeToContents)
        hheader.setSectionResizeMode(5, QtWidgets.QHeaderView.ResizeToContents)
        hheader.setSectionResizeMode(6, QtWidgets.QHeaderView.Fixed)
        # 固定操作列宽度，按两个按钮+间距+边距计算，防止按钮挤压或被拉伸
        self.table.setColumnWidth(6, ACTION_COL_WIDTH)
        layout.addWidget(self.table)

    def populate(self, files):
        self.table.setRowCount(len(files))
        for i,(name,size,time) in enumerate(files):
            name_item = QtWidgets.QTableWidgetItem(f"📄 {name}")
            name_item.setData(USER_ROLE, name)
            self.table.setItem(i,0,name_item)
            size_item = QtWidgets.QTableWidgetItem(size)
            size_item.setTextAlignment(ALIGN_CENTER)
            self.table.setItem(i,1,size_item)
            time_item = QtWidgets.QTableWidgetItem(time)
            time_item.setTextAlignment(ALIGN_CENTER)
            self.table.setItem(i,2,time_item)
            progress_widget = QtWidgets.QWidget()
            p_layout = QtWidgets.QHBoxLayout(progress_widget)
            p_layout.setContentsMargins(6,4,6,4)
            bar = QtWidgets.QProgressBar()
            bar.setRange(0,100)
            bar.setValue(0)
            bar.setFormat("0%")
            p_layout.addWidget(bar)
            cancel_btn = QtWidgets.QPushButton("✕")
            cancel_btn.setFixedSize(24,24)
            cancel_btn.setStyleSheet("QPushButton { background-color:#EF4444;color:white;border:none;border-radius:12px;font-weight:bold;} QPushButton:hover { background-color:#DC2626; }")
            p_layout.addWidget(cancel_btn)
            p_layout.addStretch()
            self.table.setCellWidget(i,3,progress_widget)
            status_item = QtWidgets.QTableWidgetItem("⏸️ 等待")
            status_item.setTextAlignment(ALIGN_CENTER)
            self.table.setItem(i,4,status_item)
            speed_item = QtWidgets.QTableWidgetItem("---")
            speed_item.setTextAlignment(ALIGN_CENTER)
            self.table.setItem(i,5,speed_item)
            # 操作列：两个固定尺寸按钮，左右留白，整体不随表格拉伸
            btn_widget = QtWidgets.QWidget()
            btn_layout = QtWidgets.QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(ACTION_COL_HMARGIN,4,ACTION_COL_HMARGIN,4)
            btn_layout.setSpacing(ACTION_BTN_SPACING)
            download_btn = TableButton("下载", "#10B981", "⬇️")
            view_btn = TableButton("查看", "#0EA5E9", "👁️")
            for b in (download_btn, view_btn):
                b.setFixedSize(ACTION_BTN_W, ACTION_BTN_H)
                b.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
            btn_layout.addStretch(1)
            btn_layout.addWidget(download_btn)
            btn_layout.addWidget(view_btn)
            btn_layout.addStretch(1)
            self.table.setCellWidget(i,6,btn_widget)
if __name__ == '__main__':
    import sys
    app = QtWidgets.QApplication(sys.argv)
    w = LogDownloadView()
    w.populate([
        ("diagnostics_20240601.log", "2.3 MB", "2024-06-01 14:23:45"),
        ("error_20240601.log", "1.1 MB", "2024-06-01 13:15:22"),
        ("system_20240601.log", "5.6 MB", "2024-06-01 12:05:10"),
    ])
    w.show()
    sys.exit(app.exec_())
