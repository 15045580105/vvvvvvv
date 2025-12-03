"""Ethernet SOME/IP & DoIP client utilities.

This module provides a high‑level client class that wraps the low‑level
Ethernet helper in `protocols/ETH_Read_Send.py` and offers a simple
"connect / send / receive" style API for talking to a known ECU over
Ethernet.

设计目标
--------
* 连接前先启动以太网接收，这样能够抓到对端的回复。
* 连接对象通过已知的 IP 和端口(逻辑概念) 来描述，方便上层调用。
* 实际上传输仍然基于原有的以太网帧 + SOME/IP 或 DoIP 报文，不强行拆分。

说明
----
* 这里的 "IP/端口" 主要是给上层调用者一个语义化的接口；
  在底层我们仍旧发送以太网帧（SOME/IP 使用 0x80B5，DoIP 使用 0x80F9）。
* 如果项目之后需要真正的 UDP/TCP Socket 形式的 SOME/IP/DoIP，可以在
  兼容此接口的前提下扩展实现。
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional, Literal, Any

from app.common.communication.protocols.ETH_Read_Send import EthernetSniffer


EthernetProtocol = Literal["someip", "doip", "raw"]


@dataclass
class EthernetConnectionConfig:
    """以太网逻辑连接配置.

    注意: ip/port 在此处更多是逻辑概念, 便于上层统一管理不同协议连接。
    底层仍然通过以太网帧发送 SOME/IP / DoIP 报文。
    """

    remote_ip: str
    remote_port: int
    # 物理层参数
    interface: Optional[str] = None  # None = 由 EthernetSniffer 自动选择
    dst_mac: str = "ff:ff:ff:ff:ff:ff"  # 默认广播, 调用时一般传具体 ECU MAC
    src_mac: Optional[str] = None

    # 报文类型
    protocol: EthernetProtocol = "raw"

    # SOME/IP 相关默认参数 (仅当 protocol=="someip" 时使用)
    service_id: int = 0x1234
    method_id: int = 0x0001
    client_id: int = 0x0001
    session_id: int = 0x0001

    # DOIP 相关默认参数 (仅当 protocol=="doip" 时使用)
    doip_payload_type: int = 0x8001


class SomeipDoipEthernetClient:
    """以太网上的 SOME/IP + DoIP 简易客户端.

    主要职责:
    * 在“连接”前启动 EthernetSniffer, 持续抓包.
    * 提供统一的 send / close / is_connected API.
    * 根据配置决定发送 SOME/IP / DoIP / 原始以太网负载.

    参数
    ----
    config: EthernetConnectionConfig
        逻辑连接配置, 包含 remote_ip / remote_port 等上层信息以及
        发送以太网帧所需的 MAC 地址和协议类型.
    on_packet:
        可选回调函数, 每当底层 EthernetSniffer 收到一帧时被调用。
        形如: ``def on_packet(packet_bytes: bytes, meta: dict) -> None``。
        默认不做任何处理，只在控制台打印 (沿用原有 EthernetSniffer 行为)。
    """

    # 类级别的共享嗅探器, 确保接收线程在整个进程中只启动一次
    _global_sniffer: Optional[EthernetSniffer] = None
    _global_sniffer_lock = threading.RLock()

    def __init__(
        self,
        config: EthernetConnectionConfig,
        on_packet: Optional[Callable[[bytes, dict], None]] = None,
    ) -> None:
        self._config = config
        self._sniffer: Optional[EthernetSniffer] = None
        self._lock = threading.RLock()
        self._connected = False
        self._user_on_packet = on_packet

    # ------------------------------------------------------------------
    # 属性/状态
    # ------------------------------------------------------------------
    @property
    def config(self) -> EthernetConnectionConfig:
        return self._config

    def is_connected(self) -> bool:
        """是否已经执行过 connect, 且嗅探线程仍在运行."""
        with self._lock:
            return bool(self._connected and self._sniffer and self._sniffer.is_running())

    # ------------------------------------------------------------------
    # 连接与关闭
    # ------------------------------------------------------------------
    def _ensure_receiver_started(self, timeout: float = 2.0) -> None:
        """确保底层以太网接收(嗅探)已经启动, 且全局只会启动一次.

        使用类级别的 `_global_sniffer` 来承载嗅探线程:
        * 若已有全局嗅探器且在运行, 直接复用, 不再新建/重启;
        * 若不存在, 则创建一个新的 EthernetSniffer 并启动一次。

        这样可以满足“接收只能开启一次”的需求, 避免多个客户端重复
        启动多个嗅探线程。
        """
        with SomeipDoipEthernetClient._global_sniffer_lock:
            # 已经有全局嗅探器并在运行, 直接使用
            if (SomeipDoipEthernetClient._global_sniffer is not None and
                    SomeipDoipEthernetClient._global_sniffer.is_running()):
                # 将全局嗅探器引用给当前实例
                self._sniffer = SomeipDoipEthernetClient._global_sniffer
                return

            # 初始化新的全局嗅探器
            sniffer = EthernetSniffer(interface=self._config.interface)

            # 如果用户提供了回调，则轻量包装一下 packet_handler
            if self._user_on_packet is not None:

                original_handler = sniffer.packet_handler

                def _wrapped_handler(packet: Any) -> None:  # type: ignore[override]
                    # 原 handler 打印/解析
                    original_handler(packet)
                    try:
                        raw_bytes = bytes(packet)
                        meta = {
                            "timestamp": time.time(),
                            "interface": sniffer.interface,
                        }
                        self._user_on_packet(raw_bytes, meta)
                    except Exception:
                        # 避免用户回调异常影响嗅探线程
                        pass

                sniffer.packet_handler = _wrapped_handler  # type: ignore[assignment]

            # 启动嗅探
            sniffer.start()

            # 等待线程真正进入运行状态
            start_ts = time.time()
            while not sniffer.is_running() and (time.time() - start_ts) < timeout:
                time.sleep(0.01)

            SomeipDoipEthernetClient._global_sniffer = sniffer
            self._sniffer = sniffer

    def connect(self, timeout: float = 2.0) -> None:
        """建立“连接”.

        实际行为:
        * **优先启动以太网接收** (嗅探线程)，确保在发送任何报文前就开始接收。
        * 标记为已连接状态, 供 `send()`/`close()` 等方法使用。
        """
        with self._lock:
            if self.is_connected():
                return

            # 先保证已经开启接收, 再认为“连接”已建立
            self._ensure_receiver_started(timeout=timeout)
            self._connected = True

    def close(self) -> None:
        """关闭当前客户端的逻辑连接.

        注意: 为了保证“接收只开启一次”的语义, 这里**不会**主动停止
        全局嗅探线程, 只是将当前客户端标记为未连接,
        嗅探线程仍可被其他客户端复用。
        若确实需要完全关闭接收, 可在应用退出时调用
        ``SomeipDoipEthernetClient.shutdown_global_receiver()``。
        """
        with self._lock:
            self._connected = False
            # 不再停止全局嗅探器, 仅解除当前实例引用
            self._sniffer = SomeipDoipEthernetClient._global_sniffer

    @classmethod
    def shutdown_global_receiver(cls) -> None:
        """停止全局嗅探线程, 一般在程序退出时调用.

        调用后再次创建/连接客户端时, 会重新启动接收线程一次。
        """
        with cls._global_sniffer_lock:
            if cls._global_sniffer is not None and cls._global_sniffer.is_running():
                try:
                    cls._global_sniffer.stop()
                except Exception:
                    pass
            cls._global_sniffer = None

    # ------------------------------------------------------------------
    # 发送接口 (统一对外暴露 ip/port 概念)
    # ------------------------------------------------------------------
    def send(self, payload: bytes) -> bool:
        """发送一帧数据.

        根据 ``config.protocol`` 不同, 行为如下:
        * "raw"   : 直接作为以太网负载发送.
        * "someip": 使用 ``EthernetSniffer.send_someip_packet`` 封装并发送.
        * "doip"  : 使用 ``EthernetSniffer.send_doip_packet`` 封装并发送.

        返回
        ----
        bool
            底层发送是否报告成功.
        """
        with self._lock:
            if not self.is_connected() or not self._sniffer:
                raise RuntimeError("Ethernet client is not connected; call connect() first.")

            cfg = self._config
            dst_mac = cfg.dst_mac
            src_mac = cfg.src_mac

            if cfg.protocol == "someip":
                return self._sniffer.send_someip_packet(
                    dst_mac=dst_mac,
                    src_mac=src_mac,
                    service_id=cfg.service_id,
                    method_id=cfg.method_id,
                    client_id=cfg.client_id,
                    session_id=cfg.session_id,
                    payload=payload,
                )

            if cfg.protocol == "doip":
                return self._sniffer.send_doip_packet(
                    dst_mac=dst_mac,
                    src_mac=src_mac,
                    payload_type=cfg.doip_payload_type,
                    payload=payload,
                )

            # raw
            return self._sniffer.send_ethernet_frame(
                dst_mac=dst_mac,
                src_mac=src_mac,
                payload=payload,
            )

    # ------------------------------------------------------------------
    # 便捷方法: 直接发送 SOME/IP / DoIP 特定语义报文
    # ------------------------------------------------------------------
    def send_someip_rpc(self, rpc_payload: Optional[bytes] = None) -> bool:
        """按照配置发送 SOME/IP RPC 请求."""
        with self._lock:
            if not self.is_connected() or not self._sniffer:
                raise RuntimeError("Ethernet client is not connected; call connect() first.")

            cfg = self._config
            return self._sniffer.send_someip_rpc_request(
                dst_mac=cfg.dst_mac,
                src_mac=cfg.src_mac,
                service_id=cfg.service_id,
                method_id=cfg.method_id,
                client_id=cfg.client_id,
                session_id=cfg.session_id,
                rpc_payload=rpc_payload,
            )

    def send_someip_notification(self, notification_data: Optional[bytes] = None) -> bool:
        """按照配置发送 SOME/IP 通知事件."""
        with self._lock:
            if not self.is_connected() or not self._sniffer:
                raise RuntimeError("Ethernet client is not connected; call connect() first.")

            cfg = self._config
            return self._sniffer.send_someip_notification(
                dst_mac=cfg.dst_mac,
                src_mac=cfg.src_mac,
                service_id=cfg.service_id,
                method_id=cfg.method_id,
                client_id=cfg.client_id,
                session_id=cfg.session_id,
                notification_data=notification_data,
            )

    def send_doip_vehicle_identification(self) -> bool:
        """发送 DOIP 车辆识别请求."""
        with self._lock:
            if not self.is_connected() or not self._sniffer:
                raise RuntimeError("Ethernet client is not connected; call connect() first.")

            cfg = self._config
            return self._sniffer.send_doip_vehicle_identification_request(
                dst_mac=cfg.dst_mac,
                src_mac=cfg.src_mac,
            )

    def send_doip_routing_activation(self, source_address: int = 0x0E00, activation_type: int = 0x00) -> bool:
        """发送 DOIP 路由激活请求."""
        with self._lock:
            if not self.is_connected() or not self._sniffer:
                raise RuntimeError("Ethernet client is not connected; call connect() first.")

            cfg = self._config
            return self._sniffer.send_doip_routing_activation_request(
                dst_mac=cfg.dst_mac,
                src_mac=cfg.src_mac,
                source_address=source_address,
                activation_type=activation_type,
            )


# 简单的自检/示例, 便于在独立运行该模块时快速验证
if __name__ == "__main__":
    # 注意: 运行此示例需要管理员权限以及已正确安装 Npcap / Scapy.
    cfg = EthernetConnectionConfig(
        remote_ip="192.168.0.10",
        remote_port=30490,
        interface=None,  # 使用默认接口
        dst_mac="ff:ff:ff:ff:ff:ff",  # 这里示例用广播, 实际请替换 ECU MAC
        protocol="raw",
    )

    client = SomeipDoipEthernetClient(cfg)
    client.connect()

    # 仅发送一帧简单 payload 作为示例
    client.send(b"Hello Ethernet from SomeipDoipEthernetClient")

    time.sleep(1.0)
    client.close()

