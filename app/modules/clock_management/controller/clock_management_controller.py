from PyQt5.QtCore import pyqtSignal

from app.core.base_controller import BaseController
from app.modules.clock_management.view.clock_management_view import ClockManagementWidget


class ClockManagementController(BaseController):
    """时钟管理模块控制器：封装 ClockManagementWidget 以适配主界面架构。"""

    switch_page = pyqtSignal(dict, str)

    def __init__(self, parent=None):
        self.view = ClockManagementWidget(parent)
        # 时钟页面目前没有独立的模型，直接传 None
        super().__init__(model=None, view=self.view, parent=parent)

    def get_view(self):
        """供 MainController / Tab 构建使用，返回视图对象。"""
        return self.view

