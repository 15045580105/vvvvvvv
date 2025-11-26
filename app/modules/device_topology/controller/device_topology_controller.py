from app.core.base_controller import BaseController
from app.modules.device_topology.model.device_topology_model import TopologyModel
from app.modules.device_topology.view.device_topology_view import TopologyView


class TopologyController(BaseController):
    def __init__(self, parent=None):
        self.model = TopologyModel(parent)
        self.view = TopologyView(parent)
        super().__init__(self.model, self.view, parent)
        self.view.refresh_btn.clicked.connect(self.refresh)
        self.on_model_changed()

    def refresh(self):
        self.model.load_mock()

    def on_model_changed(self):
        self.view.populate(self.model.nodes, self.model.networks)

    def get_view(self):
        return self.view

