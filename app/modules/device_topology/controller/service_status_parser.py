import struct
import json
import collections
from datetime import datetime
from enum import IntEnum
from typing import List, Dict, Any, Optional, Union
import binascii

# ==========================================
# 1. 枚举与基础类型定义
# ==========================================

class BasicCommunicationPhase(IntEnum):
    """通信阶段枚举"""
    UNKNOWN = 0
    READY = 1
    NOT_READY = 2
    # 根据实际情况补充
    STARTUP = 3
    SHUTDOWN = 4

class TransportProtocol(IntEnum):
    """传输协议枚举"""
    UDP = 0
    TCP = 1
    # 根据实际情况补充

class SubscriptionState(IntEnum):
    """订阅状态枚举"""
    NOT_SUBSCRIBED = 0
    SUBSCRIBED = 1
    SUBSCRIPTION_PENDING = 2
    # 根据实际情况补充

# ==========================================
# 2. 核心解析器框架
# ==========================================

class SomeIpParser:
    def __init__(self, strict_mode: bool = False):
        self.strict_mode = strict_mode
        self.parsed_data = {}
        self.offset = 0
        self.binary_data = b""

    def parse_data(self, data_type: str, binary_data: bytes) -> object:
        """
        通用反序列化接口
        :param data_type: 数据类型名称 ('ApServiceStateVectorType', 'ApEventGroupStateVectorType', etc.)
        :param binary_data: 原始字节数据
        :return: 解析后的对象
        """
        self.binary_data = binary_data
        self.offset = 0
        self.parsed_data = {}

        try:
            if data_type == 'ApServiceStateVectorType':
                return self._parse_ap_service_state_vector()
            else:
                raise ValueError(f"Unknown data type: {data_type}")
        except Exception as e:
            if self.strict_mode:
                raise
            return {"error": f"Parsing failed: {str(e)}", "partial_data": self.parsed_data}

    def parse_hex_string(self, hex_string: str) -> Dict[str, Any]:
        """解析十六进制字符串 (默认只解析 ApServiceStateVectorType，为了兼容旧代码)"""
        # 移除空白字符
        clean_hex = "".join(hex_string.split())
        try:
            data = binascii.unhexlify(clean_hex)
            return self.parse_data('ApServiceStateVectorType', data)
        except binascii.Error as e:
            return {"error": f"Invalid hex string: {str(e)}"}

    def parse_bytes(self, data: bytes) -> Dict[str, Any]:
        """解析字节数据 (默认只解析 ApServiceStateVectorType)"""
        return self.parse_data('ApServiceStateVectorType', data)

    # --- 基础类型解析辅助方法 ---

    def _read_uint8(self) -> int:
        if not self._check_remaining(1):
             raise ValueError(f"Insufficient data for uint8 at offset {self.offset}")
        value = struct.unpack_from(">B", self.binary_data, self.offset)[0]
        self.offset += 1
        return value

    def _read_uint16(self) -> int:
        if not self._check_remaining(2):
             raise ValueError(f"Insufficient data for uint16 at offset {self.offset}")
        value = struct.unpack_from(">H", self.binary_data, self.offset)[0]
        self.offset += 2
        return value

    def _read_uint32(self) -> int:
        if not self._check_remaining(4):
             raise ValueError(f"Insufficient data for uint32 at offset {self.offset}")
        value = struct.unpack_from(">I", self.binary_data, self.offset)[0]
        self.offset += 4
        return value

    def _read_uint64(self) -> int:
        if not self._check_remaining(8):
             raise ValueError(f"Insufficient data for uint64 at offset {self.offset}")
        value = struct.unpack_from(">Q", self.binary_data, self.offset)[0]
        self.offset += 8
        return value

    def _read_boolean(self) -> bool:
        return bool(self._read_uint8())

    def _check_remaining(self, size: int) -> bool:
        return (self.offset + size) <= len(self.binary_data)

    def _ip_to_str(self, ip_int: int) -> str:
        """将uint32 IP转换为字符串格式 (Little-endian)"""
        return f"{ip_int & 0xFF}.{(ip_int >> 8) & 0xFF}.{(ip_int >> 16) & 0xFF}.{(ip_int >> 24) & 0xFF}"

    def _format_timestamp(self, timestamp_ms: int) -> str:
        """将毫秒时间戳转换为格式化时间字符串"""
        if timestamp_ms == 0:
            return "0"
        try:
            dt = datetime.fromtimestamp(timestamp_ms / 1000.0)
            return dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        except (ValueError, OSError):
            return str(timestamp_ms)

    def _map_enum(self, enum_cls, value):
        """尝试将整数映射为枚举，失败则返回整数"""
        try:
            return enum_cls(value).name
        except ValueError:
            return f"UNKNOWN_{value}"

    # --- 复合结构体解析方法 ---

    def _parse_ap_service_state_vector(self) -> Dict[str, Any]:
        """ApServiceStateVectorType - 服务状态容器"""
        # 前置 uint32 长度字段
        vector_length = self._read_uint32()
        start_offset = self.offset
        end_offset = start_offset + vector_length
        services = []

        # 循环解析直到达到长度限制
        while self.offset < end_offset:
            # 检查是否有前置长度字段 (User specified dynamic array elements might have length prefix)
            # 在 XX.txt 的分析中，我们发现每项都有一个 uint32 长度前缀
            if not self._check_remaining(4):
                break

            # 读取当前元素长度
            item_length = self._read_uint32()
            item_end_offset = self.offset + item_length

            # 确保数据足够
            if not self._check_remaining(item_length):
                 if self.strict_mode: raise ValueError(f"Insufficient data for service item at {self.offset}")
                 break

            service_info = self._parse_service_state_info()
            services.append(service_info)

            # 强制对齐到声明的长度（如果有偏差）
            if self.offset != item_end_offset:
                self.offset = item_end_offset

        result = {
            "type": "ApServiceStateVectorType",
            "length_bytes": vector_length,
            "count": len(services),
            "services": services
        }
        self.parsed_data = result
        return result

    def _parse_service_state_info(self) -> Dict[str, Any]:
        """service_state_info_t - 服务状态信息"""

        # 记录起始位置以便计算已读取字节数（如果有必要调试）
        # start_pos = self.offset

        # 结构体字段按顺序解析
        state_time = self._read_uint64()
        service_ip = self._read_uint32()
        ttl = self._read_uint32()
        cycle_time = self._read_uint32()

        service_id = self._read_uint16()
        instance_id = self._read_uint16()
        minor_version = self._read_uint32()
        major_version = self._read_uint8()

        phase_val = self._read_uint8()
        reliable_flag = self._read_boolean()
        unreliable_flag = self._read_boolean()

        tcp_port = self._read_uint16()
        udp_port = self._read_uint16()

        # eventgroup_ids (Vector)
        eventgroup_ids = self._parse_eventgroup_ids_vector()

        return {
            "state_time": self._format_timestamp(state_time),
            "service_ip": self._ip_to_str(service_ip),
            "ttl": ttl,
            "cycle_time": cycle_time,
            "service_id": f"0x{service_id:04X}",
            "instance_id": instance_id,
            "minor_version": minor_version,
            "major_version": major_version,
            "phase": self._map_enum(BasicCommunicationPhase, phase_val),
            "reliable_flag": reliable_flag,
            "unreliable_flag": unreliable_flag,
            "tcp_port": tcp_port,
            "udp_port": udp_port,
            "eventgroup_ids": eventgroup_ids
        }


    # -----------------------------------------------------
    # 向量与子结构解析
    # -----------------------------------------------------

    def _parse_eventgroup_ids_vector(self) -> List[int]:
        """eventgroup_ids_Ref (Vector of uint16)"""
        if not self._check_remaining(4):
            return []
        length = self._read_uint32()
        count = length // 2
        ids = []
        for _ in range(count):
            ids.append(self._read_uint16())
        return ids

    def _parse_subscribers_vector(self) -> List[Dict[str, Any]]:
        """subscriber_t_Ref"""
        if not self._check_remaining(4): return []
        length = self._read_uint32()
        end = self.offset + length
        items = []
        while self.offset < end:
            items.append(self._parse_subscriber())
        return items

    def _parse_subscriber(self) -> Dict[str, Any]:
        """subscriber_t"""
        # assuming fixed size if no dynamic content, BUT user doc doesn't say "dynamic struct"
        # However, parent usually handles vector boundaries.
        # Struct: time(8)+ip(4)+udp(2)+tcp(2)+is_client(1)+state(1) = 18 bytes
        return {
            "time": self._read_uint64(),
            "ip": self._ip_to_str(self._read_uint32()),
            "udp_port": self._read_uint16(),
            "tcp_port": self._read_uint16(),
            "is_client": self._read_boolean(),
            "subscription_state": self._map_enum(SubscriptionState, self._read_uint8())
        }

    def _parse_local_subscribers_vector(self) -> List[Dict[str, Any]]:
        """local_subscriber_t_Ref"""
        if not self._check_remaining(4): return []
        length = self._read_uint32()
        end = self.offset + length
        items = []
        while self.offset < end:
            items.append(self._parse_local_subscriber())
        return items

    def _parse_local_subscriber(self) -> Dict[str, Any]:
        """local_subscriber_t"""
        # Struct: time(8)+client_id(2)+state(1) = 11 bytes
        return {
             "time": self._read_uint64(),
             "client_id": self._read_uint16(),
             "subscription_state": self._map_enum(SubscriptionState, self._read_uint8())
        }

    def _parse_events_vector(self) -> List[int]:
        """events_Ref (Vector of uint16)"""
        # Same structure as eventgroup_ids_Ref
        if not self._check_remaining(4): return []
        length = self._read_uint32()
        count = length // 2
        ids = []
        for _ in range(count):
            ids.append(self._read_uint16())
        return ids

