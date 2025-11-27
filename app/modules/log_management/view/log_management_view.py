# python
from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtCore import Qt as _Qt

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

    def __init__(self, parent=None):
        super().__init__(parent)
        self.all_files = []
        self.filtered_files = []
        self.page = 1
        self.page_size = 10

    def setup_ui(self):
        if not hasattr(self, "all_files"): self.all_files = []
        if not hasattr(self, "filtered_files"): self.filtered_files = []
        if not hasattr(self, "page"): self.page = 1
        if not hasattr(self, "page_size"): self.page_size = 10

        # 全局样式
        self.setStyleSheet("""
        QWidget { font-family: "Microsoft YaHei"; }
        QGroupBox {
            border: 1px solid #E5E7EB;
            border-radius: 10px;
            margin-top: 12px;
            background: #FFFFFF;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 12px; top: -2px;
            background: transparent;
            color: #111827; font-weight: 600;
        }
        QLineEdit, QComboBox, QDateTimeEdit {
            height: 32px; padding: 4px 8px;
            border: 1px solid #D1D5DB; border-radius: 8px;
            background: #F9FAFB;
        }
        QLineEdit:focus, QComboBox:focus, QDateTimeEdit:focus {
            border: 1px solid #60A5FA; background: #FFFFFF;
        }
        QTableWidget {
            gridline-color: #E5E7EB;
            background: #FFFFFF;
            border: 1px solid #E5E7EB; border-radius: 10px;
        }
        QHeaderView::section {
            background: #F3F4F6; color: #374151;
            padding: 8px; border: none; border-right: 1px solid #E5E7EB;
        }
        QTableWidget::item { padding: 6px; }
        QProgressBar {
            border: 1px solid #E5E7EB; border-radius: 8px;
            background: #F3F4F6; text-align: center;
            height: 18px;
        }
        QProgressBar::chunk {
            background-color: #60A5FA; border-radius: 8px;
        }
        QLabel#muted {
            color: #6B7280;
        }
        """)

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
        self.table = QtWidgets.QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["文件名", "大小", "修改时间", "进度", "状态", "速度", "操作"])
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        pal = self.table.palette()
        pal.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor("#F9FAFB"))
        self.table.setPalette(pal)
        self.table.setMinimumHeight(420)
        self.table.setWordWrap(False)

        vheader = self.table.verticalHeader()
        vheader.setDefaultSectionSize(54)
        vheader.setMinimumSectionSize(42)
        vheader.setSectionResizeMode(QtWidgets.QHeaderView.Fixed)

        hheader = self.table.horizontalHeader()
        hheader.setStretchLastSection(False)
        hheader.setHighlightSections(False)
        #hheader.setDefaultAlignment()
        hheader.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        hheader.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        hheader.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
        hheader.setSectionResizeMode(3, QtWidgets.QHeaderView.Stretch)
        hheader.setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeToContents)
        hheader.setSectionResizeMode(5, QtWidgets.QHeaderView.ResizeToContents)
        hheader.setSectionResizeMode(6, QtWidgets.QHeaderView.Fixed)
        self.table.setColumnWidth(6, ACTION_COL_WIDTH)

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

        # 信号
        self.search_btn.clicked.connect(self.on_search)
        self.refresh_btn.clicked.connect(self.on_refresh)
        self.prev_btn.clicked.connect(self.on_prev_page)
        self.next_btn.clicked.connect(self.on_next_page)
        self.page_size_combo.currentTextChanged.connect(self.on_change_page_size)

    def populate(self, files):
        self.all_files = files[:]
        self.apply_filters(reset_page=True)

    def apply_filters(self, reset_page=False):
        path_kw = self.path_input.text().strip().lower()
        app_kw = self.appid_input.text().strip().lower()
        name_kw = self.filename_input.text().strip().lower()
        status_sel = self.status_combo.currentText()
        dt_from = self.date_from.dateTime().toSecsSinceEpoch()
        dt_to = self.date_to.dateTime().toSecsSinceEpoch()

        def normalize(it):
            if isinstance(it, dict):
                name = it.get("name") or it.get("filename") or ""
                size = it.get("size") or it.get("filesize") or ""
                time_str = it.get("time") or it.get("mtime") or it.get("created_at") or ""
                status = it.get("status") or "等待"
                return str(name or ""), str(size or ""), str(time_str or ""), str(status or "等待")
            try:
                seq = list(it)
            except Exception:
                return "", "", "", "等待"
            if len(seq) >= 4:
                name, size, time_str, status = seq[:4]
            elif len(seq) == 3:
                name, size, time_str = seq
                status = "等待"
            else:
                name = seq[0] if len(seq) > 0 else ""
                size = seq[1] if len(seq) > 1 else ""
                time_str = seq[2] if len(seq) > 2 else ""
                status = "等待"
            return str(name or ""), str(size or ""), str(time_str or ""), str(status or "等待")

        def match_item(it):
            name, size, time_str, status = normalize(it)
            dt = QtCore.QDateTime.fromString(time_str, "yyyy-MM-dd HH:mm:ss").toSecsSinceEpoch()
            if dt_from and dt_to and dt:
                if dt < dt_from or dt > dt_to:
                    return False
            if status_sel != "全部" and (status or "等待") != status_sel:
                return False
            text_blob = f"{name} {size} {time_str} {status}".lower()
            ok = True
            if path_kw: ok = ok and (path_kw in text_blob)
            if app_kw: ok = ok and (app_kw in text_blob)
            if name_kw: ok = ok and (name_kw in name.lower())
            return ok

        self.filtered_files = [normalize(f) for f in self.all_files if match_item(f)]
        if reset_page: self.page = 1
        self.refresh_page()

    def refresh_page(self):
        total = len(self.filtered_files)
        page_size = self.page_size
        max_page = max(1, (total + page_size - 1) // page_size)
        self.page = max(1, min(self.page, max_page))
        start = (self.page - 1) * page_size
        end = min(start + page_size, total)
        subset = self.filtered_files[start:end]

        self.table.setRowCount(len(subset))
        for i, (name, size, time, status) in enumerate(subset):
            # 文件列，带图标更直观
            name_item = QtWidgets.QTableWidgetItem(f"📄 {name}")
            name_item.setData(USER_ROLE, name)
            self.table.setItem(i, 0, name_item)

            size_item = QtWidgets.QTableWidgetItem(size or "")
            size_item.setTextAlignment(ALIGN_CENTER)
            self.table.setItem(i, 1, size_item)

            time_item = QtWidgets.QTableWidgetItem(time or "")
            time_item.setTextAlignment(ALIGN_CENTER)
            self.table.setItem(i, 2, time_item)

            # 进度+取消
            progress_widget = QtWidgets.QWidget()
            p_layout = QtWidgets.QHBoxLayout(progress_widget)
            p_layout.setContentsMargins(8, 6, 8, 6)
            p_layout.setSpacing(8)

            bar = QtWidgets.QProgressBar()
            bar.setRange(0, 100)
            prog_map = {"等待": 0, "下载中": 45, "已完成": 100, "失败": 0}
            val = prog_map.get(status or "等待", 0)
            bar.setValue(val)
            bar.setFormat(f"{val}%")
            p_layout.addWidget(bar)

            cancel_btn = QtWidgets.QPushButton("✕")
            cancel_btn.setFixedSize(28, 28)
            cancel_btn.setStyleSheet(
                "QPushButton { background-color:#EF4444;color:white;border:none;border-radius:14px;font-weight:bold;}"
                "QPushButton:hover { background-color:#DC2626; }"
            )
            p_layout.addWidget(cancel_btn)
            p_layout.addStretch()
            self.table.setCellWidget(i, 3, progress_widget)

            status_text = status or "等待"
            status_chip = QtWidgets.QLabel(status_text)
            status_chip.setAlignment(ALIGN_CENTER)
            status_chip.setMinimumHeight(24)
            status_chip.setStyleSheet(self._chip_style(status_text))
            self.table.setCellWidget(i, 4, status_chip)

            speed_item = QtWidgets.QTableWidgetItem("---" if (status or "等待") != "下载中" else "1.2 MB/s")
            speed_item.setTextAlignment(ALIGN_CENTER)
            self.table.setItem(i, 5, speed_item)

            btn_widget = QtWidgets.QWidget()
            btn_layout = QtWidgets.QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(ACTION_COL_HMARGIN, 6, ACTION_COL_HMARGIN, 6)
            btn_layout.setSpacing(ACTION_BTN_SPACING)
            download_btn = TableButton("下载", "#10B981", "⬇️")
            view_btn = TableButton("查看", "#2563EB", "👁️")
            for b in (download_btn, view_btn):
                b.setFixedSize(ACTION_BTN_W, ACTION_BTN_H)
                b.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
            btn_layout.addStretch(1)
            btn_layout.addWidget(download_btn)
            btn_layout.addWidget(view_btn)
            btn_layout.addStretch(1)
            self.table.setCellWidget(i, 6, btn_widget)

        self.page_label.setText(f"第 {self.page}/{max_page} 页，共 {total} 条")
        self.prev_btn.setEnabled(self.page > 1)
        self.next_btn.setEnabled(self.page < max_page)

    def _chip_style(self, status: str) -> str:
        color = {
            "等待": ("#F59E0B", "#FEF3C7"),
            "下载中": ("#3B82F6", "#DBEAFE"),
            "已完成": ("#10B981", "#D1FAE5"),
            "失败": ("#EF4444", "#FEE2E2"),
        }.get(status, ("#6B7280", "#F3F4F6"))
        return f"QLabel {{ color:{color[0]}; background:{color[1]}; border-radius:12px; padding:4px 10px; }}"

    # 事件
    def on_search(self):
        self.apply_filters(reset_page=True)

    def on_refresh(self):
        self.apply_filters(reset_page=False)

    def on_prev_page(self):
        if self.page > 1:
            self.page -= 1
            self.refresh_page()

    def on_next_page(self):
        self.page += 1
        self.refresh_page()

    def on_change_page_size(self, text):
        try:
            self.page_size = int(text)
        except ValueError:
            self.page_size = 10
        self.apply_filters(reset_page=True)
