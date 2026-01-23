# python
from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtCore import Qt as _Qt, pyqtSignal

from app.common.ui.widgets import ModernButton
from app.common.ui.modern_widgets import MessageToast
from app.presentation.views.base_view import BaseView
from app.common.ui.checkable_header import CheckBoxHeaderView, CheckableHeaderController
from app.modules.bus_data_management.view.CalendarDateEdit import CalendarDateEdit  # 新增引用

ALIGN_CENTER = int(getattr(_Qt, "AlignCenter", 132))
USER_ROLE = int(getattr(_Qt, "UserRole", 256))

ACTION_BTN_W = 84
ACTION_BTN_H = 30
ACTION_BTN_SPACING = 10
ACTION_COL_HMARGIN = 10
ACTION_COL_WIDTH = ACTION_BTN_W * 2 + ACTION_BTN_SPACING + ACTION_COL_HMARGIN * 2

STATUS_OPTIONS = ["全部", "未下载", "下载中", "已下载", "下载失败", "已取消"]

# 日志文件下载
class LogDownloadView(BaseView):
    # ---- 对外信号：交互事件交给 Controller 处理 ----
    sig_search_clicked = pyqtSignal(dict)          # {path_kw, app_kw, name_kw, status, date_from, date_to}
    sig_refresh_clicked = pyqtSignal()
    sig_page_changed = pyqtSignal(int)             # 目标页码
    sig_page_size_changed = pyqtSignal(int)        # 每页条数
    sig_download_clicked = pyqtSignal(str)         # path
    sig_cancel_clicked = pyqtSignal(str)           # path
    sig_batch_download_clicked = pyqtSignal()      # 批量下载
    sig_batch_cancel_clicked = pyqtSignal()        # 批量取消

    sig_sort_requested = pyqtSignal(int)  # logical_index

    def __init__(self, parent=None):
        super().__init__(parent)
        self._locale = QtCore.QLocale(QtCore.QLocale.English)
        self._check_header = None
        self._header_ctrl = None

    def setup_ui(self):
        if not hasattr(self, "all_files"): self.all_files = []
        if not hasattr(self, "filtered_files"): self.filtered_files = []
        if not hasattr(self, "page"): self.page = 1
        if not hasattr(self, "page_size"): self.page_size = 100


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

        # a) Path 输入框
        self.path_input = QtWidgets.QLineEdit()
        self.path_input.setPlaceholderText("输入 path")
        self.path_input.setText("/log/CCUA/core")

        # b) APPID 下拉框 (Changed from QLineEdit)
        self.appid_combo = QtWidgets.QComboBox()
        self.appid_combo.addItem("全部")
        self.appid_combo.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

        # d) FileName输入框
        self.filename_input = QtWidgets.QLineEdit()
        self.filename_input.setPlaceholderText("输入 filename")

        # 修改：替换为自定义的 CalendarDateEdit
        self.date_from = CalendarDateEdit()
        self.date_from.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

        self.date_to = CalendarDateEdit()
        self.date_to.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

        self.status_combo = QtWidgets.QComboBox()
        self.status_combo.addItems(STATUS_OPTIONS)

        self.search_btn = ModernButton("搜索", "#2563EB", "🔍")
        self.refresh_btn = ModernButton("刷新", "#10B981", "🔄")

        # 批量操作按钮
        self.batch_download_btn = ModernButton("批量下载", "#3B82F6", "⬇️")
        self.batch_cancel_btn = ModernButton("批量取消", "#EF4444", "✕")

        # 直接保持时间控件可用
        self.date_from.setEnabled(True)
        self.date_to.setEnabled(True)

        # 两行排布，更紧凑
        toolbar.addWidget(QtWidgets.QLabel("Path"), 0, 0)
        toolbar.addWidget(self.path_input, 0, 1)
        toolbar.addWidget(QtWidgets.QLabel("AppID"), 0, 2)
        toolbar.addWidget(self.appid_combo, 0, 3)
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
        btns.addSpacing(20)  # 在批量按钮和常用按钮间加点间隔
        btns.addWidget(self.search_btn)
        btns.addWidget(self.refresh_btn)

        fc.addLayout(toolbar)
        fc.addLayout(btns)
        root.addWidget(filter_card)

        # 表格
        # 11 列：选择, 序号, FileName, Path, APPID, Size(KB), CreateTime, ModifiedTime, 下载进度, 状态, 操作
        self.table = QtWidgets.QTableView() # Changed from QTableWidget
        self.table.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        pal = self.table.palette()
        pal.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor("#F9FAFB"))
        self.table.setPalette(pal)
        self.table.setShowGrid(False) # Optional style

        # 调整行高和列宽策略
        vheader = self.table.verticalHeader()
        # 行高在这里调，高一些比如 46 像素
        vheader.setDefaultSectionSize(55)
        vheader.setMinimumSectionSize(40)
        vheader.setSectionResizeMode(QtWidgets.QHeaderView.Fixed)

        # 使用支持“全选”的表头（第0列）
        self._check_header = CheckBoxHeaderView(_Qt.Horizontal, self.table)
        self.table.setHorizontalHeader(self._check_header)
        self._header_ctrl = CheckableHeaderController(self.table, self._check_header)

        hheader = self.table.horizontalHeader()
        hheader.setStretchLastSection(True)
        hheader.setHighlightSections(False)
        hheader.setDefaultSectionSize(110)
        hheader.setMinimumSectionSize(70)

        # 启用表头排序点击
        hheader.setSectionsClickable(True)
        hheader.setSortIndicatorShown(True)
        hheader.sectionClicked.connect(self._on_header_clicked)

        # 设置 Delegates (代理渲染)
        self.table.setItemDelegateForColumn(0, CenteredCheckBoxDelegate(self.table))
        self.table.setItemDelegateForColumn(8, ProgressDelegate(self.table))
        self.table.setItemDelegateForColumn(9, StatusDelegate(self.table))

        self.action_delegate = ActionDelegate(self.table)
        self.action_delegate.sig_download.connect(self.sig_download_clicked)
        self.action_delegate.sig_cancel.connect(self.sig_cancel_clicked)
        self.table.setItemDelegateForColumn(10, self.action_delegate)
        self.table.setMouseTracking(True)

        # 优化选中样式：使用浅色背景 + 深色文字
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
        self.page_size_combo.addItems(["500", "1000", "2000", "3000"])
        # # 日志页默认每页1000条
        self.page_size_combo.setCurrentText("1000")

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

        self.batch_download_btn.clicked.connect(self.sig_batch_download_clicked)
        self.batch_cancel_btn.clicked.connect(self.sig_batch_cancel_clicked)
        self.prev_btn.clicked.connect(self._on_prev_page_clicked)
        self.next_btn.clicked.connect(self._on_next_page_clicked)
        self.page_size_combo.currentTextChanged.connect(self._on_page_size_changed)


        # 允许多行选择以支持批量操作（用户可以 Ctrl/Shift 选择多行）
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)

        # 初始化 Toast
        self.toast = MessageToast(self)

        # 新增：绑定时间变化信号，用于实时校验
        self.date_from.dateTimeChanged.connect(self._on_time_changed)
        self.date_to.dateTimeChanged.connect(self._on_time_changed)

    # ---- 供 Controller 调用的接口 ----
    def show_toast(self, text: str, type_: int = 0):
        """显示 Toast 提示 (0:success, 1:error, 2:info)"""
        self.toast.show_toast(text, type_)

    def get_filter_criteria(self) -> dict:
        """从界面控件收集当前过滤条件，返回一个 dict。
        返回字段说明：
            path_kw (str)   : Path 关键字，"全部"或空字符串表示不限制
            app_kw  (str)   : 应用 ID 关键字，"全部"或空字符串表示不限制
            name_kw (str)   : 文件名关键字
            status  (str)   : 下拉框选中的状态文本，"全部" 表示不过滤状态
            date_from/date_to (QDateTime|None): 时间范围；无效时返回 None
        """
        # 读取用户在界面上输入的 Path
        path_kw = self.path_input.text().strip()

        # 读取 AppID 下拉框
        app_kw = self.appid_combo.currentText()
        if app_kw == "全部":
            app_kw = ""

        # 读取 Filename 输入框并去除空白
        name_kw = self.filename_input.text().strip()
        # 读取状态下拉框的当前显示文本（例如：全部、未下载、下载中、已下载、失败...）
        status = self.status_combo.currentText()

        # --- 时间范围过滤（始终生效）---
        d_from = self.date_from.dateTime()
        d_to = self.date_to.dateTime()

        # 修改判断逻辑：基于 CalendarDateEdit 的 null_date 判断
        from_ok = d_from and (d_from > self.date_from.null_date)
        to_ok = d_to and (d_to > self.date_to.null_date)

        # 修改：不再在此处进行拦截校验，仅返回数据
        criteria = {
            "path_kw": path_kw,
            "app_kw": app_kw,
            "name_kw": name_kw,
            "status": status,
            "date_from": d_from if from_ok else None,
            "date_to": d_to if to_ok else None,
        }
        return criteria  # 返回过滤条件

    def _is_time_range_valid(self) -> bool:
        """单独的校验逻辑：起始时间不能晚于结束时间"""
        d_from = self.date_from.dateTime()
        d_to = self.date_to.dateTime()
        from_ok = d_from and (d_from > self.date_from.null_date)
        to_ok = d_to and (d_to > self.date_to.null_date)

        if from_ok and to_ok and d_from > d_to:
            self.show_toast("起始时间不能晚于结束时间", 1)
            return False
        return True

    def set_appid_options(self, appids: list):
        """更新 APPID 下拉框选项，保持当前选中项"""
        current = self.appid_combo.currentText()

        self.appid_combo.blockSignals(True) # 防止触发不必要的信号
        self.appid_combo.clear()
        self.appid_combo.addItem("全部")
        self.appid_combo.addItems(appids)

        # 尝试恢复之前选中的项目
        idx = self.appid_combo.findText(current)
        if idx >= 0:
            self.appid_combo.setCurrentIndex(idx)
        else:
            self.appid_combo.setCurrentIndex(0) # 默认选中全部

        self.appid_combo.blockSignals(False)

    def set_table_model(self, model):
        """设置 QTableView 的模型"""
        # 绑定 header <-> model 的全选逻辑（公共实现）
        if self._header_ctrl is None and self._check_header is not None:
            self._header_ctrl = CheckableHeaderController(self.table, self._check_header)
        if self._header_ctrl is not None:
            self._header_ctrl.bind_model(model)
        else:
            self.table.setModel(model)

        self.table.setMouseTracking(True)

        # 你想要“表头在 view 写死，model 只传数据”是可以的：
        # 这里直接把 headers 设置到 model（如果它支持 set_headers）。
        fixed_headers = ["", "序号", "FileName", "Path", "Type", "Size(KB)", "CreateTime", "ModifiedTime", "下载进度", "状态", "操作"]
        if hasattr(model, "set_headers"):
            try:
                model.set_headers(fixed_headers)
            except Exception:
                pass

        # 调整列宽
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

        # 初始同步一次
        if self._header_ctrl is not None:
            try:
                self._header_ctrl._sync_from_model()
            except Exception:
                pass


    def update_pager(self, page: int, page_count: int, total: int):
        self.page_label.setText(f"第 {page}/{page_count} 页，共 {total} 条")
        self.prev_btn.setEnabled(page > 1)
        self.next_btn.setEnabled(page < page_count)

    def get_checked_rows(self) -> list:
        """获取当前页面所有被勾选的行索引 (row_index)"""
        # 修改为从 model 取状态
        model = self.table.model()
        if hasattr(model, "_checks"):
            return [r for r, checked in model._checks.items() if checked]
        return []

    # ---- 内部槽：把 UI 事件转换成信号，交给 Controller ----
    def _on_search_clicked(self):
        # 修改：点击搜索前先校验时间，若非法则直接返回不搜索
        if not self._is_time_range_valid():
            return

        # 收集界面上用户填写的过滤条件，得到一个字典
        criteria = self.get_filter_criteria()
        # 发送“搜索按钮被点击”信号，并将过滤条件作为参数传递
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
            size = 1000
        self.sig_page_size_changed.emit(size)

    def _on_header_clicked(self, logical_index: int):
        """表头点击事件：View 只发信号，排序规则由 Controller 决定。"""
        self.sig_sort_requested.emit(int(logical_index))

    def _on_time_changed(self):
        """时间控件值变化时触发校验"""
        self._is_time_range_valid()

