"""
@FileName：bus_data_download_view.py
@Description：
@Author：QinHao
@Time：2025/12/9 14:56
@Department：PTV_AT
"""
from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtCore import Qt as _Qt, pyqtSignal

from app.common.ui.widgets import ModernButton
from app.common.ui.modern_widgets import MessageToast
from app.common.ui.checkable_header import CheckBoxHeaderView, CheckableHeaderController
from app.modules.bus_data_management.view.CalendarDateEdit import CalendarDateEdit
from app.presentation.views.base_view import BaseView

ACTION_BTN_W = 84
ACTION_BTN_H = 30
ACTION_BTN_SPACING = 10
ACTION_COL_HMARGIN = 10
ACTION_COL_WIDTH = ACTION_BTN_W * 2 + ACTION_BTN_SPACING + ACTION_COL_HMARGIN * 2

STATUS_OPTIONS = ["全部", "未下载", "下载中", "已下载", "下载失败", "已取消"]

# 总线数据下载界面
class BusDataDownloadView(BaseView):
    # 对外信号
    sig_search_clicked = pyqtSignal(dict)     # 携带筛选条件字典{tab_kw, type_kw, name_kw, status, date_from, date_to}
    sig_refresh_clicked = pyqtSignal()        # 刷新
    sig_page_changed = pyqtSignal(int)   # 翻页
    sig_page_size_changed = pyqtSignal(int)  # 每页条数改变
    sig_download_clicked = pyqtSignal(str)  # 携带 Path单条下载
    sig_cancel_clicked = pyqtSignal(str)  # 取消单条下载
    sig_batch_download_clicked = pyqtSignal()      # 批量下载
    sig_batch_cancel_clicked = pyqtSignal()        # 批量取消
    sig_sort_requested = pyqtSignal(int)   # 表头点击排序信号
    sig_view_shown = pyqtSignal()          # 界面显示信号

    def __init__(self, parent=None):
        super().__init__(parent)
        self._check_header = None  # type: CheckBoxHeaderView
        self._header_ctrl = None  # type: CheckableHeaderController

    def setup_ui(self):

        root = QtWidgets.QVBoxLayout(self)
        root.setSpacing(14)
        root.setContentsMargins(14, 14, 14, 14)

        # 过滤查询区域
        filter_card = QtWidgets.QGroupBox("过滤查询")
        fc = QtWidgets.QVBoxLayout(filter_card)
        fc.setContentsMargins(12, 8, 12, 12)
        toolbar = QtWidgets.QGridLayout()
        toolbar.setHorizontalSpacing(10)
        toolbar.setVerticalSpacing(8)
        toolbar.setColumnStretch(1, 1)
        toolbar.setColumnStretch(3, 1)
        toolbar.setColumnStretch(5, 1)

        self.tab_input = QtWidgets.QComboBox()
        self.tab_input.setEditable(False)
        # 默认不再提供“全部/根目录”项；实际选项由 set_tab_options() 填充
        self.tab_input.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

        self.type_combo = QtWidgets.QComboBox()
        self.type_combo.addItem("全部")
        self.type_combo.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

        self.filename_input = QtWidgets.QLineEdit()
        self.filename_input.setPlaceholderText("输入 filename")
        self.date_from = CalendarDateEdit()
        self.date_from.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.date_to = CalendarDateEdit()
        self.date_to.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

        self.status_combo = QtWidgets.QComboBox()
        self.status_combo.addItems(STATUS_OPTIONS)

        self.search_btn = ModernButton("搜索", "#2563EB", "🔍")
        self.refresh_btn = ModernButton("刷新", "#10B981", "🔄")

        self.batch_download_btn = ModernButton("批量下载", "#3B82F6", "⬇️")
        self.batch_cancel_btn = ModernButton("批量取消", "#EF4444", "✕")

        toolbar.addWidget(QtWidgets.QLabel("TAB"), 0, 0)
        toolbar.addWidget(self.tab_input, 0, 1)
        toolbar.addWidget(QtWidgets.QLabel("Type"), 0, 2)
        toolbar.addWidget(self.type_combo, 0, 3)
        toolbar.addWidget(QtWidgets.QLabel("Filename"), 0, 4)
        toolbar.addWidget(self.filename_input, 0, 5)

        toolbar.addWidget(QtWidgets.QLabel("创建时间"), 1, 0)
        toolbar.addWidget(self.date_from, 1, 1)
        toolbar.addWidget(QtWidgets.QLabel("至"), 1, 2)
        toolbar.addWidget(self.date_to, 1, 3)
        toolbar.addWidget(QtWidgets.QLabel("下载状态"), 1, 4)
        toolbar.addWidget(self.status_combo, 1, 5)

        btns = QtWidgets.QHBoxLayout()
        btns.addStretch(1)
        btns.addWidget(self.batch_download_btn)
        btns.addWidget(self.batch_cancel_btn)
        btns.addSpacing(20)
        btns.addWidget(self.search_btn)
        btns.addWidget(self.refresh_btn)

        fc.addLayout(toolbar)
        fc.addLayout(btns)
        root.addWidget(filter_card)

        # 数据表
        self.table = QtWidgets.QTableView()
        self.table.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet("""
            QTableView {
                outline: none;
                selection-background-color: #E0E7FF;
                selection-color: #1F2937;
            }
            QTableView::item:selected {
                background-color: #E0E7FF;
                color: #1F2937;
                font-weight: bold;
            }
            QTableView::item:hover {
                background-color: #F3F4F6;
            }
        """)
        pal = self.table.palette()
        pal.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor("#F9FAFB"))
        self.table.setPalette(pal)
        self.table.setShowGrid(False)

        vheader = self.table.verticalHeader()
        vheader.setDefaultSectionSize(55)
        vheader.setMinimumSectionSize(40)
        vheader.setSectionResizeMode(QtWidgets.QHeaderView.Fixed)

        self._check_header = CheckBoxHeaderView(_Qt.Horizontal, self.table)
        self.table.setHorizontalHeader(self._check_header)
        self._header_ctrl = CheckableHeaderController(self.table, self._check_header)

        hheader = self.table.horizontalHeader()
        hheader.setStretchLastSection(True)
        hheader.setHighlightSections(False)
        hheader.setDefaultSectionSize(110)
        hheader.setMinimumSectionSize(70)
        hheader.setSectionsClickable(True)
        hheader.setSortIndicatorShown(True)
        hheader.sectionClicked.connect(self._on_header_clicked)

        self.table.setItemDelegateForColumn(0, CenteredCheckBoxDelegate(self.table))
        self.table.setItemDelegateForColumn(8, ProgressDelegate(self.table))
        self.table.setItemDelegateForColumn(9, StatusDelegate(self.table))
        self.action_delegate = ActionDelegate(self.table)
        self.action_delegate.sig_download.connect(self.sig_download_clicked)
        self.action_delegate.sig_cancel.connect(self.sig_cancel_clicked)
        self.table.setItemDelegateForColumn(10, self.action_delegate)
        self.table.setMouseTracking(True)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)

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
        self.page_size_combo.addItems(["500", "1000", "2000", "3000"])
        self.page_size_combo.setCurrentText("1000")

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
        self.batch_download_btn.clicked.connect(self.sig_batch_download_clicked)
        self.batch_cancel_btn.clicked.connect(self.sig_batch_cancel_clicked)
        self.prev_btn.clicked.connect(self._on_prev_page_clicked)
        self.next_btn.clicked.connect(self._on_next_page_clicked)
        self.page_size_combo.currentTextChanged.connect(self._on_page_size_changed)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.toast = MessageToast(self)
        self.date_from.dateTimeChanged.connect(self._on_time_changed)
        self.date_to.dateTimeChanged.connect(self._on_time_changed)

    def show_toast(self, text: str, type_: int = 0):
        """显示 Toast 提示 (0:success, 1:error, 2:info)"""
        self.toast.show_toast(text, type_)

    def set_tab_options(self, labels, values):
        '''设置 Tab 选项'''
        self.tab_input.blockSignals(True)
        # 记录当前选中的值，以便刷新后恢复（如果还在的话）
        current_data = self.tab_input.currentData()

        self.tab_input.clear()
        for label, value in zip(labels, values):
            self.tab_input.addItem(label, value)

        # 尝试恢复选中项
        if current_data:
            idx = self.tab_input.findData(current_data)
            if idx >= 0:
                self.tab_input.setCurrentIndex(idx)

        self.tab_input.blockSignals(False)

    def set_type_options(self, types: list):
        current = self.type_combo.currentText()
        self.type_combo.blockSignals(True)
        self.type_combo.clear()
        self.type_combo.addItem("全部")
        self.type_combo.addItems(sorted(types))
        idx = self.type_combo.findText(current)
        self.type_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.type_combo.blockSignals(False)

    def update_pager(self, page: int, page_count: int, total: int):
        self.page_label.setText(f"第 {page}/{page_count} 页，共 {total} 条")
        self.prev_btn.setEnabled(page > 1)
        self.next_btn.setEnabled(page < page_count)

    def get_filter_criteria(self) -> dict:
        tab_kw = self.tab_input.currentData()
        if tab_kw is None:
            tab_kw = ""

        type_kw = self.type_combo.currentText()
        if type_kw == "全部":
            type_kw = ""

        name_kw = self.filename_input.text().strip()
        status = self.status_combo.currentText()
        d_from = self.date_from.dateTime()
        d_to = self.date_to.dateTime()

        from_ok = d_from and (d_from > self.date_from.null_date)
        to_ok = d_to and (d_to > self.date_to.null_date)

        return {
            "tab_kw": tab_kw,
            "type_kw": type_kw,
            "name_kw": name_kw,
            "status": status,
            "date_from": d_from if from_ok else None,
            "date_to": d_to if to_ok else None,
        }

    def set_table_model(self, model):
        if self._header_ctrl is None and self._check_header is not None:
            self._header_ctrl = CheckableHeaderController(self.table, self._check_header)
        if self._header_ctrl is not None:
            self._header_ctrl.bind_model(model)
        else:
            self.table.setModel(model)
        self.table.setMouseTracking(True)
        fixed_headers = ["", "序号", "FileName", "Path", "Type", "Size(KB)", "CreateTime", "ModifiedTime", "下载进度", "状态", "操作"]
        if hasattr(model, "set_headers"):
            try:
                model.set_headers(fixed_headers)
            except Exception:
                pass
        hheader = self.table.horizontalHeader()
        hheader.setSectionResizeMode(0, QtWidgets.QHeaderView.Fixed)
        self.table.setColumnWidth(0, 80)
        hheader.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        hheader.setSectionResizeMode(2, QtWidgets.QHeaderView.Interactive)
        self.table.setColumnWidth(2, 180)
        hheader.setSectionResizeMode(3, QtWidgets.QHeaderView.Interactive)
        self.table.setColumnWidth(3, 360)
        hheader.setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeToContents)
        hheader.setSectionResizeMode(5, QtWidgets.QHeaderView.ResizeToContents)
        hheader.setSectionResizeMode(6, QtWidgets.QHeaderView.ResizeToContents)
        hheader.setSectionResizeMode(7, QtWidgets.QHeaderView.ResizeToContents)
        hheader.setSectionResizeMode(8, QtWidgets.QHeaderView.Stretch)
        self.table.setColumnWidth(8, 200)
        hheader.setSectionResizeMode(9, QtWidgets.QHeaderView.Interactive)
        self.table.setColumnWidth(9, 120)
        hheader.setSectionResizeMode(10, QtWidgets.QHeaderView.Fixed)
        self.table.setColumnWidth(10, ACTION_COL_WIDTH)
        if self._header_ctrl is not None:
            try:
                self._header_ctrl._sync_from_model()
            except Exception:
                pass

    # 优化: 校验时间范围，只处理一次提示
    def _is_time_range_valid(self) -> bool:
        d_from = self.date_from.dateTime()
        d_to = self.date_to.dateTime()
        from_ok = d_from and (d_from > self.date_from.null_date)
        to_ok = d_to and (d_to > self.date_to.null_date)
        if from_ok and to_ok and d_from > d_to:
            self.show_toast("起始时间不能晚于结束时间", 1)
            return False
        return True

    def _on_search_clicked(self):
        if not self._is_time_range_valid():
            return
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

    def _on_header_clicked(self, logical_index: int):
        self.sig_sort_requested.emit(int(logical_index))

    def _on_time_changed(self):
        self._is_time_range_valid()

    def showEvent(self, event):
        super().showEvent(event)
        self.sig_view_shown.emit()

