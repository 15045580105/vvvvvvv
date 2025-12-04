from PyQt5 import QtCore

from app.core.base_model import BaseModel
from app.presentation.views.base_view import BaseView


class BaseController(QtCore.QObject):
    """Base controller connecting model and view."""

    def __init__(self, model: BaseModel, view: BaseView, parent=None):
        super().__init__(parent)
        self.model = model
        self.view = view
        self.connect_signals()

    def connect_signals(self):
        if hasattr(self.model, 'dataChanged'):
            self.model.dataChanged.connect(self.on_model_changed)

    def on_model_changed(self):
        pass

    def get_view(self):
        """统一提供视图访问接口，供 MainController 构建 Tab 使用"""
        return self.view
