from typing import Any, Dict
from app.core.base_service import BaseService
from app.services.system.config_service import ConfigService as SystemConfigService

class AppConfigurationService(BaseService):
    def __init__(self):
        super().__init__()
        # Use SystemConfigService to handle file I/O
        self._system_config_service = SystemConfigService()
        self._config_name = "app_settings"
        self._settings = self._load_settings()

    def _load_settings(self) -> Dict[str, Any]:
        defaults = self._get_default_settings()
        loaded = self._system_config_service.load_json(self._config_name, default=defaults)
        # Merge defaults to ensure all keys exist
        return self._merge_defaults(loaded, defaults)

    def _merge_defaults(self, loaded: Dict, defaults: Dict) -> Dict:
        for key, value in defaults.items():
            if key not in loaded:
                loaded[key] = value
            elif isinstance(value, dict) and isinstance(loaded[key], dict):
                self._merge_defaults(loaded[key], value)
        return loaded

    def _get_default_settings(self):
        return {
            "doip": {
                "protocol_version": 0,
                "logical_addr": "0x0E80",
                "routing_type": "0x00",
                "routing_request": True,
                "network_interface": 0,
                "tcp_use_any": False,
                "udp_broadcast": False
            },
            "diag_layer": {
                "s3_client_time": "3000",
                "s3_server_time": "5000",
                "dll_path": "",
                "physical_addr": "0x004F",
                "functional_addr": "0x07DF",
                "ecu_config_path": ""
            },
            "domain_update": {
                "success_delay": "20",
                "failure_delay": "20",
                "ecu_reset": False,
                "stop_on_failure": False
            },
            "app_log": {
                "export_path": "",
                "export_module": "All Modules"
            }
        }

    def save_settings(self):
        self._system_config_service.save_json(self._config_name, self._settings)

    @property
    def doip_settings(self):
        return self._settings.get("doip", {})

    @doip_settings.setter
    def doip_settings(self, value):
        self._settings["doip"] = value
        self.save_settings()

    @property
    def diag_layer_settings(self):
        return self._settings.get("diag_layer", {})

    @diag_layer_settings.setter
    def diag_layer_settings(self, value):
        self._settings["diag_layer"] = value
        self.save_settings()

    @property
    def domain_update_settings(self):
        return self._settings.get("domain_update", {})

    @domain_update_settings.setter
    def domain_update_settings(self, value):
        self._settings["domain_update"] = value
        self.save_settings()

    @property
    def app_log_settings(self):
        return self._settings.get("app_log", {})

    @app_log_settings.setter
    def app_log_settings(self, value):
        self._settings["app_log"] = value
        self.save_settings()

