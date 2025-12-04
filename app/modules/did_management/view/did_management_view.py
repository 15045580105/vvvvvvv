from PyQt5 import QtWidgets, QtGui, QtCore
from PyQt5.QtCore import Qt

from app.common.ui.widgets import ModernButton
from app.presentation.views.base_view import BaseView


class FullCellDelegate(QtWidgets.QStyledItemDelegate):
    """A delegate that provides a QLineEdit editor sized to the entire cell.

    仅负责“整格编辑”的无边框输入框，不包含任何业务逻辑。
    """

    def createEditor(self, parent, option, index):
        editor = QtWidgets.QLineEdit(parent)
        editor.setFrame(False)
        editor.setStyleSheet("border: none; padding: 0px; margin: 0px; background: transparent;")
        editor.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        editor.setContentsMargins(0, 0, 0, 0)
        editor.setTextMargins(0, 0, 0, 0)
        if parent is not None:
            try:
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
        editor.setGeometry(option.rect)
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
        for text in self._get_items(index):
            editor.addItem(text)
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
        editor.setGeometry(option.rect)


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
        """构建 DID 界面布局：上方控制区 + DID 表格 + 请求/响应原始数据。"""
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setSpacing(4)
        main_layout.setContentsMargins(4, 4, 4, 4)

        # 顶部控制条：ECU 地址表导入 + DPT 导入 + 表格操作 + 读取/写入（全部放在同一行）
        ctl = QtWidgets.QHBoxLayout()
        ctl.setSpacing(4)

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
            b.setFixedSize(24, 32)
            ctl.addWidget(b)

        # 读取/写入 放在最右侧
        ctl.addStretch()
        self.read_btn = ModernButton("读取", "#0EA5E9", "")
        self.write_btn = ModernButton("写入", "#F97316", "")
        self.read_btn.setFixedWidth(60)
        self.write_btn.setFixedWidth(60)
        ctl.addWidget(self.read_btn)
        ctl.addWidget(self.write_btn)

        main_layout.addLayout(ctl)

        # 中间区域：DID 表格
        table_container = QtWidgets.QVBoxLayout()
        table_container.setSpacing(2)

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
        header = self.table.horizontalHeader()
        # 使用自适应 + 最后一列拉伸，配合 resizeEvent 中的比例控制
        header.setSectionResizeMode(QtWidgets.QHeaderView.Fixed)
        header.setStretchLastSection(True)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        # 编辑触发交给 controller 控制
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        # 行高稍微大一点，看起来更接近截图
        self.table.verticalHeader().setDefaultSectionSize(26)
        # 让表格在容器中尽量占满空间
        self.table.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)

        table_container.addWidget(self.table)

        # 提高中部区域的最小高度，避免按钮和表格被压扁
        table_widget = QtWidgets.QWidget()
        table_widget.setLayout(table_container)
        table_widget.setMinimumHeight(220)
        main_layout.addWidget(table_widget, 2)  # 上部约 2/3

        # 底部区域：仅保留请求/响应原始数据，占 1/3
        raw_group = QtWidgets.QGroupBox("请求/响应原始数据")
        raw_layout = QtWidgets.QVBoxLayout(raw_group)
        font = QtGui.QFont("Consolas", 9)
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

        self._apply_column_widths()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_column_widths()

    def _apply_column_widths(self) -> None:
        if not hasattr(self, "table"):
            return
        header = self.table.horizontalHeader()
        total_width = max(1, self.table.viewport().width())
        weights = [1, 6, 3, 3, 4, 4, 8]
        total = sum(weights)
        for i, w in enumerate(weights):
            header.resizeSection(i, int(total_width * (w / total)))

    def build_row_widgets(self, row: int):
        """仅做一行基础单元格的初始化，不再创建嵌套控件。"""
        chk = QtWidgets.QTableWidgetItem()
        chk.setFlags(chk.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
        self.table.setItem(row, 0, chk)

        did_item = QtWidgets.QTableWidgetItem("")
        did_item.setFlags(did_item.flags() | Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsEditable)
        self.table.setItem(row, 2, did_item)

        value_item = QtWidgets.QTableWidgetItem("")
        value_item.setFlags(value_item.flags() | Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsEditable)
        self.table.setItem(row, 6, value_item)

        # 兼容旧接口，返回值不再使用
        return None, None, None, None, None
