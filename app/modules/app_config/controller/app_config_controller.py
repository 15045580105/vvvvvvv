"""
@FileName：app_config_controller.py
@Description：
@Author：QinHao
@Time：2025/12/18 14:41
@Department：PTV_AT
"""
import sys

from PyQt5.QtWidgets import QApplication

from app.core.base_controller import BaseController
from app.modules.app_config.model.app_config_model import AppConfigModel
from app.modules.app_config.view.app_config_view import SettingsWindow


class AppConfigController(BaseController):
    def __init__(self, parent=None):
        self.model = AppConfigModel(parent)
        self.view = SettingsWindow()
        super().__init__(self.model, self.view, parent)

        # Connect view signals to controller slots
        self.view.doip_page.save_signal.connect(self.save_doip_settings)
        self.view.doip_page.reset_signal.connect(self.reset_doip_settings)

        self.view.diag_layer_page.save_signal.connect(self.save_diag_layer_settings)
        self.view.diag_layer_page.reset_signal.connect(self.reset_diag_layer_settings)

        self.view.domain_update_page.save_signal.connect(self.save_domain_update_settings)
        self.view.domain_update_page.reset_signal.connect(self.reset_domain_update_settings)

        self.view.app_log_page.save_signal.connect(self.save_app_log_settings)
        self.view.app_log_page.reset_signal.connect(self.reset_app_log_settings)

        # Initial data load
        self.on_model_changed()

    def on_model_changed(self):
        """Update view when model changes"""
        self.view.doip_page.update_ui(self.model.doip_settings)
        self.view.diag_layer_page.update_ui(self.model.diag_layer_settings)
        self.view.domain_update_page.update_ui(self.model.domain_update_settings)
        self.view.app_log_page.update_ui(self.model.app_log_settings)

    def save_doip_settings(self, settings):
        self.model.save_doip_settings(settings)

    def reset_doip_settings(self):
        self.model.reset_doip_defaults()

    def save_diag_layer_settings(self, settings):
        self.model.save_diag_layer_settings(settings)

    def reset_diag_layer_settings(self):
        self.model.reset_diag_layer_defaults()

    def save_domain_update_settings(self, settings):
        self.model.save_domain_update_settings(settings)

    def reset_domain_update_settings(self):
        self.model.reset_domain_update_defaults()

    def save_app_log_settings(self, settings):
        self.model.save_app_log_settings(settings)

    def reset_app_log_settings(self):
        self.model.reset_app_log_defaults()

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = SettingsWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
