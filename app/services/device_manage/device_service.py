import time
import warnings
import socket
import psutil
from typing import Dict, Any, Callable, Optional

from PyQt5.QtCore import QObject, pyqtSignal
from paramiko.ssh_exception import AuthenticationException, SSHException

from app.common.communication.clients.Doip_Client import DoIPClientHandler
from app.common.communication.clients.Someip_Client import SomeIPClient
from app.common.communication.clients.ssh_client import SSHClient
from app.common.utils.security_access_helper import SecurityAccessHelper
from app.core.dependency_injection import di_container
from app.modules.device_management.models.device_model import CONNECTING, DISCONNECTED, CONNECT_FAILED
from app.services.configuration.config_service import AppConfigurationService


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

    def connect_device(self, device: Dict[str, Any], log_signal: Optional[pyqtSignal] = None) -> None:
        """连接单个设备：按 SSH/DoIP/SomeIP 三种协议尝试建链，并统一发出状态信号。
        """
        # 保存设备配置以便重连使用
        self._last_connected_device = device

        # 设置初始状态为 CONNECTING
        device["ssh_connect_status"] = CONNECTING
        device["doip_connect_status"] = CONNECTING
        device["someip_connect_status"] = CONNECTING
        self._change_status(device)

        # 强制等待，确保UI有时间渲染所有协议的转圈状态
        time.sleep(0.5)

        # 1. SomeIP 客户端准备
        time.sleep(1.0)
        self._connect_someip(device, log_signal)
        self._change_status(device)

        # 2. DoIP 连接
        # 模拟连接过程，避免瞬间完成导致看不到转圈
        time.sleep(1.0)
        self._connect_doip(device, log_signal)
        self._change_status(device)

        # 3. SSH 连接：通过执行激活DoIP激活命令，才能连接ssh服务
        time.sleep(0.5)
        self.active_ssh_command(log_signal)
        self._connect_ssh(device, log_signal=log_signal)
        self._change_status(device)
        if log_signal is not None:
            log_signal.emit("设备连接成功")
        else:
            self.log_signal.emit("设备连接成功")

    def reset_connection_clients(self) -> None:
        """强制关闭并清理当前客户端实例，确保后续重连为全新连接。(公开版本，供Controller调用)"""
        self._reset_connection_clients()

    def _reset_connection_clients(self) -> None:
        """强制关闭并清理当前客户端实例，确保后续重连为全新连接。"""
        try:
            if self._ssh_client is not None:
                self._ssh_client.disconnect()
        except Exception:
            pass
        try:
            if self._someip_client is not None:
                self._someip_client.stop()
        except Exception:
            pass
        try:
            if self._doip_handler is not None:
                self._doip_handler.disconnect()
        except Exception:
            pass
        self._ssh_client = None
        self._someip_client = None
        self._doip_handler = None

    def reconnect_device(self, log_signal: Optional[pyqtSignal] = None) -> None:
        """请求重连最后一次连接的设备。逻辑委托给 Controller 层处理。"""
        if not self._last_connected_device:
            self.log_signal.emit("无上次连接设备记录，无法重连")
            return

        # 发送重连请求信号，由 Controller 接收并执行 _do_disconnect / _do_connect
        # 传递设备信息副本，供 Controller 查找对应索引
        device = self._last_connected_device.copy()

        # 发送信号，通知上层 UI 控制器执行重连流程
        self.reconnect_requested_signal.emit(device, log_signal)


    def disconnect_device(self, device: Dict[str, Any], log_signal: Optional[pyqtSignal] = None) -> None:
        """断开设备三种协议连接，并发出状态信号。"""
        # 1. 主动关闭 DoIP 连接
        self._disconnect_doip(device, log_signal)
        # 2.停止 SOME/IP 客户端
        self._disconnect_someip(device, log_signal)
        # 3.断开ssh连接
        self._disconnect_ssh(device, log_signal)
        self._change_status(device)


    def _disconnect_ssh(self, device, log_signal: Optional[pyqtSignal] = None):
        _log = log_signal.emit if log_signal else self.log_signal.emit
        _log("正在通过SSH断开设备...")
        try:
            if not self._ssh_client is None and self._ssh_client.is_connected():
                self._ssh_client.disconnect()
                device["ssh_connect_status"] = DISCONNECTED
                device["ssh_connect_info"] = "SSH已断链成功"
        except Exception as e:
            msg = f"SSH 断开异常: {e}"
            _log(msg)
            device["ssh_connect_status"] = CONNECT_FAILED
            device["ssh_connect_info"] = msg

    def _disconnect_someip(self, device, log_signal: Optional[pyqtSignal] = None):
        _log = log_signal.emit if log_signal else self.log_signal.emit
        if self._someip_client is not None:
            try:
                self._someip_client.stop()
                device["someip_connect_status"] = DISCONNECTED
                device["someip_connect_info"] = "SomeIP已断链成功"
            except Exception as e:
                msg = f"SomeIP 断开异常: {e}"
                _log(msg)
                device["someip_connect_status"] = CONNECT_FAILED
                device["someip_connect_info"] = msg


    def _disconnect_doip(self, device, log_signal: Optional[pyqtSignal] = None):
        _log = log_signal.emit if log_signal else self.log_signal.emit
        if self._doip_handler is not None:
            try:
                self._doip_handler.disconnect()
                device["doip_connect_status"] = DISCONNECTED
                device["doip_connect_info"] = "DoIP已断链成功"
            except Exception as e:
                msg = f"SomeIP 断开异常: {e}"
                _log(msg)
                device["doip_connect_status"] = CONNECT_FAILED
                device["doip_connect_info"] = msg

    def is_ssh_connected(self, device: Dict[str, Any]) -> bool:
        """检查指定设备的 SSH 是否连接成功。"""
        ip = device.get("ip")
        port = int(device.get("port", 22))
        if not ip:
            return False
        return self._ssh_client.is_connected()

    def _connect_doip(self, device: Dict[str, Any], log_signal: Optional[pyqtSignal] = None) -> None:
        """内部辅助：为当前设备建立 DoIP 连接，并在 device 上写入状态字段。
        约定使用字段：
          - doip_connect_status: 建链成功 / 连接失败 / 离线
          - doip_connect_info: 失败原因或成功提示
        """
        _log = log_signal.emit if log_signal else self.log_signal.emit
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
        _log(f"正在通过DoIP连接设备 {ip}:{tcp_port}...")
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
            return

        if ok:
            device["doip_connect_status"] = "建链成功"
            device["doip_connect_info"] = f"DoIP 已连接到 {ip}:{tcp_port}"
        else:
            device["doip_connect_status"] = "连接失败"
            device["doip_connect_info"] = f"DoIP 连接 {ip}:{tcp_port} 失败"

    def _get_mac_address(self, ip_address: str, log_signal: Optional[pyqtSignal] = None) -> str:
        """获取指定 IP 地址对应的网卡 MAC 地址"""
        _log = log_signal.emit if log_signal else self.log_signal.emit
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

    def _ensure_someip_client(self, device: Dict[str, Any], log_signal: Optional[pyqtSignal] = None) -> SomeIPClient | None:
        """内部辅助：创建并启动 SomeIPClient。

        使用设备配置中的参数进行连接：
        - client_port: 作为本地绑定的端口 (local_port)
        - multicast_ip: 组播 IP
        - multicast_port: 组播端口
        - vlan_id: VLAN ID
        - client_id: 客户端 ID (用于 SomeIP header)
        """
        _log = log_signal.emit if log_signal else self.log_signal.emit
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

    def _connect_someip(self, device: Dict[str, Any], log_signal: Optional[pyqtSignal] = None) -> None:
        _log = log_signal.emit if log_signal else self.log_signal.emit
        _log(f"正在通过SomeIP连接设备...")
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

    def _connect_ssh(
        self,
        device: Dict[str, Any],
        timeout: int = 30,
        log_signal: Optional[pyqtSignal] = None
    ) -> tuple[str, str, int] | None:
        _log = log_signal.emit if log_signal else self.log_signal.emit
        host = device.get("ip")
        port = int(device.get("port", 22))
        username = device.get("user") or device.get("username") or "root"
        password = device.get("password")
        key_file = device.get("key_file")
        try:
            # register_host 幂等，重复调用安全
            self._ssh_client = SSHClient()
            connect_result = self._ssh_client.connect(host, port, username, password)
            if not connect_result:
                device["ssh_connect_status"] = "连接失败"
                device["ssh_connect_info"] = "SSH 认证失败"
                return "", "SSH 认证失败", 255
            device["ssh_connect_status"] = "建链成功"
            device["ssh_connect_info"] = f"SSH 已连接到 {host}:{port}"
            _log(f"SSH 已连接到 {host}:{port}")
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
        """获取当前的 DoIP 客户端实例"""
        if self._doip_handler is None:
            self._doip_handler = DoIPClientHandler()
        return self._doip_handler

    def get_ssh_client(self) -> Optional[SSHClient]:
        """获取当前的 SSH 客户端实例"""
        return self._ssh_client
    def get_someip_client(self) -> Optional[SomeIPClient]:
        """获取当前的 SomeIP 客户端实例"""
        return self._someip_client

    def get_current_device_ip(self) -> Optional[str]:
        """获取当前连接设备的 IP 地址"""
        if self._last_connected_device:
            return self._last_connected_device.get("ip")
        return None


    def close_device_connections(self):
        if self._ssh_client is not None:
            self._ssh_client.disconnect()
        if self._someip_client is not None:
            self._someip_client.stop()
        if self._doip_handler is not None:
            self._doip_handler.disconnect()


    def active_ssh_command(self, log_signal: Optional[pyqtSignal] = None):
        """
        发送 DoIP 指令激活 SSH (或其他功能)
        """
        _log = log_signal.emit if log_signal else self.log_signal.emit
        _log("开始发送激活 SSH 指令...")
        # 31 01 BE E9
        routine = bytes.fromhex("31 01 BE E9")
        self.execute_secure_routine(routine, sec_level=0x21, log_signal=log_signal)

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
        # 1. 获取客户端实例
        client = self.get_doip_client()
        if client is None:
            self.log_signal.emit("错误：DoIP 客户端实例为 None")
            return None

        # 计算超时
        if timeout is None:
            try:
                timeout_ms = int(self._config_service.diag_layer_settings.get("s3_client_time", 3000))
                timeout = timeout_ms / 1000.0
            except (ValueError, TypeError):
                timeout = 3.0

        # 2. 预检查连接状态
        # 如果未连接，且有上次连接记录，先尝试重连一次
        if not client.connected:
            if self._last_connected_device:
                self.log_signal.emit("发现 DoIP 未连接，尝试利用上次记录重连...")
                self._connect_doip(self._last_connected_device)
                if not client.connected:
                    self.log_signal.emit("重连失败，放弃发送")
                    return None
            else:
                # self.log_signal.emit("DoIP 未连接且无历史连接记录，无法自动重连")
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
                self.log_signal.emit("发送报文时连接断开")
                if self._last_connected_device:
                    self.log_signal.emit("尝试通过断线重连恢复并重发...")
                    self._connect_doip(self._last_connected_device)

                    if client.connected:
                        self.log_signal.emit("断线重连成功，正在重发报文...")
                        resp = client.send_doip_message(
                            payload,
                            timeout=timeout,
                            response_index=response_index,
                            target_did=target_did,
                            prefer_last=prefer_last,
                        )
                    else:
                        self.log_signal.emit("断线重连失败")
                else:
                    self.log_signal.emit("连接断开且无重连信息")
            else:
                # 状态仍为 Connected，说明是单纯的超时，未发生断链
                # self.log_signal.emit("发送等到超时（未收到响应），连接保持正常")
                pass

        return resp

    def execute_secure_routine(self, routine_command: bytes, sec_level: int = 0x21, return_on_auth_fail: bool = False, log_signal: Optional[pyqtSignal] = None) -> bool | bytes:
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
        log_emit = log_signal.emit if log_signal else self.log_signal.emit

        client = self.get_doip_client()
        if not client:
            log_emit("DoIP 未连接，无法发送指令")
            return False

        # 1. 诊断会话控制 (10 03)
        tx_session = bytes.fromhex("10 03")
        log_emit(f"发送: {tx_session.hex(' ').upper()}")
        rx_session = client.send_doip_message(tx_session)
        if not rx_session or rx_session[0] != 0x50:
            log_emit(f"会话控制失败: {rx_session.hex(' ').upper() if rx_session else '无响应'}")
            return False
        log_emit(f"会话控制成功: {rx_session.hex(' ').upper()}")

        # 2. 安全访问
        tx_seed = bytes([0x27, sec_level])
        log_emit(f"请求种子: {tx_seed.hex(' ').upper()}")
        rx_seed = client.send_doip_message(tx_seed)

        if not rx_seed or rx_seed[0] != 0x67:
            log_emit(f"请求种子失败: {rx_seed.hex(' ').upper() if rx_seed else '无响应'}")
            return False
        log_emit(f"收到种子: {rx_seed.hex(' ').upper()}")

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
