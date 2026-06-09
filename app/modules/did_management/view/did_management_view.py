from typing import Optional
from datetime import datetime
from PyQt5 import QtWidgets, QtGui, QtCore
from PyQt5.QtCore import Qt

from app.common.log.operation_log_manager import OperationLogManager
from app.common.ui.widgets import ModernButton
from app.presentation.views.base_view import BaseView
from app.modules.ecu_initialization.view.ecu_initialization_view import ECUInitView
from app.common.ui.log_splitter import LogAreaSplitter
from app.common.ui.log_panel import LogPanelBuilder


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


class DIDTableWidget(QtWidgets.QTableWidget):
    """表格控件"""

    def __init__(self, parent=None):
        super().__init__(parent)
        # Disable drag and drop
        self.setDragEnabled(False)
        self.setAcceptDrops(False)
        self.setDragDropMode(QtWidgets.QAbstractItemView.NoDragDrop)

        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        # self.setDropIndicatorShown(True)

    def mousePressEvent(self, event):
        # 恢复默认的 mousePressEvent，不再拦截
        # 如果需要保留特定的复选框判定逻辑以优化点击体验（例如点文字也能勾选），可以保留
        # 但标准 QTableWidget 对 Checkbox 列的点击处理通常是很好的
        # 用户之前的抱怨主要是因为 setDragEnabled(True) 导致的冲突
        # 现在禁用了 Drag，标准的点击处理应该足够
        super().mousePressEvent(event)

class CheckBoxHeader(QtWidgets.QHeaderView):
    checkBoxClicked = QtCore.pyqtSignal(int, bool)

    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self.checkBoxStates = {0: False, 4: False}
        self._sort_logical_index = -1
        self._sort_order = Qt.AscendingOrder

    def setCustomSort(self, logical_index: int, order: Qt.SortOrder):
        """设置自定义排序状态并重绘表头。"""
        self._sort_logical_index = logical_index
        self._sort_order = order
        self.viewport().update()

    def paintSection(self, painter, rect, logicalIndex):
        painter.save()
        super().paintSection(painter, rect, logicalIndex)
        painter.restore()

        # 绘制排序指示器 (如果当前列是排序列)
        if logicalIndex == self._sort_logical_index:
            painter.save()

            # 箭头配置
            arrow_size = 4
            margin_right = 8

            # 如果该列同时有 CheckBox，可能需要避让 (Col 0 and Col 4)
            # Col 0 is centered checkbox usually, Col 4 is left aligned.
            # Usually sort indicator is on the right, text on left/center.

            cx = rect.right() - margin_right - arrow_size
            cy = rect.center().y()

            # 使用醒目的颜色 (例如 #6366F1 / Indigo 或 #3B82F6 / Blue)
            # 这里使用深灰色以匹配通用风格，或者强调色
            color = QtGui.QColor("#4F46E5")
            painter.setBrush(color)
            painter.setPen(QtCore.Qt.NoPen)
            painter.setRenderHint(QtGui.QPainter.Antialiasing)

            path = QtGui.QPainterPath()
            if self._sort_order == Qt.AscendingOrder:
                # 向上箭头
                path.moveTo(cx, cy - arrow_size)
                path.lineTo(cx - arrow_size, cy + arrow_size)
                path.lineTo(cx + arrow_size, cy + arrow_size)
            else:
                # 向下箭头
                path.moveTo(cx, cy + arrow_size)
                path.lineTo(cx - arrow_size, cy - arrow_size)
                path.lineTo(cx + arrow_size, cy - arrow_size)

            path.closeSubpath()
            painter.drawPath(path)
            painter.restore()

        if logicalIndex in self.checkBoxStates:
            style = self.style()
            option = QtWidgets.QStyleOptionViewItem()
            option.initFrom(self)

            # 获取适应 DPI 的尺寸
            chk_width = style.pixelMetric(QtWidgets.QStyle.PM_IndicatorWidth, option, self)
            chk_height = style.pixelMetric(QtWidgets.QStyle.PM_IndicatorHeight, option, self)

            # Col 0: Center. Col 4: Left (with padding)
            if logicalIndex == 0:
                x = rect.x() + (rect.width() - chk_width) // 2
            else:                x = rect.x() + 7 # Align with cell padding (6px) + margin

            y = rect.y() + (rect.height() - chk_height) // 2

            option.rect = QtCore.QRect(x, y, chk_width, chk_height)
            option.state = QtWidgets.QStyle.State_Enabled | QtWidgets.QStyle.State_Active
            if self.checkBoxStates[logicalIndex]:
                option.state |= QtWidgets.QStyle.State_On
                option.checkState = Qt.Checked
            else:
                option.state |= QtWidgets.QStyle.State_Off
                option.checkState = Qt.Unchecked

            style.drawPrimitive(QtWidgets.QStyle.PE_IndicatorItemViewItemCheck, option, painter, self)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            logicalIndex = self.logicalIndexAt(event.pos())
            if logicalIndex in self.checkBoxStates:
                headerPos = self.sectionViewportPosition(logicalIndex)
                sec_width = self.sectionSize(logicalIndex)

                style = self.style()
                option = QtWidgets.QStyleOptionViewItem()
                option.initFrom(self)

                chk_width = style.pixelMetric(QtWidgets.QStyle.PM_IndicatorWidth, option, self)
                chk_height = style.pixelMetric(QtWidgets.QStyle.PM_IndicatorHeight, option, self)

                if logicalIndex == 0:
                    x = headerPos + (sec_width - chk_width) // 2
                else:
                    x = headerPos + 7

                y = (self.height() - chk_height) // 2

                # 增加一点点击区域容错
                checkRect = QtCore.QRect(x - 2, y - 2, chk_width + 4, chk_height + 4)

                if checkRect.contains(event.pos()):
                    self.checkBoxStates[logicalIndex] = not self.checkBoxStates[logicalIndex]
                    self.viewport().update()
                    self.checkBoxClicked.emit(logicalIndex, self.checkBoxStates[logicalIndex])
                    return
        super().mousePressEvent(event)


