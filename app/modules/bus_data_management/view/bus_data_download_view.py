"""
@FileName：bus_data_download_view.py
@Description：
@Author：QinHao
@Time：2025/12/9 14:56
@Department：PTV_AT
"""
from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtCore import Qt as _Qt, pyqtSignal

from app.common.ui.widgets import ModernButton, TableButton
from app.presentation.views.base_view import BaseView

ACTION_BTN_W = 84
ACTION_BTN_H = 30
ACTION_BTN_SPACING = 10
ACTION_COL_HMARGIN = 10
ACTION_COL_WIDTH = ACTION_BTN_W * 2 + ACTION_BTN_SPACING + ACTION_COL_HMARGIN * 2

STATUS_OPTIONS = ["全部", "等待", "下载中", "已完成", "失败"]


class BusDataDownloadView(BaseView):
    """总线数据下载界面，参照日志下载界面实现。"""

    # 对外信号
    sig_search_clicked = pyqtSignal(dict)          # {tab_kw, type_kw, name_kw, status, date_from, date_to}
    sig_refresh_clicked = pyqtSignal()
    sig_page_changed = pyqtSignal(int)
    sig_page_size_changed = pyqtSignal(int)
    sig_download_clicked = pyqtSignal(int)
    sig_cancel_clicked = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)

    def setup_ui(self):

        root = QtWidgets.QVBoxLayout(self)
        root.setSpacing(14)
        root.setContentsMargins(14, 14, 14, 14)

        # 过滤查询区域：Path、APPID 改为 TAB、Type
        filter_card = QtWidgets.QGroupBox("过滤查询")
        fc = QtWidgets.QVBoxLayout(filter_card)
        fc.setContentsMargins(12, 8, 12, 12)
        toolbar = QtWidgets.QGridLayout()
        toolbar.setHorizontalSpacing(10)
        toolbar.setVerticalSpacing(8)

        self.tab_input = QtWidgets.QLineEdit()
        self.tab_input.setPlaceholderText("输入 TAB")
        self.type_input = QtWidgets.QLineEdit()
        self.type_input.setPlaceholderText("输入 type")
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

        toolbar.addWidget(QtWidgets.QLabel("TAB"), 0, 0)
        toolbar.addWidget(self.tab_input, 0, 1)
        toolbar.addWidget(QtWidgets.QLabel("Type"), 0, 2)
        toolbar.addWidget(self.type_input, 0, 3)
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

        # 表格：沿用日志下载的 10 列结构
        self.table = QtWidgets.QTableWidget(0, 10)
        self.table.setHorizontalHeaderLabels([
            "序号",
            "FileName",
            "Path",          # 可以后续按需改为 BusData 的路径字段
            "APPID",         # 可以后续按需改为 ECU/Channel 等
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

        vheader = self.table.verticalHeader()
        vheader.setDefaultSectionSize(55)
        vheader.setMinimumSectionSize(40)
        vheader.setSectionResizeMode(QtWidgets.QHeaderView.Fixed)

        hheader = self.table.horizontalHeader()
        hheader.setStretchLastSection(True)
        hheader.setHighlightSections(False)
        hheader.setDefaultSectionSize(100)
        hheader.setMinimumSectionSize(60)
        hheader.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        hheader.setSectionResizeMode(1, QtWidgets.QHeaderView.Interactive)
        self.table.setColumnWidth(1, 180)
        hheader.setSectionResizeMode(2, QtWidgets.QHeaderView.Interactive)
        self.table.setColumnWidth(2, 360)
        hheader.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeToContents)
        hheader.setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeToContents)
        hheader.setSectionResizeMode(5, QtWidgets.QHeaderView.ResizeToContents)
        hheader.setSectionResizeMode(6, QtWidgets.QHeaderView.ResizeToContents)
        hheader.setSectionResizeMode(7, QtWidgets.QHeaderView.Stretch)
        self.table.setColumnWidth(7, 260)
        hheader.setSectionResizeMode(8, QtWidgets.QHeaderView.Interactive)
        self.table.setColumnWidth(8, 120)
        hheader.setSectionResizeMode(9, QtWidgets.QHeaderView.Fixed)
        self.table.setColumnWidth(9, ACTION_COL_WIDTH)

        root.addWidget(self.table)

        # 分页
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
        self.page_size_combo.setCurrentText("10")

        pc.addWidget(self.prev_btn)
        pc.addWidget(self.next_btn)
        pc.addSpacing(8)
        pc.addWidget(QtWidgets.QLabel("每页条数"))
        pc.addWidget(self.page_size_combo)
        pc.addStretch(1)
        pc.addWidget(self.page_label)

        root.addWidget(pager_card)

        # 信号转发
        self.search_btn.clicked.connect(self._on_search_clicked)
        self.refresh_btn.clicked.connect(self._on_refresh_clicked)
        self.prev_btn.clicked.connect(self._on_prev_page_clicked)
        self.next_btn.clicked.connect(self._on_next_page_clicked)
        self.page_size_combo.currentTextChanged.connect(self._on_page_size_changed)

    # --- 提供给 Controller 的接口 ---
    def get_filter_criteria(self) -> dict:
        tab_kw = self.tab_input.text().strip()
        type_kw = self.type_input.text().strip()
        name_kw = self.filename_input.text().strip()
        status = self.status_combo.currentText()
        date_from = self.date_from.dateTime()
        date_to = self.date_to.dateTime()
        return {
            "tab_kw": tab_kw,
            "type_kw": type_kw,
            "name_kw": name_kw,
            "status": status,
            "date_from": date_from,
            "date_to": date_to,
        }

    def render_rows(self, rows, page: int, page_count: int, total: int, page_size: int):
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

            idx_item = QtWidgets.QTableWidgetItem(str((page - 1) * page_size + row_idx + 1))
            idx_item.setTextAlignment(_Qt.AlignCenter)
            self.table.setItem(row_idx, 0, idx_item)

            name_item = QtWidgets.QTableWidgetItem(filename)
            self.table.setItem(row_idx, 1, name_item)

            path_item = QtWidgets.QTableWidgetItem(path)
            self.table.setItem(row_idx, 2, path_item)

            app_item = QtWidgets.QTableWidgetItem(appid)
            app_item.setTextAlignment(_Qt.AlignCenter)
            self.table.setItem(row_idx, 3, app_item)

            size_item = QtWidgets.QTableWidgetItem(size_kb)
            size_item.setTextAlignment(_Qt.AlignCenter)
            self.table.setItem(row_idx, 4, size_item)

            ctime_item = QtWidgets.QTableWidgetItem(create_time)
            ctime_item.setTextAlignment(_Qt.AlignCenter)
            self.table.setItem(row_idx, 5, ctime_item)

            mtime_item = QtWidgets.QTableWidgetItem(modified_time)
            mtime_item.setTextAlignment(_Qt.AlignCenter)
            self.table.setItem(row_idx, 6, mtime_item)

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

            status_chip = QtWidgets.QLabel(status)
            status_chip.setAlignment(_Qt.AlignCenter)
            status_chip.setMinimumHeight(24)
            status_chip.setStyleSheet(self._chip_style(status))
            self.table.setCellWidget(row_idx, 8, status_chip)

            btn_widget = QtWidgets.QWidget()
            btn_layout = QtWidgets.QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(ACTION_COL_HMARGIN, 6, ACTION_COL_HMARGIN, 6)
            btn_layout.setSpacing(ACTION_BTN_SPACING)

            download_btn = TableButton("下载", "#10B981", "⬇️")
            cancel_btn = TableButton("取消", "#EF4444", "✕")
            for b in (download_btn, cancel_btn):
                b.setFixedSize(ACTION_BTN_W, ACTION_BTN_H)
                b.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)

            download_btn.clicked.connect(lambda _=False, r=row_idx: self.sig_download_clicked.emit(int(r)))
            cancel_btn.clicked.connect(lambda _=False, r=row_idx: self.sig_cancel_clicked.emit(int(r)))

            btn_layout.addStretch(1)
            btn_layout.addWidget(download_btn)
            btn_layout.addWidget(cancel_btn)
            btn_layout.addStretch(1)
            self.table.setCellWidget(row_idx, 9, btn_widget)

        self.update_pager(page, page_count, total)

    def update_pager(self, page: int, page_count: int, total: int):
        self.page_label.setText(f"第 {page}/{page_count} 页，共 {total} 条")
        self.prev_btn.setEnabled(page > 1)
        self.next_btn.setEnabled(page < page_count)

    # --- 内部槽：只负责发射信号 ---
    def _on_search_clicked(self):
        self.sig_search_clicked.emit(self.get_filter_criteria())

    def _on_refresh_clicked(self):
        self.sig_refresh_clicked.emit()

    def _on_prev_page_clicked(self):
        self.sig_page_changed.emit(-1)

    def _on_next_page_clicked(self):
        self.sig_page_changed.emit(+1)

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
