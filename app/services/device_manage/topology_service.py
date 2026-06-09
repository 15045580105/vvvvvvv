from __future__ import annotations

import math # Added math import
import json
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional, Any, Callable, Union, Literal
import re
import logging
from PyQt5.QtCore import QObject, pyqtSignal, QMutex
from app.modules.device_topology.controller.service_status_parser import SomeIpParser
from app.core.dependency_injection import di_container
from app.services.device_manage.device_service import DeviceService
from app.services.diagnostic.dpt_service import DPTService
from app.common.utils.worker import Worker

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


logger = logging.getLogger(__name__)


class TopologyService(QObject):
    """负责通过 DoIP/SSH 等方式采集拓扑信息的服务。

    当前支持两种模式：
      * use_dummy=True: 返回本地模拟数据（UI 开发和联调阶段使用）；
      * use_dummy=False: 通过注入的 DeviceService 使用 DoIPClient 向 ECU 请求真实拓扑数据。
    """

    # 定义信号
    sig_topology_updated = pyqtSignal(object) # 携带 TopologySnapshot
    sig_can_lin_topology_updated = pyqtSignal(list) # 携带 List[Tuple]

    # 1. 车辆信息
    sig_vin_updated = pyqtSignal(str)
    sig_vehicle_mode_updated = pyqtSignal(str)
    sig_user_mode_updated = pyqtSignal(str)
    sig_factory_mode_updated = pyqtSignal(str)
    sig_voltage_updated = pyqtSignal(str)

    # 2. 证书信息
    sig_cert_infos_updated = pyqtSignal(str)
    sig_key_slot_status_updated = pyqtSignal(str)
    sig_cms_env_updated = pyqtSignal(str)

    # 3. 存储/版本/服务
    sig_storage_updated = pyqtSignal(str)
    sig_version_updated = pyqtSignal(str)
    sig_service_summary_updated = pyqtSignal(str)

    # 4. 网络管理 (保持分组更新，或者拆分)
    # 暂时拆分以便 granular update，虽然目前是一个函数返回
    sig_power_wake_updated = pyqtSignal(str)
    sig_pnc_updated = pyqtSignal(str)
    sig_rt1_net_updated = pyqtSignal(str)

    sig_switch_fault_updated = pyqtSignal(str) # Switch DTC结果
    sig_pfe_fault_updated = pyqtSignal(str) # PFE DTC结果
    sig_tx_rx_updated = pyqtSignal(tuple) # (success, result_str)
    sig_capture_finished = pyqtSignal(bool, str) # (success, msg)
    sig_ping_result = pyqtSignal(str, tuple) # (key, (ok0, ok4))
    log_signal = pyqtSignal(str) # 用于透传日志到界面
    sig_error = pyqtSignal(str) # 用于报告错误

    def __init__(self, device_service: Optional[DeviceService] = None) -> None:
        super().__init__()
        self._device_service = device_service
        self._dpt_service = di_container.resolve(DPTService) or DPTService()
        self._workers = [] # 管理内部 Worker
        self._mutex = QMutex() # 互斥锁，保护 DoIP/UDS 访问
        self._dpt_ready = False
        self._width = 600
        self._height = 500


    def request_vehicle_info(self):
        """异步请求车辆信息"""
        doip_tasks = [
            ("vin", self._get_vin, self.sig_vin_updated),
            ("vehicle_mode", self._get_vehicle_mode, self.sig_vehicle_mode_updated),
            ("factory_mode", self._get_factory_mode, self.sig_factory_mode_updated),
            ("voltage", self._get_voltage, self.sig_voltage_updated)
        ]
        self._execute_parallel_tasks(doip_tasks)

        # 单独执行 SOME/IP 任务，不竞争 DoIP 锁
        self.sig_user_mode_updated.emit("请求中...")
        def someip_task():
            try:
                # SOME/IP 通信通常独立于 DoIP，不需要 self._mutex?
                # 假设 _get_user_mode 自己处理线程安全或不需要锁
                val = self._get_user_mode()
                self.sig_user_mode_updated.emit(val)
            except Exception as e:
                self.sig_user_mode_updated.emit(f"请求失败: {e}")

        self._start_worker(someip_task, self.sig_user_mode_updated) # Pass signal but task returns None, so it won't implicit emit

    def request_service_status(self):
        """异步请求服务状态"""
        # 目前 _get_service_status 返回 dict string，这里简化为只返回 summary string
        tasks = [
            ("status_summary", self._get_service_status_str, self.sig_service_summary_updated)
        ]
        self._execute_parallel_tasks(tasks)

    def request_security_info(self):
        """异步请求证书信息（独立线程并发获取，互不影响）"""

        # 1. 获取证书信息
        self.sig_cert_infos_updated.emit("请求中...")
        def task_cert():
            self._mutex.lock()
            try:
                val = self._get_cert_info()
            except Exception as e:
                val = f"请求异常: {e}"
            finally:
                self._mutex.unlock()
            self.sig_cert_infos_updated.emit(val)
        self._start_worker(task_cert, None)

        # 2. 获取密钥槽状态
        self.sig_key_slot_status_updated.emit("请求中...")
        def task_key():
            self._mutex.lock()
            try:
                val = self._get_key_slot_status()
            except Exception as e:
                val = f"请求异常: {e}"
            finally:
                self._mutex.unlock()
            self.sig_key_slot_status_updated.emit(val)
        self._start_worker(task_key, None)

        # 3. 获取CMS环境
        self.sig_cms_env_updated.emit("请求中...")
        def task_cms():
            self._mutex.lock()
            try:
                val = self._get_cms_env()
            except Exception as e:
                val = f"请求异常: {e}"
            finally:
                self._mutex.unlock()
            self.sig_cms_env_updated.emit(val)
        self._start_worker(task_cms, None)

    def request_network_mgmt(self):
        """异步请求网络管理信息"""
        pass

    def request_storage_info(self):
        """异步请求存储信息"""
        tasks = [
            ("a_core_storage", self._get_storage_info, self.sig_storage_updated)
        ]
        self._execute_parallel_tasks(tasks)

    def request_version_info(self):
        """异步请求版本信息"""
        tasks = [
            ("version", self._get_version_info, self.sig_version_updated)
        ]
        self._execute_parallel_tasks(tasks)

    def _execute_parallel_tasks(self, tasks: List[Tuple[str, Callable, pyqtSignal]]):
        """通用并行任务执行器"""
        # 先通知 UI 所有项都在 "请求中..."
        for key, func, signal in tasks:
            signal.emit("请求中...")

        # 定义单个任务的 Worker 函数
        def single_task_runner(key: str, func: Callable, signal: pyqtSignal):
            try:
                self._mutex.lock()
                try:
                    val = func()
                finally:
                    self._mutex.unlock()

                signal.emit(val)

            except Exception as e:
                msg = f"请求失败: {e}"
                signal.emit(msg)

        # 启动 Workers
        for key, func, signal in tasks:
            def worker_func(k=key, f=func, s=signal):
                single_task_runner(k, f, s)

            self._start_worker(worker_func, pyqtSignal())

    def _hex_to_bytes(self, raw_hex: str) -> Optional[bytes]:
        """安全地将 HEX 字符串转换为 bytes。"""
        if not raw_hex:
            return None
        try:
            normalized = raw_hex.replace(' ', '').strip()
            if not normalized:
                return None
            return bytes.fromhex(normalized)
        except ValueError:
            return None

    def _parse_ascii_from_raw_hex(self, raw_hex: str) -> str:
        """按 ASCII 规则解析原始 HEX。"""
        raw_bytes = self._hex_to_bytes(raw_hex)
        if not raw_bytes:
            return "未配置"

        if all(b in (0x20, 0x00, 0xFF) for b in raw_bytes):
            return "未配置"

        cleaned = raw_bytes.replace(b'\x00', b'').replace(b'\xff', b'')
        try:
            text = cleaned.decode('ascii', errors='ignore').strip()
            return text if text else "未配置"
        except Exception:
            return f"原始值异常 [HEX: {raw_hex}]"

    def _parse_unsigned_from_raw_hex(self, raw_hex: str, *, offset: int = 0, byteorder: Literal['big', 'little'] = 'big') -> str:
        """按 Unsigned + offset 规则解析原始 HEX。"""
        raw_bytes = self._hex_to_bytes(raw_hex)
        if not raw_bytes:
            return "未配置"

        value = int.from_bytes(raw_bytes, byteorder=byteorder, signed=False) + offset
        return str(value)

    def _get_response_slice_hex(self, response_bytes: bytes, start: int, end: int) -> str:
        """按完整响应的 0-based 字节位置提取闭区间 HEX。"""
        if not response_bytes or start < 0 or end < start or start >= len(response_bytes):
            return ""
        actual_end = min(end, len(response_bytes) - 1)
        return response_bytes[start:actual_end + 1].hex(' ').upper()

    def _extract_field_range_from_parsed_result(self, parsed_result, field_name_key: str) -> str:
        """仅从 DPT 结果中提取字段的 range_str，用于日志展示。

        注意：当前证书值的实际切片仍以 ECU 原始响应字节为准，
        DPT 的 range_str 只作为“字段位置说明”和调试日志输出来源，
        这样可以避免 DPT 配置边界与 ECU 实际报文边界存在 1 byte 偏差时，
        影响最终页面展示结果。
        """
        if not parsed_result or not getattr(parsed_result, 'fields', None):
            return ""
        for field in parsed_result.fields:
            name = getattr(field, 'name', '')
            if field_name_key in name:
                return str(getattr(field, 'range_str', '')).strip()
        return ""

    def _parse_cert_info_from_response(self, response_bytes: bytes, parsed_result=None) -> Dict[str, str]:
        """按 ECU 的原始响应字节位置切片，提取证书信息字段。

        解析约定：
        1. `response_bytes` 是完整的正响应，例如：`71 01 BE E8 ...`；
        2. 这里的 byte 位号按当前完整响应的 0-based 索引计算；
        3. 证书字段边界以 ECU 实际报文为准，避免完全依赖 DPT range_str 导致尾部字段错位；
        4. DPT 结果只用于补充“这个字段在 DPT 中声明的范围”，方便日志对照。
        """
        # 证书信息字段与原始响应字节位置的对应关系：
        # byte 005      -> 证书状态信息
        # byte 006~021 -> 证书版本号（ASCII）
        # byte 022~277 -> 证书环境（ASCII）
        # byte 278~340 -> 证书序列号
        # byte 341~342 -> 证书有效期_年（2 byte，little-endian，offset=2000）
        # byte 343     -> 证书有效期_月
        # byte 344     -> 证书有效期_日
        # byte 345     -> 证书有效期_时
        # byte 346     -> 证书有效期_分
        # byte 347     -> 证书有效期_秒
        cert_status_hex = self._get_response_slice_hex(response_bytes, 5, 5)
        cert_version_hex = self._get_response_slice_hex(response_bytes, 6, 21)
        cert_environment_hex = self._get_response_slice_hex(response_bytes, 22, 277)
        cert_sequence_hex = self._get_response_slice_hex(response_bytes, 278, 340)
        cert_year_hex = self._get_response_slice_hex(response_bytes, 341, 342)
        cert_month_hex = self._get_response_slice_hex(response_bytes, 343, 343)
        cert_day_hex = self._get_response_slice_hex(response_bytes, 344, 344)
        cert_hour_hex = self._get_response_slice_hex(response_bytes, 345, 345)
        cert_min_hex = self._get_response_slice_hex(response_bytes, 346, 346)
        cert_sec_hex = self._get_response_slice_hex(response_bytes, 347, 347)

        cert_status_range = self._extract_field_range_from_parsed_result(parsed_result, "Szitrus_certStatus") or '5/ALL'
        cert_version_range = self._extract_field_range_from_parsed_result(parsed_result, "Szitrus_getVersion") or '6-21/ALL'
        cert_environment_range = self._extract_field_range_from_parsed_result(parsed_result, "Environment") or '22-277/ALL'
        cert_sequence_range = self._extract_field_range_from_parsed_result(parsed_result, "Sequence_number") or '278-340/ALL'
        cert_year_range = self._extract_field_range_from_parsed_result(parsed_result, "Validity_duration_Year") or '341-342/ALL'
        cert_month_range = self._extract_field_range_from_parsed_result(parsed_result, "Validity_duration_Month") or '343/ALL'
        cert_day_range = self._extract_field_range_from_parsed_result(parsed_result, "Validity_duration_Day") or '344/ALL'
        cert_hour_range = self._extract_field_range_from_parsed_result(parsed_result, "Validity_duration_Hour") or '345/ALL'
        cert_min_range = self._extract_field_range_from_parsed_result(parsed_result, "Validity_duration_Min") or '346/ALL'
        cert_sec_range = self._extract_field_range_from_parsed_result(parsed_result, "Validity_duration_Sec") or '347/ALL'

        # 年字段当前按 little-endian 解析，例如 raw `60 00` -> 0x0060 -> 96，再加偏置 2000 得到 2096。
        # 月/日/时/分/秒均按单字节 Unsigned 解析，无额外偏置。
        year = self._parse_int_safely(self._parse_unsigned_from_raw_hex(cert_year_hex, offset=2000, byteorder='little'))
        month = self._parse_int_safely(self._parse_unsigned_from_raw_hex(cert_month_hex, offset=0))
        day = self._parse_int_safely(self._parse_unsigned_from_raw_hex(cert_day_hex, offset=0))
        hour = self._parse_int_safely(self._parse_unsigned_from_raw_hex(cert_hour_hex, offset=0))
        minute = self._parse_int_safely(self._parse_unsigned_from_raw_hex(cert_min_hex, offset=0))
        second = self._parse_int_safely(self._parse_unsigned_from_raw_hex(cert_sec_hex, offset=0))

        year_text = f"{year:04d}" if year is not None else "----"
        month_text = f"{month:02d}" if month is not None else "--"
        day_text = f"{day:02d}" if day is not None else "--"
        hour_text = f"{hour:02d}" if hour is not None else "--"
        minute_text = f"{minute:02d}" if minute is not None else "--"
        second_text = f"{second:02d}" if second is not None else "--"

        return {
            "cert_status": self._parse_unsigned_from_raw_hex(cert_status_hex),
            "cert_status_raw": cert_status_hex,
            "cert_version": self._parse_ascii_from_raw_hex(cert_version_hex),
            "cert_version_raw": cert_version_hex,
            "cert_environment": self._parse_ascii_from_raw_hex(cert_environment_hex),
            "cert_environment_raw": cert_environment_hex,
            "cert_sequence": self._parse_unsigned_from_raw_hex(cert_sequence_hex, byteorder='little'),
            "cert_sequence_raw": cert_sequence_hex,
            "validity_year": year_text,
            "validity_month": month_text,
            "validity_day": day_text,
            "validity_hour": hour_text,
            "validity_min": minute_text,
            "validity_sec": second_text,
            "validity_text": f"{year_text}-{month_text}-{day_text} {hour_text}:{minute_text}:{second_text}",
            "validity_raw": f"{cert_year_hex} | {cert_month_hex} | {cert_day_hex} | {cert_hour_hex} | {cert_min_hex} | {cert_sec_hex}",
            "range_map": (
                f"证书状态信息[{cert_status_range}]，证书版本号[{cert_version_range}]，证书环境[{cert_environment_range}]，"
                f"证书序列号[{cert_sequence_range}]，证书有效期_年[{cert_year_range}]，证书有效期_月[{cert_month_range}]，"
                f"证书有效期_日[{cert_day_range}]，证书有效期_时[{cert_hour_range}]，证书有效期_分[{cert_min_range}]，证书有效期_秒[{cert_sec_range}]"
            ),
        }

    def _parse_int_safely(self, value: Any) -> Optional[int]:
        if value is None:
            return None
        match = re.search(r'-?\d+', str(value))
        if not match:
            return None
        try:
            return int(match.group(0))
        except Exception:
            return None

    def _build_cert_info_display(self, response_bytes: bytes, parsed_result=None) -> str:
        """将 BEE8 的完整原始响应整理成最终展示文本。

        这里做三件事：
        1. 调用 `_parse_cert_info_from_response()` 从原始报文中切片取值；
        2. 做基础合法性校验（例如年月日时分秒是否落在合理范围）；
        3. 拼出界面直接展示的多行文本，并把 raw HEX 一并带上，方便问题定位。
        """
        if not response_bytes:
            return "DPT解析结果为空"

        cert_info = self._parse_cert_info_from_response(response_bytes, parsed_result)
        anomalies: List[str] = []

        self.log_signal.emit(f"证书字段位置映射：{cert_info['range_map']}")
        self.log_signal.emit(
            "证书原始字节映射："
            f"证书序列号 [raw: {cert_info['cert_sequence_raw'] if 'cert_sequence_raw' in cert_info else 'N/A'}]；"
            f"证书有效期 [raw: {cert_info['validity_raw']}]"
        )

        year = self._parse_int_safely(cert_info["validity_year"])
        month = self._parse_int_safely(cert_info["validity_month"])
        day = self._parse_int_safely(cert_info["validity_day"])
        hour = self._parse_int_safely(cert_info["validity_hour"])
        minute = self._parse_int_safely(cert_info["validity_min"])
        second = self._parse_int_safely(cert_info["validity_sec"])

        invalid_validity = (
            (year is not None and year < 2000)
            or (month is not None and not 1 <= month <= 12)
            or (day is not None and not 1 <= day <= 31)
            or (hour is not None and not 0 <= hour <= 23)
            or (minute is not None and not 0 <= minute <= 59)
            or (second is not None and not 0 <= second <= 59)
        )
        if invalid_validity:
            anomalies.append(f"证书有效期疑似异常: {cert_info['validity_text']}，原始字节: {cert_info['validity_raw']}")

        if parsed_result and getattr(parsed_result, 'fields', None):
            for field in parsed_result.fields:
                if "Szitrus_certStatus" in getattr(field, 'name', ''):
                    parsed_value = str(getattr(field, 'parsed_value', '')).strip()
                    if "reserved" in parsed_value.lower() or "reverved" in parsed_value.lower() or "预留" in parsed_value:
                        anomalies.append(f"证书状态信息DPT枚举结果为预留值，原始字节: {getattr(field, 'raw_hex', '')}")
                    break

        if anomalies:
            self.log_signal.emit("证书信息异常提示：" + "；".join(anomalies))

        return "\n".join([
            f"证书状态信息：{cert_info['cert_status']} [raw: {cert_info.get('cert_status_raw', 'N/A')}]",
            f"证书版本号：{cert_info['cert_version']} [raw: {cert_info.get('cert_version_raw', 'N/A')}]",
            f"证书环境：{cert_info['cert_environment']} [raw: {cert_info.get('cert_environment_raw', 'N/A')}]",
            f"证书序列号：{cert_info['cert_sequence']} [raw: {cert_info.get('cert_sequence_raw', 'N/A')}]",
            f"证书有效期：{cert_info['validity_text']} [raw: {cert_info.get('validity_raw', 'N/A')}]",
        ])

    # --- UDS Helpers (Refactored) ---
    def _get_cert_info(self) -> str:
        # 证书信息读取整体链路：
        # 1) 发送 31 01 BE E8 例程请求 ECU 返回证书原始数据；
        # 2) 若 DPT 就绪，则用 DPT 解析字段名称/range，辅助日志定位；
        # 3) 最终仍以 `_build_cert_info_display()` 基于原始响应字节切片输出展示文本。
        self.log_signal.emit("-->读取证书信息<--")
        payload = bytes([0x31, 0x01, 0xBE, 0xE8])
        data = self._device_service.execute_secure_routine(payload, sec_level=0x21, log_signal=self.log_signal)

        if not isinstance(data, (bytes, bytearray)) or not data:
            self.log_signal.emit(f"证书信息读取失败，原始返回: {data}")
            return "读取失败(可能需要解锁)"

        data = bytes(data)
        self.log_signal.emit(f"证书信息原始响应长度: {len(data)} 字���")
        self.log_signal.emit(f"证书信息原始响应: {data.hex(' ').upper()}")

        # 使用 DPTService 解析数据
        if self._dpt_service.is_ready():
            parsed_result = self._dpt_service.parse_bytes(data, did="BEE8")
            if parsed_result:
                self.log_signal.emit(f"DPT解析结果: {parsed_result.fields}")
                display_text = self._build_cert_info_display(data, parsed_result)
                self.log_signal.emit(f"证书信息整理结果:\n{display_text}")
                return display_text
            else:
                self.log_signal.emit("DPT解析失败: 未找到匹配的解析规则")
        else:
            self.log_signal.emit("DPT服务未就绪，无法解析数据")

        return self._build_cert_info_display(data)

    def _get_key_slot_status(self) -> str:
        self.log_signal.emit("-->读取密钥槽状态<--")
        data = self._send_uds_read(0xBE, 0x2C)
        if not data:
            return "读取失败"

        # 使用 DPTService 解析数据
        if self._dpt_service.is_ready():
            parsed_result = self._dpt_service.parse_bytes(data, did="BE2C")
            if parsed_result:
                # self.log_signal.emit(f"DPT解析结果: {parsed_result.fields}")
                groups = {}
                for field in parsed_result.fields:
                    if hasattr(field, 'name') and hasattr(field, 'parsed_value'):
                        name = field.name
                        # Skip Reserved fields
                        if "Reserved" in name or "预留" in name:
                            continue
                        if name not in groups:
                            groups[name] = []
                        groups[name].append(str(field.parsed_value))

                final_output_lines = []
                for name, values in groups.items():
                    meaningful_values = [v for v in values if "unknown" not in v.lower() and "未知状态" not in v and not v.startswith("0 -")]

                    # If we have meaningful values, use them. Otherwise use the original values (which are all unknown).
                    target_values = meaningful_values if meaningful_values else values

                    display_values = []
                    for v in target_values:
                        # Extract content in parentheses
                        m = re.search(r'\((.*?)\)', v)
                        if m:
                            display_values.append(m.group(1))
                        else:
                            display_values.append(v)

                    # Deduplicate
                    display_values = list(dict.fromkeys(display_values))

                    status_str = ", ".join(display_values) if display_values else "未知状态"

                    # Extract label from name: "SecOCkeySlotStatus(SecOC秘钥槽状态)" -> "SecOC秘钥槽状态"
                    m_label = re.search(r'\((.*?)\)', name)
                    label = m_label.group(1) if m_label else name

                    final_output_lines.append(f"{label}：{status_str}")

                if final_output_lines:
                    res ="\n".join(final_output_lines)
                    self.log_signal.emit(f"读取密钥槽状态DPT解析结果: {res}")
                    return res
                else:
                    return "解析结果为空"

            else:
                self.log_signal.emit("DPT解析失败: 未找到匹配的解析规则")
                return f"DPT解析失败 Data: {data.hex(' ').upper()}"
        else:
            self.log_signal.emit("DPT服务未就绪，无法解析数据")
            return f"Raw: {data.hex(' ').upper()}"

    def _get_cms_env(self) -> str:
        self.log_signal.emit("-->读取CMS环境<--")
        data = self._send_uds_read(0xBE, 0x2D)

        if not data:
            return "读取失败"

        if self._dpt_service.is_ready():
            parsed_result = self._dpt_service.parse_bytes(data, did="BE2D")
            if parsed_result:
                lines = []
                res = "解析结果为空"
                for field in parsed_result.fields:
                    name = field.name
                    val_str = str(field.parsed_value)

                    # 针对 ASCII 编码字段或特定字段名进行 ASCII 转换尝试
                    # 主要是处理全FF情况，或者 DPT 返回了 Hex String 的情况
                    is_ascii_field = getattr(field, 'encoding', '') == 'ASCII' or 'CMS' in name
                    if is_ascii_field:
                        raw_hex = getattr(field, 'raw_hex', '')
                        if raw_hex:
                            try:
                                hex_str = raw_hex.replace(' ', '')
                                byte_data = bytes.fromhex(hex_str)
                                # 检查是否全为 FF 或 00 (未配置)
                                if all(b == 0xFF for b in byte_data) or all(b == 0x00 for b in byte_data):
                                    val_str = "未配置"
                                else:
                                    # 尝试去除 padding (00 或 FF) 并解码
                                    clean_bytes = byte_data.replace(b'\xff', b'').replace(b'\x00', b'')
                                    if clean_bytes:
                                        decoded = clean_bytes.decode('ascii', errors='ignore').strip()
                                        val_str = decoded if decoded else val_str
                                    else:
                                        val_str = "未配置"
                            except Exception:
                                pass

                    lines.append(f"{name}：{val_str}")
                    res = "\n".join(lines) if lines else "解析结果为空"
                    self.log_signal.emit(f"读取CMS环境DPT解析结果: {res}")
                return res
            else:
                 self.log_signal.emit("DPT解析失败: 未找到匹配的解析规则")
                 return f"DPT解析失败 Data: {data.hex(' ').upper()}"
        else:
            self.log_signal.emit("DPT服务未就绪，无法解析数据")
            return f"Raw: {data.hex(' ').upper()}"

    def _start_worker(self, func: Callable, result_signal: Optional[pyqtSignal] = None):
        """启动 Worker 执行任务"""
        # 封装任务以捕获异常并发送错误信号
        def wrapped_task():
            try:
                return func()
            except Exception as e:
                import traceback
                traceback.print_exc()
                self.sig_error.emit(str(e))  # type: ignore
                return None

        worker = Worker(wrapped_task)
        # 连接日志信号，转发给 UI
        worker.log_signal.connect(self.log_signal.emit)  # type: ignore
        # 连接结果信号
        if result_signal:
            worker.result_signal.connect(lambda res: result_signal.emit(res) if res is not None else None)  # type: ignore
        # 清理
        worker.finished.connect(lambda: self._workers.remove(worker) if worker in self._workers else None)

        self._workers.append(worker)
        worker.start()

    def request_eth_snapshot(self):
        """采集整车拓扑概览（异步）。"""
        def task():
            # 加锁保护
            self._mutex.lock()
            try:
                return self._fetch_eth_snapshot()
            finally:
                self._mutex.unlock()

        # _fetch_eth_snapshot 内部已发送 sig_topology_updated，这里传入 None 避免重复发送
        self._start_worker(task, None)

    def _get_service_status_str(self) -> str:
        """Helper to get service status as string"""
        res = self._get_service_status()
        if hasattr(res, 'get') and "status_summary" in res:
            return str(res["status_summary"])
        if isinstance(res, dict): return str(res)
        return str(res)

    def _build_dummy_can_lin_snapshot(self) -> List[Tuple[str, str, str, int, int]]:
        """模拟 CAN/LIN 拓扑数据"""
        nodes = [("LLCE", "", "online", 0, 0)]
        for i in range(1, 14):
            nodes.append((f"CANFD{i}", "", "online", 0, 0))
        nodes.append(("LIN1", "", "online", 0, 0))
        nodes.append(("LIN2", "", "online", 0, 0))
        return nodes

    def _extract_node_name(self, key: str) -> str:
        """从 DPT Key 中提取节点名称"""
        node_name = key
        # 提取规则: "与...连接的以太网联接状态"
        match = re.search(r"与(.+?)连接的以太网联接状态", key)
        if match:
            node_name = match.group(1).strip()
        else:
            match = re.search(r"与(.+?)的以太网联接状态", key)
            if match:
                node_name = match.group(1).strip()
            else:
                match = re.search(r"与(.+?)以太网联接状态", key)
                if match:
                    node_name = match.group(1).strip()

        corrections = {
            "GMAC0": "GMACO",
            "ZCUL": "ZCULL",
            "PFE_MAC2": "PFE_EMAC2",
            "PCS/PAPA": "PCS/FAPA"
        }
        return corrections.get(node_name, node_name)

    def _fetch_eth_snapshot(self) -> TopologySnapshot:
        """通过已建立的 DoIP 连接向 ECU 请求拓扑信息，并转换为 TopologySnapshot。"""
        if self._device_service is None:
            raise TopologyServiceError("未注入 DeviceService，无法通过 DoIP 采集拓扑")
        # 以太网 link 状态（新增）：通过 22 BE1A 获取当前各节点 link up/down 信息
        link_status = self._get_eth_link_status()
        self.log_signal.emit(f"获取到的 Link Status Keys: {list(link_status.keys())}")
        # 拓扑节点构建
        nodes = []
        # 中心节点
        nodes.append(("ETH Switch", "🌐", "online", 0, 0))
        link_items = self._get_link_status_items(link_status)
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

        self.log_signal.emit(f"构建的拓扑节点 ({len(nodes)}个): {nodes}")
        snapshot = TopologySnapshot(
            nodes=nodes,
            vehicle_info={},
            service_status={},
            security_info={},
            network_management={},
            storage_info={},
        )

        # 手动发送信号，确保界面更新
        self.sig_topology_updated.emit(snapshot)
        return snapshot

    def _get_link_status_items(self, link_status: Dict[str, str]) -> List[Tuple[str, str]]:
        """根据链路状态构建链接项"""
        link_items = []
        for key, value in link_status.items():
            # 过滤出包含 "以太网联接状态" 的项
            if "以太网联接状态" in key or "ETH_SWITCH" in key or "PFE_EMAC" in key:
                # 使用专门的规则提取节点名称
                node_name = self._extract_node_name(key)
                # 状态映射: Link up -> 正常 (online), Link Down -> 离线 (offline)
                status = "online" if "Link up" in value else "offline"
                link_items.append((node_name, status))
        return link_items


    # --- DoIP Helpers ---
    def _send_uds_read(self, did_high, did_low) -> Optional[bytes]:
        payload = bytes([0x22, did_high, did_low])
        self.log_signal.emit(f"发送 UDS 读取: {payload.hex(' ').upper()}")
        rx = self._device_service.send_doip_payload(payload, timeout=1.0)
        if rx and len(rx) >= 3 and rx[0] == 0x62 and rx[1] == did_high and rx[2] == did_low:
            self.log_signal.emit(f"收到 UDS 响应: {rx.hex(' ').upper()}")
            return rx[3:]
        self.log_signal.emit(f"UDS 读取失败或无响应: {rx.hex(' ').upper() if rx else 'None'}")
        return None

    def _get_eth_link_status(self) -> Dict[str, str]:
        """读取以太网各节点 link 状态（UDS 22 BE1A）。
        """
        if not self._dpt_ready:
            self.log_signal.emit("DPTService 尚未就绪，跳过解析")
        self.log_signal.emit("开始执行：读取以太网Link状态")
        result: Dict[str, str] = {}
        payload = bytes([0x22, 0xBE, 0x1A])
        self.log_signal.emit(f"发送 UDS 读取: {payload.hex(' ').upper()}")
        try:
            rx = self._device_service.send_doip_payload(payload, timeout=1.0)
        except Exception as e:
            self.log_signal.emit(f"读取失败: {e}")
            result["eth_link_raw"] = f"读取失败: {e}"
            return result

        if not rx or len(rx) < 3 or rx[0] != 0x62 or rx[1] != 0xBE or rx[2] != 0x1A:
            self.log_signal.emit(f"无有效响应: {rx.hex(' ').upper() if rx else 'None'}")
            result["eth_link_raw"] = "无有效响应"
            return result

        data = rx[3:]
        self.log_signal.emit(f"Link状态原始数据: {data.hex(' ').upper()}")

        # 使用 DPTService 解析数据
        if self._dpt_service.is_ready():
            parsed_result = self._dpt_service.parse_bytes(data, did="BE1A")
            if parsed_result:
                self.log_signal.emit(f"DPT解析结果: {parsed_result.fields}")
                for field in parsed_result.fields:
                    if hasattr(field, 'name') and hasattr(field, 'parsed_value'):
                        result[field.name] = str(field.parsed_value)
            else:
                self.log_signal.emit("DPT解析失败: 未找到匹配的解析规则")
        else:
            self.log_signal.emit("DPT服务未就绪，无法解析数据")

        # 暂不清楚各节点对应 bit/byte 的精确含义，这里先挂原始 hex，方便 UI 或日志查看
        result["eth_link_raw"] = data.hex(' ').upper()
        self.log_signal.emit(f"Link状态解析结果: {result}")
        return result

    def _get_vin(self) -> str:
        self.log_signal.emit("-->读取VIN码<--")
        data = self._send_uds_read(0xF1, 0x90)
        if data:
            self.log_signal.emit(f"VIN原始数据: {data.hex(' ').upper()}")
            try:
                result = data.decode('ascii').strip()
            except:
                result = data.hex()
            self.log_signal.emit(f"VIN解析结果: {result}")
            return result
        self.log_signal.emit("VIN读取失败: 无数据")
        return "Unknown"

    def _get_vehicle_mode(self) -> str:
        self.log_signal.emit("-->读取车辆模式<--")
        data = self._send_uds_read(0x50, 0x01)
        if data:
            self.log_signal.emit(f"车辆模式原始数据: {data.hex(' ').upper()}")
            mode = data[0] & 0x0F
            modes = {
                0x00: "正常模式", 0x01: "生产模式", 0x02: "运输模式", 0x03: "展厅模式",
                0x04: "碰撞模式", 0x05: "维修模式"
            }
            result = modes.get(mode, f"未知模式({mode})")
            self.log_signal.emit(f"车辆模式解析结果: {result}")
            return result
        self.log_signal.emit("车辆模式读取失败: 无数据")
        return "Unknown"

    def _get_factory_mode(self) -> str:
        self.log_signal.emit("-->读取工厂模式<--")
        # 假设工厂模式 DID 为 0xBE01 (示例)
        data = self._send_uds_read(0xBE, 0x01)
        if data:
            self.log_signal.emit(f"工厂模式原始数据: {data.hex(' ').upper()}")
            # 假设 01 为工厂模式，00 为用户模式
            return "工厂模式" if data[0] == 0x01 else "用户模式"
        return "未知"

    def _get_voltage(self) -> str:
        self.log_signal.emit("-->读取电压<--")
        data = self._send_uds_read(0x10, 0x00)
        if data:
            self.log_signal.emit(f"电压原始数据: {data.hex(' ').upper()}")
            # 假设是 raw hex 或者某种编码，这里直接转 hex 显示
            result = f"{int.from_bytes(data, 'big')} mV" # 假设单位 mV，具体需确认
            self.log_signal.emit(f"电压解析结果: {result}")
            return result
        self.log_signal.emit("电压读取失败: 无数据")
        return "Unknown"



    # --- SomeIP Helpers ---

    def _get_user_mode(self) -> str:
        """模拟获取用户模式"""
        if self._device_service is None:
            self.log_signal.emit("未连接设备，无法获取服务状态")
            return "未连接设备，无法获取服务状态"

        someip_client = self._device_service.get_someip_client()
        if not someip_client:
            self.log_signal.emit("SomeIP Client 未初始化")
            return "SomeIP Client 未初始化"
        CLIENT_IP = "172.16.64.47"
        ECU_UNICAST_IP = "172.16.66.79"
        # 你的测试参数
        SERVICE_ID = 0x1055

        # METHOD_ID:
        # 输入 < 0x8000 (如 0x0001) 将自动走 RPC Request (UDP/TCP)
        # 输入 >= 0x8000 (如 0x9001) 将自动走 Event 订阅
        METHOD_ID = 0x9001

        # Event Group ID (Event模式下需要)
        EVENT_GROUP_ID = 0x0001

        # Payload (RPC模式下需要，Event模式忽略)
        # PAYLOAD = None
        PAYLOAD = b'\x00'
        try:
            # 只需要调用这一个通用接口，内部会自动处理
            # 1. 发现服务
            # 2. 如果是 9001 -> 订阅 -> 等待 Notification
            # 3. 如果是 0001 -> 请求 -> 等待 Response
            result = someip_client.request_with_discovery(
                service_id=SERVICE_ID,
                method_id=METHOD_ID,
                payload=PAYLOAD,
                target_ip=ECU_UNICAST_IP,
                event_group_id=EVENT_GROUP_ID,  # 如果是 RPC 这里的参数会被忽略
                timeout=10  # 等待时间
            )
            if result is not None:
                logger.info(f"\n[测试成功] 收到结果 (Hex): {result.hex()}")
            else:
                logger.info(f"\n[测试失败] 未收到预期回复 (RPC Response 或 Event Notification)")

        except KeyboardInterrupt:
            # print("停止")
            pass
        return "Unknown"

    def _get_service_status(self) -> Union[str, Dict[str, Any]]:
        """
        采集 SOME/IP 服务状态。
        通过 SOME/IP SD 协议或特定的 Discovery 机制获取。
        """
        if self._device_service is None:
            self.log_signal.emit("未连接设备，无法获取服务状态")
            return "No Device Service"
        someip_client = self._device_service.get_someip_client()
        if not someip_client:
            self.log_signal.emit("SomeIP Client 未初始化")
            return "No SomeIP Client"

        self.log_signal.emit("-->开始获取 SOME/IP 服务状态<--")
        TARGET_SERVICE_ID = 0x10FA
        TARGET_METHOD_ID = 0x0003
        request_payload = b''
        try:
            self.log_signal.emit(f"发送 Discovery 请求: Service=0x{TARGET_SERVICE_ID:04X}, Method=0x{TARGET_METHOD_ID:04X}")
            response_data = someip_client.request_with_discovery(
                service_id=TARGET_SERVICE_ID,
                method_id=TARGET_METHOD_ID,
                payload=request_payload,
                target_ip="172.16.66.79",
                timeout=10
            )

            parser = SomeIpParser()
            response_parser = parser.parse_data('ApServiceStateVectorType', response_data)

            # 返回原始数据作为临时方案
            if response_data:
                self.log_signal.emit(f"收到服务状态响应(Raw): {response_data.hex()}")
                self.log_signal.emit(f"收到服务状态响应(解析结果): {response_parser}")

                try:
                    # Format response_parser as indented JSON string
                    formatted_json = json.dumps(response_parser, indent=4, ensure_ascii=False)
                    return f"解析格式: \n{formatted_json}"
                except Exception as e:
                    self.log_signal.emit(f"JSON格式化失败: {e}, 使用默认转换")
                    return f"解析格式: {response_parser}"
            else:
                self.log_signal.emit("未收到服务状态响应")
                return "No response"

        except ImportError:
            msg = "无法导入 SomeIpParser，请检查 app.modules.device_topology.controller.test 模块"
            self.log_signal.emit(msg)
            return msg
        except Exception as e:
            msg = f"获取服务状态过程中发生异常: {str(e)}"
            self.log_signal.emit(msg)
            return msg


    # --- SSH Helpers ---
    def _get_storage_info(self) -> str:
        cmd = "df -h"
        self.log_signal.emit(f"发送 SSH 指令: {cmd}")

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
            self.log_signal.emit(f"SSH 指令成功: \n{result}")
            return result

        self.log_signal.emit(f"SSH 指令失败 or Empty")
        return "Error: Empty response"

    def _get_version_info(self) -> str:
        if self._device_service is None:
            self.log_signal.emit("DeviceService 未注入，无法获取版本信息")
            return "服务不可用"

        client = self._device_service.get_ssh_client()
        if client is None:
            self.log_signal.emit("SSH客户端未初始化，无法获取版本信息")
            return "SSH客户端无效"

        if not client.is_connected():
            self.log_signal.emit("SSH未连接，无法获取版本信息")
            return "SSH未连接"

        cmd = "get_ccu_all_version"
        self.log_signal.emit(f"发送 SSH 指令: {cmd}")

        try:
            out = client.execute_command(cmd)
            if out:
                result = out.strip()
                self.log_signal.emit(f"SSH 指令成功: \n{result}")
                return result
            else:
                return "Empty Response"
        except Exception as e:
            self.log_signal.emit(f"SSH指令执行异常: {e}")
            return f"Error: {e}"

    # --- Network Diagnosis Helpers (Moved from Controller) ---

    def execute_capture_routine(self, command: bytes) -> bool:
        """执行抓包相关的 UDS 例程"""
        if self._device_service is None:
            self.log_signal.emit("DeviceService 未注入，无法执行抓包指令")
            return False
        # Use emit
        return self._device_service.execute_secure_routine(command, sec_level=0x01, log_signal=self.log_signal) # log_callback removed, assume DeviceService now uses signal

    def request_capture_ccu_eth(self) -> bool:
        """CCU ETH数据抓包"""
        cmd = bytes.fromhex("31 01 BE E7 3E")
        return self.execute_capture_routine(cmd)

    def request_capture_node_eth(self) -> bool:
        """节点 ETH数据抓包"""
        cmd = bytes.fromhex("31 01 BE E7 03")
        return self.execute_capture_routine(cmd)

    def request_capture_vehicle_eth(self) -> bool:
        """整车 ETH数据抓包"""
        cmd = bytes.fromhex("31 01 BE E7 FF")
        return self.execute_capture_routine(cmd)


    def request_tx_rx_count(self) -> Tuple[bool, str]:
        """获取 TX/RX 计数"""
        if self._device_service is None:
            self.log_signal.emit("服务不可用: DeviceService 未注入")
            return False, "服务不可用"

        ssh_client = self._device_service.get_ssh_client()
        if not ssh_client or not ssh_client.is_connected():
            self.log_signal.emit("SSH未连接")
            return False, "SSH未连接"

        cmd = "Use -mib -all"
        self.log_signal.emit(f"发送 SSH 指令: {cmd}")
        out = ssh_client.execute_command(cmd)

        if out:
            self.log_signal.emit(f"收到 SSH 响应: {out.strip()}")
        else:
            self.log_signal.emit("SSH 指令执行无响应或失败")

        # execute_command 返回 stdout (str) 或 None
        if out is not None:
            return True, out.strip().splitlines()[0] if out else "OK"
        else:
            return False, "执行失败"

    def request_ping_node(self, key: str):
        """
        请求 Ping 指定节点
        :param key: 节点标识 (如 "adc", "rt2")
        """
        # ---------- Ping Logic Refactored ----------
        mapping = {
            "idc": ("IDC", "172.16.0.43", "172.16.64.43"),
            "adc_soc": ("ADC_SOC", "172.16.0.14", "172.16.64.14"),
            "adc_mcu": ("ADC_MCU", "172.16.5.14"),
            "tbox": ("TBOX", "172.16.0.45", "172.16.64.45"),
            "fl": ("FL", "172.16.0.21", "172.16.64.21"),
            "rt1": ("RT1", "172.16.0.79", "172.16.64.79"),
            "rt2": ("RT2", "172.16.1.79")
        }
        if key not in mapping:
            self.log_signal.emit(f"[Ping] 未配置节点: {key}")
            return

        config = mapping[key]
        name = config[0]
        ip0 = config[1]
        ip4 = config[2] if len(config) > 2 else None

        def task():
            if self._device_service is None:
                self.log_signal.emit("服务不可用: DeviceService 未注入")
                return None

            # 1. Ping VLAN 0
            self.log_signal.emit(f"正在 Ping {name} (VLAN0: {ip0})...")
            self.log_signal.emit(f"正在 每隔0.1s Ping {name} 一次，共Ping 10次，请稍候...")
            ok0 = self._ping_synch(ip0)

            # 2. Ping VLAN 4 (如果存在)
            ok4 = None # 使用 None 表示跳过
            if ip4:
                self.log_signal.emit(f"正在 Ping {name} (VLAN4: {ip4})...")
                self.log_signal.emit(f"正在 每隔0.1s Ping {name} 一次，共Ping 10次，请稍候...")
                ok4 = self._ping_synch(ip4)
            return key, ok0, ok4

        def on_finished(result):
            if result:
                self.sig_ping_result.emit(result[0], (result[1], result[2]))
        self._start_worker_with_result(task, on_finished)

    def _ping_synch(self, ip: str) -> bool:
        """同步执行 ping 命令"""
        client = self._device_service.get_ssh_client()
        if not client or not client.is_connected:
            return False
        cmd = f"ping -c 10 -i 0.1 {ip}" # 减少次数加快速度
        self.log_signal.emit(f"开始执行ping指令: {cmd}")
        out = client.execute_command(cmd)
        self.log_signal.emit(f"执行Ping指令返回结果: {out}")
        if out and ("packets received" in out):
            if re.search(r"\b0 packets received", out) or "100% packet loss" in out:
                return False
            return True
        return False

    def _start_worker_with_result(self, task_func: Callable, on_result: Callable):
        """Helper to start a worker and handle result"""
        worker = Worker(task_func)
        worker.log_signal.connect(self.log_signal.emit)
        worker.result_signal.connect(on_result)

        def cleanup():
            if worker in self._workers:
                self._workers.remove(worker)
        worker.finished.connect(cleanup)

        self._workers.append(worker)
        worker.start()

    # -------------------- 模拟数据路径 --------------------
    # @staticmethod
    # def _build_dummy_snapshot() -> TopologySnapshot:
    #     nodes = [
    #         ("CCU主控制器", "🖥️", "正常", 0, 0),
    #         ("CCU A-M核(RT1)", "⚡", "正常", -250, -150),
    #         ("CCU A-M核(RT2)", "⚡", "离线", 250, -150),
    #         ("IDC SoC", "🧠", "正常", -250, 150),
    #         ("TBOX", "📡", "正常", 250, 150),
    #         ("ADC SoC", "🎛️", "正常", -350, 0),
    #         ("ADC MCU", "🔌", "正常", 350, 0),
    #         ("激光雷达", "📡", "正常", 0, -200),
    #     ]
    #
    #     vehicle_info = {
    #         "vin": "LJ8A12345CCU67890",
    #         "vehicle_mode": "测试模式",
    #         "user_mode": "体验版",
    #         "factory_mode": "关闭",
    #         "voltage": "12.4 V",
    #     }
    #     service_status = {
    #         "srv_id01": "在线",
    #         "srv_id02": "运行中",
    #         "srv_id03": "待命",
    #     }
    #     security_info = {
    #         "cert_server": "cms.prod.internal",
    #         "pki_status": "正常",
    #         "cert_valid_date": "2026-05-30",
    #         "key_slot_status": "Slot#2 / 正常",
    #         "tls_switch": "已开启",
    #         "secoc_switch": "启用",
    #         "cms_env": "Production",
    #     }
    #     network_mgmt = {
    #         "power_wake_source": "车钥匙+远程",
    #         "pnc": "保持在线",
    #         "rt1_net_source": "CCU A-M核",
    #         "rt2_net_source": "CCU A-M核",
    #         "rt1_ext_msg": "稳定",
    #         "rt2_ext_msg": "低报文",
    #         "a_core_net_req": "已授权",
    #         "obd_can_net": "待机",
    #     }
    #     storage_info = {
    #         "a_core_storage": "65% / 128GB",
    #         "m_core_storage": "48% / 64GB",
    #     }
    #     return TopologySnapshot(
    #         nodes=nodes,
    #         vehicle_info=vehicle_info,
    #         service_status=service_status,
    #         security_info=security_info,
    #         network_management=network_mgmt,
    #         storage_info=storage_info,
    #     )

    def request_can_lin_snapshot(self):
        """
        采集 CAN/LIN 拓扑信息（异步）
        """
        def task():
            return self._fetch_can_lin_snapshot()

        self._start_worker(task, self.sig_can_lin_topology_updated)

    def _fetch_can_lin_snapshot(self) -> List[Tuple[str, str, str, int, int]]:
        """
        采集 CAN/LIN 拓扑信息
        总线状态获取方法：读取当前故障DTC，19022f，判断返回的DTC中是否有busoff的DTC。
        """
        if self._device_service is None:
            # 回退到 dummy 数据
            self.log_signal.emit("未连接设备，使用模拟数据")
            return self._build_dummy_can_lin_snapshot()

        client = self._device_service.get_doip_client()
        if not client or not client.is_connected:
            self.log_signal.emit("DoIP 未连接，使用模拟数据")
            return self._build_dummy_can_lin_snapshot()

        # 1. 故障读取 (DTC 0x19 02 2F)
        req = bytes.fromhex("19 02 2F")
        self.log_signal.emit(f"发送 DTC 读取指令: {req.hex(' ').upper()}")
        try:
            rx = client.send_doip_message(req, timeout=5.0)
        except Exception as e:
            self.log_signal.emit(f"DTC 读取异常: {e}")
            return self._build_dummy_can_lin_snapshot()

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
                    dtc_hex = dtc_bytes.hex(' ').upper()
                    dtc_list.append(dtc_hex)
            self.log_signal.emit(f"读取到的 DTC 列表: {dtc_list}")
        else:
            self.log_signal.emit(f"DTC 读取失败或无响应: {rx.hex(' ').upper() if rx else 'None'}")

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
        # dtc_list = ['05162F', '06162F', '098728', '0A8728', '0B8728', '0C8768', '0E8728', '0F8728', '108728', '128728', '138728', '148728', '158728', '168728', '1C8728', '1D8728', '1E8728', '058728', '068728', '078728', '088728', '098728', '248728', '258728', '268728', '2B622F', '0A622F', '0D622F', '3F772E', '8B8820', '45292F', '18292F', '19292F', '230A28', '540928', 'B68728', '7B7728', '988728', '29872C', '12872C', '20872C', '30872C', '40872C', '508728', '9F0188', 'C07388']
        # self.log_signal.emit(f"因设备未读有故障码，模拟的 DTC 列表: {dtc_list}")
        # 默认所有节点在线
        node_status = {name: "online" for name in dtc_map.values()}

        # 根据 DTC 更新状态
        for code in dtc_list:
             # 有可能只匹配前6位或者其他规则? 假设 exact match
             # 注意 dtc_list 里的格式是 "C07388"
             if code in dtc_map:
                node_name = dtc_map[code]
                node_status[node_name] = "offline"
                self.log_signal.emit(f"发现故障 DTC {code}，节点 {node_name} 标记为离线")

        # 3. 构建节点数据
        # 格式: (name, icon, status, x, y)
        nodes = []
        # 中心节点
        nodes.append(("LLCE", "", "online", 0, 0))

        # 按照 dtc_map 的 values 生成节点列表? 或者按照固定列表?
        # 为了保证顺序和完整性，按照 map 里的 values 遍历
        # 去重
        all_node_names = sorted(list(set(dtc_map.values())))
        # 或者按照之前的 dummy 列表来保证完整性

        for name in all_node_names:
            status = node_status.get(name, "online")
            nodes.append((name, "", status, 0, 0))

        return nodes

    def request_switch_fault(self):
        codes = {
            "B140716": "Ethernet switch 欠压故障",
            "B14074B": "Ethernet switch 过温故障",
        }
        self._read_dtc_and_match(codes, "无switch DTC", self.sig_switch_fault_updated)

    def request_pfe_fault(self):
        codes = {
            "B1F0794": "PFE软件故障",
            "B1F0796": "PFE硬件故障",
        }
        self._read_dtc_and_match(codes, "无PFE DTC", self.sig_pfe_fault_updated)

    # ---------- 故障读取（DTC 0x19 02 2F） ----------
    def _read_dtc_and_match(self, codes: dict, empty_text: str, result_signal: pyqtSignal):
        """
        通用 DTC 读取与匹配逻辑
        :param codes: 故障码字典 {code: description}
        :param empty_text: 无故障时的提示文本
        :param result_signal: 用于发送结果的信号 (str)
        """
        if not self._device_service:
            self.log_signal.emit("DeviceService 未注入，无法读取 DTC")
            result_signal.emit("服务不可用")
            return

        def task():
            client = self._device_service.get_doip_client()
            if client is None or not client.is_connected:
                # 尝试重连? 或者直接报错
                # 这里简单处理，若未连接则直接返回
                return "DoIP 未连接"

            try:
                # 19 02 08 (读取DTC) 或 19 02 2F (根据具体需求，这里保持原样)
                req = bytes.fromhex("19 02 2F")
                self.log_signal.emit(f"发送 DTC 读取指令: {req.hex(' ').upper()}")

                # 发送 DoIP 消息
                rx = client.send_doip_message(req, timeout=2.0)

                if not rx:
                    self.log_signal.emit("DTC 读取无响应")
                    return "读取超时"

                self.log_signal.emit(f"收到 DTC 响应: {rx.hex(' ').upper()}")

                # 简单 hex 查找匹配 DTC 码
                # 响应格式通常为 [59 02 2F] [StatusAvailabilityMask] [DTC1] [Status1] ...
                # 这里简化处理，直接在 hex 字符串中查找
                hex_str = rx.hex(' ').upper()
                hits = []
                for code, desc in codes.items():
                    # 移除可能存在的 0x 前缀，确保纯 hex 匹配
                    clean_code = code.replace("0x", "").upper()
                    if clean_code in hex_str:
                        hits.append(desc)

                if hits:
                    return ", ".join(hits)
                else:
                    return empty_text

            except Exception as e:
                self.log_signal.emit(f"读取 DTC 失败: {e}")
                return f"异常: {str(e)}"

        # 创建 Worker 执行任务
        worker = Worker(task)
        # 将 Worker 的日志信号连接到 Service 的日志信号，由 Controller 转发到 View
        # Worker emits strings to log_signal. We connect it to self.log_signal.
        worker.log_signal.connect(self.log_signal.emit) # type: ignore

        def on_finished(result):
            # 任务结束，通过信号发送结果
            result_signal.emit(result)
            if worker in self._workers:
                self._workers.remove(worker)

        worker.result_signal.connect(on_finished)
        self._workers.append(worker)
        worker.start()



