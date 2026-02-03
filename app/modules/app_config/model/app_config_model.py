"""
@FileName：app_config_model.py
@Description：
@Author：QinHao
@Time：2025/12/18 14:41
@Department：PTV_AT
"""

from app.core.base_model import BaseModel
from app.core.dependency_injection import di_container
from app.services.configuration.config_service import AppConfigurationService


class AppConfigModel(BaseModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._config_service = di_container.resolve(AppConfigurationService)
        if not self._config_service:
            self._config_service = AppConfigurationService()
            di_container.register_singleton(AppConfigurationService, self._config_service)

    @property
    def doip_settings(self):
        return self._config_service.doip_settings

    @doip_settings.setter
    def doip_settings(self, value):
        self._config_service.doip_settings = value
        self.dataChanged.emit()

    @property
    def diag_layer_settings(self):
        return self._config_service.diag_layer_settings

    @diag_layer_settings.setter
    def diag_layer_settings(self, value):
        self._config_service.diag_layer_settings = value
        self.dataChanged.emit()

    @property
    def someip_settings(self):
        return self._config_service.someip_settings

    @someip_settings.setter
    def someip_settings(self, value):
        self._config_service.someip_settings = value
        self.dataChanged.emit()

    @property
    def domain_update_settings(self):
        return self._config_service.domain_update_settings

    @domain_update_settings.setter
    def domain_update_settings(self, value):
        self._config_service.domain_update_settings = value
        self.dataChanged.emit()

    @property
    def app_log_settings(self):
        return self._config_service.app_log_settings

    @app_log_settings.setter
    def app_log_settings(self, value):
        self._config_service.app_log_settings = value
        self.dataChanged.emit()

    def save_doip_settings(self, settings):
        self.doip_settings = settings

    def save_diag_layer_settings(self, settings):
        self.diag_layer_settings = settings

    def save_someip_settings(self, settings):
        self.someip_settings = settings

    def save_domain_update_settings(self, settings):
        self.domain_update_settings = settings

    def save_app_log_settings(self, settings):
        self.app_log_settings = settings

    def reset_doip_defaults(self):
        self.doip_settings = {
            "protocol_version": 0,
            "logical_addr": "0x0E80",
            "routing_type": "0x00",
            "routing_request": True,
            "network_interface": 0,
            "target_phy_addr": "0x004F",
            "target_fun_addr": "0x07DF",
            "target_addr_mode": 1,
            "dpt_file": ""
        }

    def reset_diag_layer_settings(self):
        self.diag_layer_settings = {
            "s3_client_time": "3000",
            "s3_server_time": "5000",
            "dll_path": "",
            "physical_addr": "0x004F",
            "functional_addr": "0x07DF",
            "ecu_config_path": "",
            "target_ecu_name": "",
            "diag_addr_mode": 1
        }

    def reset_someip_defaults(self):
        self.someip_settings = {
            "local_ip": ""
        }

    def reset_domain_update_settings(self):
        self.domain_update_settings = {
            "success_delay": "20",
            "failure_delay": "20",
            "ecu_reset": False,
            "stop_on_failure": False
        }

    def reset_app_log_settings(self):
        self.app_log_settings = {
            "export_path": "",
            "export_module": "All Modules"
        }
