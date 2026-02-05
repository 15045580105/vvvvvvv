from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional, Any, Callable
import re

from app.services.device_manage.device_service import DeviceService
from app.services.diagnostic.dpt_service import DPTService
import math

class TopologyServiceError(Exception):
    """拓扑数据采集失败。"""


@dataclass
class TopologySnapshot:
    # 节点：名称、图标、状态、相对 X/Y 坐标
    nodes: List[Tuple[str, str, str, int, int]]
    # 车辆/整车信息区
    vehicle_info: Dict[str, str] = None
    # 服务运行状态
    service_status: Dict[str, str] = None
    # 安全与证书信息
    security_info: Dict[str, str] = None
    # 网络管理/电源唤醒等
    network_management: Dict[str, str] = None
    # 存储信息
    storage_info: Dict[str, str] = None


class TopologyService:
    """负责通过 DoIP/SSH 等方式采集拓扑信息的服务。

    当前支持两种模式：
      * use_dummy=True: 返回本地模拟数据（UI 开发和联调阶段使用）；
      * use_dummy=False: 通过注入的 DeviceService 使用 DoIPClient 向 ECU 请求真实拓扑数据。
    """

    def __init__(self, device_service: Optional[DeviceService] = None) -> None:
        self._device_service = device_service
        self._dpt_service = DPTService()
        try:
            self._dpt_service.load_from_file(r"D:\uidq9000\Downloads\dpt.json")
        except Exception as e:
            print(f"Failed to load DPT file: {e}")

    def fetch_snapshot(self, log_callback: Optional[Callable[[str], None]] = None) -> TopologySnapshot:
        """采集整车拓扑概览。后续可接入 DoIP，目前在 use_dummy=True 时返回模拟数据。"""
        return self._fetch_doip_snapshot(log_callback=log_callback)

    def fetch_vehicle_info(self, log_callback: Optional[Callable[[str], None]] = None) -> Dict[str, str]:
        """仅采集车辆信息"""
        if log_callback: log_callback("开始采集车辆信息...")
        info = {
            "vin": self._get_vin(log_callback),
            "vehicle_mode": self._get_vehicle_mode(log_callback),
            "user_mode": self._get_user_mode(log_callback),
            "factory_mode": self._get_factory_mode(log_callback),
            "voltage": self._get_voltage(log_callback)
        }
        if log_callback: log_callback("车辆信息采集完成")
        return info

    def fetch_service_status(self, log_callback: Optional[Callable[[str], None]] = None) -> Dict[str, str]:
        """仅采集服务状态"""
        if log_callback: log_callback("开始采集服务状态...")
        service_status_raw = self._get_service_status(log_callback)
        if log_callback: log_callback("服务状态采集完成")
        return {"status_summary": service_status_raw}

    def fetch_security_info(self, log_callback: Optional[Callable[[str], None]] = None) -> Dict[str, str]:
        """仅采集证书信息"""
        if log_callback: log_callback("开始采集证书信息...")
        info = {
            "cert_info": self._get_cert_info(log_callback),
            "key_slot_status": self._get_key_slot_status(log_callback),
            "cms_env": self._get_cms_env(log_callback)
        }
        if log_callback: log_callback("证书信息采集完成")
        return info

    def fetch_network_mgmt(self, log_callback: Optional[Callable[[str], None]] = None) -> Dict[str, str]:
        """仅采集网络管理信息"""
        if log_callback: log_callback("开始采集网络管理信息...")
        pnc_mgmt = self._get_pnc_status(log_callback)
        network_mgmt = {}
        network_mgmt.update(pnc_mgmt)
        if log_callback: log_callback("网络管理信息采集完成")
        return network_mgmt

    def fetch_storage_info(self, log_callback: Optional[Callable[[str], None]] = None) -> Dict[str, str]:
        """仅采集存储信息"""
        if log_callback: log_callback("开始采集存储信息...")
        info = {
            "a_core_storage": self._get_storage_info(log_callback)
        }
        if log_callback: log_callback("存储信息采集完成")
        return info

    def fetch_version_info(self, log_callback: Optional[Callable[[str], None]] = None) -> Dict[str, str]:
        """仅采集版本信息"""
        if log_callback: log_callback("开始采集版本信息...")
        info = {
            "m_core_storage": self._get_version_info(log_callback)
        }
        if log_callback: log_callback("版本信息采集完成")
        return info

    def _extract_node_name(self, key: str) -> str:
        """从 DPT Key 中提取节点名称，并进行标准化修正"""
        node_name = key

        # 提取规则
        # 1. "与...连接的以太网联接状态"
        match = re.search(r"与(.+?)连接的以太网联接状态", key)
        if match:
            node_name = match.group(1).strip()
        else:
            # 2. "与...的以太网联接状态"
            match = re.search(r"与(.+?)的以太网联接状态", key)
            if match:
                node_name = match.group(1).strip()
            else:
                # 3. "与...以太网联接状态"
                match = re.search(r"与(.+?)以太网联接状态", key)
                if match:
                    node_name = match.group(1).strip()

        # 特殊名称修正 (根据用户需求)
        corrections = {
            "GMAC0": "GMACO",
            "ZCUL": "ZCULL",
            "PFE_MAC2": "PFE_EMAC2",
            "PCS/PAPA": "PCS/FAPA"
        }
        return corrections.get(node_name, node_name)

    def _fetch_doip_snapshot(self, log_callback: Optional[Callable[[str], None]] = None) -> TopologySnapshot:
        """通过已建立的 DoIP 连接向 ECU 请求拓扑信息，并转换为 TopologySnapshot。"""
        if self._device_service is None:
            raise TopologyServiceError("未注入 DeviceService，无法通过 DoIP 采集拓扑")
        # 4. 以太网 link 状态（新增）：通过 22 BE1A 获取当前各节点 link up/down 信息
        link_status = self._get_eth_link_status(log_callback=log_callback)
        if log_callback:
            log_callback(f"获取到的 Link Status Keys: {list(link_status.keys())}")

        # 1. 车辆信息
        # vin = self._get_vin(log_callback=log_callback)
        # vehicle_mode = self._get_vehicle_mode(log_callback=log_callback)
        # user_mode = self._get_user_mode(log_callback=log_callback)
        # factory_mode = self._get_factory_mode(log_callback=log_callback)
        # voltage = self._get_voltage(log_callback=log_callback)
        # vehicle_info = {
        #     "vin": vin,
        #     "vehicle_mode": vehicle_mode,
        #     "user_mode": user_mode,
        #     "factory_mode": factory_mode,
        #     "voltage": voltage
        # }
        #
        # # 2. 服务状态 (SomeIP)
        # service_status_raw = self._get_service_status(log_callback=log_callback)
        # service_status = {"status_summary": service_status_raw}
        #
        # # 3. 信息安全
        # cert_info = self._get_cert_info(log_callback=log_callback)
        # key_slot = self._get_key_slot_status(log_callback=log_callback)
        # cms_env = self._get_cms_env(log_callback=log_callback)
        # security_info = {
        #     "cert_info": cert_info,
        #     "key_slot_status": key_slot,
        #     "cms_env": cms_env
        # }
        #
        #
        # # 5. PNC 网络管理 (SomeIP)
        # pnc_mgmt = self._get_pnc_status(log_callback=log_callback)
        # # 将 link 状态合并进 network_management，便于统一在信息块里展示
        # network_mgmt: Dict[str, str] = {}
        # network_mgmt.update(pnc_mgmt)
        # network_mgmt.update(link_status)
        #
        # # 6. 存储/版本信息 (SSH)
        # storage_info_str = self._get_storage_info(log_callback=log_callback)
        # version_info = self._get_version_info(log_callback=log_callback)
        # storage_info = {
        #     "a_core_storage": storage_info_str,
        #     "m_core_storage": version_info,
        # }

        # 拓扑节点构建
        nodes = []
        # 中心节点
        nodes.append(("ETH Switch", "🌐", "online", 0, 0))

        link_items = []
        for key, value in link_status.items():
            # 过滤出包含 "以太网联接状态" 的项
            if "以太网联接状态" in key or "ETH_SWITCH" in key or "PFE_EMAC" in key:
                # 使用专门的规则提取节点名称
                node_name = self._extract_node_name(key)

                # 状态映射: Link up -> 正常 (online), Link Down -> 离线 (offline)
                status = "online" if "Link up" in value else "offline"
                link_items.append((node_name, status))

        # 布局参数: 圆形布局
        count = len(link_items)
        radius = 300
        angle_step = 360 / count if count > 0 else 0

        for i, (name, status) in enumerate(link_items):
            angle_rad = math.radians(i * angle_step)
            x = int(radius * math.cos(angle_rad))
            y = int(radius * math.sin(angle_rad))

            # 图标根据名称简单匹配
            icon = "🔌"
            if "GMACO" in name: icon = "🖥️"
            elif "ZCU" in name: icon = "🧠"
            elif "ADC" in name: icon = "🎛️"
            elif "IDC" in name: icon = "🧠"
            elif "TBOX" in name: icon = "📡"
            elif "Lidar" in name or "雷达" in name: icon = "📡"
            elif "CAM" in name or "IFC" in name: icon = "📷"

            nodes.append((name, icon, status, x, y))

        if log_callback:
            log_callback(f"构建的拓扑节点 ({len(nodes)}个): {nodes}")

        return TopologySnapshot(
            nodes=nodes,
            vehicle_info={},
            service_status={},
            security_info={},
            network_management={},
            storage_info={},
        )

    # --- DoIP Helpers ---
    def _send_uds_read(self, did_high, did_low, log_callback: Optional[Callable[[str], None]] = None) -> Optional[bytes]:
        # 发送 UDS 读取请求 (22 xx xx)，返回数据部分
        #  # [0x22] -> Service ID (SID) 表示 "按标识符读取数据"
        payload = bytes([0x22, did_high, did_low])
        if log_callback: log_callback(f"发送 UDS 读取: {payload.hex(' ').upper()}")
        rx = self._device_service.send_doip_payload(payload, timeout=1.0)
        if rx and len(rx) >= 3 and rx[0] == 0x62 and rx[1] == did_high and rx[2] == did_low:
            if log_callback: log_callback(f"收到 UDS 响应: {rx.hex(' ').upper()}")
            return rx[3:]
        if log_callback: log_callback(f"UDS 读取失败或无响应: {rx.hex(' ').upper() if rx else 'None'}")
        return None

    def _get_eth_link_status(self, log_callback: Optional[Callable[[str], None]] = None) -> Dict[str, str]:
        """读取以太网各节点 link 状态（UDS 22 BE1A）。
        """
        if log_callback: log_callback("-->读取以太网Link状态<--")
        result: Dict[str, str] = {}
        payload = bytes([0x22, 0xBE, 0x1A])
        if log_callback: log_callback(f"发送 UDS 读取: {payload.hex(' ').upper()}")
        try:
            rx = self._device_service.send_doip_payload(payload, timeout=1.0)
        except Exception as e:
            if log_callback: log_callback(f"读取失败: {e}")
            result["eth_link_raw"] = f"读取失败: {e}"
            return result

        if not rx or len(rx) < 3 or rx[0] != 0x62 or rx[1] != 0xBE or rx[2] != 0x1A:
            if log_callback: log_callback(f"无有效响应: {rx.hex(' ').upper() if rx else 'None'}")
            result["eth_link_raw"] = "无有效响应"
            return result

        data = rx[3:]
        if log_callback: log_callback(f"Link状态原始数据: {data.hex(' ').upper()}")

        # 使用 DPTService 解析数据
        if self._dpt_service.is_ready():
            parsed_result = self._dpt_service.parse_bytes(data, did="BE1A")
            if parsed_result:
                if log_callback: log_callback(f"DPT解析结果: {parsed_result.fields}")
                # 将解析结果转换为 dict
                # parsed_result.fields 是一个 list，包含 DPTFieldValue 对象
                # 我们需要遍历这个 list，提取 name 和 parsed_value
                for field in parsed_result.fields:
                    # 假设 DPTFieldValue 有 name 和 parsed_value 属性
                    if hasattr(field, 'name') and hasattr(field, 'parsed_value'):
                        result[field.name] = str(field.parsed_value)
            else:
                if log_callback: log_callback("DPT解析失败: 未找到匹配的解析规则")
        else:
            if log_callback: log_callback("DPT服务未就绪，无法解析数据")

        # 暂不清楚各节点对应 bit/byte 的精确含义，这里先挂原始 hex，方便 UI 或日志查看
        result["eth_link_raw"] = data.hex().upper()
        if log_callback: log_callback(f"Link状态解析结果: {result}")
        return result

    def _get_vin(self, log_callback: Optional[Callable[[str], None]] = None) -> str:
        if log_callback: log_callback("-->读取VIN码<--")
        data = self._send_uds_read(0xF1, 0x90, log_callback)
        if data:
            if log_callback: log_callback(f"VIN原始数据: {data.hex(' ').upper()}")
            try:
                result = data.decode('ascii').strip()
            except:
                result = data.hex()
            if log_callback: log_callback(f"VIN解析结果: {result}")
            return result
        if log_callback: log_callback("VIN读取失败: 无数据")
        return "Unknown"

    def _get_vehicle_mode(self, log_callback: Optional[Callable[[str], None]] = None) -> str:
        if log_callback: log_callback("-->读取车辆模式<--")
        data = self._send_uds_read(0x50, 0x01, log_callback)
        if data:
            if log_callback: log_callback(f"车辆模式原始数据: {data.hex(' ').upper()}")
            mode = data[0] & 0x0F
            modes = {
                0x00: "正常模式", 0x01: "生产模式", 0x02: "运输模式", 0x03: "展厅模式",
                0x04: "碰撞模式", 0x05: "维修模式"
            }
            result = modes.get(mode, f"未知模式({mode})")
            if log_callback: log_callback(f"车辆模式解析结果: {result}")
            return result
        if log_callback: log_callback("车辆模式读取失败: 无数据")
        return "Unknown"

    def _get_factory_mode(self, log_callback: Optional[Callable[[str], None]] = None) -> str:
        if log_callback: log_callback("-->读取工厂模式<--")
        # 假设工厂模式 DID 为 0xBE01 (示例)
        data = self._send_uds_read(0xBE, 0x01, log_callback)
        if data:
            if log_callback: log_callback(f"工厂模式原始数据: {data.hex(' ').upper()}")
            # 假设 01 为工厂模式，00 为用户模式
            return "工厂模式" if data[0] == 0x01 else "用户模式"
        return "未知"

    def _get_voltage(self, log_callback: Optional[Callable[[str], None]] = None) -> str:
        if log_callback: log_callback("-->读取电压<--")
        data = self._send_uds_read(0x10, 0x00, log_callback)
        if data:
            if log_callback: log_callback(f"电压原始数据: {data.hex(' ').upper()}")
            # 假设是 raw hex 或者某种编码，这里直接转 hex 显示
            result = f"{int.from_bytes(data, 'big')} mV" # 假设单位 mV，具体需确认
            if log_callback: log_callback(f"电压解析结果: {result}")
            return result
        if log_callback: log_callback("电压读取失败: 无数据")
        return "Unknown"

    def _get_cert_info(self, log_callback: Optional[Callable[[str], None]] = None) -> str:
        if log_callback: log_callback("-->读取证书信息<--")
        # 31 01 BE E8 (Routine Control)
        # 需要 Security Access，这里尝试直接发送，如果失败则返回提示
        payload = bytes([0x31, 0x01, 0xBE, 0xE8])

        routine = bytes.fromhex("31 01 BE E9")
        self._device_service.execute_secure_routine(routine, sec_level=0x21)

        # rx = self._device_service.send_doip_payload(payload, timeout=2.0)
        # if rx and rx[0] == 0x71:
        #     if log_callback: log_callback(f"收到 UDS 响应: {rx.hex(' ').upper()}")
        #     result = "读取成功: " + rx[4:].hex() # 假设格式
        #     if log_callback: log_callback(f"证书信息解析结果: {result}")
        #     return result
        # if log_callback: log_callback(f"UDS 例程失败或无响应: {rx.hex(' ').upper() if rx else 'None'}")
        return "读取失败(可能需要解锁)"

    def _get_key_slot_status(self, log_callback: Optional[Callable[[str], None]] = None) -> str:
        if log_callback: log_callback("-->读取密钥槽状态<--")
        data = self._send_uds_read(0xBE, 0x2C, log_callback)
        if data:
            if log_callback: log_callback(f"密钥槽状态原始数据: {data.hex(' ').upper()}")
            result = data.hex()
            if log_callback: log_callback(f"密钥槽状态解析结果: {result}")
            return result
        if log_callback: log_callback("密钥槽状态读取失败: 无数据")
        return "Unknown"

    def _get_cms_env(self, log_callback: Optional[Callable[[str], None]] = None) -> str:
        if log_callback: log_callback("-->读取CMS环境<--")
        data = self._send_uds_read(0xBE, 0x2D, log_callback)
        if data:
            if log_callback: log_callback(f"CMS环境原始数据: {data.hex(' ').upper()}")
            result = data.hex()
            if log_callback: log_callback(f"CMS环境解析结果: {result}")
            return result
        if log_callback: log_callback("CMS环境读取失败: 无数据")
        return "Unknown"

    # --- SomeIP Helpers ---
    def _someip_request_sync(self, service: int, method: int, payload: bytes = b'', timeout: float = 2.0, target_port: int = 30500) -> Optional[bytes]:
        client = self._device_service.get_someip_client()
        if not client:
            return None

        # 1. 获取目标IP
        target_ip = self._device_service.get_current_device_ip()
        if not target_ip:
            # 未知IP时尝试使用默认值
            target_ip = "10.1.0.79"

        # 记录详细的发送参数
        if hasattr(self, '_log_callback') and self._log_callback:
            self._log_callback(f"[Debug] Sending SOME/IP to {target_ip}:{target_port}")

        result = None
        event = threading.Event()

        # 2. 定义回调
        def cb(pkt):
            nonlocal result
            try:
                # 尝试提取 load
                if hasattr(pkt, 'payload') and hasattr(pkt.payload, 'load'):
                     result = pkt.payload.load
                else:
                     # 兜底转换
                     result = bytes(pkt.payload)
            except:
                result = b''
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
            # 发送请求
            client.send_request(service, method, payload, target_ip=target_ip, target_port=target_port)
            event.wait(timeout)
        finally:
            # 清理回调
            client.unregister_callback(service, method)

        return result

    def _get_user_mode(self, log_callback: Optional[Callable[[str], None]] = None) -> str:
        # 保存 callback 引用，以便 _someip_request_sync 可以使用它来打印调试信息
        self._log_callback = log_callback

        if log_callback: log_callback("-->读取用户模式<--")
        try:
            client = self._device_service.get_someip_client()
        except Exception:
            client = None
        if not client:
            if log_callback: log_callback("SomeIP Client 未就绪或未注入")
            return "SomeIP Client未就绪"


    def _get_service_status(self, log_callback: Optional[Callable[[str], None]] = None) -> str:
        # 10FA, 0003
        try:
            client = self._device_service.get_someip_client()
        except Exception:
            client = None
        if not client:
            if log_callback: log_callback("SomeIP Client 未就绪或未注入")
            return "SomeIP Client未就绪"
        client.request_with_discovery(service_id=0x10FA, method_id=0x0003, target_ip="172.16.64.79")
        return "获取中..." # 需完善 SomeIP 通信机制

    def _get_pnc_status(self, log_callback: Optional[Callable[[str], None]] = None) -> Dict[str, str]:
        # 多个 Notifier，需要 Subscribe
        return {
            "power_wake_source": "Unknown",
            "pnc": "Unknown",
            "rt1_net": "Unknown"
        }

    # --- SSH Helpers ---
    def _get_storage_info(self, log_callback: Optional[Callable[[str], None]] = None) -> str:
        cmd = "df -h"
        if log_callback: log_callback(f"发送 SSH 指令: {cmd}")

        try:
            res = self._device_service.get_ssh_client().execute_command(cmd)
            out = res
            if isinstance(res, tuple):
                 out = res[0]

        except Exception as e:
            return f"Error: {e}"

        if out:
            # 筛选以 /dev 开头的行
            lines = [line for line in out.strip().splitlines() if line.strip().startswith('/dev')]
            result = "\n".join(lines)
            if log_callback: log_callback(f"SSH 指令成功: \n{result}")
            return result

        if log_callback: log_callback(f"SSH 指令失败 or Empty")
        return "Error: Empty response"

    def _get_version_info(self, log_callback: Optional[Callable[[str], None]] = None) -> str:
        cmd = "get_ccu_all_version"
        if log_callback: log_callback(f"发送 SSH 指令: {cmd}")
        out = self._device_service.get_ssh_client().execute_command(cmd)
        return out.strip()

    # --- Network Diagnosis Helpers (Moved from Controller) ---

    def execute_capture_routine(self, command: bytes, log_callback: Optional[Callable[[str], None]] = None) -> bool:
        """执行抓包相关的 UDS 例程"""
        if self._device_service is None:
            if log_callback:
                log_callback("DeviceService 未注入，无法执行抓包指令")
            return False

        # 定义内部日志函数，如果未提供 callback 则忽略
        def _log(msg: str):
            if log_callback:
                log_callback(msg)

        return self._device_service.execute_secure_routine(command, sec_level=0x01, log_callback=_log)

    def capture_ccu_eth(self, log_callback: Optional[Callable[[str], None]] = None) -> bool:
        """CCU ETH数据抓包"""
        cmd = bytes.fromhex("31 01 BE E7 3E")
        return self.execute_capture_routine(cmd, log_callback)

    def capture_node_eth(self, log_callback: Optional[Callable[[str], None]] = None) -> bool:
        """节点 ETH数据抓包"""
        cmd = bytes.fromhex("31 01 BE E7 03")
        return self.execute_capture_routine(cmd, log_callback)

    def capture_vehicle_eth(self, log_callback: Optional[Callable[[str], None]] = None) -> bool:
        """整车 ETH数据抓包"""
        cmd = bytes.fromhex("31 01 BE E7 FF")
        return self.execute_capture_routine(cmd, log_callback)

    def get_tx_rx_count(self, log_callback: Optional[Callable[[str], None]] = None) -> Tuple[bool, str]:
        """获取 TX/RX 计数"""
        if self._device_service is None:
            if log_callback: log_callback("服务不可用: DeviceService 未注入")
            return False, "服务不可用"

        ssh_client = self._device_service.get_ssh_client()
        if not ssh_client or not ssh_client.is_connected():
            if log_callback: log_callback("SSH未连接")
            return False, "SSH未连接"

        cmd = "Use -mib -all"
        if log_callback: log_callback(f"发送 SSH 指令: {cmd}")
        out = ssh_client.execute_command(cmd)

        if log_callback:
            if out:
                log_callback(f"收到 SSH 响应: {out.strip()}")
            else:
                log_callback("SSH 指令执行无响应或失败")

        # execute_command 返回 stdout (str) 或 None
        if out is not None:
            return True, out.strip().splitlines()[0] if out else "OK"
        else:
            return False, "执行失败"

    def ping_ip(self, ip: str, log_callback: Optional[Callable[[str], None]] = None) -> bool:
        """Ping 指定 IP"""
        if self._device_service is None:
            if log_callback: log_callback("服务不可用: DeviceService 未注入")
            return False

        ssh_client = self._device_service.get_ssh_client()
        if not ssh_client or not ssh_client.is_connected():
            if log_callback: log_callback("SSH未连接")
            return False

        cmd = f"ping -c 10 -i 0.1 {ip}"
        if log_callback: log_callback(f"发送 SSH 指令: {cmd}")

        out = ssh_client.execute_command(cmd)

        if log_callback:
            if out:
                log_callback(f"收到 SSH 响应: {out.strip()}")
            else:
                log_callback("SSH 指令执行无响应或失败")

        if not out:
            return False

        # 解析 ping 结果
        if "100% packet loss" in out or "0 packets received" in out:
            if log_callback: log_callback(f"Ping {ip} 结果: 不通 (丢包)")
            return False

        if "packets received" in out:
             if log_callback: log_callback(f"Ping {ip} 结果: 通")
             return True

        return False

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
            vehicle_info=vehicle_info,
            service_status=service_status,
            security_info=security_info,
            network_management=network_mgmt,
            storage_info=storage_info,
        )

    def fetch_can_lin_snapshot(self, log_callback: Optional[Callable[[str], None]] = None) -> List[Tuple[str, str, str, int, int]]:
        """
        采集 CAN/LIN 拓扑信息
        总线状态获取方法：读取当前故障DTC，19022f，判断返回的DTC中是否有busoff的DTC。
        """
        if self._device_service is None:
             # 回退到 dummy 数据
             if log_callback: log_callback("未连接设备，使用模拟数据")
             return self._build_dummy_can_lin_snapshot()

        client = self._device_service.get_doip_client()
        if not client or not client.is_connected:
            if log_callback: log_callback("DoIP 未连接，使用模拟数据")
            return self._build_dummy_can_lin_snapshot()

        # 1. 故障读取 (DTC 0x19 02 2F)
        req = bytes.fromhex("19 02 2F")
        if log_callback: log_callback(f"发送 DTC 读取指令: {req.hex(' ').upper()}")
        rx = client.send_doip_message(req, timeout=5.0)

        dtc_list = []
        if rx and rx[0] == 0x59:
             # 解析 DTC
             # 格式: 59 02 2F [StatusAvailabilityMask] [DTC1] [Status1] [DTC2] [Status2] ...
             # DTC 是 3 字节，Status 是 1 字节
             if len(rx) > 4:
                 data = rx[4:]
                 count = len(data) // 4
                 for i in range(count):
                     dtc_bytes = data[i*4 : i*4+3]
                     dtc_hex = dtc_bytes.hex().upper()
                     dtc_list.append(dtc_hex)
             if log_callback: log_callback(f"读取到的 DTC 列表: {dtc_list}")
        else:
             if log_callback: log_callback(f"DTC 读取失败或无响应: {rx.hex(' ').upper() if rx else 'None'}")

        # 2. 映射关系
        # DTC - 节点名称映射
        # 存在DTC的通道，显示为红色(offline)，不存在DTC的通道，显示为绿色(online)
        dtc_map = {
            "C07388": "CCU_CANFD5", # CAN00
            "D8D088": "CCU_CANFD11", # CAN01
            "D8D188": "Rollback1", # CAN02
            "D8D288": "CCU_CANFD2", # CAN03
            "D8D388": "CCU_CANFD4", # CAN04
            "D8D488": "CCU_CANFD13", # CAN05
            "D8D588": "CCU_CANFD3", # CAN06
            "D8D688": "OBD_CAN", # CAN07
            "D8D788": "CCU_CANFD12", # CAN08
            "D8D888": "CCU_CANFD7", # CAN09
            "D8D988": "CCU_CANFD8", # CAN10
            "D8DA88": "CCU_CANFD9", # CAN11
            "D8DB88": "CCU_CANFD10", # CAN12
            "D8DC88": "CCU_CANFD1", # CAN13
            "D8DD88": "Rollback2", # CAN14
            "D8DE88": "CCU_CANFD6", # CAN15
            "9F0088": "LIN1",
            "9F0188": "LIN2"
        }
        dtc_list = ['05162F', '06162F', '098728', '0A8728', '0B8728', '0C8768', '0E8728', '0F8728', '108728', '128728', '138728', '148728', '158728', '168728', '1C8728', '1D8728', '1E8728', '058728', '068728', '078728', '088728', '098728', '248728', '258728', '268728', '2B622F', '0A622F', '0D622F', '3F772E', '8B8820', '45292F', '18292F', '19292F', '230A28', '540928', 'B68728', '7B7728', '988728', '29872C', '12872C', '20872C', '30872C', '40872C', '508728', '9F0188', 'C07388']
        if log_callback: log_callback(f"因设备未读有故障码，模拟的 DTC 列表: {dtc_list}")
        # 默认所有节点在线
        node_status = {name: "online" for name in dtc_map.values()}

        # 根据 DTC 更新状态
        for dtc in dtc_list:
            if dtc in dtc_map:
                node_name = dtc_map[dtc]
                node_status[node_name] = "offline"
                if log_callback: log_callback(f"发现故障 DTC {dtc}，节点 {node_name} 标记为离线")

        # 3. 构建节点数据
        # 格式: (name, icon, status, x, y)
        nodes = []
        # 中心节点
        nodes.append(("LLCE", "", "online", 0, 0))

        # 子节点
        # 使用圆周布局或其他布局，这里暂时由 TopologyWidget 自动布局
        # 此处只提供数据列表

        # 按照用户提供的列表顺序或者逻辑顺序添加
        ordered_nodes = [
             "CCU_CANFD1", "CCU_CANFD2", "CCU_CANFD3", "CCU_CANFD4", "CCU_CANFD5", "CCU_CANFD6",
             "CCU_CANFD7", "CCU_CANFD8", "CCU_CANFD9", "CCU_CANFD10", "CCU_CANFD11", "CCU_CANFD12", "CCU_CANFD13",
             "Rollback1", "Rollback2", "OBD_CAN", "LIN1", "LIN2"
        ]

        for name in ordered_nodes:
            status = node_status.get(name, "online")
            nodes.append((name, "", status, 0, 0))

        return nodes

    def _build_dummy_can_lin_snapshot(self) -> List[Tuple[str, str, str, int, int]]:
        """模拟 CAN/LIN 拓扑数据"""
        nodes = [("LLCE", "", "online", 0, 0)]
        for i in range(1, 14):
            nodes.append((f"CANFD{i}", "", "online", 0, 0))
        nodes.append(("LIN1", "", "online", 0, 0))
        nodes.append(("LIN2", "", "online", 0, 0))
        return nodes

