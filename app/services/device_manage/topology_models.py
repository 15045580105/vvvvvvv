from dataclasses import dataclass
from typing import Dict, List, Tuple

@dataclass
class TopologySnapshot:
    """拓扑快照数据类"""
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

