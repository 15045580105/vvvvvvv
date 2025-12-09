from app.core.base_controller import BaseController
from app.modules.log_management.model.log_management_model import LogDownloadModel, PageResult
from app.modules.log_management.view.log_management_view import LogDownloadView


class LogDownloadController(BaseController):
    def __init__(self, parent=None):
        self.model = LogDownloadModel(parent)
        self.view = LogDownloadView(parent)
        super().__init__(self.model, self.view, parent)

        # 连接 Model 信号
        self.model.dataChanged.connect(self.on_model_changed)

        # 连接 View 信号
        self.view.sig_search_clicked.connect(self.on_search)
        self.view.sig_refresh_clicked.connect(self.on_refresh)
        self.view.sig_page_changed.connect(self.on_page_changed)
        self.view.sig_page_size_changed.connect(self.on_page_size_changed)

        # 首次加载第一页
        self.on_model_changed()

    # ---- Controller 槽函数 ----
    def on_model_changed(self):
        """模型数据变更时，根据当前过滤和分页状态刷新视图。"""
        page_result: PageResult = self.model.get_page()
        self.view.render_rows(
            rows=page_result.rows,
            page=page_result.page,
            page_count=page_result.page_count,
            total=page_result.total,
            page_size=page_result.page_size,
        )

    def on_search(self, criteria: dict):
        """用户点击搜索按钮，更新过滤条件并刷新第一页。"""
        self.model.set_filter(criteria)
        # set_filter 会触发 dataChanged，进而调用 on_model_changed

    def on_refresh(self):
        """用户点击刷新按钮，重新加载数据。"""
        self.model.load_mock()  # 加载模拟数据或真实数据源
        # load_mock 内部会触发 dataChanged

    def on_page_changed(self, delta: int):
        """分页切换：delta=-1 表示上一页，+1 表示下一页。"""
        current_page = self.model.page
        target_page = current_page + int(delta or 0)
        if target_page < 1:
            target_page = 1
        self.model.set_page(target_page)
        # set_page 会触发 dataChanged

    def on_page_size_changed(self, page_size: int):
        """用户修改每页条数，回到第一页。"""
        self.model.set_page_size(page_size)
        # set_page_size 会触发 dataChanged

    def get_view(self):
        return self.view
