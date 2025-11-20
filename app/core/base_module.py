# app/core/base_module.py
from abc import ABC, abstractmethod
from PyQt5.QtWidgets import QWidget
from PyQt5.QtCore import QObject, pyqtSignal


class BaseModule(QObject, ABC):
    """
    模块基类 - 所有功能模块必须实现的接口
    确保所有模块都提供统一的接口方法
    """

    # 模块状态信号
    module_initialized = pyqtSignal(str)  # 模块名称
    module_error = pyqtSignal(str, str)  # 模块名称, 错误信息

    def __init__(self, module_name: str, di_container):
        super().__init__()
        self.module_name = module_name
        self.di_container = di_container
        self._is_initialized = False
        self._controller = None
        self._view = None

    @abstractmethod
    def initialize(self) -> bool:
        """初始化模块 - 必须实现"""
        pass

    @abstractmethod
    def get_view(self) -> QWidget:
        """获取模块的视图组件 - 必须实现"""
        pass

    @abstractmethod
    def get_controller(self):
        """获取模块的控制器 - 必须实现"""
        pass

    @abstractmethod
    def cleanup(self):
        """清理模块资源 - 必须实现"""
        pass

    @property
    def is_initialized(self) -> bool:
        return self._is_initialized

    @property
    def display_name(self) -> str:
        """获取模块的显示名称"""
        return self.module_name.replace('_', ' ').title()