class DIDView(BaseView):
    value_detail_requested = QtCore.pyqtSignal(int)
    read_requested = QtCore.pyqtSignal()
    write_requested = QtCore.pyqtSignal()
    add_row_requested = QtCore.pyqtSignal()
    remove_row_requested = QtCore.pyqtSignal()
    move_up_requested = QtCore.pyqtSignal()
    move_down_requested = QtCore.pyqtSignal()
    move_top_requested = QtCore.pyqtSignal()
    cell_clicked = QtCore.pyqtSignal(int, int)
    cell_double_clicked = QtCore.pyqtSignal(int, int)
    ecu_init_requested = QtCore.pyqtSignal()
    clear_requested = QtCore.pyqtSignal()

    def setup_ui(self):
        # 存储待应用的像素宽度（在首次布局完成后应用）
        self._pending_pixel_widths = None
        self._preferred_log_height = 300
        self._user_resized_log = False
        """构建 DID 界面布局：上方控制区 + DID 表格 + 请求/响应原始数据。"""
        self.main_layout = QtWidgets.QVBoxLayout(self)
        self.main_layout.setSpacing(6)
        self.main_layout.setContentsMargins(6, 6, 6, 6)

        # 顶部控制条：恢复原样子进行布局，只修正按钮挤压
        self.ctl = QtWidgets.QHBoxLayout()
        self.ctl.setSpacing(6)

        self.ecu_init_btn = ModernButton("ECU初始化", "#8B5CF6", "🔧")
        self.ecu_init_btn.setToolTip("点击切换到 ECU 初始化界面")
        self.ecu_init_btn.setFixedWidth(136)
        self.ecu_init_btn.setFixedHeight(36)
        self.ecu_init_btn.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.ctl.addWidget(self.ecu_init_btn)

        self.add_btn = ModernButton("+", "#22C55E", "")
        self.add_btn.setToolTip("添加一行新的 DID")
        self.remove_btn = ModernButton("-", "#EF4444", "")
        self.remove_btn.setToolTip("删除当前选中的行")
        self.up_btn = ModernButton("↑", "#6B7280", "")
        self.up_btn.setToolTip("上移选中行")
        self.down_btn = ModernButton("↓", "#6B7280", "")
        self.down_btn.setToolTip("下移选中行")
        self.top_btn = ModernButton("⇈", "#6B7280", "")
        self.top_btn.setToolTip("选中行置顶")

        self.add_btn.setFixedSize(44, 36)
        self.remove_btn.setFixedSize(44, 36)
        self.up_btn.setFixedSize(44, 36)
        self.down_btn.setFixedSize(44, 36)
        self.top_btn.setFixedSize(44, 36)
        for b in (self.add_btn, self.remove_btn, self.up_btn, self.down_btn, self.top_btn):
            b.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
            self.ctl.addWidget(b)

        self.search_input = QtWidgets.QLineEdit()
        self.search_input.setPlaceholderText("搜索 DID...")
        self.search_input.setToolTip("输入 DID 号或描述进行搜索")
        self.search_input.setFixedWidth(160)
        self.search_input.setMinimumWidth(120)
        self.search_input.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.search_input.setStyleSheet("QLineEdit { border: 1px solid #E5E7EB; border-radius: 4px; padding: 4px; }")
        self.ctl.addWidget(self.search_input)

        self.search_btn = ModernButton("🔍", "#6B7280", "")
        self.search_btn.setToolTip("执行搜索")
        self.search_btn.setFixedSize(44, 36)
        self.search_btn.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.ctl.addWidget(self.search_btn)

        self.ctl.addStretch()
        self.read_btn = ModernButton("读取", "#0EA5E9", "")
        self.read_btn.setToolTip("读取勾选 DID 的值")
        self.write_btn = ModernButton("写入", "#F97316", "")
        self.write_btn.setToolTip("写入值到勾选的 DID")
        self.clear_btn = ModernButton("清除", "#EF4444", "")
        self.clear_btn.setToolTip("清除所有值和日志")
        for btn in (self.read_btn, self.write_btn, self.clear_btn):
            btn.setFixedWidth(86)
            btn.setFixedHeight(36)
            btn.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
            self.ctl.addWidget(btn)

        self.main_layout.addLayout(self.ctl)

        # Splitter for resizable log window
        self.splitter = LogAreaSplitter(self, min_log_height=150, max_log_ratio=0.8)
        self.main_layout.addWidget(self.splitter)

        # 使用 QStackedWidget 来切换 DID 表格和 ECU 初始化界面
        self.stack = QtWidgets.QStackedWidget()

        # --- 页面 1: DID 表格 ---
        table_widget = QtWidgets.QWidget()
        table_container = QtWidgets.QVBoxLayout(table_widget)
        table_container.setContentsMargins(0, 0, 0, 0)
        table_container.setSpacing(4)

        # DID 表格
        self.table = DIDTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "",  # 选中
            "Description",
            "DID",
            "STR/HEX",
            "Follow DPT",
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
        header = CheckBoxHeader(Qt.Horizontal, self.table)
        self.table.setHorizontalHeader(header)
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
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.table.setAlternatingRowColors(True)

        # Enable vertical header (row numbers) and style it
        self.table.verticalHeader().setVisible(True)
        self.table.verticalHeader().setDefaultSectionSize(34)
        # Ensure minimum width for visibility on high DPI
        self.table.verticalHeader().setMinimumWidth(40)

        # 编辑触发交给 controller 控制
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        # 让表格在容器中尽量占满空间
        self.table.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)

        # 更明显的网格线与内边距，使复选框左右间距一致
        self.table.setShowGrid(True)
        self.table.setGridStyle(QtCore.Qt.SolidLine)
        # 保持原有风格但增强网格线（不改动表头样式）
        # 增加 indicator 样式以增强拖拽提示可见性
        self.table.setStyleSheet(
            "QTableWidget::item{ padding-left:6px; padding-right:6px; }"
            "QTableWidget::item:selected{ background: #bfdbfe; }"
            # 与现有界面风格一致的细微横/纵分隔线
            "QTableView::item{ border-bottom: 1px solid rgba(0,0,0,0.06); border-right: 1px solid rgba(0,0,0,0.04); }"
            # Style vertical header
            "QHeaderView::section:vertical { background-color: #F3F4F6; border: none; border-right: 1px solid #E5E7EB; padding-right: 4px; font-family: 'Segoe UI', sans-serif; font-size: 11px; color: #6B7280; }"
        )

        # Enable mouse tracking to support delegate tooltips (e.g. Value column button)
        self.table.setMouseTracking(True)
        self.table.viewport().setMouseTracking(True)

        table_container.addWidget(self.table)
        self.stack.addWidget(table_widget) # Index 0

        # --- 页面 2: ECU 初始化界面 ---
        self.ecu_init_view = ECUInitView()
        self.stack.addWidget(self.ecu_init_view) # Index 1

        # 底部区域：仅保留请求/响应原始数据，占 1/3
        raw_group = QtWidgets.QGroupBox("操作日志")
        raw_layout = QtWidgets.QVBoxLayout(raw_group)
        raw_layout.setContentsMargins(8, 12, 8, 8)
        font = QtGui.QFont("Consolas", 10)
        self.raw_text = QtWidgets.QTextEdit()
        self.raw_text.setPlaceholderText("请求和响应原始数据将在这里显示...")
        self.raw_text.setFont(font)
        self.raw_text.setReadOnly(True)
        self.raw_text.setMinimumHeight(0)
        LogPanelBuilder.attach_search(raw_layout, self.raw_text)
        raw_layout.addWidget(self.raw_text)

        self.splitter.set_panels(self.stack, raw_group, initial_log_height=300)
        try:
            self.splitter.splitterMoved.connect(self._on_log_splitter_moved)
        except Exception:
            pass

        # 信号转发（仅界面层）
        self.read_btn.clicked.connect(self.read_requested.emit)
        self.write_btn.clicked.connect(self.write_requested.emit)
        self.clear_btn.clicked.connect(self.clear_requested.emit)
        self.add_btn.clicked.connect(self.add_row_requested.emit)
        self.remove_btn.clicked.connect(self.remove_row_requested.emit)
        self.up_btn.clicked.connect(self.move_up_requested.emit)
        self.down_btn.clicked.connect(self.move_down_requested.emit)
        self.top_btn.clicked.connect(self.move_top_requested.emit)
        self.ecu_init_btn.clicked.connect(self.toggle_ecu_init_panel)

        # 表格事件交给 controller，view 只做信号透传
        self.table.cellClicked.connect(self.cell_clicked.emit)
        self.table.cellDoubleClicked.connect(self.cell_double_clicked.emit)

        # 初始布局：延迟应用列宽以便字体度量和视口尺寸可用
        # 使用 singleShot 在事件循环处理完布局后运行一次，防止初始尺寸过窄并确保表头可见
        QtCore.QTimer.singleShot(0, lambda: self._apply_responsive_layout(force=True))

    def toggle_ecu_init_panel(self):
        """切换 ECU 初始化面板的显示/隐藏状态（切换 Stack 页面）。"""
        if self.stack.currentIndex() == 0:
            self.stack.setCurrentIndex(1)
            self.ecu_init_btn.setText("返回DID列表")
            self.ecu_init_btn.color = QtGui.QColor("#6B7280") # Gray for back
            self.ecu_init_btn.update_style()
        else:
            self.stack.setCurrentIndex(0)
            self.ecu_init_btn.setText("ECU初始化")
            self.ecu_init_btn.color = QtGui.QColor("#8B5CF6") # Original purple
            self.ecu_init_btn.update_style()

    def append_log(self, message: str):
        """Append message to the raw text log area."""
        OperationLogManager.instance().append_log("DID数据管理", message)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        log_entry = f"[{timestamp}] {message}"

        color = "#374151"
        if "TX:" in message or "TX " in message:
            color = "#2563EB"
        elif "RX:" in message or "RX " in message:
            color = "#059669"
        elif "Error" in message or "失败" in message or "错误" in message or "Fail" in message:
            color = "#DC2626"
        elif "Warning" in message or "警告" in message:
            color = "#D97706"

        log_escaped = log_entry.replace("<", "&lt;").replace(">", "&gt;")
        html_msg = f'<span style="color: {color};">{log_escaped}</span>'

        self.raw_text.append(html_msg)
        self.raw_text.moveCursor(QtGui.QTextCursor.End)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_responsive_layout()

        # Adjust vertical header width to fit row numbers
        try:
            # Calculate required width for the last row number
            row_count = self.table.rowCount()
            if row_count > 0:
                # Get font metrics
                fm = self.table.verticalHeader().fontMetrics()
                # Measure width of the largest number string
                text = str(row_count + 1) # +1 just in case
                width = fm.horizontalAdvance(text) + 20 # Add padding
                # Set width (ensure minimum)
                self.table.verticalHeader().setFixedWidth(max(40, width))
        except Exception:
            pass

    def _scale_button_size(self, button, base_w, base_h, ratio, min_w, max_w, min_h, max_h):
        width = max(min_w, min(max_w, int(base_w * ratio)))
        height = max(min_h, min(max_h, int(base_h * ratio)))
        button.setFixedSize(width, height)

    def _scale_button_width(self, button, base_w, ratio, min_w, max_w):
        width = max(min_w, min(max_w, int(base_w * ratio)))
        button.setFixedWidth(width)

    def _on_log_splitter_moved(self, pos, index):
        try:
            sizes = self.splitter.sizes()
            if len(sizes) > 1:
                self._preferred_log_height = sizes[1]
                self._user_resized_log = True
        except Exception:
            pass

    def _apply_responsive_layout(self, force: bool = False):
        view_width = max(1, self.width())
        bucket = view_width // 80
        if not force and getattr(self, '_last_layout_bucket', None) == bucket:
            self._apply_column_widths()
            return
        self._last_layout_bucket = bucket

        spacing = 4 if view_width < 1500 else 6
        margin = 4 if view_width < 1500 else 6

        self.main_layout.setSpacing(spacing)
        self.main_layout.setContentsMargins(margin, margin, margin, margin)
        self.ctl.setSpacing(spacing)

        # 文字按钮固定，不再参与压缩
        self.ecu_init_btn.setFixedWidth(136)
        self.ecu_init_btn.setFixedHeight(36)
        for btn in (self.read_btn, self.write_btn, self.clear_btn):
            btn.setFixedWidth(86)
            btn.setFixedHeight(36)

        # 这 5 个按钮宽度直接锁定，避免符号显示不全
        self.add_btn.setFixedSize(44, 36)
        self.remove_btn.setFixedSize(44, 36)
        self.up_btn.setFixedSize(44, 36)
        self.down_btn.setFixedSize(44, 36)
        self.top_btn.setFixedSize(44, 36)

        # 搜索区域也给足显示空间，避免占位符和图标被截断
        self.search_btn.setFixedSize(44, 36)
        self.search_input.setFixedWidth(120 if view_width < 1500 else 160)

        try:
            split_sizes = self.splitter.sizes()
            if len(split_sizes) > 1:
                total_h = max(1, sum(split_sizes))
                if self._user_resized_log:
                    desired_log = max(150, min(int(total_h * 0.8), self._preferred_log_height))
                else:
                    desired_log = max(180, min(int(total_h * 0.42), 320))
                self.splitter.setSizes([max(240, total_h - desired_log), desired_log])
        except Exception:
            pass

        self._apply_column_widths(force=True)

    def _apply_column_widths(self, force: bool = False) -> None:
        if not hasattr(self, "table"):
            return
        header = self.table.horizontalHeader()
        # 使用视口宽度（可见区域）计算可用的水平空间
        total_width = max(1, self.table.viewport().width())
        # 使用可配置的权重（controller 可更新以匹配设计稿）
        weights = getattr(self, "_column_weights", [1, 8, 3, 2, 2, 4, 4, 10])
        # 使用表头字体度量准确计算表头文本宽度
        fm = header.fontMetrics()
        # 从表头文本计算每列的最小宽度
        header_mins = []
        for i, w in enumerate(weights):
            header_text = self.table.horizontalHeaderItem(i).text() if self.table.horizontalHeaderItem(i) else ""
            # 增加填充以降低表头被截断的概率（保守处理）
            header_min = fm.horizontalAdvance(header_text) + 36
            if i == 1:
                header_min = max(header_min, 180)
            elif i == 2:
                header_min = max(header_min, 88)
            elif i == 3:
                header_min = max(header_min, 92)
            elif i == 4:
                header_min = max(header_min, 110)
            elif i in (5, 6):
                header_min = max(header_min, 135)
            elif i == 7:
                header_min = max(header_min, 220)
            elif i == 0:
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
        # 仅处理 table.viewport() 的鼠标事件：在 Value 列按钮上显示提示与手形光标
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

    def helpEvent(self, event, view, option, index):
        if not event or not view:
            return False
        if event.type() == QtCore.QEvent.ToolTip:
            try:
                btn_rect = self.button_rect_from_cell(option.rect)
                pos = event.pos() # helpEvent pos is usually relative to view
                # Ensure pos is mapped correctly if needed, but event.pos() for helpEvent
                # is usually viewport coordinates?
                # Actually helpEvent(QHelpEvent) -> pos() is widget relative.
                if btn_rect.contains(pos):
                    QtWidgets.QToolTip.showText(event.globalPos(), "DPT解析结果", view)
                    return True
            except Exception:
                pass
        return super().helpEvent(event, view, option, index)


