from PyQt5.QtCore import QObject, pyqtSignal

class EventBus(QObject):
    """全局事件总线单例，用于跨模块通信"""
    # 设备列表变更信号
    device_list_changed = pyqtSignal()

    _instance = None
    _is_initialized = False

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(EventBus, cls).__new__(cls, *args, **kwargs)
            # 必须调用 QObject 初始化，但在单例 __new__ 中通常不直接 init
            # 这里如果不掉用 QObject.__init__ 信号可能无法工作
            # 更好的做法是让 _instance 成为模块级变量，或者 standard singleton pattern
        return cls._instance

    def __init__(self):
        # 防止重复初始化
        if EventBus._is_initialized:
            return
        super().__init__()
        EventBus._is_initialized = True

# 全局单例实例
event_bus = EventBus()

# 事件总线