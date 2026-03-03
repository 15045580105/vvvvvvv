from PyQt5 import QtCore
import inspect

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
                # 检查 func 是否接受 log_callback 作为第一个参数，或者是否接受 args
                # 如果 func 的第一个参数看起来是 log_callback (比如叫 log_cb, callback, 或者只是多了一个参数位置)
                # 使用 inspect 检查签名
                try:
                    sig = inspect.signature(self.func)
                    params = list(sig.parameters.values())

                    pass_log_cb = False
                    if len(params) > 0:
                        # 简单启发式：如果有参数，且参数数量比我们传进来的 args 多1，且第一个参数名有 hint
                        # 或者 просто 尝试绑定

                        # 更加健壮的方法：尝试绑定。
                        # 我们想传 (log_cb, *args, **kwargs)
                        # 如果绑定成功，就传。如果失败 (TypeError)，就只传 (*args, **kwargs)
                        # 但是 bind 会抛出 TypeError 如果不匹配

                        try:
                            sig.bind(self.log_signal.emit, *self.args, **self.kwargs)
                            pass_log_cb = True
                        except TypeError:
                            pass_log_cb = False

                    if pass_log_cb:
                        result = self.func(self.log_signal.emit, *self.args, **self.kwargs)
                    else:
                        result = self.func(*self.args, **self.kwargs)
                except Exception:
                    # 如果 inspect 失败（比如 C-extensions），回退到旧行为或直接调用
                    # 但为了不破坏旧代码，我们可以尝试 catch TypeError
                     try:
                        result = self.func(self.log_signal.emit, *self.args, **self.kwargs)
                     except TypeError:
                        result = self.func(*self.args, **self.kwargs)

            self.result_signal.emit(result)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.log_signal.emit(f"执行异常: {e}")
            self.result_signal.emit(None)
        finally:
            self.finished.emit()
