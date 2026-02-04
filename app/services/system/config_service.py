import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List

from app.core.base_service import BaseService


class ConfigService(BaseService):
    """简单的 JSON 配置读写服务，用于保存设备列表等数据。

    这里只做最小实现：
    - 约定一个应用配置根目录
    - 提供读/写 JSON 文件的通用方法
    """

    def __init__(self, app_name: str = "oneboxforgac") -> None:
        super().__init__()
        self._app_name = app_name
        self._config_root = self._resolve_config_root()
        self._config_root.mkdir(parents=True, exist_ok=True)

    # ----------------- 路径相关 -----------------
    def _resolve_config_root(self) -> Path:
        """解析应用配置根目录。

        Windows 下默认放在用户目录的 .appname 子目录下：
          C:/Users/<user>/.oneboxforgac/
        """
        home = Path(os.path.expanduser("~"))
        return home / f".{self._app_name}"

    def get_config_path(self, name: str) -> Path:
        """获取某个配置文件的完整路径（自动补 .json 后缀）。"""
        if not name.endswith(".json"):
            name = f"{name}.json"
        return self._config_root / name

    # ----------------- JSON 读写 -----------------
    def load_json(self, name: str, default: Any = None) -> Any:
        path = self.get_config_path(name)
        if not path.exists():
            return default

        # 增加重试机制，防止文件锁竞争
        for i in range(5):
            try:
                with path.open("r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                if i == 4:  # 最后一次尝试失败
                    print(f"[ConfigService] Load failed for {name}: {e}")
                    return default
                time.sleep(0.2)
        return default

    def save_json(self, name: str, data: Any) -> None:
        path = self.get_config_path(name)

        # Safe serialize check
        try:
             json_str = json.dumps(data, ensure_ascii=False, indent=2)
        except Exception as e:
             print(f"[ConfigService] Serialization failed: {e}")
             # If serialization fails, DO NOT touch the file.
             return

        # 增加重试机制
        for i in range(5):
            try:
                # Use atomic write pattern: write to temp file, then rename
                temp_path = path.with_suffix('.tmp')
                with temp_path.open("w", encoding="utf-8") as f:
                    f.write(json_str)
                    f.flush()
                    os.fsync(f.fileno())

                # Atomic rename
                if path.exists():
                     path.unlink()
                temp_path.rename(path)
                return
            except Exception as e:
                if i == 4:
                    print(f"[ConfigService] Save failed for {name}: {e}")
                time.sleep(0.2)

    # ----------------- 设备专用封装 -----------------
    def load_devices(self) -> List[Dict[str, Any]]:
        """从设备配置文件中加载设备列表。"""
        data = self.load_json("devices", default=[])
        if isinstance(data, list):
            return data
        return []

    def save_devices(self, devices: List[Dict[str, Any]]) -> None:
        """将设备列表保存到配置文件。"""
        self.save_json("devices", devices)
