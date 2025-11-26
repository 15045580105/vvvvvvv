from app.core.base_controller import BaseController
from app.modules.dtc_management.model.dtc_management_model import DTCModel
from app.modules.dtc_management.view.dtc_management_view import DTCView


class DTCController(BaseController):
    def __init__(self, parent=None):
        self.model = DTCModel(parent)
        self.view = DTCView(parent)
        super().__init__(self.model, self.view, parent)
        self.on_model_changed()

    def on_model_changed(self):
        self.view.populate(self.model.categories, self.model.dtcs)

    def get_view(self):
        return self.view

