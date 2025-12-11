from typing import Optional
from PyQt5 import QtWidgets, QtGui, QtCore
from PyQt5.QtCore import Qt

from app.common.ui.widgets import ModernButton
from app.presentation.views.base_view import BaseView


class FullCellDelegate(QtWidgets.QStyledItemDelegate):
    """一个委托，提供覆盖整格的 QLineEdit 编辑器。

    仅负责“整格编辑”的无边框输入框，不包含任何业务逻辑。
    """

    def createEditor(self, parent, option, index):
        editor = QtWidgets.QLineEdit(parent)
        editor.setFrame(False)
        # 移除边框和外间距，但保留不透明背景以避免重影
        # 使用调色板的基色作为实心不透明背景以遮盖底层文本
        try:
            palette = (option.palette() if option is not None else parent.palette())
            base_color = palette.color(QtGui.QPalette.Base).name()
            # 确保编辑器绘制不透明背景以覆盖单元格
            editor.setStyleSheet(
                f"background-color: {base_color}; border: none; padding: 2px 6px; margin: 0px;"
            )
            # 提示 Qt 该控件将绘制不透明背景
            editor.setAttribute(QtCore.Qt.WA_OpaquePaintEvent, True)
            # 确保样式化背景的处理
            editor.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        except Exception:
            editor.setStyleSheet("border: none; padding: 2px 6px; margin: 0px;")
        editor.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        editor.setContentsMargins(0, 0, 0, 0)
        editor.setTextMargins(0, 0, 0, 0)
        # 使用父控件的调色板填充背景（防止底层文字透出）
        try:
            editor.setAutoFillBackground(True)
            palette = parent.palette() if parent is not None else editor.palette()
            editor.setPalette(palette)
            editor.setBackgroundRole(QtGui.QPalette.Base)
        except Exception:
            pass
        try:
            if parent is not None:
                editor.setFont(parent.font())
        except Exception:
            pass
        try:
            editor.setClearButtonEnabled(False)
        except Exception:
            pass
        return editor

    def setEditorData(self, editor, index):
        value = index.model().data(index, Qt.EditRole)
        editor.setText("" if value is None else str(value))

    def setModelData(self, editor, model, index):
        model.setData(index, editor.text(), Qt.EditRole)

    def updateEditorGeometry(self, editor, option, index):
        # 确保编辑器覆盖整个可视矩形并使用准确的高度
        rect = option.rect.adjusted(0, 0, 0, 0)
        editor.setGeometry(rect)
        editor.setContentsMargins(0, 0, 0, 0)
        editor.setTextMargins(0, 0, 0, 0)
        try:
            editor.setFixedHeight(option.rect.height())
        except Exception:
            pass


class ComboBoxDelegate(QtWidgets.QStyledItemDelegate):
    """通用整格下拉委托：常态显示文本，编辑时整格变成 QComboBox。"""

    def __init__(self, items_provider=None, parent=None):
        super().__init__(parent)
        self._items_provider = items_provider

    def _get_items(self, index):
        if callable(self._items_provider):
            items = self._items_provider(index)
            try:
                return list(items)
            except TypeError:
                return []
        return []

    def createEditor(self, parent, option, index):
        editor = QtWidgets.QComboBox(parent)
        editor.setFrame(False)
        editor.setEditable(False)
        editor.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToContents)
        # 确保下拉在编辑时为不透明背景，遮盖底层文本
        try:
            palette = (option.palette() if option is not None else (parent.palette() if parent is not None else editor.palette()))
            base_color = palette.color(QtGui.QPalette.Base).name()
            editor.setStyleSheet(f"background-color: {base_color}; border: none; padding: 2px 6px;")
            editor.setAutoFillBackground(True)
            editor.setPalette(palette)
            editor.setBackgroundRole(QtGui.QPalette.Base)
            editor.setAttribute(QtCore.Qt.WA_OpaquePaintEvent, True)
        except Exception:
            pass
        for text in self._get_items(index):
            editor.addItem(text)

        # 尝试在有 option.rect 的情况下将编辑器和弹出视图调整为覆盖整个单元格
        try:
            if option is not None and option.rect.isValid():
                w = max(20, option.rect.width())
                h = max(20, option.rect.height())
                # 编辑器本体尺寸
                editor.setMinimumWidth(w)
                try:
                    editor.setFixedHeight(h)
                except Exception:
                    pass
                # 下拉视图（QListView）宽度应与单元格一致
                try:
                    popup_view = editor.view()
                    popup_view.setMinimumWidth(w)
                    try:
                        popup_view.setFixedWidth(w)
                    except Exception:
                        pass
                except Exception:
                    pass
        except Exception:
            pass

        return editor

    def setEditorData(self, editor, index):
        if not isinstance(editor, QtWidgets.QComboBox):
            return
        current_text = str(index.data(Qt.EditRole) or "")
        idx = editor.findText(current_text)
        if idx >= 0:
            editor.setCurrentIndex(idx)

    def setModelData(self, editor, model, index):
        if not isinstance(editor, QtWidgets.QComboBox):
            return
        model.setData(index, editor.currentText(), Qt.EditRole)

    def updateEditorGeometry(self, editor, option, index):
        # 确保编辑器填满单元格并且弹出视图具有相同宽度
        try:
            editor.setGeometry(option.rect)
            popup_view = editor.view()
            try:
                popup_view.setMinimumWidth(option.rect.width())
                try:
                    popup_view.setFixedWidth(option.rect.width())
                except Exception:
                    pass
            except Exception:
                pass
        except Exception:
            # 回退
            editor.setGeometry(option.rect)


