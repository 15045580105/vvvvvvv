
import random

from app.core.base_model import BaseModel


class LogDownloadModel(BaseModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.files = []
        self.load_mock()

    def load_mock(self):
        self.files = [
            ("system.log", "2.4 MB", "2024-11-19 14:30:22"),
            ("diagnostic_trace_001.log", "15.8 MB", "2024-11-19 13:15:10"),
            ("error_dump_20241119.log", "8.2 MB", "2024-11-19 12:45:33"),
            ("network_status.log", "1.1 MB", "2024-11-19 11:20:15"),
            ("app_performance_data.log", "5.6 MB", "2024-11-19 10:55:42"),
        ]
        self.dataChanged.emit()

    def random_speed(self):
        return f"{random.uniform(0.5,5.0):.1f} MB/s"

