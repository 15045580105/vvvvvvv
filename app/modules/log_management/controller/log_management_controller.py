from app.core.base_controller import BaseController
from app.modules.log_management.model.log_management_model import LogDownloadModel
from app.modules.log_management.view.log_management_view import LogDownloadView


class LogDownloadController(BaseController):
    def __init__(self, parent=None):
        self.model = LogDownloadModel(parent)
        self.view = LogDownloadView(parent)
        super().__init__(self.model, self.view, parent)
        self.on_model_changed()
        self.view.refresh_btn.clicked.connect(self.model.load_mock)

    def on_model_changed(self):
        self.view.populate(self.model.files)

    def get_view(self):
        return self.view

