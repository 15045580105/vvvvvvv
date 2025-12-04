import sys

from PyQt5 import QtWidgets, QtCore

from app.common.utils.license_manager import is_activated
from app.presentation.controller.main_window_controller import MainController



if __name__ == "__main__":
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling)
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps)
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("车载诊断工具")
    app.setOrganizationName("Automotive Diagnostics")
    app.setApplicationDisplayName("车载诊断工具平台 v1.0")

    # 如未激活，则在主界面上方弹出激活窗口
    if not is_activated():
        from app.modules.login.view.login_view import LoginDialog

        dialog = LoginDialog()
        # 阻塞，直到用户处理激活
        if dialog.exec_() != LoginDialog.Accepted:
            # 用户未完成激活，直接退出整个应用
            sys.exit(0)

    controller = MainController()
    main_view = controller.get_view()
    main_view.showMaximized()

    sys.exit(app.exec_())