
import random

from app.core.base_model import BaseModel


class PerformanceModel(BaseModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.metrics = []
        self.processes = []
        self.update()

    def update(self):
        self.metrics = [
            ("📊 CPU总使用率", f"{random.uniform(15.0,45.0):.1f}%", "正常"),
            ("🧠 内存使用率", f"{random.uniform(40.0,75.0):.1f}%", "正常"),
            ("💾 磁盘IO", f"{random.uniform(10.0,150.0):.1f} MB/s", "正常"),
        ]
        self.processes = [
            ["diagnostic_service","1254","12.5","128","root"],
            ["memory_manager","892","8.3","96","system"],
        ]
        self.dataChanged.emit()

