from __future__ import annotations

import os
import threading
import math # Added math import
import json
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional, Any, Callable, Union
import re

import logging
from PyQt5.QtCore import QObject, pyqtSignal, QMutex

from app.modules.device_topology.controller.service_status_parser import SomeIpParser
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
        self._dpt_service = DPTService()
        self._workers = [] # 管理内部 Worker
        self._mutex = QMutex() # 互斥锁，保护 DoIP/UDS 访问
        self._dpt_ready = False
        # 异步加载 DPT
        # self._load_dpt_async()
        self._width = 600
        self._height = 500

    # def _load_dpt_async(self):
    #     """异步加载 DPT 配置"""
    #     def load_task():
    #         try:
    #             # 尝试加载项目根目录下的 dpt_config.json，或者 Downloads 下的 dpt.json
    #             # 优先使用相对路径
    #             paths = [
    #                 "dpt_config.json",
    #                 r"D:\uidq9000\Downloads\dpt.json"
    #             ]
    #             loaded = False
    #             for path in paths:
    #                 try:
    #                     if os.path.exists(path):
    #                         self.log_signal.emit(f"正在加载 DPT 配置: {path}")
    #                         self._dpt_service.load_from_file(path)
    #                         loaded = True
    #                         break
    #                 except Exception as e:
    #                     self.log_signal.emit(f"加载 {path} 失败: {e}")
    #
    #             return loaded
    #         except Exception as e:
    #             return False
    #
    #     def on_loaded(success):
    #         self._dpt_ready = success
    #         if success:
    #             self.log_signal.emit("DPT 配置加载完成")  # type: ignore
    #         else:
    #             self.log_signal.emit("DPT 配置加载失败，部分功能可能不可用")  # type: ignore
    #
    #     # 使用 _start_worker_common (需稍微调整适应) 或直接用 Worker
    #     # 这里手动创建 Worker 以避免依赖尚未初始化的部分
    #     worker = Worker(load_task)
    #     worker.log_signal.connect(self.log_signal.emit)  # type: ignore
    #     worker.result_signal.connect(on_loaded)
    #     worker.finished.connect(lambda: self._workers.remove(worker) if worker in self._workers else None)
    #     self._workers.append(worker)
    #     worker.start()

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
        """异步请求证书信息"""
        tasks = [
            ("cert_info", self._get_cert_info, self.sig_cert_infos_updated),
            ("key_slot_status", self._get_key_slot_status, self.sig_key_slot_status_updated),
            ("cms_env", self._get_cms_env, self.sig_cms_env_updated)
        ]
        self._execute_parallel_tasks(tasks)

    def request_network_mgmt(self):
        """异步请求网络管理信息"""
        # 拆分 pnc_status 字典为多个 granular updates
        # 由于 _get_pnc_status 返回 dict，我们可以做一个 wrapper 或者 post-process
        # 或者为了简单，我们定义 3个任务，分别取 dict 的不同值 (效率低但架构统一)
        # 或者定义一个任务返回 dict，然后 helper 分发 emit (复杂)
        # 最佳方案: 重写 _get_pnc_status 逻辑，或者定义 3 个 helper 获取单个值

        # 既然 _get_pnc_status 只是 mock，我们定义 3 个 helper
        tasks = [
            ("power_wake_source", self._get_power_wake, self.sig_power_wake_updated),
            ("pnc", self._get_pnc, self.sig_pnc_updated),
            ("rt1_net_source", self._get_rt1_net, self.sig_rt1_net_updated)
        ]
        self._execute_parallel_tasks(tasks)

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

    # --- UDS Helpers (Refactored) ---
    def _get_cert_info(self) -> str:
        self.log_signal.emit("-->读取证书信息<--")
        payload = bytes([0x31, 0x01, 0xBE, 0xE8])
        routine = bytes.fromhex("31 01 BE E9")
        data =self._device_service.execute_secure_routine(routine, sec_level=0x21, log_signal=self.log_signal)
        if data: return data.hex()
        # rx = self._device_service.send_doip_payload(payload, timeout=2.0)
        return "读取失败(可能需要解锁)"

    def _get_key_slot_status(self) -> str:
        self.log_signal.emit("-->读取密钥槽状态<--")
        data = self._send_uds_read(0xBE, 0x2C)
        if data: return data.hex()
        return "Unknown"

    def _get_cms_env(self) -> str:
        self.log_signal.emit("-->读取CMS环境<--")
        data = self._send_uds_read(0xBE, 0x2D)
        if data: return data.hex()
        return "Unknown"

    def _get_power_wake(self) -> str:
        return "Unknown" # Mock data

    def _get_pnc(self) -> str:
        return "Unknown" # Mock data

    def _get_rt1_net(self) -> str:
        return "Unknown" # Mock data

    def _get_pnc_status(self) -> Dict[str, str]:
        return {
            "power_wake_source": "Unknown",
            "pnc": "Unknown",
            "rt1_net": "Unknown"
        }

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

    def _start_worker_common(self, func: Callable, signal: pyqtSignal, action_name: str):
        """通用的 Worker 启动"""
        def wrapped_task():
            try:
                success = func()
                msg = f"{action_name}指令发送完成" if success else f"{action_name}指令发送失败"
                return success, msg
            except Exception as e:
                return False, str(e)
        self._start_worker(wrapped_task, signal)

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
        result["eth_link_raw"] = data.hex().upper()
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
        if hasattr(self, 'log_signal'):
            self.log_signal.emit(f"[Debug] Sending SOME/IP to {target_ip}:{target_port}")

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
        if not client or not client.is_connected():
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
                    dtc_hex = dtc_bytes.hex().upper()
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
                hex_str = rx.hex().upper()
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

