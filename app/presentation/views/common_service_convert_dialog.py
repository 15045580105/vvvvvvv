import os
from PyQt5 import QtCore, QtGui, QtWidgets
from app.common.utils.common_service_excel_loader import convert_common_service_excel
from app.common.utils.worker import Worker


POINTING_HAND_CURSOR = (
    QtCore.Qt.CursorShape.PointingHandCursor
    if hasattr(QtCore.Qt, "CursorShape")
    else getattr(QtCore.Qt, "PointingHandCursor", 13)
)


DIALOG_STYLE = """
QDialog {
    background-color: #F9FAFB;
}
QLabel#title {
    font-size: 18px;
    font-weight: bold;
    color: #111827;
    margin-bottom: 5px;
}
QLabel#subtitle {
    font-size: 13px;
    color: #6B7280;
    margin-bottom: 15px;
}
QGroupBox {
    border: 1px solid #E5E7EB;
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 20px;
    background-color: #FFFFFF;
    font-weight: 600;
    color: #374151;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 5px;
    background-color: transparent;
}
QLineEdit {
    border: 1px solid #D1D5DB;
    border-radius: 6px;
    padding: 8px 10px;
    background-color: #F9FAFB;
    color: #1F2937;
    selection-background-color: #3B82F6;
}
QLineEdit:focus {
    border: 1px solid #3B82F6;
    background-color: #FFFFFF;
}
QPushButton {
    padding: 8px 16px;
    border-radius: 6px;
    font-weight: 600;
    font-size: 13px;
}
QPushButton#browse {
    background-color: #FFFFFF;
    color: #374151;
    border: 1px solid #D1D5DB;
}
QPushButton#browse:hover {
    background-color: #F3F4F6;
    border-color: #9CA3AF;
}
QPushButton#primary {
    background-color: #3B82F6;
    color: white;
    border: none;
}
QPushButton#primary:hover {
    background-color: #2563EB;
}
QPushButton#primary:disabled {
    background-color: #93C5FD;
}
QPushButton#secondary {
    background-color: #FFFFFF;
    color: #4B5563;
    border: 1px solid #E5E7EB;
}
QPushButton#secondary:hover {
    background-color: #F9FAFB;
    border-color: #D1D5DB;
}
"""


def run_conversion_task(log_callback, input_path, output_dir, output_filename):
    """后台执行 Excel -> JSON 转换，供 GUI 对话框异步调用。"""
    # GUI 与 CLI 最终都会收敛到同一个转换器：
    # `common_service_excel_loader.convert_common_service_excel(...)`。
    # 因此无论从按钮触发还是命令行触发，输出 schema 都应保持一致。
    log_callback("正在解析常用服务 Excel 文件...")
    output_path = convert_common_service_excel(input_path, output_dir, output_filename)
    log_callback("常用服务 JSON 已生成")
    return output_path


class CommonServiceConvertDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("常用服务文件转换")
        self.setMinimumWidth(640)
        self.resize(700, 460)
        self.setStyleSheet(DIALOG_STYLE)
        self._worker = None
        self._init_ui()

    def _init_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(25, 25, 25, 25)

        header_layout = QtWidgets.QVBoxLayout()
        header_layout.setSpacing(4)
        title_label = QtWidgets.QLabel("常用服务文件转换")
        title_label.setObjectName("title")
        header_layout.addWidget(title_label)
        main_layout.addLayout(header_layout)

        file_group = QtWidgets.QGroupBox("输入文件 (Input Source)")
        file_layout = QtWidgets.QHBoxLayout(file_group)
        file_layout.setContentsMargins(15, 15, 15, 15)
        file_layout.setSpacing(10)

        self.file_path_edit = QtWidgets.QLineEdit()
        self.file_path_edit.setPlaceholderText("请选择 Excel 文件 (.xlsx)")
        self.file_path_edit.setReadOnly(True)
        self.file_path_edit.setMinimumHeight(36)

        self.file_btn = QtWidgets.QPushButton("📂 选择文件")
        self.file_btn.setObjectName("browse")
        self.file_btn.setMinimumHeight(36)
        self.file_btn.setCursor(QtGui.QCursor(POINTING_HAND_CURSOR))
        self.file_btn.clicked.connect(self.select_file)

        file_layout.addWidget(self.file_path_edit)
        file_layout.addWidget(self.file_btn)
        main_layout.addWidget(file_group)

        output_group = QtWidgets.QGroupBox("输出配置 (Output Destination)")
        output_layout = QtWidgets.QGridLayout(output_group)
        output_layout.setContentsMargins(15, 15, 15, 15)
        output_layout.setHorizontalSpacing(10)
        output_layout.setVerticalSpacing(10)

        self.out_path_edit = QtWidgets.QLineEdit()
        self.out_path_edit.setPlaceholderText("请选择输出文件夹")
        self.out_path_edit.setReadOnly(True)
        self.out_path_edit.setMinimumHeight(36)

        self.out_btn = QtWidgets.QPushButton("📂 选择文件夹")
        self.out_btn.setObjectName("browse")
        self.out_btn.setMinimumHeight(36)
        self.out_btn.setCursor(QtGui.QCursor(POINTING_HAND_CURSOR))
        self.out_btn.clicked.connect(self.select_output_dir)

        self.filename_edit = QtWidgets.QLineEdit("common_service_config.json")
        self.filename_edit.setMinimumHeight(36)

        output_layout.addWidget(QtWidgets.QLabel("输出目录"), 0, 0)
        output_layout.addWidget(self.out_path_edit, 0, 1)
        output_layout.addWidget(self.out_btn, 0, 2)
        output_layout.addWidget(QtWidgets.QLabel("输出文件名"), 1, 0)
        output_layout.addWidget(self.filename_edit, 1, 1, 1, 2)
        main_layout.addWidget(output_group)

        main_layout.addStretch()

        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.HLine)
        line.setFrameShadow(QtWidgets.QFrame.Sunken)
        line.setStyleSheet("background-color: #E5E7EB; border: none; max-height: 1px;")
        main_layout.addWidget(line)

        button_layout = QtWidgets.QHBoxLayout()
        button_layout.setSpacing(12)

        self.status_label = QtWidgets.QLabel("")
        self.status_label.setStyleSheet("color: #6B7280; font-size: 9pt;")
        button_layout.addWidget(self.status_label)
        button_layout.addStretch()

        self.close_btn = QtWidgets.QPushButton("关闭")
        self.close_btn.setObjectName("secondary")
        self.close_btn.setMinimumHeight(38)
        self.close_btn.setMinimumWidth(100)
        self.close_btn.clicked.connect(self.close)

        self.convert_btn = QtWidgets.QPushButton("🚀 开始转换")
        self.convert_btn.setObjectName("primary")
        self.convert_btn.setMinimumHeight(38)
        self.convert_btn.setMinimumWidth(140)
        self.convert_btn.clicked.connect(self.start_conversion)

        button_layout.addWidget(self.close_btn)
        button_layout.addWidget(self.convert_btn)
        main_layout.addLayout(button_layout)

    def select_file(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "选择 Excel 文件", "", "Excel Files (*.xlsx)")
        if path:
            self.file_path_edit.setText(path)
            if not self.out_path_edit.text():
                self.out_path_edit.setText(os.path.dirname(path))
            self.status_label.setText("就绪")

    def select_output_dir(self):
        path = QtWidgets.QFileDialog.getExistingDirectory(self, "选择输出文件夹")
        if path:
            self.out_path_edit.setText(path)

    def start_conversion(self):
        """收集用户输入，并启动 Excel -> JSON 转换任务。"""
        # 对话框本身不理解业务字段，只负责收集路径并启动后台任务；
        # 真正的表头识别、行合并、schema 精简都在 loader 里完成。
        input_path = self.file_path_edit.text().strip()
        output_dir = self.out_path_edit.text().strip()
        output_filename = self.filename_edit.text().strip() or "common_service_config.json"

        if not input_path or not os.path.exists(input_path):
            QtWidgets.QMessageBox.warning(self, "错误", "请输入有效的 Excel 文件路径")
            return

        if not output_dir or not os.path.exists(output_dir):
            QtWidgets.QMessageBox.warning(self, "错误", "请输入有效的输出文件夹路径")
            return

        if not output_filename.lower().endswith(".json"):
            QtWidgets.QMessageBox.warning(self, "错误", "输出文件名必须以 .json 结尾")
            return

        self.convert_btn.setEnabled(False)
        self.convert_btn.setText("⏳ 转换中...")
        self.status_label.setText("准备开始...")

        self._worker = Worker(run_conversion_task, input_path, output_dir, output_filename)
        self._worker.log_signal.connect(self.status_label.setText)
        self._worker.result_signal.connect(self.on_conversion_finished)
        self._worker.start()

    def on_conversion_finished(self, result):
        self.convert_btn.setEnabled(True)
        self.convert_btn.setText("🚀 开始转换")

        if result:
            self.status_label.setText("✅ 转换完成")
            QtWidgets.QMessageBox.information(self, "成功", f"转换成功！\n文件已保存至: {result}")
        else:
            self.status_label.setText("❌ 转换失败")
            QtWidgets.QMessageBox.critical(self, "错误", "转换失败，请检查 Excel 格式是否满足转换要求。")



