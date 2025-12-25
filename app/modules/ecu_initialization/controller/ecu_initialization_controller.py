import configparser
from PyQt5 import QtCore, QtWidgets
from app.core.base_controller import BaseController
from app.modules.ecu_initialization.model.ecu_initialization_model import ECUInitModel
from app.modules.ecu_initialization.view.ecu_initialization_view import ECUInitView

class ECUInitController(BaseController):
    def __init__(self, parent=None, view=None):
        self.model = ECUInitModel()
        self.view = view if view else ECUInitView(parent)
        super().__init__(self.model, self.view, parent)

        # Connect view signals
        self.view.file_selected.connect(self.on_file_selected)
        self.view.init_requested.connect(self.on_init_requested)

    def on_file_selected(self, file_path: str):
        """Handle file selection: parse INI and populate MTOC dropdown."""
        try:
            config = configparser.ConfigParser()
            config.optionxform = str # Preserve case

            # Handle potential encoding issues
            try:
                config.read(file_path, encoding='utf-8-sig')
            except UnicodeDecodeError:
                config.read(file_path, encoding='gbk')

            # Extract all unique keys (MTOCs) from all sections
            # Assuming MTOCs are the keys in the INI file sections
            mtocs = set()
            for section in config.sections():
                for key in config[section]:
                    mtocs.add(key)

            sorted_mtocs = sorted(list(mtocs))
            self.view.set_mtoc_items(sorted_mtocs)

        except Exception as e:
            QtWidgets.QMessageBox.warning(self.view, "解析错误", f"无法解析配置文件: {str(e)}")

    def on_init_requested(self):
        """Handle init button click."""
        mtoc = self.view.get_selected_mtoc()
        if not mtoc:
            QtWidgets.QMessageBox.warning(self.view, "提示", "请先选择 MTOC")
            return

        # Start initialization process (mock for now)
        # In a real scenario, this would involve communication with the ECU
        self.view.set_progress(0)

        # Mock progress
        self._progress = 0
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._update_progress)
        self._timer.start(50)

    def _update_progress(self):
        self._progress += 2
        self.view.set_progress(self._progress)
        if self._progress >= 100:
            self._timer.stop()
            QtWidgets.QMessageBox.information(self.view, "完成", "初始化完成")
