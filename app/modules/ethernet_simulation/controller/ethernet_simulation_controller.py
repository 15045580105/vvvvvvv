# app/modules/ethernet_simulation/controller/ethernet_simulation_controller.py
from __future__ import annotations

import copy
import json
import logging
import socket
import struct
import threading
import time
from typing import Dict, List, Optional

from PyQt5.QtCore import QTimer, pyqtSignal, QThread

from app.core.base_controller import BaseController
from app.core.base_model import BaseModel
from app.modules.ethernet_simulation.model.ethernet_simulation_model import (
    EthernetSimulationModel, SimMessage, TraceEntry, TransportProtocol, MessageDirection,
)
from app.modules.ethernet_simulation.view.ethernet_simulation_view import EthernetSimulationView

logger = logging.getLogger(__name__)


class ReceiveWorker(QThread):
    """后台接收线程 - 监听 UDP/TCP 端口接收报文。"""

    packet_received = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self, local_ip: str, port: int, protocol: str, parent=None):
        super().__init__(parent)
        self.local_ip = local_ip
        self.port = port
        self.protocol = protocol
        self._running = False
        self._socket: Optional[socket.socket] = None

    def run(self):
        self._running = True
        try:
            if self.protocol in ("UDP", "SOME/IP"):
                self._run_udp()
            elif self.protocol == "TCP":
                self._run_tcp()
        except Exception as exc:
            if self._running:
                self.error_occurred.emit(str(exc))

    def stop(self):
        self._running = False
        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass
        self.wait(1000)

    def _run_udp(self):
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.settimeout(0.5)
        try:
            self._socket.bind(("", self.port))
        except OSError as exc:
            self.error_occurred.emit(f"绑定端口 {self.port} 失败: {exc}")
            return

        while self._running:
            try:
                data, addr = self._socket.recvfrom(65535)
                self.packet_received.emit({
                    "src_ip": addr[0],
                    "src_port": addr[1],
                    "dst_ip": self.local_ip,
                    "dst_port": self.port,
                    "protocol": self.protocol,
                    "length": len(data),
                    "payload": data.hex(),
                })
            except socket.timeout:
                continue
            except OSError:
                if self._running:
                    break

    def _run_tcp(self):
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.settimeout(0.5)
        try:
            self._socket.bind(("", self.port))
            self._socket.listen(5)
        except OSError as exc:
            self.error_occurred.emit(f"绑定端口 {self.port} 失败: {exc}")
            return

        while self._running:
            try:
                conn, addr = self._socket.accept()
                conn.settimeout(0.5)
                while self._running:
                    try:
                        data = conn.recv(65535)
                        if not data:
                            break
                        self.packet_received.emit({
                            "src_ip": addr[0],
                            "src_port": addr[1],
                            "dst_ip": self.local_ip,
                            "dst_port": self.port,
                            "protocol": self.protocol,
                            "length": len(data),
                            "payload": data.hex(),
                        })
                    except socket.timeout:
                        continue
                    except OSError:
                        break
                conn.close()
            except socket.timeout:
                continue
            except OSError:
                if self._running:
                    break


class CycleSendWorker(QThread):
    """周期发送线程。"""

    packet_sent = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False
        self._tasks: List[dict] = []  # {msg, interval, send_func}

    def add_task(self, msg: SimMessage, interval: float, send_func):
        self._tasks.append({
            "msg": msg,
            "interval": interval,
            "send_func": send_func,
            "last_sent": 0.0,
        })

    def clear_tasks(self):
        self._tasks.clear()

    def run(self):
        self._running = True
        while self._running:
            now = time.time()
            for task in self._tasks:
                if now - task["last_sent"] >= task["interval"]:
                    try:
                        task["send_func"](task["msg"])
                        task["last_sent"] = now
                    except Exception as exc:
                        self.error_occurred.emit(str(exc))
            time.sleep(0.01)  # 10ms 精度

    def stop(self):
        self._running = False
        self.wait(1000)


