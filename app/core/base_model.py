# 模块基类
from PyQt5 import QtCore
from PyQt5.QtCore import QObject, pyqtSignal
import json
from datetime import datetime


class BaseModel(QtCore.QObject):
    """Base model providing common signals."""
    dataChanged = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
