"""
@FileName：data_format_converter_controller.py
@Description：数据格式转换 Controller
@Author：QinHao
@Time：2025/12/9 15:24
@Department：PTV_AT
"""
from pathlib import Path

from PyQt5.QtCore import QObject, QTimer

from app.core.base_controller import BaseController
from app.modules.data_format_converter.model.data_format_converter_model import (
    DataFormatConverterModel,
    ConvertTaskState,
)
from app.modules.data_format_converter.view.data_format_converter_view import DataFormatConverterView


class DataFormatConverterController(BaseController):
    def __init__(self, parent: QObject | None = None):
        self.model = DataFormatConverterModel(parent)
        self.view = DataFormatConverterView(parent)
        super().__init__(self.model, self.view, parent)

        # 连接信号
        self.model.stateChanged.connect(self.on_state_changed)

        self.view.sig_file_dropped.connect(self.on_file_dropped_or_browse)
        self.view.sig_output_dir_browse.connect(self.on_browse_output_dir)
        self.view.sig_convert_clicked.connect(self.on_convert_clicked)
        self.view.sig_clear_log_clicked.connect(self.on_clear_log)

        # 转换模拟 timer
        self._timer = QTimer(self.view)
        self._timer.timeout.connect(self.on_timer_tick)

    # ---- 槽：View -> Model ----
    def on_file_dropped_or_browse(self, path: str):
        """文件拖拽或点击选择。若 path 为空则走文件对话框（浏览模式）。"""
        if not path:
            # 打开文件选择对话框
            from PyQt5 import QtWidgets

            file_name, _ = QtWidgets.QFileDialog.getOpenFileName(
                self.view,
                "选择源文件",
                "",
                "All Files (*.*)",
            )
            if not file_name:
                return
            path = file_name

        self.view.set_selected_file(path)
        # 简单根据扩展名猜测格式
        ext = Path(path).suffix.lower()
        if ext == ".dlt":
            self.view.conversion_type_combo.setCurrentIndex(0)
            self.view.source_format_combo.setCurrentText("DLT")
        self.view.append_log(f"已加载文件: {path}")

    def on_browse_output_dir(self):
        from PyQt5 import QtWidgets

        directory = QtWidgets.QFileDialog.getExistingDirectory(self.view, "选择输出目录", "")
        if directory:
            self.view.set_output_dir(directory)

    def on_convert_clicked(self):
        """开始转换。"""
        source_file = self.view.file_path_display.text().strip()
        output_dir = self.view.output_path_display.text().strip()
        if not source_file:
            self.view.append_log("❌ 错误: 请先选择源文件")
            return

        if not output_dir:
            output_dir = str(Path(source_file).parent)
            self.view.set_output_dir(output_dir)

        conversion_type = self.view.conversion_type_combo.currentText()
        source_format = self.view.source_format_combo.currentText()
        target_format = self.view.target_format_combo.currentText()
        filename_template = self.view.filename_template.text().strip() or "{original}_{timestamp}.{ext}"

        self.model.start_task(
            source_file=source_file,
            output_dir=output_dir,
            conversion_type=conversion_type,
            source_format=source_format,
            target_format=target_format,
            filename_template=filename_template,
        )

        self.view.append_log("=" * 50)
        self.view.append_log(f"🚀 任务开始: {conversion_type}")
        self.view.append_log(f"📥 输入: {source_file}")
        self.view.append_log(f"📤 输出格式: {target_format}")
        self.view.append_log(f"📁 输出目录: {output_dir}")

        self.view.set_busy(True)
        self.view.set_progress(0, visible=True)
        self._timer.start(120)

    def on_quick_convert_clicked(self):
        """快速转换：和普通转换一致，目前只是入口不同。"""
        self.on_convert_clicked()

    def on_clear_log(self):
        self.view.clear_log()

    # ---- Model -> View ----
    def on_state_changed(self, state: ConvertTaskState):
        self.view.set_progress(state.progress, visible=state.running or state.progress > 0)
        if not state.running and state.progress >= 100:
            self.view.append_log("✅ 转换完成！文件已保存到输出目录")
            self.view.append_log("=" * 50)
            self.view.set_busy(False)
            self._timer.stop()

    # ---- Timer ----
    def on_timer_tick(self):
        state = self.model.simulate_step(10)
        if state.progress == 30:
            self.view.append_log("🔍 正在解析文件结构...")
        elif state.progress == 60:
            self.view.append_log("⚙️ 正在转换数据格式...")
        elif state.progress == 90:
            self.view.append_log("💾 正在写入输出文件...")

        if not state.running:
            # 最终完成由 on_state_changed 负责
            self._timer.stop()

    def get_view(self):
        return self.view
