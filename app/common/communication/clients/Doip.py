# DOIP over UDS 客户端封装

import threading
import ctypes
import os
from typing import Optional


# ==========================
# 异常与常量定义
# ==========================


class DoipError(Exception):
    """DOIP 通用错误"""


class DoipConnectionError(DoipError):
    """连接相关错误（TCP 连接失败、断开等）"""


class DoipTimeoutError(DoipError):
    """超时错误（Routing Activation 或 诊断响应超时）"""


class DoipProtocolError(DoipError):
    """协议层错误（报文格式、返回码等）"""


DOIP_DEFAULT_PORT = 13400
DOIP_DEFAULT_TIMEOUT_MS = 2000
DOIP_DEFAULT_KEEPALIVE_INTERVAL_MS = 5000


# ==========================
# DLL 封装层
# ==========================


class _DoipLib:
    """对 psi_diagnostic.dll 进行 ctypes 封装的内部类

    说明：
    - 这里根据头文件进行函数签名绑定时，你需要对照实际的 doip_client.h / diag_client.h 微调。
    - 此类的职责：
      * 加载 DLL
      * 绑定需要用到的 C 函数
      * 将返回码转换为 Python 异常
    """

    _instance: Optional["_DoipLib"] = None

    def __init__(self, dll_path: Optional[str] = None) -> None:
        if dll_path is None:
            # 默认从项目下常见位置查找 dll，可按实际路径调整
            # 这里假定项目根目录为 four levels up: .../oneboxforgac/
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
            candidates = [
                # 优先从项目根目录下的 lib 目录查找
                os.path.join(project_root, "lib", "psi_diagnostic.dll"),
                # 其次从当前文件所在目录查找
                os.path.join(os.path.dirname(__file__), "psi_diagnostic.dll"),
                # 最后从当前工作目录查找
                "psi_diagnostic.dll",
            ]
            for p in candidates:
                if os.path.isfile(p):
                    dll_path = p
                    break
        if not dll_path or not os.path.isfile(dll_path):
            raise DoipError(f"无法找到 psi_diagnostic.dll，请检查 DLL 路径: {dll_path!r}")

        # Windows 环境加载 DLL
        self._dll = ctypes.WinDLL(dll_path)

        # 绑定 C 函数签名（这里是示意，需根据实际头文件调整）
        self._bind_functions()

    @classmethod
    def instance(cls, dll_path: Optional[str] = None) -> "_DoipLib":
        if cls._instance is None:
            cls._instance = cls(dll_path)
        return cls._instance

    # --------- C 函数绑定与调用包装 ---------

    def _bind_functions(self) -> None:
        """绑定需要的 C 函数签名

        注意：这里的函数名/参数列表是根据常见 DOIP SDK 推断的，需要你根据
        include/diag/doip/doip_client.h 中的实际声明做对应修改。
        """
        dll = self._dll

        # client 句柄类型：void*
        self._handle_t = ctypes.c_void_p

        # int doip_client_create(doip_client_handle* out_handle)
        if hasattr(dll, "doip_client_create"):
            dll.doip_client_create.argtypes = [ctypes.POINTER(self._handle_t)]
            dll.doip_client_create.restype = ctypes.c_int

        # int doip_client_destroy(doip_client_handle handle)
        if hasattr(dll, "doip_client_destroy"):
            dll.doip_client_destroy.argtypes = [self._handle_t]
            dll.doip_client_destroy.restype = ctypes.c_int

        # int doip_client_set_target(doip_client_handle h, const char* ip, uint16_t port)
        if hasattr(dll, "doip_client_set_target"):
            dll.doip_client_set_target.argtypes = [self._handle_t, ctypes.c_char_p, ctypes.c_uint16]
            dll.doip_client_set_target.restype = ctypes.c_int

        # int doip_client_set_timeout(doip_client_handle h, uint32_t ms)
        if hasattr(dll, "doip_client_set_timeout"):
            dll.doip_client_set_timeout.argtypes = [self._handle_t, ctypes.c_uint32]
            dll.doip_client_set_timeout.restype = ctypes.c_int

        # int doip_client_connect(doip_client_handle h)
        if hasattr(dll, "doip_client_connect"):
            dll.doip_client_connect.argtypes = [self._handle_t]
            dll.doip_client_connect.restype = ctypes.c_int

        # int doip_client_disconnect(doip_client_handle h)
        if hasattr(dll, "doip_client_disconnect"):
            dll.doip_client_disconnect.argtypes = [self._handle_t]
            dll.doip_client_disconnect.restype = ctypes.c_int

        # int doip_client_routing_activation(doip_client_handle h, uint16_t sa, uint16_t ta, uint8_t activation_type, uint32_t timeout_ms)
        if hasattr(dll, "doip_client_routing_activation"):
            dll.doip_client_routing_activation.argtypes = [
                self._handle_t,
                ctypes.c_uint16,
                ctypes.c_uint16,
                ctypes.c_uint8,
                ctypes.c_uint32,
            ]
            dll.doip_client_routing_activation.restype = ctypes.c_int

        # int doip_client_send_diag_request(doip_client_handle h, const uint8_t* data, uint16_t len)
        if hasattr(dll, "doip_client_send_diag_request"):
            dll.doip_client_send_diag_request.argtypes = [
                self._handle_t,
                ctypes.POINTER(ctypes.c_uint8),
                ctypes.c_uint16,
            ]
            dll.doip_client_send_diag_request.restype = ctypes.c_int

        # int doip_client_recv_diag_response(doip_client_handle h, uint8_t* buf, uint16_t buf_size, uint16_t* out_len, uint32_t timeout_ms)
        if hasattr(dll, "doip_client_recv_diag_response"):
            dll.doip_client_recv_diag_response.argtypes = [
                self._handle_t,
                ctypes.POINTER(ctypes.c_uint8),
                ctypes.c_uint16,
                ctypes.POINTER(ctypes.c_uint16),
                ctypes.c_uint32,
            ]
            dll.doip_client_recv_diag_response.restype = ctypes.c_int

        # 可选：KeepAlive / AliveCheck
        if hasattr(dll, "doip_client_send_alive_check"):
            dll.doip_client_send_alive_check.argtypes = [self._handle_t]
            dll.doip_client_send_alive_check.restype = ctypes.c_int

    # --------- 对外包装方法（抛出 Python 异常） ---------

    def _check_ret(self, ret: int, func: str) -> None:
        if ret == 0:
            return
        # 根据实际错误码区分不同异常，这里先简单分类
        if ret == -1:
            raise DoipConnectionError(f"{func} 失败: 连接错误, code={ret}")
        if ret == -2:
            raise DoipTimeoutError(f"{func} 失败: 超时, code={ret}")
        if ret == -3:
            raise DoipProtocolError(f"{func} 失败: 协议错误, code={ret}")
        raise DoipError(f"{func} 调用失败, 返回码={ret}")

    def create_client(self) -> ctypes.c_void_p:
        handle = self._handle_t()
        ret = self._dll.doip_client_create(ctypes.byref(handle))
        self._check_ret(ret, "doip_client_create")
        return handle

    def destroy_client(self, handle: ctypes.c_void_p) -> None:
        if not handle:
            return
        ret = self._dll.doip_client_destroy(handle)
        self._check_ret(ret, "doip_client_destroy")

    def set_target(self, handle: ctypes.c_void_p, ip: str, port: int) -> None:
        ip_bytes = ip.encode("ascii")
        ret = self._dll.doip_client_set_target(handle, ip_bytes, ctypes.c_uint16(port))
        self._check_ret(ret, "doip_client_set_target")

    def set_timeout(self, handle: ctypes.c_void_p, timeout_ms: int) -> None:
        if hasattr(self._dll, "doip_client_set_timeout"):
            ret = self._dll.doip_client_set_timeout(handle, ctypes.c_uint32(timeout_ms))
            self._check_ret(ret, "doip_client_set_timeout")

    def connect(self, handle: ctypes.c_void_p) -> None:
        ret = self._dll.doip_client_connect(handle)
        self._check_ret(ret, "doip_client_connect")

    def disconnect(self, handle: ctypes.c_void_p) -> None:
        if not handle:
            return
        if hasattr(self._dll, "doip_client_disconnect"):
            ret = self._dll.doip_client_disconnect(handle)
            self._check_ret(ret, "doip_client_disconnect")

    def routing_activation(self, handle: ctypes.c_void_p, source_addr: int, target_addr: int, activation_type: int, timeout_ms: int) -> None:
        if not hasattr(self._dll, "doip_client_routing_activation"):
            raise DoipError("DLL 中未找到 doip_client_routing_activation 函数，请检查 SDK 版本")
        ret = self._dll.doip_client_routing_activation(
            handle,
            ctypes.c_uint16(source_addr),
            ctypes.c_uint16(target_addr),  # 修正变量名
            ctypes.c_uint8(activation_type),
            ctypes.c_uint32(timeout_ms),
        )
        self._check_ret(ret, "doip_client_routing_activation")

    def send_diag_request(self, handle: ctypes.c_void_p, uds_payload: bytes) -> None:
        if not hasattr(self._dll, "doip_client_send_diag_request"):
            raise DoipError("DLL 中未找到 doip_client_send_diag_request 函数，请检查 SDK 版本")
        length = len(uds_payload)
        if length == 0:
            raise ValueError("UDS 请求数据不能为空")
        buf_type = ctypes.c_uint8 * length
        buf = buf_type.from_buffer_copy(uds_payload)
        ret = self._dll.doip_client_send_diag_request(handle, buf, ctypes.c_uint16(length))
        self._check_ret(ret, "doip_client_send_diag_request")

    def recv_diag_response(self, handle: ctypes.c_void_p, timeout_ms: int, max_len: int = 4096) -> bytes:
        if not hasattr(self._dll, "doip_client_recv_diag_response"):
            raise DoipError("DLL 中未找到 doip_client_recv_diag_response 函数，请检查 SDK 版本")
        buf_type = ctypes.c_uint8 * max_len
        buf = buf_type()
        out_len = ctypes.c_uint16(0)
        ret = self._dll.doip_client_recv_diag_response(
            handle,
            buf,
            ctypes.c_uint16(max_len),
            ctypes.byref(out_len),
            ctypes.c_uint32(timeout_ms),
        )
        self._check_ret(ret, "doip_client_recv_diag_response")
        return bytes(buf[: out_len.value])

    def send_alive_check(self, handle: ctypes.c_void_p) -> None:
        if not hasattr(self._dll, "doip_client_send_alive_check"):
            # 部分 SDK 可能没有该函数，则忽略
            return
        ret = self._dll.doip_client_send_alive_check(handle)
        self._check_ret(ret, "doip_client_send_alive_check")


