import ctypes
import sys
import os

from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtGui import QIcon

from app.common.log.app_log import SystemLog
from app.common.utils.license_manager import is_activated
from app.presentation.controller.main_window_controller import MainController



if __name__ == "__main__":
    # 启用高DPI缩放支持 (High DPI Scaling)
    # 1. 开启自动屏幕缩放因子
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"

    # 2. 设置DPI缩放舍入策略为 PassThrough (Qt 5.14+)
    #    这能解决 125%, 150% 缩放被强制进位到 200% 导致界面过大的问题
    if hasattr(QtCore.Qt, 'HighDpiScaleFactorRoundingPolicy'):
        QtWidgets.QApplication.setHighDpiScaleFactorRoundingPolicy(
            QtCore.Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    SystemLog().initialize()

    # 3. 启用高DPI缩放属性
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling)
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps)

    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("myappid")
    app = QtWidgets.QApplication(sys.argv)

    # 设置全局默认字体 (Global Font)
    font = QtGui.QFont("Segoe UI", 9)
    font.setHintingPreference(QtGui.QFont.PreferFullHinting)
    app.setFont(font)

    app.setApplicationName("车载诊断工具")
    app.setOrganizationName("Automotive Diagnostics")
    app.setApplicationDisplayName("车载诊断工具平台 v1.0")

    # 设置应用和任务栏图标（更健壮的查找：尝试多个常见位置并回退到仓库搜索）
    project_root = os.path.dirname(__file__)
    icon_path = os.path.join(project_root, 'resources', 'images', 'vcc_logo.png')
    # 备用位置（实际项目中图标位于 app/resources/images）
    if not os.path.exists(icon_path):
        alt = os.path.join(project_root, 'app', 'resources', 'images', 'vcc_logo.png')
        if os.path.exists(alt):
            icon_path = alt
        else:
            # 在仓库中搜索第一个匹配的文件
            for root, dirs, files in os.walk(project_root):
                if 'vcc_logo.png' in files:
                    icon_path = os.path.join(root, 'vcc_logo.png')
                    break
    try:
        if os.path.exists(icon_path):
            app.setWindowIcon(QIcon(icon_path))
    except Exception:
        # 如果路径无效或图标无法加载，则忽略，应用仍可正常启动
        pass

    # 如未激活，则在主界面上方弹出激活窗口
    if not is_activated():
        from app.modules.login.view.login_view import LoginDialog

        dialog = LoginDialog()
        # 阻塞，直到用户处理激活
        if dialog.exec_() != LoginDialog.Accepted:
            # 用户未完成激活，直接退出整个应用
            sys.exit(0)

    controller = MainController()

    # 注册应用退出时的清理回调
    app.aboutToQuit.connect(controller.on_close)

    main_view = controller.get_view()
    # 确保主窗口也显示相同图标（部分平台需要在窗口上设置）
    try:
        if os.path.exists(icon_path):
            main_view.setWindowIcon(QIcon(icon_path))
    except Exception:
        pass

    main_view.showMaximized()

    sys.exit(app.exec_())