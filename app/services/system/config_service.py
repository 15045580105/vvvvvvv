import json
import os
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
        try:
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            # 解析失败时返回默认值，避免影响界面
            return default

    def save_json(self, name: str, data: Any) -> None:
        path = self.get_config_path(name)
        try:
            with path.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            # 简单实现：暂不向上抛异常，后续可加日志
            pass

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

