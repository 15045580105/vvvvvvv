"""
@FileName：app_config_controller.py
@Description：
@Author：QinHao
@Time：2025/12/18 14:41
@Department：PTV_AT
"""
import sys
import json
import os
import threading

from PyQt5 import QtCore
from PyQt5.QtWidgets import QApplication

from app.core.base_controller import BaseController
from app.core.dependency_injection import di_container
from app.modules.app_config.model.app_config_model import AppConfigModel
from app.modules.app_config.view.app_config_view import SettingsWindow
from app.services.diagnostic.dpt_service import DPTService


class AppConfigController(BaseController):
    dpt_status_signal = QtCore.pyqtSignal(str, str)
    ecu_config_loaded_signal = QtCore.pyqtSignal(object)

    def __init__(self, parent=None):
        self.model = AppConfigModel(parent)
        self.view = SettingsWindow()
        super().__init__(self.model, self.view, parent)

        # Connect view signals to controller slots
        self.view.doip_page.save_signal.connect(self.save_doip_settings)
        self.view.doip_page.reset_signal.connect(self.reset_doip_settings)

        self.view.someip_page.save_signal.connect(self.save_someip_settings)
        self.view.someip_page.reset_signal.connect(self.reset_someip_settings)

        self.view.diag_layer_page.save_signal.connect(self.save_diag_layer_settings)
        self.view.diag_layer_page.reset_signal.connect(self.reset_diag_layer_settings)
        self.view.diag_layer_page.ecu_file_changed_signal.connect(self.on_ecu_file_changed)

        self.view.domain_update_page.save_signal.connect(self.save_domain_update_settings)
        self.view.domain_update_page.reset_signal.connect(self.reset_domain_update_settings)

        self.view.app_log_page.save_signal.connect(self.save_app_log_settings)
        self.view.app_log_page.reset_signal.connect(self.reset_app_log_settings)

        # Register status callback
        self.dpt_status_signal.connect(self.handle_dpt_status)
        self.ecu_config_loaded_signal.connect(self.on_ecu_config_loaded)

        # Delay heavy initialization
        QtCore.QTimer.singleShot(0, self.delayed_init)

    def delayed_init(self):
        dpt_service = di_container.resolve(DPTService)
        if not dpt_service:
            dpt_service = DPTService()
            di_container.register_singleton(DPTService, dpt_service)
        dpt_service.add_status_callback(self._on_dpt_status)

        # Initial data load
        self.on_model_changed()

    def on_model_changed(self):
        """Update view when model changes"""
        self.view.doip_page.update_ui(self.model.doip_settings)
        self.view.someip_page.load_settings(self.model.someip_settings)

        # Load ECU config if path exists
        ecu_config_path = self.model.diag_layer_settings.get("ecu_config_path")
        if ecu_config_path and os.path.exists(ecu_config_path):
            self.load_ecu_config(ecu_config_path)

        self.view.diag_layer_page.update_ui(self.model.diag_layer_settings)
        self.view.domain_update_page.update_ui(self.model.domain_update_settings)
        self.view.app_log_page.update_ui(self.model.app_log_settings)

    def save_doip_settings(self, settings):
        self.model.save_doip_settings(settings)

        # Reload DPT Service if path changed
        dpt_file = settings.get("dpt_file")
        if dpt_file:
            dpt_service = di_container.resolve(DPTService)
            if not dpt_service:
                dpt_service = DPTService()
                di_container.register_singleton(DPTService, dpt_service)

            try:
                dpt_service.load_from_file(dpt_file, persist=False)
            except Exception as e:
                print(f"Failed to reload DPT file: {e}")

    def reset_doip_settings(self):
        self.model.reset_doip_defaults()

    def save_someip_settings(self, settings):
        self.model.save_someip_settings(settings)

    def reset_someip_settings(self):
        self.model.reset_someip_defaults()

    def save_diag_layer_settings(self, settings):
        self.model.save_diag_layer_settings(settings)

    def reset_diag_layer_settings(self):
        self.model.reset_diag_layer_settings()

    def save_domain_update_settings(self, settings):
        self.model.save_domain_update_settings(settings)

    def reset_domain_update_settings(self):
        self.model.reset_domain_update_settings()

    def save_app_log_settings(self, settings):
        self.model.save_app_log_settings(settings)

    def reset_app_log_settings(self):
        self.model.reset_app_log_settings()

    def on_ecu_file_changed(self, file_path):
        if file_path and os.path.exists(file_path):
            self.load_ecu_config(file_path)
            # Save path to settings
            settings = self.model.diag_layer_settings
            settings["ecu_config_path"] = file_path
            self.model.save_diag_layer_settings(settings)

    def load_ecu_config(self, file_path):
        threading.Thread(target=self._load_ecu_config_worker, args=(file_path,), daemon=True).start()

    def _load_ecu_config_worker(self, file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Validate data format if needed, assuming dict {name: address} or list
                ecu_map = {}
                if isinstance(data, dict):
                    ecu_map = data
                elif isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and "name" in item:
                            # Store full item if possible, or just address
                            # The view expects dict {name: info} or list of dicts
                            # Let's pass the raw data or processed map
                            # If item has 'address', use it. If it has 'physical_addr', use it.
                            ecu_map[item["name"]] = item

                self.ecu_config_loaded_signal.emit(ecu_map)
        except Exception as e:
            print(f"Failed to load ECU config: {e}")
            # Optionally emit an error signal or handle it

    def on_ecu_config_loaded(self, ecu_map):
        self.view.diag_layer_page.update_ecu_combo(ecu_map)

    def _on_dpt_status(self, status, message):
        self.dpt_status_signal.emit(status, message)

    def handle_dpt_status(self, status, message):
        if hasattr(self.view.doip_page, "set_dpt_status"):
            self.view.doip_page.set_dpt_status(status, message)

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = SettingsWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
