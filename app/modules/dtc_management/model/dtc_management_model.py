# python
from app.core.base_model import BaseModel


class DTCModel(BaseModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.categories = []
        self.dtcs = []
        self.load_mock()

    def load_mock(self):
        # 分类统计可根据实际数据数量动态生成，这里保留示例
        self.categories = [
            "全部故障 (8)",
            "当前故障 (3)",
            "历史故障 (4)",
            "未决故障 (1)",
        ]
        # 新结构: (故障码, 故障描述, 上报子系统, 状态码, 故障状态, 冻结帧状态)
        # 冻结帧状态初始统一为“未读取”
        self.dtcs = [
            ("U010100", "与TCU通信丢失", "VCU", "0x21", "当前故障", "读取成功"),
            ("B12A1F", "电池电压过低", "VCU", "0x10", "当前故障", "未读取"),
            ("C05687", "转向角传感器故障", "CCU", "0x33", "当前故障", "未读取"),
            ("U042286", "无效数据接收", "CCU", "0x52", "历史故障", "未读取"),
            ("U012387", "与ABS通信丢失", "VCU", "0x27", "当前故障", "未读取"),
            ("B1900A", "安全气囊回路故障", "CCU", "0x71", "当前故障", "未读取"),
        ]
        self.dataChanged.emit()
