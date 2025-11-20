import logging
import os
from datetime import datetime

def setup_logger(name='gac_tool'):
    """设置日志记录器"""

    # 创建logs目录
    log_dir = 'logs'
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # 日志文件名（按日期）
    log_file = os.path.join(log_dir, f'{datetime.now().strftime("%Y%m%d")}.log')

    # 创建logger
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # 避免重复添加handler
    if not logger.handlers:
        # 文件handler
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.INFO)

        # 控制台handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)

        # 格式化器
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)

        # 添加handler
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

    return logger