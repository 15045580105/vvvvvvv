"""
@FileName：demo_page_controller.py
@Description：
@Author：QinHao
@Time：2025/12/23 16:28
@Department：PTV_AT
"""
from app.core.base_controller import BaseController
from app.modules.demo_page.model.demo_page_model import DemoPageModel
from app.modules.demo_page.view.demo_page_view import ControlGalleryWidget


class DemoPageController(BaseController):

    def __init__(self, parent=None):
        self.view = ControlGalleryWidget()
        self.model = DemoPageModel(parent)
        super().__init__(self.model,self.view, parent=parent)

