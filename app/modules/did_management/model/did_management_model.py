from app.core.base_model import BaseModel


class DIDModel(BaseModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.response_tree = []
        self.raw_data = ""

    def read_did(self, did: str):
        # mock parse
        self.raw_data = f"响应数据: DID {did}\n数据: 01 02 03 04 05 06"
        self.response_tree = [("版本", "v2.1.3"), ("VIN", "LFV2A21K3N4xxxxxx"), ("模式", "正常模式")]
        self.dataChanged.emit()

    def write_did(self, did: str, value: str):
        self.raw_data = f"写入DID {did} 值 {value} 成功"
        self.dataChanged.emit()

