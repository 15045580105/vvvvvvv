from PyQt5 import QtWidgets, QtCore, QtGui

from app.common.ui.widgets import ModernButton
from app.presentation.views.base_view import BaseView


class ScriptExecView(BaseView):
    def setup_ui(self):
        # 根垂直布局：上方设备区 + 下方脚本与指令区
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        # 顶部使用垂直分割器，用户可调整上下比例
        self.main_splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)

        # ==================== 上：设备表格区域 ====================
        self.device_group = QtWidgets.QGroupBox("设备列表")
        device_layout = QtWidgets.QVBoxLayout(self.device_group)
        device_layout.setContentsMargins(8, 8, 8, 8)
        device_layout.setSpacing(6)

        # 顶部工具条：过滤 + 刷新
        device_toolbar = QtWidgets.QHBoxLayout()
        self.device_filter_edit = QtWidgets.QLineEdit()
        self.device_filter_edit.setPlaceholderText("按设备名或 IP 过滤...")
        self.device_refresh_btn = ModernButton("刷新设备", "#059669", "↻")
        device_toolbar.addWidget(self.device_filter_edit)
        device_toolbar.addWidget(self.device_refresh_btn)
        device_layout.addLayout(device_toolbar)

        # 设备表格
        self.device_table = QtWidgets.QTableWidget()
        self.device_table.setColumnCount(5)
        self.device_table.setHorizontalHeaderLabels([
            "设备名",
            "IP 地址",
            "SSH 端口",
            "状态",
            "说明",
        ])
        header = self.device_table.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QtWidgets.QHeaderView.Stretch)
        self.device_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.device_table.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.device_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.device_table.setAlternatingRowColors(True)

        device_layout.addWidget(self.device_table)
        self.main_splitter.addWidget(self.device_group)

        # ==================== 下：脚本与指令区域 ====================
        bottom_widget = QtWidgets.QWidget()
        bottom_layout = QtWidgets.QHBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(8)

        # 使用水平分割器更好地自适应宽度
        self.bottom_splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)

        # ---------- 左：脚本列表 ----------
        self.script_group = QtWidgets.QGroupBox("脚本列表")
        script_layout = QtWidgets.QVBoxLayout(self.script_group)
        script_layout.setContentsMargins(8, 8, 8, 8)
        script_layout.setSpacing(6)

        # 脚本搜索
        self.script_filter_edit = QtWidgets.QLineEdit()
        self.script_filter_edit.setPlaceholderText("按脚本名过滤...")
        script_layout.addWidget(self.script_filter_edit)

        # 脚本列表
        self.script_list = QtWidgets.QListWidget()
        self.script_list.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.script_list.setAlternatingRowColors(True)
        script_layout.addWidget(self.script_list)

        # 列表下方操作按钮行
        script_btn_layout = QtWidgets.QHBoxLayout()
        self.upload_btn = ModernButton("上传脚本", "#0EA5E9", "⬆")
        self.refresh_btn = ModernButton("刷新列表", "#059669", "↻")
        script_btn_layout.addWidget(self.upload_btn)
        script_btn_layout.addWidget(self.refresh_btn)
        script_btn_layout.addStretch()
        script_layout.addLayout(script_btn_layout)

        self.bottom_splitter.addWidget(self.script_group)

        # ---------- 中：执行配置 + 发送指令 ----------
        self.exec_group = QtWidgets.QGroupBox("执行配置与下发")
        exec_layout = QtWidgets.QVBoxLayout(self.exec_group)
        exec_layout.setContentsMargins(8, 8, 8, 8)
        exec_layout.setSpacing(8)

        # 当前上下文信息（只读）
        context_layout = QtWidgets.QFormLayout()
        context_layout.setLabelAlignment(QtCore.Qt.AlignRight)
        context_layout.setFormAlignment(QtCore.Qt.AlignTop)
        context_layout.setHorizontalSpacing(8)
        context_layout.setVerticalSpacing(4)

        self.current_script_label = QtWidgets.QLabel("未选择")
        self.target_devices_label = QtWidgets.QLabel("未选择")
        context_layout.addRow("当前脚本:", self.current_script_label)
        context_layout.addRow("目标设备:", self.target_devices_label)
        exec_layout.addLayout(context_layout)

        # 参数表单
        form = QtWidgets.QFormLayout()
        form.setLabelAlignment(QtCore.Qt.AlignRight)
        form.setFormAlignment(QtCore.Qt.AlignTop)
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(6)

        # 一般执行参数
        self.param_line = QtWidgets.QLineEdit()
        self.param_line.setPlaceholderText("例如: --id 1 --mode test（可选）")
        form.addRow("执行参数:", self.param_line)

        # 超时时间（秒）
        timeout_row = QtWidgets.QHBoxLayout()
        self.timeout_spin = QtWidgets.QSpinBox()
        self.timeout_spin.setRange(10, 3600)
        self.timeout_spin.setValue(300)
        self.timeout_spin.setSuffix(" 秒")
        timeout_row.addWidget(self.timeout_spin)
        timeout_row.addStretch()
        form.addRow("超时时间:", timeout_row)

        exec_layout.addLayout(form)

        # 发送/指令按钮排成一行
        btn_row_layout = QtWidgets.QHBoxLayout()
        self.send_script_btn = ModernButton("发送脚本到设备", "#2563EB", "⇪")
        self.exec_cmd_btn = ModernButton("下发执行指令", "#059669", "➤")
        btn_row_layout.addWidget(self.send_script_btn)
        btn_row_layout.addWidget(self.exec_cmd_btn)
        btn_row_layout.addStretch()
        exec_layout.addLayout(btn_row_layout)

        exec_layout.addStretch()
        self.bottom_splitter.addWidget(self.exec_group)

        # ---------- 右：日志单独一块 ----------
        self.log_group = QtWidgets.QGroupBox("执行日志")
        log_layout = QtWidgets.QVBoxLayout(self.log_group)
        log_layout.setContentsMargins(8, 8, 8, 8)
        log_layout.setSpacing(4)

        # 顶部工具行：清空 + 预留过滤/导出（暂只放清空按钮）
        log_toolbar = QtWidgets.QHBoxLayout()
        self.clear_output_btn = ModernButton("清空", "#6B7280", "✕")
        log_toolbar.addWidget(self.clear_output_btn)
        log_toolbar.addStretch()
        log_layout.addLayout(log_toolbar)

        # 日志输出框
        self.script_output = QtWidgets.QTextEdit()
        self.script_output.setReadOnly(True)
        self.script_output.setFont(QtGui.QFont("Consolas", 10))
        self.script_output.setLineWrapMode(QtWidgets.QTextEdit.NoWrap)
        log_layout.addWidget(self.script_output)

        self.bottom_splitter.addWidget(self.log_group)

        # 设置各列初始宽度比例：左脚本 < 中参数与指令 < 右日志
        self.bottom_splitter.setStretchFactor(0, 3)
        self.bottom_splitter.setStretchFactor(1, 4)
        self.bottom_splitter.setStretchFactor(2, 5)

        bottom_layout.addWidget(self.bottom_splitter)
        self.main_splitter.addWidget(bottom_widget)

        # 上下比例
        self.main_splitter.setStretchFactor(0, 3)
        self.main_splitter.setStretchFactor(1, 5)

        main_layout.addWidget(self.main_splitter)

    def populate(self, scripts):
        """兼容旧接口：填充脚本列表。"""
        self.script_list.clear()
        for s in scripts:
            self.script_list.addItem(s)

    # 预留一些常用的辅助方法，便于控制器调用
    def set_devices(self, devices):
        """根据设备列表填充设备表格。

        devices: 可迭代对象，每项为 dict 或具备属性 name/ip/port/status/desc
        """
        self.device_table.setRowCount(0)
        for row, d in enumerate(devices):
            self.device_table.insertRow(row)
            name = getattr(d, "name", None) or d.get("name", "")
            ip = getattr(d, "ip", None) or d.get("ip", "")
            port = getattr(d, "port", None) or d.get("port", "")
            status = getattr(d, "status", None) or d.get("status", "")
            desc = getattr(d, "desc", None) or d.get("desc", "")

            self.device_table.setItem(row, 0, QtWidgets.QTableWidgetItem(str(name)))
            self.device_table.setItem(row, 1, QtWidgets.QTableWidgetItem(str(ip)))
            self.device_table.setItem(row, 2, QtWidgets.QTableWidgetItem(str(port)))
            self.device_table.setItem(row, 3, QtWidgets.QTableWidgetItem(str(status)))
            self.device_table.setItem(row, 4, QtWidgets.QTableWidgetItem(str(desc)))

    def get_selected_devices(self):
        """返回当前选中的设备行索引列表。实际可按需扩展为返回数据对象。"""
        rows = set()
        for item in self.device_table.selectedItems():
            rows.add(item.row())
        return sorted(rows)

    def get_selected_script(self):
        item = self.script_list.currentItem()
        if not item:
            return None
        return item.text()

    def get_exec_options(self):
        """收集执行参数配置（仅作为传给后端/目标设备的参数，不在本地直接执行）。"""
        return {
            "timeout": self.timeout_spin.value(),
            "params": self.param_line.text().strip(),
        }

    def update_context(self, script_name: str | None, selected_device_count: int):
        """更新中间面板上的当前脚本/目标设备摘要显示。"""
        self.current_script_label.setText(script_name or "未选择")
        if selected_device_count <= 0:
            self.target_devices_label.setText("未选择")
        else:
            self.target_devices_label.setText(f"已选 {selected_device_count} 台设备")

    def append_output(self, text: str):
        self.script_output.append(text)

    def clear_output(self):
        self.script_output.clear()
