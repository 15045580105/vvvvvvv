from app.core.base_model import BaseModel


class FileTransferModel(BaseModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.local_path = "C:/Diagnostics/Logs"
        self.remote_filter = ""
        self.tasks = []

