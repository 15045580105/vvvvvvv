# 模块基类
from PyQt5.QtCore import QObject, pyqtSignal
import json
from datetime import datetime


class BaseModel(QObject):
    """基础数据模型类"""

    data_changed = pyqtSignal()
    error_occurred = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._data = {}
        self._is_modified = False

    @property
    def data(self):
        return self._data.copy()

    @property
    def is_modified(self):
        return self._is_modified

    def update_data(self, key, value):
        """更新数据"""
        if self._data.get(key) != value:
            self._data[key] = value
            self._is_modified = True
            self.data_changed.emit()

    def to_dict(self):
        """转换为字典"""
        return self._data.copy()

    def from_dict(self, data_dict):
        """从字典加载数据"""
        self._data.update(data_dict)
        self._is_modified = True
        self.data_changed.emit()

    def clear(self):
        """清空数据"""
        self._data.clear()
        self._is_modified = False
        self.data_changed.emit()