class ValueCellWidget(QtWidgets.QWidget):
    detailClicked = QtCore.pyqtSignal()
    editingFinished = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.line_edit = QtWidgets.QLineEdit(self)
        self.line_edit.setFrame(False)
        self.line_edit.setPlaceholderText("Value")
        self.line_edit.setClearButtonEnabled(False)
        self.line_edit.setMinimumHeight(28)
        layout.addWidget(self.line_edit)

        self.button = QtWidgets.QPushButton("...", self)
        self.button.setFixedSize(28, 28)
        self.button.setCursor(QtGui.QCursor(Qt.PointingHandCursor))
        self.button.setStyleSheet(
            "QPushButton { border: 1px solid #CBD5F5; border-radius: 4px; padding: 0; }"
            "QPushButton:hover { background-color: #EEF2FF; }"
        )
        self.button.setToolTip("查看 DPT 解析详情")
        layout.addWidget(self.button)

        self.button.clicked.connect(self.detailClicked.emit)
        self.line_edit.editingFinished.connect(self.editingFinished.emit)

    def set_text(self, text: str) -> None:
        self.line_edit.setText(text or "")

    def text(self) -> str:
        return self.line_edit.text()

    def set_placeholder(self, text: str) -> None:
        self.line_edit.setPlaceholderText(text or "Value")

    def set_text_color(self, color: Optional[QtGui.QColor]) -> None:
        palette = self.line_edit.palette()
        target = color or self.style().standardPalette().color(QtGui.QPalette.Text)
        palette.setColor(QtGui.QPalette.Text, target)
        self.line_edit.setPalette(palette)

    def focus_editor(self, select_all: bool = False) -> None:
        self.line_edit.setFocus(Qt.TabFocusReason)
        if select_all:
            self.line_edit.selectAll()

    def detail_button(self) -> QtWidgets.QPushButton:
        """Return the embedded detail button for popup anchoring."""
        return self.button


