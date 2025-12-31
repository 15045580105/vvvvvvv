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
            "全部故障 (8)",
            "当前故障 (3)",
            "历史故障 (4)",
            "未决故障 (1)",
        ]
        # DTCs
        self.dtcs = [
            ("P31AE87", "ZCUF存在故障，报文丢失", "VCU", "0x2F", "当前故障", "读取成功"),
            ("P31DF08", "EPB_2存在故障，总线信号/报文故障", "VCU", "0x2F", "当前故障", "未读取"),
            ("U012987", "与IBCS通讯存在故障，报文丢失", "CCU平台", "0x2E", "历史故障", "未读取"),
            ("C200554", "TPMS存在故障，标定丢失", "TPMS", "0x2F", "当前故障", "读取失败"),
            ("U010100", "与TCU通信丢失", "VCU", "0x21", "当前故障", "读取成功"),
            ("B12A1F", "电池电压过低", "VCU", "0x10", "当前故障", "未读取"),
        ]

        # Mock Freeze Frame Data
        self.freeze_frames = [
            {
                "code": "P31AE87",
                "desc": "ZCUF存在故障，报文丢失",
                "type": "Type A",
                "did": "0x0501",
                "length": 8,
                "params": [
                    {"byte": "0~1", "bit": "All", "name": "车速", "value": "100", "unit": "km/h"},
                    {"byte": "2~3", "bit": "All", "name": "电机转速", "value": "2000", "unit": "r/m"},
                    {"byte": "4~5", "bit": "All", "name": "电压", "value": "14.5", "unit": "V"},
                    {"byte": "6", "bit": "All", "name": "使用模式", "value": "驾驶模式", "unit": "/"},
                    {"byte": "All", "bit": "All", "name": "车辆模式", "value": "生产模式", "unit": "/"},
                ]
            },
            {
                "code": "P31AE87", # Same code, different DID block
                "desc": "ZCUF存在故障，报文丢失",
                "type": "Type A",
                "did": "0x0502",
                "length": 12,
                "params": [
                    {"byte": "0", "bit": "All", "name": "发生时间-年", "value": "2025", "unit": "/"},
                    {"byte": "1", "bit": "All", "name": "发生时间-月", "value": "9", "unit": "/"},
                    {"byte": "2", "bit": "All", "name": "发生时间-日", "value": "18", "unit": "/"},
                    {"byte": "3", "bit": "All", "name": "发生时间-时", "value": "9", "unit": "/"},
                    {"byte": "4", "bit": "All", "name": "发生时间-分", "value": "10", "unit": "/"},
                    {"byte": "5", "bit": "All", "name": "发生时间-秒", "value": "26", "unit": "/"},
                    {"byte": "6~7", "bit": "All", "name": "车速", "value": "100", "unit": "km/h"},
                    {"byte": "8~9", "bit": "All", "name": "电机转速", "value": "2000", "unit": "r/m"},
                    {"byte": "10~11", "bit": "All", "name": "电压", "value": "14.5", "unit": "V"},
                ]
            }
        ]

        self.dataChanged.emit()
