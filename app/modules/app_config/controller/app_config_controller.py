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
from app.common.utils.someip_utils import SomeIPMatrixStore


class SomeIPImportWorker(QtCore.QThread):
    progress_signal = QtCore.pyqtSignal(int, str)
    finished_signal = QtCore.pyqtSignal(bool, str, str)

    def __init__(self, file_path: str):
        super().__init__()
        self.file_path = file_path

    def run(self):
        try:
            self.progress_signal.emit(10, "正在检查矩阵文件...")
            if not self.file_path or not os.path.exists(self.file_path):
                raise FileNotFoundError("矩阵文件不存在")

            self.progress_signal.emit(35, "正在解析 Deployment sheet...")
            store = SomeIPMatrixStore()
            result = store.import_matrix(self.file_path, force_reload=True)

            self.progress_signal.emit(85, "正在写入缓存...")
            count = result.get("count", 0)
            self.progress_signal.emit(100, f"导入完成，共解析 {count} 条服务记录")
            self.finished_signal.emit(True, self.file_path, f"导入完成，共解析 {count} 条服务记录")
        except Exception as e:
            self.finished_signal.emit(False, self.file_path, f"导入失败: {e}")


class AppConfigController(BaseController):
    dpt_status_signal = QtCore.pyqtSignal(str, str)
    ecu_config_loaded_signal = QtCore.pyqtSignal(object)
    someip_import_progress_signal = QtCore.pyqtSignal(int, str)
    someip_import_finished_signal = QtCore.pyqtSignal(bool, str, str)

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

        # Connect batch save signals
        self.view.save_started.connect(self.start_batch_save)
        self.view.save_finished.connect(self.finish_batch_save)

        self.view.window_shown.connect(self.on_model_changed)  # Refresh UI on show

        # Register status callback
        self.dpt_status_signal.connect(self.handle_dpt_status)
        self.ecu_config_loaded_signal.connect(self.on_ecu_config_loaded)

        # Delay heavy initialization
        QtCore.QTimer.singleShot(0, self.delayed_init)

        # SomeIP import worker
        self._someip_import_worker = None
        self.view.someip_page.import_matrix_signal.connect(self.import_someip_matrix)
        self.someip_import_progress_signal.connect(self.handle_someip_import_progress)
        self.someip_import_finished_signal.connect(self.handle_someip_import_finished)

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
        # Ensure config service is loaded before updating UI
        self._ensure_config_service()

        # Force reload settings from disk to ensure data consistency
        # This fixes the issue where settings appear lost if they weren't synced to disk properly
        if self.model._config_service:
            self.model._config_service._settings = self.model._config_service._load_settings()

        self.view.doip_page.update_ui(self.model.doip_settings)
        self.view.someip_page.load_settings(self.model.someip_settings)

        # Load ECU config if path exists
        ecu_config_path = self.model.diag_layer_settings.get("ecu_config_path")
        if ecu_config_path and os.path.exists(ecu_config_path):
            self.load_ecu_config(ecu_config_path)

        self.view.diag_layer_page.update_ui(self.model.diag_layer_settings)
        self.view.domain_update_page.update_ui(self.model.domain_update_settings)
        self.view.app_log_page.update_ui(self.model.app_log_settings)
        if hasattr(self.view, "license_page") and hasattr(self.view.license_page, "refresh_license_info"):
            self.view.license_page.refresh_license_info()

    def show_page(self, page_id: str = "doip", focus_target: str | None = None):
        self.on_model_changed()
        if hasattr(self.view, "select_page"):
            self.view.select_page(page_id, focus_target=focus_target)
        self.view.show()
        self.view.raise_()
        self.view.activateWindow()

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

    def start_batch_save(self):
        """Handle start of batch save process"""
        # Enable batch save to ensure atomic file write
        self._ensure_config_service()
        if self.model._config_service:
            self.model._config_service.suspend_save()

    def finish_batch_save(self):
        """Handle end of batch save process"""
        self._ensure_config_service()
        if not self.model._config_service:
            return

        # Persist only once, using the aggregated settings from the view
        pending = getattr(self.view, "_pending_all_settings", None)
        if isinstance(pending, dict) and pending:
            try:
                self.model._config_service.update_all_settings(pending)
                # Reload in-memory settings so other parts of the app can immediately use them
                self.model._config_service.reload()
            except Exception as e:
                print(f"[AppConfigController] Failed to persist settings: {e}")
        else:
            # Fallback: just ensure current in-memory settings are flushed
            self.model._config_service.resume_save()

        # clear
        if hasattr(self.view, "_pending_all_settings"):
            self.view._pending_all_settings = None

    def _ensure_config_service(self):
        """Helper to ensure config service is available"""
        if not self.model._config_service:
            from app.services.configuration.config_service import AppConfigurationService
            self.model._config_service = di_container.resolve(AppConfigurationService)

    def on_ecu_file_changed(self, file_path):
        if file_path and os.path.exists(file_path):
            self.load_ecu_config(file_path)
            # DO NOT save here.
            # If we save here, we overwrite the current model settings with the current state of the model.
            # But the user might have changed other fields (like DLL path) in the UI which haven't been saved to model yet.
            # When the user clicks OK, `save_settings` will be called and will include the ECU path (since the view updates it).

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

    def import_someip_matrix(self, file_path: str):
        if not file_path or (self._someip_import_worker and self._someip_import_worker.isRunning()):
            return

        self.view.set_someip_import_in_progress(True)
        self.view.someip_page.set_import_in_progress(True, "正在导入矩阵...")

        self._someip_import_worker = SomeIPImportWorker(file_path)
        self._someip_import_worker.progress_signal.connect(self.someip_import_progress_signal.emit)
        self._someip_import_worker.finished_signal.connect(self.someip_import_finished_signal.emit)
        self._someip_import_worker.start()

    def handle_someip_import_progress(self, progress: int, message: str):
        self.view.someip_page.update_import_progress(progress, message)

    def handle_someip_import_finished(self, success: bool, file_path: str, message: str):
        self.view.set_someip_import_in_progress(False)
        self.view.someip_page.handle_import_finished(success, message)

        if success:
            settings = dict(self.model.someip_settings or {})
            settings["local_ip"] = self.view.someip_page.network_combo.currentData()
            settings["matrix_file"] = file_path
            self.model.save_someip_settings(settings)
            self.view.someip_page.load_settings(self.model.someip_settings)

        self._someip_import_worker = None

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = SettingsWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
