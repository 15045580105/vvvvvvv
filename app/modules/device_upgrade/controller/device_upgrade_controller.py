from app.core.base_controller import BaseController
from app.modules.device_upgrade.model.device_upgrade_model import UpgradeModel
from app.modules.device_upgrade.view.device_upgrade_view import UpgradeView


class UpgradeController(BaseController):
    def __init__(self, parent=None):
        self.model = UpgradeModel(parent)
        self.view = UpgradeView(parent)
        super().__init__(self.model, self.view, parent)

    def get_view(self):
        return self.view

    def activate_for_device(self, device_info):
        """激活升级界面并显示目标设备信息"""
        self.model.selected_device = device_info
        self.view.show_device_targets([device_info])

    def handle_switch_payload(self, payload: dict):
        """通用入口：接收主窗口透传过来的payload（例如当前选中设备）。"""
        device = payload.get("device") if isinstance(payload, dict) else None
        if device:
            # 这里可以把设备信息显示到升级界面，例如填表或追加到设备列表
            if hasattr(self.view, "show_device_targets"):
                self.view.show_device_targets([device])
