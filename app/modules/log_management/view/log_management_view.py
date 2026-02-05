# python
from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtCore import Qt as _Qt, pyqtSignal

from app.common.ui.widgets import ModernButton
from app.common.ui.modern_widgets import MessageToast
from app.presentation.views.base_view import BaseView
from app.common.ui.checkable_header import CheckBoxHeaderView, CheckableHeaderController
from app.modules.bus_data_management.view.CalendarDateEdit import CalendarDateEdit  # 新增引用
from app.modules.bus_data_management.view.delegates import CenteredCheckBoxDelegate, ProgressDelegate, StatusDelegate, ActionDelegate, ACTION_COL_WIDTH

ALIGN_CENTER = int(getattr(_Qt, "AlignCenter", 132))
USER_ROLE = int(getattr(_Qt, "UserRole", 256))

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
    sig_view_shown = pyqtSignal()  # 页面显示信号（在 widget.showEvent 时触发）

    def __init__(self, parent=None):
        """初始化视图，设置父对象和基础状态。"""
        # 1. 调用父类初始化
        super().__init__(parent)
        self._locale = QtCore.QLocale(QtCore.QLocale.English)
        self._check_header = None
        self._header_ctrl = None

    def setup_ui(self):
        """构建整体 UI 布局，包括筛选栏、表格和分页栏。"""
        # 1. 初始化默认属性（若不存在）
        if not hasattr(self, "all_files"): self.all_files = []
        if not hasattr(self, "filtered_files"): self.filtered_files = []
        if not hasattr(self, "page"): self.page = 1
        if not hasattr(self, "page_size"): self.page_size = 100

        # 2. 设置根布局
        root = QtWidgets.QVBoxLayout(self)
        root.setSpacing(14)
        root.setContentsMargins(14, 14, 14, 14)

        # 3. 创建过滤查询区域（卡片）
        filter_card = QtWidgets.QGroupBox("过滤查询")
        fc = QtWidgets.QVBoxLayout(filter_card)
        fc.setContentsMargins(12, 8, 12, 12)
        toolbar = QtWidgets.QGridLayout()
        toolbar.setHorizontalSpacing(10)
        toolbar.setVerticalSpacing(8)

        # 4. 初始化输入控件：Path
        self.path_combo = QtWidgets.QComboBox()
        self.path_combo.setEditable(True)
        self.path_combo.setPlaceholderText("选择或输入 path")
        # 默认值
        self.path_combo.setEditText("/log/CCUA/core")
        # 让下拉框宽一些
        self.path_combo.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

        # 5. 初始化输入控件：APPID
        self.appid_combo = QtWidgets.QComboBox()
        self.appid_combo.setEditable(True)  # 支持可编辑
        # 配置 Completer 以支持前缀筛选 (Case Insensitive)
        completer = self.appid_combo.completer()
        if completer:
            completer.setCompletionMode(QtWidgets.QCompleter.PopupCompletion)
            completer.setFilterMode(_Qt.MatchStartsWith)
            completer.setCaseSensitivity(_Qt.CaseInsensitive)
        self.appid_combo.addItem("全部")
        self.appid_combo.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

        # 6. 初始化输入控件：Filename
        self.filename_input = QtWidgets.QLineEdit()
        self.filename_input.setPlaceholderText("输入 filename")

        # 7. 初始化时间选择控件（自定义 CalendarDateEdit）
        self.date_from = CalendarDateEdit()
        self.date_from.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.date_to = CalendarDateEdit()
        self.date_to.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

        # 8. 初始化状态下拉框
        self.status_combo = QtWidgets.QComboBox()
        self.status_combo.addItems(STATUS_OPTIONS)

        # 9. 初始化功能按钮
        self.search_btn = ModernButton("搜索", "#2563EB", "🔍")
        self.refresh_btn = ModernButton("刷新", "#10B981", "🔄")
        # 新增：重置按钮，重置所有过滤条件并触发一次搜索
        self.reset_btn = ModernButton("重置", "#F59E0B", "🔄")

        # 10. 初始化批量操作按钮
        self.batch_download_btn = ModernButton("批量下载", "#3B82F6", "⬇️")
        self.batch_cancel_btn = ModernButton("批量取消", "#EF4444", "✕")

        # 11. 确保时间控件可用
        self.date_from.setEnabled(True)
        self.date_to.setEnabled(True)

        # 12. 组装输入工具栏布局（两行排布）
        toolbar.addWidget(QtWidgets.QLabel("Path"), 0, 0)
        toolbar.addWidget(self.path_combo, 0, 1)
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

        # 13. 组装按钮布局
        btns = QtWidgets.QHBoxLayout()
        btns.addStretch(1)

        btns.addWidget(self.batch_download_btn)
        btns.addWidget(self.batch_cancel_btn)
        btns.addSpacing(20)  # 在批量按钮和常用按钮间加点间隔
        btns.addWidget(self.search_btn)
        btns.addWidget(self.refresh_btn)
        btns.addWidget(self.reset_btn)

        # 14. 添加到过滤区域
        fc.addLayout(toolbar)
        fc.addLayout(btns)
        root.addWidget(filter_card)

        # 15. 初始化数据表及其基本的显示属性
        self.table = QtWidgets.QTableView() # Changed from QTableWidget
        self.table.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        pal = self.table.palette()
        pal.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor("#F9FAFB"))
        self.table.setPalette(pal)
        self.table.setShowGrid(False) # Optional style

        # 16. 调整行高和列宽策略
        vheader = self.table.verticalHeader()
        # 行高在这里调，高一些比如 46 像素
        vheader.setDefaultSectionSize(55)
        vheader.setMinimumSectionSize(40)
        vheader.setSectionResizeMode(QtWidgets.QHeaderView.Fixed)

        # 17. 使用支持“全选”的表头（第0列）
        self._check_header = CheckBoxHeaderView(_Qt.Horizontal, self.table)
        self.table.setHorizontalHeader(self._check_header)
        self._header_ctrl = CheckableHeaderController(self.table, self._check_header)

        hheader = self.table.horizontalHeader()
        hheader.setStretchLastSection(True)
        hheader.setHighlightSections(False)
        hheader.setDefaultSectionSize(110)
        hheader.setMinimumSectionSize(70)

        # 18. 启用表头排序点击
        hheader.setSectionsClickable(True)
        hheader.setSortIndicatorShown(True)
        hheader.sectionClicked.connect(self._on_header_clicked)

        # 19. 设置 Delegates (代理渲染)
        self.table.setItemDelegateForColumn(0, CenteredCheckBoxDelegate(self.table))
        self.table.setItemDelegateForColumn(8, ProgressDelegate(self.table))
        self.table.setItemDelegateForColumn(9, StatusDelegate(self.table))

        # 20. 配置操作列代理（显式传入 path_col/status_col）
        self.action_delegate = ActionDelegate(self.table, path_col=3, status_col=9)
        self.action_delegate.sig_download.connect(self.sig_download_clicked)
        self.action_delegate.sig_cancel.connect(self.sig_cancel_clicked)
        self.table.setItemDelegateForColumn(10, self.action_delegate)
        self.table.setMouseTracking(True)

        # 21. 优化选中样式：使用浅色背景 + 深色文字
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

        # 22. 初始化分页控制条（卡片式）
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

        # 23. 连接信号：绑定到内部槽函数
        self.search_btn.clicked.connect(self._on_search_clicked)
        self.refresh_btn.clicked.connect(self._on_refresh_clicked)
        self.reset_btn.clicked.connect(self._on_reset_clicked)

        self.batch_download_btn.clicked.connect(self.sig_batch_download_clicked)
        self.batch_cancel_btn.clicked.connect(self.sig_batch_cancel_clicked)
        self.prev_btn.clicked.connect(self._on_prev_page_clicked)
        self.next_btn.clicked.connect(self._on_next_page_clicked)
        self.page_size_combo.currentTextChanged.connect(self._on_page_size_changed)

        # 24. 允许多行选择以支持批量操作
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)

        # 25. 初始化 Toast 组件
        self.toast = MessageToast(self)

        # 26. 绑定时间变化信号，用于实时校验
        self.date_from.dateTimeChanged.connect(self._on_time_changed)
        self.date_to.dateTimeChanged.connect(self._on_time_changed)

    # ---- 供 Controller 调用的接口 ----
    def show_toast(self, text: str, type_: int = 0):
        """显示 Toast 提示 (0:success, 1:error, 2:info)。"""
        # 1. 调用 MessageToast 显示方法
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
        # 1. 读取用户在界面上输入的 Path
        path_kw = self.path_combo.currentText().strip()

        # 2. 读取 AppID 下拉框
        app_kw = self.appid_combo.currentText()
        if app_kw == "全部":
            app_kw = ""

        # 3. 读取 Filename 输入框并去除空白
        name_kw = self.filename_input.text().strip()
        # 4. 读取状态下拉框的当前显示文本
        status = self.status_combo.currentText()

        # 5. 读取时间范围（始终生效）
        d_from = self.date_from.dateTime()
        d_to = self.date_to.dateTime()

        # 6. 判断时间有效性：基于 CalendarDateEdit 的 null_date 判断
        from_ok = d_from and (d_from > self.date_from.null_date)
        to_ok = d_to and (d_to > self.date_to.null_date)

        # 7. 组装并返回过滤条件字典
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
        """单独的校验逻辑：校验起始时间是否晚于结束时间。"""
        # 1. 获取时间对象
        d_from = self.date_from.dateTime()
        d_to = self.date_to.dateTime()
        # 2. 检查有效性
        from_ok = d_from and (d_from > self.date_from.null_date)
        to_ok = d_to and (d_to > self.date_to.null_date)

        # 3. 比较时间
        if from_ok and to_ok and d_from > d_to:
            self.show_toast("起始时间不能晚于结束时间", 1)
            return False
        return True

    def set_appid_options(self, appids: list):
        """更新 APPID 下拉框选项，保持当前选中项。"""
        # 1. 获取当前选中的文本
        current = self.appid_combo.currentText()

        # 2. 屏蔽信号并更新下拉项
        self.appid_combo.blockSignals(True) # 防止触发不必要的信号
        self.appid_combo.clear()
        self.appid_combo.addItem("全部")
        self.appid_combo.addItems(appids)

        # 3. 尝试恢复之前选中的项目
        idx = self.appid_combo.findText(current)
        if idx >= 0:
            self.appid_combo.setCurrentIndex(idx)
        else:
            self.appid_combo.setCurrentIndex(0) # 默认选中全部

        # 4. 恢复信号响应
        self.appid_combo.blockSignals(False)

    def set_path_options(self, paths: list):
        """更新 Path 下拉框选项，保持当前选中项。"""
        # 1. 获取当前选中的文本
        current = self.path_combo.currentText()

        # 2. 屏蔽信号并更新下拉项
        self.path_combo.blockSignals(True)
        self.path_combo.clear()
        # 我们可以加一个为空的或者默认的选项吗？用户可能更喜欢保持当前的
        self.path_combo.addItems(paths)

        # 3. 恢复之前选中的文本
        self.path_combo.setEditText(current)

        # 4. 恢复信号响应
        self.path_combo.blockSignals(False)

    def set_table_model(self, model):
        """设置 QTableView 的模型，并配置表头和代理。"""
        # 1. 绑定 header <-> model 的全选逻辑（公共实现）
        if self._header_ctrl is None and self._check_header is not None:
            self._header_ctrl = CheckableHeaderController(self.table, self._check_header)
        if self._header_ctrl is not None:
            self._header_ctrl.bind_model(model)
        else:
            self.table.setModel(model)

        self.table.setMouseTracking(True)

        # 2. 尝试向 model 注入固定表头信息（如果支持）
        fixed_headers = ["", "序号", "FileName", "Path", "Type", "Size(KB)", "CreateTime", "ModifiedTime", "下载进度", "状态", "操作"]
        if hasattr(model, "set_headers"):
            try:
                model.set_headers(fixed_headers)
            except Exception:
                pass

        # 3. 调整列宽和模式
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

        # 4. 初始同步一次全选框状态
        if self._header_ctrl is not None:
            try:
                self._header_ctrl._sync_from_model()
            except Exception:
                pass


    def update_pager(self, page: int, page_count: int, total: int):
        """更新分页栏控件的状态。"""
        # 1. 更新信息标签
        self.page_label.setText(f"第 {page}/{page_count} 页，共 {total} 条")
        # 2. 更新按钮启用状态
        self.prev_btn.setEnabled(page > 1)
        self.next_btn.setEnabled(page < page_count)

    def get_checked_rows(self) -> list:
        """获取当前页面所有被勾选的行索引 (row_index)。"""
        # 1. 从 model 取状态
        model = self.table.model()
        if hasattr(model, "_checks"):
            return [r for r, checked in model._checks.items() if checked]
        return []

    # ---- 内部槽：把 UI 事件转换成信号，交给 Controller ----
    def _on_search_clicked(self):
        """搜索按钮点击槽函数。"""
        # 1. 校验时间范围，若非法则直接返回
        if not self._is_time_range_valid():
            return

        # 2. 收集界面上用户填写的过滤条件
        criteria = self.get_filter_criteria()
        # 3. 发送搜索信号
        self.sig_search_clicked.emit(criteria)

    def _on_refresh_clicked(self):
        """刷新按钮点击槽函数。"""
        # 1. 发送刷新信号
        self.sig_refresh_clicked.emit()

    def _on_reset_clicked(self):
        """重置按钮点击槽函数：清空条件并触发一次默认搜索。"""
        try:
            # 1. 清除 Path 输入
            if hasattr(self, 'path_combo'):
                self.path_combo.setEditText("")
            # 2. 清除 Filename 输入
            if hasattr(self, 'filename_input'):
                self.filename_input.clear()
            # 3. 恢复 AppID 下拉（默认全部）
            if hasattr(self, 'appid_combo'):
                try:
                    self.appid_combo.setCurrentIndex(0)
                except Exception:
                    pass
            # 4. 恢复 Status 下拉（默认全部）
            if hasattr(self, 'status_combo'):
                try:
                    self.status_combo.setCurrentIndex(0)
                except Exception:
                    pass
            # 5. 清空时间选择
            if hasattr(self, 'date_from'):
                try:
                    self.date_from.clear()
                except Exception:
                    pass
            if hasattr(self, 'date_to'):
                try:
                    self.date_to.clear()
                except Exception:
                    pass
        except Exception:
            pass

        # 6. 触发一次搜索以刷新结果
        self._on_search_clicked()

    def _on_prev_page_clicked(self):
        """上一页按钮点击槽函数。"""
        # 1. 发送上一页信号 (-1)
        self.sig_page_changed.emit(-1)  # 使用 -1 表示上一页

    def _on_next_page_clicked(self):
        """下一页按钮点击槽函数。"""
        # 1. 发送下一页信号 (+1)
        self.sig_page_changed.emit(+1)  # 使用 +1 表示下一页

    def _on_page_size_changed(self, text: str):
        """每页条数变更槽函数。"""
        # 1. 解析数值
        try:
            size = int(text)
        except ValueError:
            size = 1000
        # 2. 发送变更信号
        self.sig_page_size_changed.emit(size)

    def _on_header_clicked(self, logical_index: int):
        """表头点击事件：View 只发信号，排序规则由 Controller 决定。"""
        # 1. 发送排序请求信号
        self.sig_sort_requested.emit(int(logical_index))

    def _on_time_changed(self):
        """时间控件值变化时触发校验。"""
        # 1. 执行校验
        self._is_time_range_valid()

    def showEvent(self, event):
        """窗口显示事件重写。"""
        # 1. 调用父类显示
        super().showEvent(event)
        # 2. 发送视图显示信号
        self.sig_view_shown.emit()

    def _create_filter_area(self) -> QtWidgets.QWidget:
        """创建过滤查询区域的控件（似乎是废弃代码，保留备份）。"""
        # 1. 创建容器
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)

        # 2. 创建顶部行布局
        # 顶部一行：Path, AppID, Filename
        top_row = QtWidgets.QGridLayout()
        top_row.setHorizontalSpacing(10)
        top_row.setVerticalSpacing(8)

        # 3. Path 输入
        self.search_input = QtWidgets.QLineEdit()
        self.search_input.setPlaceholderText("输入关键字")
        top_row.addWidget(QtWidgets.QLabel("关键字"), 0, 0)
        top_row.addWidget(self.search_input, 0, 1)

        # 4. AppID 下拉
        self.level_combo = QtWidgets.QComboBox()
        self.level_combo.addItem("全部")
        self.level_combo.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        top_row.addWidget(QtWidgets.QLabel("日志级别"), 0, 2)
        top_row.addWidget(self.level_combo, 0, 3)

        # 5. 时间范围
        self.start_date = CalendarDateEdit()
        self.end_date = CalendarDateEdit()
        top_row.addWidget(QtWidgets.QLabel("时间范围"), 0, 4)
        top_row.addWidget(self.start_date, 0, 5)
        top_row.addWidget(QtWidgets.QLabel("至"), 0, 6)
        top_row.addWidget(self.end_date, 0, 7)

        # 6. 按钮区域
        self.search_btn = ModernButton("查询", "primary")
        self.search_btn.clicked.connect(self._on_search)

        self.reset_btn = ModernButton("重置", "default")
        self.reset_btn.clicked.connect(self._on_reset)

        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addStretch(1)
        button_layout.addWidget(self.search_btn)
        button_layout.addWidget(self.reset_btn)

        # 7. 组合布局
        # 将时间选择器和按钮布局添加到主布局
        layout.addLayout(top_row)
        layout.addLayout(button_layout)

        return widget

    def _on_search(self):
        """（废弃或备用）搜索逻辑。"""
        # 1. 校验时间
        if not self._is_time_range_valid():
            return

        # 2. 构建条件
        criteria = {
            "keyword": self.search_input.text().strip(),
            "level": self.level_combo.currentText(),
            "date_from": self.start_date.dateTime() if self.start_date.is_valid() else None,
            "date_to": self.end_date.dateTime() if self.end_date.is_valid() else None
        }

        # 3. 发送信号 (sig_search_requested 未定义，可能是笔误或旧代码)
        self.sig_search_requested.emit(criteria)

    def _on_reset(self):
        """（废弃或备用）重置逻辑。"""
        # 1. 清空控件
        self.start_date.clear()
        self.end_date.clear()
        if hasattr(self, 'level_combo'):
            self.level_combo.setCurrentIndex(0)
        self.search_input.clear()
        # 2. 触发搜索
        self._on_search()