# ---- Delegates ----
class CenteredCheckBoxDelegate(QtWidgets.QStyledItemDelegate):
    def paint(self, painter, option, index):
        if not index.isValid():
            return
        painter.save()
        opt = QtWidgets.QStyleOptionViewItem(option)
        opt.state &= ~QtWidgets.QStyle.State_HasFocus
        style = opt.widget.style() if opt.widget else QtWidgets.QApplication.style()
        check_state = index.data(QtCore.Qt.CheckStateRole)
        cb_opt = QtWidgets.QStyleOptionButton()
        cb_opt.state |= QtWidgets.QStyle.State_Enabled
        cb_opt.state |= QtWidgets.QStyle.State_On if check_state == QtCore.Qt.Checked else QtWidgets.QStyle.State_Off
        indicator_w = style.pixelMetric(QtWidgets.QStyle.PM_IndicatorWidth, None, opt.widget)
        indicator_h = style.pixelMetric(QtWidgets.QStyle.PM_IndicatorHeight, None, opt.widget)
        r = opt.rect
        x = r.x() + (r.width() - indicator_w) // 2
        y = r.y() + (r.height() - indicator_h) // 2
        cb_opt.rect = QtCore.QRect(x, y, indicator_w, indicator_h)
        style.drawPrimitive(QtWidgets.QStyle.PE_IndicatorCheckBox, cb_opt, painter, opt.widget)
        painter.restore()

    def editorEvent(self, event, model, option, index):
        if not index.isValid():
            return False
        if event.type() == QtCore.QEvent.MouseButtonRelease and event.button() == QtCore.Qt.LeftButton:
            state = index.data(QtCore.Qt.CheckStateRole)
            new_state = QtCore.Qt.Unchecked if state == QtCore.Qt.Checked else QtCore.Qt.Checked
            return model.setData(index, new_state, QtCore.Qt.CheckStateRole)
        return False

