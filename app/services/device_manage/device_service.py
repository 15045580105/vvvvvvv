from typing import List, Dict, Any, Tuple

from PyQt5.QtCore import QObject, pyqtSignal
from paramiko.ssh_exception import AuthenticationException, SSHException

from app.common.communication.clients.Doip_Client import DoIPClientHandler
from app.common.communication.clients.Someip_Client import SomeIPClient
from app.services.communication.ssh_service import SSHService
import warnings

# Suppress the SIP/PyQt deprecation about sipPyTypeDict() which is raised from the
# underlying extension module. This is a runtime DeprecationWarning originating
# in PyQt/sip internals and safe to ignore in the short term. Long-term fix is to
# upgrade PyQt/sip to versions that no longer use sipPyTypeDict.
warnings.filterwarnings(
    "ignore",
    message=r".*sipPyTypeDict\(\) is deprecated.*",
    category=DeprecationWarning,
)


class DeviceService(QObject):
    # 文本日志信号
    log_signal = pyqtSignal(str)
    # 协议状态变更信号：payload 为包含 ip/port 及各协议状态字段的 device dict
    protocol_status_changed = pyqtSignal(dict)
    # 长耗时操作进度信号：例如“正在连接设备 ...”、“正在断开设备 ...”、“连接完成”等
    operation_progress = pyqtSignal(str)

    """设备管理领域的 Service 层封装。"""

    def __init__(self) -> None:
        super().__init__()
        self._ssh_service = SSHService()
        # 独立的 DoIP / SomeIP 客户端实例，由 DeviceService 统一管理生命周期
        self._doip_handler: DoIPClientHandler | None = None
        self._someip_client: SomeIPClient | None = None

    def connect_device(self, device: Dict[str, Any]) -> None:
        """连接单个设备：按 SSH/DoIP/SomeIP 三种协议尝试建链，并统一发出状态信号。
        """
        ip = device.get("ip")
        port = int(device.get("port", 22))

        # 通知上层：开始连接（可用于显示等待对话框）
        self.operation_progress.emit(f"正在连接设备 {ip}:{port} ，请稍候...")

        # 1. DoIP 连接
        self.log_signal.emit(f"正在通过DoIP连接设备 {ip}:{port}...")
        self._connect_doip(device)

        # 2. SomeIP 客户端准备
        self.log_signal.emit(f"正在通过SomeIP连接设备 {ip}:{port}...")
        self._connect_someip(device)

        # 3. SSH 连接：通过执行 ipconfig 验证链路
        self.log_signal.emit(f"正在通过SSH连接设备 {ip}:{port}...")
        out, err, code = self.execute_ssh_command_on_device(device, "ipconfig")
        if code == 0:
            self.log_signal.emit("SSH 连接成功")
            device["ssh_connect_status"] = "建链成功"
            device["ssh_connect_info"] = "建链成功"
        else:
            self.log_signal.emit(f"SSH 连接失败: {err}")
            device["ssh_connect_status"] = "连接失败"
            device["ssh_connect_info"] = err or "SSH 连接失败"

        # 统一发出协议状态变化信号，让 Controller 更新三行状态和详情
        payload = {
            "ip": ip,
            "port": port,
            "ssh_connect_status": device.get("ssh_connect_status"),
            "ssh_connect_info": device.get("ssh_connect_info"),
            "doip_connect_status": device.get("doip_connect_status"),
            "doip_connect_info": device.get("doip_connect_info"),
            "someip_connect_status": device.get("someip_connect_status"),
            "someip_connect_info": device.get("someip_connect_info"),
        }
        self.protocol_status_changed.emit(payload)

        # 通知上层：连接结束，可关闭等待提示
        self.operation_progress.emit(f"设备 {ip}:{port} 连接操作已完成。")

    def disconnect_device(self, device: Dict[str, Any]) -> None:
        """断开设备三种协议连接，并发出状态信号。"""
        ip = device.get("ip")
        port = int(device.get("port", 22))

        # 通知上层：开始断开
        self.operation_progress.emit(f"正在断开设备 {ip}:{port} ，请稍候...")

        self.log_signal.emit(f"开始断开设备 {ip}:{port}...")

        # 1. DoIP / SomeIP 断开
        # 主动关闭 DoIP 连接
        if self._doip_handler is not None:
            try:
                self._doip_handler.disconnect()
            except Exception:
                pass
        device["doip_connect_status"] = "已断链"
        device["doip_connect_info"] = "已断链"

        # 停止 SOME/IP 客户端
        if self._someip_client is not None:
            try:
                self._someip_client.stop()
            except Exception:
                pass
        device["someip_connect_status"] = "已断链"
        device["someip_connect_info"] = "已断链"

        # 2. SSH 断开
        self.log_signal.emit("正在通过SSH断开设备...")
        try:
            self._ssh_service.close_host(ip, port)
            device["ssh_connect_status"] = "已断链"
            device["ssh_connect_info"] = "已断链"
        except Exception as e:
            msg = f"SSH 断开异常: {e}"
            self.log_signal.emit(msg)
            device["ssh_connect_status"] = "连接失败"
            device["ssh_connect_info"] = msg

        payload = {
            "ip": ip,
            "port": port,
            "ssh_connect_status": device.get("ssh_connect_status"),
            "ssh_connect_info": device.get("ssh_connect_info"),
            "doip_connect_status": device.get("doip_connect_status"),
            "doip_connect_info": device.get("doip_connect_info"),
            "someip_connect_status": device.get("someip_connect_status"),
            "someip_connect_info": device.get("someip_connect_info"),
        }
        self.protocol_status_changed.emit(payload)

        # 通知上层：断开结束
        self.operation_progress.emit(f"设备 {ip}:{port} 断开操作已完成。")

    # ---- 设备与 SSH 连接管理 ----
    def _parse_ssh_params(self, device: Dict[str, Any]) -> Tuple[str, int, str, str | None, str | None]:
        """从设备字典中提取 SSH 连接所需参数。

        仅负责解析结构，不做任何网络操作或状态更新。
        """
        host = device.get("ip")
        port = int(device.get("port", 22))
        username = device.get("user") or device.get("username") or "root"
        password = device.get("password")
        key_file = device.get("key_file")
        return host, port, username, password, key_file

    def register_devices(self, devices: List[Dict[str, Any]]) -> None:
        """批量注册设备到 SSHService。

        devices: 列表元素示例：
            {
                "name": "设备A",
                "ip": "10.132.8.227",
                "port": 22,
                "user": "uidq9000",
                "password": "xxx"  # 可选
            }
        """
        for d in devices:
            host, port, username, password, key_file = self._parse_ssh_params(d)
            if not host:
                continue
            self._ssh_service.register_host(
                host=host,
                port=port,
                username=username,
                password=password,
                key_file=key_file,
                eager_connect=False,
            )

    def _connect_doip(self, device: Dict[str, Any]) -> None:
        """内部辅助：为当前设备建立 DoIP 连接，并在 device 上写入状态字段。

        约定使用字段：
          - doip_connect_status: 建链成功 / 连接失败 / 离线
          - doip_connect_info: 失败原因或成功提示
        """
        ip = device.get("ip") or ""
        # 默认使用经典 DoIP 端口 13400，如有特殊端口可后续通过 device 字段扩展
        tcp_port = int(device.get("doip_port", 13400))
        # ECU 逻辑地址及本机逻辑地址可按需从 device 中扩展配置，这里使用 DoIPClientHandler 默认值
        self.log_signal.emit(f"正在通过DoIP连接设备 {ip}:{tcp_port}...")
        if not ip:
            device["doip_connect_status"] = "连接失败"
            device["doip_connect_info"] = "缺少 ECU IP"
            return

        if self._doip_handler is None:
            self._doip_handler = DoIPClientHandler()

        try:
            ok = self._doip_handler.connect(ip, tcp_port=tcp_port)
        except Exception as exc:  # 防御性捕获，避免影响 SSH
            self.log_signal.emit(f"DoIP 连接异常: {exc}")
            device["doip_connect_status"] = "连接失败"
            device["doip_connect_info"] = str(exc)
            return

        if ok:
            device["doip_connect_status"] = "建链成功"
            device["doip_connect_info"] = f"DoIP 已连接到 {ip}:{tcp_port}"
        else:
            device["doip_connect_status"] = "连接失败"
            device["doip_connect_info"] = f"DoIP 连接 {ip}:{tcp_port} 失败"

    def _ensure_someip_client(self, local_ip: str | None = None) -> SomeIPClient | None:
        """内部辅助：创建并启动 SomeIPClient。

        当前简单实现：
          * local_ip 为空时使用 127.0.0.1，方便本地联调；
          * 仅负责创建 + start，不做服务发现，后续可在业务 Service 中细化。
        """
        if self._someip_client is not None:
            return self._someip_client

        ip = local_ip or "127.0.0.1"
        client = SomeIPClient(local_ip=ip, local_port=0)
        started = client.start()
        if not started:
            self.log_signal.emit(f"SomeIP 客户端启动失败，本地IP={ip}")
            return None
        self._someip_client = client
        return self._someip_client

    def _connect_someip(self, device: Dict[str, Any]) -> None:
        self.log_signal.emit(f"正在通过SomeIP连接设备...")
        """内部辅助：为当前设备准备 SOME/IP 通信客户端，并更新状态字段。

        注意：SOME/IP 多数场景是无连接 UDP，这里仅表示“本地客户端已就绪”。
        """
        # 可以按需从 device 中取本地网卡 IP 或接口信息，目前简单使用回环地址
        local_ip = device.get("someip_local_ip")  # 可选字段

        client = self._ensure_someip_client(local_ip)

        if client is None:
            device["someip_connect_status"] = "连接失败"
            device["someip_connect_info"] = "SomeIP 客户端启动失败"
            return

        device["someip_connect_status"] = "建链成功"
        device["someip_connect_info"] = f"SomeIP 客户端就绪，本地 {client.local_ip}:{client.local_port}"

    def _change_status(self, device):
        payload = {
            "ip": device.get("ip"),
            "port": device.get("port"),
            "ssh_connect_status": device.get("ssh_connect_status"),
            "ssh_connect_info": device.get("ssh_connect_info"),
            "doip_connect_status": device.get("doip_connect_status"),
            "doip_connect_info": device.get("doip_connect_info"),
            "someip_connect_status": device.get("someip_connect_status"),
            "someip_connect_info": device.get("someip_connect_info"),
        }
        self.protocol_status_changed.emit(payload)

    def execute_ssh_command_on_device(
        self,
        device: Dict[str, Any],
        command: str,
        timeout: int = 30,
    ) -> Tuple[str, str, int]:
        """对单个设备执行 SSH 命令并返回 (stdout, stderr, exit_code)，内部捕获异常避免应用崩溃。
        本方法内部也会更新 device["ssh_connect_status"] 和 device["ssh_connect_info"]，
        以便上层在需要时将最新状态透传给 Controller/Model。
        """
        host, port, username, password, key_file = self._parse_ssh_params(device)
        self.log_signal.emit(f"正在通过SSH连接设备 {host}:{port}...")
        try:
            # register_host 幂等，重复调用安全
            self._ssh_service.register_host(host, port, username, password, key_file, eager_connect=False)
            out, err, code = self._ssh_service.execute(host, port, command, timeout=timeout)
        except AuthenticationException as e:
            msg = f"SSH认证失败: {e}"
            self.log_signal.emit(msg)
            device["ssh_connect_status"] = "连接失败"
            device["ssh_connect_info"] = msg
            return "", msg, 255
        except SSHException as e:
            msg = f"SSH错误: {e}"
            self.log_signal.emit(msg)
            device["ssh_connect_status"] = "连接失败"
            device["ssh_connect_info"] = msg
            return "", msg, 255
        except Exception as e:
            msg = f"SSH未知错误: {e}"
            self.log_signal.emit(msg)
            device["ssh_connect_status"] = "连接失败"
            device["ssh_connect_info"] = msg
            return "", msg, 255

        if code == 0:
            device["ssh_connect_status"] = "建链成功"
            device["ssh_connect_info"] = f"命令成功: {command}" if command else "SSH 命令执行成功"
        else:
            msg = err or f"SSH命令失败, 返回码 {code}"
            device["ssh_connect_status"] = "连接失败"
            device["ssh_connect_info"] = msg
        return out, err, code

    def execute_command_on_multiple_devices(
        self,
        devices: List[Dict[str, Any]],
        command: str,
        timeout: int = 30,
    ) -> Dict[Tuple[str, int], Dict[str, Any]]:
        """对一组设备执行相同命令，返回按 (ip, port) 聚合的结果。"""
        self.register_devices(devices)
        commands: Dict[Tuple[str, int], str] = {}
        for d in devices:
            host = d.get("ip")
            if not host:
                continue
            port = int(d.get("port", 22))
            commands[(host, port)] = command
        return self._ssh_service.execute_many(commands, timeout=timeout)



    def close_single_device_connections(self, device: Dict[str, Any]) -> None:
        """关闭单个设备的底层 SSH 连接。"""
        host, port, *_ = self._parse_ssh_params(device)
        if not host:
            return
        try:
            self._ssh_service.close_host(host, port)
        except Exception:
            # 底层关闭失败不应影响上层逻辑，这里静默忽略
            pass

    def close_all_device_connections(self) -> None:
        """关闭所有底层 SSH 连接。"""
        self._ssh_service.close_all()
        self._doip_handler.disconnect()
        self._someip_client.stop()

    # ---- 提供给其他 Service 复用的 DoIP / SomeIP 能力 ----
    def get_doip_client(self) -> DoIPClientHandler | None:
        """返回当前 DoIP 客户端实例（若尚未连接则为 None）。"""
        if self._doip_handler is not None and getattr(self._doip_handler, "is_connected", lambda: False)():
            return self._doip_handler
        return None

    def send_doip_payload(
        self,
        payload: bytes,
        *,
        timeout: float = 1.0,
        response_index: int | None = None,
        target_did: int | None = None,
        prefer_last: bool = False,
    ) -> bytes | None:
        """统一的 DoIP 发送接口，供 Topology/Diagnostic 等业务 Service 重用。"""
        client = self.get_doip_client()
        if client is None:
            self.log_signal.emit("DoIP 客户端未连接，无法发送报文")
            return None
        try:
            return client.send_doip_message(
                payload,
                timeout=timeout,
                response_index=response_index,
                target_did=target_did,
                prefer_last=prefer_last,
            )
        except Exception as e:
            self.log_signal.emit(f"通过 DoIP 发送报文失败: {e}")
            return None

    def get_someip_client(self) -> SomeIPClient | None:
        """返回当前 SomeIP 客户端实例（可能为 None）。"""
        return self._someip_client