class EthernetSimulationController(BaseController):
    """以太网仿真控制器 - CANOE 风格。"""

    def __init__(self, parent=None):
        self.model = EthernetSimulationModel(parent)
        self.view = EthernetSimulationView(parent)
        super().__init__(self.model, self.view, parent)

        self._recv_worker: Optional[ReceiveWorker] = None
        self._cycle_worker: Optional[CycleSendWorker] = None
        self._send_sockets: Dict[str, socket.socket] = {}
        self._per_cycle_timers: Dict[int, QTimer] = {}  # row -> QTimer for per-message cycle

        # 连接信号
        self.view.start_requested.connect(self.on_start)
        self.view.stop_requested.connect(self.on_stop)
        self.view.send_once_requested.connect(self.on_send_once)
        self.view.add_message_requested.connect(self.on_add_message)
        self.view.remove_message_requested.connect(self.on_remove_message)
        self.view.duplicate_message_requested.connect(self.on_duplicate_message)
        self.view.clear_messages_requested.connect(self.on_clear_messages)
        self.view.message_selected.connect(self.on_message_selected)
        self.view.import_requested.connect(self.on_import_config)
        self.view.export_requested.connect(self.on_export_config)
        self.view.toggle_send_requested.connect(self.on_toggle_message_send)
        self.view.select_all_requested.connect(self.on_select_all)
        self.view.message_enabled_changed.connect(self.on_message_enabled_changed)

        self.model.simulationStateChanged.connect(self.view.set_simulation_running)
        self.model.messageListChanged.connect(self._refresh_message_table)
        self.model.messageSendingChanged.connect(self._on_message_sending_changed)

        # 初始化默认报文模板
        self._init_default_messages()

    # ================================================================
    # 仿真控制
    # ================================================================

    def on_start(self):
        """开始仿真。"""
        # 启动接收线程（绑定所有接口，监听 UDP 30500）
        self._recv_worker = ReceiveWorker("0.0.0.0", 30500, "UDP", self)
        self._recv_worker.packet_received.connect(self._on_packet_received)
        self._recv_worker.error_occurred.connect(self._on_recv_error)
        self._recv_worker.start()

        self.model.start_simulation()
        logger.info("以太网仿真已启动 - 接收监听已启动，请单独启动报文的周期发送")

    def on_stop(self):
        """停止仿真。"""
        if self._recv_worker:
            self._recv_worker.stop()
            self._recv_worker = None
        if self._cycle_worker:
            self._cycle_worker.stop()
            self._cycle_worker = None

        # 停止所有单条报文周期发送
        for index in list(self._per_cycle_timers.keys()):
            self._stop_message_cycle(index)

        # 关闭所有发送 socket
        for sock in self._send_sockets.values():
            try:
                sock.close()
            except Exception:
                pass
        self._send_sockets.clear()

        self.model.stop_simulation()
        logger.info("以太网仿真已停止")

    def on_send_once(self, index: int):
        """单次发送指定报文。"""
        if index < 0 or index >= len(self.model.messages):
            return
        msg = self.model.messages[index]
        try:
            self._do_send_message(msg)
        except Exception as exc:
            logger.error("发送报文失败: %s", exc)
            self.model.increment_error()

    # ================================================================
    # 报文管理
    # ================================================================

    def on_add_message(self, protocol_name: str):
        """添加新报文。"""
        config = self.view.get_network_config()
        proto_map = {"UDP": TransportProtocol.UDP, "TCP": TransportProtocol.TCP,
                     "SOME/IP": TransportProtocol.SOMEIP}
        msg = SimMessage(
            name=f"Msg_{len(self.model.messages) + 1}",
            dst_ip="192.168.62.129",
            dst_port=config["dst_port"],
            src_port=config["src_port"],
            protocol=proto_map.get(protocol_name, TransportProtocol.UDP),
        )
        self.model.add_message(msg)
        self._refresh_message_table()
        # 选中新添加的报文
        row = len(self.model.messages) - 1
        self.view.msg_table.selectRow(row)
        self.view.load_editor_from_message(msg)

    def on_remove_message(self, index: int):
        """移除报文。"""
        self.model.remove_message(index)
        self._refresh_message_table()

    def on_duplicate_message(self, index: int):
        """复制报文。"""
        new_msg = self.model.duplicate_message(index)
        if new_msg:
            self.model.add_message(new_msg)
            self._refresh_message_table()

    def on_clear_messages(self):
        """清空所有报文。"""
        self.model.clear_messages()
        self._refresh_message_table()

    def on_message_selected(self, index: int):
        """报文选中 - 加载到编辑器。"""
        if 0 <= index < len(self.model.messages):
            msg = self.model.messages[index]
            self.view.load_editor_from_message(msg)

    def on_toggle_message_send(self, index: int):
        """单条报文开始/停止周期发送。"""
        if index < 0 or index >= len(self.model.messages):
            return
        msg = self.model.messages[index]
        if msg.sending:
            # 停止该报文的周期发送
            self._stop_message_cycle(index)
        else:
            # 开始该报文的周期发送
            if msg.cycle_ms <= 0:
                # 单次发送
                try:
                    self._do_send_message(msg)
                except Exception as exc:
                    logger.error("发送报文失败: %s", exc)
                    self.model.increment_error()
                return
            self._start_message_cycle(index, msg)

    def on_select_all(self, enabled: bool):
        """全选/取消全选。"""
        self.model.set_all_enabled(enabled)

    def _start_message_cycle(self, index: int, msg: SimMessage):
        """开始单条报文的周期发送。"""
        if index in self._per_cycle_timers:
            return  # 已经在发送
        timer = QTimer(self)
        timer.timeout.connect(lambda: self._on_per_cycle_tick(index))
        timer.start(msg.cycle_ms)
        self._per_cycle_timers[index] = timer
        self.model.set_message_sending(index, True)
        logger.info("报文 [%s] 开始周期发送: %dms", msg.name, msg.cycle_ms)

    def _stop_message_cycle(self, index: int):
        """停止单条报文的周期发送。"""
        if index in self._per_cycle_timers:
            timer = self._per_cycle_timers.pop(index)
            timer.stop()
            timer.deleteLater()
            self.model.set_message_sending(index, False)
            if index < len(self.model.messages):
                logger.info("报文 [%s] 停止周期发送", self.model.messages[index].name)

    def _on_per_cycle_tick(self, index: int):
        """单条报文周期发送定时器触发。"""
        if index < 0 or index >= len(self.model.messages):
            return
        msg = self.model.messages[index]
        try:
            self._do_send_message(msg)
        except Exception as exc:
            logger.error("周期发送报文失败: %s", exc)
            self.model.increment_error()

    def _on_message_sending_changed(self, row: int, sending: bool):
        """报文发送状态变更 - 更新视图。"""
        self.view.update_row_sending_status(row, sending)

    def on_message_enabled_changed(self, row: int, enabled: bool):
        """报文启用状态变更。"""
        if 0 <= row < len(self.model.messages):
            self.model.messages[row].enabled = enabled

    # ================================================================
    # 配置导入/导出
    # ================================================================

    def on_import_config(self):
        """导入配置。"""
        from PyQt5.QtWidgets import QFileDialog
        file_path, _ = QFileDialog.getOpenFileName(
            self.view, "导入仿真配置", "", "JSON 文件 (*.json);;所有文件 (*)"
        )
        if not file_path:
            return
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._load_config(data)
            logger.info("配置导入成功: %s", file_path)
        except Exception as exc:
            logger.error("配置导入失败: %s", exc)
            self.view.show_message(f"配置导入失败: {exc}", "error")

    def on_export_config(self):
        """导出配置。"""
        from PyQt5.QtWidgets import QFileDialog
        file_path, _ = QFileDialog.getSaveFileName(
            self.view, "导出仿真配置", "ethernet_sim_config.json",
            "JSON 文件 (*.json);;所有文件 (*)"
        )
        if not file_path:
            return
        try:
            data = self._save_config()
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info("配置导出成功: %s", file_path)
        except Exception as exc:
            logger.error("配置导出失败: %s", exc)
            self.view.show_message(f"配置导出失败: {exc}", "error")

    # ================================================================
    # 内部方法
    # ================================================================

    def _do_send_message(self, msg: SimMessage):
        """实际发送报文。"""
        src_ip = msg.src_ip

        if msg.protocol == TransportProtocol.SOMEIP:
            self._send_someip(msg, src_ip)
        elif msg.protocol == TransportProtocol.TCP:
            self._send_tcp(msg, src_ip)
        else:
            self._send_udp(msg, src_ip)

        # 记录追踪
        entry = TraceEntry(
            direction=MessageDirection.TX,
            src_ip=src_ip,
            dst_ip=msg.dst_ip,
            src_port=msg.src_port,
            dst_port=msg.dst_port,
            protocol=msg.protocol.value,
            length=len(msg.payload_bytes()),
            summary=msg.summary(),
            payload_hex=msg.payload_hex,
            msg_name=msg.name,
        )
        self.model.append_trace([entry])
        msg.tx_count += 1
        self._refresh_message_table()

    def _send_udp(self, msg: SimMessage, local_ip: str):
        """发送 UDP 报文。"""
        key = f"udp_{msg.src_port}"
        if key not in self._send_sockets:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((local_ip, msg.src_port))
            self._send_sockets[key] = sock
        data = msg.payload_bytes()
        self._send_sockets[key].sendto(data, (msg.dst_ip, msg.dst_port))

    def _send_tcp(self, msg: SimMessage, local_ip: str):
        """发送 TCP 报文。"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3.0)
        try:
            sock.connect((msg.dst_ip, msg.dst_port))
            sock.sendall(msg.payload_bytes())
        finally:
            sock.close()

    def _send_someip(self, msg: SimMessage, local_ip: str):
        """发送 SOME/IP 报文。"""
        try:
            from scapy.contrib.automotive.someip import SOMEIP
            payload = msg.payload_bytes()
            someip_pkt = SOMEIP(
                srv_id=msg.service_id,
                sub_id=msg.method_id,
                client_id=msg.client_id,
                session_id=1,
                msg_type=msg.msg_type,
                retcode=0x00,
            ) / payload
            data = bytes(someip_pkt)
            # 通过 UDP 发送 SOME/IP
            key = f"udp_{msg.src_port}"
            if key not in self._send_sockets:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind((local_ip, msg.src_port))
                self._send_sockets[key] = sock
            self._send_sockets[key].sendto(data, (msg.dst_ip, msg.dst_port))
        except ImportError:
            # 如果没有 scapy，直接发送原始数据
            self._send_udp(msg, local_ip)

    def _on_packet_received(self, packet_info: dict):
        """收到报文回调。"""
        entry = TraceEntry(
            direction=MessageDirection.RX,
            src_ip=packet_info.get("src_ip", ""),
            dst_ip=packet_info.get("dst_ip", ""),
            src_port=packet_info.get("src_port", 0),
            dst_port=packet_info.get("dst_port", 0),
            protocol=packet_info.get("protocol", ""),
            length=packet_info.get("length", 0),
            summary=f"RX {packet_info.get('protocol', '')} "
                    f"Len={packet_info.get('length', 0)}",
            payload_hex=packet_info.get("payload", ""),
        )
        self.model.append_trace([entry])

    def _on_recv_error(self, error: str):
        """接收错误回调。"""
        logger.error("接收错误: %s", error)
        self.model.increment_error()

    def _on_send_error(self, error: str):
        """发送错误回调。"""
        logger.error("周期发送错误: %s", error)
        self.model.increment_error()

    def _on_cycle_packet_sent(self, info: dict):
        """周期发送回调。"""
        pass  # 已在 _do_send_message 中记录

    def _refresh_message_table(self):
        """刷新报文表格。"""
        self.view.update_message_table(self.model.messages)

    def _init_default_messages(self):
        """初始化默认报文模板。"""
        defaults = [
            SimMessage(
                name="UDP_Request",
                dst_ip="192.168.62.129",
                dst_port=30500,
                src_port=30500,
                protocol=TransportProtocol.UDP,
                payload_hex="DE AD BE EF",
                cycle_ms=0,
            ),
            SimMessage(
                name="SOMEIP_FindService",
                dst_ip="239.0.0.255",
                dst_port=30490,
                src_port=30490,
                protocol=TransportProtocol.SOMEIP,
                service_id=0xFFFF,
                method_id=0x8100,
                client_id=0x0000,
                msg_type=0x02,
                payload_hex="C0 00 00 20 00 00 00 00 01 00 00 00 00 00 10 00 FF FF FF FF 00 01 03 00 00 04 C0 A8 3E 64 11 75 30",
                cycle_ms=1000,
            ),
        ]
        for msg in defaults:
            self.model.messages.append(msg)
        self._refresh_message_table()

    def _load_config(self, data: dict):
        """从字典加载配置。"""
        # 网络配置
        net = data.get("network", {})
        if net:
            self.view.vlan_spin.setValue(net.get("vlan_id", 62))

        # 报文列表
        msgs_data = data.get("messages", [])
        self.model.messages.clear()
        for m in msgs_data:
            proto_map = {"UDP": TransportProtocol.UDP, "TCP": TransportProtocol.TCP,
                         "SOME/IP": TransportProtocol.SOMEIP}
            msg = SimMessage(
                name=m.get("name", ""),
                src_ip=m.get("src_ip", "192.168.62.100"),
                dst_ip=m.get("dst_ip", ""),
                dst_port=m.get("dst_port", 30500),
                src_port=m.get("src_port", 30500),
                protocol=proto_map.get(m.get("protocol", "UDP"), TransportProtocol.UDP),
                service_id=m.get("service_id", 0),
                method_id=m.get("method_id", 0),
                client_id=m.get("client_id", 0),
                msg_type=m.get("msg_type", 0x00),
                payload_hex=m.get("payload_hex", ""),
                cycle_ms=m.get("cycle_ms", 0),
                enabled=m.get("enabled", True),
            )
            self.model.messages.append(msg)
        self._refresh_message_table()

    def _save_config(self) -> dict:
        """保存配置到字典。"""
        config = self.view.get_network_config()
        return {
            "network": {
                "vlan_id": config["vlan_id"],
                "src_port": config["src_port"],
                "dst_port": config["dst_port"],
            },
            "messages": [
                {
                    "name": msg.name,
                    "src_ip": msg.src_ip,
                    "dst_ip": msg.dst_ip,
                    "dst_port": msg.dst_port,
                    "src_port": msg.src_port,
                    "protocol": msg.protocol.value,
                    "service_id": msg.service_id,
                    "method_id": msg.method_id,
                    "client_id": msg.client_id,
                    "msg_type": msg.msg_type,
                    "payload_hex": msg.payload_hex,
                    "cycle_ms": msg.cycle_ms,
                    "enabled": msg.enabled,
                }
                for msg in self.model.messages
            ],
        }

    def on_close(self):
        """清理资源。"""
        self.on_stop()
