from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PyQt5.QtCore import pyqtSignal


class BaseView(QWidget):
    #"""基础视图类"""
    # 通用信号
    view_initialized = pyqtSignal()
    data_requested = pyqtSignal(str)
    operation_requested = pyqtSignal(str, dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.controller = None
        self.setup_ui()

    def setup_ui(self):
        """设置UI界面 - 由子类实现"""
        pass

    def set_controller(self, controller):
        """设置控制器"""
        self.controller = controller

    def update_display(self, data):
        """更新显示 - 由子类实现"""
        pass

    def show_error(self, error_msg):
        """显示错误信息"""
        # 这里可以统一实现错误提示
        pass