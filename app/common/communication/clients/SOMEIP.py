import socket
import struct
import threading
from typing import Dict, Optional, Callable, Tuple, Any
from enum import IntEnum


class MessageType(IntEnum):
    REQUEST = 0x00
    REQUEST_NO_RETURN = 0x01
    NOTIFICATION = 0x02
    RESPONSE = 0x80
    ERROR = 0x81


class ReturnCode(IntEnum):
    OK = 0x00
    NOT_OK = 0x01
    UNKNOWN_SERVICE = 0x02
    UNKNOWN_METHOD = 0x03
    NOT_READY = 0x04
    NOT_REACHABLE = 0x05
    TIMEOUT = 0x06
    WRONG_PROTOCOL_VERSION = 0x07
    WRONG_INTERFACE_VERSION = 0x08
    MALFORMED_MESSAGE = 0x09
    WRONG_MESSAGE_TYPE = 0x0A


class SOMEIPMessage:
    """SOME/IP消息解析/构造"""

    def __init__(self, data: bytes = None):
        if data:
            self.parse(data)
        else:
            self.service_id = 0
            self.method_id = 0
            self.length = 0
            self.client_id = 0
            self.session_id = 0
            self.protocol_version = 1
            self.interface_version = 1
            self.message_type = 0
            self.return_code = 0
            self.payload = b""

    def parse(self, data: bytes):
        """解析SOME/IP报文"""
        if len(data) < 16:
            raise ValueError("Invalid SOME/IP packet length")

        # 解析头部
        (self.service_id, self.method_id, self.length,
         self.client_id, self.session_id, proto_if,
         self.message_type, self.return_code) = struct.unpack('>HHIIIIHH', data[:16])

        # 协议版本和接口版本
        self.protocol_version = (proto_if >> 4) & 0x0F
        self.interface_version = proto_if & 0x0F

        # 负载
        payload_length = self.length - 8
        self.payload = data[16:16 + payload_length] if payload_length > 0 else b""

    def build(self) -> bytes:
        """构建SOME/IP报文"""
        # 计算长度
        self.length = len(self.payload) + 8

        # 构建协议和接口版本字段
        proto_if = ((self.protocol_version & 0x0F) << 4) | (self.interface_version & 0x0F)

        # 构建头部
        header = struct.pack('>HHIIIIHH',
                             self.service_id,
                             self.method_id,
                             self.length,
                             self.client_id,
                             self.session_id,
                             proto_if,
                             self.message_type,
                             self.return_code
                             )

        return header + self.payload

    def __str__(self):
        return (f"SOME/IP Message:\n"
                f"  Service: 0x{self.service_id:04X}\n"
                f"  Method: 0x{self.method_id:04X}\n"
                f"  Length: {self.length}\n"
                f"  Client: 0x{self.client_id:08X}\n"
                f"  Session: 0x{self.session_id:08X}\n"
                f"  MsgType: 0x{self.message_type:02X}\n"
                f"  Return: 0x{self.return_code:02X}\n"
                f"  Payload: {self.payload.hex() if len(self.payload) <= 20 else self.payload[:20].hex() + '...'}")


class _SomeipSocketLib:
    """基于 Python socket 的 SOME/IP 传输封装

    设计目标：
    - 抽象出“客户端句柄”，用于统一 send/recv 操作；
    - 后续如果有 C/DLL 实现，可以新增其它 Lib 类保持接口一致。
    """

    class Handle:
        def __init__(self) -> None:
            self.udp_socket: Optional[socket.socket] = None

    def create_client(self) -> "_SomeipSocketLib.Handle":
        return _SomeipSocketLib.Handle()

    def destroy_client(self, handle: "_SomeipSocketLib.Handle") -> None:
        if handle and handle.udp_socket:
            try:
                handle.udp_socket.close()
            except OSError:
                pass
            handle.udp_socket = None

    def set_local_endpoint(self, handle: "_SomeipSocketLib.Handle", local_ip: str, local_port: Optional[int] = None,
                            timeout: float = 0.1) -> None:
        if handle.udp_socket is not None:
            return
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        port = local_port if local_port is not None else 0
        sock.bind((local_ip, port))
        sock.settimeout(timeout)
        handle.udp_socket = sock

    def send_udp(self, handle: "_SomeipSocketLib.Handle", data: bytes, ip: str, port: int) -> None:
        if not handle.udp_socket:
            raise RuntimeError("UDP socket not initialized, call set_local_endpoint first")
        handle.udp_socket.sendto(data, (ip, port))

    def recv_udp(self, handle: "_SomeipSocketLib.Handle", bufsize: int = 4096,
                 timeout: float = 0.1) -> Optional[Tuple[bytes, Tuple[str, int]]]:
        if not handle.udp_socket:
            raise RuntimeError("UDP socket not initialized, call set_local_endpoint first")
        # 临时修改超时时间，避免影响外部配置
        old_timeout = handle.udp_socket.gettimeout()
        try:
            handle.udp_socket.settimeout(timeout)
            data, addr = handle.udp_socket.recvfrom(bufsize)
            return data, addr
        except socket.timeout:
            return None
        finally:
            handle.udp_socket.settimeout(old_timeout)


