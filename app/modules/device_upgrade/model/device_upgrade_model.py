from app.core.base_model import BaseModel


class UpgradeModel(BaseModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.devices = ["CCUA","CCU0","CCU1"]

