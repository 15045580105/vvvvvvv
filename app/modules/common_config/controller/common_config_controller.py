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
        self._device_service = di_container.resolve(DeviceService)
        if self._device_service:
            self.common_config_service.inject_device_service(self._device_service)

        self._workers = []
        self._bind_signals()
        self._init_data()

    def _bind_signals(self):
        self.view.import_json_btn.clicked.connect(self._on_import_json)
        self.view.prev_page_btn.clicked.connect(self._on_prev_page)
        self.view.next_page_btn.clicked.connect(self._on_next_page)

        if hasattr(self.view, 'page_size_combo'):
            self.view.page_size_combo.currentTextChanged.connect(self._on_page_size_changed)

        self.view.routine_prev_page_btn.clicked.connect(self._on_routine_prev_page)
        self.view.routine_next_page_btn.clicked.connect(self._on_routine_next_page)
        self.view.routine_page_size_combo.currentTextChanged.connect(self._on_routine_page_size_changed)

    def _init_data(self):
        self.services_2e = []
        self.current_page = 1
        try:
            if hasattr(self.view, 'page_size_combo'):
                self.page_size = int(self.view.page_size_combo.currentText())
            else:
                self.page_size = 10
        except ValueError:
            self.page_size = 10

        self.services_routine = []
        self.routine_current_page = 1
        try:
            self.routine_page_size = int(self.view.routine_page_size_combo.currentText())
        except ValueError:
            self.routine_page_size = 10

        shared_config_path = self.common_config_service.get_config_path("COMMON")
        if shared_config_path:
            if self._load_shared_config(shared_config_path, auto_load=True):
                return
            self.view.append_param_log(f"无法加载上次配置: {shared_config_path}")
            self.view.append_routine_log(f"无法加载上次配置: {shared_config_path}")

        self._update_2e_view()
        self._update_routine_view()

    def _on_import_json(self):
        """导入统一 JSON 配置文件，并同时刷新两个标签页。"""
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self.view, "选择配置文件", "", "JSON Files (*.json)"
        )
        if file_path:
            if self._load_shared_config(file_path):
                self.view.show_message(
                    f"成功加载 $2E: {len(self.services_2e)} 条，$31/$2F: {len(self.services_routine)} 条配置",
                    "success",
                )
            else:
                self.view.show_message("配置文件中未找到可用的常用服务定义", "warning")

    def _load_shared_config(self, file_path: str, auto_load: bool = False) -> bool:
        """加载统一 JSON 配置，并把两类服务分别灌入两个表格。

        这是 JSON -> 界面渲染 的 controller 入口：
        - service 层负责解析/标准化 JSON
        - controller 负责保存结果、处理分页并通知 view 刷新
        """
        services_2e, services_routine = self.common_config_service.load_shared_config(file_path)
        self.services_2e = services_2e
        self.services_routine = services_routine
        self.view.config_path_input.setText(file_path)
        self.common_config_service.save_config_path("COMMON", file_path)

        self.current_page = 1
        self.routine_current_page = 1
        self._update_2e_view()
        self._update_routine_view()

        if auto_load and (services_2e or services_routine):
            self.view.append_param_log(f"已自动加载上次配置: {file_path}")
            self.view.append_routine_log(f"已自动加载上次配置: {file_path}")

        return bool(services_2e or services_routine)

    def _update_2e_view(self):
        """更新 `$2E` 服务视图（含分页）。

        `services_2e` 已经是标准化后的运行期数据，
        view 会直接读取其中的 `paramObject/paramState/...` 配置创建控件。
        """
        total_items = len(self.services_2e)
        total_pages = (total_items + self.page_size - 1) // self.page_size if total_items > 0 else 1

        # Ensure current page is valid
        if self.current_page > total_pages: self.current_page = total_pages
        if self.current_page < 1: self.current_page = 1

        start_idx = (self.current_page - 1) * self.page_size
        end_idx = min(start_idx + self.page_size, total_items)

        current_services = self.services_2e[start_idx:end_idx]

        self.view.update_2e_table(current_services, self._on_execute_2e)
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
        # 检查参数
        param_obj_val = service_info.get("paramObject_val", "---")
        param_state_val = service_info.get("paramState_val", "---")

        # 更宽松的校验：只要对象或状态有一个是有效的即可尝试执行
        # 若两者都是无效值 (---, /, "") 则拦截
        invalid_values = ["---", "", "/", "N/A"]

        is_obj_invalid = param_obj_val in invalid_values or (isinstance(param_obj_val, list) and not param_obj_val)
        is_state_invalid = param_state_val in invalid_values

        if is_obj_invalid and is_state_invalid:
            self.view.show_message("先选择参数对象或参数状态", "warning")
            return

        # 临时连接信号到 param_log (注意：并发执行可能导致日志混淆，但在单用户界面操作下通常可接受)
        try:
            self.common_config_service.log_signal.disconnect()
        except Exception:
            pass
        self.common_config_service.log_signal.connect(self.view.append_param_log)

        def task():
            # 获取当前用户输入的值
            # 注意：service_info 是引用，View 中的控件更新会直接回写
            # `paramObject_val` / `paramState_val`，这里直接拿最新值去拼 UDS。
            try:
                return self.common_config_service.execute_2e_service(service_info)
            except TypeError as e:
                # 重新抛出非调用签名的 TypeError，防止 Worker 误判
                import traceback
                traceback.print_exc()
                raise Exception(f"TypeError inside task: {e}") from e

        worker = Worker(task)
        worker.log_signal.connect(self.view.append_param_log)

        self.view.set_button_status(self.view.param_table, row_index, "executing")

        def on_finished(success):
            if not self._device_service or not self._device_service.get_doip_client():
                 self.view.show_message("设备未连接 (DoIP)", "error")
                 self.view.set_button_status(self.view.param_table, row_index, "failed")
                 return

            # 处理成功与否
            if not success:
                 self.view.set_button_status(self.view.param_table, row_index, "failed")
                 return

            # 这里假设有个验证步骤，实际情况根据服务定义调整
            verify_success = True # self.common_config_service.verify_service_output(service_info)

            if not verify_success:
                 self.view.set_button_status(self.view.param_table, row_index, "failed")
                 return

            self.view.set_button_status(self.view.param_table, row_index, "success")

            # 更新最后读取时间
            import datetime
            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.view.set_last_read_time(now_str)

        worker.result_signal.connect(on_finished)
        worker.start()
        self._workers.append(worker)
        worker.finished.connect(lambda: self._workers.remove(worker) if worker in self._workers else None)


    def _on_execute_routine(self, service_info, row_index):
        """执行 31&2F 请求"""

        # 临时连接信号到 routine_log
        try:
            self.common_config_service.log_signal.disconnect()
        except Exception:
            pass
        self.common_config_service.log_signal.connect(self.view.append_routine_log)

        self.view.set_button_status(self.view.routine_table, row_index, "executing")

        def task():
             # 提取 paramObject_val 和 paramState_val
            param_obj_val = service_info.get("paramObject_val", "---")
            param_state_val = service_info.get("paramState_val", "---")

            # 调用 service 执行 (移除 log_callback)
            return self.common_config_service.execute_routine_v2(service_info, param_obj_val, param_state_val, service_info.get("routineControlType_val", "---"))

        worker = Worker(task)
        worker.log_signal.connect(self.view.append_routine_log)

        def on_finished(success):
            self.view.update_routine_status(row_index, "执行成功" if success else "执行失败", success)
            if success:
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


    def _update_routine_view(self):
        """更新 `$31/$2F` 服务视图（含分页）。

        例程页相比 `$2E` 多了 `routineControlType` 控件，
        view 在渲染后还会根据控制类型联动禁用/启用对象与状态选择器。
        """
        total_items = len(self.services_routine)
        total_pages = (total_items + self.routine_page_size - 1) // self.routine_page_size if total_items > 0 else 1

        if self.routine_current_page > total_pages:
            self.routine_current_page = max(1, total_pages)

        start_idx = (self.routine_current_page - 1) * self.routine_page_size
        end_idx = min(start_idx + self.routine_page_size, total_items)

        current_services = self.services_routine[start_idx:end_idx]

        # 把当前页的数据交给 view；view 会为每行创建下拉框/输入框/执行按钮，
        # 并把用户选择直接写回每个 service dict。
        self.view.update_routine_table(current_services, self._on_execute_routine_service)
        # self.view.set_routine_page_info(self.routine_current_page, total_pages, total_items)
        if hasattr(self.view, 'set_routine_page_info'):
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
        """执行 31&2F 请求 (闭包适配)"""
        try:
            self.common_config_service.log_signal.disconnect()
        except Exception:
            pass
        self.common_config_service.log_signal.connect(self.view.append_routine_log)

        self.view.set_button_status(self.view.routine_table, row_index, "executing")

        def task():
            return self.common_config_service.execute_routine_service(service_info)

        worker = Worker(task)
        worker.log_signal.connect(self.view.append_routine_log)

        def on_finished(success):
            self.view.update_routine_status(row_index, "执行成功" if success else "执行失败", success)
            if success:
                import datetime
                now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.view.set_routine_last_read_time(now_str)

        worker.result_signal.connect(on_finished)
        worker.start()
        self._workers.append(worker)
