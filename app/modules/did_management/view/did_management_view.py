from PyQt5 import QtWidgets, QtGui, QtCore

from app.common.ui.widgets import ModernButton
from app.presentation.views.base_view import BaseView


class DIDView(BaseView):
    ecu_map_import_requested = QtCore.pyqtSignal()
    dpt_import_requested = QtCore.pyqtSignal()

    def setup_ui(self):
        """构建 DID 界面布局，组合控制区、原始数据与解析结果面板。"""
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setSpacing(8)

        # Top control bar: ECU dest mapping import, DPT import, request data input + execute
        ctl = QtWidgets.QHBoxLayout()
        ctl.setSpacing(12)

        self.ecu_map_btn = ModernButton("导入ECU目的地址表", "#6366F1", "📥")
        self.dpt_import_btn = ModernButton("导入DPT文件", "#22C55E", "📂")
        ctl.addWidget(self.ecu_map_btn)
        ctl.addWidget(self.dpt_import_btn)

        # Request data input (DID-style) and execute button on same line
        self.request_input = QtWidgets.QLineEdit()
        self.request_input.setPlaceholderText("请输入请求数据，例如: 22 F1 90 00 ...")
        font = QtGui.QFont("Consolas", 9)
        self.request_input.setFont(font)
        ctl.addWidget(self.request_input, 1)

        self.exec_btn = ModernButton("执行", "#0EA5E9", "▶")
        ctl.addWidget(self.exec_btn)

        ctl.addStretch()
        main_layout.addLayout(ctl)

        # Bottom area: make three resizable panels with QSplitter
        splitter = QtWidgets.QSplitter()
        splitter.setOrientation(QtCore.Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        # Left panel: ECU list fills vertically
        left_widget = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        ecu_label = QtWidgets.QLabel("ECU 列表")
        left_layout.addWidget(ecu_label)

        self.ecu_list = QtWidgets.QListWidget()
        self.ecu_list.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.ecu_list.setAlternatingRowColors(True)
        left_layout.addWidget(self.ecu_list, 1)

        splitter.addWidget(left_widget)

        # Middle panel: raw request/response text
        middle_widget = QtWidgets.QWidget()
        middle_layout = QtWidgets.QVBoxLayout(middle_widget)
        middle_layout.setContentsMargins(0, 0, 0, 0)
        middle_layout.setSpacing(8)

        raw_group = QtWidgets.QGroupBox("请求/响应原始数据")
        raw_layout = QtWidgets.QVBoxLayout(raw_group)
        raw_layout.setSpacing(4)

        self.raw_text = QtWidgets.QTextEdit()
        self.raw_text.setPlaceholderText("请求和响应原始数据将在这里显示...")
        self.raw_text.setFont(font)
        raw_layout.addWidget(self.raw_text)

        middle_layout.addWidget(raw_group)
        splitter.addWidget(middle_widget)

        # Right panel: parsed result table (four columns)
        right_widget = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        parsed_group = QtWidgets.QGroupBox("解析结果")
        parsed_layout = QtWidgets.QVBoxLayout(parsed_group)

        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabels(["bit位", "功能", "二进制值", "状态"])
        header = self.tree.header()

        # 交互式列宽，默认按比例分配，保证四列在默认布局下全部可见
        header.setSectionResizeMode(QtWidgets.QHeaderView.Interactive)

        # 右侧区域默认大约占总宽度的三分之一，这里按 380px 左右的内容区预估列宽
        initial_tree_width = 380
        col_ratios = [0.14, 0.42, 0.22, 0.22]  # bit位稍窄，功能最多，后二列中等
        for idx, ratio in enumerate(col_ratios):
            header.resizeSection(idx, int(initial_tree_width * ratio))

        # 列最小宽度，避免被压得看不清文字
        header.setMinimumSectionSize(50)

        # 让“功能”列在窗口放大时优先伸展，其他列保持相对稳定
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)

        parsed_layout.addWidget(self.tree)
        right_layout.addWidget(parsed_group)

        # 右侧默认宽度约为总宽的三分之一，同时保证能完整显示四列
        right_widget.setMinimumWidth(420)
        splitter.addWidget(right_widget)

        # 设置 splitter 初始比例为 3:5:4（左:中:右），右侧约占三分之一
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 5)
        splitter.setStretchFactor(2, 4)
        splitter.setSizes([300, 500, 400])

        main_layout.addWidget(splitter, 1)

        self.ecu_map_btn.clicked.connect(self.ecu_map_import_requested.emit)
        self.dpt_import_btn.clicked.connect(self.dpt_import_requested.emit)
