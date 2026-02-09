import os
import json
from PyQt5 import QtWidgets, QtCore, QtGui
from app.common.utils.dpt_excel_loader import parse_excel_to_json_structure
from app.common.utils.crypto_utils import dpt_encryptor
from app.common.utils.worker import Worker

def run_conversion_task(log_callback, input_path, output_dir):
    """
    后台转换任务函数
    """
    log_callback("正在解析 Excel 文件...")
    data = parse_excel_to_json_structure(input_path)

    log_callback("正在加密数据...")
    output_file = os.path.join(output_dir, "dpt_config.dat")

    json_str = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    encrypted_bytes = dpt_encryptor.encrypt(json_str)

    with open(output_file, "wb") as f:
        f.write(encrypted_bytes)

    return output_file

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
/* Browse Buttons */
QPushButton#browse {
    background-color: #FFFFFF;
    color: #374151;
    border: 1px solid #D1D5DB;
}
QPushButton#browse:hover {
    background-color: #F3F4F6;
    border-color: #9CA3AF;
}
/* Primary Action Button */
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
/* Secondary Action Button */
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

class DPTConvertDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("DPT文件转换工具")
        self.setMinimumWidth(600)
        self.resize(650, 450)
        self.setStyleSheet(DIALOG_STYLE)
        self.init_ui()

    def init_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(25, 25, 25, 25)

        # Header
        header_layout = QtWidgets.QVBoxLayout()
        header_layout.setSpacing(4)
        title_label = QtWidgets.QLabel("DPT 文件转换")
        title_label.setObjectName("title")
        subtitle_label = QtWidgets.QLabel("将 Excel 格式的 DPT 定义文件转换为加密的 .dat 配置文件。")
        subtitle_label.setObjectName("subtitle")
        header_layout.addWidget(title_label)
        header_layout.addWidget(subtitle_label)
        main_layout.addLayout(header_layout)

        # File selection
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
        self.file_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.file_btn.clicked.connect(self.select_file)

        file_layout.addWidget(self.file_path_edit)
        file_layout.addWidget(self.file_btn)
        main_layout.addWidget(file_group)

        # Output dir selection
        out_group = QtWidgets.QGroupBox("输出位置 (Output Destination)")
        out_layout = QtWidgets.QHBoxLayout(out_group)
        out_layout.setContentsMargins(15, 15, 15, 15)
        out_layout.setSpacing(10)

        self.out_path_edit = QtWidgets.QLineEdit()
        self.out_path_edit.setPlaceholderText("请选择输出文件夹")
        self.out_path_edit.setReadOnly(True)
        self.out_path_edit.setMinimumHeight(36)

        self.out_btn = QtWidgets.QPushButton("📂 选择文件夹")
        self.out_btn.setObjectName("browse")
        self.out_btn.setMinimumHeight(36)
        self.out_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.out_btn.clicked.connect(self.select_output_dir)

        out_layout.addWidget(self.out_path_edit)
        out_layout.addWidget(self.out_btn)
        main_layout.addWidget(out_group)

        # Spacer
        main_layout.addStretch()

        # Action Buttons
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.setSpacing(12)

        self.status_label = QtWidgets.QLabel("")
        self.status_label.setStyleSheet("color: #6B7280; font-size: 9pt;")
        btn_layout.addWidget(self.status_label)

        btn_layout.addStretch()

        self.close_btn = QtWidgets.QPushButton("关闭 (Close)")
        self.close_btn.setObjectName("secondary")
        self.close_btn.setMinimumHeight(38)
        self.close_btn.setMinimumWidth(100)
        self.close_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.close_btn.clicked.connect(self.close)

        self.convert_btn = QtWidgets.QPushButton("🚀 开始转换 (Convert)")
        self.convert_btn.setObjectName("primary")
        self.convert_btn.setMinimumHeight(38)
        self.convert_btn.setMinimumWidth(140)
        self.convert_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.convert_btn.clicked.connect(self.start_conversion)

        btn_layout.addWidget(self.close_btn)
        btn_layout.addWidget(self.convert_btn)

        # Add a separator line above buttons
        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.HLine)
        line.setFrameShadow(QtWidgets.QFrame.Sunken)
        line.setStyleSheet("background-color: #E5E7EB; border: none; max-height: 1px;")

        main_layout.addWidget(line)
        main_layout.addLayout(btn_layout)

    def select_file(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "选择 Excel 文件", "", "Excel Files (*.xlsx)"
        )
        if path:
            self.file_path_edit.setText(path)
            # Default output dir to same as input if not set
            if not self.out_path_edit.text():
                self.out_path_edit.setText(os.path.dirname(path))
            self.status_label.setText("就绪")

    def select_output_dir(self):
        path = QtWidgets.QFileDialog.getExistingDirectory(self, "选择输出文件夹")
        if path:
            self.out_path_edit.setText(path)

    def start_conversion(self):
        input_path = self.file_path_edit.text()
        output_dir = self.out_path_edit.text()

        if not input_path or not os.path.exists(input_path):
            QtWidgets.QMessageBox.warning(self, "错误", "请输入有效的Excel文件路径")
            return

        if not output_dir or not os.path.exists(output_dir):
            QtWidgets.QMessageBox.warning(self, "错误", "请输入有效的输出文件夹路径")
            return

        self.convert_btn.setEnabled(False)
        self.convert_btn.setText("⏳ 转换中...")
        self.status_label.setText("准备开始...")

        # 使用 Worker 在后台线程运行转换
        self.worker = Worker(run_conversion_task, input_path, output_dir)
        self.worker.log_signal.connect(self.status_label.setText)
        self.worker.result_signal.connect(self.on_conversion_finished)
        self.worker.start()

    def on_conversion_finished(self, result):
        self.convert_btn.setEnabled(True)
        self.convert_btn.setText("🚀 开始转换 (Convert)")

        if result:
            self.status_label.setText("✅ 转换完成")
            QtWidgets.QMessageBox.information(self, "成功", f"转换成功！\n文件已保存至: {result}")
        else:
            self.status_label.setText("❌ 转换失败")
            # Worker 会在失败时通过 log_signal 发送错误信息，所以这里可能已经被 setText 更新了部分信息
            # 不过我们还是弹窗提示
            QtWidgets.QMessageBox.critical(self, "错误", "转换失败，请检查文件格式或日志。")
