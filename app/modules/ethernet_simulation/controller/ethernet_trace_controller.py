# app/modules/ethernet_simulation/controller/ethernet_trace_controller.py
from __future__ import annotations

import logging
from typing import List, Optional

from PyQt5.QtCore import QObject

from app.modules.ethernet_simulation.model.ethernet_simulation_model import (
    EthernetSimulationModel, TraceEntry,
)
from app.modules.ethernet_simulation.view.ethernet_trace_view import EthernetTraceView

logger = logging.getLogger(__name__)


class EthernetTraceController(QObject):
    """报文追踪页面控制器 - 独立页面，接收仿真控制器推送的追踪数据。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.view = EthernetTraceView(parent)
        self._model: Optional[EthernetSimulationModel] = None

        # 连接视图信号
        self.view.clear_requested.connect(self.on_clear)
        self.view.trace_row_selected.connect(self.on_trace_row_selected)

    def bind_model(self, model: EthernetSimulationModel):
        """绑定仿真模型，接收追踪数据和统计更新。"""
        self._model = model
        model.traceAppended.connect(self.view.append_trace_entries)
        model.statsChanged.connect(self.view.update_stats)

    def on_clear(self):
        """清空追踪。"""
        self.view.clear_trace_table()
        if self._model:
            self._model.clear_trace()

    def on_trace_row_selected(self, row: int):
        """追踪行选中 - 显示报文详情。"""
        if not self._model:
            return
        if 0 <= row < len(self._model.trace_entries):
            entry = self._model.trace_entries[row]
            detail_lines = [
                f"序号:     {entry.no}",
                f"时间:     {entry.timestamp:.6f} s",
                f"方向:     {entry.direction.value}",
                f"源:       {entry.src_ip}:{entry.src_port}",
                f"目的:     {entry.dst_ip}:{entry.dst_port}",
                f"协议:     {entry.protocol}",
                f"长度:     {entry.length} bytes",
                f"名称:     {entry.msg_name}",
                f"摘要:     {entry.summary}",
                "",
                "── 负载数据 (Hex) ──",
            ]
            # 格式化 hex 数据，每行 16 字节
            hex_str = entry.payload_hex or ""
            for i in range(0, len(hex_str), 32):
                chunk = hex_str[i:i + 32]
                # 添加空格分隔
                spaced = " ".join(chunk[j:j + 2] for j in range(0, len(chunk), 2))
                offset = i // 2
                detail_lines.append(f"  {offset:04X}: {spaced}")

            self.view.set_detail_text("\n".join(detail_lines))

    def get_view(self):
        """供 MainController 获取视图。"""
        return self.view

    def on_close(self):
        """清理。"""
        pass
