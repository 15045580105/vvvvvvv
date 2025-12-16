from app.core.base_controller import BaseController
from app.modules.device_topology.model.device_topology_model import TopologyModel
from app.modules.device_topology.view.device_topology_view import TopologyView
from app.services.device_manage.device_service import DeviceService
from app.services.device_manage.topology_service import TopologyService


class TopologyController(BaseController):
    def __init__(self, parent=None, device_service: DeviceService = None):
        self.model = TopologyModel(parent)
        self.view = TopologyView(parent)
        super().__init__(self.model, self.view, parent)

        # 注入 DeviceService，并初始化 TopologyService
        # 如果 device_service 为 None，TopologyService 内部会回退到 dummy 模式
        self.device_service = device_service
        # 默认 use_dummy=False，如果 device_service 为空，TopologyService 内部会自动处理
        # 但为了明确意图，如果没注入 device_service，我们也可以显式设为 True
        use_dummy = (device_service is None)
        self.topology_service = TopologyService(device_service=self.device_service, use_dummy=use_dummy)

        self.current_device = None # 存储当前选中的设备信息

        self.view.refresh_btn.clicked.connect(self.refresh)
        self.on_model_changed()

    def handle_switch_payload(self, payload: dict):
        """处理页面切换时传递的 payload，例如设备信息"""
        if payload and "device" in payload:
            self.current_device = payload["device"]
            self.view.append_log(f"已切换到设备: {self.current_device.get('ip')}")
            # 自动刷新或等待用户点击刷新
            # self.refresh()

    def refresh(self):
        # 调用 TopologyService 获取快照
        try:
            # 传入当前设备信息用于 SSH 连接
            snapshot = self.topology_service.fetch_snapshot(device_info=self.current_device)
            # 将 snapshot 数据更新到 model
            # 这里假设 model 有 update_from_snapshot 方法，或者手动更新字段
            # self.model.update_from_snapshot(snapshot)
            # 暂时手动更新 model 字段以匹配现有逻辑
            self.model.nodes = snapshot.nodes
            self.model.networks = snapshot.networks
            # 触发界面更新
            self.on_model_changed()

            # 更新信息块
            self.view.update_vehicle_info(snapshot.vehicle_info)
            self.view.update_service_status(snapshot.service_status)
            self.view.update_security_info(snapshot.security_info)
            self.view.update_network_mgmt(snapshot.network_management)
            self.view.update_storage_info(snapshot.storage_info)

            self.view.append_log("已刷新拓扑信息")
        except Exception as e:
            self.view.append_log(f"刷新拓扑失败: {e}")

    # def on_model_changed(self):
    #     self.view.populate(self.model.nodes, self.model.networks)
    #     info_payload = self.model.info_blocks_payload()
    #     self.view.update_vehicle_info(info_payload["vehicle_info"])
    #     self.view.update_service_status(info_payload["service_status"])
    #     self.view.update_security_info(info_payload["security_info"])
    #     self.view.update_network_mgmt(info_payload["network_mgmt"])
    #     self.view.update_storage_info(info_payload["storage_info"])

    def get_view(self):
        return self.view
