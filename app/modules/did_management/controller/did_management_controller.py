from app.core.base_controller import BaseController
from app.modules.did_management.model.did_management_model import DIDModel
from app.modules.did_management.view.did_management_view import DIDView


class DIDController(BaseController):
    def __init__(self, parent=None):
        self.model = DIDModel(parent)
        self.view = DIDView(parent)
        super().__init__(self.model, self.view, parent)
        self.view.read_btn.clicked.connect(self.read)
        self.view.write_btn.clicked.connect(self.write)

    def read(self):
        did = self.view.did_input.text() or "0xF190"
        self.model.read_did(did)

    def write(self):
        did = self.view.did_input.text() or "0xF190"
        self.model.write_did(did, "TEST")

    def on_model_changed(self):
        self.view.populate(self.model.response_tree, self.model.raw_data)

    def get_view(self):
        return self.view

