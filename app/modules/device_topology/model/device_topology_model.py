from app.core.base_model import BaseModel


class TopologyModel(BaseModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.networks = []
        self.nodes = []
        self.load_mock()

    def load_mock(self):
        self.networks = [
            ("电源管理网络", "正常", "2.1 KB/s"),
            ("PNC网络", "正常", "5.8 KB/s"),
            ("RT1外网报文", "正常", "1.2 KB/s"),
            ("RT2外网报文", "正常", "0.8 KB/s"),
            ("A核应用网络", "正常", "12.5 KB/s"),
            ("OBD-CAN网络", "正常", "0.3 KB/s"),
        ]
        self.nodes = [
            ("CCU主控制器", "🖥️", "正常", 0, 0),
            ("CCU A-M核(RT1)", "⚡", "正常", -250, -150),
            ("CCU A-M核(RT2)", "⚡", "离线", 250, -150),
            ("IDC SoC", "🧠", "正常", -250, 150),
            ("TBOX", "📡", "正常", 250, 150),
            ("ADC SoC", "🎛️", "正常", -350, 0),
            ("ADC MCU", "🔌", "正常", 350, 0),
            ("激光雷达", "📡", "正常", 0, -200),
        ]
        self.dataChanged.emit()

