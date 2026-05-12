import ctypes
import sys
import os

from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtGui import QIcon

if __name__ == "__main__":
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"

    if hasattr(QtCore.Qt, 'HighDpiScaleFactorRoundingPolicy'):
        QtWidgets.QApplication.setHighDpiScaleFactorRoundingPolicy(
            QtCore.Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    # 3. 启用高DPI缩放属性
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling)
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps)

    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("myappid")
    app = QtWidgets.QApplication(sys.argv)

    font = QtGui.QFont("Segoe UI", 9)
    font.setHintingPreference(QtGui.QFont.PreferFullHinting)
    app.setFont(font)

    app.setApplicationName("车载测试工具")
    app.setOrganizationName("Automotive Diagnostics")
    app.setApplicationDisplayName("车载测试平台 v1.0")
    
    project_root = os.path.dirname(__file__)
    icon_path = os.path.join(project_root, 'resources', 'images', 'vcc_logo.png')
    if not os.path.exists(icon_path):
        alt = os.path.join(project_root, 'app', 'resources', 'images', 'vcc_logo.png')
        if os.path.exists(alt):
            icon_path = alt
        else:
            for root, dirs, files in os.walk(project_root):
                if 'vcc_logo.png' in files:
                    icon_path = os.path.join(root, 'vcc_logo.png')
                    break
    try:
        if os.path.exists(icon_path):
            app.setWindowIcon(QIcon(icon_path))
    except Exception:
        pass

    # === 展示加载页面 ===
    from app.presentation.views.splash import SplashScreen
    splash_image_path = os.path.join(project_root, 'app', 'resources', 'images', 'splash.jpg')
    if not os.path.exists(splash_image_path):
        splash_image_path = os.path.join(project_root, 'resources', 'images', 'splash.jpg')
    
    splash = SplashScreen(splash_image_path)
    splash.show()
    app.processEvents()

    # == 延迟导入以加速加载页面显示 ==
    splash.set_progress(10)
    app.processEvents()
    
    from app.common.log.app_log import SystemLog
    
    splash.set_progress(30)
    app.processEvents()
    
    from app.common.utils.license_manager import is_activated
    
    splash.set_progress(50)
    app.processEvents()
    
    from app.presentation.controller.main_window_controller import MainController

    SystemLog().initialize()
    splash.set_progress(60)
    app.processEvents()

    if not is_activated():
        splash.hide()
        from app.modules.login.view.login_view import LoginDialog
        dialog = LoginDialog()
        if dialog.exec_() != LoginDialog.Accepted:
            sys.exit(0)
        splash.show()

    splash.set_progress(75)
    app.processEvents()

    controller = MainController()

    app.aboutToQuit.connect(controller.on_close)

    main_view = controller.get_view()
    
    splash.set_progress(100)
    app.processEvents()
    
    # Wait for the animation to actually reach 100%
    while splash.progress < 100:
        app.processEvents()
        QtCore.QThread.msleep(10)

    try:
        if os.path.exists(icon_path):
            main_view.setWindowIcon(QIcon(icon_path))
    except Exception:
        pass

    main_view.showMaximized()
    splash.finish(main_view) # To hide splash and close

    sys.exit(app.exec_())