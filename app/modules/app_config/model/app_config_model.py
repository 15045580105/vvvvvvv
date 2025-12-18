"""
@FileName：app_config_model.py
@Description：
@Author：QinHao
@Time：2025/12/18 14:41
@Department：PTV_AT
"""

from app.core.base_model import BaseModel


class AppConfigModel(BaseModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._doip_settings = {
            "protocol_version": 0,
            "logical_addr": "0x0E80",
            "routing_type": "0x00",
            "routing_request": True,
            "network_interface": 0,
            "tcp_use_any": False,
            "udp_broadcast": False,
            "physical_addr": "0x004F",
            "functional_addr": "0x07DF"
        }
        self._diag_layer_settings = {
            "s3_client_time": "3000",
            "s3_server_time": "5000",
            "dll_path": "D:/GAC客户提供/GAC_CCU_SA.dll"
        }
        self._domain_update_settings = {
            "success_delay": "20",
            "failure_delay": "20",
            "ecu_reset": False,
            "stop_on_failure": False
        }
        self._app_log_settings = {
            "export_path": "",
            "export_module": "All Modules"
        }

    @property
    def doip_settings(self):
        return self._doip_settings

    @doip_settings.setter
    def doip_settings(self, value):
        self._doip_settings = value
        self.dataChanged.emit()

    @property
    def diag_layer_settings(self):
        return self._diag_layer_settings

    @diag_layer_settings.setter
    def diag_layer_settings(self, value):
        self._diag_layer_settings = value
        self.dataChanged.emit()

    @property
    def domain_update_settings(self):
        return self._domain_update_settings

    @domain_update_settings.setter
    def domain_update_settings(self, value):
        self._domain_update_settings = value
        self.dataChanged.emit()

    @property
    def app_log_settings(self):
        return self._app_log_settings

    @app_log_settings.setter
    def app_log_settings(self, value):
        self._app_log_settings = value
        self.dataChanged.emit()

    def save_doip_settings(self, settings):
        self.doip_settings = settings
        # TODO: Persist to file or database

    def save_diag_layer_settings(self, settings):
        self.diag_layer_settings = settings
        # TODO: Persist to file or database

    def save_domain_update_settings(self, settings):
        self.domain_update_settings = settings
        # TODO: Persist to file or database

    def save_app_log_settings(self, settings):
        self.app_log_settings = settings
        # TODO: Persist to file or database

    def reset_doip_defaults(self):
        self.doip_settings = {
            "protocol_version": 0,
            "logical_addr": "0x0E80",
            "routing_type": "0x00",
            "routing_request": True,
            "network_interface": 0,
            "tcp_use_any": False,
            "udp_broadcast": False,
            "physical_addr": "0x004F",
            "functional_addr": "0x07DF"
        }

    def reset_diag_layer_defaults(self):
        self.diag_layer_settings = {
            "s3_client_time": "3000",
            "s3_server_time": "5000",
            "dll_path": "D:/GAC客户提供/GAC_CCU_SA.dll"
        }

    def reset_domain_update_defaults(self):
        self.domain_update_settings = {
            "success_delay": "20",
            "failure_delay": "20",
            "ecu_reset": False,
            "stop_on_failure": False
        }

    def reset_app_log_defaults(self):
        self.app_log_settings = {
            "export_path": "",
            "export_module": "All Modules"
        }
