from PyQt5 import QtWidgets


class BaseView(QtWidgets.QWidget):
    """Base view class. Subclasses should implement setup_ui()."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        pass

    def show_message(self, message, type="info"):
        """显示消息提示框"""
        if type == "info":
            QtWidgets.QMessageBox.information(self, "提示", message)
        elif type == "warning":
            QtWidgets.QMessageBox.warning(self, "警告", message)
        elif type == "error":
            QtWidgets.QMessageBox.critical(self, "错误", message)
        elif type == "success":
            QtWidgets.QMessageBox.information(self, "成功", message)
        else:
            QtWidgets.QMessageBox.information(self, "提示", message)

    def show_confirm(self, message):
        """显示确认对话框"""
        reply = QtWidgets.QMessageBox.question(
            self, "确认", message,
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )
        return reply == QtWidgets.QMessageBox.Yes
