from app.core.base_model import BaseModel
import math


class LogConfigModel(BaseModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.ecu_levels = {"CCUA":"INFO","CCU0":"WARN","CCU1":"ERROR"}

        # 全量数据缓存
        self._all_apps = []

        #当前页显示的数据 (用于 View 显示)
        self.apps = []

        # 分页状态
        self.current_page = 1
        self.page_size = 10
        self.total_pages = 1

    def set_data(self, data):
        """设置全量数据并重置分页"""
        self._all_apps = data
        self.current_page = 1
        self._calculate_pagination()

    def set_page_size(self, size):
        self.page_size = size
        self.current_page = 1 # 改变页大小时通常重置到第一页
        self._calculate_pagination()

    def next_page(self):
        if self.current_page < self.total_pages:
            self.current_page += 1
            self._update_current_view()
            return True
        return False

    def prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self._update_current_view()
            return True
        return False

    def _calculate_pagination(self):
        total_items = len(self._all_apps)
        if self.page_size <= 0: self.page_size = 10

        self.total_pages = math.ceil(total_items / self.page_size)
        if self.total_pages < 1: self.total_pages = 1

        # 边界检查
        if self.current_page > self.total_pages:
            self.current_page = self.total_pages
        if self.current_page < 1:
            self.current_page = 1

        self._update_current_view()

    def _update_current_view(self):
        """[内部方法] 根据当前页码切片数据，并转换为视图所需的格式。"""
        # 1. 计算切片范围
        start_index = (self.current_page - 1) * self.page_size
        end_index = start_index + self.page_size

        # 2. 从全量数据中获取当前页数据
        page_data = self._all_apps[start_index:end_index]

        # 3. 转换数据格式以适配 View (将字典转换为元组列表)
        # 对应界面显示的列：AppID, ECU, LogLevel, FileNo, FileSize, TotalSize
        self.apps = [
            (app["app_id"], app["ecu_id"], app["log_level"], app["file_no"], app["file_size"], app["total_size"])
            for app in page_data
        ]

    def get_all_data(self):
        """获取全量数据（例如用于保存配置时）。"""
        # 1. 返回内部存储的所有应用配置列表
        return self._all_apps

    def update_app_level(self, app_id, ecu_id, new_level):
        """更新本地缓存：当用户在界面修改日志级别时调用。"""
        # 1. 遍历所有应用数据
        for app in self._all_apps:
            # 2. 找到匹配的 AppID 和 ECU
            if app["app_id"] == app_id and app["ecu_id"] == ecu_id:
                # 3. 更新其日志级别
                app["log_level"] = new_level
                break

        # 4. 重新计算当前页的视图数据，确保界面同步更新
        self._update_current_view()