# ---- Delegates ----
# 自定义复选框 Delegate，实现居中显示和点击切换状态
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
        if check_state == QtCore.Qt.Checked:
            cb_opt.state |= QtWidgets.QStyle.State_On
        else:
            cb_opt.state |= QtWidgets.QStyle.State_Off

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

# 自定义进度条 Delegate
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

# 自定义状态标签 Delegate
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

# 自定义操作列按钮 Delegate
class ActionDelegate(QtWidgets.QStyledItemDelegate):
    """操作列按钮 Delegate：与日志下载页实现保持一模一样（同颜色/同圆角/同禁用态/同文字）。"""

    sig_download = QtCore.pyqtSignal(str)
    sig_cancel = QtCore.pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

    def paint(self, painter, option, index):
        if not index.isValid():
            return

        # Column 10 is actions. Column 9 is status.
        status_idx = index.sibling(index.row(), 9)
        status = status_idx.data(QtCore.Qt.DisplayRole)

        is_downloading = (status == "下载中")

        # Btn geometry
        spacing = 10
        btn_w = 84
        btn_h = 30

        total_w = 2 * btn_w + spacing
        start_x = option.rect.left() + (option.rect.width() - total_w) // 2
        y = option.rect.top() + (option.rect.height() - btn_h) // 2

        rect_down = QtCore.QRect(start_x, y, btn_w, btn_h)
        rect_cancel = QtCore.QRect(start_x + btn_w + spacing, y, btn_w, btn_h)

        # Draw "Download" Btn
        self._paint_modern_btn(painter, rect_down, "#10B981", "⬇️ 下载", True)
        # Draw "Cancel" Btn (enabled only when downloading/waiting)
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
