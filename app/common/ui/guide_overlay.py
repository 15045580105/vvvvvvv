from PyQt5 import QtWidgets, QtCore, QtGui

class GuideOverlay(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.steps = []
        self.current_step_index = 0

        # Setup UI components for the overlay
        self.info_widget = QtWidgets.QWidget(self)
        self.info_widget.setStyleSheet("""
            QWidget {
                background-color: white;
                border-radius: 8px;
                padding: 15px;
            }
            QLabel {
                color: #333;
                background-color: transparent;
                border: none;
            }
            QPushButton {
                background-color: #007AFF;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 16px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #0062CC;
            }
            QPushButton#btn_prev {
                background-color: #F0F0F0;
                color: #333;
                border: 1px solid #DDD;
            }
            QPushButton#btn_prev:hover {
                background-color: #E0E0E0;
            }
        """)

        # Add shadow to info widget
        shadow = QtWidgets.QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QtGui.QColor(0, 0, 0, 80))
        shadow.setOffset(0, 4)
        self.info_widget.setGraphicsEffect(shadow)

        self.info_layout = QtWidgets.QVBoxLayout(self.info_widget)
        self.info_layout.setSpacing(10)
        self.info_layout.setContentsMargins(10, 10, 10, 10)

        self.title_label = QtWidgets.QLabel()
        self.title_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #111;")
        self.desc_label = QtWidgets.QLabel()
        self.desc_label.setStyleSheet("font-size: 14px; color: #555; line-height: 1.4;")
        self.desc_label.setWordWrap(True)
        self.desc_label.setMinimumWidth(250)

        self.btn_layout = QtWidgets.QHBoxLayout()
        self.btn_prev = QtWidgets.QPushButton("上一步")
        self.btn_prev.setObjectName("btn_prev")
        self.btn_next = QtWidgets.QPushButton("下一步")
        self.btn_finish = QtWidgets.QPushButton("开始使用")

        self.btn_layout.addWidget(self.btn_prev)
        self.btn_layout.addStretch()
        self.btn_layout.addWidget(self.btn_next)
        self.btn_layout.addWidget(self.btn_finish)

        self.info_layout.addWidget(self.title_label)
        self.info_layout.addWidget(self.desc_label)
        self.info_layout.addLayout(self.btn_layout)

        self.btn_prev.clicked.connect(self.prev_step)
        self.btn_next.clicked.connect(self.next_step)
        self.btn_finish.clicked.connect(self.close_guide)

        self.info_widget.hide()
        self.hide()

    def add_step(self, target, title, description):
        self.steps.append({
            "target": target,
            "title": title,
            "description": description
        })

    def start(self):
        if not self.steps:
            return
        self.current_step_index = 0
        if self.parent():
            self.resize(self.parent().size())
        self.show()
        self.raise_()
        self.update_step()

    def close_guide(self):
        self.hide()

    def update_step(self):
        if not 0 <= self.current_step_index < len(self.steps):
            return

        step = self.steps[self.current_step_index]

        self.title_label.setText(step["title"])
        self.desc_label.setText(step["description"])

        self.btn_prev.setVisible(self.current_step_index > 0)
        self.btn_next.setVisible(self.current_step_index < len(self.steps) - 1)
        self.btn_finish.setVisible(self.current_step_index == len(self.steps) - 1)

        self.info_widget.adjustSize()
        self.info_widget.show()
        self.update() # Trigger repaint

    def prev_step(self):
        if self.current_step_index > 0:
            self.current_step_index -= 1
            self.update_step()

    def next_step(self):
        if self.current_step_index < len(self.steps) - 1:
            self.current_step_index += 1
            self.update_step()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        if not self.steps:
            # Just draw dark background if no steps (shouldn't happen usually)
            painter.fillRect(self.rect(), QtGui.QColor(0, 0, 0, 160))
            return

        step = self.steps[self.current_step_index]
        target = step["target"]

        # Create the path for the background (whole screen)
        path = QtGui.QPainterPath()
        path.addRect(QtCore.QRectF(self.rect()))

        highlight_rect = QtCore.QRect()

        if target and target.isVisible():
            try:
                # Calculate target rect in overlay coordinates
                top_left = target.mapToGlobal(QtCore.QPoint(0, 0))
                target_pos = self.mapFromGlobal(top_left)
                target_rect = QtCore.QRect(target_pos, target.size())

                # Add padding
                padding = 5
                highlight_rect = target_rect.adjusted(-padding, -padding, padding, padding)

                # Create path for the hole
                hole_path = QtGui.QPainterPath()
                hole_path.addRoundedRect(QtCore.QRectF(highlight_rect), 8, 8)

                # Subtract hole from background
                path = path.subtracted(hole_path)

            except Exception as e:
                print(f"Error calculating target rect: {e}")

        # Draw the background with hole
        painter.fillPath(path, QtGui.QColor(0, 0, 0, 160))

        if not highlight_rect.isNull():
            # Draw border around the hole
            painter.setPen(QtGui.QPen(QtGui.QColor("#007AFF"), 3))
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.drawRoundedRect(highlight_rect, 8, 8)

            # Position the info widget
            self.position_info_widget(highlight_rect)

            # Draw Arrow
            self.draw_arrow(painter, highlight_rect)
        else:
            # Center info widget if no target
            self.info_widget.move(
                self.width() // 2 - self.info_widget.width() // 2,
                self.height() // 2 - self.info_widget.height() // 2
            )

    def position_info_widget(self, highlight_rect):
        info_w = self.info_widget.width()
        info_h = self.info_widget.height()

        # Determine best position
        # Check if target is very tall (like a sidebar)
        is_tall = highlight_rect.height() > self.height() * 0.5

        pos_x = 0
        pos_y = 0
        position_mode = "bottom" # bottom, top, right, left

        if is_tall:
            # Try placing to the right
            if highlight_rect.right() + info_w + 20 < self.width():
                pos_x = highlight_rect.right() + 20
                pos_y = highlight_rect.center().y() - info_h // 2
                position_mode = "right"
            # Try placing to the left
            elif highlight_rect.left() - info_w - 20 > 0:
                pos_x = highlight_rect.left() - info_w - 20
                pos_y = highlight_rect.center().y() - info_h // 2
                position_mode = "left"
            else:
                # Fallback to center
                pos_x = self.width() // 2 - info_w // 2
                pos_y = self.height() // 2 - info_h // 2
                position_mode = "center"
        else:
            # Standard top/bottom placement
            space_below = self.height() - highlight_rect.bottom()
            space_above = highlight_rect.top()

            # Prefer below
            if space_below >= info_h + 20:
                pos_y = highlight_rect.bottom() + 20
                position_mode = "bottom"
            elif space_above >= info_h + 20:
                pos_y = highlight_rect.top() - info_h - 20
                position_mode = "top"
            else:
                # Not enough space, pick the larger one
                if space_below > space_above:
                    pos_y = highlight_rect.bottom() + 20
                    position_mode = "bottom"
                else:
                    pos_y = highlight_rect.top() - info_h - 20
                    position_mode = "top"

            # Horizontal centering for top/bottom
            pos_x = highlight_rect.center().x() - info_w // 2

        # Clamp to screen boundaries
        if pos_x < 10: pos_x = 10
        if pos_x + info_w > self.width() - 10:
            pos_x = self.width() - info_w - 10

        if pos_y < 10: pos_y = 10
        if pos_y + info_h > self.height() - 10:
            pos_y = self.height() - info_h - 10

        self.info_widget.move(int(pos_x), int(pos_y))
        self.current_pos_mode = position_mode # Store for arrow drawing

    def draw_arrow(self, painter, highlight_rect):
        if not hasattr(self, 'current_pos_mode'):
            return

        mode = self.current_pos_mode
        info_rect = self.info_widget.geometry()

        start_pos = QtCore.QPoint()
        end_pos = QtCore.QPoint()

        if mode == "bottom":
            start_pos = QtCore.QPoint(int(highlight_rect.center().x()), int(info_rect.top()))
            end_pos = QtCore.QPoint(int(highlight_rect.center().x()), int(highlight_rect.bottom() + 8))
        elif mode == "top":
            start_pos = QtCore.QPoint(int(highlight_rect.center().x()), int(info_rect.bottom()))
            end_pos = QtCore.QPoint(int(highlight_rect.center().x()), int(highlight_rect.top() - 8))
        elif mode == "right":
            start_pos = QtCore.QPoint(int(info_rect.left()), int(highlight_rect.center().y()))
            end_pos = QtCore.QPoint(int(highlight_rect.right() + 8), int(highlight_rect.center().y()))
        elif mode == "left":
            start_pos = QtCore.QPoint(int(info_rect.right()), int(highlight_rect.center().y()))
            end_pos = QtCore.QPoint(int(highlight_rect.left() - 8), int(highlight_rect.center().y()))
        else:
            return # No arrow for center/overlap

        # Clamp arrow start/end X to be within rects (in case of clamping)
        # This is a simple check, can be improved

        painter.setPen(QtGui.QPen(QtCore.Qt.white, 2, QtCore.Qt.DashLine))
        painter.drawLine(start_pos, end_pos)

        # Draw small circle at the end
        painter.setBrush(QtCore.Qt.white)
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawEllipse(end_pos, 3, 3)


    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update()

    def mousePressEvent(self, event):
        # Consume mouse events
        pass

