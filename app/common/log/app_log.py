"""
@FileName：app_log.py
@Description：
@Author：QinHao
@Time：2026/1/16 12:03
@Department：PTV_AT
"""

import logging
import os
import sys
from logging.handlers import TimedRotatingFileHandler

class SystemLog:
    """
    系统级日志封装类 (Singleton)
    负责初始化日志配置，包括文件输出（带轮转）和控制台输出
    """
    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(SystemLog, cls).__new__(cls)
        return cls._instance

    def initialize(self, log_dir=None, log_name="oneboxforgac.log", level=logging.INFO):
        """
        初始化日志系统
        :param log_dir: 日志存放目录。如果不传(None)，将自动保存到系统用户的AppPath下(如Windows的AppData/Local)
        :param log_name: 主日志文件名
        :param level: 日志级别
        """
        if self._initialized:
            return

        if log_dir:
            # 如果指定了路径
            if os.path.isabs(log_dir):
                log_dir_path = log_dir
            else:
                # 如果是相对路径，则相对于项目根目录
                current_file_dir = os.path.dirname(os.path.abspath(__file__))
                project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_file_dir)))
                log_dir_path = os.path.join(project_root, log_dir)
        else:
            # 未指定路径，使用系统标准位置
            if sys.platform == "win32":
                # Windows: C:\Users\<User>\AppData\Local\Automotive Diagnostics\OneBoxForGAC\logs
                # 使用 LOCALAPPDATA 环境变量
                app_data = os.getenv("LOCALAPPDATA")
                if not app_data:
                     app_data = os.path.join(os.path.expanduser("~"), "AppData", "Local")

                log_dir_path = os.path.join(app_data, "Automotive Diagnostics", "OneBoxForGAC", "logs")
            else:
                # Linux/Mac: ~/.oneboxforgac/logs
                log_dir_path = os.path.join(os.path.expanduser("~"), ".oneboxforgac", "logs")

        if not os.path.exists(log_dir_path):
            try:
                os.makedirs(log_dir_path)
            except Exception as e:
                print(f"Failed to create log directory: {e}")
                # Fallback to current dir if system dir fails
                log_dir_path = os.path.join(os.getcwd(), 'logs')
                os.makedirs(log_dir_path, exist_ok=True)

        log_file_path = os.path.join(log_dir_path, log_name)

        # 配置 Root Logger
        root_logger = logging.getLogger()
        root_logger.setLevel(level)

        # 清除已有的handlers，避免重复打印
        if root_logger.hasHandlers():
            root_logger.handlers.clear()

        # 日志格式
        formatter = logging.Formatter(
            fmt='[%(asctime)s] [%(levelname)s] [%(threadName)s] [%(filename)s:%(lineno)d] - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # 1. 滚动文件 Handler (按天滚动)
        try:
            file_handler = TimedRotatingFileHandler(
                filename=log_file_path,
                when='MIDNIGHT',
                interval=1,
                backupCount=30,  # 保留30天
                encoding='utf-8',
                delay=False
            )
            file_handler.setFormatter(formatter)
            file_handler.setLevel(level)
            file_handler.suffix = "%Y-%m-%d.log"
            root_logger.addHandler(file_handler)
        except Exception as e:
            print(f"Failed to setup file logging: {e}")

        # 2. 控制台 Handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        console_handler.setLevel(level)
        root_logger.addHandler(console_handler)

        self._initialized = True
        #logging.info(f"System logging initialized. Log file: {log_file_path}")

# module level helpers
def get_logger(name: str) -> logging.Logger:
    """
    获取Logger实例. 如果系统日志未初始化，会尝试使用默认配置初始化.
    """
    if not SystemLog()._initialized:
        SystemLog().initialize()
    return logging.getLogger(name)

if __name__ == '__main__':
    # 测试代码
    log = get_logger("TestLogger")
    log.info("This is an info message")
    log.error("This is an error message")
