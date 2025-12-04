from typing import List, Dict, Any, Tuple

from PyQt5.QtCore import QObject, pyqtSignal
from paramiko.ssh_exception import AuthenticationException, SSHException

from app.common.communication.clients.Someip_Doip_Client import SomeipDoipEthernetClient, EthernetConnectionConfig
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

    """设备管理领域的 Service 层封装。"""

    def __init__(self) -> None:
        super().__init__()
        self._ssh_service = SSHService()
        self.someip_doip_ethernet_service = None  # 占位，后续可接入 DoIPService

    # ---- 设备与 SSH 连接管理 ----
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
            host = d.get("ip")
            if not host:
                continue
            port = int(d.get("port", 22))
            username = d.get("user") or d.get("username") or "root"
            password = d.get("password")
            key_file = d.get("key_file")
            self._ssh_service.register_host(
                host=host,
                port=port,
                username=username,
                password=password,
                key_file=key_file,
                eager_connect=False,
            )

    def connect_device(self, device: Dict[str, Any]) -> None:
        """连接单个设备：按 SSH/DoIP/SomeIP 三种协议尝试建链，并统一发出状态信号。
        """
        ip = device.get("ip")
        port = int(device.get("port", 22))
        self.log_signal.emit(f"正在通过DoIP/SomeIP连接设备 {ip}:{port}...")

        # 1. DoIP / SomeIP 都是同一个TCP建链
        cfg = EthernetConnectionConfig(
            remote_ip=ip,
            remote_port=port,
            interface=None,  # 使用默认接口
            dst_mac="ff:ff:ff:ff:ff:ff",  # 这里示例用广播, 实际请替换 ECU MAC
            protocol="raw",
        )
        self.someip_doip_ethernet_service = SomeipDoipEthernetClient(cfg)
        self.someip_doip_ethernet_service.connect()
        res = self.someip_doip_ethernet_service.is_connected()
        if res:
            self.log_signal.emit("DoIP/SomeIP连接成功")
            device["doip_connect_status"] = "建链成功"
            device["doip_connect_info"] = "建链成功"
            device["someip_connect_status"] = "建链成功"
            device["someip_connect_info"] = " 建链成功"
        else:
            self.log_signal.emit("DoIP/SomeIP连接失败")
            device["doip_connect_status"] = "建链失败"
            # device["doip_connect_info"] = err or "建链失败"
            device["doip_connect_info"] = "建链失败"
            device["someip_connect_status"] = "建链失败"
            # device["someip_connect_info"] = err or "建链失败"
            device["someip_connect_info"] =  "建链失败"

        # 2. SSH 连接：通过执行 ipconfig 验证链路
        self.log_signal.emit(f"正在通过SSH连接设备 {ip}:{port}...")
        out, err, code = self.execute_ssh_command_on_device(device, "ipconfig")
        if code == 0:
            self.log_signal.emit("SSH 连接成功")
            device["ssh_connect_status"] = "建链成功"
            # 简要记录一次成功信息
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


    def disconnect_device(self, device: Dict[str, Any]) -> None:
        """断开设备三种协议连接，并发出状态信号。"""
        ip = device.get("ip")
        port = int(device.get("port", 22))
        self.log_signal.emit(f"开始断开设备 {ip}:{port}...")

        # 1. DoIP / SomeIP 断开
        device["doip_connect_status"] = "已断链"
        device["doip_connect_info"] = "已断链"
        device["someip_connect_status"] = "已断链"
        device["someip_connect_info"] = "已断链"

        # 3. SSH 断开
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
        host = device.get("ip")
        port = int(device.get("port", 22))
        username = device.get("user") or device.get("username") or "root"
        password = device.get("password")
        key_file = device.get("key_file")

        try:
            self._ssh_service.register_host(host, port, username, password, key_file, eager_connect=False)
            out, err, code = self._ssh_service.execute(host, port, command, timeout=timeout)
        except AuthenticationException as e:
            msg = f"认证失败: {e}"
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
            msg = f"未知错误: {e}"
            self.log_signal.emit(msg)
            device["ssh_connect_status"] = "连接失败"
            device["ssh_connect_info"] = msg
            return "", msg, 255

        if code == 0:
            device["ssh_connect_status"] = "建链成功"
            device["ssh_connect_info"] = f"命令成功: {command}" if command else "SSH 命令执行成功"
        else:
            # 将 stderr 或通用信息写入详情
            msg = err or f"命令失败, 返回码 {code}"
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
        self._ssh_service.close_host("127.0.0.1", 22)


    def close_all_device_connections(self) -> None:
        """关闭所有底层 SSH 连接。"""
        self._ssh_service.close_all()
