import os
import sys

def get_app_data_path():
    """
    Get the application data directory.
    Windows: %LOCALAPPDATA%\Automotive Diagnostics\OneBoxForGAC
    Others: ~/.oneboxforgac
    """
    if sys.platform == "win32":
        app_data = os.getenv("LOCALAPPDATA")
        if not app_data:
            app_data = os.path.join(os.path.expanduser("~"), "AppData", "Local")
        base_path = os.path.join(app_data, "Automotive Diagnostics", "OneBoxForGAC")
    else:
        base_path = os.path.join(os.path.expanduser("~"), ".oneboxforgac")

    if not os.path.exists(base_path):
        try:
            os.makedirs(base_path)
        except Exception:
            # Fallback to current directory if permission denied
            base_path = os.path.join(os.getcwd())

    return base_path


def get_device_config_path():
    """
    Get the directory for device configuration files like devices.json and common_config_settings.json.
    Path: ...\OneBoxForGAC\DeviceConfig
    """
    path = os.path.join(get_app_data_path(), "DeviceConfig")
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)
    return path


def get_app_config_path():
    """
    Get the directory for application configuration files like license.json.
    Path: ...\OneBoxForGAC\APP
    """
    path = os.path.join(get_app_data_path(), "APP")
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)
    return path


def get_logs_path():
    path = os.path.join(get_app_data_path(), "logs")
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)
    return path


def get_performance_export_path():
    """
    Get the directory for performance export files.
    Path: .../OneBoxForGAC/Performance
    """
    path = os.path.join(get_app_data_path(), "Performance")
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)
    return path
