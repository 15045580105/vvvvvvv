"""通信数据中心 (Observer/Listener 模式).

职责:
    * 作为以太网接收的集中入口, 接收并缓存从 `EthernetSniffer` 解析好的报文;
    * 提供监听者(观察者)注册/注销接口, 只对**已注册**的监听者分发数据;
    * 一个监听者类只要实现约定的回调方法, 即可收到分发的报文;
    * 保证在开始接收前完成监听者注册, 否则不会收到历史数据。

整体设计:
    EthernetSniffer(packet_handler -> parse_ethernet_packet)
        ↓ (raw_bytes + parse_result)
    DataCenter (单例/全局实例)
        ↓
    多个 Listener(实现 `on_eth_message(self, raw_bytes, parsed)` 方法)

使用示例 (伪代码):

    from app.common.communication.DataCenter.DataCenter import DataCenter
    from app.common.communication.clients.Someip_Doip_Client import (
        EthernetConnectionConfig, SomeipDoipEthernetClient,
    )

    class MyListener:
        def on_eth_message(self, raw_bytes, parsed):
            print("收到解析报文", parsed)

    dc = DataCenter.get_instance()
    dc.register_listener(MyListener())   # ⚠ 必须在 connect() 前注册

    cfg = EthernetConnectionConfig(...)
    client = SomeipDoipEthernetClient(
        cfg,
        on_packet=dc.on_raw_packet,      # 把 DataCenter 挂到 Sniffer 回调上
    )
    client.connect()                     # 先开启接收
    client.send(...)

这样, 只要实现了 `on_eth_message` 的类且在接收前完成注册, 就可以收到分发的报文。
"""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Protocol, Optional


class EthernetMessageListener(Protocol):
    """监听者协议: 任意实现此方法的类都可以作为监听者注册.

    你也可以简单地在类中实现同名方法, 而不显式继承该 Protocol:

        class MyListener:
            def on_eth_message(self, raw_bytes, parsed: dict) -> None:
                ...
    """

    def on_eth_message(self, raw_bytes: bytes, parsed: Dict[str, Any]) -> None:  # pragma: no cover - Protocol
        ...


class DataCenter:
    """通信数据中心, 采用监听者/观察者模式.

    - 以单例形式提供 `get_instance()` 获取全局唯一实例;
    - 对外暴露 `register_listener` / `unregister_listener`;
    - 提供 `on_raw_packet` 给以太网接收端回调使用, 统一解析并分发。
    """

    _instance: Optional["DataCenter"] = None
    _instance_lock = threading.RLock()

    def __init__(self) -> None:
        # 当前已注册的监听者
        self._listeners: List[EthernetMessageListener] = []
        self._listeners_lock = threading.RLock()

        # 简单的接收计数器, 方便调试/监控
        self._rx_count = 0

    # ------------------------------------------------------------------
    # 单例相关
    # ------------------------------------------------------------------
    @classmethod
    def get_instance(cls) -> "DataCenter":
        """获取全局唯一的数据中心实例."""
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    # ------------------------------------------------------------------
    # 监听者注册/注销
    # ------------------------------------------------------------------
    def register_listener(self, listener: EthernetMessageListener) -> None:
        """注册一个监听者.

        说明:
            * 必须在开始接收(即客户端 connect/开启嗅探)之前注册,
              否则不会收到之前的历史报文;
            * 同一个实例重复注册会被忽略.
        """
        if listener is None:
            return

        with self._listeners_lock:
            if listener in self._listeners:
                return
            self._listeners.append(listener)

    def unregister_listener(self, listener: EthernetMessageListener) -> None:
        """注销一个监听者."""
        if listener is None:
            return

        with self._listeners_lock:
            if listener in self._listeners:
                self._listeners.remove(listener)

    # ------------------------------------------------------------------
    # 接收入口 (供 EthernetSniffer / Client 回调使用)
    # ------------------------------------------------------------------
    def on_parsed_packet(self, parsed: Dict[str, Any], raw_bytes: Optional[bytes] = None) -> None:
        """由底层嗅探器回调的入口: 直接接收**已解析**的报文结果.

        Args:
            parsed: ETH_Read_Send.packet_handler 中解析完成后的结果字典;
            raw_bytes: 可选的原始字节数据, 便于上层需要十六进制等展示时使用。

        说明:
            * 相比之前的 on_raw_packet, 这里不再进行二次解析；
            * DataCenter 只负责记录计数并将 (raw_bytes, parsed) 分发给监听者。
        """
        self._rx_count += 1

        # meta 信息可以放入 parsed 的一个子字段, 避免接口再膨胀
        meta = parsed.get("meta") if isinstance(parsed, dict) else None
        if not isinstance(meta, dict):
            meta = {}
        meta.setdefault("timestamp", time.time())
        meta.setdefault("rx_index", self._rx_count)
        # 写回 parsed 供上层使用
        if isinstance(parsed, dict):
            parsed["meta"] = meta

        if raw_bytes is None:
            # 部分场景如果没法拿到原始 bytes, 也允许为 None
            raw_bytes = b""

        with self._listeners_lock:
            listeners_snapshot = list(self._listeners)

        for listener in listeners_snapshot:
            try:
                listener.on_eth_message(raw_bytes, parsed)  # type: ignore[attr-defined]
            except Exception:
                continue

    # 保留旧接口, 但标记为兼容用途, 直接转调 on_parsed_packet
    def on_raw_packet(self, raw_bytes: bytes, meta: Dict[str, Any]) -> None:
        """兼容入口: 若底层仍然按 raw_bytes 回调, 可在外层先解析后再调用 on_parsed_packet.

        当前推荐的使用方式是: 在 `ETH_Read_Send.EthernetSniffer.packet_handler` 中
        已经解析出结果 `parsed`, 然后直接调用::

            dc.on_parsed_packet(parsed, raw_bytes)

        这样 DataCenter 就不会重复解析。
        """
        # 默认实现仅包装 meta 为 parsed 中的 meta 字段, 不做解析
        if not isinstance(meta, dict):
            meta = {"meta": meta}
        parsed: Dict[str, Any] = {"meta": meta, "raw_hex": raw_bytes.hex()}
        self.on_parsed_packet(parsed, raw_bytes)

    # ------------------------------------------------------------------
    # 调试/监控辅助方法
    # ------------------------------------------------------------------
    @property
    def rx_count(self) -> int:
        """已接收到并尝试分发的报文数量."""
        return self._rx_count


# 可选: 若你希望在独立运行 DataCenter 进行简单自测, 可添加少量 demo 代码
if __name__ == "__main__":  # pragma: no cover - 手动测试用
    class DemoListener:
        def on_eth_message(self, raw_bytes: bytes, parsed: Dict[str, Any]) -> None:
            print("[DemoListener] 收到报文, 长度:", len(raw_bytes))
            print("[DemoListener] 解析结果 keys:", list(parsed.keys()))

    dc = DataCenter.get_instance()
    dc.register_listener(DemoListener())

    # 模拟一帧原始数据 (这里直接用空 bytes)
    dc.on_raw_packet(b"", {"interface": "demo0"})
    print("rx_count =", dc.rx_count)

