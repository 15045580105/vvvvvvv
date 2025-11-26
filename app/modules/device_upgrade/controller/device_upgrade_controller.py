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

