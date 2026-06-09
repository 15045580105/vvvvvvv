import logging
import time
import socket
import threading
import ipaddress
import psutil
from typing import Dict, Any, Optional

from PyQt5.QtCore import QObject, pyqtSignal
from paramiko.ssh_exception import AuthenticationException, SSHException

from app.common.communication.clients.Doip_Client import DoIPClientHandler
from app.common.communication.clients.Someip_Client import SomeIPClient
from app.common.communication.clients.ssh_client import SSHClient
from app.common.utils.security_access_helper import SecurityAccessHelper
from app.core.dependency_injection import di_container
from app.modules.device_management.models.device_model import CONNECTING, DISCONNECTED, CONNECT_FAILED, OFFLINE
from app.services.configuration.config_service import AppConfigurationService


logger = logging.getLogger(__name__)


class DeviceService(QObject):
    # 文本日志信号
    log_signal = pyqtSignal(str)
    # 协议状态变更信号：payload 为包含 ip/port 及各协议状态字段的 device dict
    protocol_status_changed_signal = pyqtSignal(dict)
    # 新增: 申请重连信号，参数为设备信息, 日志信号
    reconnect_requested_signal = pyqtSignal(dict, object)

    # 设备操作进度信号：payload 为文本描述
    """设备管理领域的 Service 层封装。"""

    def __init__(self) -> None:
        super().__init__()
        # 独立的 DoIP / SomeIP /SSH 客户端实例，由 DeviceService 统一管理生命周期
        self._doip_handler: DoIPClientHandler | None = None
        self._someip_client: SomeIPClient | None = None
        self._ssh_client: SSHClient | None = None

        # 记录最后一次连接的设备配置，用于断线重连
        self._last_connected_device: Dict[str, Any] | None = None

        self._config_service = di_container.resolve(AppConfigurationService)
        if not self._config_service:
            self._config_service = AppConfigurationService()
            di_container.register_singleton(AppConfigurationService, self._config_service)

        self._cleanup_lock = threading.Lock()
        self._cleanup_thread: Optional[threading.Thread] = None
        self._connection_generation = 0

    def _get_log_emit(self, log_signal: Optional[object] = None):
        """统一返回日志输出函数，兼容 PyQtBoundSignal / callable。"""
        if log_signal is not None:
            emit = getattr(log_signal, "emit", None)
            if callable(emit):
                return emit
            if callable(log_signal):
                return log_signal
        return getattr(self.log_signal, "emit")

    def _debug_log(self, message: str) -> None:
        """仅输出到控制台/调试日志，不进入前端操作日志。"""
        logger.info(message)

    def _bump_connection_generation(self, reason: str, device: Optional[Dict[str, Any]] = None) -> int:
        """为一次新的连接上下文分配代际号。

        目的：
        1. 让重连前后的 DoIP/SSH/SomeIP 生命周期可观测；
        2. 排查“页面显示已连接，但业务模块还拿着旧连接对象”的问题时，
           能快速从日志判断当前操作属于哪一代连接上下文。
        """
        self._connection_generation += 1
        device_text = ""
        if device:
            device_text = f" -> {device.get('ip', '')}:{device.get('port', 22)}"
        self._debug_log(f"[连接上下文] generation={self._connection_generation} | reason={reason}{device_text}")
        return self._connection_generation

    def get_connection_context(self) -> Dict[str, Any]:
        """返回当前连接上下文快照，供控制器/服务日志使用。"""
        active_service = self._get_active_service()
        if active_service is not self:
            return active_service.get_connection_context()

        ssh_connected = bool(self._ssh_client and self._ssh_client.is_connected())
        doip_connected = bool(self._doip_handler and getattr(self._doip_handler, "connected", False))
        someip_client = self._someip_client
        someip_running = bool(someip_client and getattr(someip_client, "running", False))
        current_ip = None
        if self._last_connected_device:
            current_ip = self._last_connected_device.get("ip")

        return {
            "generation": self._connection_generation,
            "ip": current_ip,
            "ssh_connected": ssh_connected,
            "doip_connected": doip_connected,
            "someip_connected": someip_running,
        }

    def _format_connection_context_text(self) -> str:
        ctx = self.get_connection_context()
        return (
            f"generation={ctx.get('generation', 0)} | ip={ctx.get('ip') or '--'} | "
            f"SSH={'Y' if ctx.get('ssh_connected') else 'N'} | "
            f"DoIP={'Y' if ctx.get('doip_connected') else 'N'} | "
            f"SomeIP={'Y' if ctx.get('someip_connected') else 'N'}"
        )

    def _get_active_service(self) -> "DeviceService":
        """返回当前 DI 容器中的主 DeviceService。

        某些模块可能在历史版本中缓存过旧的 DeviceService 引用；
        重连完成后，这些旧引用如果继续访问各自实例字段，会看到过期的
        DoIP/SSH/SomeIP 客户端状态。这里统一回落到 DI 中当前注册的主实例，
        让旧引用也能拿到最新连接上下文。
        """
        try:
            active = di_container.resolve(DeviceService)
        except Exception:
            active = None
        return active if active is not None else self

    def _emit_protocol_status(self, payload: Dict[str, Any]) -> None:
        emit = getattr(self.protocol_status_changed_signal, "emit", None)
        if callable(emit):
            emit(payload)

    def _run_async_cleanup(self, log_signal: Optional[object] = None, *, reason: str = "") -> None:
        _log = self._get_log_emit(log_signal)
        with self._cleanup_lock:
            if self._cleanup_thread is not None and self._cleanup_thread.is_alive():
                if reason:
                    _log(f"后台连接清理已在进行中，跳过重复触发：{reason}")
                return

            def _cleanup():
                try:
                    if reason:
                        _log(f"开始后台清理连接资源：{reason}")
                    self._reset_connection_clients(source="DeviceService._run_async_cleanup", reason=reason or "async_cleanup")
                    if reason:
                        _log(f"后台清理连接资源完成：{reason}")
                finally:
                    with self._cleanup_lock:
                        self._cleanup_thread = None

            worker = threading.Thread(target=_cleanup, name="DeviceServiceCleanup", daemon=True)
            self._cleanup_thread = worker
            worker.start()

    def _emit_reconnect_request(self, device: Dict[str, Any], log_signal: Optional[object] = None) -> None:
        emit = getattr(self.reconnect_requested_signal, "emit", None)
        if callable(emit):
            emit(device, log_signal)

    def connect_device(
        self,
        device: Dict[str, Any],
        log_signal: Optional[object] = None,
        cancel_event: threading.Event = None,
        reconnect: bool = False,
        attempt_id: int = None,
        **kwargs
    ) -> None:
        """主入口：尝试并发连接所有可用协议（或者仅连接指定协议），将结果更新回 device 的各个状态字段。
        此操作为同步阻塞方法，应被放入子线程执行。
        """
        connect_protocol = device.get("_connect_protocol")
        _log = self._get_log_emit(log_signal)

        target_ip = device.get("ip") or device.get("doip_ip") or device.get("ssh_ip") or device.get("someip_ip", "")
        # 后向兼容：将优先尝试 DoIP，再尝试 SSH
        has_doip = bool(device.get("doip_ip"))
        has_someip = bool(device.get("someip_ip"))
        has_ssh = bool(device.get("ssh_ip"))

        if not has_doip and not has_ssh and not has_someip:
            if target_ip:
                has_doip = True
                has_ssh = True
                has_someip = True

        futures = []

        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            future_to_task = {}

            if has_doip and (not connect_protocol or connect_protocol == "doip"):
                future_to_task[executor.submit(self._connect_doip_task, device, log_signal, cancel_event)] = "DoIP"

            if has_someip and (not connect_protocol or connect_protocol == "someip"):
                future_to_task[executor.submit(self._connect_someip_task, device, log_signal, cancel_event)] = "SomeIP"

            if has_ssh and (not connect_protocol or connect_protocol == "ssh"):
                future_to_task[executor.submit(self._connect_ssh_task, device, log_signal, cancel_event)] = "SSH"

            dispatched = set(future_to_task.values())
            for p, name in [("doip", "DoIP"), ("someip", "SomeIP"), ("ssh", "SSH")]:
                if (not connect_protocol or connect_protocol == p) and name not in dispatched:
                    if device.get(f"{p}_connect_status") == CONNECTING:
                        device[f"{p}_connect_status"] = CONNECT_FAILED
                        device[f"{p}_connect_info"] = "未配置该协议的有效连接参数"

            # 如果没有派发任何任务（比如缺失IP，或者指定的协议不在配置中）
            if not future_to_task:
                self._get_log_emit(log_signal)("无可用协议或连接参数，无法执行连接")
                self._change_status(device, attempt_id=attempt_id)
                return

            for future in concurrent.futures.as_completed(future_to_task):
                try:
                    future.result()
                except Exception as e:
                    _log(f"连接任务失败: {e}")

                # 每当一个协议完成（成功或失败），立即将状态推送到 UI，这样可以形成真实的分别转圈交互
                self._change_status(device, attempt_id=attempt_id)

        self._last_connected_device = device.copy()

    def _connect_doip_task(self, device, log_signal, cancel_event):
        try:
            self._connect_doip(device, log_signal)
        except Exception as e:
            self._get_log_emit(log_signal)(f"DoIP连接失败: {e}")
            device["doip_connect_status"] = CONNECT_FAILED
            device["doip_connect_info"] = str(e)

    def _connect_someip_task(self, device, log_signal, cancel_event):
        try:
            self._connect_someip(device, log_signal)
        except Exception as e:
            self._get_log_emit(log_signal)(f"SomeIP连接失败: {e}")
            device["someip_connect_status"] = CONNECT_FAILED
            device["someip_connect_info"] = str(e)

    def _connect_ssh_task(self, device, log_signal, cancel_event):
        try:
            self._connect_ssh(device, log_signal=log_signal, cancel_event=cancel_event)
        except Exception as e:
            self._get_log_emit(log_signal)(f"SSH连接失败: {e}")
            device["ssh_connect_status"] = CONNECT_FAILED
            device["ssh_connect_info"] = str(e)

    def request_cancel_connection(
        self,
        device: Dict[str, Any],
        log_signal: Optional[object] = None,
        *,
        reason: str = "用户取消连接",
        attempt_id: Optional[int] = None,
    ) -> None:
        """响应用户主动断开：尽快清理底层客户端，并将界面状态回滚为已断开。"""
        _log = self._get_log_emit(log_signal)
        _log(f"收到取消连接请求 -> {device.get('ip', '')}:{device.get('port', 22)}")
        self._mark_connection_cancelled(device, log_signal, reason=reason, attempt_id=attempt_id)
        self._run_async_cleanup(log_signal, reason=reason)

    def _is_cancelled(self, cancel_event: Optional[threading.Event]) -> bool:
        return bool(cancel_event and cancel_event.is_set())

    def _mark_connection_cancelled(
        self,
        device: Dict[str, Any],
        log_signal: Optional[object] = None,
        *,
        reason: str = "用户取消连接",
        attempt_id: Optional[int] = None,
    ) -> None:
        for protocol in ("ssh", "doip", "someip"):
            device[f"{protocol}_connect_status"] = DISCONNECTED
            device[f"{protocol}_connect_info"] = reason
        self._change_status(device, attempt_id=attempt_id)

    def _connect_doip_with_retry(
        self,
        device: Dict[str, Any],
        log_signal: Optional[object] = None,
        *,
        cancel_event: Optional[threading.Event] = None,
        attempt_id: Optional[int] = None,
        max_wait: float = 18.0,
        retry_interval: float = 2.0,
    ) -> bool:
        _log = self._get_log_emit(log_signal)
        deadline = time.monotonic() + max(1.0, max_wait)
        attempt = 0

        while True:
            if self._is_cancelled(cancel_event):
                return False

            attempt += 1
            if attempt > 1:
                remaining = max(0.0, deadline - time.monotonic())
                device["doip_connect_status"] = CONNECTING
                device["doip_connect_info"] = f"DoIP 尚未就绪，{retry_interval:.0f}s 后进行第 {attempt} 次重试（剩余约 {int(remaining)}s）"
                self._change_status(device, attempt_id=attempt_id)

            _log(f"DoIP 重连尝试 #{attempt} -> {device.get('ip', '')}:{device.get('doip_port', 13400)}")
            self._connect_doip(device, log_signal)
            self._change_status(device, attempt_id=attempt_id)
            if "建链成功" in str(device.get("doip_connect_status", "")):
                return True

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False

            sleep_time = min(retry_interval, remaining)
            end_time = time.monotonic() + sleep_time
            while time.monotonic() < end_time:
                if self._is_cancelled(cancel_event):
                    return False
                time.sleep(min(0.2, end_time - time.monotonic()))

    def _wait_for_ssh_port(
        self,
        host: str,
        port: int,
        cancel_event: Optional[threading.Event] = None,
        max_wait: float = 8.0,
        probe_timeout: float = 0.8,
        interval: float = 0.35,
    ) -> bool:
        """在短时间内轮询 SSH 端口是否就绪，避免 Paramiko 长时间阻塞。"""
        deadline = time.monotonic() + max(0.5, max_wait)
        while time.monotonic() < deadline:
            if self._is_cancelled(cancel_event):
                return False
            try:
                with socket.create_connection((host, port), timeout=probe_timeout):
                    return True
            except OSError:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                time.sleep(min(interval, remaining))
        return False

    def reset_connection_clients(self, *, source: str = "DeviceService.reset_connection_clients", reason: str = "manual_reset") -> None:
        """强制关闭并清理当前客户端实例，确保后续重连为全新连接。(公开版本，供Controller调用)"""
        self._reset_connection_clients(source=source, reason=reason)

    def _reset_connection_clients(self, *, source: str = "DeviceService._reset_connection_clients", reason: str = "reset_connection_clients") -> None:
        """强制关闭并清理当前客户端实例，确保后续重连为全新连接。"""
        self._debug_log(f"[连接上下文] 开始清理客户端实例 | {self._format_connection_context_text()}")
        try:
            if self._ssh_client is not None:
                self._ssh_client.disconnect(source=source, reason=reason, include_stack=False)
        except Exception:
            pass
        try:
            if self._someip_client is not None:
                self._someip_client.stop(source=source, reason=reason)
        except Exception:
            pass
        try:
            if self._doip_handler is not None:
                self._doip_handler.disconnect(source=source, reason=reason)
        except Exception:
            pass
        self._ssh_client = None
        self._someip_client = None
        self._doip_handler = None
        self._debug_log(f"[连接上下文] 客户端实例清理完成 | {self._format_connection_context_text()}")

    def reconnect_device(self, log_signal: Optional[object] = None) -> None:
        """请求重连最后一次连接的设备。逻辑委托给 Controller 层处理。"""
        active_service = self._get_active_service()
        if active_service is not self:
            active_service.reconnect_device(log_signal=log_signal)
            return

        if not self._last_connected_device:
            self._get_log_emit()("无上次连接设备记录，无法重连")
            return

        # 发送重连请求信号，由 Controller 接收并执行 _do_disconnect / _do_connect
        # 传递设备信息副本，供 Controller 查找对应索引
        device = self._last_connected_device.copy()

        # 发送信号，通知上层 UI 控制器执行重连流程
        self._emit_reconnect_request(device, log_signal)


    def disconnect_device(self, device: Dict[str, Any], log_signal: Optional[object] = None, disconnect_protocol: Optional[str] = None) -> Dict[str, Any]:
        """按协议选择性断开设备连接，并清理残留客户端实例。"""
        _log = self._get_log_emit(log_signal)

        status_map = {
            "ssh": str(device.get("ssh_connect_status", OFFLINE)),
            "doip": str(device.get("doip_connect_status", OFFLINE)),
            "someip": str(device.get("someip_connect_status", OFFLINE)),
        }
        
        if disconnect_protocol and disconnect_protocol in status_map:
            already_disconnected = {disconnect_protocol: self._is_disconnected_status(status_map[disconnect_protocol])}
            all_already_disconnected = already_disconnected[disconnect_protocol]
        else:
            already_disconnected = {name: self._is_disconnected_status(status) for name, status in status_map.items()}
            all_already_disconnected = all(already_disconnected.values())

        result = {
            "all_already_disconnected": all_already_disconnected,
            "disconnected_protocols": [],
            "skipped_protocols": [name for name, is_done in already_disconnected.items() if is_done],
            "cleaned_instances": [],
        }

        disconnect_actions = [
            ("doip", self._disconnect_doip),
            ("someip", self._disconnect_someip),
            ("ssh", self._disconnect_ssh),
        ]
        
        if disconnect_protocol:
            disconnect_actions = [(p, h) for p, h in disconnect_actions if p == disconnect_protocol]

        if not all_already_disconnected:
            for protocol, handler in disconnect_actions:
                if already_disconnected[protocol]:
                    continue
                changed, cleaned = handler(device, log_signal, force_cleanup=False)
                if changed:
                    result["disconnected_protocols"].append(protocol)
                if cleaned:
                    result["cleaned_instances"].append(protocol)
        else:
            self.log_signal.emit("检测到 SSH、DoIP、SomeIP 当前状态均已断开")

        for protocol, handler in disconnect_actions:
            if protocol in result["cleaned_instances"]:
                continue
            _, cleaned = handler(device, log_signal, force_cleanup=True)
            if cleaned:
                result["cleaned_instances"].append(protocol)

        self._change_status(device)
        return result

    def _is_disconnected_status(self, status: str) -> bool:
        status = str(status or "").strip()
        return status in {OFFLINE, DISCONNECTED, "已断开", "断开", "未连接"}

    def _disconnect_ssh(self, device, log_signal: Optional[object] = None, force_cleanup: bool = False):
        _log = self._get_log_emit(log_signal)
        cleaned = False
        should_disconnect = force_cleanup or not self._is_disconnected_status(device.get("ssh_connect_status", OFFLINE))
        if not should_disconnect:
            return False, cleaned

        if self._ssh_client is None:
            if force_cleanup:
                return False, False
            device["ssh_connect_status"] = DISCONNECTED
            device["ssh_connect_info"] = "SSH已断链成功"
            return True, False

        _log("正在通过SSH断开设备...")
        try:
            if hasattr(self._ssh_client, "is_connected") and self._ssh_client.is_connected():
                self._ssh_client.disconnect(
                    source="DeviceService._disconnect_ssh",
                    reason="force_cleanup" if force_cleanup else "user_disconnect_or_protocol_disconnect",
                    include_stack=False,
                )
            elif force_cleanup and hasattr(self._ssh_client, "disconnect"):
                self._ssh_client.disconnect(
                    source="DeviceService._disconnect_ssh",
                    reason="force_cleanup_inactive_transport",
                    include_stack=False,
                )
            cleaned = True
            self._ssh_client = None
            if not force_cleanup:
                device["ssh_connect_status"] = DISCONNECTED
                device["ssh_connect_info"] = "SSH已断链成功"
                return True, cleaned
            self._debug_log("检测到残留 SSH 实例，已清理并置空")
        except Exception as e:
            msg = f"SSH 断开异常: {e}"
            _log(msg)
            if not force_cleanup:
                device["ssh_connect_status"] = CONNECT_FAILED
                device["ssh_connect_info"] = msg
                return True, cleaned
        return False, cleaned

    def _disconnect_someip(self, device, log_signal: Optional[object] = None, force_cleanup: bool = False):
        _log = self._get_log_emit(log_signal)
        cleaned = False
        should_disconnect = force_cleanup or not self._is_disconnected_status(device.get("someip_connect_status", OFFLINE))
        if not should_disconnect:
            return False, cleaned

        if self._someip_client is None:
            if force_cleanup:
                return False, False
            device["someip_connect_status"] = DISCONNECTED
            device["someip_connect_info"] = "SomeIP已断链成功"
            return True, False

        try:
            self._someip_client.stop(
                source="DeviceService._disconnect_someip",
                reason="force_cleanup" if force_cleanup else "user_disconnect_or_protocol_disconnect",
            )
            cleaned = True
            self._someip_client = None
            if not force_cleanup:
                device["someip_connect_status"] = DISCONNECTED
                device["someip_connect_info"] = "SomeIP已断链成功"
                return True, cleaned
            self._debug_log("检测到残留 SomeIP 实例，已清理并置空")
        except Exception as e:
            msg = f"SomeIP 断开异常: {e}"
            _log(msg)
            if not force_cleanup:
                device["someip_connect_status"] = CONNECT_FAILED
                device["someip_connect_info"] = msg
                return True, cleaned
        return False, cleaned

    def _disconnect_doip(self, device, log_signal: Optional[object] = None, force_cleanup: bool = False):
        _log = self._get_log_emit(log_signal)
        cleaned = False
        should_disconnect = force_cleanup or not self._is_disconnected_status(device.get("doip_connect_status", OFFLINE))
        if not should_disconnect:
            return False, cleaned

        if self._doip_handler is None:
            if force_cleanup:
                return False, False
            device["doip_connect_status"] = DISCONNECTED
            device["doip_connect_info"] = "DoIP已断链成功"
            return True, False

        try:
            self._doip_handler.disconnect(
                source="DeviceService._disconnect_doip",
                reason="force_cleanup" if force_cleanup else "user_disconnect_or_protocol_disconnect",
            )
            cleaned = True
            self._doip_handler = None
            if not force_cleanup:
                device["doip_connect_status"] = DISCONNECTED
                device["doip_connect_info"] = "DoIP已断链成功"
                return True, cleaned
            self._debug_log("检测到残留 DoIP 实例，已清理并置空")
        except Exception as e:
            msg = f"DoIP 断开异常: {e}"
            _log(msg)
            if not force_cleanup:
                device["doip_connect_status"] = CONNECT_FAILED
                device["doip_connect_info"] = msg
                return True, cleaned
        return False, cleaned

    def is_ssh_connected(self, device: Dict[str, Any]) -> bool:
        """检查指定设备的 SSH 是否连接成功。"""
        ip = device.get("ip")
        port = int(device.get("port", 22))
        if not ip:
            return False
        return self._ssh_client.is_connected()

    def _connect_doip(self, device: Dict[str, Any], log_signal: Optional[object] = None) -> None:
        """内部辅助：为当前设备建立 DoIP 连接，并在 device 上写入状态字段。
        约定使用字段：
          - doip_connect_status: 建链成功 / 连接失败 / 离线
          - doip_connect_info: 失败原因或成功提示
        """
        _log = self._get_log_emit(log_signal)
        ip = device.get("ip") or ""
        # 默认使用经典 DoIP 端口 13400，如有特殊端口可后续通过 device 字段扩展
        tcp_port = int(device.get("doip_port", 13400))

        # 从 AppConfig 获取 DoIP 配置
        doip_settings = self._config_service.doip_settings
        diag_layer_settings = self._config_service.diag_layer_settings

        # Use device IP
        ip = device.get("ip") or ""

        # 协议版本转换: 0 -> 0x02 (DoIP V2), 1 -> 0x03 (DoIP V3/Other)
        # 注意：界面上 Index 0 是 V2, Index 1 是 V1(但用户要求传3)
        pv_index = int(doip_settings.get("protocol_version", 0))
        if pv_index == 1:
            protocol_version = 0x03
        else:
            protocol_version = 0x02

        client_logical_address = int(doip_settings.get("logical_addr", "0x0E80"), 16)
        routing_type = int(doip_settings.get("routing_type", "0x00"), 16)

        # Determine ECU logical address based on selected mode in DoIP settings
        # 1 = Physical, 2 = Functional
        target_addr_mode = doip_settings.get("target_addr_mode", 1)
        if target_addr_mode == 2:
            ecu_logical_address = int(doip_settings.get("target_fun_addr", "0x07DF"), 16)
        else:
            ecu_logical_address = int(doip_settings.get("target_phy_addr", "0x004F"), 16)

        # ECU 逻辑地址及本机逻辑地址可按需从 device 中扩展配置，这里使用 DoIPClientHandler 默认值
        _log(f"正在通过DoIP连接设备 {ip}:{tcp_port}... | generation={self._connection_generation}")
        if not ip:
            device["doip_connect_status"] = "连接失败"
            device["doip_connect_info"] = "缺少 ECU IP"
            return

        if self._doip_handler is None:
            self._doip_handler = DoIPClientHandler()

        # 处理网 卡选择
        network_interface_ip = doip_settings.get("network_interface_ip")
        if network_interface_ip:
            self._doip_handler.select_network_interface(network_interface_ip)
        else:
            # Fallback to index logic if IP not found (e.g. old config)
            interface_index = int(doip_settings.get("network_interface", 0))
            interfaces = self._doip_handler.get_network_interfaces()
            if 0 <= interface_index < len(interfaces):
                local_ip = interfaces[interface_index][1]
                self._doip_handler.select_network_interface(local_ip)
            else:
                # Auto select if index is invalid
                self._doip_handler.select_network_interface()

        selected_interface_ip = getattr(self._doip_handler, "interface_ip", None)
        interface_details = self._get_interface_details_by_ip(selected_interface_ip)
        local_ip = interface_details.get("local_ip", "")
        interface_name = interface_details.get("interface_name", "")
        netmask = interface_details.get("netmask", "")
        if local_ip:
            if interface_name:
                _log(f"当前 DoIP 使用的本机网络接口: {interface_name} ({local_ip})")
            else:
                _log(f"当前 DoIP 使用的本机网络接口 IP: {local_ip}")
        else:
            _log("当前 DoIP 未识别到可用的本机网络接口 IP")

        try:
            ok = self._doip_handler.connect(
                ecu_ip=ip,
                tcp_port=tcp_port,
                ecu_logical_address=ecu_logical_address,
                activation_type=routing_type,
                protocol_version=protocol_version,
                client_logical_address=client_logical_address
            )
        except Exception as exc:  # 防御性捕获，避免影响 SSH
            _log(f"DoIP 连接异常: {exc}")
            device["doip_connect_status"] = "连接失败"
            device["doip_connect_info"] = str(exc)
            self._attach_doip_diagnostic(
                device,
                local_ip=local_ip,
                interface_name=interface_name,
                netmask=netmask,
            )
            return

        if ok:
            device["doip_connect_status"] = "建链成功"
            device["doip_connect_info"] = f"DoIP 已连接到 {ip}:{tcp_port}"
            _log(f"DoIP 建链成功 | {self._format_connection_context_text()}")
        else:
            device["doip_connect_status"] = "连接失败"
            device["doip_connect_info"] = f"DoIP 连接 {ip}:{tcp_port} 失败"
            _log(f"DoIP 建链失败 | generation={self._connection_generation} | target={ip}:{tcp_port}")

        self._attach_doip_diagnostic(
            device,
            local_ip=local_ip,
            interface_name=interface_name,
            netmask=netmask,
        )
        diagnostic = device.get("_doip_diagnostic") or {}
        if diagnostic.get("need_check_interface"):
            mismatch_msg = (
                f"DoIP 连接失败，检测到本机网络接口 {diagnostic.get('local_ip', '--')}"
                f" 与设备 IP {diagnostic.get('target_ip', '--')} 不在同一网段"
            )
            if diagnostic.get("netmask"):
                mismatch_msg += f" (掩码 {diagnostic.get('netmask')})"
            _log(mismatch_msg)

    def _get_mac_address(self, ip_address: str, log_signal: Optional[object] = None) -> str:
        """获取指定 IP 地址对应的网卡 MAC 地址"""
        _log = self._get_log_emit(log_signal)
        try:
            for interface, snics in psutil.net_if_addrs().items():
                for snic in snics:
                    if snic.family == socket.AF_INET and snic.address == ip_address:
                        # 找到对应 IP 的网卡，现在查找 MAC 地址
                        # 在 Windows 上，MAC 地址通常也在同一个网卡的 addresses 列表中，AF_LINK 标识
                        for snic_mac in snics:
                            if snic_mac.family == psutil.AF_LINK:
                                return snic_mac.address.replace("-", ":").upper()
        except Exception as e:
            _log(f"获取 MAC 地址失败: {e}")
        return ""

    def _ensure_someip_client(self, device: Dict[str, Any], log_signal: Optional[object] = None) -> SomeIPClient | None:
        """内部辅助：创建并启动 SomeIPClient。

        使用设备配置中的参数进行连接：
        - client_port: 作为本地绑定的端口 (local_port)
        - multicast_ip: 组播 IP
        - multicast_port: 组播端口
        - vlan_id: VLAN ID
        - client_id: 客户端 ID (用于 SomeIP header)
        """
        _log = self._get_log_emit(log_signal)
        if self._someip_client is not None:
            # TODO: 如果参数变化是否需要重启？目前假定单例
            return self._someip_client

        # 从 device 中获取参数 (所有参数均有默认值，方便测试)
        multicast_ip = device.get("multicast_ip") or "239.192.255.1"  # Default Multicast IP
        multicast_port_str = device.get("multicast_port") or "30490"  # Default Multicast Port
        vlan_id_str = str(device.get("vlan_id") or "4")              # Default VLAN
        client_port_str = device.get("client_port") or "30813"      # Default Client Port
        client_id_str = device.get("client_id") or "30813"      # Default Client ID

        try:
            multicast_port = int(multicast_port_str)
        except ValueError:
            multicast_port = 30490

        try:
            local_port = int(client_port_str)
        except ValueError:
            local_port = 30813

        try:
            # Parse hex or int for client_id
            if str(client_id_str).strip().lower().startswith("0x"):
                client_id = int(str(client_id_str), 16)
            else:
                client_id = int(client_id_str)
        except ValueError:
            client_id = 30813

        vlan_id = None
        if vlan_id_str and vlan_id_str.lower() != "none" and vlan_id_str != "":
            try:
                vlan_id = int(vlan_id_str)
            except:
                pass

        # Try to get Local IP from App Config
        someip_settings = self._config_service.someip_settings
        config_local_ip = someip_settings.get("local_ip")

        # Use configured IP, or fallback to a hardcoded default
        if config_local_ip:
            LOCAL_CLIENT_IP = config_local_ip
        else:
             _log(f"警告: SomeIP 本地 IP 未配置")
             LOCAL_CLIENT_IP = "172.16.64.47"
        LOCAL_CLIENT_IP = "172.16.64.47"
        LOCAL_CLIENT_MAC = self._get_mac_address(LOCAL_CLIENT_IP, log_signal)
        if not LOCAL_CLIENT_MAC:
             # Fallback MAC if look up fails
             LOCAL_CLIENT_MAC = "00:00:00:00:00:00"

        _log(f"启动 SomeIPClient: Multi={multicast_ip}:{multicast_port}, LocalPort={local_port}, ClientID={hex(client_id)}, VLAN={vlan_id}, LocalIP={LOCAL_CLIENT_IP}, MAC={LOCAL_CLIENT_MAC}")

        client = SomeIPClient(local_ip=LOCAL_CLIENT_IP, local_port=local_port, client_id=client_id,
                              multicast_ip=multicast_ip, multicast_port=multicast_port, vlan_id=vlan_id,
                              client_mac=LOCAL_CLIENT_MAC)
        started = client.start()
        if not started:
            _log(f"SomeIP 客户端启动失败，配置: IP={LOCAL_CLIENT_IP}")
            return None
        self._someip_client = client
        return self._someip_client

    def _connect_someip(self, device: Dict[str, Any], log_signal: Optional[object] = None) -> None:
        _log = self._get_log_emit(log_signal)
        _log(f"正在通过SomeIP连接设备... | generation={self._connection_generation}")
        """内部辅助：为当前设备准备 SOME/IP 通信客户端，并更新状态字段。
        注意：SOME/IP 多数场景是无连接 UDP，这里仅表示“本地客户端已就绪”。
        """
        client = self._ensure_someip_client(device, log_signal)
        if client is None:
            device["someip_connect_status"] = "连接失败"
            device["someip_connect_info"] = "SomeIP 客户端启动失败"
            return

        device["someip_connect_status"] = "建链成功"
        device["someip_connect_info"] = f"SomeIP 连接成功>> {client.local_ip}:{client.local_port} (VLAN {client.vlan_id})"
        _log(f"SomeIP 客户端就绪 | {self._format_connection_context_text()}")

    def _get_interface_details_by_ip(self, interface_ip: Optional[str]) -> Dict[str, str]:
        if not interface_ip:
            return {}

        try:
            for interface_name, snics in psutil.net_if_addrs().items():
                for snic in snics:
                    if snic.family == socket.AF_INET and snic.address == interface_ip:
                        return {
                            "interface_name": interface_name,
                            "local_ip": snic.address or "",
                            "netmask": snic.netmask or "",
                        }
        except Exception:
            pass

        return {"local_ip": interface_ip or ""}

    def _same_subnet(self, local_ip: Optional[str], target_ip: Optional[str], netmask: Optional[str]) -> Optional[bool]:
        if not local_ip or not target_ip or not netmask:
            return None
        try:
            network = ipaddress.IPv4Network(f"{local_ip}/{netmask}", strict=False)
            return ipaddress.IPv4Address(target_ip) in network
        except Exception:
            return None

    def _attach_doip_diagnostic(
        self,
        device: Dict[str, Any],
        *,
        local_ip: Optional[str],
        interface_name: Optional[str],
        netmask: Optional[str],
    ) -> None:
        target_ip = str(device.get("ip") or "").strip()
        same_subnet = self._same_subnet(local_ip, target_ip, netmask)
        need_check_interface = bool(
            local_ip and target_ip and same_subnet is False and "连接失败" in str(device.get("doip_connect_status", ""))
        )
        device["_doip_diagnostic"] = {
            "local_ip": local_ip or "",
            "interface_name": interface_name or "",
            "netmask": netmask or "",
            "target_ip": target_ip,
            "same_subnet": same_subnet,
            "need_check_interface": need_check_interface,
        }

    def _change_status(self, device, attempt_id: Optional[int] = None):
        payload = {
            "ip": device.get("ip"),
            "port": device.get("port"),
            "ssh_connect_status": device.get("ssh_connect_status"),
            "ssh_connect_info": device.get("ssh_connect_info"),
            "doip_connect_status": device.get("doip_connect_status"),
            "doip_connect_info": device.get("doip_connect_info"),
            "someip_connect_status": device.get("someip_connect_status"),
            "someip_connect_info": device.get("someip_connect_info"),
            "_connection_generation": self._connection_generation,
        }
        if isinstance(device.get("_doip_diagnostic"), dict):
            payload["_doip_diagnostic"] = dict(device.get("_doip_diagnostic") or {})
        if attempt_id is not None:
            payload["_attempt_id"] = attempt_id
        self._emit_protocol_status(payload)

    def _connect_ssh(
        self,
        device: Dict[str, Any],
        timeout: int = 8,
        log_signal: Optional[object] = None,
        cancel_event: Optional[threading.Event] = None,
    ) -> tuple[str, str, int] | None:
        _log = self._get_log_emit(log_signal)
        host = device.get("ip")
        port = int(device.get("port", 22))
        username = device.get("user") or device.get("username") or "root"
        password = device.get("password")
        if not host:
            device["ssh_connect_status"] = "连接失败"
            device["ssh_connect_info"] = "缺少 SSH 目标 IP"
            return "", "缺��� SSH 目标 IP", 255

        if self._is_cancelled(cancel_event):
            return None

        ssh_ready = self._wait_for_ssh_port(
            host,
            port,
            cancel_event,
            float(timeout),
            0.8,
            0.35,
        )
        if self._is_cancelled(cancel_event):
            return None
        if not ssh_ready:
            msg = f"SSH 端口 {port} 未就绪或连接超时"
            _log(msg)
            device["ssh_connect_status"] = "连接失败"
            device["ssh_connect_info"] = msg
            return "", msg, 255

        try:
            self._ssh_client = SSHClient()
            connect_kwargs = {
                "auth_timeout": 3.5,
                "banner_timeout": 2.5,
                "look_for_keys": False,
                "allow_agent": False,
            }
            connect_callable = getattr(self._ssh_client, "connect")
            connect_result = connect_callable(
                host,
                port,
                username,
                password,
                min(float(timeout), 3.0),
                **connect_kwargs,
            )
            if self._is_cancelled(cancel_event):
                self._ssh_client.disconnect(source="DeviceService._connect_ssh", reason="connect_cancelled_after_established", include_stack=False)
                self._ssh_client = None
                return None
            if not connect_result:
                device["ssh_connect_status"] = "连接失败"
                device["ssh_connect_info"] = "SSH 建链失败或认证失败"
                return "", "SSH 建链失败或认证失败", 255
            device["ssh_connect_status"] = "建链成功"
            device["ssh_connect_info"] = f"SSH 已连接到 {host}:{port}"
            _log(f"SSH 已连接到 {host}:{port} | {self._format_connection_context_text()}")
        except AuthenticationException as e:
            msg = f"SSH认证失败: {e}"
            _log(msg)
            device["ssh_connect_status"] = "连接失败"
            device["ssh_connect_info"] = msg
            return "", msg, 255
        except SSHException as e:
            msg = f"SSH错误: {e}"
            _log(msg)
            device["ssh_connect_status"] = "连接失败"
            device["ssh_connect_info"] = msg
            return "", msg, 255
        except Exception as e:
            msg = f"SSH未知错误: {e}"
            _log(msg)
            device["ssh_connect_status"] = "连接失败"
            device["ssh_connect_info"] = msg
            return "", msg, 255


    def close_device_all_connections(self, device: Dict[str, Any]) -> None:
        self.disconnect_device(device)

    # ---- 提供给其他 Service 复用的 已连接成功的 DoIP / SomeIP /ssh 能力 ----
    def get_doip_client(self) -> Optional[DoIPClientHandler]:
        """获取当前的 DoIP 客户端实例。"""
        active_service = self._get_active_service()
        if active_service is not self:
            return active_service.get_doip_client()
        return self._doip_handler

    def get_ssh_client(self) -> Optional[SSHClient]:
        """获取当前的 SSH 客户端实例"""
        active_service = self._get_active_service()
        if active_service is not self:
            return active_service.get_ssh_client()
        return self._ssh_client
    def get_someip_client(self) -> Optional[SomeIPClient]:
        """获取当前的 SomeIP 客户端实例"""
        active_service = self._get_active_service()
        if active_service is not self:
            return active_service.get_someip_client()
        return self._someip_client

    def get_current_device_ip(self) -> Optional[str]:
        """获取当前连接设备的 IP 地址"""
        active_service = self._get_active_service()
        if active_service is not self:
            return active_service.get_current_device_ip()
        if self._last_connected_device:
            return self._last_connected_device.get("ip")
        return None


    def close_device_connections(self):
        active_service = self._get_active_service()
        if active_service is not self:
            active_service.close_device_connections()
            return
        if self._ssh_client is not None:
            self._ssh_client.disconnect(source="DeviceService.close_device_connections", reason="application_or_module_shutdown", include_stack=False)
        if self._someip_client is not None:
            self._someip_client.stop(source="DeviceService.close_device_connections", reason="application_or_module_shutdown")
        if self._doip_handler is not None:
            self._doip_handler.disconnect(source="DeviceService.close_device_connections", reason="application_or_module_shutdown")


    def active_ssh_command(
        self,
        log_signal: Optional[object] = None,
        *,
        cancel_event: Optional[threading.Event] = None,
    ):
        """
        发送 DoIP 指令激活 SSH (或其他功能)
        """
        _log = self._get_log_emit(log_signal)
        _log("开始发送激活 SSH 指令...")
        # 31 01 BE E9
        routine = bytes.fromhex("31 01 BE E9")
        self.execute_secure_routine(routine, sec_level=0x21, log_signal=log_signal, cancel_event=cancel_event)

    def send_doip_payload(
            self,
            payload: bytes,
            *,
            timeout: float | None = None,
            response_index: int | None = None,
            target_did: int | None = None,
            prefer_last: bool = False,
    ) -> bytes | None:
        """统一的 DoIP ��送接口，供 Topology/Diagnostic 等业务 Service 重用。"""
        active_service = self._get_active_service()
        if active_service is not self:
            return active_service.send_doip_payload(
                payload,
                timeout=timeout,
                response_index=response_index,
                target_did=target_did,
                prefer_last=prefer_last,
            )

        # 1. 获取客户端实例
        client = self.get_doip_client()
        if client is None:
            self._get_log_emit()("错误：DoIP 客户端实例为 None")
            return None

        # 计算超时
        if timeout is None:
            try:
                timeout_ms = int(self._config_service.diag_layer_settings.get("s3_client_time", 3000))
                timeout = timeout_ms / 1000.0
            except (ValueError, TypeError):
                timeout = 3.0

        def _try_reconnect_for_payload(stage_text: str) -> bool:
            if not self._last_connected_device:
                self._get_log_emit()(f"{stage_text}，但无历史连接记���，无法自动重连")
                return False

            self._get_log_emit()(f"{stage_text}，进入 DoIP 自动重连窗口...")
            reconnected = self._connect_doip_with_retry(
                self._last_connected_device,
                log_signal=self.log_signal,
                max_wait=max(8.0, (timeout or 3.0) * 4),
                retry_interval=1.5,
            )
            if not reconnected:
                self._get_log_emit()("DoIP 自动重连失败，放弃发送")
                return False
            self._get_log_emit()("DoIP 自动重连成功，继续发送报文")
            return True

        # 2. 预检查连接状态
        # 如果未连接，且有上次连接记录，先尝试重连一次
        if not client.connected:
            if not _try_reconnect_for_payload("发现 DoIP 未连接"):
                return None

        # 3. 尝试发送
        # 注意：client.send_doip_message 内部可能还有一层重连机制
        resp = client.send_doip_message(
            payload,
            timeout=timeout,
            response_index=response_index,
            target_did=target_did,
            prefer_last=prefer_last,
        )

        # 4. 如果发送失败 (resp is None)
        # 这可能是超时（应用层无响应），也可能是连接断开（IO错误）
        if resp is None:
            # 检查连接状态
            # 如果 send_doip_message 遇到了 IO 错误，它会将 connected 置为 False
            if not client.connected:
                self._get_log_emit()("发送报文时连接断开")
                if _try_reconnect_for_payload("发送报文时连接断开"):
                    resp = client.send_doip_message(
                        payload,
                        timeout=timeout,
                        response_index=response_index,
                        target_did=target_did,
                        prefer_last=prefer_last,
                    )
            else:
                # 状态仍为 Connected，说明是单纯的超时，未发生断链
                # self.log_signal.emit("发送等到超时（未收到响应），连接保持正常")
                pass

        return resp

    def execute_secure_routine(
        self,
        routine_command: bytes,
        sec_level: int = 0x21,
        return_on_auth_fail: bool = False,
        log_signal: Optional[object] = None,
        *,
        cancel_event: Optional[threading.Event] = None,
    ) -> bool | bytes:
        """
        执行带安全访问的 UDS 例程序列:
        1. 10 03 (Extended Session)
        2. 27 <sec_level> (Request Seed) -> Calculate Key -> 27 <sec_level+1> (Send Key)
        3. <routine_command>

        :param routine_command: 例程指令 bytes
        :param sec_level: 安全访问级别
        :param return_on_auth_fail: 安全访问失败是否退出
        :param log_signal: 用于发送日志的信号，如果为None则使用self.log_signal
        :return: 成功返回 响应数据(bytes)，失败返回 False。
        """
        # 确定使用的日志信号或emit函数
        log_emit = self._get_log_emit(log_signal)

        active_service = self._get_active_service()
        if active_service is not self:
            return active_service.execute_secure_routine(
                routine_command,
                sec_level=sec_level,
                return_on_auth_fail=return_on_auth_fail,
                log_signal=log_signal,
                cancel_event=cancel_event,
            )

        client = self.get_doip_client()
        if not client:
            log_emit("DoIP 未连接，无法发送指令")
            return False

        if self._is_cancelled(cancel_event):
            log_emit("激活 SSH 流程已取消")
            return False

        # 1. 诊断会话控制 (10 03)
        tx_session = bytes.fromhex("10 03")
        log_emit(f"发送: {tx_session.hex(' ').upper()}")
        rx_session = client.send_doip_message(tx_session)
        if not rx_session or rx_session[0] != 0x50:
            log_emit(f"会话控制失败: {rx_session.hex(' ').upper() if rx_session else '无响应'}")
            return False
        log_emit(f"会话控制成功: {rx_session.hex(' ').upper()}")
        if self._is_cancelled(cancel_event):
            log_emit("激活 SSH 流程已取消")
            return False

        # 2. 安全访问
        tx_seed = bytes([0x27, sec_level])
        log_emit(f"请求种子: {tx_seed.hex(' ').upper()}")
        rx_seed = client.send_doip_message(tx_seed)

        if not rx_seed or rx_seed[0] != 0x67:
            log_emit(f"请求种子失败: {rx_seed.hex(' ').upper() if rx_seed else '无响应'}")
            return False
        log_emit(f"收到种子: {rx_seed.hex(' ').upper()}")
        if self._is_cancelled(cancel_event):
            log_emit("激活 SSH 流程已取消")
            return False

        # 计算密钥
        if len(rx_seed) < 3:
            log_emit("种子响应长度不足")
            return False

        seed = rx_seed[2:]
        key, error_msg = SecurityAccessHelper.calculate_key(sec_level, seed)

        if not key:
            log_emit(f"密钥计算失败: {error_msg}")
            return False

        # 发送密钥
        tx_key = bytes([0x27, sec_level + 1]) + key
        log_emit(f"发送密钥: {tx_key.hex(' ').upper()}")
        rx_key = client.send_doip_message(tx_key)

        if not rx_key or rx_key[0] != 0x67:
            log_emit(f"安全访问失败: {rx_key.hex(' ').upper() if rx_key else '无响应'}")
            if return_on_auth_fail:
                return False
        else:
            log_emit(f"安全访问成功: {rx_key.hex(' ').upper()}")
        if self._is_cancelled(cancel_event):
            log_emit("激活 SSH 流程已取消")
            return False

        # 3. 例程控制
        log_emit(f"发送例程: {routine_command.hex(' ').upper()}")
        rx_routine = client.send_doip_message(routine_command)

        # 检查响应是否为肯定响应 (Request Service ID + 0x40)
        expected_response_sid = routine_command[0] + 0x40
        if not rx_routine or rx_routine[0] != expected_response_sid:
            log_emit(f"例程控制失败: {rx_routine.hex(' ').upper() if rx_routine else '无响应'}")
            return False
        log_emit(f"例程控制成功: {rx_routine.hex(' ').upper()}")
        return rx_routine
