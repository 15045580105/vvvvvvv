from app.core.base_model import BaseModel


class UDSSequenceModel(BaseModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.commands = ["22 F190 - 读取VIN码","22 5001 - 读取车辆模式","2E 0110 - 写入工厂模式","31 01 - 例程控制"]
        self.log = ""

