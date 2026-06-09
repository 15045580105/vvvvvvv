import ctypes
import ctypes.wintypes
import sys
import os

from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtGui import QIcon


ERROR_ALREADY_EXISTS = 183
MUTEX_NAME = "Global\\VCC_AutomotiveDiagnostics_SingleInstance"
APP_USER_MODEL_ID = "AutomotiveDiagnostics.VCC.1.0"


def acquire_single_instance_mutex():
    """Return a process-wide mutex handle, or None when another VCC is running."""
    if os.name != "nt":
        return True
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    kernel32.CreateMutexW.restype = ctypes.wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [ctypes.wintypes.HANDLE]
    kernel32.CloseHandle.restype = ctypes.c_bool
    handle = kernel32.CreateMutexW(None, True, MUTEX_NAME)
    if not handle:
        return None
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        return None
    return handle


def release_single_instance_mutex(handle):
    if os.name != "nt" or handle in (None, True):
        return
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.ReleaseMutex.argtypes = [ctypes.wintypes.HANDLE]
    kernel32.ReleaseMutex.restype = ctypes.c_bool
    kernel32.CloseHandle.argtypes = [ctypes.wintypes.HANDLE]
    kernel32.CloseHandle.restype = ctypes.c_bool
    kernel32.ReleaseMutex(handle)
    kernel32.CloseHandle(handle)

if __name__ == "__main__":
    single_instance_mutex = acquire_single_instance_mutex()
    if not single_instance_mutex:
        sys.exit(0)

    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"

    if hasattr(QtCore.Qt, 'HighDpiScaleFactorRoundingPolicy'):
        QtWidgets.QApplication.setHighDpiScaleFactorRoundingPolicy(
            QtCore.Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    # 3. 启用高DPI缩放属性
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling)
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps)

    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
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
    controller = None
    try:
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
                splash.close()
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

        exit_code = app.exec_()
        sys.exit(exit_code)
    except Exception:
        splash.close()
        raise
    finally:
        release_single_instance_mutex(single_instance_mutex)
