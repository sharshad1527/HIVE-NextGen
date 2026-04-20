from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QWidget
from PySide6.QtCore import Qt, QPoint, QRect, QRectF
from PySide6.QtGui import QPainter, QColor, QPen, QPainterPath, QFont

class GraphCanvas(QWidget):
    def __init__(self, keyframe_tuple, parent=None):
        super().__init__(parent)
        self.prop_name, self.kf = keyframe_tuple
        self.setMinimumSize(400, 200)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect()
        painter.fillRect(rect, QColor("#111111"))

        painter.setPen(QPen(QColor("#333333"), 1))
        for i in range(1, 4):
            y = i * rect.height() / 4
            painter.drawLine(0, y, rect.width(), y)
            x = i * rect.width() / 4
            painter.drawLine(x, 0, x, rect.height())

        from core.models import Easing
        path = QPainterPath()
        
        points = 100
        for i in range(points + 1):
            t = i / points
            
            y_val = t
            if self.kf.easing == Easing.EASE_IN:
                y_val = t * t
            elif self.kf.easing == Easing.EASE_OUT:
                y_val = t * (2 - t)
            elif self.kf.easing == Easing.EASE_IN_OUT:
                y_val = t * t * (3 - 2 * t)
            elif self.kf.easing == Easing.CUBIC_IN:
                y_val = t * t * t
            elif self.kf.easing == Easing.CUBIC_OUT:
                import math
                y_val = 1 - math.pow(1 - t, 3)
            elif self.kf.easing == Easing.BOUNCE:
                n1 = 7.5625
                d1 = 2.75
                if t < 1 / d1:
                    y_val = n1 * t * t
                elif t < 2 / d1:
                    t -= 1.5 / d1
                    y_val = n1 * t * t + 0.75
                elif t < 2.5 / d1:
                    t -= 2.25 / d1
                    y_val = n1 * t * t + 0.9375
                else:
                    t -= 2.625 / d1
                    y_val = n1 * t * t + 0.984375
            elif self.kf.easing == Easing.ELASTIC:
                import math
                c4 = (2 * math.pi) / 3
                if t == 0:
                    y_val = 0
                elif t == 1:
                    y_val = 1
                else:
                    y_val = -math.pow(2, 10 * t - 10) * math.sin((t * 10 - 10.75) * c4)

            px = i * rect.width() / points
            py = rect.height() - (y_val * rect.height())
            
            if i == 0:
                path.moveTo(px, py)
            else:
                path.lineTo(px, py)

        painter.setPen(QPen(QColor("#e66b2c"), 2))
        painter.drawPath(path)

        painter.setBrush(QColor("#e66b2c"))
        painter.drawEllipse(QPoint(0, rect.height()), 4, 4)
        painter.drawEllipse(QPoint(rect.width(), 0), 4, 4)

class GraphEditorDialog(QDialog):
    def __init__(self, item, backend_clip, hit_kfs, parent=None):
        super().__init__(parent)
        self.item = item
        self.backend_clip = backend_clip
        self.hit_kfs = hit_kfs
        
        self.setWindowTitle("Keyframe Graph Editor")
        self.setMinimumSize(500, 300)
        self.setStyleSheet("background-color: #1a1a1a; color: #ffffff;")
        
        layout = QVBoxLayout(self)
        
        title = ", ".join([prop.replace('_', ' ').title() for prop, kf in hit_kfs])
        lbl = QLabel(f"Editing Easing for: {title}")
        lbl.setFont(QFont("Arial", 12, QFont.Bold))
        layout.addWidget(lbl)
        
        # We just visualize the first selected keyframe for now
        self.canvas = GraphCanvas(self.hit_kfs[0])
        layout.addWidget(self.canvas)
        
        btn_layout = QHBoxLayout()
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet("background-color: #333333; padding: 5px 15px; border-radius: 3px;")
        close_btn.clicked.connect(self.accept)
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)