# import sys
# import os
#
# from app.common.utils.logger import setup_logger
# from app.presentation.main_window import MainWindow
# from app.presentation.views.login_view import LoginDialog
#
# # 添加当前目录到Python路径
# sys.path.append(os.path.dirname(os.path.abspath(__file__)))
#
# from PyQt5.QtWidgets import QApplication
# from PyQt5.QtCore import QTimer
#
#
# class GACApplication:
#     """GAC工具主应用程序"""
#
#     def __init__(self):
#         self.app = QApplication(sys.argv)
#         self.logger = setup_logger()
#         self.main_window = None
#
#     def run(self):
#         """运行应用程序"""
#         try:
#             # 显示登录对话框
#             login_dialog = LoginDialog()
#
#             if login_dialog.exec_() == LoginDialog.Accepted:
#                 self.logger.info("用户登录成功")
#
#                 # 创建主窗口
#                 self.main_window = MainWindow()
#                 self.main_window.show()
#
#                 self.logger.info("主窗口创建成功")
#
#                 # 运行应用
#                 return self.app.exec_()
#             else:
#                 self.logger.info("用户取消登录")
#                 return 0
#
#         except Exception as e:
#             self.logger.error(f"应用程序错误: {str(e)}")
#             return 1
#
#
# def main():
#     """主函数"""
#     application = GACApplication()
#     sys.exit(application.run())
#
#
# if __name__ == '__main__':
#     main()
import sys

from PyQt5 import QtWidgets, QtCore

from app.presentation.controller.main_window_controller import MainController

if __name__ == "__main__":
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling)
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps)
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("车载诊断工具")
    app.setOrganizationName("Automotive Diagnostics")
    app.setApplicationDisplayName("车载诊断工具平台 v1.0")
    controller = MainController()
    controller.get_view().show()
    sys.exit(app.exec_())