# ==========================
# 会话层：DoipSession
# ==========================


class DoipSession:
    """表示一个 DOIP/UDS 会话（与一个 ECU 的连接实例）

    - 负责建立/断开连接
    - 完成 Routing Activation
    - 发送/接收 DOIP on UDS 报文
    - 可选 KeepAlive 线程保持连接
    """

    def __init__(
        self,
        ip: str,
        port: int = DOIP_DEFAULT_PORT,
        source_addr: int = 0x0E00,
        target_addr: int = 0x0E01,
        timeout_ms: int = DOIP_DEFAULT_TIMEOUT_MS,
        keepalive_interval_ms: Optional[int] = DOIP_DEFAULT_KEEPALIVE_INTERVAL_MS,
        dll_path: Optional[str] = None,
    ) -> None:
        self._lib = _DoipLib.instance(dll_path)
        self._handle = self._lib.create_client()

        self._ip = ip
        self._port = int(port)
        self._source_addr = int(source_addr)
        self._target_addr = int(target_addr)
        self._timeout_ms = int(timeout_ms)
        self._keepalive_interval_ms = keepalive_interval_ms

        self._connected = False
        self._routing_activated = False
        self._closed = False

        self._lock = threading.Lock()
        self._keepalive_thread: Optional[threading.Thread] = None
        self._keepalive_stop_event = threading.Event()

        # 初始化目标与超时
        self._lib.set_target(self._handle, self._ip, self._port)
        self._lib.set_timeout(self._handle, self._timeout_ms)

    # --------- 上下文管理 ---------

    def __enter__(self) -> "DoipSession":
        # 默认仅返回自身，不强制自动连接；由调用侧明确调用 connect/routing_activation
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            # 避免析构阶段抛异常
            pass

    # --------- 连接与 Routing Activation ---------

    def connect(self) -> None:
        if self._closed:
            raise DoipError("会话已关闭，不能再次连接")
        if self._connected:
            return
        self._lib.connect(self._handle)
        self._connected = True
        self._start_keepalive_thread()

    def routing_activation(self, activation_type: int = 0x00) -> None:
        if not self._connected:
            raise DoipConnectionError("尚未建立 TCP 连接，无法进行 Routing Activation")
        if self._routing_activated:
            return
        self._lib.routing_activation(
            self._handle,
            self._source_addr,
            self._target_addr,
            activation_type,
            self._timeout_ms,
        )
        self._routing_activated = True

    # --------- 发送 / 接收 UDS 报文 ---------

    def send_request(self, uds_payload: bytes) -> None:
        if not self._connected:
            raise DoipConnectionError("尚未连接，无法发送请求")
        if not self._routing_activated:
            raise DoipProtocolError("尚未进行 Routing Activation，无法发送诊断请求")
        if not isinstance(uds_payload, (bytes, bytearray)):
            raise TypeError("uds_payload 必须是 bytes 或 bytearray")

        with self._lock:
            self._lib.send_diag_request(self._handle, bytes(uds_payload))

    def receive_response(self, timeout_ms: Optional[int] = None) -> bytes:
        if not self._connected:
            raise DoipConnectionError("尚未连接，无法接收响应")
        if not self._routing_activated:
            raise DoipProtocolError("尚未进行 Routing Activation，无法接收诊断响应")

        to = int(timeout_ms if timeout_ms is not None else self._timeout_ms)
        if to <= 0:
            raise ValueError("timeout_ms 必须为正整数")

        with self._lock:
            return self._lib.recv_diag_response(self._handle, to)

    def send_and_receive(self, uds_payload: bytes, timeout_ms: Optional[int] = None) -> bytes:
        """同步发送 UDS 请求并等待响应

        :param uds_payload: UDS 数据区（不含任何 DOIP/ISO-TP 头），如 b"\x10\x03"
        :param timeout_ms: 覆盖默认超时（毫秒）
        :return: UDS 响应数据区（不含 DOIP 头）
        """
        self.send_request(uds_payload)
        return self.receive_response(timeout_ms)

    # --------- KeepAlive 管理 ---------

    def _start_keepalive_thread(self) -> None:
        interval = self._keepalive_interval_ms
        if interval is None or interval <= 0:
            return
        if self._keepalive_thread and self._keepalive_thread.is_alive():
            return

        self._keepalive_stop_event.clear()

        def _worker() -> None:
            while not self._keepalive_stop_event.wait(interval / 1000.0):
                if self._closed or not self._connected:
                    break
                try:
                    self._lib.send_alive_check(self._handle)
                except DoipError:
                    # 这里不抛出到外层，只是保持连接；具体日志可集成到项目 logger 中
                    continue

        t = threading.Thread(target=_worker, name="DoipKeepAlive", daemon=True)
        self._keepalive_thread = t
        t.start()

    def _stop_keepalive_thread(self) -> None:
        if self._keepalive_thread and self._keepalive_thread.is_alive():
            self._keepalive_stop_event.set()
            self._keepalive_thread.join(timeout=1.0)
        self._keepalive_thread = None

    # --------- 关闭与状态 ---------

    def close(self) -> None:
        if self._closed:
            return
        self._stop_keepalive_thread()
        if self._connected:
            try:
                self._lib.disconnect(self._handle)
            except DoipError:
                # 忽略断开错误，继续销毁 client
                pass
        try:
            self._lib.destroy_client(self._handle)
        finally:
            self._handle = None
            self._connected = False
            self._routing_activated = False
            self._closed = True

    def is_connected(self) -> bool:
        return self._connected and not self._closed

    def is_routing_activated(self) -> bool:
        return self._routing_activated and self.is_connected()

    def get_config(self) -> dict:
        return {
            "ip": self._ip,
            "port": self._port,
            "source_addr": self._source_addr,
            "target_addr": self._target_addr,
            "timeout_ms": self._timeout_ms,
            "keepalive_interval_ms": self._keepalive_interval_ms,
        }


