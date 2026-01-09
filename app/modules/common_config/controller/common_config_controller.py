from PyQt5 import QtWidgets
from app.core.base_controller import BaseController
from app.core.dependency_injection import di_container
from app.modules.common_config.view.common_config_view import CommonConfigView
from app.modules.common_config.model.common_config_model import CommonConfigModel
from app.services.configuration.common_config_service import CommonConfigService
from app.services.device_manage.device_service import DeviceService
from app.common.utils.worker import Worker

class CommonConfigController(BaseController):
    def __init__(self, parent=None):
        # 即使传入了 parent (MainView)，我们也应该创建自己的 CommonConfigView
        view = CommonConfigView(parent)
        model = CommonConfigModel()
        super().__init__(model, view)

        self.common_config_service = di_container.resolve(CommonConfigService)
        if not self.common_config_service:
            self.common_config_service = CommonConfigService()
            di_container.register_singleton(CommonConfigService, self.common_config_service)

        # 尝试注入 DeviceService
        device_service = di_container.resolve(DeviceService)
        if device_service:
            self.common_config_service.inject_device_service(device_service)

        self._workers = []
        self._bind_signals()
        self._init_data()

    def _bind_signals(self):
        # 绑定表格按钮点击事件等
        # 由于表格按钮是动态生成的，我们需要在生成时绑定，或者使用代理
        # 这里我们假设 View 提供了一个信号或者我们直接操作 View 的组件
        self.view.import_json_btn.clicked.connect(self._on_import_json)
        self.view.prev_page_btn.clicked.connect(self._on_prev_page)
        self.view.next_page_btn.clicked.connect(self._on_next_page)

        if hasattr(self.view, 'page_size_combo'):
            self.view.page_size_combo.currentTextChanged.connect(self._on_page_size_changed)

        # 绑定常用例程相关信号
        self.view.routine_import_btn.clicked.connect(self._on_import_routine_json)
        self.view.routine_prev_page_btn.clicked.connect(self._on_routine_prev_page)
        self.view.routine_next_page_btn.clicked.connect(self._on_routine_next_page)
        self.view.routine_page_size_combo.currentTextChanged.connect(self._on_routine_page_size_changed)

    def _init_data(self):
        # 1. 初始化常用 $2E 服务配置
        self.services_2e = []
        last_config_path = self.common_config_service.get_last_2e_config_path()

        if last_config_path:
            # 尝试加载上次保存的配置
            loaded_services = self.common_config_service.load_2e_config(last_config_path)
            if loaded_services:
                self.services_2e = loaded_services
                self.view.json_path_edit.setText(last_config_path)
                self.view.append_param_log(f"已自动加载上次配置: {last_config_path}")
            else:
                self.view.append_param_log(f"无法加载上次配置: {last_config_path}")

        self.current_page = 1
        try:
            if hasattr(self.view, 'page_size_combo'):
                self.page_size = int(self.view.page_size_combo.currentText())
            else:
                self.page_size = 10
        except ValueError:
            self.page_size = 10

        self._update_2e_view()

        # 2. 初始化常用 $31/$2F 例程配置
        self.services_routine = []
        last_routine_path = self.common_config_service.get_last_routine_config_path()

        if last_routine_path:
            loaded_routines = self.common_config_service.load_routine_config(last_routine_path)
            if loaded_routines:
                self.services_routine = loaded_routines
                self.view.routine_json_path_edit.setText(last_routine_path)
                self.view.append_routine_log(f"已自动加载上次例程配置: {last_routine_path}")
            else:
                self.view.append_routine_log(f"无法加载上次例程配置: {last_routine_path}")

        self.routine_current_page = 1
        try:
            self.routine_page_size = int(self.view.routine_page_size_combo.currentText())
        except ValueError:
            self.routine_page_size = 10

        self._update_routine_view()

    def _on_import_json(self):
        """导入 JSON 配置文件"""
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self.view, "选择配置文件", "", "JSON Files (*.json)"
        )
        if file_path:
            self.view.json_path_edit.setText(file_path)
            self.services_2e = self.common_config_service.load_2e_config(file_path)

            # 保存路径
            self.common_config_service.save_last_2e_config_path(file_path)

            self.current_page = 1
            self._update_2e_view()
            self.view.show_message(f"成功加载 {len(self.services_2e)} 条配置", "success")

    def _update_2e_view(self):
        """更新 2E 服务视图（含分页）"""
        total_items = len(self.services_2e)
        total_pages = (total_items + self.page_size - 1) // self.page_size if total_items > 0 else 1

        # Ensure current page is valid
        if self.current_page > total_pages: self.current_page = total_pages
        if self.current_page < 1: self.current_page = 1

        start_idx = (self.current_page - 1) * self.page_size
        end_idx = min(start_idx + self.page_size, total_items)

        current_services = self.services_2e[start_idx:end_idx]

        self.view.update_2e_table(current_services, self._on_execute_2e, self._on_custom_execute_2e)
        self.view.set_page_info(self.current_page, total_pages, total_items)

        # 更新按钮状态
        self.view.prev_page_btn.setEnabled(self.current_page > 1)
        self.view.next_page_btn.setEnabled(self.current_page < total_pages)

    def _on_prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self._update_2e_view()

    def _on_next_page(self):
        total_items = len(self.services_2e)
        total_pages = (total_items + self.page_size - 1) // self.page_size
        if self.current_page < total_pages:
            self.current_page += 1
            self._update_2e_view()

    def _on_execute_2e(self, service_info, row_index):
        """执行配置的 2E 服务"""
        def task(log_callback):
            # 获取当前用户输入的值
            # 注意：service_info 是引用，View 中的控件更新会直接修改 service_info 中的 paramObject_val 和 paramState_val
            return self.common_config_service.execute_2e_service(service_info, log_callback)

        worker = Worker(task)
        # 使用 append_param_log
        worker.log_signal.connect(self.view.append_param_log)

        def on_finished(success):
            status = "执行成功" if success else "执行失败"
            self.view.update_2e_status(row_index, status, success)

            # 更新最后读取时间
            import datetime
            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.view.set_last_read_time(now_str)

        worker.result_signal.connect(on_finished)
        worker.start()
        self._workers.append(worker)
        worker.finished.connect(lambda: self._workers.remove(worker) if worker in self._workers else None)

    def _on_custom_execute_2e(self, command_hex, row_index):
        """执行自定义 2E 请求"""
        if not command_hex:
            self.view.show_message("请输入指令", "warning")
            return

        service_info = {"command": command_hex, "serviceId": "custom", "paramObject_val": command_hex}
        self._on_execute_2e(service_info, row_index)

    def _on_execute_routine(self, service_info, row_index):
        """执行 31&2F 请求"""
        def task(log_callback):
             # 提取 paramObject_val 和 paramState_val
            param_obj_val = service_info.get("paramObject_val", "---")
            param_state_val = service_info.get("paramState_val", "---")

            # 调用 service 执行
            return self.common_config_service.execute_routine_v2(service_info, param_obj_val, param_state_val, log_callback)

        worker = Worker(task)
        # 使用 append_routine_log
        worker.log_signal.connect(self.view.append_routine_log)

        def on_finished(success):
            status = "执行成功" if success else "执行失败"
            self.view.update_routine_status(row_index, status, success)

            # 更新最后读取时间
            import datetime
            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.view.set_routine_last_read_time(now_str)


        worker.result_signal.connect(on_finished)
        worker.start()
        self._workers.append(worker)
        worker.finished.connect(lambda: self._workers.remove(worker) if worker in self._workers else None)

    def _on_page_size_changed(self, text):
        try:
            self.page_size = int(text)
            self.current_page = 1 # Reset to first page
            self._update_2e_view()
        except ValueError:
            pass

    def _on_import_routine_json(self):
        """导入常用例程 JSON 配置文件"""
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self.view, "选择配置文件", "", "JSON Files (*.json)"
        )
        if file_path:
            self.view.routine_json_path_edit.setText(file_path)
            self.services_routine = self.common_config_service.load_routine_config(file_path)

            # 保存路径
            self.common_config_service.save_last_routine_config_path(file_path)

            self.routine_current_page = 1
            self._update_routine_view()
            self.view.show_message(f"成功加载 {len(self.services_routine)} 条例程配置", "success")

    def _update_routine_view(self):
        """更新常用例程视图（含分页）"""
        total_items = len(self.services_routine)
        total_pages = (total_items + self.routine_page_size - 1) // self.routine_page_size if total_items > 0 else 1

        if self.routine_current_page > total_pages: self.routine_current_page = total_pages
        if self.routine_current_page < 1: self.routine_current_page = 1

        start_idx = (self.routine_current_page - 1) * self.routine_page_size
        end_idx = min(start_idx + self.routine_page_size, total_items)

        current_services = self.services_routine[start_idx:end_idx]

        self.view.update_routine_table(current_services, self._on_execute_routine_service)
        self.view.set_routine_page_info(self.routine_current_page, total_pages, total_items)

        self.view.routine_prev_page_btn.setEnabled(self.routine_current_page > 1)
        self.view.routine_next_page_btn.setEnabled(self.routine_current_page < total_pages)

    def _on_routine_prev_page(self):
        if self.routine_current_page > 1:
            self.routine_current_page -= 1
            self._update_routine_view()

    def _on_routine_next_page(self):
        total_items = len(self.services_routine)
        total_pages = (total_items + self.routine_page_size - 1) // self.routine_page_size
        if self.routine_current_page < total_pages:
            self.routine_current_page += 1
            self._update_routine_view()

    def _on_routine_page_size_changed(self, text):
        try:
            self.routine_page_size = int(text)
            self.routine_current_page = 1
            self._update_routine_view()
        except ValueError:
            pass

    def _on_execute_routine_service(self, service_info, row_index):
        """执行常用例程服务"""
        def task(log_callback):
            return self.common_config_service.execute_routine_service(service_info, log_callback)

        worker = Worker(task)
        worker.log_signal.connect(self.view.append_routine_log)

        def on_finished(success):
            status = "执行成功" if success else "执行失败"
            self.view.update_routine_status(row_index, status, success)

            # 更新最后读取时间
            import datetime
            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.view.set_routine_last_read_time(now_str)

        worker.result_signal.connect(on_finished)
        worker.start()
        self._workers.append(worker)
        worker.finished.connect(lambda: self._workers.remove(worker) if worker in self._workers else None)

    def on_view_init(self):
        # Initialize view data
        pass

    def get_view(self):
        return self.view
