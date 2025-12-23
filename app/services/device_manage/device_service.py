from typing import Dict, Any, Tuple
import time

from PyQt5.QtCore import QObject, pyqtSignal
from paramiko.ssh_exception import AuthenticationException, SSHException

from app.common.communication.clients.Doip_Client import DoIPClientHandler
from app.common.communication.clients.Someip_Client import SomeIPClient
from app.modules.device_management.models.device_model import CONNECTING, DISCONNECTED, CONNECT_FAILED
from app.services.communication.ssh_service import SSHService
from app.services.configuration.config_service import AppConfigurationService
from app.core.dependency_injection import di_container
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
    protocol_status_changed_signal = pyqtSignal(dict)
    # 设备操作进度信号：payload 为文本描述
    """设备管理领域的 Service 层封装。"""

    def __init__(self) -> None:
        super().__init__()
        self._ssh_service = SSHService()
        # 独立的 DoIP / SomeIP 客户端实例，由 DeviceService 统一管理生命周期
        self._doip_handler: DoIPClientHandler | None = None
        self._someip_client: SomeIPClient | None = None

        self._config_service = di_container.resolve(AppConfigurationService)
        if not self._config_service:
            self._config_service = AppConfigurationService()
            di_container.register_singleton(AppConfigurationService, self._config_service)

    def connect_device(self, device: Dict[str, Any]) -> None:
        """连接单个设备：按 SSH/DoIP/SomeIP 三种协议尝试建链，并统一发出状态信号。
        """
        # 设置初始状态为 CONNECTING
        device["ssh_connect_status"] = CONNECTING
        device["doip_connect_status"] = CONNECTING
        device["someip_connect_status"] = CONNECTING
        self._change_status(device)

        # 强制等待，确保UI有时间渲染所有协议的转圈状态
        time.sleep(0.5)

        # 1. DoIP 连接
        # 模拟连接过程，避免瞬间完成导致看不到转圈
        time.sleep(1.0)
        self._connect_doip(device)
        self._change_status(device)

        # 2. SomeIP 客户端准备
        time.sleep(1.0)
        self._connect_someip(device)
        self._change_status(device)

        # 3. SSH 连接：通过执行 ipconfig 验证链路
        time.sleep(0.5)
        self._connect_ssh(device)
        self._change_status(device)


    def disconnect_device(self, device: Dict[str, Any]) -> None:
        """断开设备三种协议连接，并发出状态信号。"""
        # 1. 主动关闭 DoIP 连接
        self._disconnect_doip(device)

        # 2.停止 SOME/IP 客户端
        self._disconnect_someip(device)

        # 3.断开ssh连接
        self._disconnect_ssh(device)
        self._change_status(device)


    def _disconnect_ssh(self, device):
        self.log_signal.emit("正在通过SSH断开设备...")
        ip = device.get("ip")
        port = int(device.get("port", 22))
        try:
            self._ssh_service.close_host(ip, port)
            device["ssh_connect_status"] = DISCONNECTED
            device["ssh_connect_info"] = "SSH已断链成功"
        except Exception as e:
            msg = f"SSH 断开异常: {e}"
            self.log_signal.emit(msg)
            device["ssh_connect_status"] = CONNECT_FAILED
            device["ssh_connect_info"] = msg

    def _disconnect_someip(self, device):
        if self._someip_client is not None:
            try:
                self._someip_client.stop()
                device["someip_connect_status"] = DISCONNECTED
                device["someip_connect_info"] = "SomeIP已断链成功"
            except Exception as e:
                msg = f"SomeIP 断开异常: {e}"
                self.log_signal.emit(msg)
                device["someip_connect_status"] = CONNECT_FAILED
                device["someip_connect_info"] = msg


    def _disconnect_doip(self, device):
        if self._doip_handler is not None:
            try:
                self._doip_handler.disconnect()
                device["doip_connect_status"] = DISCONNECTED
                device["doip_connect_info"] = "DoIP已断链成功"
            except Exception as e:
                msg = f"SomeIP 断开异常: {e}"
                self.log_signal.emit(msg)
                device["doip_connect_status"] = CONNECT_FAILED
                device["doip_connect_info"] = msg


    def _connect_ssh(self, device):
        ip = device.get("ip")
        port = int(device.get("port", 22))
        self.log_signal.emit(f"正在通过SSH连接设备 {ip}:{port}...")
        out, err, code = self.execute_ssh_command_on_device(device, "get_ccu_all_version")
        if code == 0:
            self.log_signal.emit("SSH 连接成功")
            device["ssh_connect_status"] = "建链成功"
            device["ssh_connect_info"] = f"已成功连接到SSH服务 {ip}:{port}"
        else:
            self.log_signal.emit(f" SSH 连接失败: {err}")
            device["ssh_connect_status"] = "连接失败"
            device["ssh_connect_info"] = err or f"SSH 连接{ip}:{port}失败"


    def _connect_doip(self, device: Dict[str, Any]) -> None:
        """内部辅助：为当前设备建立 DoIP 连接，并在 device 上写入状态字段。
        约定使用字段：
          - doip_connect_status: 建链成功 / 连接失败 / 离线
          - doip_connect_info: 失败原因或成功提示
        """
        ip = device.get("ip") or ""
        # 默认使用经典 DoIP 端口 13400，如有特殊端口可后续通过 device 字段扩展
        tcp_port = int(device.get("doip_port", 13400))

        # 从 AppConfig 获取 DoIP 配置
        doip_settings = self._config_service.doip_settings

        # 协议版本转换: 0 -> 0x02 (DoIP V2), 1 -> 0x03 (DoIP V3/Other)
        # 注意：界面上 Index 0 是 V2, Index 1 是 V1(但用户要求传3)
        pv_index = int(doip_settings.get("protocol_version", 0))
        if pv_index == 1:
            protocol_version = 0x03
        else:
            protocol_version = 0x02

        client_logical_address = int(doip_settings.get("logical_addr", "0x0E80"), 16)
        routing_type = int(doip_settings.get("routing_type", "0x00"), 16)
        ecu_logical_address = int(doip_settings.get("physical_addr", "0x004F"), 16)

        # ECU 逻辑地址及本机逻辑地址可按需从 device 中扩展配置，这里使用 DoIPClientHandler 默认值
        self.log_signal.emit(f"正在通过DoIP连接设备 {ip}:{tcp_port}...")
        if not ip:
            device["doip_connect_status"] = "连接失败"
            device["doip_connect_info"] = "缺少 ECU IP"
            return

        if self._doip_handler is None:
            self._doip_handler = DoIPClientHandler()

        # 处理网卡选择
        target_ip = doip_settings.get("network_interface_ip")
        if target_ip:
            self._doip_handler.select_network_interface(target_ip)
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
        local_ip = device.get("ip")  # 可选字段
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
        self.protocol_status_changed_signal.emit(payload)

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


    def close_device_all_connections(self, device: Dict[str, Any]) -> None:
        self.disconnect_device(device)

    # ---- 提供给其他 Service 复用的 已连接成功的 DoIP / SomeIP /ssh 能力 ----
    def get_doip_client(self) -> DoIPClientHandler | None:
        """返回当前 DoIP 客户端实例（若尚未连接则为 None）。"""
        if self._doip_handler is not None and self._doip_handler.is_connected():
            return self._doip_handler
        return None

    def send_doip_payload(
        self,
        payload: bytes,
        *,
        timeout: float | None = None,
        response_index: int | None = None,
        target_did: int | None = None,
        prefer_last: bool = False,
    ) -> bytes | None:
        """统一的 DoIP 发送接口，供 Topology/Diagnostic 等业务 Service 重用。"""
        client = self.get_doip_client()
        if client is None:
            self.log_signal.emit("DoIP 客户端未连接，无法发送报文")
            return None

        if timeout is None:
            try:
                timeout_ms = int(self._config_service.diag_layer_settings.get("s3_client_time", 3000))
                timeout = timeout_ms / 1000.0
            except (ValueError, TypeError):
                timeout = 3.0

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
        """返回当前 SomeIP 客客户端实例（可能为 None）。"""
        return self._someip_client

    def get_ssh_service(self) -> SSHService:
        """返回当前 SSH 服务实例。"""
        return self._ssh_service

    def close_device_connections(self):
        self._ssh_service.close_all()
        self._someip_client.stop()
        self._doip_handler.disconnect()


def main():
    # 测试入口
    # 注意：请根据实际环境修改 IP、用户名和密码
    test_device = {
        "ip": "10.1.0.79",
        "port": 22,
        "username": "root",
        "password": "$ww0328_G"
    }

    print(f"Starting SSH test for device: {test_device['ip']}")
    service = DeviceService()

    # 监听日志信号
    service.log_signal.connect(lambda msg: print(f"[Service Log] {msg}"))

    # 1. 测试 get_ccu_all_version
    cmd1 = "get_ccu_all_version"
    print(f"\n>>> Executing: {cmd1}")
    out1, err1, code1 = service.execute_ssh_command_on_device(test_device, cmd1)
    print(f"Res Code: {code1}")
    print(f"Output:\n{out1}")
    if err1:
        print(f"Error:\n{err1}")

    # 2. 测试 df -h
    cmd2 = "df -h"
    print(f"\n>>> Executing: {cmd2}")
    out2, err2, code2 = service.execute_ssh_command_on_device(test_device, cmd2)
    print(f"Code: {code2}")
    print(f"Output:\n{out2}")
    if err2:
        print(f"Error:\n{err2}")


if __name__ == "__main__":
    main()