class SomeipSession:
    """SOME/IP 会话层，负责管理 UDP socket、会话 ID、请求/响应与事件通知。

    - 使用 `_SomeipSocketLib` 作为默认底层实现；
    - 对外暴露同步阻塞接口，便于和 DoipSession 风格统一。
    """

    def __init__(
        self,
        local_ip: str = "0.0.0.0",
        local_port: Optional[int] = None,
        default_remote_ip: Optional[str] = None,
        default_remote_port: Optional[int] = None,
        client_id: int = 0x1000,
    ) -> None:
        self._lib = _SomeipSocketLib()
        self._handle = self._lib.create_client()

        self._local_ip = local_ip
        self._local_port = local_port
        self._default_remote_ip = default_remote_ip
        self._default_remote_port = default_remote_port
        self._client_id = client_id

        self._session_counter = 0
        self._running = False
        self._recv_thread: Optional[threading.Thread] = None

        # 事件/通知处理
        self._notification_handlers: Dict[Tuple[int, int], Callable[["SOMEIPMessage", Tuple[str, int]], None]] = {}

        # pending responses: session_id -> dict with fields {"event", "response"}
        self._pending_lock = threading.Lock()
        self._pending_responses: Dict[int, Dict[str, Any]] = {}

        # 已发现服务（可手动注入）
        self.discovered_services: Dict[int, Tuple[str, int]] = {}

        # 初始化本地端口
        self._lib.set_local_endpoint(self._handle, self._local_ip, self._local_port)

    # --------- 生命周期管理 ---------

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._recv_thread = threading.Thread(target=self._receive_loop, name="SomeipRecv", daemon=True)
        self._recv_thread.start()

    def close(self) -> None:
        self._running = False
        if self._recv_thread and self._recv_thread.is_alive():
            self._recv_thread.join(timeout=1.0)
        self._lib.destroy_client(self._handle)

    # --------- 辅助 ---------

    def _get_next_session(self) -> int:
        self._session_counter = (self._session_counter + 1) & 0xFFFFFFFF
        return self._session_counter

    # --------- 对外接口 ---------

    def register_notification_handler(self, service_id: int, event_id: int,
                                      handler: Callable[["SOMEIPMessage", Tuple[str, int]], None]) -> None:
        self._notification_handlers[(service_id, event_id)] = handler

    def send_raw(self, data: bytes, ip: Optional[str] = None, port: Optional[int] = None) -> None:
        """直接发送原始 SOME/IP 报文（包含头和负载）

        该接口适合你已经构造好完整 SOME/IP bytes 的场景，类似于“发送原始 UDS 帧”。
        """
        if ip is None or port is None:
            ip, port = self._default_remote_ip, self._default_remote_port
        if ip is None or port is None:
            raise ValueError("No remote endpoint specified for raw SOME/IP message")
        self._lib.send_udp(self._handle, data, ip, port)

    def send_message(self, msg: "SOMEIPMessage", ip: Optional[str] = None, port: Optional[int] = None) -> None:
        if ip is None or port is None:
            if msg.service_id in self.discovered_services:
                ip, port = self.discovered_services[msg.service_id]
            else:
                ip, port = self._default_remote_ip, self._default_remote_port
        if ip is None or port is None:
            raise ValueError("No remote endpoint specified for SOME/IP message")

        self._lib.send_udp(self._handle, msg.build(), ip, port)

    def request(self, service_id: int, method_id: int, payload: bytes = b"",
                ip: Optional[str] = None, port: Optional[int] = None,
                timeout: float = 5.0) -> Optional["SOMEIPMessage"]:
        """发送请求并等待响应，内部通过 pending_responses 与接收线程协作。"""
        # 构造请求
        req = SOMEIPMessage()
        req.service_id = service_id
        req.method_id = method_id
        req.client_id = self._client_id
        req.session_id = self._get_next_session()
        req.message_type = MessageType.REQUEST
        req.return_code = ReturnCode.OK
        req.payload = payload or b""

        # 注册 pending
        event = threading.Event()
        with self._pending_lock:
            self._pending_responses[req.session_id] = {"event": event, "response": None}

        # 发送
        self.send_message(req, ip, port)

        # 等待
        if not event.wait(timeout):
            with self._pending_lock:
                self._pending_responses.pop(req.session_id, None)
            return None

        with self._pending_lock:
            entry = self._pending_responses.pop(req.session_id, None)
        if not entry:
            return None
        return entry.get("response")

    def subscribe_event(self, service_id: int, event_id: int,
                        ip: Optional[str] = None, port: Optional[int] = None,
                        handler: Optional[Callable[["SOMEIPMessage", Tuple[str, int]], None]] = None) -> bool:
        """订阅 SOME/IP 事件。

        - 这里重用原 SOMEIPClient 的订阅报文格式（简化版）。
        - 仅做发送+本地 handler 注册，不做复杂 SD 状态机。
        """
        sub_msg = SOMEIPMessage()
        sub_msg.service_id = service_id
        sub_msg.method_id = event_id
        sub_msg.client_id = self._client_id
        sub_msg.session_id = self._get_next_session()
        sub_msg.message_type = MessageType.REQUEST
        sub_msg.return_code = ReturnCode.OK
        sub_msg.payload = struct.pack('>I', 0x00000001)

        if handler is not None:
            self.register_notification_handler(service_id, event_id, handler)

        try:
            self.send_message(sub_msg, ip, port)
            return True
        except Exception:
            return False

    # --------- 接收循环 ---------

    def _receive_loop(self) -> None:
        while self._running:
            try:
                result = self._lib.recv_udp(self._handle, bufsize=4096, timeout=0.1)
                if result is None:
                    continue
                data, addr = result
                self._handle_message(data, addr)
            except Exception:
                if self._running:
                    # 为了保持安静，这里不打印详细异常；如需调试可加日志
                    continue

    def _handle_message(self, data: bytes, addr: Tuple[str, int]) -> None:
        try:
            msg = SOMEIPMessage(data)
        except Exception:
            return

        # 通知
        if msg.message_type == MessageType.NOTIFICATION:
            handler = self._notification_handlers.get((msg.service_id, msg.method_id))
            if handler:
                try:
                    handler(msg, addr)
                except Exception:
                    pass
            return

        # 响应
        if msg.message_type in (MessageType.RESPONSE, MessageType.ERROR):
            with self._pending_lock:
                entry = self._pending_responses.get(msg.session_id)
                if entry:
                    entry["response"] = msg
                    entry["event"].set()


