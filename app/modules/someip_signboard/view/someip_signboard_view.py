from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from PyQt5.QtCore import QAbstractTableModel, QModelIndex, Qt, pyqtSignal
from PyQt5.QtGui import QDragEnterEvent, QDropEvent
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QProgressBar,
    QSplitter,
    QTableView,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from app.common.utils.packet_parser_utils import PacketParserUtils
from app.presentation.views.base_view import BaseView


class PacketTableModel(QAbstractTableModel):
    def __init__(self, headers: Sequence[str], parent=None):
        super().__init__(parent)
        self._headers = list(headers)
        self._packets: List[Dict[str, Any]] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._packets)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._headers)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self._packets):
            return None

        value = self._row_values(self._packets[index.row()])[index.column()]
        if role in (Qt.DisplayRole, Qt.ToolTipRole):
            return str(value)
        if role == Qt.TextAlignmentRole and index.column() in (0, 5):
            return int(Qt.AlignCenter)
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal and 0 <= section < len(self._headers):
            return self._headers[section]
        if orientation == Qt.Vertical:
            return None
        return None

    def reset_packets(self, packets: Sequence[Dict[str, Any]]):
        self.beginResetModel()
        self._packets = list(packets)
        self.endResetModel()

    def append_packets(self, packets: Sequence[Dict[str, Any]]):
        if not packets:
            return
        start = len(self._packets)
        end = start + len(packets) - 1
        self.beginInsertRows(QModelIndex(), start, end)
        self._packets.extend(packets)
        self.endInsertRows()

    def refresh_row(self, row: int):
        if row < 0 or row >= len(self._packets):
            return
        top_left = self.index(row, 0)
        bottom_right = self.index(row, max(0, len(self._headers) - 1))
        self.dataChanged.emit(top_left, bottom_right, [Qt.DisplayRole, Qt.ToolTipRole])

    @staticmethod
    def _row_values(packet: Dict[str, Any]) -> List[str]:
        return [
            str(packet.get("no", "")),
            str(packet.get("timestamp", "")),
            str(packet.get("source", "")),
            str(packet.get("destination", "")),
            str(packet.get("protocol", "")),
            str(packet.get("length", 0)),
            str(packet.get("summary", "")),
        ]


