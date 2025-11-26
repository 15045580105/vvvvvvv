from app.core.base_controller import BaseController
from app.modules.device_management.models.device_model import DeviceModel
from app.modules.device_management.views.device_management_view import DeviceView


class DeviceController(BaseController):
    def __init__(self, parent=None):
        self.model = DeviceModel(parent)
        self.view = DeviceView(parent)
        super().__init__(self.model, self.view, parent)
        self.view.scan_btn.clicked.connect(self.model.refresh)

    def on_model_changed(self):
        self.view.populate(self.model.devices)

    def get_view(self):
        return self.view
