# app/modules/ethernet_simulation/model/ethernet_simulation_model.py
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import pyqtSignal

from app.core.base_model import BaseModel


class TransportProtocol(str, Enum):
    UDP = "UDP"
    TCP = "TCP"
    SOMEIP = "SOME/IP"


class MessageDirection(str, Enum):
    TX = "TX"
    RX = "RX"


@dataclass
class SimMessage:
    """仿真报文定义 - 类似 CANOE 的报文编辑器条目。"""
    name: str = ""
    src_ip: str = "192.168.62.100"
    dst_ip: str = ""
    dst_port: int = 30500
    src_port: int = 30500
    protocol: TransportProtocol = TransportProtocol.UDP
    # SOME/IP 专用字段
    service_id: int = 0
    method_id: int = 0
    client_id: int = 0
    session_id: int = 0
    msg_type: int = 0x00  # 0x00=Request, 0x80=Response, 0x02=Notification
    # 负载 (十六进制字符串)
    payload_hex: str = ""
    # 周期发送配置 (ms, 0=单次)
    cycle_ms: int = 0
    # 启用状态
    enabled: bool = True
    # 单条发送状态 (是否正在周期发送)
    sending: bool = False
    # 统计
    tx_count: int = 0
    rx_count: int = 0

    def payload_bytes(self) -> bytes:
        """将十六进制字符串转换为字节。"""
        text = (self.payload_hex or "").strip().replace(" ", "").replace("_", "")
        if text.lower().startswith("0x"):
            text = text[2:]
        if not text:
            return b""
        try:
            return bytes.fromhex(text)
        except ValueError:
            return b""

    def summary(self) -> str:
        """生成报文摘要。"""
        if self.protocol == TransportProtocol.SOMEIP:
            return (f"SOME/IP Srv=0x{self.service_id:04X} "
                    f"Mth=0x{self.method_id:04X} "
                    f"Type=0x{self.msg_type:02X} "
                    f"Len={len(self.payload_bytes())}")
        return f"{self.protocol.value} -> {self.dst_ip}:{self.dst_port} Len={len(self.payload_bytes())}"


@dataclass
class TraceEntry:
    """报文追踪记录 - 类似 CANOE 的 Trace 窗口。"""
    no: int = 0
    timestamp: float = 0.0
    direction: MessageDirection = MessageDirection.TX
    src_ip: str = ""
    dst_ip: str = ""
    src_port: int = 0
    dst_port: int = 0
    protocol: str = ""
    length: int = 0
    summary: str = ""
    payload_hex: str = ""
    msg_name: str = ""


@dataclass
class NetworkConfig:
    """网络配置。"""
    local_ip: str = "192.168.62.100"
    vlan_id: int = 62
    src_port: int = 30500
    dst_port: int = 30500
    protocol: TransportProtocol = TransportProtocol.UDP


class EthernetSimulationModel(BaseModel):
    """以太网仿真数据模型。"""

    # 信号
    traceAppended = pyqtSignal(list)
    simulationStateChanged = pyqtSignal(bool)  # True=running
    statsChanged = pyqtSignal(dict)
    messageListChanged = pyqtSignal()
    messageSendingChanged = pyqtSignal(int, bool)  # row, sending

    def __init__(self, parent=None):
        super().__init__(parent)
        self.network_config = NetworkConfig()
        self.messages: List[SimMessage] = []
        self.trace_entries: List[TraceEntry] = []
        self._trace_counter = 0
        self._start_time: float = 0.0
        self.is_running: bool = False

        # 统计
        self.tx_count: int = 0
        self.rx_count: int = 0
        self.error_count: int = 0
        self.bytes_sent: int = 0
        self.bytes_received: int = 0

    # ---- 仿真状态管理 ----

    def start_simulation(self):
        """开始仿真。"""
        self.is_running = True
        self._start_time = time.time()
        self.simulationStateChanged.emit(True)
        self.dataChanged.emit()

    def stop_simulation(self):
        """停止仿真。"""
        self.is_running = False
        self.simulationStateChanged.emit(False)
        self.dataChanged.emit()

    # ---- 报文管理 ----

    def add_message(self, msg: SimMessage):
        """添加仿真报文。"""
        self.messages.append(msg)
        self.messageListChanged.emit()
        self.dataChanged.emit()

    def remove_message(self, index: int):
        """移除仿真报文。"""
        if 0 <= index < len(self.messages):
            self.messages.pop(index)
            self.messageListChanged.emit()
            self.dataChanged.emit()

    def update_message(self, index: int, msg: SimMessage):
        """更新仿真报文。"""
        if 0 <= index < len(self.messages):
            self.messages[index] = msg
            self.messageListChanged.emit()
            self.dataChanged.emit()

    def duplicate_message(self, index: int) -> Optional[SimMessage]:
        """复制仿真报文。"""
        if 0 <= index < len(self.messages):
            import copy
            new_msg = copy.deepcopy(self.messages[index])
            new_msg.name = f"{new_msg.name}_copy"
            new_msg.tx_count = 0
            new_msg.rx_count = 0
            return new_msg
        return None

    def clear_messages(self):
        """清空所有报文。"""
        self.messages.clear()
        self.messageListChanged.emit()
        self.dataChanged.emit()

    # ---- 追踪记录 ----

    def append_trace(self, entries: List[TraceEntry]):
        """追加追踪记录。"""
        for entry in entries:
            self._trace_counter += 1
            entry.no = self._trace_counter
            if entry.timestamp == 0.0:
                entry.timestamp = time.time() - self._start_time if self._start_time else 0.0
        self.trace_entries.extend(entries)
        self.traceAppended.emit(entries)

        # 更新统计
        for entry in entries:
            if entry.direction == MessageDirection.TX:
                self.tx_count += 1
                self.bytes_sent += entry.length
            else:
                self.rx_count += 1
                self.bytes_received += entry.length

        self._emit_stats()

    def clear_trace(self):
        """清空追踪记录。"""
        self.trace_entries.clear()
        self._trace_counter = 0
        self.dataChanged.emit()

    def reset_stats(self):
        """重置统计。"""
        self.tx_count = 0
        self.rx_count = 0
        self.error_count = 0
        self.bytes_sent = 0
        self.bytes_received = 0
        self._emit_stats()

    def _emit_stats(self):
        """发射统计变更信号。"""
        elapsed = time.time() - self._start_time if self._start_time else 0.0
        self.statsChanged.emit({
            "tx_count": self.tx_count,
            "rx_count": self.rx_count,
            "error_count": self.error_count,
            "bytes_sent": self.bytes_sent,
            "bytes_received": self.bytes_received,
            "elapsed": elapsed,
            "total": self.tx_count + self.rx_count,
        })

    # ---- 工具方法 ----

    def get_enabled_messages(self) -> List[SimMessage]:
        """获取所有启用的报文。"""
        return [m for m in self.messages if m.enabled]

    def get_message_count(self) -> int:
        return len(self.messages)

    def get_trace_count(self) -> int:
        return len(self.trace_entries)

    def increment_error(self):
        self.error_count += 1
        self._emit_stats()

    def set_message_sending(self, index: int, sending: bool):
        """设置单条报文的发送状态。"""
        if 0 <= index < len(self.messages):
            self.messages[index].sending = sending
            self.messageSendingChanged.emit(index, sending)

    def set_all_enabled(self, enabled: bool):
        """全选/取消全选。"""
        for msg in self.messages:
            msg.enabled = enabled
        self.messageListChanged.emit()