class ValueDetailDialog(QtWidgets.QDialog):
    """显示 DID 值详细解析结果的对话框。"""

    def __init__(self, parent, parse_result, row_info):
        super().__init__(parent)
        self.setWindowTitle(f"详细解析 - {row_info.did}")
        self.resize(800, 500)
        # 设为模态或非模态取决于需求，这里作为独立窗口显示
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        layout = QtWidgets.QVBoxLayout(self)

        # 顶部信息区
        info_group = QtWidgets.QGroupBox("基本信息")
        info_layout = QtWidgets.QFormLayout(info_group)
        info_layout.addRow("DID:", QtWidgets.QLabel(row_info.did))

        # 优先使用解析结果中的描述，如果没有则使用表格行中的描述
        description = parse_result.description if parse_result and parse_result.description else row_info.description
        info_layout.addRow("描述:", QtWidgets.QLabel(description))

        # 原始值显示（每行32字节，最多4行，悬浮显示全部）
        raw_val = row_info.value if row_info.value else ""

        # 尝试智能分词：如果有空格则按空格分，否则按每2个字符（Hex Byte）分
        if " " in raw_val:
            parts = raw_val.split()
        else:
            parts = [raw_val[i:i+2] for i in range(0, len(raw_val), 2)]

        chunks = []
        if parts:
            # 每32个字节元素合并为一行
            chunks = [" ".join(parts[i:i+32]) for i in range(0, len(parts), 32)]

        full_text = "\n".join(chunks)

        if len(chunks) > 4:
            display_text = "\n".join(chunks[:4]) + "\n..."
        else:
            display_text = full_text

        val_label = QtWidgets.QLabel(display_text)
        val_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        # 设置 tooltip 显示完整内容
        val_label.setToolTip(full_text)

        info_layout.addRow("原始值:", val_label)

        layout.addWidget(info_group)

        # 解析结果表格
        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Byte / Bit", "Function / Name", "Value", "Status / Unit"])

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QtWidgets.QHeaderView.Stretch)

        self.table.setAlternatingRowColors(True)

        # Style vertical header for detail dialog too
        self.table.verticalHeader().setVisible(True)
        self.table.verticalHeader().setDefaultSectionSize(28)
        # self.table.verticalHeader().setFixedWidth(35)
        self.table.setStyleSheet(
            "QHeaderView::section:vertical { background-color: #F3F4F6; border: none; border-right: 1px solid #E5E7EB; padding-right: 4px; font-family: 'Segoe UI', sans-serif; font-size: 11px; color: #6B7280; }"
        )

        layout.addWidget(self.table)

        # 填充表格
        if parse_result:
            # 假设 parse_result.to_table_rows() 返回 [(col1, col2, col3, col4), ...]
            rows = parse_result.to_table_rows()
            self.table.setRowCount(len(rows))
            for r, row_data in enumerate(rows):
                for c, val in enumerate(row_data):
                    val_str = str(val) if val is not None else ""
                    tooltip_str = val_str
                    if c in (2, 3):
                        if " " in val_str:
                            parts = val_str.split(" ")
                            if len(parts) > 15:
                                val_str = " ".join(parts[:15]) + " ..."
                            # 悬浮显示每行最多50个字节
                            tooltip_str = "\n".join([" ".join(parts[i:i+50]) for i in range(0, len(parts), 50)])
                        else:
                            if len(val_str) > 30:
                                val_str = val_str[:30] + "..."
                            # 悬浮显示每行最多100个字符(50个字节)
                            tooltip_str = "\n".join([tooltip_str[i:i+100] for i in range(0, len(tooltip_str), 100)])
                    item = QtWidgets.QTableWidgetItem(val_str)
                    item.setFlags(item.flags() ^ Qt.ItemIsEditable)  # 只读
                    item.setToolTip(tooltip_str) # 悬浮显示完整内容
                    self.table.setItem(r, c, item)

        # 底部按钮
        btn_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        btn_box.rejected.connect(self.close)
        layout.addWidget(btn_box)

    def showEvent(self, event):
        super().showEvent(event)
        parent = self.parent()
        if parent:
            top_level = parent.window()
            if top_level:
                parent_rect = top_level.geometry()
                self.move(
                    parent_rect.x() + (parent_rect.width() - self.width()) // 2,
                    parent_rect.y() + (parent_rect.height() - self.height()) // 2
                )
                return

        # Fallback to screen center
        screen = QtWidgets.QApplication.primaryScreen().geometry()
        self.move(
            (screen.width() - self.width()) // 2,
            (screen.height() - self.height()) // 2
        )
