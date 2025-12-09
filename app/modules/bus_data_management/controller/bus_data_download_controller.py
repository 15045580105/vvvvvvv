"""
@FileName：bus_data_download_controller.py
@Description：总线数据下载控制器
@Author：QinHao
@Time：2025/12/9 14:58
@Department：PTV_AT
"""
from app.core.base_controller import BaseController
from app.modules.bus_data_management.model.bus_data_download_model import (
    BusDataDownloadModel,
    PageResult,
)
from app.modules.bus_data_management.view.bus_data_download_view import BusDataDownloadView


class BusDataDownloadController(BaseController):
    def __init__(self, parent=None):
        self.model = BusDataDownloadModel(parent)
        self.view = BusDataDownloadView(parent)
        super().__init__(self.model, self.view, parent)

        # 连接 Model 信号
        self.model.dataChanged.connect(self.on_model_changed)

        # 连接 View 基本交互信号
        self.view.sig_search_clicked.connect(self.on_search)
        self.view.sig_refresh_clicked.connect(self.on_refresh)
        self.view.sig_page_changed.connect(self.on_page_changed)
        self.view.sig_page_size_changed.connect(self.on_page_size_changed)

        # 下载/取消按钮
        self.view.sig_download_clicked.connect(self.on_row_download_clicked)
        self.view.sig_cancel_clicked.connect(self.on_row_cancel_clicked)

        # 首次加载
        self.on_model_changed()

    # ---- 模型变化 -> 刷新视图 ----
    def on_model_changed(self):
        page_result: PageResult = self.model.get_page()
        self.view.render_rows(
            rows=page_result.rows,
            page=page_result.page,
            page_count=page_result.page_count,
            total=page_result.total,
            page_size=page_result.page_size,
        )

    # ---- 顶部过滤 / 刷新 ----
    def on_search(self, criteria: dict):
        self.model.set_filter(criteria)

    def on_refresh(self):
        self.model.load_mock()

    # ---- 分页 ----
    def on_page_changed(self, delta: int):
        current_page = self.model.page
        target_page = current_page + int(delta or 0)
        if target_page < 1:
            target_page = 1
        self.model.set_page(target_page)

    def on_page_size_changed(self, page_size: int):
        self.model.set_page_size(page_size)

    # ---- 行级操作：下载/取消 ----
    def on_row_download_clicked(self, row: int):
        """点击下载按钮：row 为当前页中的行索引。"""
        page_result: PageResult = self.model.get_page()
        if row < 0 or row >= len(page_result.rows):
            return
        item = page_result.rows[row]
        # 这里可以接入真实下载逻辑；暂时先把状态改为 "下载中"
        item["status"] = "下载中"
        item["progress"] = 0
        # 简单刷新：当前实现中 _all_rows / _filtered_rows 指向同一对象列表，可直接 emit
        self.model.dataChanged.emit()

    def on_row_cancel_clicked(self, row: int):
        """点击取消按钮：row 为当前页中的行索引。"""
        page_result: PageResult = self.model.get_page()
        if row < 0 or row >= len(page_result.rows):
            return
        item = page_result.rows[row]
        # 暂时把状态置为 "等待"，进度清零
        item["status"] = "等待"
        item["progress"] = 0
        self.model.dataChanged.emit()

    def get_view(self):
        return self.view
