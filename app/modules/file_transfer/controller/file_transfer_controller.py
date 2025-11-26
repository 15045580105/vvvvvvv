from app.core.base_controller import BaseController
from app.modules.file_transfer.model.file_transfer_model import FileTransferModel
from app.modules.file_transfer.view.file_transfer_view import FileTransferView


class FileTransferController(BaseController):
    def __init__(self, parent=None):
        self.model = FileTransferModel(parent)
        self.view = FileTransferView(parent)
        super().__init__(self.model, self.view, parent)

    def get_view(self):
        return self.view

