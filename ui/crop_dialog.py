# ui/crop_dialog.py
import os
import qtawesome as qta
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                               QPushButton, QComboBox, QWidget, QFrame, QGridLayout)
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QImage, QPixmap, QPainterPath

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False


class CropCanvas(QWidget):
    """Visual interactive canvas for cropping media with aspect ratio locking."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(400, 300)
        self.setMouseTracking(True)
        
        self.pixmap = None
        self.img_w = 0
        self.img_h = 0
        
        # Crop bounds in relative coordinates (0.0 to 1.0)
        self.crop_x = 0.0
        self.crop_y = 0.0
        self.crop_w = 1.0
        self.crop_h = 1.0
        
        self.preset = "Original"
        self.target_ratio = None  # Absolute target aspect ratio (W / H)
        
        # Interaction state
        self.active_handle = None
        self.drag_start_pos = None
        self.drag_start_crop = None
        
        # UI Metrics
        self.handle_size = 12
        self.handle_hitbox = 20

    def set_image_from_item(self, item, playhead_logical):
        """Extracts the exact frame using OpenCV for video, or loads the image directly."""
        file_path = item.get("file_path")
        if not file_path or not os.path.exists(file_path):
            return

        if item["type"] == "video" and CV2_AVAILABLE:
            cap = cv2.VideoCapture(file_path)
            
            # Find the exact local millisecond to extract the frame accurately
            trim_in = item.get("trim_in", 0)
            if isinstance(item.get("applied_effects"), dict):
                trim_in = max(trim_in, item["applied_effects"].get("source_in", 0) * 10)
                
            local_ms = trim_in
            if item["x"] <= playhead_logical <= item["x"] + item["w"]:
                local_ms = ((playhead_logical - item["x"]) * 10) + trim_in
                
            cap.set(cv2.CAP_PROP_POS_MSEC, local_ms)
            ret, frame = cap.read()
            if not ret:
                cap.set(cv2.CAP_PROP_POS_MSEC, 0)
                ret, frame = cap.read()
                
            if ret:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = frame.shape
                bytes_per_line = ch * w
                qimg = QImage(frame.data, w, h, bytes_per_line, QImage.Format_RGB888).copy()
                self.pixmap = QPixmap.fromImage(qimg)
            cap.release()
            
        elif item["type"] == "image":
            self.pixmap = QPixmap(file_path)

        if self.pixmap and not self.pixmap.isNull():
            self.img_w = self.pixmap.width()
            self.img_h = self.pixmap.height()
            
        self.update()

    def load_state(self, x, y, w, h, preset):
        """Loads percentage-based state (0-100) from backend to relative coordinates (0-1)."""
        self.crop_x = max(0.0, min(1.0, x / 100.0))
        self.crop_y = max(0.0, min(1.0, y / 100.0))
        self.crop_w = max(0.05, min(1.0 - self.crop_x, w / 100.0))
        self.crop_h = max(0.05, min(1.0 - self.crop_y, h / 100.0))
        self.set_preset(preset)
        
    def get_state(self):
        """Returns percentages ready for the backend."""
        return {
            "crop_x": round(self.crop_x * 100, 2),
            "crop_y": round(self.crop_y * 100, 2),
            "crop_w": round(self.crop_w * 100, 2),
            "crop_h": round(self.crop_h * 100, 2),
            "crop_preset": self.preset
        }

    def set_preset(self, preset):
        self.preset = preset
        ratios = {"16:9": 16/9, "9:16": 9/16, "1:1": 1.0, "4:3": 4/3, "3:4": 3/4}
        
        if preset in ratios:
            self.target_ratio = ratios[preset]
            self._enforce_aspect_ratio_center()
        elif preset == "Original":
            self.target_ratio = self.img_w / self.img_h if self.img_h > 0 else 1.0
            self._enforce_aspect_ratio_center()
        else:
            self.target_ratio = None
            
        self.update()

    def _enforce_aspect_ratio_center(self):
        """Instantly fixes the crop box to the target ratio without leaving image bounds."""
        if not self.target_ratio or self.img_w == 0 or self.img_h == 0:
            return
            
        current_abs_w = self.crop_w * self.img_w
        current_abs_h = self.crop_h * self.img_h
        
        new_abs_w = current_abs_w
        new_abs_h = current_abs_w / self.target_ratio
        
        if new_abs_h > self.img_h:
            new_abs_h = self.img_h
            new_abs_w = new_abs_h * self.target_ratio
            
        if new_abs_w > self.img_w:
            new_abs_w = self.img_w
            new_abs_h = new_abs_w / self.target_ratio

        self.crop_w = new_abs_w / self.img_w
        self.crop_h = new_abs_h / self.img_h
        
        # Center it around current center
        cx = self.crop_x + (current_abs_w / self.img_w) / 2
        cy = self.crop_y + (current_abs_h / self.img_h) / 2
        
        self.crop_x = min(max(cx - self.crop_w / 2, 0.0), 1.0 - self.crop_w)
        self.crop_y = min(max(cy - self.crop_h / 2, 0.0), 1.0 - self.crop_h)

    def _get_draw_metrics(self):
        """Calculates where the image is drawn inside the widget."""
        if not self.pixmap or self.pixmap.isNull():
            return None
        
        scaled = self.pixmap.scaled(self.rect().size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        dx = (self.width() - scaled.width()) / 2
        dy = (self.height() - scaled.height()) / 2
        return dx, dy, scaled.width(), scaled.height(), scaled

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#111111"))

        metrics = self._get_draw_metrics()
        if not metrics:
            painter.setPen(QColor("#555555"))
            painter.drawText(self.rect(), Qt.AlignCenter, "No Media Available")
            return

        dx, dy, sw, sh, scaled_pixmap = metrics
        
        # 1. Draw Image
        painter.drawPixmap(int(dx), int(dy), scaled_pixmap)

        # Calculate Crop Rect in Widget Space
        cx = dx + (self.crop_x * sw)
        cy = dy + (self.crop_y * sh)
        cw = self.crop_w * sw
        ch = self.crop_h * sh

        # 2. Draw Dark Overlay outside crop rect
        painter.fillRect(int(dx), int(dy), int(sw), int(cy - dy), QColor(0, 0, 0, 160)) # Top
        painter.fillRect(int(dx), int(cy + ch), int(sw), int((dy + sh) - (cy + ch)), QColor(0, 0, 0, 160)) # Bottom
        painter.fillRect(int(dx), int(cy), int(cx - dx), int(ch), QColor(0, 0, 0, 160)) # Left
        painter.fillRect(int(cx + cw), int(cy), int((dx + sw) - (cx + cw)), int(ch), QColor(0, 0, 0, 160)) # Right

        # 3. Draw Rule of Thirds Grid
        painter.setPen(QPen(QColor(255, 255, 255, 100), 1, Qt.DashLine))
        painter.drawLine(int(cx + cw/3), int(cy), int(cx + cw/3), int(cy + ch))
        painter.drawLine(int(cx + 2*cw/3), int(cy), int(cx + 2*cw/3), int(cy + ch))
        painter.drawLine(int(cx), int(cy + ch/3), int(cx + cw), int(cy + ch/3))
        painter.drawLine(int(cx), int(cy + 2*ch/3), int(cx + cw), int(cy + 2*ch/3))

        # 4. Draw Border
        painter.setPen(QPen(QColor("#e66b2c"), 2))
        painter.drawRect(QRectF(cx, cy, cw, ch))

        # 5. Draw Thick Corner Handles
        painter.setPen(QPen(Qt.white, 4))
        l = 15 # handle length
        # TL
        painter.drawLine(int(cx), int(cy+l), int(cx), int(cy))
        painter.drawLine(int(cx), int(cy), int(cx+l), int(cy))
        # TR
        painter.drawLine(int(cx+cw-l), int(cy), int(cx+cw), int(cy))
        painter.drawLine(int(cx+cw), int(cy), int(cx+cw), int(cy+l))
        # BR
        painter.drawLine(int(cx+cw), int(cy+ch-l), int(cx+cw), int(cy+ch))
        painter.drawLine(int(cx+cw), int(cy+ch), int(cx+cw-l), int(cy+ch))
        # BL
        painter.drawLine(int(cx), int(cy+ch-l), int(cx), int(cy+ch))
        painter.drawLine(int(cx), int(cy+ch), int(cx+l), int(cy+ch))

    def _get_handle(self, pos):
        """Determines which part of the crop box is hovered/clicked."""
        metrics = self._get_draw_metrics()
        if not metrics: return None
        dx, dy, sw, sh, _ = metrics
        
        cx = dx + (self.crop_x * sw)
        cy = dy + (self.crop_y * sh)
        cw = self.crop_w * sw
        ch = self.crop_h * sh
        
        x, y = pos.x(), pos.y()
        h = self.handle_hitbox
        
        if abs(x - cx) < h and abs(y - cy) < h: return "TL"
        if abs(x - (cx + cw)) < h and abs(y - cy) < h: return "TR"
        if abs(x - (cx + cw)) < h and abs(y - (cy + ch)) < h: return "BR"
        if abs(x - cx) < h and abs(y - (cy + ch)) < h: return "BL"
        
        if abs(y - cy) < h and cx < x < cx + cw: return "T"
        if abs(y - (cy + ch)) < h and cx < x < cx + cw: return "B"
        if abs(x - cx) < h and cy < y < cy + ch: return "L"
        if abs(x - (cx + cw)) < h and cy < y < cy + ch: return "R"
        
        if cx < x < cx + cw and cy < y < cy + ch: return "CENTER"
        return None

    def mouseMoveEvent(self, event):
        if not self.active_handle:
            handle = self._get_handle(event.position())
            if handle in ["TL", "BR"]: self.setCursor(Qt.SizeFDiagCursor)
            elif handle in ["TR", "BL"]: self.setCursor(Qt.SizeBDiagCursor)
            elif handle in ["L", "R"]: self.setCursor(Qt.SizeHorCursor)
            elif handle in ["T", "B"]: self.setCursor(Qt.SizeVerCursor)
            elif handle == "CENTER": self.setCursor(Qt.SizeAllCursor)
            else: self.setCursor(Qt.ArrowCursor)
            return

        metrics = self._get_draw_metrics()
        if not metrics: return
        dx, dy, sw, sh, _ = metrics

        rel_x = max(0.0, min(1.0, (event.position().x() - dx) / sw))
        rel_y = max(0.0, min(1.0, (event.position().y() - dy) / sh))
        
        start_crop = self.drag_start_crop
        ox, oy, ow, oh = start_crop
        
        if self.active_handle == "CENTER":
            start_rel_x = (self.drag_start_pos.x() - dx) / sw
            start_rel_y = (self.drag_start_pos.y() - dy) / sh
            diff_x = rel_x - start_rel_x
            diff_y = rel_y - start_rel_y
            
            self.crop_x = min(max(ox + diff_x, 0.0), 1.0 - ow)
            self.crop_y = min(max(oy + diff_y, 0.0), 1.0 - oh)
            self.update()
            return

        # Free Style Dragging Logic
        new_x, new_y, new_w, new_h = ox, oy, ow, oh
        
        if "L" in self.active_handle:
            new_w = ow + (ox - rel_x)
            new_x = rel_x if new_w >= 0.05 else ox + ow - 0.05
            new_w = max(0.05, new_w)
        if "R" in self.active_handle:
            new_w = max(0.05, rel_x - ox)
        if "T" in self.active_handle:
            new_h = oh + (oy - rel_y)
            new_y = rel_y if new_h >= 0.05 else oy + oh - 0.05
            new_h = max(0.05, new_h)
        if "B" in self.active_handle:
            new_h = max(0.05, rel_y - oy)

        # Apply Aspect Ratio Locking safely using Image Aspect Math
        if self.target_ratio and self.img_h > 0:
            rel_aspect_ratio = self.target_ratio / (self.img_w / self.img_h)
            
            # Decide dominating axis based on handle
            if self.active_handle in ["T", "B"]:
                new_w = new_h * rel_aspect_ratio
                if "L" in self.active_handle: new_x = ox + ow - new_w
            else:
                new_h = new_w / rel_aspect_ratio
                if "T" in self.active_handle: new_y = oy + oh - new_h

        # Bounds Checking Protection
        if new_x >= 0.0 and new_y >= 0.0 and (new_x + new_w) <= 1.0 and (new_y + new_h) <= 1.0:
            self.crop_x, self.crop_y, self.crop_w, self.crop_h = new_x, new_y, new_w, new_h
            
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.active_handle = self._get_handle(event.position())
            if self.active_handle:
                self.drag_start_pos = event.position()
                self.drag_start_crop = (self.crop_x, self.crop_y, self.crop_w, self.crop_h)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.active_handle = None


class CropDialog(QDialog):
    """Sleek dialog for cropping media with visual canvas editor."""
    def __init__(self, tracks_canvas, selected_id, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Visual Crop Editor")
        self.setFixedSize(900, 650)
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint)
        
        self.tracks_canvas = tracks_canvas
        self.selected_id = selected_id
        
        self.item = next((i for i in tracks_canvas.items if i["id"] == selected_id), None)
        if not self.item:
            self.reject()
            return
            
        self.setStyleSheet("""
            QDialog { background-color: #0e0e10; border: 1px solid #262626; border-radius: 12px; }
            QLabel { color: #d1d1d1; font-size: 12px; font-weight: bold; }
            QComboBox { background-color: #1a1a1a; border: 1px solid #333; border-radius: 6px; color: #d1d1d1; padding: 8px; }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView { background-color: #1a1a1a; color: #d1d1d1; selection-background-color: #e66b2c; }
            QPushButton { background-color: rgba(255, 255, 255, 0.05); color: #d1d1d1; border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 6px; padding: 8px 16px; font-weight: bold; }
            QPushButton:hover { background-color: rgba(255, 255, 255, 0.1); }
            QPushButton#Primary { background-color: #e66b2c; color: #fff; border: none; }
            QPushButton#Primary:hover { background-color: #d85a1e; }
            QPushButton#Danger { background-color: transparent; color: #e81123; border: 1px solid rgba(232, 17, 35, 0.3); }
            QPushButton#Danger:hover { background-color: rgba(232, 17, 35, 0.1); }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)

        # 1. Header Bar
        header = QWidget()
        header.setFixedHeight(45)
        header.setStyleSheet("background-color: #151515; border-bottom: 1px solid #262626; border-top-left-radius: 12px; border-top-right-radius: 12px;")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(20, 0, 10, 0)
        
        lbl_title = QLabel("Visual Crop Editor")
        lbl_title.setStyleSheet("font-size: 14px; color: #ffffff;")
        
        btn_close = QPushButton(qta.icon('mdi6.close', color='#808080'), "")
        btn_close.setFixedSize(30, 30)
        btn_close.setStyleSheet("QPushButton { background: transparent; border: none; } QPushButton:hover { background-color: #e81123; border-radius: 6px; }")
        btn_close.clicked.connect(self.reject)
        
        h_layout.addWidget(lbl_title)
        h_layout.addStretch()
        h_layout.addWidget(btn_close)
        layout.addWidget(header)

        # 2. Main Workspace
        workspace = QWidget()
        w_layout = QHBoxLayout(workspace)
        w_layout.setContentsMargins(20, 20, 20, 20)
        w_layout.setSpacing(20)

        # Left: Interactive Canvas
        self.canvas = CropCanvas()
        self.canvas.setStyleSheet("background-color: #111111; border: 1px solid #262626; border-radius: 8px;")
        w_layout.addWidget(self.canvas, stretch=3)

        # Right: Sidebar Controls
        sidebar = QFrame()
        sidebar.setFixedWidth(240)
        sidebar.setStyleSheet("background-color: #151515; border-radius: 8px; border: 1px solid #262626;")
        s_layout = QVBoxLayout(sidebar)
        s_layout.setContentsMargins(20, 20, 20, 20)
        s_layout.setSpacing(15)

        s_layout.addWidget(QLabel("Aspect Ratio"))
        self.combo = QComboBox()
        self.combo.addItems(["Original", "Free Style", "16:9", "9:16", "1:1", "4:3", "3:4"])
        self.combo.currentTextChanged.connect(self._on_preset_change)
        s_layout.addWidget(self.combo)

        info_lbl = QLabel("Drag corners or edges to reframe.\nDrag center to move the crop box.")
        info_lbl.setStyleSheet("color: #808080; font-size: 11px; font-weight: normal;")
        info_lbl.setWordWrap(True)
        s_layout.addWidget(info_lbl)

        s_layout.addStretch()

        btn_reset = QPushButton("Reset Crop")
        btn_reset.setObjectName("Danger")
        btn_reset.setCursor(Qt.PointingHandCursor)
        btn_reset.clicked.connect(self._reset_crop)
        s_layout.addWidget(btn_reset)

        btn_done = QPushButton("Apply Crop")
        btn_done.setObjectName("Primary")
        btn_done.setCursor(Qt.PointingHandCursor)
        btn_done.clicked.connect(self._apply_crop)
        s_layout.addWidget(btn_done)

        w_layout.addWidget(sidebar)
        layout.addWidget(workspace)

        # 3. Initialization Logic
        self._init_data()

    def _init_data(self):
        # Extract visual frame for canvas
        self.canvas.set_image_from_item(self.item, self.tracks_canvas.logical_playhead)
        
        # Load backend parameters into Canvas
        preset = self.item.get("crop_preset", "Original")
        self.combo.setCurrentText(preset)
        self.canvas.load_state(
            self.item.get("crop_x", 0),
            self.item.get("crop_y", 0),
            self.item.get("crop_w", 100),
            self.item.get("crop_h", 100),
            preset
        )

    def _on_preset_change(self, text):
        self.canvas.set_preset(text)

    def _reset_crop(self):
        self.combo.setCurrentText("Original")
        self.canvas.load_state(0, 0, 100, 100, "Original")
        self.canvas.update()

    def _apply_crop(self):
        state = self.canvas.get_state()
        for prop, value in state.items():
            self.tracks_canvas.update_item_property(self.selected_id, prop, value)
            
        # Push the playhead slightly to trigger an instant re-render in the UI Preview
        self.tracks_canvas.playhead_changed.emit(self.tracks_canvas.logical_playhead)
        self.accept()