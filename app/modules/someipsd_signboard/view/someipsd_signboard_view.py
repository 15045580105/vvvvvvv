from PyQt5.QtCore import Qt, QSize, pyqtSignal, QTimer, QPointF, QRectF, QDateTime
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QGridLayout,
    QGraphicsDropShadowEffect, QLineEdit, QListWidget,
    QListWidgetItem, QAbstractItemView, QCheckBox, QPushButton, QFileDialog,
    QScrollArea, QDateTimeEdit
)
from PyQt5.QtGui import QColor, QPainter, QPixmap, QIcon, QPainterPath, QPen

from app.presentation.views.base_view import BaseView
from app.common.ui.widgets import ModernButton


def create_vector_icon(shape: str, color: str, size: int = 40) -> QIcon:
    """
    Creates a high-quality vector-based icon using QPainter.
    shape: 'pin_filled', 'pin_outline', 'eye', 'eye_off'
    size: Physical pixel size of the internal map (higher = crisper)
    """
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    c = QColor(color)
    pen_width = max(2, size // 12)

    painter.setPen(QPen(c, pen_width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))

    m = size * 0.2
    w = size - 2 * m

    if shape == 'pin_filled' or shape == 'pin_outline':
        center = QPointF(size/2, size/2)
        painter.translate(center)
        painter.rotate(45)
        painter.translate(-center)

        body_w = w * 0.4
        body_h = w * 0.6
        top_rect = QRectF((size - body_w)/2, m, body_w, body_h)
        tip_start = QPointF(size/2, m + body_h)
        tip_end = QPointF(size/2, size - m)

        if shape == 'pin_filled':
            painter.setBrush(c)
            painter.drawRect(top_rect)
            painter.drawLine(tip_start, tip_end)
        else:
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(top_rect)
            painter.drawLine(tip_start, tip_end)

    elif shape == 'eye':
        painter.setBrush(Qt.NoBrush)
        path = QPainterPath()
        path.moveTo(m, size/2)
        path.quadTo(size/2, m - m*0.5, size-m, size/2)
        path.quadTo(size/2, size-m + m*0.5, m, size/2)
        painter.drawPath(path)
        painter.setBrush(c)
        painter.setPen(Qt.NoPen)
        pupil_r = w * 0.15
        painter.drawEllipse(QPointF(size/2, size/2), pupil_r, pupil_r)

    elif shape == 'eye_off':
        painter.setBrush(Qt.NoBrush)
        path = QPainterPath()
        path.moveTo(m, size/2)
        path.quadTo(size/2, m - m*0.5, size-m, size/2)
        path.quadTo(size/2, size-m + m*0.5, m, size/2)
        painter.drawPath(path)
        painter.setBrush(c)
        painter.setPen(Qt.NoPen)
        pupil_r = w * 0.15
        painter.drawEllipse(QPointF(size/2, size/2), pupil_r, pupil_r)
        painter.setPen(QPen(c, pen_width, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(QPointF(m, size-m), QPointF(size-m, m))

    painter.end()
    return QIcon(pixmap)


class ServiceCard(QFrame):
    """
    Card widget representing a single SOME/IP service instance.
    Includes Pin and Hide actions.
    """
    # Signals to notify parent view
    action_triggered = pyqtSignal(str, dict) # action_type ('pin', 'hide', 'restore'), data

    def __init__(self, data, is_pinned=False, is_hidden=False, parent=None):
        super().__init__(parent)
        self.data = data
        self.is_pinned = is_pinned
        self.is_hidden_state = is_hidden
        self.setCursor(Qt.OpenHandCursor) # Indicate draggable
        self._shadow = None # Keep reference
        self.setup_ui()
        self.apply_style()

    def setup_ui(self):
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setObjectName("ServiceCard")

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- Top Bar (Status & ID & Actions) ---
        top_bar = QFrame()
        top_bar.setObjectName("CardTopBar")
        top_layout = QHBoxLayout(top_bar)

        top_layout.setContentsMargins(8, 6, 8, 6)
        top_layout.setSpacing(8)

        # Index Label (Serial Number)
        self.index_lbl = QLabel(str(self.data.get("index", "#")))
        self.index_lbl.setObjectName("IndexLabel")
        top_layout.addWidget(self.index_lbl)

        # Service ID Badge
        self.id_lbl = QLabel(self.data.get("service_id", "0x0000"))
        self.id_lbl.setObjectName("ServiceIdLabel")

        # Status
        self.status_lbl = QLabel()
        # Initial status set in update_content

        top_layout.addWidget(self.id_lbl)
        top_layout.addWidget(self.status_lbl)
        top_layout.addStretch()

        # Detail Button
        self.detail_btn = QPushButton("详情")
        self.detail_btn.setFixedHeight(28)
        self.detail_btn.setCursor(Qt.PointingHandCursor)
        self.detail_btn.clicked.connect(self._on_detail_clicked)
        self.detail_btn.setStyleSheet("QPushButton { border: 1px solid #D1D5DB; border-radius: 6px; padding: 2px 8px; background-color: #FFFFFF; color: #374151; } QPushButton:hover { background-color: #F3F4F6; }")

        # Pin Button
        self.pin_btn = QPushButton()
        self.pin_btn.setFixedSize(30, 30)
        self.pin_btn.setIconSize(QSize(20, 20))
        self.pin_btn.setCursor(Qt.PointingHandCursor)
        self.pin_btn.clicked.connect(self._on_pin_clicked)
        # Base style - will be overridden by update
        self.pin_btn.setStyleSheet("QPushButton { border: 1px solid #CBD5E1; border-radius: 6px; background-color: #F8FAFC; border: none; }")

        # Hide/Restore Button
        self.hide_btn = QPushButton()
        self.hide_btn.setFixedSize(30, 30)
        self.hide_btn.setIconSize(QSize(20, 20))
        self.hide_btn.setCursor(Qt.PointingHandCursor)
        self.hide_btn.clicked.connect(self._on_hide_clicked)
        # Base style
        self.hide_btn.setStyleSheet("QPushButton { border: 1px solid #CBD5E1; border-radius: 6px; background-color: #F8FAFC; border: none; }")

        top_layout.addWidget(self.detail_btn)
        top_layout.addWidget(self.pin_btn)
        top_layout.addWidget(self.hide_btn)

        main_layout.addWidget(top_bar)

        # --- Content Body ---
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(10, 6, 10, 6)
        content_layout.setSpacing(4)

        # Service Name
        self.name_lbl = QLabel(self.data.get("service_name", "未知服务"))
        self.name_lbl.setObjectName("ServiceNameLabel")
        self.name_lbl.setWordWrap(True)
        content_layout.addWidget(self.name_lbl)

        # Summary Frame (initially visible)
        self.summary_frame = QWidget()
        summary_layout = QVBoxLayout(self.summary_frame)
        summary_layout.setContentsMargins(0, 0, 0, 0)
        summary_layout.setSpacing(4)

        # Info Grid
        self.info_grid = QGridLayout()
        self.info_grid.setVerticalSpacing(2)
        self.info_grid.setHorizontalSpacing(8)

        # Initialize labels for grid rows to update later
        self.grid_labels = {}

        def add_row(key, row, icon, label):
            icon_lbl = QLabel(icon)
            icon_lbl.setFixedSize(18, 18)
            icon_lbl.setAlignment(Qt.AlignCenter)
            icon_lbl.setStyleSheet("color: #6B7280; font-size: 13px;")

            lbl_widget = QLabel(label)
            lbl_widget.setStyleSheet("color: #6B7280; font-size: 12px;")

            val_widget = QLabel()
            val_widget.setObjectName(f"Val_{key}")

            self.grid_labels[key] = val_widget

            self.info_grid.addWidget(icon_lbl, row, 0)
            self.info_grid.addWidget(lbl_widget, row, 1)
            self.info_grid.addWidget(val_widget, row, 2)
            self.info_grid.setColumnStretch(2, 1)

        add_row("inst", 0, "🆔", "实例ID")
        add_row("ver", 1, "📌", "版本号")
        add_row("ep", 2, "🌐", "服务端点")
        add_row("time", 3, "🕒", "最后活跃")

        summary_layout.addLayout(self.info_grid)

        # Preview
        self.preview_lbl = QLabel()
        self.preview_lbl.setWordWrap(True)
        self.preview_lbl.setTextFormat(Qt.RichText)
        self.preview_lbl.setStyleSheet("color: #4B5563; font-size: 11px;")
        self.preview_lbl.setVisible(False)
        summary_layout.addWidget(self.preview_lbl)

        content_layout.addWidget(self.summary_frame)

        # Detail Frame (initially hidden)
        self.detail_frame = QWidget()
        detail_layout = QVBoxLayout(self.detail_frame)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.setSpacing(6)

        self.detail_title_lbl = QLabel("详情信息")
        self.detail_title_lbl.setStyleSheet("font-size: 13px; font-weight: 700; color: #1F2937;")
        detail_layout.addWidget(self.detail_title_lbl)

        self.detail_scroll = QScrollArea()
        self.detail_scroll.setWidgetResizable(True)
        self.detail_scroll.setFrameShape(QFrame.NoFrame)
        self.detail_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.detail_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.detail_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; } QScrollBar:vertical { width: 10px; } QScrollBar:horizontal { height: 10px; }")

        self.detail_scroll_content = QWidget()
        self.detail_scroll_content.setObjectName("DetailScrollContent")
        self.detail_scroll_layout = QVBoxLayout(self.detail_scroll_content)
        self.detail_scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.detail_scroll_layout.setSpacing(8)

        self.detail_content_lbl = QLabel()
        self.detail_content_lbl.setWordWrap(True)
        self.detail_content_lbl.setTextFormat(Qt.RichText)
        self.detail_content_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.detail_content_lbl.setStyleSheet("color: #374151; font-size: 11px; line-height: 1.6;")
        self.detail_scroll_layout.addWidget(self.detail_content_lbl)
        self.detail_scroll_layout.addStretch()

        self.detail_scroll.setWidget(self.detail_scroll_content)
        detail_layout.addWidget(self.detail_scroll)

        content_layout.addWidget(self.detail_frame)

        main_layout.addWidget(content_widget, 1)

        # --- Footer (Subscribers) ---
        self.footer = QFrame()
        self.footer.setObjectName("CardFooter")
        footer_layout = QVBoxLayout(self.footer)
        footer_layout.setContentsMargins(8, 4, 8, 4)
        footer_layout.setSpacing(2)

        # Clients Summary
        count_layout = QHBoxLayout()
        self.sub_count_lbl = QLabel("👥 订阅: 0")
        self.sub_count_lbl.setStyleSheet("font-size: 11px; color: #4B5563; font-weight: 600;")

        self.find_count_lbl = QLabel("🔍 发现: 0")
        self.find_count_lbl.setStyleSheet("font-size: 11px; color: #4B5563; font-weight: 600;")

        count_layout.addWidget(self.sub_count_lbl)
        count_layout.addStretch()
        count_layout.addWidget(self.find_count_lbl)
        footer_layout.addLayout(count_layout)

        main_layout.addWidget(self.footer)

        # Initial content update
        self._update_all_widgets()

    def update_content(self, data, is_pinned, is_hidden):
        """Update data and state without recreating widget to improve performance."""
        self.data = data
        self.is_pinned = is_pinned
        self.is_hidden_state = is_hidden
        self._update_all_widgets()
        self.apply_style() # Re-apply style for pinned/hidden border changes

    def _update_all_widgets(self):
        # Index
        self.index_lbl.setText(str(self.data.get("index", "")))

        # Service ID
        self.id_lbl.setText(self.data.get("service_id", "0x0000"))

        # Status: 唯一标准为是否命中矩阵
        matrix_flag = self.data.get("matrix_matched", self.data.get("in_matrix", False))
        if isinstance(matrix_flag, str):
            is_active = matrix_flag.strip().lower() in ("1", "true", "yes", "y", "active")
        else:
            is_active = bool(matrix_flag)

        status_text = " Active " if is_active else " Inactive "
        self.status_lbl.setText(status_text)
        self.status_lbl.setObjectName("StatusLabel_Active" if is_active else "StatusLabel_Inactive")
        # Force style reload for dynamic object name
        self.status_lbl.style().unpolish(self.status_lbl)
        self.status_lbl.style().polish(self.status_lbl)

        # Name
        self.name_lbl.setText(self.data.get("service_name", "未知服务"))

        # Grid Data
        def set_grid_text(key, val, mono=False):
            txt = str(val)
            self.grid_labels[key].setToolTip(txt)
            if len(txt) > 30:
                txt = txt[:28] + "..."
            self.grid_labels[key].setText(txt)
            style = "color: #374151; font-size: 12px; font-weight: 500;"
            if mono: style += " font-family: 'Consolas', monospace;"
            self.grid_labels[key].setStyleSheet(style)

        set_grid_text("inst", self.data.get("instance_id", "-"), True)
        set_grid_text("ver", self.data.get("version", "-"))
        set_grid_text("ep", self.data.get("server_endpoint", "-"), True)
        set_grid_text("time", self.data.get("last_time", "-"))

        # Footer
        subs = self.data.get("subscribe_info", [])
        finds = self.data.get("find_info", [])

        self.sub_count_lbl.setText(f"👥 订阅: {len(subs)}")
        self.find_count_lbl.setText(f"🔍 发现: {len(finds)}")

        self.preview_lbl.clear()
        self.preview_lbl.setVisible(False)

        # Detail View Content
        detail_lines = []
        last_time = self.data.get('last_time', '-')
        last_time_source = self.data.get('last_time_source', '-')
        status_reason = self.data.get('status_reason', '-')
        detail_lines.append(
            "<div style='margin-bottom:10px;'>"
            "<div style='font-size:12px;font-weight:700;color:#111827;margin-bottom:6px;'>Activity Info</div>"
            "<div style='margin:0 0 10px 0; padding:8px 10px; background:#F8FAFC; border:1px solid #E5E7EB; border-radius:6px;'>"
            f"<div><span style='color:#6B7280;'>Current Status：</span><span style='color:#111827;'>{'Active' if is_active else 'Inactive'}</span></div>"
            f"<div><span style='color:#6B7280;'>Status Reason：</span><span style='color:#111827;'>{status_reason}</span></div>"
            f"<div><span style='color:#6B7280;'>Last Active Time：</span><span style='color:#111827;'>{last_time}</span></div>"
            f"<div><span style='color:#6B7280;'>Time Source：</span><span style='color:#111827;'>{last_time_source}</span></div>"
            "</div>"
            "</div>"
        )

        if finds:
            detail_lines.append(
                "<div style='margin-bottom:10px;'>"
                "<div style='font-size:12px;font-weight:700;color:#111827;margin-bottom:6px;'>Find Info</div>"
            )
            for idx, item in enumerate(finds, start=1):
                detail_lines.append(
                    "<div style='margin:0 0 10px 0; padding:8px 10px; background:#F8FAFC; border:1px solid #E5E7EB; border-radius:6px;'>"
                    f"<div style='font-weight:600;color:#1F2937;margin-bottom:4px;'>#{idx} Finder</div>"
                    f"<div><span style='color:#6B7280;'>Finder IP：</span><span style='font-family:Consolas,monospace;color:#111827;'>{item.get('finder_ip', '-')}</span></div>"
                    f"<div><span style='color:#6B7280;'>Find Version：</span><span style='color:#111827;'>{item.get('find_version', '-')}</span></div>"
                    f"<div><span style='color:#6B7280;'>Last Find Time：</span><span style='color:#111827;'>{item.get('last_find_time', '-')}</span></div>"
                    "</div>"
                )
            detail_lines.append("</div>")

        if subs:
            detail_lines.append(
                "<div style='margin-bottom:4px;'>"
                "<div style='font-size:12px;font-weight:700;color:#111827;margin-bottom:6px;'>Subscribe Info</div>"
            )
            for idx, item in enumerate(subs, start=1):
                detail_lines.append(
                    "<div style='margin:0 0 10px 0; padding:8px 10px; background:#F8FAFC; border:1px solid #E5E7EB; border-radius:6px;'>"
                    f"<div style='font-weight:600;color:#1F2937;margin-bottom:4px;'>#{idx} Subscriber</div>"
                    f"<div><span style='color:#6B7280;'>Subscriber IP/Port：</span><span style='font-family:Consolas,monospace;color:#111827;'>{item.get('subscriber_ip_port', '-')}</span></div>"
                    f"<div><span style='color:#6B7280;'>Event Group ID：</span><span style='font-family:Consolas,monospace;color:#111827;'>{item.get('event_group_id', '-')}</span></div>"
                    f"<div><span style='color:#6B7280;'>Last Subscribe Time：</span><span style='color:#111827;'>{item.get('last_subscribe_time', '-')}</span></div>"
                    f"<div><span style='color:#6B7280;'>Last SubAck Time：</span><span style='color:#111827;'>{item.get('last_suback_time', '-')}</span></div>"
                    f"<div><span style='color:#6B7280;'>Last NACK Time：</span><span style='color:#111827;'>{item.get('last_nack_time', '-')}</span></div>"
                    "</div>"
                )
            detail_lines.append("</div>")

        if not detail_lines:
            detail_lines.append("<div style='color:#6B7280;'>暂无详情</div>")
        self.detail_content_lbl.setText("".join(detail_lines))

        # Toggle between summary and detail view
        show_details = bool(self.data.get("show_details"))
        self.summary_frame.setVisible(not show_details)
        self.detail_frame.setVisible(show_details)
        self.name_lbl.setVisible(not show_details)
        self.detail_btn.setText("返回" if show_details else "详情")
        self.footer.setVisible(not show_details)

        # Update Buttons Styling

        # 1. PIN BUTTON
        if self.is_pinned:
            # ACTIVE/PINNED: Filled Pin Icon
            self.pin_btn.setIcon(create_vector_icon("pin_filled", "#DC2626", 64))
            self.pin_btn.setToolTip("取消置顶")
            self.pin_btn.setStyleSheet("""
                QPushButton { 
                    background-color: #FEF2F2; 
                    border: 1px solid #FECACA; 
                    border-radius: 6px; 
                } 
                QPushButton:hover { 
                    background-color: #FEE2E2;
                    border-color: #EF4444;
                }
            """)
        else:
            # INACTIVE: Outline Pin Icon
            self.pin_btn.setIcon(create_vector_icon("pin_outline", "#94A3B8", 64))
            self.pin_btn.setToolTip("置顶服务")
            self.pin_btn.setStyleSheet("""
                QPushButton { 
                    background-color: transparent; 
                    border: 1px solid transparent; 
                    border-radius: 6px; 
                } 
                QPushButton:hover { 
                    background-color: #F1F5F9; 
                    border-color: #CBD5E1;
                }
            """)

        # 2. HIDE BUTTON
        if self.is_hidden_state:
            # HIDDEN (RESTORE MODE): Eye (Show)
            self.hide_btn.setIcon(create_vector_icon("eye", "#059669", 64))
            self.hide_btn.setToolTip("恢复显示")
            self.hide_btn.setStyleSheet("""
                QPushButton { 
                    background-color: #ECFDF5; 
                    border: 1px solid #A7F3D0; 
                    border-radius: 6px; 
                } 
                QPushButton:hover { 
                    background-color: #D1FAE5;
                     border-color: #10B981;
                }
            """)
        else:
            # VISIBLE (HIDE MODE): Eye with Slash (Hide)
            self.hide_btn.setIcon(create_vector_icon("eye_off", "#94A3B8", 64))
            self.hide_btn.setToolTip("隐藏服务")
            self.hide_btn.setStyleSheet("""
                QPushButton { 
                    background-color: transparent; 
                    border: 1px solid transparent; 
                    border-radius: 6px; 
                } 
                QPushButton:hover { 
                    background-color: #F1F5F9; 
                    border-color: #CBD5E1;
                    color: #EF4444;
                }
            """)

    def apply_style(self):
        # Base Card Style
        base_color = "#FFFFFF"
        border_color = "#E5E7EB"
        shadow_color = QColor(0, 0, 0, 20)

        # Consolidated stylesheet for stability
        style_sheet = f"""
            QFrame#ServiceCard {{
                background-color: {base_color};
                border: 1px solid {border_color};
                border-radius: 8px;
            }}
            QFrame#ServiceCard:hover {{
                border-color: #D1D5DB;
            }}
            QFrame#CardTopBar {{
                background-color: #F9FAFB;
                border-bottom: 1px solid #E5E7EB;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
            }}
            QFrame#CardFooter {{
                background-color: #F9FAFB;
                border-top: 1px solid #E5E7EB;
                border-bottom-left-radius: 8px;
                border-bottom-right-radius: 8px;
            }}
            QWidget#DetailScrollContent {{
                background-color: transparent;
            }}

            QLabel#IndexLabel {{
                color: #9CA3AF;
                font-family: 'Consolas', monospace;
                font-weight: bold;
                font-size: 14px;
                min-width: 24px;
            }}

            /* Status Labels */
            QLabel#StatusLabel_Active {{
                color: #15803D;
                font-weight: 600;
            }}
            QLabel#StatusLabel_Inactive {{
                color: #DC2626;
                font-weight: 600;
            }}

            /* General Button Hover (fallback/base) */
            QPushButton:hover {{
                background-color: #F3F4F6;
            }}
            QPushButton:pressed {{
                background-color: #E5E7EB;
            }}
        """
        self.setStyleSheet(style_sheet)

        # --- Labels ---
        for key, label in self.grid_labels.items():
            label.setStyleSheet("color: #374151; font-size: 12px; font-weight: 500;")

        # --- Shadow Effect ---
        if not self._shadow:
            self._shadow = QGraphicsDropShadowEffect(self)
            self._shadow.setBlurRadius(20)
            self._shadow.setXOffset(0)
            self._shadow.setYOffset(4)
            self._shadow.setColor(shadow_color)
            self.setGraphicsEffect(self._shadow)

    def _on_pin_clicked(self):
        self.action_triggered.emit('pin', self.data)

    def _on_hide_clicked(self):
        action = 'restore' if self.is_hidden_state else 'hide'
        self.action_triggered.emit(action, self.data)

    def _on_detail_clicked(self):
        self.action_triggered.emit('details', self.data)


class SomeIpSignboardView(BaseView):
    # Signals for Controller interaction
    pcap_selected = pyqtSignal(str)
    refresh_requested = pyqtSignal()
    search_changed = pyqtSignal(str)
    show_hidden_toggled = pyqtSignal(bool)
    card_action_triggered = pyqtSignal(str, dict)
    page_changed = pyqtSignal(int)
    page_size_calculated = pyqtSignal(int)
    baseline_time_changed = pyqtSignal(str)

    def setup_ui(self):
        self.page_size = 12

        self.resize_timer = QTimer(self)
        self.resize_timer.setSingleShot(True)
        self.resize_timer.setInterval(200)
        self.resize_timer.timeout.connect(self._recalculate_page_size)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(24, 24, 24, 24)
        self.layout.setSpacing(16)

        header_layout = QHBoxLayout()
        header_text_layout = QVBoxLayout()

        title_lbl = QLabel("SOME/IP-SD 服务看板")
        title_lbl.setStyleSheet("font-size: 24px; font-weight: bold; color: #111827;")
        subtitle_lbl = QLabel("实时监控与服务发现")
        subtitle_lbl.setStyleSheet("font-size: 14px; color: #6B7280;")

        header_text_layout.addWidget(title_lbl)
        header_text_layout.addWidget(subtitle_lbl)
        header_layout.addLayout(header_text_layout)
        header_layout.addStretch()
        self.layout.addLayout(header_layout)

        toolbar_layout = QHBoxLayout()
        toolbar_layout.setSpacing(12)

        self.pcap_input = QLineEdit()
        self.pcap_input.setPlaceholderText("未选择文件 (使用实时流)...")
        self.pcap_input.setReadOnly(True)
        self.pcap_input.setStyleSheet("""
            QLineEdit {
                border: 1px solid #E5E7EB; border-radius: 6px; padding: 6px 12px;
                background-color: #F9FAFB; color: #374151; font-size: 13px;
            }
        """)

        self.baseline_time_edit = QDateTimeEdit(QDateTime.currentDateTime())
        self.baseline_time_edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.baseline_time_edit.setCalendarPopup(True)
        self.baseline_time_edit.setMinimumWidth(190)
        self.baseline_time_edit.setToolTip("设置抓包时间基准：作为 0 时刻，后续报文按文件中的时间间隔累加显示")
        self.baseline_time_edit.setStyleSheet("""
            QDateTimeEdit {
                border: 1px solid #E5E7EB; border-radius: 6px; padding: 6px 10px;
                background-color: white; color: #374151; font-size: 13px;
            }
            QDateTimeEdit:focus { border: 1px solid #3B82F6; }
        """)
        self.baseline_time_edit.dateTimeChanged.connect(
            lambda dt: self.baseline_time_changed.emit(dt.toString("yyyy-MM-dd HH:mm:ss"))
        )

        browse_btn = QPushButton("📂 导入 PCAP")
        browse_btn.setCursor(Qt.PointingHandCursor)
        browse_btn.clicked.connect(self._on_browse_clicked)
        browse_btn.setStyleSheet("""
            QPushButton {
                background-color: #FFFFFF; border: 1px solid #D1D5DB; border-radius: 6px;
                padding: 6px 12px; color: #374151; font-weight: 500; font-size: 13px;
            }
            QPushButton:hover { background-color: #F3F4F6; }
        """)

        toolbar_layout.addWidget(self.pcap_input, 1)
        toolbar_layout.addWidget(QLabel("时间基准:"))
        toolbar_layout.addWidget(self.baseline_time_edit)
        toolbar_layout.addWidget(browse_btn)

        line = QFrame()
        line.setFrameShape(QFrame.VLine)
        line.setFrameShadow(QFrame.Sunken)
        line.setStyleSheet("color: #E5E7EB;")
        toolbar_layout.addWidget(line)

        self.show_hidden_cb = QCheckBox("显示已隐藏")
        self.show_hidden_cb.setStyleSheet("""
            QCheckBox { font-size: 13px; color: #4B5563; }
            QCheckBox::indicator { width: 16px; height: 16px; }
        """)
        self.show_hidden_cb.stateChanged.connect(lambda: self.show_hidden_toggled.emit(self.show_hidden_cb.isChecked()))
        toolbar_layout.addWidget(self.show_hidden_cb)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 搜索服务...")
        self.search_input.setFixedWidth(220)
        self.search_input.setStyleSheet("""
            QLineEdit {
                border: 1px solid #E5E7EB; border-radius: 6px; padding: 6px 12px;
                background-color: white; font-size: 13px; color: #374151;
            }
            QLineEdit:focus { border: 1px solid #3B82F6; }
        """)
        self.search_input.textChanged.connect(lambda text: self.search_changed.emit(text))
        toolbar_layout.addWidget(self.search_input)

        refresh_btn = ModernButton("刷新", "#3B82F6", "↻")
        refresh_btn.setMinimumHeight(32)
        refresh_btn.clicked.connect(self.refresh_requested.emit)
        toolbar_layout.addWidget(refresh_btn)

        self.layout.addLayout(toolbar_layout)

        self.card_list = QListWidget()
        self.card_list.setViewMode(QListWidget.IconMode)
        self.card_list.setResizeMode(QListWidget.Adjust)
        self.card_list.setSpacing(10)
        self.card_list.setMovement(QListWidget.Static)
        self.card_list.setDragDropMode(QAbstractItemView.NoDragDrop)
        self.card_list.setDefaultDropAction(Qt.IgnoreAction)
        self.card_list.setStyleSheet("""
            QListWidget {
                background-color: #F3F4F6;
                border: none;
                outline: none;
            }
            QListWidget::item {
                background-color: transparent;
                border: none;
                margin: 0px;
            }
            QListWidget::item:selected {
                background-color: transparent;
                border: none;
            }
            QListWidget::item:hover {
                background-color: transparent;
            }
        """)
        self.layout.addWidget(self.card_list)

        pagination_layout = QHBoxLayout()
        pagination_layout.addStretch()

        self.prev_btn = QPushButton("◀ 上一页")
        self.prev_btn.setCursor(Qt.PointingHandCursor)
        self.prev_btn.clicked.connect(lambda: self._on_page_nav(-1))
        self.prev_btn.setStyleSheet("QPushButton { border: 1px solid #E5E7EB; border-radius: 6px; padding: 6px 12px; background: white; color: #374151; } QPushButton:hover { background: #F9FAFB; }")

        self.page_lbl = QLabel("第 1 / 1 页")
        self.page_lbl.setStyleSheet("color: #4B5563; font-weight: 600; margin: 0 10px;")

        self.next_btn = QPushButton("下一页 ▶")
        self.next_btn.setCursor(Qt.PointingHandCursor)
        self.next_btn.clicked.connect(lambda: self._on_page_nav(1))
        self.next_btn.setStyleSheet("QPushButton { border: 1px solid #E5E7EB; border-radius: 6px; padding: 6px 12px; background: white; color: #374151; } QPushButton:hover { background: #F9FAFB; }")

        pagination_layout.addWidget(self.prev_btn)
        pagination_layout.addWidget(self.page_lbl)
        pagination_layout.addWidget(self.next_btn)
        pagination_layout.addStretch()
        self.layout.addLayout(pagination_layout)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.resize_timer.start()

    def update_view_data(self, page_items, total_pages, current_page, pinned_ids, hidden_ids):
        self.page_lbl.setText(f"第 {current_page} / {total_pages} 页")
        self.prev_btn.setEnabled(current_page > 1)
        self.next_btn.setEnabled(current_page < total_pages)
        self.current_page = current_page

        current_count = self.card_list.count()
        target_count = len(page_items)

        if current_count < target_count:
            for _ in range(target_count - current_count):
                list_item = QListWidgetItem(self.card_list)
                list_item.setSizeHint(QSize(320, 210))
                card = ServiceCard({}, parent=self)
                card.action_triggered.connect(self._handle_card_action)
                self.card_list.setItemWidget(list_item, card)
        elif current_count > target_count:
            for _ in range(current_count - target_count):
                self.card_list.takeItem(self.card_list.count() - 1)

        for i in range(target_count):
            list_item = self.card_list.item(i)
            item_data = page_items[i]
            card_height = 520 if item_data.get('show_details') else 210
            list_item.setSizeHint(QSize(320, card_height))
            card = self.card_list.itemWidget(list_item)
            uid = item_data['uid']
            card.update_content(item_data, uid in pinned_ids, uid in hidden_ids)

    def _handle_card_action(self, action, data):
        self.card_action_triggered.emit(action, data)

    def _on_browse_clicked(self):
        fname, _ = QFileDialog.getOpenFileName(self, '选择 PCAP 文件', '', 'PCAP Files (*.pcap *.pcapng)')
        if fname:
            self.pcap_input.setText(fname)
            self.pcap_selected.emit(fname)

    def _on_page_nav(self, direction):
        new_page = self.current_page + direction
        self.page_changed.emit(new_page)
        self.card_list.scrollToTop()

    def _recalculate_page_size(self):
        if not self.card_list.isVisible():
            return

        list_size = self.card_list.viewport().size()
        width = list_size.width()
        height = list_size.height()
        card_w = 320 + 10
        card_h = 210 + 10

        if width < card_w or height < card_h:
            return

        cols = max(1, width // card_w)
        rows = max(1, height // card_h)
        new_page_size = max(1, cols * rows)

        if new_page_size != self.page_size:
            self.page_size = new_page_size
            self.page_size_calculated.emit(new_page_size)

    def get_baseline_time_text(self):
        return self.baseline_time_edit.dateTime().toString("yyyy-MM-dd HH:mm:ss")