class ProgressDelegate(QtWidgets.QStyledItemDelegate):
    def paint(self, painter, option, index):
        if not index.isValid():
            return
        if option.state & QtWidgets.QStyle.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())
        text = (index.data(QtCore.Qt.DisplayRole) or "0%").strip()
        pct = 0
        try:
            pct_part = text.split("%", 1)[0]
            pct = int("".join(ch for ch in pct_part if ch.isdigit()) or "0")
        except Exception:
            pct = 0
        pct = max(0, min(100, pct))
        painter.save()
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        rect = option.rect.adjusted(8, 12, -8, -12)
        if rect.height() < 12:
            rect = option.rect.adjusted(6, 6, -6, -6)
        radius = max(6, rect.height() // 2)
        track_color = QtGui.QColor("#EEF2FF") if not (option.state & QtWidgets.QStyle.State_Selected) else QtGui.QColor("#DDE7FF")
        track_pen = QtGui.QPen(QtGui.QColor("#CBD5E1"))
        track_pen.setWidth(1)
        painter.setPen(track_pen)
        painter.setBrush(track_color)
        painter.drawRoundedRect(rect, radius, radius)
        if pct > 0:
            fill_w = int(rect.width() * pct / 100)
            fill_rect = QtCore.QRect(rect.x(), rect.y(), fill_w, rect.height())
            fill_path = QtGui.QPainterPath()
            fill_path.addRoundedRect(QtCore.QRectF(fill_rect), radius, radius)
            grad = QtGui.QLinearGradient(fill_rect.topLeft(), fill_rect.topRight())
            grad.setColorAt(0.0, QtGui.QColor("#3B82F6"))
            grad.setColorAt(1.0, QtGui.QColor("#06B6D4"))
            painter.setPen(QtCore.Qt.NoPen)
            painter.fillPath(fill_path, grad)
        painter.setPen(QtGui.QColor("#0F172A") if not (option.state & QtWidgets.QStyle.State_Selected) else option.palette.highlightedText().color())
        font = option.font
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(option.rect, QtCore.Qt.AlignCenter, text)
        painter.restore()

class StatusDelegate(QtWidgets.QStyledItemDelegate):
    def paint(self, painter, option, index):
        if not index.isValid():
            return
        status = index.data(QtCore.Qt.DisplayRole)
        color_map = {
            "未下载": ("#6B7280", "#F3F4F6"),
            "下载中": ("#3B82F6", "#DBEAFE"),
            "已下载": ("#10B981", "#D1FAE5"),
            "下载失败": ("#EF4444", "#FEE2E2"),
            "已取消": ("#F97316", "#FFEDD5"),
        }
        text_color, bg_color = color_map.get(status, ("#6B7280", "#F3F4F6"))
        painter.save()
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        rect = option.rect
        pill_rect = QtCore.QRect(0, 0, 80, 24)
        pill_rect.moveCenter(rect.center())
        path = QtGui.QPainterPath()
        path.addRoundedRect(QtCore.QRectF(pill_rect), 12, 12)
        painter.fillPath(path, QtGui.QColor(bg_color))
        painter.setPen(QtGui.QColor(text_color))
        painter.drawText(pill_rect, QtCore.Qt.AlignCenter, status)
        painter.restore()

class ActionDelegate(QtWidgets.QStyledItemDelegate):
    sig_download = QtCore.pyqtSignal(str)
    sig_cancel = QtCore.pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

    def paint(self, painter, option, index):
        if not index.isValid():
            return
        status_idx = index.sibling(index.row(), 9)
        status = status_idx.data(QtCore.Qt.DisplayRole)
        is_downloading = (status == "下载中")
        spacing = 10
        btn_w = 84
        btn_h = 30
        total_w = 2 * btn_w + spacing
        start_x = option.rect.left() + (option.rect.width() - total_w) // 2
        y = option.rect.top() + (option.rect.height() - btn_h) // 2
        rect_down = QtCore.QRect(start_x, y, btn_w, btn_h)
        rect_cancel = QtCore.QRect(start_x + btn_w + spacing, y, btn_w, btn_h)
        self._paint_modern_btn(painter, rect_down, "#10B981", "⬇️ 下载", True)
        self._paint_modern_btn(painter, rect_cancel, "#EF4444", "✕ 取消", is_downloading)

    def _paint_modern_btn(self, painter, rect, base_color, text, enabled):
        painter.save()
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        bg = QtGui.QColor(base_color) if enabled else QtGui.QColor("#E5E7EB")
        path = QtGui.QPainterPath()
        path.addRoundedRect(QtCore.QRectF(rect), 4, 4)
        painter.fillPath(path, bg)
        painter.setPen(QtGui.QColor("white") if enabled else QtGui.QColor("#9CA3AF"))
        painter.drawText(rect, QtCore.Qt.AlignCenter, text)
        painter.restore()

    def editorEvent(self, event, model, option, index):
        if event.type() == QtCore.QEvent.MouseButtonRelease:
            spacing = 10
            btn_w = 84
            btn_h = 30
            total_w = 2 * btn_w + spacing
            start_x = option.rect.left() + (option.rect.width() - total_w) // 2
            y = option.rect.top() + (option.rect.height() - btn_h) // 2
            rect_down = QtCore.QRect(start_x, y, btn_w, btn_h)
            rect_cancel = QtCore.QRect(start_x + btn_w + spacing, y, btn_w, btn_h)
            pos = event.pos()
            if rect_down.contains(pos):
                path = index.sibling(index.row(), 3).data(QtCore.Qt.DisplayRole)
                self.sig_download.emit(path)
                return True
            elif rect_cancel.contains(pos):
                status_idx = index.sibling(index.row(), 9)
                status = status_idx.data(QtCore.Qt.DisplayRole)
                if status == "下载中":
                    path = index.sibling(index.row(), 3).data(QtCore.Qt.DisplayRole)
                    self.sig_cancel.emit(path)
                return True
        return False

