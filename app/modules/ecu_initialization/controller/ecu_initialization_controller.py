import configparser
import re
from PyQt5 import QtWidgets
from app.core.base_controller import BaseController
from app.modules.ecu_initialization.model.ecu_initialization_model import ECUInitModel
from app.modules.ecu_initialization.view.ecu_initialization_view import ECUInitView
from app.core.dependency_injection import di_container
from app.services.device_manage.device_service import DeviceService

class ECUInitController(BaseController):
    def __init__(self, parent=None, view=None):
        self.model = ECUInitModel()
        self.view = view if view else ECUInitView(parent)
        super().__init__(self.model, self.view, parent)

        self.device_service = di_container.resolve(DeviceService)
        if not self.device_service:
             self.device_service = DeviceService()
             di_container.register_singleton(DeviceService, self.device_service)

        self.ini_data = {} # Stores parsed INI data: {section: {key: value}}
        self.ecu_map = {} # Stores mapping from ECU name to list of sections: {ecu_name: [section_name1, ...]}

        # Connect view signals
        self.view.file_selected.connect(self.on_file_selected)
        self.view.init_requested.connect(self.on_init_requested)

    def on_file_selected(self, file_path: str):
        """Handle file selection: parse INI and populate MTOC dropdown and ECU list."""
        try:
            config = configparser.ConfigParser()
            config.optionxform = str # Preserve case

            # Handle potential encoding issues
            try:
                config.read(file_path, encoding='utf-8-sig')
            except UnicodeDecodeError:
                config.read(file_path, encoding='gbk')

            self.ini_data = {}
            self.ecu_map = {}
            mtocs = set()

            # Regex to parse section name: extract ECU name and DID
            # Assumes format: Prefix_ECUName_didDID or similar, ending with _didXXXX
            # We treat everything before _did as the ECU identifier.
            section_pattern = re.compile(r'^(.*)_[dD][iI][dD]([0-9A-Fa-f]+)$')

            sections = config.sections()
            if not sections:
                QtWidgets.QMessageBox.warning(self.view, "提示", "配置文件为空或格式不正确")
                return

            # 1. Get MTOCs from the first section to preserve order
            first_section = sections[0]
            # configparser preserves order of keys in sections
            mtocs = list(config[first_section].keys())

            # 2. Parse all sections to find ECUs
            for section in sections:
                self.ini_data[section] = dict(config[section])

                # Parse section name for ECU
                match = section_pattern.match(section)
                if match:
                    ecu_name = match.group(1)
                    if ecu_name not in self.ecu_map:
                        self.ecu_map[ecu_name] = []
                    self.ecu_map[ecu_name].append(section)

            # Update View
            # MTOCs are already ordered by file appearance
            self.view.set_mtoc_items(mtocs)

            # ECUs sorted alphabetically for better UX
            sorted_ecus = sorted(list(self.ecu_map.keys()))
            self.view.set_ecu_items(sorted_ecus)

            # Default select all ECUs
            self.view.select_all_ecus()

        except Exception as e:
            QtWidgets.QMessageBox.warning(self.view, "解析错误", f"无法解析配置文件: {str(e)}")

    def on_init_requested(self):
        """Handle init button click."""
        mtoc = self.view.get_selected_mtoc()
        selected_ecus = self.view.get_selected_ecus()

        if not mtoc:
            QtWidgets.QMessageBox.warning(self.view, "提示", "请先选择 MTOC")
            return

        if not selected_ecus:
            QtWidgets.QMessageBox.warning(self.view, "提示", "请至少选择一个 ECU")
            return

        if not self.device_service:
             QtWidgets.QMessageBox.warning(self.view, "错误", "无法获取设备服务")
             return

        # Check if connected
        doip_client = self.device_service.get_doip_client()
        if not doip_client:
             QtWidgets.QMessageBox.warning(self.view, "提示", "设备未连接 (DoIP)")
             return

        # Collect tasks
        tasks = []
        section_pattern = re.compile(r'^(.*)_[dD][iI][dD]([0-9A-Fa-f]+)$')

        for ecu in selected_ecus:
            if ecu in self.ecu_map:
                for section in self.ecu_map[ecu]:
                    match = section_pattern.match(section)
                    if match:
                        did_str = match.group(2)

                        # Get value for MTOC
                        if section in self.ini_data and mtoc in self.ini_data[section]:
                            value = self.ini_data[section][mtoc]
                            # Check if value is valid (not the "skip" message)
                            if "该ECU不写配置码" not in value:
                                tasks.append({
                                    'ecu': ecu,
                                    'did': did_str,
                                    'value': value,
                                    'section': section
                                })

        if not tasks:
            QtWidgets.QMessageBox.information(self.view, "提示", "当前选择没有需要写入的配置")
            return

        self.view.set_progress(0)
        total_tasks = len(tasks)
        success_count = 0
        fail_count = 0

        # Execute tasks in a separate thread or just loop here (blocking UI for now, but simple)
        # For better UX, we should use a thread, but user asked for simple "call send".
        # We will use processEvents to keep UI responsive.

        for i, task in enumerate(tasks):
            did_hex_str = task['did']
            value_hex_str = task['value']

            try:
                # Construct UDS Write Data By Identifier (0x2E)
                # DID is 2 bytes
                did_bytes = bytes.fromhex(did_hex_str)
                if len(did_bytes) != 2:
                     # Try padding if needed, or assume it's correct
                     pass

                data_bytes = bytes.fromhex(value_hex_str)

                payload = b'\x2E' + did_bytes + data_bytes

                # Send request
                # Using send_doip_payload from DeviceService
                response = self.device_service.send_doip_payload(payload, timeout=2.0)

                # Check positive response: 0x6E + DID
                if response and response[0] == 0x6E:
                    success_count += 1
                    # self.view.log(f"写入成功: {task['section']} -> DID {did_hex_str}")
                else:
                    fail_count += 1
                    # self.view.log(f"写入失败: {task['section']} -> DID {did_hex_str}")

            except Exception as e:
                fail_count += 1
                print(f"Error writing {task['section']}: {e}")

            # Update progress
            progress = int((i + 1) / total_tasks * 100)
            self.view.set_progress(progress)
            QtWidgets.QApplication.processEvents()

        QtWidgets.QMessageBox.information(self.view, "完成", f"初始化完成\n成功: {success_count}\n失败: {fail_count}")

    def _update_progress(self):
        # ...existing code...
        pass
