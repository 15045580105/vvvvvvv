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

def get_logs_path():
    path = os.path.join(get_app_data_path(), "logs")
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)
    return path

