from PyQt5 import QtCore

class Worker(QtCore.QThread):
    """
    通用后台工作线程
    """
    log_signal = QtCore.pyqtSignal(str)
    progress_signal = QtCore.pyqtSignal(int)
    result_signal = QtCore.pyqtSignal(object)
    finished = QtCore.pyqtSignal()

    def __init__(self, func, *args, **kwargs):
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs

    def run(self):
        try:
            # 尝试调用 func，传入 log_callback 作为第一个参数
            # 适用于 def task(log_callback): ... 这种形式
            if not self.args and not self.kwargs:
                try:
                    result = self.func(self.log_signal.emit)
                except TypeError:
                    # 如果不需要参数，则无参调用
                    result = self.func()
            else:
                # 如果有其他参数，尝试将 log_callback 注入到 kwargs 中
                # 或者作为第一个参数？这取决于 func 的定义
                # 为了兼容性，建议使用者使用 lambda: func(arg1, arg2, log_callback=worker.log_signal.emit)
                # 但 worker 在 init 时还不存在。

                # 简单策略：直接调用，假设 args/kwargs 已经包含了所有需要的
                # 但 LogConfigController 需要 log_callback

                # 我们修改策略：总是尝试传入 log_callback 作为第一个参数，如果 args 存在则追加
                # 这要求 func 的第一个参数必须是 log_callback
                result = self.func(self.log_signal.emit, *self.args, **self.kwargs)

            self.result_signal.emit(result)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.log_signal.emit(f"执行异常: {e}")
            self.result_signal.emit(None)
        finally:
            self.finished.emit()