class SomeipClient:
    """对外使用的 SOME/IP 客户端，高层封装，风格靠近 DoipClient。

    示例：
        client = SomeipClient(ip="127.0.0.1", port=30500, client_id=0x1000)
        client.connect()
        resp = client.send_request(0x1234, 0x0001, b"Hello")
    """

    def __init__(
        self,
        ip: str,
        port: int,
        client_id: int = 0x1000,
        local_ip: str = "0.0.0.0",
        local_port: Optional[int] = None,
    ) -> None:
        self._remote_ip = ip
        self._remote_port = int(port)
        self._session = SomeipSession(
            local_ip=local_ip,
            local_port=local_port,
            default_remote_ip=self._remote_ip,
            default_remote_port=self._remote_port,
            client_id=client_id,
        )

    def connect(self) -> None:
        self._session.start()

    def close(self) -> None:
        self._session.close()

    def send_request(self, service_id: int, method_id: int,
                     payload: bytes = b"", timeout: float = 5.0) -> Optional["SOMEIPMessage"]:
        return self._session.request(
            service_id=service_id,
            method_id=method_id,
            payload=payload,
            ip=self._remote_ip,
            port=self._remote_port,
            timeout=timeout,
        )

    def subscribe(self, service_id: int, event_id: int,
                  handler: Callable[["SOMEIPMessage", Tuple[str, int]], None]) -> bool:
        return self._session.subscribe_event(
            service_id=service_id,
            event_id=event_id,
            ip=self._remote_ip,
            port=self._remote_port,
            handler=handler,
        )

    # ========= UDS 风格便捷接口 =========

    def send_raw_someip(self, data: bytes) -> None:
        """发送原始 SOME/IP 报文（已经包含完整 SOME/IP 头）

        用法：
            raw = SOMEIPMessage(...).build()
            client.send_raw_someip(raw)
        """
        self._session.send_raw(data, ip=self._remote_ip, port=self._remote_port)

    def send_uds_request(self, service_id: int, method_id: int, uds_payload: bytes,
                          timeout: float = 5.0) -> Optional["SOMEIPMessage"]:
        """类似 DoipClient.request 的 UDS 风格接口

        - service_id/method_id 指定 SOME/IP 服务与方法；
        - uds_payload 为 UDS 数据区（实际就是 SOME/IP payload 部分）；
        - 返回 SOMEIPMessage，调用方可从 .payload 中取出 UDS 响应数据。
        """
        return self.send_request(service_id, method_id, payload=uds_payload, timeout=timeout)


