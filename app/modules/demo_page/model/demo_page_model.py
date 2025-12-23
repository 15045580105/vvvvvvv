"""
@FileName：demo_page_model.py
@Description：
@Author：QinHao
@Time：2025/12/23 18:22
@Department：PTV_AT
"""
from app.core.base_model import BaseModel


class DemoPageModel(BaseModel):
    def __init__(self, parent=None):
        super().__init__(parent)