# app/modules/device_management/device_management_controller.py
from app.core.base_controller import BaseController
from .device_management_view import DeviceManagementView


class DeviceManagementController(BaseController):
    """设备管理控制器"""

    def __init__(self, module_name: str, device_service, communication_service):
        super().__init__(module_name)
        self.device_service = device_service
        self.communication_service = communication_service
        self._view = None

    def initialize(self) -> bool:
        try:
            # 创建视图
            self._view = DeviceManagementView(self)

            # 连接信号槽
            self._setup_signal_connections()

            # 初始数据加载
            self.refresh_data()

            return True

        except Exception as e:
            print(f"设备管理控制器初始化失败: {str(e)}")
            return False

    def get_view(self):
        """获取视图"""
        return self._view

    def _setup_signal_connections(self):
        """设置信号连接"""
        # 视图信号连接到控制器方法
        self._view.device_selected.connect(self.on_device_selected)
        self._view.connect_requested.connect(self.on_connect_requested)
        self._view.refresh_requested.connect(self.on_refresh_requested)

        # 控制器信号连接到视图更新
        self.data_updated.connect(self._view.update_display)
        self.operation_completed.connect(self._view.on_operation_completed)

    def refresh_data(self):
        """刷新数据"""
        try:
            # 调用服务获取数据
            devices = self.device_service.get_all_devices()

            # 发射数据更新信号
            self.data_updated.emit({
                'devices': devices,
                'timestamp': '刚刚更新'
            })

        except Exception as e:
            print(f"刷新数据失败: {str(e)}")

    def on_device_selected(self, device_id: str):
        """设备选择事件"""
        try:
            device_info = self.device_service.get_device_info(device_id)
            self.data_updated.emit({
                'selected_device': device_info
            })

        except Exception as e:
            print(f"获取设备信息失败: {str(e)}")

    def on_connect_requested(self, device_id: str):
        """连接设备请求"""
        try:
            success = self.device_service.connect_device(device_id)
            self.operation_completed.emit('connect_device', success)

            # 刷新数据
            self.refresh_data()

        except Exception as e:
            print(f"连接设备失败: {str(e)}")
            self.operation_completed.emit('connect_device', False)

    def on_refresh_requested(self):
        """刷新请求"""
        self.refresh_data()

    def cleanup(self):
        """清理资源"""
        if self._view:
            self._view.deleteLater()
            self._view = None