# ==========================================
# 3. 输出与导出功能 (Demo Interface)
# ==========================================

class SomeIpAnalyzer:
    @staticmethod
    def generate_report(parsed_obj: Dict[str, Any]) -> str:
        """生成简要统计报告"""
        if "services" in parsed_obj:
            count = parsed_obj.get("count", 0)
            services = parsed_obj.get("services", [])
            # 统计 IP 分布
            ip_counter = collections.Counter(s['service_ip'] for s in services if 'service_ip' in s)

            report = []
            report.append(f"Analysis Report for ApServiceStateVectorType:")
            report.append(f"Total Entries: {count}")
            report.append(f"Unique IPs: {len(ip_counter)}")
            report.append("Top 5 IPs:")
            for ip, cnt in ip_counter.most_common(5):
                report.append(f"  - {ip}: {cnt} services")
            return "\n".join(report)

        elif "event_groups" in parsed_obj:
             count = parsed_obj.get("count", 0)
             return f"Analysis Report for ApEventGroupStateVectorType:\nTotal Event Groups: {count}"

        return "Unknown Data Structure"

if __name__ == "__main__":
    import os

    # 简单的测试入口
    test_file = r"D:\uidq9000\PycharmProjects\oneboxforgac\XX.txt"
    if os.path.exists(test_file):
        with open(test_file, 'r') as f:
            hex_data = f.read().strip()

        parser = SomeIpParser()
        print(f"Parsing file: {test_file} ...")

        # 假设文件内容是 ApServiceStateVectorType (根据前文分析)
        result = parser.parse_hex_string(hex_data)

        if "error" in result:
            print("Error:", result["error"])
        else:
            print("Successfully parsed.")
            print(SomeIpAnalyzer.generate_report(result))

            # 打印前2个条目作为示例
            print("\nSample Data (First 2 entries):")
            print(json.dumps(result.get("services", [])[:2], indent=2, default=str))
            # 打印所有
            print("\nAll Data:")
            print(json.dumps(result, indent=2, default=str))

    else:
        print(f"File not found: {test_file}")
