"""
@FileName：data_format_converter_model.py
@Description：数据格式转换 Model
@Author：QinHao
@Time：2025/12/9 15:24
@Department：PTV_AT
"""
from dataclasses import dataclass
from typing import Optional

from PyQt5.QtCore import QObject, pyqtSignal


@dataclass
class ConvertTaskState:
    source_file: str = ""
    output_dir: str = ""
    conversion_type: str = ""
    source_format: str = ""
    target_format: str = ""
    filename_template: str = "{original}_{timestamp}.{ext}"
    progress: int = 0
    running: bool = False


class DataFormatConverterModel(QObject):
    """保存数据格式转换任务的状态，逻辑尽量简单。"""

    stateChanged = pyqtSignal(ConvertTaskState)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._state = ConvertTaskState()

    # 基础 set/get
    @property
    def state(self) -> ConvertTaskState:
        return self._state

    def update_state(self, **kwargs):
        for k, v in kwargs.items():
            if hasattr(self._state, k):
                setattr(self._state, k, v)
        self.stateChanged.emit(self._state)

    def reset_progress(self):
        self._state.progress = 0
        self._state.running = False
        self.stateChanged.emit(self._state)

    def start_task(self, source_file: str, output_dir: str, conversion_type: str,
                   source_format: str, target_format: str, filename_template: str):
        self._state.source_file = source_file
        self._state.output_dir = output_dir
        self._state.conversion_type = conversion_type
        self._state.source_format = source_format
        self._state.target_format = target_format
        self._state.filename_template = filename_template or self._state.filename_template
        self._state.progress = 0
        self._state.running = True
        self.stateChanged.emit(self._state)

    def simulate_step(self, step: int = 10) -> ConvertTaskState:
        """简单的进度前进接口，返回最新状态。"""
        if not self._state.running:
            return self._state
        self._state.progress = min(100, self._state.progress + abs(int(step)))
        if self._state.progress >= 100:
            self._state.running = False
        self.stateChanged.emit(self._state)
        return self._state
