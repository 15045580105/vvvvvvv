# app/core/base_controller.py
from abc import ABC, abstractmethod
from PyQt5.QtWidgets import QWidget
from PyQt5.QtCore import QObject, pyqtSignal


class BaseController(QObject, ABC):
    """
    控制器基类 - 所有模块控制器必须实现的接口
    确保所有控制器都提供统一的接口方法
    """

    # 通用信号
    view_ready = pyqtSignal(QWidget)  # 视图就绪
    data_updated = pyqtSignal(dict)  # 数据更新
    operation_completed = pyqtSignal(str, bool)  # 操作完成 (操作名, 成功与否)

    def __init__(self, module_name: str):
        super().__init__()
        self.module_name = module_name
        self._view = None

    @abstractmethod
    def get_view(self) -> QWidget:
        """获取控制器管理的视图 - 必须实现"""
        pass

    @abstractmethod
    def initialize(self) -> bool:
        """初始化控制器 - 必须实现"""
        pass

    @abstractmethod
    def cleanup(self):
        """清理控制器资源 - 必须实现"""
        pass

    @abstractmethod
    def refresh_data(self):
        """刷新数据 - 必须实现"""
        pass