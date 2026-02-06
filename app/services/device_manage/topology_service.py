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

    # --- Data Parsing Helper ---
    def _parse_data(self, data: bytes, did: str) -> str:
        """解析数据，如果DPT可用则使用DPT，否则返回HEX字符串"""
        if not data:
            return "No Data"

        # 尝试使用 DPT 解析
        if self._dpt_service.is_ready():
            try:
                parsed_result = self._dpt_service.parse_bytes(data, did=did)
                if parsed_result and parsed_result.fields:
                    # 将解析出的字段拼接成字符串
                    # 例如: "Status: 0x01 (Active), Count: 5"
                    parts = []
                    for field in parsed_result.fields:
                         if hasattr(field, 'name') and hasattr(field, 'parsed_value'):
                             parts.append(f"{field.name}: {field.parsed_value}")
                    if parts:
                        return ", ".join(parts)
            except Exception as e:
                # 解析出错，记录但不崩溃，回退到 HEX
                pass

        # 默认回退：转 HEX 字符串
        return data.hex(' ').upper()

    def _get_cert_info(self, log_callback: Optional[Callable[[str], None]] = None) -> str:
        if log_callback: log_callback("-->读取证书信息<--")

        # 1. 安全访问解锁 (Level 0x21/0x22)
        # DeviceService.execute_secure_routine 内部实现了 27 21 -> 27 22 的逻辑
        # 这里需要先执行一次安全解锁，可以是任意需要解锁的操作，或者直接调解锁接口
        # 但 execute_secure_routine 是设计为"执行一个需要安全的routine"

        # 目标 Routine: 31 01 BE E8 (或者 B1 D1)
        # 我们先尝试 BE E8
        routine_id = bytes([0xBE, 0xE8])
        routine_control_type = 0x01 # Start Routine

        try:
            # execute_secure_routine(routine_payload, sec_level)
            # routine_payload 应该是完整的 RoutineControl 数据除 SID 之外的部分?
            # 查看 DeviceService 定义，通常 payload 是 '01 FF FF ...' (Control Type + ID + Option)
            # execute_secure_routine 会先做 27，然后发送 31 + payload

            # 构造 payload: Control Type (1) + Routine ID (2) + OptionRecord (0)
            payload = bytes([routine_control_type]) + routine_id

            if log_callback: log_callback(f"尝试执行安全例程: 31 {payload.hex(' ').upper()} (Level 21)")

            # 调用 DeviceService 的安全例程执行方法
            # 注意：execute_secure_routine 返回的是 Response 完整数据 (71 ...)
            rx = self._device_service.execute_secure_routine(payload, sec_level=0x21)

            # 如果 BE E8 失败 (例如不支持)，尝试 B1 D1
            if not rx or rx[0] == 0x7F: # 负响应
                if log_callback: log_callback("Routine BEE8 失败，尝试 B1D1")
                routine_id_alt = bytes([0xB1, 0xD1])
                payload_alt = bytes([routine_control_type]) + routine_id_alt
                rx = self._device_service.execute_secure_routine(payload_alt, sec_level=0x21)

            if rx and rx[0] == 0x71: # 正响应 71 01 BE E8 ...
                if log_callback: log_callback(f"Routine 执行成功: {rx.hex(' ').upper()}")
                # 解析数据：去掉头部 (71 01 DID_H DID_L) 共4字节
                if len(rx) > 4:
                    raw_data = rx[4:]
                    # 尝试解析，假设 DID 为 Routine ID 对应的标识
                    # 这里传 hex string 形式的 ID 供 parse 查找
                    did_str = routine_id.hex().upper()
                    return self._parse_data(raw_data, did=did_str)
                return "无返回数据"

            error_msg = f"执行失败: {rx.hex(' ').upper() if rx else 'None'}"
            if log_callback: log_callback(error_msg)
            return error_msg

        except Exception as e:
             if log_callback: log_callback(f"证书信息读取异常: {e}")
             return f"异常: {e}"

    def _get_key_slot_status(self, log_callback: Optional[Callable[[str], None]] = None) -> str:
        if log_callback: log_callback("-->读取密钥槽状态 (DID: BE2C)<--")
        # 22 BE 2C
        data = self._send_uds_read(0xBE, 0x2C, log_callback)
        if data is not None:
             return self._parse_data(data, did="BE2C")
        return "读取失败"

    def _get_cms_env(self, log_callback: Optional[Callable[[str], None]] = None) -> str:
        if log_callback: log_callback("-->读取CMS环境 (DID: BE2D/BE37)<--")
        # 尝试 22 BE 2D
        data = self._send_uds_read(0xBE, 0x2D, log_callback)
        did_used = "BE2D"

        if data is None:
            if log_callback: log_callback("BE2D 读取失败，尝试 BE37")
            # 尝试 22 BE 37
            data = self._send_uds_read(0xBE, 0x37, log_callback)
            did_used = "BE37"

        if data is not None:
            return self._parse_data(data, did=did_used)
        return "读取失败"

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
        # 使用圆周布局或其他布局，
