from app.core.base_model import BaseModel


class DTCModel(BaseModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.categories = []
        self.dtcs = []
        self.load_mock()

    def load_mock(self):
        self.categories = ["全部故障 (42)", "当前故障 (3)", "历史故障 (38)", "未决故障 (1)"]
        self.dtcs = [
            ("U010100", "与TCU通信丢失", "已确认", "3", "2024-11-18 09:15:22"),
            ("B12A1F", "电池电压过低", "已确认", "12", "2024-11-17 20:45:10"),
            ("C05687", "转向角传感器故障", "未确认", "1", "2024-11-19 10:30:55"),
            ("P030200", "#2缸失火", "历史", "45", "2024-11-15 13:22:18"),
            ("U042286", "无效数据接收", "历史", "8", "2024-11-16 16:44:33"),
        ]
        self.dataChanged.emit()

