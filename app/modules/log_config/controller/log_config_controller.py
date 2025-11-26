from app.core.base_controller import BaseController
from app.modules.log_config.model.log_config_model import LogConfigModel
from app.modules.log_config.view.log_config_view import LogConfigView


class LogConfigController(BaseController):
    def __init__(self, parent=None):
        self.model = LogConfigModel(parent)
        self.view = LogConfigView(parent)
        super().__init__(self.model, self.view, parent)
        self.on_model_changed()

    def on_model_changed(self):
        self.view.populate(self.model.apps)

    def get_view(self):
        return self.view

