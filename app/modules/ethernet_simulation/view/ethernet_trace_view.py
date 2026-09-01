# app/modules/ethernet_simulation/view/ethernet_trace_view.py
from __future__ import annotations

from typing import List, Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QAbstractItemView, QFrame, QHeaderView, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QSplitter, QTableWidget, QTableWidgetItem,
    QTextEdit, QVBoxLayout, QWidget,
)

from app.modules.ethernet_simulation.model.ethernet_simulation_model import (
    TraceEntry, MessageDirection,
)
from app.presentation.views.base_view import BaseView


# ---- 样式 ----
_TRACE_STYLE = (
    "QTableWidget { background:white; alternate-background-color:#F8FAFC; "
    "border:1px solid #E2E8F0; border-radius:8px; gridline-color:#E2E8F0; "
    "font-family:'Consolas','Courier New',monospace; font-size:11px; }"
    "QHeaderView::section { background:#1E293B; border:none; "
    "border-right:1px solid #334155; padding:6px 8px; color:#E2E8F0; font-weight:700; font-size:11px; }"
)
_INPUT_STYLE = (
    "QLineEdit { background:#FFFFFF; border:1px solid #CBD5E1; border-radius:6px; "
    "padding:5px 8px; font-size:12px; }"
    "QLineEdit:focus { border-color:#2563EB; }"
)
_BTN_GHOST = (
    "QPushButton { background:#FFFFFF; color:#1E293B; border:1px solid #CBD5E1; "
    "border-radius:8px; padding:6px 12px; font-weight:600; font-size:12px; }"
    "QPushButton:hover { background:#F1F5F9; }"
)


