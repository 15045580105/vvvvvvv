from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional, Any

from app.services.device_manage.device_service import DeviceService


class TopologyServiceError(Exception):
    """拓扑数据采集失败。"""


@dataclass
class TopologySnapshot:
    # 节点：名称、图标、状态、相对 X/Y 坐标
    nodes: List[Tuple[str, str, str, int, int]]
    # 网络：名称、状态、带宽/负载信息
    networks: List[Tuple[str, str, str]]
    # 车辆/整车信息区
    vehicle_info: Dict[str, str]
    # 服务运行状态
    service_status: Dict[str, str]
    # 安全与证书信息
    security_info: Dict[str, str]
    # 网络管理/电源唤醒等
    network_management: Dict[str, str]
    # 存储信息
    storage_info: Dict[str, str]


class TopologyService:
    """负责通过 DoIP/SSH 等方式采集拓扑信息的服务。

    当前支持两种模式：
      * use_dummy=True: 返回本地模拟数据（UI 开发和联调阶段使用）；
      * use_dummy=False: 通过注入的 DeviceService 使用 DoIPClient 向 ECU 请求真实拓扑数据。
    """

    def __init__(self, device_service: Optional[DeviceService] = None, *, use_dummy: bool = True) -> None:
        self._use_dummy = use_dummy
        self._device_service = device_service

    def fetch_snapshot(self, device_info: Dict[str, Any] = None) -> TopologySnapshot:
        """采集整车拓扑概览。后续可接入 DoIP，目前在 use_dummy=True 时返回模拟数据。"""
        if self._use_dummy or self._device_service is None:
            return self._build_dummy_snapshot()
        return self._fetch_doip_snapshot(device_info)

    def _fetch_doip_snapshot(self, device_info: Dict[str, Any] = None) -> TopologySnapshot:
        """通过已建立的 DoIP 连接向 ECU 请求拓扑信息，并转换为 TopologySnapshot。"""
        if self._device_service is None:
            raise TopologyServiceError("未注入 DeviceService，无法通过 DoIP 采集拓扑")

        # 1. 车辆信息
        vin = self._get_vin()
        vehicle_mode = self._get_vehicle_mode()
        user_mode = self._get_user_mode()
        factory_mode = self._get_factory_mode()
        voltage = self._get_voltage()
        vehicle_info = {
            "vin": vin,
            "vehicle_mode": vehicle_mode,
            "user_mode": user_mode,
            "factory_mode": factory_mode,
            "voltage": voltage
        }

        # 2. 服务状态 (SomeIP)
        service_status_raw = self._get_service_status()
        service_status = {"status_summary": service_status_raw}

        # 3. 信息安全
        cert_info = self._get_cert_info()
        key_slot = self._get_key_slot_status()
        cms_env = self._get_cms_env()
        security_info = {
            "cert_info": cert_info,
            "key_slot_status": key_slot,
            "cms_env": cms_env
        }

        # 4. 以太网 link 状态（新增）：通过 22 BE1A 获取当前各节点 link up/down 信息
        link_status = self._get_eth_link_status()

        # 5. PNC 网络管理 (SomeIP)
        pnc_mgmt = self._get_pnc_status()
        # 将 link 状态合并进 network_management，便于统一在信息块里展示
        network_mgmt: Dict[str, str] = {}
        network_mgmt.update(pnc_mgmt)
        network_mgmt.update(link_status)

        # 6. 存储/版本信息 (SSH)
        storage_info_str = self._get_storage_info(device_info)
        version_info = self._get_version_info(device_info)
        storage_info = {
            "a_core_storage": storage_info_str,
            "m_core_storage": version_info,
        }

        # 拓扑节点和网络结构目前仍使用 dummy
        dummy = self._build_dummy_snapshot()

        return TopologySnapshot(
            nodes=dummy.nodes,
            networks=dummy.networks,
            vehicle_info=vehicle_info,
            service_status=service_status,
            security_info=security_info,
            network_management=network_mgmt,
            storage_info=storage_info,
        )

    # --- DoIP Helpers ---
    def _send_uds_read(self, did_high, did_low) -> Optional[bytes]:
        payload = bytes([0x22, did_high, did_low])
        rx = self._device_service.send_doip_payload(payload, timeout=1.0)
        if rx and len(rx) >= 3 and rx[0] == 0x62 and rx[1] == did_high and rx[2] == did_low:
            return rx[3:]
        return None

    def _get_eth_link_status(self) -> Dict[str, str]:
        """读取以太网各节点 link 状态（UDS 22 BE1A）。

        返回一个 dict，用于填充 network_management，例如：
        {
            "eth_link_idc": "UP",
            "eth_link_adc": "DOWN",
            ...
        }

        具体 bit/字节解析需参考 DPT 表，这里提供一个占位解析：
        - 若成功返回数据，则将��始 hex 串挂到 eth_link_raw 上，方便后续调试；
        - 一旦协议细节明确，可在此根据位定义拆分到各节点。
        """
        result: Dict[str, str] = {}
        # 使用 UDS 22 BE1A
        payload = bytes([0x22, 0xBE, 0x1A])
        try:
            rx = self._device_service.send_doip_payload(payload, timeout=1.0)
        except Exception as e:
            result["eth_link_raw"] = f"读取失败: {e}"
            return result

        if not rx or len(rx) < 3 or rx[0] != 0x62 or rx[1] != 0xBE or rx[2] != 0x1A:
            result["eth_link_raw"] = "无有效响应"
            return result

        data = rx[3:]
        # 暂不清楚各节点对应 bit/byte 的精确含义，这里先挂原始 hex，方便 UI 或日志查看
        result["eth_link_raw"] = data.hex().upper()
        return result

    def _get_vin(self) -> str:
        data = self._send_uds_read(0xF1, 0x90)
        if data:
            try:
                return data.decode('ascii').strip()
            except:
                return data.hex()
        return "Unknown"

    def _get_vehicle_mode(self) -> str:
        data = self._send_uds_read(0x50, 0x01)
        if data:
            mode = data[0] & 0x0F
            modes = {
                0x00: "正常模式", 0x01: "生产模式", 0x02: "运输模式", 0x03: "展厅模式",
                0x04: "碰撞模式", 0x05: "维修模式"
            }
            return modes.get(mode, f"未知模式({mode})")
        return "Unknown"

    def _get_factory_mode(self) -> str:
        data = self._send_uds_read(0x01, 0x10)
        if data:
            val = data[0]
            if 0x10 <= val <= 0xFF:
                return "工厂模式"
            return "非工厂模式"
        return "Unknown"

    def _get_voltage(self) -> str:
        data = self._send_uds_read(0x10, 0x00)
        if data:
            # 假设是 raw hex 或者某种编码，这里直接转 hex 显示
            return f"{int.from_bytes(data, 'big')} mV" # 假设单位 mV，具体需确认
        return "Unknown"

    def _get_cert_info(self) -> str:
        # 31 01 BE E8 (Routine Control)
        # 需要 Security Access，这里尝试直接发送，如果失败则返回提示
        payload = bytes([0x31, 0x01, 0xBE, 0xE8])
        rx = self._device_service.send_doip_payload(payload, timeout=2.0)
        if rx and rx[0] == 0x71:
            return "读取成功: " + rx[4:].hex() # 假设格式
        return "读取失败(可能需要解锁)"

    def _get_key_slot_status(self) -> str:
        data = self._send_uds_read(0xBE, 0x2C)
        return data.hex() if data else "Unknown"

    def _get_cms_env(self) -> str:
        data = self._send_uds_read(0xBE, 0x2D)
        return data.hex() if data else "Unknown"

    # --- SomeIP Helpers ---
    def _someip_request_sync(self, service, method, payload=b'', timeout=2.0) -> Optional[Any]:
        client = self._device_service.get_someip_client()
        if not client:
            return None

        result = None
        event = threading.Event()

        def cb(pkt):
            nonlocal result
            result = pkt
            event.set()

        # 注册回调
        client.register_callback(service, method, cb)
        try:
            # 发送请求 (假设 target IP 是组播或已知)
            # 这里需要 target IP，DeviceService 里的 client 可能有默认 multicast
            # 但通常请求是单播。这里假设 client 已经配置好或者我们广播
            # 由于 DeviceService.send_someip_request 需要 target_ip，我们这里直接用 client 发
            # 暂时用 '239.255.0.1' 或 client.multicast_ip 如果是 discovery，但这是 method call
            # 假设发给 localhost 或者 device IP?
            # 我们没有 device IP 在这里。
            # 这是一个问题。SomeIP 需要目标 IP。
            # 暂时使用 '127.0.0.1' 模拟或者需要 device_info 中的 IP
            target_ip = "127.0.0.1" # Placeholder
            client.send_request(service, method, payload, target_ip=target_ip)
            event.wait(timeout)
        finally:
            # 清理回调 (SomeIPClient 暂无 unregister，可能会累积)
            pass

        return result

    def _get_user_mode(self) -> str:
        # Service 0x1055, Event 0x9001.
        # 这是一个 Event，通常需要 Subscribe。
        # 这里简化为尝试等待 Event，如果 client 已经 subscribe 了。
        # 或者我们尝试 subscribe。
        client = self._device_service.get_someip_client()
        if client:
            client.subscribe_eventgroup(0x1055, 0xFFFF, 0x9001) # 假设 instance 0xFFFF
            # 等待回调... 略复杂，暂时返回 "监听中..."
            return "监听中..."
        return "Client未就绪"

    def _get_service_status(self) -> str:
        # 10FA, 0003
        # 这是一个 Method Call
        # 需要 target IP。
        return "获取中..." # 需完善 SomeIP 通信机制

    def _get_pnc_status(self) -> Dict[str, str]:
        # 多个 Notifier，需要 Subscribe
        return {
            "power_wake_source": "Unknown",
            "pnc": "Unknown",
            "rt1_net": "Unknown"
        }

    # --- SSH Helpers ---
    def _get_storage_info(self, device_info: Dict[str, Any]) -> str:
        if not device_info: return "无设备信息"
        cmd = "df -h | grep /dev"
        out, err, code = self._device_service.execute_ssh_command_on_device(device_info, cmd)
        if code == 0:
            return out.strip()
        return f"Error: {err}"

    def _get_version_info(self, device_info: Dict[str, Any]) -> str:
        if not device_info: return "无设备信息"
        cmd = "get_ccu_all_version"
        out, err, code = self._device_service.execute_ssh_command_on_device(device_info, cmd)
        if code == 0:
            return out.strip()
        return f"Error: {err}"

    # -------------------- 模拟数据路径 --------------------
    @staticmethod
    def _build_dummy_snapshot() -> TopologySnapshot:
        nodes = [
            ("CCU主控制器", "🖥️", "正常", 0, 0),
            ("CCU A-M核(RT1)", "⚡", "正常", -250, -150),
            ("CCU A-M核(RT2)", "⚡", "离线", 250, -150),
            ("IDC SoC", "🧠", "正常", -250, 150),
            ("TBOX", "📡", "正常", 250, 150),
            ("ADC SoC", "🎛️", "正常", -350, 0),
            ("ADC MCU", "🔌", "正常", 350, 0),
            ("激光雷达", "📡", "正常", 0, -200),
        ]
        networks = [
            ("电源管理网络", "正常", "2.1 KB/s"),
            ("PNC网络", "正常", "5.8 KB/s"),
            ("RT1外网报文", "正常", "1.2 KB/s"),
            ("RT2外网报文", "正常", "0.8 KB/s"),
            ("A核应用网络", "正常", "12.5 KB/s"),
            ("OBD-CAN网络", "正常", "0.3 KB/s"),
        ]
        vehicle_info = {
            "vin": "LJ8A12345CCU67890",
            "vehicle_mode": "测试模式",
            "user_mode": "体验版",
            "factory_mode": "关闭",
            "voltage": "12.4 V",
        }
        service_status = {
            "srv_id01": "在线",
            "srv_id02": "运行中",
            "srv_id03": "待命",
        }
        security_info = {
            "cert_server": "cms.prod.internal",
            "pki_status": "正常",
            "cert_valid_date": "2026-05-30",
            "key_slot_status": "Slot#2 / 正常",
            "tls_switch": "已开启",
            "secoc_switch": "启用",
            "cms_env": "Production",
        }
        network_mgmt = {
            "power_wake_source": "车钥匙+远程",
            "pnc": "保持在线",
            "rt1_net_source": "CCU A-M核",
            "rt2_net_source": "CCU A-M核",
            "rt1_ext_msg": "稳定",
            "rt2_ext_msg": "低报文",
            "a_core_net_req": "已授权",
            "obd_can_net": "待机",
        }
        storage_info = {
            "a_core_storage": "65% / 128GB",
            "m_core_storage": "48% / 64GB",
        }
        return TopologySnapshot(
            nodes=nodes,
            networks=networks,
            vehicle_info=vehicle_info,
            service_status=service_status,
            security_info=security_info,
            network_management=network_mgmt,
            storage_info=storage_info,
        )
