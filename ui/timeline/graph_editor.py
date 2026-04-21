from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QWidget, QComboBox
from PySide6.QtCore import Qt, QPointF, QRect, QRectF
from PySide6.QtGui import QPainter, QColor, QPen, QPainterPath, QFont, QCursor
from core.signal_hub import global_signals

class GraphCanvas(QWidget):
    def __init__(self, backend_clip, prop_name, canvas_ref=None, parent=None):
        super().__init__(parent)
        self.backend_clip = backend_clip
        self.prop_name = prop_name
        self.canvas_ref = canvas_ref
        self.setMinimumSize(600, 300)
        self.setMouseTracking(True)
        
        self.dragging_idx = -1
        self.hover_idx = -1
        
        # Panning/Zooming
        self.pan_x = 0
        self.pan_y = 0
        self.scale_x = 1.0
        self.scale_y = 1.0
        self._drag_start_pos = None

    def set_prop(self, prop_name):
        self.prop_name = prop_name
        self.update()

    def get_track(self):
        if not self.backend_clip or not hasattr(self.backend_clip, 'animations'): return None
        return self.backend_clip.animations.get(self.prop_name)

    def _get_value_bounds(self):
        track = self.get_track()
        if not track or not track.keyframes: return 0, 100, 0, 100
        
        min_v = min((kf.value for kf in track.keyframes), default=0)
        max_v = max((kf.value for kf in track.keyframes), default=100)
        min_t = min((kf.time for kf in track.keyframes), default=0)
        max_t = max((kf.time for kf in track.keyframes), default=100)
        
        if min_v == max_v: min_v, max_v = min_v - 10, max_v + 10
        if min_t == max_t: min_t, max_t = min_t - 10, max_t + 10
        
        padding_v = (max_v - min_v) * 0.2
        padding_t = (max_t - min_t) * 0.1
        
        return min_t - padding_t, max_t + padding_t, min_v - padding_v, max_v + padding_v

    def _map_to_screen(self, time, value, bounds):
        min_t, max_t, min_v, max_v = bounds
        
        rect = self.rect()
        w, h = rect.width(), rect.height()
        
        norm_t = (time - min_t) / (max_t - min_t)
        norm_v = (value - min_v) / (max_v - min_v)
        
        sx = norm_t * w * self.scale_x + self.pan_x
        sy = h - (norm_v * h * self.scale_y) + self.pan_y
        return sx, sy

    def _map_from_screen(self, sx, sy, bounds):
        min_t, max_t, min_v, max_v = bounds
        
        rect = self.rect()
        w, h = rect.width(), rect.height()
        
        norm_t = (sx - self.pan_x) / (w * self.scale_x)
        norm_v = (h - (sy - self.pan_y)) / (h * self.scale_y)
        
        time = min_t + norm_t * (max_t - min_t)
        value = min_v + norm_v * (max_v - min_v)
        return time, value

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect()
        painter.fillRect(rect, QColor("#111111"))

        track = self.get_track()
        if not track or not track.keyframes:
            painter.setPen(QColor("#555555"))
            painter.drawText(rect, Qt.AlignCenter, "No Keyframes for this property.")
            return

        bounds = self._get_value_bounds()
        
        # Draw grid
        painter.setPen(QPen(QColor("#222222"), 1))
        for i in range(1, 10):
            y = i * rect.height() / 10
            painter.drawLine(0, y, rect.width(), y)
            x = i * rect.width() / 10
            painter.drawLine(x, 0, x, rect.height())

        path = QPainterPath()
        sorted_kfs = sorted(track.keyframes, key=lambda k: k.time)
        
        points = []
        for kf in sorted_kfs:
            sx, sy = self._map_to_screen(kf.time, kf.value, bounds)
            points.append(QPointF(sx, sy))
            
        if points:
            path.moveTo(points[0])
            for pt in points[1:]:
                path.lineTo(pt)
                
        painter.setPen(QPen(QColor("#e66b2c"), 2))
        painter.drawPath(path)
        
        # Draw points
        for i, pt in enumerate(points):
            is_hover = (i == self.hover_idx)
            is_drag = (i == self.dragging_idx)
            
            radius = 6 if (is_hover or is_drag) else 4
            
            painter.setBrush(QColor("#ffffff") if is_hover else QColor("#e66b2c"))
            painter.setPen(QPen(QColor("#ffffff"), 1) if (is_hover or is_drag) else Qt.NoPen)
            painter.drawEllipse(pt, radius, radius)
            
            # Label
            if is_hover or is_drag:
                kf = sorted_kfs[i]
                painter.setPen(QColor("#aaaaaa"))
                painter.setFont(QFont("Arial", 8))
                painter.drawText(int(pt.x()) + 10, int(pt.y()) - 10, f"t:{kf.time:.1f} v:{kf.value:.1f}")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            track = self.get_track()
            if not track or not track.keyframes: return
            
            bounds = self._get_value_bounds()
            sorted_kfs = sorted(track.keyframes, key=lambda k: k.time)
            
            hit_idx = -1
            for i, kf in enumerate(sorted_kfs):
                sx, sy = self._map_to_screen(kf.time, kf.value, bounds)
                if (event.position().x() - sx)**2 + (event.position().y() - sy)**2 < 100:
                    hit_idx = i
                    break
                    
            if hit_idx != -1:
                self.dragging_idx = hit_idx
                self.setCursor(Qt.ClosedHandCursor)
            else:
                self._drag_start_pos = event.position()
                
    def mouseMoveEvent(self, event):
        track = self.get_track()
        if not track or not track.keyframes: return
        bounds = self._get_value_bounds()
        sorted_kfs = sorted(track.keyframes, key=lambda k: k.time)
        
        if self.dragging_idx != -1:
            kf = sorted_kfs[self.dragging_idx]
            new_t, new_v = self._map_from_screen(event.position().x(), event.position().y(), bounds)
            
            # constrain time to neighbors
            min_allowed_t = sorted_kfs[self.dragging_idx - 1].time + 0.1 if self.dragging_idx > 0 else 0
            max_allowed_t = sorted_kfs[self.dragging_idx + 1].time - 0.1 if self.dragging_idx < len(sorted_kfs) - 1 else float('inf')
            
            kf.time = max(min_allowed_t, min(new_t, max_allowed_t))
            kf.value = new_v
            
            self.update()
            
            if self.canvas_ref:
                self.canvas_ref.update()
            if hasattr(global_signals, 'clip_updated'):
                global_signals.clip_updated.emit(self.backend_clip)
                
        elif self._drag_start_pos:
            # Pan
            dx = event.position().x() - self._drag_start_pos.x()
            dy = event.position().y() - self._drag_start_pos.y()
            self.pan_x += dx
            self.pan_y += dy
            self._drag_start_pos = event.position()
            self.update()
        else:
            hit_idx = -1
            for i, kf in enumerate(sorted_kfs):
                sx, sy = self._map_to_screen(kf.time, kf.value, bounds)
                if (event.position().x() - sx)**2 + (event.position().y() - sy)**2 < 100:
                    hit_idx = i
                    break
            
            if hit_idx != self.hover_idx:
                self.hover_idx = hit_idx
                self.setCursor(Qt.PointingHandCursor if hit_idx != -1 else Qt.ArrowCursor)
                self.update()

    def mouseReleaseEvent(self, event):
        self.dragging_idx = -1
        self._drag_start_pos = None
        self.setCursor(Qt.ArrowCursor)
        if self.canvas_ref and hasattr(self.canvas_ref, 'save_state'):
            self.canvas_ref.save_state()

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        zoom = 1.1 if delta > 0 else 0.9
        
        if event.modifiers() == Qt.ControlModifier:
            self.scale_x *= zoom
        elif event.modifiers() == Qt.ShiftModifier:
            self.scale_y *= zoom
        else:
            self.scale_x *= zoom
            self.scale_y *= zoom
        self.update()