class EthernetTraceView(BaseView):
    """独立的报文追踪页面 - 显示仿真收发日志、报文详情和统计。"""

    clear_requested = pyqtSignal()
    trace_row_selected = pyqtSignal(int)

    TRACE_HEADERS = [
        "序号", "时间", "方向", "源IP", "源端口",
        "目的IP", "目的端口", "协议", "长度", "名称/摘要", "数据",
    ]

    def setup_ui(self):
        self._building = False
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 8, 12, 8)
        root.setSpacing(6)

        # ---- 顶部工具栏 ----
        toolbar = self._create_toolbar()
        root.addWidget(toolbar)

        # ---- 主区域：Trace 表格 + 底部(详情 + 统计) ----
        main_splitter = QSplitter(Qt.Vertical)
        main_splitter.addWidget(self._create_trace_table())
        main_splitter.addWidget(self._create_bottom_area())
        main_splitter.setStretchFactor(0, 3)
        main_splitter.setStretchFactor(1, 1)
        main_splitter.setSizes([500, 180])
        root.addWidget(main_splitter, 1)

    # ================================================================
    # 顶部工具栏
    # ================================================================
    def _create_toolbar(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("traceBar")
        frame.setFixedHeight(40)
        frame.setStyleSheet(
            "QFrame#traceBar { background:#F8FAFC; border:1px solid #E2E8F0; border-radius:8px; }"
        )
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(8)

        title = QLabel("📡 报文追踪 (Trace)")
        title.setStyleSheet("font-size:14px; font-weight:700; color:#0F172A;")
        layout.addWidget(title)

        layout.addStretch()

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("🔍 过滤报文...")
        self.filter_edit.setFixedWidth(200)
        self.filter_edit.setStyleSheet(_INPUT_STYLE)
        layout.addWidget(self.filter_edit)

        self.clear_btn = QPushButton("🗑 清空")
        self.clear_btn.setStyleSheet(_BTN_GHOST)
        self.clear_btn.setCursor(Qt.PointingHandCursor)
        self.clear_btn.setFixedHeight(28)
        self.clear_btn.clicked.connect(lambda: self.clear_requested.emit())
        layout.addWidget(self.clear_btn)

        # 统计标签（紧凑一行）
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet("color:#E2E8F0;")
        sep.setFixedHeight(22)
        layout.addWidget(sep)

        stat_style = "font-size:11px; color:#475569; font-family:'Consolas',monospace;"
        self.stats_tx_label = QLabel("TX: 0")
        self.stats_rx_label = QLabel("RX: 0")
        self.stats_total_label = QLabel("总计: 0")
        self.stats_bytes_label = QLabel("0 B")
        self.stats_time_label = QLabel("0s")
        self.stats_error_label = QLabel("错误: 0")
        for lbl in [self.stats_tx_label, self.stats_rx_label, self.stats_total_label,
                     self.stats_bytes_label, self.stats_time_label, self.stats_error_label]:
            lbl.setStyleSheet(stat_style)
            lbl.setFixedWidth(65)
            layout.addWidget(lbl)

        return frame

    # ================================================================
    # Trace 表格
    # ================================================================
    def _create_trace_table(self) -> QWidget:
        container = QFrame()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.trace_table = QTableWidget()
        self.trace_table.setColumnCount(len(self.TRACE_HEADERS))
        self.trace_table.setHorizontalHeaderLabels(self.TRACE_HEADERS)
        self.trace_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.trace_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.trace_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.trace_table.setAlternatingRowColors(True)
        self.trace_table.verticalHeader().setVisible(False)
        self.trace_table.setStyleSheet(_TRACE_STYLE)
        self.trace_table.horizontalHeader().setStretchLastSection(True)
        self.trace_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)

        # 列宽
        widths = [50, 80, 45, 120, 60, 120, 60, 70, 50, 200]
        for i, w in enumerate(widths):
            self.trace_table.setColumnWidth(i, w)

        self.trace_table.selectionModel().selectionChanged.connect(self._on_row_selected)

        layout.addWidget(self.trace_table, 1)
        return container

    # ================================================================
    # 底部：详情 + 统计
    # ================================================================
    def _create_bottom_area(self) -> QWidget:
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._create_detail_panel())
        splitter.addWidget(self._create_stats_panel())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([500, 200])
        return splitter

    def _create_detail_panel(self) -> QWidget:
        container = QFrame()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 4, 0)
        layout.setSpacing(4)

        title = QLabel("报文详情")
        title.setStyleSheet("font-size:12px; font-weight:700; color:#475569;")
        layout.addWidget(title)

        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        self.detail_text.setPlaceholderText("选择追踪条目查看详情...")
        self.detail_text.setStyleSheet(
            "QTextEdit { background:#1E293B; color:#E2E8F0; border:1px solid #334155; "
            "border-radius:6px; padding:8px; font-family:'Consolas','Courier New',monospace; "
            "font-size:11px; }"
        )
        layout.addWidget(self.detail_text, 1)
        return container

    def _create_stats_panel(self) -> QWidget:
        container = QFrame()
        container.setStyleSheet(
            "QFrame { background:#F8FAFC; border:1px solid #E2E8F0; border-radius:8px; }"
        )
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(4)

        title = QLabel("📊 详细统计")
        title.setStyleSheet("font-size:12px; font-weight:700; color:#334155;")
        layout.addWidget(title)

        detail_style = "font-size:11px; color:#475569; font-family:'Consolas',monospace;"

        self.detail_tx_label = QLabel("发送帧: 0")
        self.detail_rx_label = QLabel("接收帧: 0")
        self.detail_total_label = QLabel("总帧数: 0")
        self.detail_bytes_tx_label = QLabel("发送字节: 0 B")
        self.detail_bytes_rx_label = QLabel("接收字节: 0 B")
        self.detail_elapsed_label = QLabel("运行时间: 0s")
        self.detail_error_label = QLabel("错误: 0")

        for lbl in [self.detail_tx_label, self.detail_rx_label, self.detail_total_label,
                     self.detail_bytes_tx_label, self.detail_bytes_rx_label,
                     self.detail_elapsed_label, self.detail_error_label]:
            lbl.setStyleSheet(detail_style)
            layout.addWidget(lbl)

        layout.addStretch()
        return container

    # ================================================================
    # 公共接口
    # ================================================================

    def append_trace_entries(self, entries: List[TraceEntry]):
        """追加追踪条目。"""
        for entry in entries:
            row = self.trace_table.rowCount()
            self.trace_table.insertRow(row)

            dir_text = "→ TX" if entry.direction == MessageDirection.TX else "← RX"

            values = [
                str(entry.no),
                f"{entry.timestamp:.3f}",
                dir_text,
                entry.src_ip,
                str(entry.src_port),
                entry.dst_ip,
                str(entry.dst_port),
                entry.protocol,
                str(entry.length),
                entry.summary or entry.msg_name,
                entry.payload_hex[:60] if entry.payload_hex else "",
            ]
            for col, val in enumerate(values):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignCenter if col != 10 else Qt.AlignLeft)
                if col == 2:
                    item.setForeground(Qt.blue if entry.direction == MessageDirection.TX else Qt.green)
                self.trace_table.setItem(row, col, item)

        self.trace_table.scrollToBottom()

    def update_stats(self, stats: dict):
        """更新统计面板。"""
        tx = stats.get('tx_count', 0)
        rx = stats.get('rx_count', 0)
        total = stats.get('total', 0)
        b_sent = stats.get('bytes_sent', 0)
        b_recv = stats.get('bytes_received', 0)
        elapsed = stats.get('elapsed', 0.0)
        errors = stats.get('error_count', 0)

        # 顶部紧凑统计
        self.stats_tx_label.setText(f"TX: {tx}")
        self.stats_rx_label.setText(f"RX: {rx}")
        self.stats_total_label.setText(f"总计: {total}")
        self.stats_bytes_label.setText(self._fmt_bytes(b_sent + b_recv))
        self.stats_time_label.setText(self._fmt_time(elapsed))
        self.stats_error_label.setText(f"错误: {errors}")

        # 底部详细统计
        self.detail_tx_label.setText(f"发送帧: {tx}")
        self.detail_rx_label.setText(f"接收帧: {rx}")
        self.detail_total_label.setText(f"总帧数: {total}")
        self.detail_bytes_tx_label.setText(f"发送字节: {self._fmt_bytes(b_sent)}")
        self.detail_bytes_rx_label.setText(f"接收字节: {self._fmt_bytes(b_recv)}")
        self.detail_elapsed_label.setText(f"运行时间: {self._fmt_time(elapsed)}")
        self.detail_error_label.setText(f"错误: {errors}")

    def set_detail_text(self, text: str):
        """设置报文详情。"""
        self.detail_text.setPlainText(text)

    def clear_trace_table(self):
        """清空追踪表格。"""
        self.trace_table.setRowCount(0)
        self.detail_text.clear()

    # ================================================================
    # 内部方法
    # ================================================================

    def _on_row_selected(self):
        if self._building:
            return
        row = self.trace_table.currentRow()
        if row >= 0:
            self.trace_row_selected.emit(row)

    @staticmethod
    def _fmt_bytes(b: int) -> str:
        if b > 1024 * 1024:
            return f"{b / 1024 / 1024:.1f} MB"
        if b > 1024:
            return f"{b / 1024:.1f} KB"
        return f"{b} B"

    @staticmethod
    def _fmt_time(sec: float) -> str:
        if sec > 60:
            return f"{sec / 60:.1f} min"
        return f"{sec:.1f} s"
