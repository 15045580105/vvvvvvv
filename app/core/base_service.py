# 服务基类
from PyQt5.QtCore import QObject


class BaseService(QObject):
    """应用中 Service 层的简单基类，占位以便统一类型。

    当前只继承自 QObject，后续可在此添加通用日志、线程池等能力。
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
