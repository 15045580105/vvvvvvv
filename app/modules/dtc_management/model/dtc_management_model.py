# python
from app.core.base_model import BaseModel


class DTCModel(BaseModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.categories = []
        self.dtcs = []
        self.freeze_frames = []
        self.load_mock()

    def load_mock(self):
        # Categories (Used for filter counts in real app)
        self.categories = [
            "全部故障 (0)",
            "当前故障 (0)",
            "历史故障 (0)",
            "未决故障 (0)",
        ]
        # DTCs
        self.dtcs = []

        # Mock Freeze Frame Data
        self.freeze_frames = []

        self.dataChanged.emit()
