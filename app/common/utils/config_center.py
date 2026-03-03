import os
import json
import logging

logger = logging.getLogger(__name__)

class ConfigCenter:
    """Manages global configuration file config_center.json"""

    FILE_NAME = "config_center.json"

    @staticmethod
    def _get_config_path():
        # Directory logic as per requirements
        base_dir = r"C:\Users\uidq9000\AppData\Local\Automotive Diagnostics\OneBoxForGAC\DeviceConfig"
        if not os.path.exists(base_dir):
            try:
                os.makedirs(base_dir)
            except Exception as e:
                logger.error(f"Failed to create config directory: {e}")
                return None
        return os.path.join(base_dir, ConfigCenter.FILE_NAME)

    @staticmethod
    def load_config() -> dict:
        path = ConfigCenter._get_config_path()
        if not path or not os.path.exists(path):
            return {}
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load config_center.json: {e}")
            return {}

    @staticmethod
    def save_config(data: dict):
        path = ConfigCenter._get_config_path()
        if not path:
            return
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save config_center.json: {e}")

    @staticmethod
    def get_log_map_path():
        config = ConfigCenter.load_config()
        return config.get("log_config_map_path", "")

    @staticmethod
    def set_log_map_path(path: str):
        config = ConfigCenter.load_config()
        config["log_config_map_path"] = path
        ConfigCenter.save_config(config)
