from app.core.base_controller import BaseController
from app.modules.performance_management.model.performance_management_model import PerformanceModel
from app.modules.performance_management.view.performance_management_view import PerformanceView


class PerformanceController(BaseController):
    def __init__(self, parent=None):
        self.model = PerformanceModel(parent)
        # 不把 Qt parent 传给 view，避免作为主窗口子窗口叠在布局外
        self.view = PerformanceView(self.model)
        super().__init__(self.model, self.view, parent)
        self.on_model_changed()

    def on_model_changed(self):
        self.view.populate()
