# python
from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtCore import Qt as _Qt, pyqtSignal

from app.common.ui.widgets import ModernButton, TableButton
from app.presentation.views.base_view import BaseView

ALIGN_CENTER = int(getattr(_Qt, "AlignCenter", 132))
USER_ROLE = int(getattr(_Qt, "UserRole", 256))

ACTION_BTN_W = 84
ACTION_BTN_H = 30
ACTION_BTN_SPACING = 10
ACTION_COL_HMARGIN = 10
ACTION_COL_WIDTH = ACTION_BTN_W * 2 + ACTION_BTN_SPACING + ACTION_COL_HMARGIN * 2

STATUS_OPTIONS = ["全部", "等待", "下载中", "已完成", "失败"]


class LogDownloadView(BaseView):
    # ---- 对外信号：交互事件交给 Controller 处理 ----
    sig_search_clicked = pyqtSignal(dict)          # {path_kw, app_kw, name_kw, status, date_from, date_to}
    sig_refresh_clicked = pyqtSignal()
    sig_page_changed = pyqtSignal(int)             # 目标页码
    sig_page_size_changed = pyqtSignal(int)        # 每页条数
    # 新增：表格操作信号（让 Controller 知道哪一行被点击了）
    sig_download_clicked = pyqtSignal(int)         # 行号 row
    sig_cancel_clicked = pyqtSignal(int)           # 行号 row

    def __init__(self, parent=None):
        super().__init__(parent)
        # View 不再保存数据和分页状态，这些交由 Model/Controller 管理

    def setup_ui(self):
        if not hasattr(self, "all_files"): self.all_files = []
        if not hasattr(self, "filtered_files"): self.filtered_files = []
        if not hasattr(self, "page"): self.page = 1
        if not hasattr(self, "page_size"): self.page_size = 10


        root = QtWidgets.QVBoxLayout(self)
        root.setSpacing(14)
        root.setContentsMargins(14, 14, 14, 14)

        # 顶部过滤查询（工具栏布局）
        filter_card = QtWidgets.QGroupBox("过滤查询")
        fc = QtWidgets.QVBoxLayout(filter_card)
        fc.setContentsMargins(12, 8, 12, 12)
        toolbar = QtWidgets.QGridLayout()
        toolbar.setHorizontalSpacing(10)
        toolbar.setVerticalSpacing(8)

        self.path_input = QtWidgets.QLineEdit()
        self.path_input.setPlaceholderText("输入 path")
        self.appid_input = QtWidgets.QLineEdit()
        self.appid_input.setPlaceholderText("输入 appid")
        self.filename_input = QtWidgets.QLineEdit()
        self.filename_input.setPlaceholderText("输入 filename")

        self.date_from = QtWidgets.QDateTimeEdit(QtCore.QDateTime.currentDateTime())
        self.date_from.setCalendarPopup(True)
        self.date_from.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.date_to = QtWidgets.QDateTimeEdit(QtCore.QDateTime.currentDateTime())
        self.date_to.setCalendarPopup(True)
        self.date_to.setDisplayFormat("yyyy-MM-dd HH:mm:ss")

        self.status_combo = QtWidgets.QComboBox()
        self.status_combo.addItems(STATUS_OPTIONS)

        self.search_btn = ModernButton("搜索", "#2563EB", "🔍")
        self.refresh_btn = ModernButton("刷新", "#10B981", "🔄")

        # 两行排布，更紧凑
        toolbar.addWidget(QtWidgets.QLabel("Path"), 0, 0)
        toolbar.addWidget(self.path_input, 0, 1)
        toolbar.addWidget(QtWidgets.QLabel("AppID"), 0, 2)
        toolbar.addWidget(self.appid_input, 0, 3)
        toolbar.addWidget(QtWidgets.QLabel("Filename"), 0, 4)
        toolbar.addWidget(self.filename_input, 0, 5)

        toolbar.addWidget(QtWidgets.QLabel("创建时间从"), 1, 0)
        toolbar.addWidget(self.date_from, 1, 1)
        toolbar.addWidget(QtWidgets.QLabel("到"), 1, 2)
        toolbar.addWidget(self.date_to, 1, 3)
        toolbar.addWidget(QtWidgets.QLabel("下载状态"), 1, 4)
        toolbar.addWidget(self.status_combo, 1, 5)

        btns = QtWidgets.QHBoxLayout()
        btns.addStretch(1)
        btns.addWidget(self.search_btn)
        btns.addWidget(self.refresh_btn)

        fc.addLayout(toolbar)
        fc.addLayout(btns)
        root.addWidget(filter_card)

        # 表格
        # 10 列：序号, FileName, Path, APPID, Size(KB), CreateTime, ModifiedTime, 下载进度, 状态, 操作
        self.table = QtWidgets.QTableWidget(0, 10)
        self.table.setHorizontalHeaderLabels([
            "序号",
            "FileName",
            "Path",
            "APPID",
            "Size(KB)",
            "CreateTime",
            "ModifiedTime",
            "下载进度",
            "状态",
            "操作",
        ])
        self.table.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        pal = self.table.palette()
        pal.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor("#F9FAFB"))
        self.table.setPalette(pal)
        self.table.setMinimumHeight(420)
        self.table.setWordWrap(False)

        # 调整行高和列宽策略
        vheader = self.table.verticalHeader()
        # 行高在这里调，高一些比如 46 像素
        vheader.setDefaultSectionSize(55)
        vheader.setMinimumSectionSize(40)
        vheader.setSectionResizeMode(QtWidgets.QHeaderView.Fixed)

        hheader = self.table.horizontalHeader()
        # 让列表头根据窗口宽度拉伸，填满整个表格区域
        hheader.setStretchLastSection(True)
        hheader.setHighlightSections(False)
        hheader.setDefaultSectionSize(100)
        hheader.setMinimumSectionSize(60)
        # 序号窄一些，按内容
        hheader.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        # FileName 适中
        hheader.setSectionResizeMode(1, QtWidgets.QHeaderView.Interactive)
        self.table.setColumnWidth(1, 180)
        # Path 列更长
        hheader.setSectionResizeMode(2, QtWidgets.QHeaderView.Interactive)
        self.table.setColumnWidth(2, 360)
        # APPID、Size、时间列按内容
        hheader.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeToContents)
        hheader.setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeToContents)
        hheader.setSectionResizeMode(5, QtWidgets.QHeaderView.ResizeToContents)
        hheader.setSectionResizeMode(6, QtWidgets.QHeaderView.ResizeToContents)
        # 下载进度列稍微长一点，并参与拉伸
        hheader.setSectionResizeMode(7, QtWidgets.QHeaderView.Stretch)
        self.table.setColumnWidth(7, 260)
        # 状态列稍微加宽一些，避免文字被截断
        hheader.setSectionResizeMode(8, QtWidgets.QHeaderView.Interactive)
        self.table.setColumnWidth(8, 120)
        # 操作列比较短，只放两个按钮
        hheader.setSectionResizeMode(9, QtWidgets.QHeaderView.Fixed)
        self.table.setColumnWidth(9, ACTION_COL_WIDTH)

        root.addWidget(self.table)

        # 分页条（卡片式）
        pager_card = QtWidgets.QGroupBox()
        pager_card.setTitle("")
        pc = QtWidgets.QHBoxLayout(pager_card)
        pc.setContentsMargins(12, 8, 12, 8)
        pc.setSpacing(10)

        self.prev_btn = ModernButton("上一页", "#6366F1", "◀")
        self.next_btn = ModernButton("下一页", "#6366F1", "▶")
        self.page_label = QtWidgets.QLabel("第 1/1 页，共 0 条")
        self.page_label.setObjectName("muted")

        self.page_size_combo = QtWidgets.QComboBox()
        self.page_size_combo.addItems(["10", "20", "50", "100"])
        self.page_size_combo.setCurrentText(str(self.page_size))

        pc.addWidget(self.prev_btn)
        pc.addWidget(self.next_btn)
        pc.addSpacing(8)
        pc.addWidget(QtWidgets.QLabel("每页条数"))
        pc.addWidget(self.page_size_combo)
        pc.addStretch(1)
        pc.addWidget(self.page_label)

        root.addWidget(pager_card)

        # 信号：绑定到内部槽函数，内部只负责发射高层信号，不做业务逻辑
        self.search_btn.clicked.connect(self._on_search_clicked)
        self.refresh_btn.clicked.connect(self._on_refresh_clicked)
        self.prev_btn.clicked.connect(self._on_prev_page_clicked)
        self.next_btn.clicked.connect(self._on_next_page_clicked)
        self.page_size_combo.currentTextChanged.connect(self._on_page_size_changed)

    # ---- 供 Controller 调用的接口 ----
    def get_filter_criteria(self) -> dict:
        """从界面控件收集当前过滤条件，返回一个 dict。"""
        path_kw = self.path_input.text().strip()
        app_kw = self.appid_input.text().strip()
        name_kw = self.filename_input.text().strip()
        status = self.status_combo.currentText()
        date_from = self.date_from.dateTime()
        date_to = self.date_to.dateTime()
        return {
            "path_kw": path_kw,
            "app_kw": app_kw,
            "name_kw": name_kw,
            "status": status,
            "date_from": date_from,
            "date_to": date_to,
        }

    def render_rows(self, rows, page: int, page_count: int, total: int, page_size: int):
        """渲染一页数据。rows 已经是 model 归一化后的结构。

        rows: 可迭代，每个元素为 dict：
            {
                "filename": str,
                "path": str,
                "appid": str,
                "size_kb": int | str,
                "create_time": str,
                "modified_time": str,
                "progress": int,
                "status": str,
            }
        """
        self.table.setRowCount(len(rows))
        for row_idx, item in enumerate(rows):
            filename = str(item.get("filename", ""))
            path = str(item.get("path", ""))
            appid = str(item.get("appid", ""))
            size_kb = str(item.get("size_kb", ""))
            create_time = str(item.get("create_time", ""))
            modified_time = str(item.get("modified_time", ""))
            progress = int(item.get("progress", 0) or 0)
            status = str(item.get("status", "等待") or "等待")

            # 序号
            idx_item = QtWidgets.QTableWidgetItem(str((page - 1) * page_size + row_idx + 1))
            idx_item.setTextAlignment(_Qt.AlignCenter)
            self.table.setItem(row_idx, 0, idx_item)

            # FileName
            name_item = QtWidgets.QTableWidgetItem(filename)
            name_item.setData(USER_ROLE, filename)
            self.table.setItem(row_idx, 1, name_item)

            # Path
            path_item = QtWidgets.QTableWidgetItem(path)
            self.table.setItem(row_idx, 2, path_item)

            # APPID
            app_item = QtWidgets.QTableWidgetItem(appid)
            app_item.setTextAlignment(_Qt.AlignCenter)
            self.table.setItem(row_idx, 3, app_item)

            # Size(KB)
            size_item = QtWidgets.QTableWidgetItem(size_kb)
            size_item.setTextAlignment(_Qt.AlignCenter)
            self.table.setItem(row_idx, 4, size_item)

            # CreateTime
            ctime_item = QtWidgets.QTableWidgetItem(create_time)
            ctime_item.setTextAlignment(_Qt.AlignCenter)
            self.table.setItem(row_idx, 5, ctime_item)

            # ModifiedTime
            mtime_item = QtWidgets.QTableWidgetItem(modified_time)
            mtime_item.setTextAlignment(_Qt.AlignCenter)
            self.table.setItem(row_idx, 6, mtime_item)

            # 下载进度（进度条）
            progress_widget = QtWidgets.QWidget()
            p_layout = QtWidgets.QHBoxLayout(progress_widget)
            p_layout.setContentsMargins(4, 4, 4, 4)
            p_layout.setSpacing(0)

            bar = QtWidgets.QProgressBar(progress_widget)
            bar.setRange(0, 100)
            bar.setValue(progress)
            bar.setFormat(f"{progress}%")
            bar.setTextVisible(True)
            bar.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

            p_layout.addWidget(bar)
            self.table.setCellWidget(row_idx, 7, progress_widget)

            # 状态 chip
            status_chip = QtWidgets.QLabel(status)
            status_chip.setAlignment(_Qt.AlignCenter)
            status_chip.setMinimumHeight(24)
            status_chip.setStyleSheet(self._chip_style(status))
            self.table.setCellWidget(row_idx, 8, status_chip)

            # 操作列：下载 + 取消
            btn_widget = QtWidgets.QWidget()
            btn_layout = QtWidgets.QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(ACTION_COL_HMARGIN, 6, ACTION_COL_HMARGIN, 6)
            btn_layout.setSpacing(ACTION_BTN_SPACING)

            download_btn = TableButton("下载", "#10B981", "⬇️")
            cancel_btn = TableButton("取消", "#EF4444", "✕")
            for b in (download_btn, cancel_btn):
                b.setFixedSize(ACTION_BTN_W, ACTION_BTN_H)
                b.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)

            # 绑定按钮点击信号，发射行号
            download_btn.clicked.connect(lambda _=False, r=row_idx: self.sig_download_clicked.emit(int(r)))
            cancel_btn.clicked.connect(lambda _=False, r=row_idx: self.sig_cancel_clicked.emit(int(r)))

            btn_layout.addStretch(1)
            btn_layout.addWidget(download_btn)
            btn_layout.addWidget(cancel_btn)
            btn_layout.addStretch(1)
            self.table.setCellWidget(row_idx, 9, btn_widget)

        # 更新分页信息
        self.update_pager(page, page_count, total)

    def update_pager(self, page: int, page_count: int, total: int):
        self.page_label.setText(f"第 {page}/{page_count} 页，共 {total} 条")
        self.prev_btn.setEnabled(page > 1)
        self.next_btn.setEnabled(page < page_count)

    # ---- 内部槽：把 UI 事件转换成信号，交给 Controller ----
    def _on_search_clicked(self):
        criteria = self.get_filter_criteria()
        self.sig_search_clicked.emit(criteria)

    def _on_refresh_clicked(self):
        self.sig_refresh_clicked.emit()

    def _on_prev_page_clicked(self):
        # 让 Controller 负责边界控制，当前页由 Controller 管
        self.sig_page_changed.emit(-1)  # 使用 -1 表示上一页

    def _on_next_page_clicked(self):
        self.sig_page_changed.emit(+1)  # 使用 +1 表示下一页

    def _on_page_size_changed(self, text: str):
        try:
            size = int(text)
        except ValueError:
            size = 10
        self.sig_page_size_changed.emit(size)

    def _chip_style(self, status: str) -> str:
        color = {
            "等待": ("#F59E0B", "#FEF3C7"),
            "下载中": ("#3B82F6", "#DBEAFE"),
            "已完成": ("#10B981", "#D1FAE5"),
            "失败": ("#EF4444", "#FEE2E2"),
        }.get(status, ("#6B7280", "#F3F4F6"))
        return f"QLabel {{ color:{color[0]}; background:{color[1]}; border-radius:12px; padding:4px 10px; }}"

    # 兼容旧接口：Controller 还在调用 populate 时，简单转成 render_rows
    def populate(self, files=None):
        """兼容旧接口：如果 Controller 直接传入文件列表，这里直接作为一页渲染。"""
        if not files:
            files = []
        # 视为单页全部数据，page=1, page_count=1
        normalized = []
        for it in files:
            if isinstance(it, dict):
                normalized.append({
                    "filename": it.get("filename") or it.get("name") or "",
                    "path": it.get("path", ""),
                    "appid": it.get("appid") or it.get("app_id") or "",
                    "size_kb": it.get("size_kb") or it.get("size") or it.get("filesize") or "",
                    "create_time": it.get("create_time") or it.get("ctime") or it.get("created_at") or "",
                    "modified_time": it.get("modified_time") or it.get("mtime") or it.get("time") or "",
                    "progress": it.get("progress") or 0,
                    "status": it.get("status") or "等待",
                })
            else:
                # 简单序列兼容
                seq = list(it)
                normalized.append({
                    "filename": seq[0] if len(seq) > 0 else "",
                    "path": seq[1] if len(seq) > 1 else "",
                    "appid": seq[2] if len(seq) > 2 else "",
                    "size_kb": seq[3] if len(seq) > 3 else "",
                    "create_time": seq[4] if len(seq) > 4 else "",
                    "modified_time": seq[5] if len(seq) > 5 else "",
                    "progress": seq[6] if len(seq) > 6 else 0,
                    "status": seq[7] if len(seq) > 7 else "等待",
                })

        self.render_rows(normalized, page=1, page_count=1, total=len(normalized), page_size=max(1, len(normalized) or 1))