# ===== 保留原 SOMEIPClient 以兼容旧代码 =====
# 注意：建议新代码使用上面的 SomeipClient / SomeipSession。

class SOMEIPClient:
    """向后兼容的 SOME/IP 客户端，内部基于 SomeipSession 实现。

    保留原有常用 API：start/stop/send_request/subscribe_event/discovered_services。
    """

    def __init__(self, client_id: int = 0x1000):
        self._session = SomeipSession(client_id=client_id)
        self.client_id = client_id
        # 暴露 discovered_services 引用，保持原有用法
        self.discovered_services = self._session.discovered_services

    def start(self, local_ip: str = "0.0.0.0") -> None:
        # 重新配置本地绑定（简单实现：重新创建 session）
        # 为了不破坏外部行为，这里在第一次 start 时重建 session
        if self._session._local_ip != local_ip:
            # 重新初始化 session
            client_id = self.client_id
            self._session.close()
            self._session = SomeipSession(local_ip=local_ip, client_id=client_id)
            self.discovered_services = self._session.discovered_services
        self._session.start()
        print(f"SOME/IP Client started on {local_ip}")

    def stop(self) -> None:
        self._session.close()
        print("SOME/IP Client stopped")

    def send_request(self, service_id: int, method_id: int,
                     payload: bytes = b"",
                     ip: Optional[str] = None, port: Optional[int] = None,
                     timeout: float = 5.0) -> Optional["SOMEIPMessage"]:
        # 与旧版保持行为：如果没给 ip/port，则尝试 discovered_services
        return self._session.request(service_id, method_id, payload, ip, port, timeout)

    def subscribe_event(self, service_id: int, event_id: int,
                        ip: Optional[str] = None, port: Optional[int] = None,
                        handler: Optional[Callable[["SOMEIPMessage", Tuple[str, int]], None]] = None) -> bool:
        return self._session.subscribe_event(service_id, event_id, ip, port, handler)


def main():
    # 示例使用新的 SomeipClient
    client = SomeipClient(ip="127.0.0.1", port=30500, client_id=0x1000)

    def handle_event(msg: SOMEIPMessage, addr: tuple):
        print(f"[Event] From {addr}: Service=0x{msg.service_id:04X}, "
              f"Event=0x{msg.method_id:04X}, Payload={msg.payload.hex()}")

    try:
        client.connect()
        # 订阅
        client.subscribe(0x1234, 0x8001, handler=handle_event)

        # 发送请求
        resp = client.send_request(0x1234, 0x0001, b"Hello SOME/IP")
        if resp:
            print(f"Response received: {resp}")
    finally:
        client.close()


if __name__ == "__main__":
    main()

