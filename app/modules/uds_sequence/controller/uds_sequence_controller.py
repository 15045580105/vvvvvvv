from app.core.base_controller import BaseController
from app.modules.uds_sequence.model.uds_sequence_model import UDSSequenceModel
from app.modules.uds_sequence.view.uds_sequence_view import UDSSequenceView


class UDSSequenceController(BaseController):
    def __init__(self, parent=None):
        self.model = UDSSequenceModel(parent)
        # 不把 Qt parent 传给 view，避免作为主窗口子窗口叠在布局外
        self.view = UDSSequenceView(self.model)
        super().__init__(self.model, self.view, parent)
