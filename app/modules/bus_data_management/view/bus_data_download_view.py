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
from app.modules.bus_data_management.view.delegates import (
    CenteredCheckBoxDelegate,
    ProgressDelegate,
    StatusDelegate,
    ActionDelegate,
    ACTION_COL_WIDTH,
)

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
        """初始化视图，预留 CheckBoxHeader 引用。"""
        # 1. 调用父类初始化
        super().__init__(parent)
        self._check_header = None  # type: CheckBoxHeaderView
        self._header_ctrl = None  # type: CheckableHeaderController

    def setup_ui(self):
        """构建整体 UI 布局，包括筛选栏、表格和分页栏。"""
        # 1. 设置根布局
        root = QtWidgets.QVBoxLayout(self)
        root.setSpacing(14)
        root.setContentsMargins(14, 14, 14, 14)

        # 2. 创建过滤查询区域
        filter_card = QtWidgets.QGroupBox("过滤查询")
        fc = QtWidgets.QVBoxLayout(filter_card)
        fc.setContentsMargins(12, 8, 12, 12)
        toolbar = QtWidgets.QGridLayout()
        toolbar.setHorizontalSpacing(10)
        toolbar.setVerticalSpacing(8)
        toolbar.setColumnStretch(1, 1)
        toolbar.setColumnStretch(3, 1)
        toolbar.setColumnStretch(5, 1)

        # 3. 初始化输入控件 (Tab/Type/Filename)
        self.tab_input = QtWidgets.QComboBox()
        self.tab_input.setEditable(True)
        # 配置 Completer 以支持前缀筛选 (Tab)
        tab_completer = self.tab_input.completer()
        if tab_completer:
            tab_completer.setCompletionMode(QtWidgets.QCompleter.PopupCompletion)
            tab_completer.setFilterMode(_Qt.MatchStartsWith)
            tab_completer.setCaseSensitivity(_Qt.CaseInsensitive)

        # 默认不再提供“全部/根目录”项；实际选项由 set_tab_options() 填充
        self.tab_input.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

        self.type_combo = QtWidgets.QComboBox()
        self.type_combo.setEditable(True)
        # 配置 Completer 以支持前缀筛选 (Type)
        type_completer = self.type_combo.completer()
        if type_completer:
            type_completer.setCompletionMode(QtWidgets.QCompleter.PopupCompletion)
            type_completer.setFilterMode(_Qt.MatchStartsWith)
            type_completer.setCaseSensitivity(_Qt.CaseInsensitive)

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

        # 4. 初始化功能按钮
        self.search_btn = ModernButton("搜索", "#2563EB", "🔍")
        self.refresh_btn = ModernButton("刷新", "#10B981", "🔄")

        self.batch_download_btn = ModernButton("批量下载", "#3B82F6", "⬇️")
        self.batch_cancel_btn = ModernButton("批量取消", "#EF4444", "✕")
        self.reset_btn = ModernButton("重置", "#F59E0B", "🔄")

        # 5. 组装输入工具栏布局
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

        # 6. 组装按钮布局
        btns = QtWidgets.QHBoxLayout()
        btns.addStretch(1)
        btns.addWidget(self.batch_download_btn)
        btns.addWidget(self.batch_cancel_btn)
        btns.addSpacing(20)
        btns.addWidget(self.search_btn)
        btns.addWidget(self.refresh_btn)
        btns.addWidget(self.reset_btn)

        # 7. 添加到过滤区域
        fc.addLayout(toolbar)
        fc.addLayout(btns)
        root.addWidget(filter_card)

        # 8. 初始化数据表及其样式
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

        # 9. 安装复选框表头
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

        # 10. 设置自定义代理 (Delegates)
        self.table.setItemDelegateForColumn(0, CenteredCheckBoxDelegate(self.table))
        self.table.setItemDelegateForColumn(8, ProgressDelegate(self.table))
        self.table.setItemDelegateForColumn(9, StatusDelegate(self.table))
        # 显式传入 path/status 列索引，以适配表格布局
        self.action_delegate = ActionDelegate(self.table, path_col=3, status_col=9)
        self.action_delegate.sig_download.connect(self.sig_download_clicked)
        self.action_delegate.sig_cancel.connect(self.sig_cancel_clicked)
        self.table.setItemDelegateForColumn(10, self.action_delegate)
        self.table.setMouseTracking(True)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)

        root.addWidget(self.table)

        # 11. 初始化分页控制条
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

        # 12. 连接全部交互信号
        self.search_btn.clicked.connect(self._on_search_clicked)
        self.refresh_btn.clicked.connect(self._on_refresh_clicked)
        self.batch_download_btn.clicked.connect(self.sig_batch_download_clicked)
        self.batch_cancel_btn.clicked.connect(self.sig_batch_cancel_clicked)
        self.prev_btn.clicked.connect(self._on_prev_page_clicked)
        self.next_btn.clicked.connect(self._on_next_page_clicked)
        self.page_size_combo.currentTextChanged.connect(self._on_page_size_changed)
        self.reset_btn.clicked.connect(self._on_reset)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.toast = MessageToast(self)
        self.date_from.dateTimeChanged.connect(self._on_time_changed)
        self.date_to.dateTimeChanged.connect(self._on_time_changed)

    def show_toast(self, text: str, type_: int = 0):
        """显示 Toast 提示 (0:success, 1:error, 2:info)。"""
        # 1. 调用 MessageToast 显示方法
        self.toast.show_toast(text, type_)

    def set_tab_options(self, labels, values):
        """设置 Tab 下拉框的选项列表。"""
        # 1. 暂时屏蔽信号防止触发搜索
        self.tab_input.blockSignals(True)
        # 2. 记录当前选中的值，以便刷新后恢复
        current_data = self.tab_input.currentData()

        # 3. 清空并重新添加选项
        self.tab_input.clear()
        for label, value in zip(labels, values):
            self.tab_input.addItem(label, value)

        # 4. 尝试恢复原选中项
        if current_data:
            idx = self.tab_input.findData(current_data)
            if idx >= 0:
                self.tab_input.setCurrentIndex(idx)

        # 5. 恢复信号响应
        self.tab_input.blockSignals(False)

    def set_type_options(self, types: list):
        """设置 Type 下拉框的选项列表。"""
        # 1. 获取当前选中的文本
        current = self.type_combo.currentText()
        # 2. 屏蔽信号并更新选项
        self.type_combo.blockSignals(True)
        self.type_combo.clear()
        self.type_combo.addItem("全部")
        self.type_combo.addItems(sorted(types))
        # 3. 尝试恢复选中状态
        idx = self.type_combo.findText(current)
        self.type_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.type_combo.blockSignals(False)

    def update_pager(self, page: int, page_count: int, total: int):
        """更新分页栏显示内容。"""
        # 1. 更新文本标签
        self.page_label.setText(f"第 {page}/{page_count} 页，共 {total} 条")
        # 2. 根据当前页码通过按钮状态（避免越界）
        self.prev_btn.setEnabled(page > 1)
        self.next_btn.setEnabled(page < page_count)

    def get_filter_criteria(self) -> dict:
        """获取当前界面上的所有筛选条件。"""
        # 1. 辅助函数：获取有效的日期时间对象
        def _get_valid_dt(widget):
            dt = widget.dateTime()
            return dt if dt and dt > widget.null_date else None

        type_text = self.type_combo.currentText()

        # 2. 返回条件字典
        return {
            "tab_kw": self.tab_input.currentData() or "",
            "type_kw": "" if type_text == "全部" else type_text,
            "name_kw": self.filename_input.text().strip(),
            "status": self.status_combo.currentText(),
            "date_from": _get_valid_dt(self.date_from),
            "date_to": _get_valid_dt(self.date_to),
        }

    def set_table_model(self, model):
        """设置表格模型并初始化表头控制器。"""
        # 1. 确保表头控制器已初始化
        if self._header_ctrl is None and self._check_header is not None:
            self._header_ctrl = CheckableHeaderController(self.table, self._check_header)
        # 2. 绑定模型到控制器或表格
        if self._header_ctrl is not None:
            self._header_ctrl.bind_model(model)
        else:
            self.table.setModel(model)
        self.table.setMouseTracking(True)

        # 3. 配置列宽模式
        hheader = self.table.horizontalHeader()

        # 定义列配置：(列索引, 缩放模式, 宽度(可选))
        # 模式简写：F=Fixed, R=ResizeToContents, I=Interactive, S=Stretch
        HV = QtWidgets.QHeaderView
        col_configs = [
            (0, HV.Fixed, 80),
            (1, HV.ResizeToContents, None),
            (2, HV.Interactive, 180),
            (3, HV.Interactive, 360),
            (4, HV.ResizeToContents, None),
            (5, HV.ResizeToContents, None),
            (6, HV.ResizeToContents, None),
            (7, HV.ResizeToContents, None),
            (8, HV.Stretch, 200),
            (9, HV.Interactive, 120),
            (10, HV.Fixed, ACTION_COL_WIDTH),
        ]

        # 4. 应用列配置
        for col_idx, mode, width in col_configs:
            hheader.setSectionResizeMode(col_idx, mode)
            if width is not None:
                self.table.setColumnWidth(col_idx, width)

        # 5. 同步表头数据状态
        if self._header_ctrl is not None:
            try:
                self._header_ctrl._sync_from_model()
            except Exception:
                pass

    def _is_time_range_valid(self) -> bool:
        """检查时间范围有效性（起始时间是否大于结束时间）。"""
        # 1. 获取时间
        d_from = self.date_from.dateTime()
        d_to = self.date_to.dateTime()
        # 2. 检查两者是否都已设置
        from_ok = d_from and (d_from > self.date_from.null_date)
        to_ok = d_to and (d_to > self.date_to.null_date)
        # 3. 如果都设置了且 Start > End，报错
        if from_ok and to_ok and d_from > d_to:
            self.show_toast("起始时间不能晚于结束时间", 1)
            return False
        return True

    def _on_search_clicked(self):
        """搜索按钮点击槽函数。"""
        # 1. 校验时间范围
        if not self._is_time_range_valid():
            return
        # 2. 发送搜索信号
        self.sig_search_clicked.emit(self.get_filter_criteria())

    def _on_refresh_clicked(self):
        """刷新按钮点击槽函数。"""
        # 1. 发送刷新信号
        self.sig_refresh_clicked.emit()

    def _on_prev_page_clicked(self):
        """上一页按钮点击槽函数。"""
        # 1. 发送页码变更信号（-1）
        self.sig_page_changed.emit(-1)

    def _on_next_page_clicked(self):
        """下一页按钮点击槽函数。"""
        # 1. 发送页码变更信号（+1）
        self.sig_page_changed.emit(+1)

    def _on_page_size_changed(self, text: str):
        """每页条数下拉框变更槽函数。"""
        # 1. 解析输入的数字
        try:
            size = int(text)
        except ValueError:
            size = 10
        # 2. 发送信号
        self.sig_page_size_changed.emit(size)

    def _on_header_clicked(self, logical_index: int):
        """表头点击槽函数（用于排序）。"""
        # 1. 发送排序请求
        self.sig_sort_requested.emit(int(logical_index))

    def _on_time_changed(self):
        """日期控件值变更时的实时校验。"""
        # 1. 触发一次校验逻辑
        self._is_time_range_valid()

    def showEvent(self, event):
        """窗口显示事件重写。"""
        # 1. 调用父类
        super().showEvent(event)
        # 2. 发送视图显示信号
        self.sig_view_shown.emit()

    def _on_reset(self):
        """重置按钮点击槽函数（清空所有输入控件）。"""
        # 1. 恢复控件到默认状态
        self.tab_input.setCurrentIndex(-1)  # Clear tab selection
        self.date_from.clear()
        self.date_to.clear()
        self.type_combo.setCurrentIndex(0)  # Assuming first item "全部" is index 0
        self.filename_input.clear()
        self.status_combo.setCurrentIndex(0)  # Assuming first item "全部" is index 0