# ==========================
# 高层客户端接口：DoipClient
# ==========================


class DoipClient:
    """给外部模块使用的 DOIP on UDS 客户端

    - 对外只暴露 UDS 数据区的收发接口
    - 内部基于 DoipSession 管理连接与 Routing Activation
    """

    def __init__(
        self,
        ip: str,
        port: int = DOIP_DEFAULT_PORT,
        source_addr: int = 0x0E00,
        target_addr: int = 0x0E01,
        timeout_ms: int = DOIP_DEFAULT_TIMEOUT_MS,
        keepalive_interval_ms: Optional[int] = DOIP_DEFAULT_KEEPALIVE_INTERVAL_MS,
        dll_path: Optional[str] = None,
    ) -> None:
        self._session = DoipSession(
            ip=ip,
            port=port,
            source_addr=source_addr,
            target_addr=target_addr,
            timeout_ms=timeout_ms,
            keepalive_interval_ms=keepalive_interval_ms,
            dll_path=dll_path,
        )

    # 简化的会话控制方法

    def open_session(self, activation_type: int = 0x00) -> None:
        """建立连接并完成 Routing Activation

        使用示例：
            client = DoipClient("192.168.0.10")
            client.open_session()
        """
        self._session.connect()
        self._session.routing_activation(activation_type)

    def request(self, uds_payload: bytes, timeout_ms: Optional[int] = None) -> bytes:
        """发送 UDS 请求并等待响应

        :param uds_payload: 仅 UDS 数据区，例如 b"\x10\x03"、b"\x22\xF1\x90" 等
        :param timeout_ms: 单次请求超时，可覆盖默认会话超时
        :return: UDS 响应 payload（不含 DOIP 头）
        """
        return self._session.send_and_receive(uds_payload, timeout_ms)

    def disconnect(self) -> None:
        self._session.close()

    # 可选：暴露一些常见 UDS 服务的便捷方法（根据业务需要自行扩展）

    def diagnostic_session_control(self, session_type: int, timeout_ms: Optional[int] = None) -> bytes:
        """UDS 0x10 Diagnostic Session Control 便捷方法"""
        payload = bytes([0x10, session_type & 0xFF])
        return self.request(payload, timeout_ms)

    def read_data_by_identifier(self, did: int, timeout_ms: Optional[int] = None) -> bytes:
        """UDS 0x22 ReadDataByIdentifier 便捷方法

        :param timeout_ms:
        :param did: 0x0000 ~ 0xFFFF 的 DID
        """
        did_high = (did >> 8) & 0xFF
        did_low = did & 0xFF
        payload = bytes([0x22, did_high, did_low])
        return self.request(payload, timeout_ms)

    def clear_diagnostic_information(self, group_of_dtc: int = 0xFFFFFF, timeout_ms: Optional[int] = None) -> bytes:
        """UDS 0x14 ClearDiagnosticInformation 便捷方法

        :param timeout_ms:
        :param group_of_dtc: 24bit DTC 组（常见为 0xFFFFFF 表示所有）
        """
        b1 = (group_of_dtc >> 16) & 0xFF
        b2 = (group_of_dtc >> 8) & 0xFF
        b3 = group_of_dtc & 0xFF
        payload = bytes([0x14, b1, b2, b3])
        return self.request(payload, timeout_ms)

    def test_connection(self, timeout_ms: Optional[int] = None) -> bool:
        """执行一次简单的 DoIP 连通性测试。

        整体流程：
        1. 建立 TCP 连接
        2. 执行 Routing Activation
        3. 发送一条最简单的 UDS 请求（这里使用 0x10 默认会话）
        4. 校验是否收到合法的阳性响应

        :param timeout_ms: 覆盖默认超时时间（毫秒），若为 None 则使用会话默认超时
        :return: True 表示测试成功，False 表示任一步失败
        """
        # 若未指定单次请求超时，则使用会话默认配置
        if timeout_ms is None:
            timeout_ms = self._session._timeout_ms  # 这里访问内部字段仅用于测试，不修改状态

        success = False
        try:
            print("[DoIP] 开始连接测试...")
            # 1. 建立 TCP 连接
            print("[DoIP] 正在建立 TCP 连接...")
            self._session.connect()
            print("[DoIP] TCP 连接建立成功。")

            # 2. Routing Activation
            print("[DoIP] 正在执行 Routing Activation...")
            self._session.routing_activation(activation_type=0x00)
            print("[DoIP] Routing Activation 成功。")

            # 3. 发送一条最简单的 UDS 请求：0x10 0x01（默认会话）
            request_payload = bytes([0x10, 0x01])
            print(f"[DoIP] 发送 UDS 请求: {request_payload.hex(' ')}")
            response = self._session.send_and_receive(request_payload, timeout_ms=timeout_ms)
            print(f"[DoIP] 收到 UDS 响应: {response.hex(' ')}")

            # 4. 校验响应：UDS 阳性响应服务 ID = 请求服务 ID + 0x40，即 0x50
            if not response:
                print("[DoIP] 响应为空，连接测试失败。")
                return False

            if response[0] != 0x50:
                print(f"[DoIP] 首字节不是预期的 0x50（实际为 0x{response[0]:02X}），可能为否定响应或其它服务，连接测试失败。")
                return False

            print("[DoIP] 成功收到 0x10 服务的阳性响应，连接测试通过。")
            success = True
            return True
        except DoipTimeoutError as e:
            print(f"[DoIP] 测试过程中发生超时：{e}")
            return False
        except DoipConnectionError as e:
            print(f"[DoIP] 连接失败：{e}")
            return False
        except DoipProtocolError as e:
            print(f"[DoIP] 协议错误：{e}")
            return False
        except DoipError as e:
            print(f"[DoIP] DOIP 通用错误：{e}")
            return False
        except Exception as e:
            # 捕获所有未预料异常，避免测试方法直接抛出
            print(f"[DoIP] 未预期异常：{e}")
            return False
        finally:
            # 无论成功或失败，都尝试断开连接，避免资源泄漏
            try:
                self.disconnect()
                print("[DoIP] 已关闭会话连接。")
            except Exception as e:
                # 关闭异常只做提示，不改变 success 结果
                print(f"[DoIP] 关闭连接时发生异常（已忽略）：{e}")


if __name__ == "__main__":
    """简单命令行测试入口

    直接运行本文件，将使用 IP=10.1.0.79、默认 DOIP 端口尝试进行一次连通性测试。
    若需要修改 IP/端口，可直接修改下面的默认变量，或根据需要扩展为命令行参数解析。
    """

    test_ip = "10.1.0.79"
    test_port = DOIP_DEFAULT_PORT

    print(f"[DoIP] 准备对 {test_ip}:{test_port} 执行连接测试...")
    client = DoipClient(ip=test_ip, port=test_port)
    ok = client.test_connection()

    if ok:
        print("[DoIP] 连接测试成功：已成功完成 DoIP 连接与基本 UDS 交互。")
    else:
        print("[DoIP] 连接测试失败：请检查 IP/端口、网络连通性、ECU 上电状态或 DLL 配置。")
