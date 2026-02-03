from PyQt5 import QtCore

from app.core.base_controller import BaseController
from app.core.dependency_injection import di_container
from app.modules.log_config.model.log_config_model import LogConfigModel
from app.modules.log_config.view.log_config_view import LogConfigView
from app.services.configuration.log_config_service import LogConfigService
from app.services.device_manage.device_service import DeviceService


class LogConfigController(BaseController):
    def __init__(self, parent=None):
        self.model = LogConfigModel(parent)
        self.view = LogConfigView(parent)
        super().__init__(self.model, self.view, parent)

        self.log_config_service = di_container.resolve(LogConfigService)
        if not self.log_config_service:
            self.log_config_service = LogConfigService()
            di_container.register_singleton(LogConfigService, self.log_config_service)

        # 尝试注入 DeviceService
        device_service = di_container.resolve(DeviceService)
        if device_service:
            self.log_config_service.inject_device_service(device_service)

        self._workers = []

        self._bind_signals()
        self.on_model_changed()

    def _bind_signals(self):
        # ECU Config
        self.view.ecu_execute_btn.clicked.connect(self._on_ecu_execute)

        # App Config - Filter
        self.view.app_search_btn.clicked.connect(self._on_app_search)
        self.view.app_refresh_btn.clicked.connect(self._on_app_refresh)

        # App Config - Pagination
        self.view.prev_page_btn.clicked.connect(self._on_prev_page)
        self.view.next_page_btn.clicked.connect(self._on_next_page)
        self.view.page_size_combo.currentTextChanged.connect(self._on_page_size_changed)

        # App Config - Log Operations
        self.view.export_logs_btn.clicked.connect(self._on_export_logs)
        self.view.delete_selected_btn.clicked.connect(self._on_delete_selected)
        self.view.refresh_logs_btn.clicked.connect(self._on_refresh_logs)

        # Restore Config
        self.view.restore_btn.clicked.connect(self._on_restore_config)

        # Modify App Config
        self.view.modify_requested.connect(self._on_modify_requested)

        # Import Map File
        self.view.import_map_btn.clicked.connect(self._on_import_map)

    def _on_import_map(self):
        from PyQt5 import QtWidgets
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self.view, "选择日志配置文件", "", "JSON Files (*.json);;All Files (*)"
        )
        if file_path:
            self.view.map_path_edit.setText(file_path)
            self.log_config_service.set_map_file_path(file_path)
            self.view.show_message(f"已加载配置文件: {file_path}", "success")
            # 如果 APP tab 需要依赖此文件刷新，可以在这里调用刷新
            # self._on_app_refresh()

    def _on_ecu_execute(self):
        selected_ecus = self.view.ecu_select_combo.currentSelection()
        log_level = self.view.ecu_log_level_combo.currentText()
        if not selected_ecus:
            # 使用 Toast 提示而不是弹窗
            from app.common.ui.modern_widgets import MessageToast
            MessageToast(self.view).show_toast("请选择至少一个ECU", 1)
            return

        # 检查设备是否连接
        if not self.log_config_service._device_service or not self.log_config_service._device_service.get_doip_client():
             self.view.show_message("设备未连接 (DoIP)，无法执行配置", "error")
             return

        # 使用 Worker 在后台线程执行，避免阻塞 UI
        from app.common.utils.worker import Worker
        def task(log_callback):
            return self.log_config_service.set_ecu_log_level(selected_ecus, log_level, log_callback)

        worker = Worker(task)
        # 连接日志信号到 View 的 append_log
        worker.log_signal.connect(self.view.append_log)

        def on_finished(success):
            if success:
                self.view.show_message(f"已设置 {selected_ecus} 日志等级为 {log_level}", "success")
            else:
                self.view.show_message("设置失败，请检查日志", "error")

        worker.result_signal.connect(on_finished)
        worker.start()
        # Keep reference to avoid GC
        self._workers.append(worker)
        worker.finished.connect(lambda: self._workers.remove(worker) if worker in self._workers else None)

    def _on_app_search(self):
        ecu_id = self.view.app_filter_ecu_combo.currentText()
        app_id = self.view.app_filter_appid_combo.currentText()
        log_level = self.view.app_filter_loglevel_combo.currentText()

        apps = self.log_config_service.get_apps(ecu_id, app_id, log_level)
        # Update model
        self.model.apps = [
            (app["app_id"], app["ecu_id"], app["log_level"], app["file_no"], app["file_size"], app["total_size"])
            for app in apps
        ]
        self.on_model_changed()

    def _on_app_refresh(self):
        self._on_app_search()

    def _on_prev_page(self):
        print("Previous Page")
        # TODO: Update pagination

    def _on_next_page(self):
        print("Next Page")
        # TODO: Update pagination

    def _on_page_size_changed(self, text):
        print(f"Page Size Changed: {text}")
        # TODO: Update pagination size

    def _on_export_logs(self):
        selected_rows = []
        for i in range(self.view.app_table.rowCount()):
            item = self.view.app_table.item(i, 0)
            if item.checkState() == QtCore.Qt.CheckState.Checked:
                selected_rows.append(i)

        if not selected_rows:
            self.view.show_message("请先选择要导出的日志", "warning")
            return

        app_ids = [self.model.apps[i][0] for i in selected_rows]
        # TODO: Open file dialog to get destination
        destination = "logs_export"

        success = self.log_config_service.export_logs(app_ids, destination)
        if success:
             self.view.show_message("日志导出成功", "success")

    def _on_delete_selected(self):
        selected_rows = []
        for i in range(self.view.app_table.rowCount()):
            item = self.view.app_table.item(i, 0)
            if item.checkState() == QtCore.Qt.CheckState.Checked:
                selected_rows.append(i)

        if not selected_rows:
            self.view.show_message("请先选择要删除的日志", "warning")
            return

        app_ids = [self.model.apps[i][0] for i in selected_rows]

        if self.view.show_confirm(f"确定要删除选中的 {len(app_ids)} 个日志吗？"):
            success = self.log_config_service.delete_logs(app_ids)
            if success:
                self.view.show_message("日志删除成功", "success")
                self._on_app_refresh()

    def _on_refresh_logs(self):
        self._on_app_refresh()

    def _on_restore_config(self):
        restore_ccua = self.view.restore_ccua.isChecked()
        restore_ccu0 = self.view.restore_ccu0.isChecked()
        restore_ccu1 = self.view.restore_ccu1.isChecked()
        delete_logs = self.view.delete_logs.isChecked()

        options = {
            "restore_ccua": restore_ccua,
            "restore_ccu0": restore_ccu0,
            "restore_ccu1": restore_ccu1,
            "delete_logs": delete_logs
        }

        if not any(options.values()):
             # 使用 Toast 提示
             from app.common.ui.modern_widgets import MessageToast
             MessageToast(self.view).show_toast("请选择至少一项恢复操作", 1) # 1 for Info/Warning like usage here, or 2 for Warning
             return

        # 检查设备连接 (DoIP 检查)
        if not self.log_config_service._device_service or not self.log_config_service._device_service.get_doip_client():
             self.view.show_message("设备未连接 (DoIP)，无法执行操作", "error")
             return
        msg = ""

        if delete_logs:
            # 优先提示删除日志的不可逆性
            msg = "确定要删除所有 DLT 日志文件吗？\n若删除文件将无法恢复。"

            others = []
            if restore_ccua: others.append("恢复 CCUA 默认配置")
            if restore_ccu0: others.append("恢复 CCU0 默认配置")
            if restore_ccu1: others.append("恢复 CCU1 默认配置")

            if others:
                msg += "\n\n同时执行以下操作:\n" + "\n".join([f"- {o}" for o in others])

        elif restore_ccua:
            msg = "恢复 CCUA 默认配置和修改process_log_configs？"

            others = []
            if restore_ccu0: others.append("恢复 CCU0 默认配置")
            if restore_ccu1: others.append("恢复 CCU1 默认配置")

            if others:
                msg += "\n\n其他操作:\n" + "\n".join([f"- {o}" for o in others])

        else:
            msg = "确定要执行以下操作吗？\n"
            if restore_ccu0: msg += "- 恢复 CCU0 默认配置\n"
            if restore_ccu1: msg += "- 恢复 CCU1 默认配置\n"

        if self.view.show_confirm(msg):
             from app.common.utils.worker import Worker
             # 删除日志需要 SSH
             if delete_logs:
                 ssh_client = self.log_config_service._device_service.get_ssh_client()
                 if not ssh_client or not ssh_client.is_connected():
                     self.view.show_message("设备未连接 (SSH)，无法执行删除日志操作", "error")
                     return
             # 定义任务函数
             def task(log_callback):
                 return self.log_config_service.restore_config(options, log_callback)

             worker = Worker(task)
             worker.log_signal.connect(self.view.append_log)

             def on_finished(result):
                 if hasattr(result, "get") and result.get("success", False): # Use safe access if result could be None or bool
                     if result.get("restart_required", False):
                         if self.view.show_confirm("CCUA 默认配置恢复完成，需要重启 CCU 才能生效。\n是否立即重启 CCU？"):
                             # 启动新的 worker 执行重启
                             self._perform_ccu_reset()

                     self.view.show_message("操作执行完成", "success")
                 elif isinstance(result, bool) and result:
                      self.view.show_message("操作执行完成", "success")
                 else:
                     self.view.show_message("部分操作执行失败，请查看日志", "error")

             worker.result_signal.connect(on_finished)
             worker.start()

             self._workers.append(worker)
             worker.finished.connect(lambda: self._workers.remove(worker) if worker in self._workers else None)

    def _perform_ccu_reset(self):
        from app.common.utils.worker import Worker
        def reset_task(log_callback):
            return self.log_config_service.reset_ccu(log_callback)

        worker = Worker(reset_task)
        worker.log_signal.connect(self.view.append_log)
        worker.start()
        self._workers.append(worker)
        worker.finished.connect(lambda: self._workers.remove(worker) if worker in self._workers else None)

    def _on_modify_requested(self, row_index):
        app_info = self.model.apps[row_index]
        app_id = app_info[0]
        print(f"Modify requested for row {row_index}, App: {app_id}")
        # TODO: Show dialog to modify app config

    def on_model_changed(self):
        self.view.populate(self.model.apps)

    def get_view(self):
        return self.view