class SomeIpSignboardView(BaseView):
    """Wireshark 风格报文解析页面。"""

    PACKET_LOAD_CHUNK_SIZE = 500
    PACKET_SCROLL_THRESHOLD = 80

    import_requested = pyqtSignal()
    refresh_requested = pyqtSignal()
    search_changed = pyqtSignal(str)
    file_dropped = pyqtSignal(str)
    packet_selected = pyqtSignal(int)
    tree_node_selected = pyqtSignal(object)

    PACKET_HEADERS = ["序号", "时间戳", "源", "目的", "协议", "长度", "摘要"]

    def setup_ui(self):
        self.setAcceptDrops(True)
        self._building_tree = False
        self._updating_table = False
        self._all_packets: List[Dict[str, Any]] = []
        self._loaded_packet_count = 0

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(10)

        root_layout.addWidget(self._create_import_panel())
        root_layout.addWidget(self._create_main_splitter(), 1)

    def _create_import_panel(self):
        frame = QFrame()
        frame.setObjectName("importPanel")
        frame.setStyleSheet(
            "QFrame#importPanel { background:#F8FAFC; border:1px solid #E2E8F0; border-radius:12px; }"
        )

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        hint = QLabel("📂 拖拽 PCAP / 文本十六进制 / 二进制文件到此处，或使用右侧按钮导入")
        hint.setStyleSheet("font-size: 13px; color: #334155; font-weight: 600;")
        layout.addWidget(hint)

        row = QHBoxLayout()
        row.setSpacing(10)

        self.file_path_edit = QLineEdit()
        self.file_path_edit.setReadOnly(True)
        self.file_path_edit.setPlaceholderText("尚未选择文件")
        self.file_path_edit.setStyleSheet(
            "QLineEdit { background:#FFFFFF; border:1px solid #CBD5E1; border-radius:8px; padding:8px 10px; }"
        )

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索协议 / 地址 / 摘要")
        self.search_edit.setFixedWidth(240)
        self.search_edit.setStyleSheet(self.file_path_edit.styleSheet())
        self.search_edit.returnPressed.connect(lambda: self.search_changed.emit(self.search_edit.text()))

        self.import_btn = QPushButton("导入文件")
        self.import_btn.clicked.connect(lambda: self.import_requested.emit())
        self.import_btn.setCursor(Qt.PointingHandCursor)

        self.refresh_btn = QPushButton("重新解析")
        self.refresh_btn.clicked.connect(lambda: self.refresh_requested.emit())
        self.refresh_btn.setCursor(Qt.PointingHandCursor)

        button_style = (
            "QPushButton { background:#2563EB; color:white; border:none; border-radius:8px; padding:8px 14px; font-weight:600; }"
            "QPushButton:hover { background:#1D4ED8; }"
            "QPushButton:disabled { background:#94A3B8; }"
        )
        ghost_style = (
            "QPushButton { background:#FFFFFF; color:#1E293B; border:1px solid #CBD5E1; border-radius:8px; padding:8px 14px; font-weight:600; }"
            "QPushButton:hover { background:#F8FAFC; }"
        )
        self.import_btn.setStyleSheet(button_style)
        self.refresh_btn.setStyleSheet(ghost_style)

        row.addWidget(self.file_path_edit, 1)
        row.addWidget(self.search_edit)
        row.addWidget(self.refresh_btn)
        row.addWidget(self.import_btn)
        layout.addLayout(row)

        self.status_label = QLabel("未加载报文文件")
        self.status_label.setStyleSheet("font-size: 12px; color: #64748B;")

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setStyleSheet(
            "QProgressBar { background:#E2E8F0; border:none; border-radius:6px; height:10px; text-align:center; color:#0F172A; }"
            "QProgressBar::chunk { background:#2563EB; border-radius:6px; }"
        )

        layout.addWidget(self.progress_bar)
        layout.addWidget(self.status_label)
        return frame

    def _create_main_splitter(self):
        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(self._create_packet_table())
        splitter.addWidget(self._create_detail_splitter())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([420, 320])
        return splitter

    def _create_packet_table(self):
        container = QFrame()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        title = QLabel("报文列表")
        title.setStyleSheet("font-size: 15px; font-weight: 700; color: #0F172A;")
        layout.addWidget(title)

        self.packet_table = QTableView()
        self.packet_table_model = PacketTableModel(self.PACKET_HEADERS, self.packet_table)
        self.packet_table.setModel(self.packet_table_model)
        self.packet_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.packet_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.packet_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.packet_table.setAlternatingRowColors(False)
        self.packet_table.verticalHeader().setVisible(False)
        self.packet_table.horizontalHeader().setStretchLastSection(True)
        self.packet_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.packet_table.setColumnWidth(0, 70)
        self.packet_table.setColumnWidth(1, 160)
        self.packet_table.setColumnWidth(2, 150)
        self.packet_table.setColumnWidth(3, 150)
        self.packet_table.setColumnWidth(4, 100)
        self.packet_table.setColumnWidth(5, 80)
        self.packet_table.setColumnWidth(6, 420)
        self.packet_table.setStyleSheet(
            "QTableWidget { background:white; alternate-background-color:#F8FAFC; border:1px solid #E2E8F0; border-radius:10px; gridline-color:#E2E8F0; }"
            "QHeaderView::section { background:#F1F5F9; border:none; border-bottom:1px solid #E2E8F0; padding:8px; color:#334155; font-weight:700; }"
        )
        self.packet_table.selectionModel().selectionChanged.connect(self._emit_packet_selected)
        self.packet_table.verticalScrollBar().valueChanged.connect(self._handle_packet_scroll)
        layout.addWidget(self.packet_table, 1)
        return container

    def _create_detail_splitter(self):
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._create_tree_panel())
        splitter.addWidget(self._create_right_panel())
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([360, 520])
        return splitter

    def _create_tree_panel(self):
        container = QFrame()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        title = QLabel("结构体解析")
        title.setStyleSheet("font-size: 15px; font-weight: 700; color: #0F172A;")
        layout.addWidget(title)

        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderLabels(["字段", "值"])
        self.tree_widget.header().setStretchLastSection(True)
        self.tree_widget.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.tree_widget.setColumnWidth(0, 220)
        self.tree_widget.setStyleSheet(
            "QTreeWidget { background:white; border:1px solid #E2E8F0; border-radius:10px; }"
            "QHeaderView::section { background:#F1F5F9; border:none; border-bottom:1px solid #E2E8F0; padding:8px; color:#334155; font-weight:700; }"
        )
        self.tree_widget.itemSelectionChanged.connect(self._emit_tree_node_selected)
        layout.addWidget(self.tree_widget, 1)
        return container

    def _create_right_panel(self):
        container = QFrame()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        title = QLabel("数据")
        title.setStyleSheet("font-size: 15px; font-weight: 700; color: #0F172A;")
        layout.addWidget(title)

        self.hex_text = QTextEdit()
        self.hex_text.setReadOnly(True)
        self.hex_text.setPlaceholderText("选择左侧结构体节点后，这里显示对应数据")
        self.hex_text.setStyleSheet(
            "QTextEdit { background:white; color:#0F172A; border:1px solid #E2E8F0; border-radius:10px; padding:10px; font-family:'Consolas','Courier New',monospace; font-size:12px; }"
        )
        layout.addWidget(self.hex_text, 1)
        return container

    def set_file_path(self, path: str):
        self.file_path_edit.setText(path or "")

    def set_status_text(self, text: str):
        self.status_label.setText(text or "")

    def set_import_in_progress(self, loading: bool):
        self.import_btn.setEnabled(not loading)
        self.refresh_btn.setEnabled(not loading)
        self.search_edit.setEnabled(not loading)
        self.progress_bar.setVisible(loading)
        if not loading:
            self.progress_bar.setValue(0)

    def update_import_progress(self, value: int, message: str = ""):
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(max(0, min(100, int(value))))
        if message:
            self.status_label.setText(message)

    def set_packets(self, packets: Sequence[Dict[str, Any]], selected_index: int = -1):
        self._all_packets = list(packets)
        self._loaded_packet_count = 0
        self._updating_table = True
        self.packet_table_model.reset_packets([])
        self._load_more_packets(minimum_count=selected_index + 1 if selected_index >= 0 else None)
        if 0 <= selected_index < len(self._all_packets):
            self.packet_table.selectRow(selected_index)
        else:
            self.packet_table.clearSelection()
        self._updating_table = False

    def begin_packet_stream(self):
        self._all_packets = []
        self._loaded_packet_count = 0
        self._updating_table = True
        self.packet_table_model.reset_packets([])
        self.packet_table.clearSelection()
        self._updating_table = False

    def append_packet_batch(self, packets: Sequence[Dict[str, Any]], selected_index: int = -1):
        self.packet_table_model.append_packets(packets)

    def refresh_packet_row(self, row: int):
        self.packet_table_model.refresh_row(row)

    def set_tree_nodes(self, nodes: Sequence[Dict[str, Any]]):
        self._building_tree = True
        self.tree_widget.clear()
        for node in nodes:
            self.tree_widget.addTopLevelItem(self._create_tree_item(node))
        self.tree_widget.expandToDepth(1)

        if self.tree_widget.topLevelItemCount() > 0:
            first_item = self.tree_widget.topLevelItem(0)
            self.tree_widget.setCurrentItem(first_item)
        self._building_tree = False

    def set_data_text(self, text: str):
        self.hex_text.setPlainText(text or "")

    def displayed_packet_count(self) -> int:
        return self.packet_table_model.rowCount()

    def _visible_chunk_size(self) -> int:
        row_height = max(1, self.packet_table.verticalHeader().defaultSectionSize())
        viewport_height = max(self.packet_table.viewport().height(), row_height * 12)
        visible_rows = max(20, viewport_height // row_height)
        return max(self.PACKET_LOAD_CHUNK_SIZE, visible_rows * 4)

    def _load_more_packets(self, minimum_count: Optional[int] = None):
        if self._loaded_packet_count >= len(self._all_packets):
            return

        target_count = self._loaded_packet_count + self._visible_chunk_size()
        if minimum_count is not None:
            target_count = max(target_count, minimum_count)
        next_count = min(len(self._all_packets), target_count)
        if next_count <= self._loaded_packet_count:
            return

        packets = self._all_packets[self._loaded_packet_count:next_count]
        self.packet_table_model.append_packets(packets)
        self._loaded_packet_count = next_count

    def _handle_packet_scroll(self, value: int):
        scrollbar = self.packet_table.verticalScrollBar()
        if value >= max(0, scrollbar.maximum() - self.PACKET_SCROLL_THRESHOLD):
            self._load_more_packets()

    def browse_for_file(self) -> str:
        file_name, _ = QFileDialog.getOpenFileName(
            self,
            "选择报文文件",
            "",
            PacketParserUtils.SUPPORTED_FILE_FILTER,
        )
        return file_name

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        if not urls:
            return
        file_path = urls[0].toLocalFile()
        if file_path:
            self.file_dropped.emit(file_path)

    def _create_tree_item(self, node: Dict[str, Any]) -> QTreeWidgetItem:
        item = QTreeWidgetItem([str(node.get("field", "")), str(node.get("value", ""))])
        item.setData(0, Qt.UserRole, node)
        for child in node.get("children", []) or []:
            item.addChild(self._create_tree_item(child))
        return item

    def _emit_packet_selected(self):
        if self._updating_table:
            return
        row = self.packet_table.currentIndex().row()
        self.packet_selected.emit(row)

    def _emit_tree_node_selected(self):
        if self._building_tree:
            return
        item: Optional[QTreeWidgetItem] = self.tree_widget.currentItem()
        self.tree_node_selected.emit(item.data(0, Qt.UserRole) if item else None)