class DIDView(BaseView):
    ecu_map_import_requested = QtCore.pyqtSignal()
    dpt_import_requested = QtCore.pyqtSignal()
    value_detail_requested = QtCore.pyqtSignal(int)
    read_requested = QtCore.pyqtSignal()
    write_requested = QtCore.pyqtSignal()
    add_row_requested = QtCore.pyqtSignal()
    remove_row_requested = QtCore.pyqtSignal()
    move_up_requested = QtCore.pyqtSignal()
    move_down_requested = QtCore.pyqtSignal()
    cell_clicked = QtCore.pyqtSignal(int, int)
    cell_double_clicked = QtCore.pyqtSignal(int, int)

    def setup_ui(self):
        # 存储待应用的像素宽度（在首次布局完成后应用）
        self._pending_pixel_widths = None
        """构建 DID 界面布局：上方控制区 + DID 表格 + 请求/响应原始数据。"""
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setSpacing(6)
        main_layout.setContentsMargins(6, 6, 6, 6)

        # 顶部控制条：ECU 地址表导入 + DPT 导入 + 表格操作 + 读取/响应（全部放在同一行）
        ctl = QtWidgets.QHBoxLayout()
        ctl.setSpacing(6)

        self.ecu_map_btn = ModernButton("导入ECU目的地址表", "#6366F1", "📥")
        self.dpt_import_btn = ModernButton("导入DPT文件", "#22C55E", "📂")
        ctl.addWidget(self.ecu_map_btn)
        ctl.addWidget(self.dpt_import_btn)

        # 将表格工具按钮合并到顶栏，保持在导入按钮之后
        self.add_btn = ModernButton("+", "#22C55E", "")
        self.remove_btn = ModernButton("-", "#EF4444", "")
        self.up_btn = ModernButton("↑", "#6B7280", "")
        self.down_btn = ModernButton("↓", "#6B7280", "")
        for b in (self.add_btn, self.remove_btn, self.up_btn, self.down_btn):
            b.setFixedSize(26, 36)
            ctl.addWidget(b)

        # 读取/写入 放在最右侧
        ctl.addStretch()
        self.read_btn = ModernButton("读取", "#0EA5E9", "")
        self.write_btn = ModernButton("写入", "#F97316", "")
        self.read_btn.setFixedWidth(70)
        self.write_btn.setFixedWidth(70)
        ctl.addWidget(self.read_btn)
        ctl.addWidget(self.write_btn)

        main_layout.addLayout(ctl)

        # 中间区域：DID 表格
        table_container = QtWidgets.QVBoxLayout()
        table_container.setSpacing(4)

        # DID 表格
        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "",  # 选中
            "Description",
            "DID",
            "STR/HEX",
            "DiagnosticSession",
            "SecurityAccess",
            "Value",
        ])
        # 允许接收鼠标移动事件（用于委托在按钮上显示手形光标与 ToolTip)
        try:
            self.table.setMouseTracking(True)
            self.table.viewport().setMouseTracking(True)
            # 安装事件过滤器以便在 viewport 层级捕获鼠标移动并显示自定义 tooltip
            try:
                self.table.viewport().installEventFilter(self)
            except Exception:
                pass
        except Exception:
            pass
        header = self.table.horizontalHeader()
        # 允许用户交互调整列宽
        header.setSectionResizeMode(QtWidgets.QHeaderView.Interactive)
        header.setSectionsClickable(True)
        header.setHighlightSections(True)
        # 默认不拉伸最后一列 — 我们自己控制列宽以确保表头文本不被截断。
        header.setStretchLastSection(False)
        # 允许移动表头分区（可选）
        header.setSectionsMovable(True)
        # 如果视口容纳不了所有最小宽度，允许水平滚动
        self.table.setHorizontalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        self.table.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        # 编辑触发交给 controller 控制
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        # 增加行高
        self.table.verticalHeader().setDefaultSectionSize(34)
        # 让表格在容器中尽量占满空间
        self.table.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)

        # 更明显的网格线与内边距，使复选框左右间距一致
        self.table.setShowGrid(True)
        self.table.setGridStyle(QtCore.Qt.SolidLine)
        # 保持原有风格但增强网格线（不改动表头样式）
        self.table.setStyleSheet(
            "QTableWidget::item{ padding-left:6px; padding-right:6px; }"
            "QTableWidget::item:selected{ background: #e6f7ff; }"
            # 与现有界面风格一致的细微横/纵分隔线
            "QTableView::item{ border-bottom: 1px solid rgba(0,0,0,0.06); border-right: 1px solid rgba(0,0,0,0.04); }"
        )

        table_container.addWidget(self.table)

        # 提高中部区域的最小高度，避免按钮和表格被压扁
        table_widget = QtWidgets.QWidget()
        table_widget.setLayout(table_container)
        table_widget.setMinimumHeight(260)
        main_layout.addWidget(table_widget, 2)  # 上部约 2/3

        # 底部区域：仅保留请求/响应原始数据，占 1/3
        raw_group = QtWidgets.QGroupBox("请求/响应原始数据")
        raw_layout = QtWidgets.QVBoxLayout(raw_group)
        font = QtGui.QFont("Consolas", 10)
        self.raw_text = QtWidgets.QTextEdit()
        self.raw_text.setPlaceholderText("请求和响应原始数据将在这里显示...")
        self.raw_text.setFont(font)
        self.raw_text.setReadOnly(True)
        raw_layout.addWidget(self.raw_text)
        main_layout.addWidget(raw_group, 1)

        # 信号转发（仅界面层）
        self.ecu_map_btn.clicked.connect(self.ecu_map_import_requested.emit)
        self.dpt_import_btn.clicked.connect(self.dpt_import_requested.emit)
        self.read_btn.clicked.connect(self.read_requested.emit)
        self.write_btn.clicked.connect(self.write_requested.emit)
        self.add_btn.clicked.connect(self.add_row_requested.emit)
        self.remove_btn.clicked.connect(self.remove_row_requested.emit)
        self.up_btn.clicked.connect(self.move_up_requested.emit)
        self.down_btn.clicked.connect(self.move_down_requested.emit)

        # 表格事件交给 controller，view 只做信号透传
        self.table.cellClicked.connect(self.cell_clicked.emit)
        self.table.cellDoubleClicked.connect(self.cell_double_clicked.emit)

        # 初始布局：延迟应用列宽以便字体度量和视口尺寸可用
        # 使用 singleShot 在事件循环处理完布局后运行一次，防止初始尺寸过窄并确保表头可见
        QtCore.QTimer.singleShot(0, lambda: self._apply_column_widths(force=True))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # 尽量保留用户调整的列宽，但确保满足最小宽度
        self._apply_column_widths()
        # 如果 controller 在视图显示前请求了显式像素宽度，在 resize 时应用
        try:
            if getattr(self, "_pending_pixel_widths", None):
                if self.table.viewport().width() > 0:
                    pixels = self._pending_pixel_widths
                    self._pending_pixel_widths = None
                    self.set_column_pixel_widths(pixels)
        except Exception:
            pass

    def _apply_column_widths(self, force: bool = False) -> None:
        if not hasattr(self, "table"):
            return
        header = self.table.horizontalHeader()
        # 使用视口宽度（可见区域）计算可用的水平空间
        total_width = max(1, self.table.viewport().width())
        # 使用可配置的权重（controller 可更新以匹配设计稿）
        weights = getattr(self, "_column_weights", [1, 8, 3, 2, 4, 4, 10])
        # 使用表头字体度量准确计算表头文本宽度
        fm = header.fontMetrics()
        # 从表头文本计算每列的最小宽度
        header_mins = []
        for i, w in enumerate(weights):
            header_text = self.table.horizontalHeaderItem(i).text() if self.table.horizontalHeaderItem(i) else ""
            # 增加填充以降低表头被截断的概率（保守处理）
            header_min = fm.horizontalAdvance(header_text) + 36
            # 如果表头文本较长，给予额外填充
            if len(header_text) > 12:
                header_min += 24
            # 针对 DiagnosticSession(4) 和 SecurityAccess(5) 的额外最小保护
            if i in (4, 5):
                header_min = max(header_min, 150)
            if i == 0:  # 复选框列需要稍大一点的最小宽度
                header_min = max(header_min, 40)

            # 如果 controller 提供了显式的像素最小值，则应用
            try:
                pix_mins = getattr(self, "_pixel_mins", None)
                if pix_mins and len(pix_mins) == self.table.columnCount():
                    header_min = max(header_min, int(pix_mins[i]))
            except Exception:
                pass

            header_mins.append(header_min)

        # 设置保守的最小分区尺寸以防止 Qt 强制过小
        try:
            header.setMinimumSectionSize(24)
        except Exception:
            pass

        minimal_total = sum(header_mins)

        # 如果视口太窄以致无法容纳所有最小宽度，则按最小宽度分配并允许滚动
        if total_width < minimal_total:
            for i, header_min in enumerate(header_mins):
                header.resizeSection(i, header_min)
            header.setStretchLastSection(False)
            # 保持之前设置的水平滚动行为
            return

        # 否则按权重计算目标宽度并确保每列 >= 最小值
        n = len(weights)

        # 策略：为列 0..n-2 保留最小宽度，让最后一列吸收剩余空间以填满视口
        widths = [int(header_mins[i]) for i in range(n)]

        sum_except_last = sum(widths[:-1])
        remaining = total_width - sum_except_last
        # 最后一列至少为其 header_min，否则吸收剩余空间
        last_min = int(header_mins[-1])
        last_width = max(last_min, remaining)
        widths[-1] = last_width

        # 应用计算出的宽度并让最后一列以 Stretch 模式吸收调整
        try:
            last_idx = self.table.columnCount() - 1
            # 保持其他列为交互式，以便用户可以拖动它们
            for i in range(last_idx):
                header.setSectionResizeMode(i, QtWidgets.QHeaderView.Interactive)
            header.setSectionResizeMode(last_idx, QtWidgets.QHeaderView.Stretch)
        except Exception:
            header.setStretchLastSection(True)

        for i, w in enumerate(widths):
            header.resizeSection(i, int(w))


    def set_column_weights(self, weights):
        """允许外部（controller）设置列比例，立即应用一次最小/权重宽度。

        weights: 可迭代对象，长度应为列数（7）。
        """
        if not weights or len(weights) != self.table.columnCount():
            return
        try:
            self._column_weights = list(float(w) for w in weights)
        except Exception:
            return
        # 立即应用，但除非用户宽度过小，否则不要覆盖用户调整
        self._apply_column_widths(force=True)

    def set_column_pixel_widths(self, pixels):
        """直接按像素设置每列初始宽度（长度需与列数相同）。

        说明：这个方法用于在首次展示时精确匹配设计稿/截图的像素布局。
        后续用户调整仍然允许，但首次布局会参考这些像素值。
        行为：前 N-1 列按提供像素作为最小宽度设置；最后一列设为给定最小值并启用 Stretch
        以填充剩余空间（保证最小为 pixels[-1]）。
        """
        if not pixels or len(pixels) != self.table.columnCount():
            return
        # 记住像素最小值，以便 _apply_column_widths 在 resize 时能遵守
        try:
            self._pixel_mins = [max(0, int(p)) for p in pixels]
        except Exception:
            self._pixel_mins = None

        # 如果表格尚未完成布局（例如被很早调用），缓存并在 resizeEvent 中应用
        try:
            if self.table.viewport().width() <= 0:
                self._pending_pixel_widths = list(pixels)
                return
        except Exception:
            self._pending_pixel_widths = list(pixels)
            return

        try:
            header = self.table.horizontalHeader()

            # 确保所有列都是交互式，以便用户拖动调整
            for i in range(self.table.columnCount()):
                header.setSectionResizeMode(i, QtWidgets.QHeaderView.Interactive)

            # 将提供的像素值作为初始列宽应用
            for i, p in enumerate(pixels):
                try:
                    p_int = max(0, int(p))
                    header.resizeSection(i, p_int)
                except Exception:
                    pass

            # 对最后一列：确保它至少为提供的最小值并以 Stretch 填充剩余空间
            last_idx = self.table.columnCount() - 1
            min_last = max(0, int(pixels[-1]))
            try:
                # 将最后一列设置为 Stretch 模式以吸收剩余空间
                header.setSectionResizeMode(last_idx, QtWidgets.QHeaderView.Stretch)
                # 确保其初始大小至少为请求的最小值
                if header.sectionSize(last_idx) < min_last:
                    header.resizeSection(last_idx, min_last)
            except Exception:
                # 回退：启用传统的 Stretch 标志
                header.setStretchLastSection(True)

        except Exception:
            pass

        # 确保存储的像素最小值���被基于权重的布局使用
        try:
            # 如果表格已有有效视口，重新运行 _apply_column_widths
            if getattr(self, "_pixel_mins", None) and self.table.viewport().width() > 0:
                # 强制重算，以便尊重每列存储的最小值
                self._apply_column_widths(force=True)
        except Exception:
            pass

    def build_row_widgets(self, row: int):
        """仅做一行基础单元格的初始化，不再创建嵌套控件。"""
        chk = QtWidgets.QTableWidgetItem()
        chk.setFlags(chk.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
        # 将复选框居中，使左右内边距视觉均衡
        chk.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(row, 0, chk)

        # Description 单元格：可编辑并使用 FullCellDelegate
        desc_item = QtWidgets.QTableWidgetItem("")
        desc_item.setFlags(desc_item.flags() | Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsEditable)
        self.table.setItem(row, 1, desc_item)

        did_item = QtWidgets.QTableWidgetItem("")
        did_item.setFlags(did_item.flags() | Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsEditable)
        self.table.setItem(row, 2, did_item)

    def get_value_widget(self, row: int) -> Optional[ValueCellWidget]:
        # Value 列不再使用嵌入控件，返回 None 以兼容旧用法
        return None

    def focus_value_editor(self, row: int, select_all: bool = False) -> None:
        # 在进入编辑后，尝试对当前焦点的 QLineEdit 编辑器全选文本
        editor = self.table.focusWidget()
        if isinstance(editor, QtWidgets.QLineEdit):
            if select_all:
                editor.selectAll()
            editor.setFocus()

    def eventFilter(self, obj, event):
        # 仅处理 table.viewport() 的鼠标事件：在 Value 列按钮上显示 tooltip 与手形光标
        try:
            if obj is not getattr(self, 'table', None) and obj is not getattr(self, 'table', None) and obj is not None:
                # we only care about the table viewport
                pass
            if obj is self.table.viewport():
                ev_type = event.type()
                # 鼠标移动：判断是否在 Value 列按钮区域
                if ev_type == QtCore.QEvent.MouseMove:
                    try:
                        pos = event.pos()
                        idx = self.table.indexAt(pos)
                        if idx.isValid() and idx.column() == 6:
                            rect = self.table.visualRect(idx)
                            try:
                                btn_rect = ValueButtonDelegate.button_rect_from_cell(rect)
                            except Exception:
                                btn_rect = QtCore.QRect()
                            if btn_rect.contains(pos):
                                try:
                                    self.table.viewport().setCursor(QtGui.QCursor(Qt.PointingHandCursor))
                                except Exception:
                                    pass
                                # 显示 tooltip（只在位置变化时更新，避免快速闪烁）
                                try:
                                    gpos = self.table.viewport().mapToGlobal(pos)
                                    if getattr(self, '_last_vbtn_tip_pos', None) != gpos:
                                        QtWidgets.QToolTip.showText(gpos, "DPT解析结果", self.table.viewport())
                                        self._last_vbtn_tip_pos = gpos
                                except Exception:
                                    pass
                            else:
                                try:
                                    self.table.viewport().setCursor(QtGui.QCursor(Qt.ArrowCursor))
                                except Exception:
                                    pass
                                QtWidgets.QToolTip.hideText()
                                self._last_vbtn_tip_pos = None
                        else:
                            try:
                                self.table.viewport().setCursor(QtGui.QCursor(Qt.ArrowCursor))
                            except Exception:
                                pass
                            QtWidgets.QToolTip.hideText()
                            self._last_vbtn_tip_pos = None
                    except Exception:
                        pass
                    # Let the event continue so selection/edit behavior is preserved
                    return False

                # 鼠标离开 viewport：恢复光标并隐藏 tooltip
                if ev_type == QtCore.QEvent.Leave:
                    try:
                        self.table.viewport().setCursor(QtGui.QCursor(Qt.ArrowCursor))
                        QtWidgets.QToolTip.hideText()
                    except Exception:
                        pass
                    self._last_vbtn_tip_pos = None
                    return False
        except Exception:
            pass
        return super().eventFilter(obj, event)


class ValueButtonDelegate(FullCellDelegate):
    """在 Value 列绘制一个位于最右侧的方形按钮并拦截点击。"""

    def __init__(self, table: QtWidgets.QTableWidget, clicked_callback=None):
        super().__init__(table)
        self._table = table
        self._clicked_callback = clicked_callback

    @staticmethod
    def button_rect_from_cell(cell_rect: QtCore.QRect) -> QtCore.QRect:
        size = max(24, cell_rect.height())
        left = cell_rect.right() - size + 1
        if left < cell_rect.left():
            left = cell_rect.left()
        return QtCore.QRect(left, cell_rect.top(), size, cell_rect.height())

    def createEditor(self, parent, option, index):
        # 复用 FullCellDelegate 的创建逻辑以获得与 DID 相同的编辑器外观
        try:
            editor = super().createEditor(parent, option, index)
        except Exception:
            editor = QtWidgets.QLineEdit(parent)
            editor.setFrame(False)
        # 保证编辑器不会覆盖右侧按钮（geometry 在 updateEditorGeometry 中限制）
        return editor

    def updateEditorGeometry(self, editor, option, index):
        # 将编辑器限制在不包含按钮的文本区域
        btn_rect = self.button_rect_from_cell(option.rect)
        text_rect = QtCore.QRect(option.rect.left(), option.rect.top(), max(0, option.rect.width() - btn_rect.width()), option.rect.height())
        # 一点内边距视觉更好
        text_rect = text_rect.adjusted(2, 1, -2, -1)
        editor.setGeometry(text_rect)
        try:
            editor.setFixedHeight(option.rect.height())
        except Exception:
            pass

    def paint(self, painter, option, index):
        # 将文本绘制区域缩小，不要被右侧按钮覆盖
        btn_rect = self.button_rect_from_cell(option.rect)
        text_rect = QtCore.QRect(option.rect.left(), option.rect.top(), max(0, option.rect.width() - btn_rect.width()), option.rect.height())
        opt2 = QtWidgets.QStyleOptionViewItem(option)
        opt2.rect = text_rect
        super().paint(painter, opt2, index)
        # 再在最右侧绘制一个与单元格高度一致的方形按钮（只作视觉与点击区域）
        opt = QtWidgets.QStyleOptionButton()
        opt.rect = btn_rect
        try:
            opt.state = QtWidgets.QStyle.State_Enabled | QtWidgets.QStyle.State_Raised
        except Exception:
            pass
        opt.text = "..."
        try:
            QtWidgets.QApplication.style().drawControl(QtWidgets.QStyle.CE_PushButton, opt, painter, option.widget)
        except Exception:
            painter.save()
            painter.setPen(QtGui.QPen(QtGui.QColor('#CBD5F5')))
            painter.drawRect(opt.rect)
            painter.drawText(opt.rect, Qt.AlignCenter, opt.text)
            painter.restore()

    def editorEvent(self, event, model, option, index):
        # 处理 ToolTip 与鼠标移动以显示提示并改变光标
        ev_type = event.type()
        try:
            btn_rect = self.button_rect_from_cell(option.rect)
        except Exception:
            btn_rect = QtCore.QRect()

        # 鼠标移动：在按钮上显示手形指针
        if ev_type == QtCore.QEvent.MouseMove:
            try:
                pos = event.pos()
                if btn_rect.contains(pos):
                    try:
                        self._table.viewport().setCursor(QtGui.QCursor(Qt.PointingHandCursor))
                    except Exception:
                        pass
                else:
                    try:
                        self._table.viewport().setCursor(QtGui.QCursor(Qt.ArrowCursor))
                    except Exception:
                        pass
            except Exception:
                pass
            # 让父类继续处理（以保持选择行为）
            return super().editorEvent(event, model, option, index)

        # ToolTip 事件：显示自定义提示文本
        if ev_type == QtCore.QEvent.ToolTip:
            try:
                pos = event.pos()
                global_pos = self._table.viewport().mapToGlobal(pos)
                if btn_rect.contains(pos):
                    QtWidgets.QToolTip.showText(global_pos, "DPT解析结果", self._table.viewport())
                    return True
            except Exception:
                pass
            return super().editorEvent(event, model, option, index)

        # 鼠标按下/释放：拦截按钮点击
        if ev_type in (QtCore.QEvent.MouseButtonPress, QtCore.QEvent.MouseButtonRelease):
            try:
                pos = event.pos()
            except Exception:
                return False
            if btn_rect.contains(pos):
                if ev_type == QtCore.QEvent.MouseButtonRelease and callable(self._clicked_callback):
                    try:
                        self._clicked_callback(index)
                    except Exception:
                        pass
                return True

        return super().editorEvent(event, model, option, index)