class GraphEditorDialog(QDialog):
    def __init__(self, item, backend_clip, hit_kfs, canvas=None, parent=None):
        super().__init__(parent)
        self.item = item
        self.backend_clip = backend_clip
        self.hit_kfs = hit_kfs
        self.timeline_canvas = canvas
        
        self.setWindowTitle("Keyframe Graph Editor")
        self.setMinimumSize(700, 400)
        self.setStyleSheet("background-color: #1a1a1a; color: #ffffff;")
        
        layout = QVBoxLayout(self)
        
        # Top Bar: Property Selector
        top_bar = QHBoxLayout()
        lbl = QLabel("Edit Property:")
        lbl.setFont(QFont("Arial", 10, QFont.Bold))
        top_bar.addWidget(lbl)
        
        self.prop_combo = QComboBox()
        self.prop_combo.setStyleSheet("""
            QComboBox { background-color: #333333; border: 1px solid #444444; border-radius: 4px; padding: 4px; }
            QComboBox::drop-down { border: none; }
        """)
        
        # Populate all animated properties
        if hasattr(backend_clip, 'animations'):
            for prop_name, track in backend_clip.animations.items():
                if track.keyframes:
                    self.prop_combo.addItem(prop_name.replace('_', ' ').title(), prop_name)
                    
        # Set current index to the clicked one
        if self.hit_kfs:
            clicked_prop = self.hit_kfs[0][0]
            idx = self.prop_combo.findData(clicked_prop)
            if idx >= 0:
                self.prop_combo.setCurrentIndex(idx)
                
        self.prop_combo.currentIndexChanged.connect(self._on_prop_changed)
        top_bar.addWidget(self.prop_combo)
        top_bar.addStretch()
        
        layout.addLayout(top_bar)
        
        current_prop = self.prop_combo.currentData() if self.prop_combo.count() > 0 else None
        self.canvas = GraphCanvas(self.backend_clip, current_prop, self.timeline_canvas)
        layout.addWidget(self.canvas)
        
        # Bottom Bar: Instructions & Close
        btn_layout = QHBoxLayout()
        instr = QLabel("Drag points to edit Time and Value. Scroll to zoom (Ctrl=X, Shift=Y). Drag background to pan.")
        instr.setStyleSheet("color: #888888; font-size: 11px;")
        btn_layout.addWidget(instr)
        
        btn_layout.addStretch()
        
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet("background-color: #e66b2c; padding: 6px 16px; border-radius: 4px; font-weight: bold;")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)

    def _on_prop_changed(self, index):
        prop = self.prop_combo.itemData(index)
        if prop:
            self.canvas.set_prop(prop)