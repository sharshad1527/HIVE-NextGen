import qtawesome as qta
import os
import time
import hashlib
import math
from PySide6.QtWidgets import (QFrame, QVBoxLayout, QHBoxLayout, QPushButton, 
                               QLabel, QSlider, QWidget, QStackedWidget, QComboBox, QApplication)
from PySide6.QtCore import Qt, Signal, QTimer, QUrl, QRect, QRectF, QPointF
from PySide6.QtGui import QPixmap, QPainter, QPen, QColor, QCursor
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget

from core.signal_hub import global_signals
from core.project_manager import project_manager
from core.render_engine import RenderEngine
from core.app_config import app_config


class TimelinePreviewCanvas(QWidget):
    """Custom drawing surface for the RenderEngine frames with interactive clip manipulation."""
    
    transform_changed = Signal(str, str, object)  # clip_id, prop_name, value
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_frame = None
        self.current_time = 0.0  # Synced to playhead in logical units
        self.setStyleSheet("background-color: #000000; border-radius: 8px;")
        self.setMouseTracking(True)
        
        # Interactive state
        self._selected_clip_id = ""
        self._selected_clip_bounds = None  # QRectF in canvas coordinates
        self._dragging = False
        self._rotating = False
        self._drag_start = QPointF()
        self._drag_start_pos = (0, 0)  # Original Position_X, Position_Y
        self._drag_start_rotation = 0
        self._show_handles = False
        
        # Project coordinate mapping
        self._canvas_scale = 1.0
        self._canvas_offset_x = 0
        self._canvas_offset_y = 0
        self._proj_w = 1920
        self._proj_h = 1080
        
    def set_time(self, time_logical):
        """Sets the current time in logical units (100 = 1 sec)"""
        self.current_time = time_logical
        
    def set_frame(self, qimage):
        self.current_frame = qimage
        self.update() 
    
    def _update_canvas_mapping(self):
        """Calculate the mapping between canvas widget coords and project coords."""
        if self.current_frame and not self.current_frame.isNull():
            cw, ch = self.width(), self.height()
            fw, fh = self.current_frame.width(), self.current_frame.height()
            if fw > 0 and fh > 0:
                self._canvas_scale = min(cw / fw, ch / fh)
                nw = fw * self._canvas_scale
                nh = fh * self._canvas_scale
                self._canvas_offset_x = (cw - nw) / 2
                self._canvas_offset_y = (ch - nh) / 2
    
    def _canvas_to_project(self, canvas_point):
        """Convert canvas widget coordinates to project coordinates."""
        self._update_canvas_mapping()
        if self._canvas_scale == 0:
            return QPointF(0, 0)
        
        project = project_manager.current_project
        if project:
            self._proj_w, self._proj_h = project.resolution
        
        frame_x = (canvas_point.x() - self._canvas_offset_x) / self._canvas_scale
        frame_y = (canvas_point.y() - self._canvas_offset_y) / self._canvas_scale
        
        render_engine_scale = 1.0 
        proj_x = frame_x / render_engine_scale
        proj_y = frame_y / render_engine_scale
        
        return QPointF(proj_x, proj_y)
    
    def _get_selected_clip_data(self):
        """Get the currently selected clip's data from the project."""
        if not self._selected_clip_id or not project_manager.current_project:
            return None
        for track in project_manager.current_project.tracks:
            for clip in track.clips:
                if clip.clip_id == self._selected_clip_id:
                    return clip
        return None
    
    def set_selected_clip(self, clip_id):
        """Called when a clip is selected on the timeline."""
        self._selected_clip_id = clip_id
        self._show_handles = bool(clip_id)
        self.update()
    
    def _get_clip_screen_bounds(self, clip):
        """Calculate the on-screen bounds of a clip for handle drawing."""
        if not clip or not self.current_frame:
            return None
        
        props = clip.applied_effects if isinstance(clip.applied_effects, dict) else {}
        
        base_x = getattr(clip, "Position_X", props.get("Position_X", 0))
        base_y = getattr(clip, "Position_Y", props.get("Position_Y", 0))
        base_zoom = props.get("Scale", 100) / 100.0
        base_rot = props.get("Rotation", 0)
        
        if hasattr(clip, 'get_animated_value'):
            rel_time = max(0.0, self.current_time - (clip.start_time / 10.0))
            pos_x = clip.get_animated_value("Position_X", rel_time, base_x)
            pos_y = clip.get_animated_value("Position_Y", rel_time, base_y)
            zoom = clip.get_animated_value("Scale", rel_time, base_zoom * 100) / 100.0
            rotation = clip.get_animated_value("Rotation", rel_time, base_rot)
        else:
            pos_x, pos_y, zoom, rotation = base_x, base_y, base_zoom, base_rot
            
        scale_pct = zoom
        self._update_canvas_mapping()
        
        center_x = (self._proj_w / 2) + pos_x
        center_y = (self._proj_h / 2) + pos_y
        cw, ch = self._proj_w, self._proj_h
        
        if clip.clip_type in ["video", "image"] and getattr(clip, "file_path", None) and os.path.exists(clip.file_path):
            if "media_w" not in props or "media_h" not in props:
                try:
                    import cv2
                    if clip.clip_type == "video":
                        cap = cv2.VideoCapture(clip.file_path)
                        if cap.isOpened():
                            props["media_w"] = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
                            props["media_h"] = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
                        cap.release()
                    elif clip.clip_type == "image":
                        img = cv2.imread(clip.file_path, cv2.IMREAD_UNCHANGED)
                        if img is not None:
                            props["media_w"] = img.shape[1]
                            props["media_h"] = img.shape[0]
                except ImportError:
                    pass
            
            if props.get("media_w", 0) > 0 and props.get("media_h", 0) > 0:
                mw, mh = props["media_w"], props["media_h"]
                ratio = min(self._proj_w / mw, self._proj_h / mh)
                cw = mw * ratio
                ch = mh * ratio
                
        elif clip.clip_type == "caption":
            font_size = max(1, int(props.get("Font Size", 80)))
            text = props.get("text", "") or getattr(clip, "file_path", "") or "New Caption"
            cw = len(text) * font_size * 0.6
            ch = font_size * 1.5
            
        crop_w = props.get("crop_w", 100) / 100.0
        crop_h = props.get("crop_h", 100) / 100.0
        
        cw = max(1.0, cw * crop_w)
        ch = max(1.0, ch * crop_h)

        half_w = (cw / 2) * scale_pct
        half_h = (ch / 2) * scale_pct
        
        render_scale = self._canvas_scale
        cx = self._canvas_offset_x + center_x * render_scale
        cy = self._canvas_offset_y + center_y * render_scale
        hw = half_w * render_scale
        hh = half_h * render_scale
        
        return {"cx": cx, "cy": cy, "hw": hw, "hh": hh, "rotation": rotation, "original_scale": scale_pct}
        
    def _mouse_to_local(self, pos, cx, cy, rotation):
        from PySide6.QtGui import QTransform
        t = QTransform()
        t.translate(cx, cy)
        t.rotate(rotation)
        t_inv, invertible = t.inverted()
        if not invertible: return pos
        return t_inv.map(pos)
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.black)
        
        if self.current_frame and not self.current_frame.isNull():
            cw, ch = self.width(), self.height()
            fw, fh = self.current_frame.width(), self.current_frame.height()
            
            if fw > 0 and fh > 0:
                ratio = min(cw / fw, ch / fh)
                nw, nh = int(fw * ratio), int(fh * ratio)
                x, y = (cw - nw) // 2, (ch - nh) // 2
                
                painter.setRenderHint(QPainter.SmoothPixmapTransform, False)
                painter.drawImage(QRect(x, y, nw, nh), self.current_frame)
        
        if self._show_handles and self._selected_clip_id:
            clip = self._get_selected_clip_data()
            if clip and clip.clip_type in ("video", "image", "caption"):
                bounds = self._get_clip_screen_bounds(clip)
                if bounds:
                    cx, cy = bounds["cx"], bounds["cy"]
                    hw, hh = bounds["hw"], bounds["hh"]
                    rotation = bounds["rotation"]
                    
                    painter.save()
                    painter.translate(cx, cy)
                    painter.rotate(rotation)
                    
                    painter.setPen(QPen(QColor("#e66b2c"), 2, Qt.DashLine))
                    painter.setBrush(Qt.NoBrush)
                    painter.drawRect(QRectF(-hw, -hh, hw * 2, hh * 2))
                    
                    handle_size = 8
                    corners = [
                        QPointF(-hw, -hh), QPointF(hw, -hh),
                        QPointF(-hw, hh), QPointF(hw, hh)
                    ]
                    painter.setPen(QPen(QColor("#ffffff"), 1))
                    painter.setBrush(QColor("#e66b2c"))
                    for corner in corners:
                        painter.drawRect(QRectF(
                            corner.x() - handle_size/2, corner.y() - handle_size/2,
                            handle_size, handle_size
                        ))
                    
                    top_center = QPointF(0, -hh - 25)
                    painter.setPen(QPen(QColor("#ffffff"), 1))
                    painter.setBrush(QColor("#4299e1"))
                    painter.drawEllipse(top_center, 6, 6)
                    
                    painter.setPen(QPen(QColor("#4299e1"), 1))
                    painter.drawLine(0, int(-hh), 0, int(top_center.y() + 6))
                    
                    painter.restore()
        
        painter.end()

    def _get_visible_clips(self):
        visible = []
        if not project_manager.current_project:
            return visible
        
        # Iterate in reverse track order (top tracks drawn last, clicked first)
        for track in reversed(project_manager.current_project.tracks):
            if getattr(track, 'hidden', False):
                continue
            for clip in reversed(track.clips):
                start = clip.start_time / 10.0
                end = start + (clip.duration / 10.0)
                if start <= self.current_time < end:
                    visible.append(clip)
        return visible

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            pos = event.position()
            handled = False
            
            # Check selected clip first
            if self._show_handles and self._selected_clip_id:
                clip = self._get_selected_clip_data()
                if clip:
                    bounds = self._get_clip_screen_bounds(clip)
                    if bounds:
                        local_pos = self._mouse_to_local(pos, bounds["cx"], bounds["cy"], bounds["rotation"])
                        hw, hh = bounds["hw"], bounds["hh"]
                        props = clip.applied_effects if isinstance(clip.applied_effects, dict) else {}
                        
                        self._resizing = False
                        self._dragging = False
                        self._rotating = False
                        
                        base_x = getattr(clip, "Position_X", props.get("Position_X", 0))
                        base_y = getattr(clip, "Position_Y", props.get("Position_Y", 0))
                        base_rot = props.get("Rotation", 0)
                        
                        if hasattr(clip, 'get_animated_value'):
                            rel_time = max(0.0, self.current_time - (clip.start_time / 10.0))
                            curr_x = clip.get_animated_value("Position_X", rel_time, base_x)
                            curr_y = clip.get_animated_value("Position_Y", rel_time, base_y)
                            curr_rot = clip.get_animated_value("Rotation", rel_time, base_rot)
                        else:
                            curr_x, curr_y, curr_rot = base_x, base_y, base_rot
                        
                        rot_handle = QPointF(0, -hh - 25)
                        if (local_pos - rot_handle).manhattanLength() < 20:
                            self._rotating = True
                            self._drag_start = pos
                            self._drag_start_rotation = curr_rot
                            self.setCursor(Qt.ClosedHandCursor)
                            handled = True
                        else:
                            handle_size = 12
                            corners = [
                                QPointF(-hw, -hh), QPointF(hw, -hh),
                                QPointF(-hw, hh), QPointF(hw, hh)
                            ]
                            for corner in corners:
                                if (local_pos - corner).manhattanLength() < handle_size * 2:
                                    self._resizing = True
                                    self._drag_start = pos
                                    self._drag_start_scale = bounds["original_scale"]
                                    self._drag_start_dist = math.sqrt((pos.x() - bounds["cx"])**2 + (pos.y() - bounds["cy"])**2)
                                    handled = True
                                    break
                            
                            if not handled:
                                rect = QRectF(-hw, -hh, hw * 2, hh * 2)
                                if rect.contains(local_pos):
                                    self._dragging = True
                                    self._drag_start = pos
                                    self._drag_start_pos = (curr_x, curr_y)
                                    self.setCursor(Qt.ClosedHandCursor)
                                    handled = True

            # If not handled, try to select a different clip
            if not handled:
                clicked_clip = None
                for clip in self._get_visible_clips():
                    bounds = self._get_clip_screen_bounds(clip)
                    if bounds:
                        local_pos = self._mouse_to_local(pos, bounds["cx"], bounds["cy"], bounds["rotation"])
                        hw, hh = bounds["hw"], bounds["hh"]
                        rect = QRectF(-hw, -hh, hw * 2, hh * 2)
                        if rect.contains(local_pos):
                            clicked_clip = clip
                            break
                            
                if clicked_clip:
                    self._selected_clip_id = clicked_clip.clip_id
                    self._show_handles = True
                    self.update()
                    if hasattr(global_signals, 'clip_selected'):
                        global_signals.clip_selected.emit(clicked_clip.clip_type, clicked_clip.clip_id)
                    
                    bounds = self._get_clip_screen_bounds(clicked_clip)
                    if bounds:
                        props = clicked_clip.applied_effects if isinstance(clicked_clip.applied_effects, dict) else {}
                        base_x = getattr(clicked_clip, "Position_X", props.get("Position_X", 0))
                        base_y = getattr(clicked_clip, "Position_Y", props.get("Position_Y", 0))
                        
                        if hasattr(clicked_clip, 'get_animated_value'):
                            rel_time = max(0.0, self.current_time - (clicked_clip.start_time / 10.0))
                            curr_x = clicked_clip.get_animated_value("Position_X", rel_time, base_x)
                            curr_y = clicked_clip.get_animated_value("Position_Y", rel_time, base_y)
                        else:
                            curr_x, curr_y = base_x, base_y
                            
                        self._dragging = True
                        self._drag_start = pos
                        self._drag_start_pos = (curr_x, curr_y)
                        self.setCursor(Qt.ClosedHandCursor)
                    return
                else:
                    # Clicked empty space
                    if self._selected_clip_id:
                        self._selected_clip_id = ""
                        self._show_handles = False
                        self.update()
                        if hasattr(global_signals, 'clip_deselected'):
                            global_signals.clip_deselected.emit()

            if handled:
                return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging and self._selected_clip_id:
            delta = event.position() - self._drag_start
            
            self._update_canvas_mapping()
            if self._canvas_scale > 0:
                proj_dx = delta.x() / self._canvas_scale
                proj_dy = delta.y() / self._canvas_scale
                
                new_x = int(self._drag_start_pos[0] + proj_dx)
                new_y = int(self._drag_start_pos[1] + proj_dy)
                
                clip = self._get_selected_clip_data()
                if clip:
                    rel_time = max(0.0, self.current_time - (clip.start_time / 10.0))
                    if hasattr(clip, 'is_keyframing_enabled'):
                        if clip.is_keyframing_enabled("Position_X"): clip.set_keyframe("Position_X", rel_time, new_x)
                        if clip.is_keyframing_enabled("Position_Y"): clip.set_keyframe("Position_Y", rel_time, new_y)
                    
                    setattr(clip, "Position_X", new_x)
                    setattr(clip, "Position_Y", new_y)
                    
                    if isinstance(clip.applied_effects, dict):
                        clip.applied_effects["Position_X"] = new_x
                        clip.applied_effects["Position_Y"] = new_y
                    
                    self.transform_changed.emit(self._selected_clip_id, "Position_X", new_x)
                    self.transform_changed.emit(self._selected_clip_id, "Position_Y", new_y)
                    
                    if hasattr(global_signals, 'force_refresh'):
                        global_signals.force_refresh.emit()
                    self.update()
            return
        
        elif self._rotating and self._selected_clip_id:
            clip = self._get_selected_clip_data()
            if clip:
                bounds = self._get_clip_screen_bounds(clip)
                if bounds:
                    dx = event.position().x() - bounds["cx"]
                    dy = event.position().y() - bounds["cy"]
                    angle = math.degrees(math.atan2(dx, -dy))
                    
                    dx0 = self._drag_start.x() - bounds["cx"]
                    dy0 = self._drag_start.y() - bounds["cy"]
                    start_angle = math.degrees(math.atan2(dx0, -dy0))
                    
                    delta_angle = angle - start_angle
                    new_rotation = int(max(-360, min(360, self._drag_start_rotation + delta_angle)))
                    
                    rel_time = max(0.0, self.current_time - (clip.start_time / 10.0))
                    if hasattr(clip, 'is_keyframing_enabled') and clip.is_keyframing_enabled("Rotation"):
                        clip.set_keyframe("Rotation", rel_time, new_rotation)
                    
                    setattr(clip, "Rotation", new_rotation)
                    if isinstance(clip.applied_effects, dict):
                        clip.applied_effects["Rotation"] = new_rotation
                        
                    self.transform_changed.emit(self._selected_clip_id, "Rotation", new_rotation)
                    if hasattr(global_signals, 'force_refresh'):
                        global_signals.force_refresh.emit()
                    self.update()
            return

        elif getattr(self, "_resizing", False) and self._selected_clip_id:
            clip = self._get_selected_clip_data()
            if clip:
                bounds = self._get_clip_screen_bounds(clip)
                if bounds and self._drag_start_dist > 0:
                    pos = event.position()
                    current_dist = math.sqrt((pos.x() - bounds["cx"])**2 + (pos.y() - bounds["cy"])**2)
                    
                    ratio = current_dist / self._drag_start_dist
                    new_scale = max(0.1, min(5.0, self._drag_start_scale * ratio))
                    
                    rel_time = max(0.0, self.current_time - (clip.start_time / 10.0))
                    if hasattr(clip, 'is_keyframing_enabled') and clip.is_keyframing_enabled("Scale"):
                        clip.set_keyframe("Scale", rel_time, new_scale * 100)
                        
                    setattr(clip, "Scale", new_scale * 100)
                    if isinstance(clip.applied_effects, dict):
                        clip.applied_effects["Scale"] = int(new_scale * 100)
                        
                    self.transform_changed.emit(self._selected_clip_id, "Scale", new_scale * 100)
                    if hasattr(global_signals, 'force_refresh'):
                        global_signals.force_refresh.emit()
                    self.update()
            return
        
        if self._show_handles and self._selected_clip_id:
            clip = self._get_selected_clip_data()
            if clip:
                bounds = self._get_clip_screen_bounds(clip)
                if bounds:
                    pos = event.position()
                    local_pos = self._mouse_to_local(pos, bounds["cx"], bounds["cy"], bounds["rotation"])
                    hw, hh = bounds["hw"], bounds["hh"]
                    
                    rot_handle = QPointF(0, -hh - 25)
                    if (local_pos - rot_handle).manhattanLength() < 20:
                        self.setCursor(Qt.CrossCursor)
                        return
                        
                    handle_size = 12
                    corners = [
                        QPointF(-hw, -hh), QPointF(hw, -hh),
                        QPointF(-hw, hh), QPointF(hw, hh)
                    ]
                    for corner in corners:
                        if (local_pos - corner).manhattanLength() < handle_size * 2:
                            self.setCursor(Qt.SizeFDiagCursor)
                            return
                            
                    rect = QRectF(-hw, -hh, hw * 2, hh * 2)
                    if rect.contains(local_pos):
                        self.setCursor(Qt.OpenHandCursor)
                        return
        
        self.setCursor(Qt.ArrowCursor)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._dragging or self._rotating or getattr(self, "_resizing", False):
            self._dragging = False
            self._rotating = False
            self._resizing = False
            self.setCursor(Qt.ArrowCursor)
            
            clip = self._get_selected_clip_data()
            if clip:
                global_signals.clip_transform_changed.emit(
                    self._selected_clip_id, "Position_X", getattr(clip, "Position_X", 0)
                )
                global_signals.clip_transform_changed.emit(
                    self._selected_clip_id, "Scale", getattr(clip, "Scale", 100.0)
                )
            return
        
        super().mouseReleaseEvent(event)


class PlayerPanel(QFrame):
    
    playhead_seek_requested = Signal(int)
    resolution_changed = Signal(str) 

    ASPECT_PRESETS = {
        "16:9": (16, 9),
        "9:16": (9, 16),
        "4:3": (4, 3),
        "1:1": (1, 1),
        "21:9": (21, 9),
        "4:5": (4, 5),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Panel")
        
        self.duration = 0
        self.playhead = 0
        self.is_playing = False
        
        self.is_preview_mode = False
        self.is_timeline_preview = False
        self.preview_duration = 0
        self.preview_position = 0
        
        self._preview_aspect = (16, 9)

        self.audio_players = {}

        self.play_timer = QTimer(self)
        self.play_timer.setTimerType(Qt.PreciseTimer)
        self.play_timer.timeout.connect(self._on_play_step)

        self.render_engine = RenderEngine()
        self.render_engine.frame_ready.connect(self._on_timeline_frame_received)
        self.render_engine.start()

        self.setStyleSheet("""
            QFrame#Panel {
                background-color: rgba(14, 14, 16, 0.90); 
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 12px;
            }
        """)
        
        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(15, 15, 15, 15)

        self._canvas_area = QWidget()
        self._canvas_area.setStyleSheet("background: transparent;")
        self._canvas_area_layout = QVBoxLayout(self._canvas_area)
        self._canvas_area_layout.setContentsMargins(0, 0, 0, 0)
        self._canvas_area_layout.setAlignment(Qt.AlignCenter)

        self.video_container = QFrame()
        self.video_container.setStyleSheet("""
            QFrame {
                background-color: #000000;
                border-radius: 8px;
                border: 1px solid #262626;
            }
        """)
        video_layout = QVBoxLayout(self.video_container)
        video_layout.setContentsMargins(0, 0, 0, 0)
        
        self.media_stack = QStackedWidget()
        video_layout.addWidget(self.media_stack)
        
        self.placeholder_lbl = QLabel("No Media Selected")
        self.placeholder_lbl.setAlignment(Qt.AlignCenter)
        self.placeholder_lbl.setStyleSheet("color: #555555; font-size: 16px; font-weight: bold; background: transparent;")
        
        self.video_widget = QVideoWidget()
        self.timeline_canvas = TimelinePreviewCanvas()
        
        self.timeline_canvas.transform_changed.connect(self._on_canvas_transform)
        
        if hasattr(global_signals, 'clip_transform_changed'):
            global_signals.clip_transform_changed.connect(self._on_property_changed_rerender)
            
        if hasattr(global_signals, 'force_refresh'):
            global_signals.force_refresh.connect(self._force_refresh_render)
        
        self.media_stack.addWidget(self.placeholder_lbl)
        self.media_stack.addWidget(self.video_widget)
        self.media_stack.addWidget(self.timeline_canvas) 
        
        self.media_stack.setCurrentWidget(self.timeline_canvas)
        
        self._canvas_area_layout.addWidget(self.video_container)
        self._main_layout.addWidget(self._canvas_area, stretch=1)

        controls_container = QWidget()
        controls_layout = QVBoxLayout(controls_container)
        controls_layout.setContentsMargins(0, 15, 0, 0)
        controls_layout.setSpacing(10)

        self.scrubber = QSlider(Qt.Horizontal)
        self.scrubber.setRange(0, 1000)
        self.scrubber.setStyleSheet("""
            QSlider::groove:horizontal { border-radius: 2px; height: 4px; margin: 0px; background-color: #262626; }
            QSlider::handle:horizontal { background-color: #ffffff; border: none; height: 12px; width: 12px; margin: -4px 0; border-radius: 6px; }
            QSlider::handle:horizontal:hover { transform: scale(1.2); }
            QSlider::sub-page:horizontal { background-color: #e66b2c; border-radius: 2px; }
        """)
        self.scrubber.valueChanged.connect(self._on_scrubber_moved)
        controls_layout.addWidget(self.scrubber)

        bottom_row = QHBoxLayout()

        left_layout = QHBoxLayout()
        left_layout.setSpacing(6)
        
        combo_style = """
            QComboBox {
                background-color: transparent; border: 1px solid rgba(255,255,255,0.1);
                border-radius: 4px; color: #808080; padding: 2px 8px; font-size: 10px;
                font-weight: bold;
            }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background-color: #1a1a1a; color: #d1d1d1; selection-background-color: #e66b2c;
            }
        """
        
        self.combo_aspect = QComboBox()
        self.combo_aspect.addItems(list(self.ASPECT_PRESETS.keys()))
        self.combo_aspect.setStyleSheet(combo_style)
        self.combo_aspect.setCursor(Qt.PointingHandCursor)
        self.combo_aspect.setToolTip("Player Preview Aspect Ratio")
        self.combo_aspect.currentTextChanged.connect(self._on_aspect_changed)
        
        self.combo_res = QComboBox()
        self.combo_res.addItems(["Full", "1/2", "1/4", "1/8"])
        self.combo_res.setStyleSheet(combo_style)
        self.combo_res.setCursor(Qt.PointingHandCursor)
        self.combo_res.setToolTip("Render Quality (For heavy projects)")
        self.combo_res.currentTextChanged.connect(self._on_res_changed)
        
        left_layout.addWidget(self.combo_aspect)
        left_layout.addWidget(self.combo_res)
        left_layout.addStretch(1)

        center_layout = QHBoxLayout()
        self.btn_skip_back = QPushButton(qta.icon('mdi6.skip-previous-outline', color='#e66b2c'), "")
        self.btn_play = QPushButton(qta.icon('mdi6.play', color='#e66b2c'), "")
        self.btn_skip_fwd = QPushButton(qta.icon('mdi6.skip-next-outline', color='#e66b2c'), "")
        
        for btn in [self.btn_skip_back, self.btn_play, self.btn_skip_fwd]:
            btn.setStyleSheet("background: transparent; border: none; padding: 0 10px;")
            btn.setCursor(Qt.PointingHandCursor)
            center_layout.addWidget(btn)

        self.btn_play.clicked.connect(self.toggle_play)
        self.btn_skip_fwd.clicked.connect(self.step_forward)
        self.btn_skip_back.clicked.connect(self.step_backward)

        right_layout = QHBoxLayout()
        right_layout.addStretch(1)
        self.lbl_timecode = QLabel("00:00:00:00 / 00:00:00:00")
        self.lbl_timecode.setStyleSheet("color: #d1d1d1; font-family: monospace; font-size: 12px; font-weight: bold;")
        right_layout.addWidget(self.lbl_timecode)

        bottom_row.addLayout(left_layout, 1)   
        bottom_row.addLayout(center_layout, 0) 
        bottom_row.addLayout(right_layout, 1)  

        controls_layout.addLayout(bottom_row)
        self._main_layout.addWidget(controls_container)
        
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        self.player.setVideoOutput(self.video_widget)
        
        self.player.positionChanged.connect(self._on_player_position_changed)
        self.player.durationChanged.connect(self._on_player_duration_changed)
        self.player.playbackStateChanged.connect(self._on_player_state_changed)
        
        global_signals.clip_selected.connect(self._on_clip_selected_for_preview)
        global_signals.clip_deselected.connect(self._on_clip_deselected_for_preview)
        global_signals.project_resolution_changed.connect(self._on_project_resolution_changed)
        if hasattr(global_signals, 'clip_updated'):
            global_signals.clip_updated.connect(self._on_clip_updated)
        
        if QApplication.instance():
            QApplication.instance().aboutToQuit.connect(self._cleanup)

    def _on_clip_updated(self, clip_data):
        if not self.is_playing:
            self._sync_timeline_audio(int(self.playhead))

    def _force_refresh_render(self):
        if not self.is_playing:
            self.render_engine.request_frame(int(self.playhead))

    def _on_clip_selected_for_preview(self, item_type, clip_id):
        self.timeline_canvas.set_selected_clip(clip_id)
    
    def _on_clip_deselected_for_preview(self):
        self.timeline_canvas.set_selected_clip("")

    def _on_canvas_transform(self, clip_id, prop_name, value):
        global_signals.clip_transform_changed.emit(clip_id, prop_name, value)

    def _on_property_changed_rerender(self, clip_id, prop_name, value):
        self._force_refresh_render()

    def _on_timeline_frame_received(self, frame):
        self.timeline_canvas.set_frame(frame)

    def _on_aspect_changed(self, aspect_text):
        if aspect_text in self.ASPECT_PRESETS:
            self._preview_aspect = self.ASPECT_PRESETS[aspect_text]
            self._update_canvas_size()
            self._force_refresh_render()

    def _on_project_resolution_changed(self, resolution):
        w, h = resolution
        best_match = "16:9" 
        target_ratio = w / h if h > 0 else 1.78
        min_diff = float('inf')
        for label, (aw, ah) in self.ASPECT_PRESETS.items():
            diff = abs((aw / ah) - target_ratio)
            if diff < min_diff:
                min_diff = diff
                best_match = label
        
        self.combo_aspect.blockSignals(True)
        self.combo_aspect.setCurrentText(best_match)
        self.combo_aspect.blockSignals(False)
        self._preview_aspect = self.ASPECT_PRESETS[best_match]
        self._update_canvas_size()
        self._force_refresh_render()

    def _update_canvas_size(self):
        available_w = self._canvas_area.width()
        available_h = self._canvas_area.height()
        if available_w <= 0 or available_h <= 0:
            return
        
        aspect_w, aspect_h = self._preview_aspect
        aspect_ratio = aspect_w / aspect_h
        
        if available_w / available_h > aspect_ratio:
            canvas_h = available_h
            canvas_w = int(canvas_h * aspect_ratio)
        else:
            canvas_w = available_w
            canvas_h = int(canvas_w / aspect_ratio)
        
        self.video_container.setFixedSize(max(1, canvas_w), max(1, canvas_h))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self._update_canvas_size)

    def _on_res_changed(self, res_text):
        if res_text == "Full":
            self.render_engine.set_render_scale(1.0)
            self.render_engine.set_render_fps(30.0)
        elif res_text == "1/2":
            self.render_engine.set_render_scale(0.5)
            self.render_engine.set_render_fps(30.0)
        elif res_text == "1/4":
            self.render_engine.set_render_scale(0.25)
            self.render_engine.set_render_fps(30.0)
        elif res_text == "1/8":
            self.render_engine.set_render_scale(0.125)
            self.render_engine.set_render_fps(24.0)
            
        self.resolution_changed.emit(res_text)
        
        if self.is_preview_mode and not self.is_timeline_preview:
            self._apply_preview_source()

    def load_preview(self, media_data):
        self.current_preview_data = media_data
        if not media_data:
            if hasattr(self.render_engine, 'set_preview_preset'):
                self.render_engine.set_preview_preset(None)
            self.is_preview_mode = False
            self.is_timeline_preview = False
            if self.is_playing:
                self.toggle_play()
            return

        preset_type = media_data.get("type")
        
        if preset_type in ["effect", "caption", "transition"]:
            if not self.is_preview_mode or not hasattr(self, '_original_playhead'):
                self._original_playhead = self.playhead
                
            self.is_preview_mode = True
            self.is_timeline_preview = True
            self.preview_duration = 5000 
            self.preview_position = 0
            self.preview_loops = 0
            
            preview_start_ms = self._original_playhead * 10
            
            if preset_type == "transition" and hasattr(self, "timeline_canvas") and getattr(self, "timeline_canvas", None):
                clip = None
                project = project_manager.current_project
                if project:
                    for t in project.tracks:
                        if t.track_id == "video_1":
                            for c in t.clips:
                                if c.start_time <= self._original_playhead * 10 < c.end_time:
                                    clip = c
                                    break
                if clip:
                    target_ms = max(clip.start_time, clip.end_time - 3000)
                    self.playhead = target_ms / 10.0
                    self.preview_duration = 4000
                else:
                    self.playhead = self._original_playhead
            else:
                self.playhead = self._original_playhead
            
            self.playback_start_time = time.time()
            self.playback_start_playhead = self.playhead
            
            if hasattr(self.render_engine, 'set_preview_preset'):
                self.render_engine.set_preview_preset(media_data, target_clip_id=clip.clip_id if 'clip' in locals() and clip else None)
                
            self.player.stop()
            self.media_stack.setCurrentWidget(self.timeline_canvas)
            
            if not self.is_playing:
                self.play_timer.start(33)
                self.render_engine.set_playing(True)
                self.btn_play.setIcon(qta.icon('mdi6.pause', color='#e66b2c'))
                self.is_playing = True
            return
            
        if hasattr(self.render_engine, 'set_preview_preset'):
            self.render_engine.set_preview_preset(None)
            
        self.is_preview_mode = True 
        self.is_timeline_preview = False
        self.preview_duration = 0
        self.preview_position = 0
        self._first_load_done = False
        
        if self.is_playing:
            self.toggle_play()
        self.player.stop()

        self._apply_preview_source()

    def _apply_preview_source(self):
        if not hasattr(self, 'current_preview_data') or not self.current_preview_data:
            return
            
        media_data = self.current_preview_data
        title = media_data.get("title", "")
        file_path = media_data.get("file_path", "")
        proxy_path = media_data.get("proxy_path", "")
        media_type = media_data.get("subtype", media_data.get("type", ""))

        current_res = self.combo_res.currentText()
        active_path = file_path
        
        if media_type == "video" and current_res != "Full":
            if not proxy_path or not os.path.exists(proxy_path):
                file_hash = hashlib.md5(file_path.encode()).hexdigest()
                inferred_proxy = os.path.join(str(app_config.proxy_cache_path), f"{file_hash}_proxy.mp4")
                if os.path.exists(inferred_proxy):
                    proxy_path = inferred_proxy
                    
            if proxy_path and os.path.exists(proxy_path):
                active_path = proxy_path

        if active_path and os.path.exists(active_path):
            if media_type == "video":
                self.media_stack.setCurrentWidget(self.video_widget)
                
                was_playing = self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
                current_pos = self.player.position()
                
                current_source = self.player.source().toLocalFile()
                if current_source != active_path:
                    self.player.setSource(QUrl.fromLocalFile(active_path))
                    if current_pos > 0:
                        self.player.setPosition(current_pos)
                        
                if was_playing or not self._first_load_done:
                    self.player.play()
                    
                self._first_load_done = True
                
            elif media_type == "audio":
                self.media_stack.setCurrentWidget(self.placeholder_lbl)
                self.placeholder_lbl.setText(f"Playing Audio:\n{title}")
                self.player.setSource(QUrl.fromLocalFile(active_path))
                self.player.play()
            elif media_type == "image":
                self.media_stack.setCurrentWidget(self.placeholder_lbl)
                pixmap = QPixmap(active_path)
                scaled = pixmap.scaled(self.video_container.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.placeholder_lbl.setPixmap(scaled)
                self._update_timecode_label(preview=True)
            else:
                self.media_stack.setCurrentWidget(self.placeholder_lbl)
                self.placeholder_lbl.setText(f"Preview:\n{title}")
                self._update_timecode_label(preview=True)
        else:
            self.media_stack.setCurrentWidget(self.placeholder_lbl)
            self.placeholder_lbl.clear()
            self.placeholder_lbl.setText(f"Preview Mode:\n{title}")
            self._update_timecode_label(preview=True)

    def _on_player_position_changed(self, position):
        if self.is_preview_mode and not self.is_timeline_preview:
            self.preview_position = position
            self._update_timecode_label(preview=True)
            if self.preview_duration > 0:
                perc = int((self.preview_position / self.preview_duration) * 1000)
                self.scrubber.blockSignals(True)
                self.scrubber.setValue(max(0, min(1000, perc)))
                self.scrubber.blockSignals(False)

    def _on_player_duration_changed(self, duration):
        if self.is_preview_mode and not self.is_timeline_preview and duration > 0:
            self.preview_duration = duration
            self._update_timecode_label(preview=True)

    def _on_player_state_changed(self, state):
        if self.is_preview_mode and not self.is_timeline_preview:
            if state == QMediaPlayer.PlaybackState.PlayingState:
                self.btn_play.setIcon(qta.icon('mdi6.pause', color='#e66b2c'))
            else:
                self.btn_play.setIcon(qta.icon('mdi6.play', color='#e66b2c'))

    def _sync_timeline_audio(self, logical_pos):
        project = project_manager.current_project
        if not project: return
        
        active_clip_ids = set()
        current_ms = int(logical_pos * 10)
        
        for track in project.tracks:
            if track.is_muted or track.is_hidden: continue
            for clip in track.clips:
                if clip.clip_type in ["video", "audio"] and clip.file_path:
                    if clip.start_time <= current_ms < clip.end_time:
                        active_clip_ids.add(clip.clip_id)
                        
                        props = clip.applied_effects if isinstance(clip.applied_effects, dict) else {}
                        
                        trim_in_ms = getattr(clip, 'trim_in', 0)
                        fx_source_in = props.get("source_in", 0) * 10
                        trim_in_ms = max(trim_in_ms, fx_source_in)
                        local_ms = (current_ms - clip.start_time) + trim_in_ms
                        
                        # --- KEYFRAME AUDIO EVALUATION ---
                        if hasattr(clip, 'get_animated_value'):
                            rel_time = max(0.0, (current_ms - clip.start_time) / 10.0)
                            vol_pct = clip.get_animated_value("Volume", rel_time, props.get("Volume", 100))
                            pan = clip.get_animated_value("Pan", rel_time, props.get("Pan", 0)) / 100.0
                            speed_pct = clip.get_animated_value("Speed", rel_time, props.get("Speed", 100))
                        else:
                            vol_pct = props.get("Volume", 100)
                            pan = float(props.get("Pan", 0)) / 100.0
                            speed_pct = float(props.get("Speed", 100))
                        
                        linear_vol = max(0.0, float(vol_pct) / 100.0)
                        
                        clip_duration_ms = clip.end_time - clip.start_time
                        elapsed_ms = current_ms - clip.start_time
                        fade_in_sec = float(props.get("Fade_In", 0))
                        fade_out_sec = float(props.get("Fade_Out", 0))
                        
                        fade_in_ms = fade_in_sec * 1000.0
                        fade_out_ms = fade_out_sec * 1000.0
                        
                        fade_mult = 1.0
                        if fade_in_ms > 0 and elapsed_ms < fade_in_ms:
                            fade_mult = min(1.0, elapsed_ms / fade_in_ms)
                        if fade_out_ms > 0:
                            remaining_ms = clip.end_time - current_ms
                            if remaining_ms < fade_out_ms:
                                fade_mult *= min(1.0, remaining_ms / fade_out_ms)
                        
                        effective_vol = linear_vol * fade_mult
                        
                        left_vol = effective_vol * max(0.0, 1.0 - pan)
                        right_vol = effective_vol * max(0.0, 1.0 + pan)
                        if pan != 0:
                            left_vol = min(1.0, left_vol)
                            right_vol = min(1.0, right_vol)
                        
                        playback_rate = max(0.1, min(4.0, speed_pct / 100.0))
                        
                        if clip.clip_id not in self.audio_players:
                            player = QMediaPlayer()
                            audio_output = QAudioOutput()
                            audio_output.setVolume(effective_vol)
                            player.setAudioOutput(audio_output)
                            player.setSource(QUrl.fromLocalFile(clip.file_path))
                            player.setPosition(local_ms)
                            player.setPlaybackRate(playback_rate)
                            
                            if self.is_playing:
                                player.play()
                                
                            self.audio_players[clip.clip_id] = {'player': player, 'output': audio_output}
                        else:
                            player = self.audio_players[clip.clip_id]['player']
                            audio_output = self.audio_players[clip.clip_id]['output']
                            
                            audio_output.setVolume(effective_vol)
                            
                            if abs(player.playbackRate() - playback_rate) > 0.01:
                                player.setPlaybackRate(playback_rate)
                            
                            if self.is_playing and player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
                                player.play()
                            elif not self.is_playing and player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                                player.pause()
                                
                            diff = abs(player.position() - local_ms)
                            if self.is_playing:
                                if diff > 800:
                                    player.setPosition(local_ms)
                            else:
                                if diff > 50:
                                    player.setPosition(local_ms)
                                
        stale_ids = set(self.audio_players.keys()) - active_clip_ids
        for clip_id in stale_ids:
            self.audio_players[clip_id]['player'].stop()
            self.audio_players[clip_id]['player'].deleteLater()
            self.audio_players[clip_id]['output'].deleteLater()
            del self.audio_players[clip_id]


    def _stop_all_timeline_audio(self):
        for clip_id, data in self.audio_players.items():
            data['player'].pause()

    def _on_play_step(self):
        if not hasattr(self, 'playback_start_time'):
            self.playback_start_time = time.time()
            
        elapsed = time.time() - self.playback_start_time
        new_pos = self.playback_start_playhead + (elapsed * 100.0)
        
        self.timeline_canvas.set_time(self.playhead)
        
        if self.is_timeline_preview:
            duration_sec = getattr(self, 'preview_duration', 5000) / 1000.0
            if elapsed > duration_sec:
                self.playback_start_time = time.time()
                self.playhead = self.playback_start_playhead
            else:
                self.playhead = new_pos
                self._update_timecode_label(preview=False)
                self.render_engine.request_frame(int(self.playhead))
                self._sync_timeline_audio(int(self.playhead))
            return
        
        if new_pos >= self.duration and self.duration > 0:
            new_pos = self.duration
            if self.is_playing:
                self.toggle_play() 
            
        self.playhead = new_pos
        self.render_engine.request_frame(int(new_pos))
        self.playhead_seek_requested.emit(int(new_pos))
        self._sync_timeline_audio(int(new_pos))
        
        if hasattr(global_signals, 'playhead_moved'):
            global_signals.playhead_moved.emit(self.playhead)

    def toggle_play(self):
        if self.is_preview_mode and not self.is_timeline_preview:
            if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                self.player.pause()
            else:
                self.player.play()
        else:
            if self.media_stack.currentWidget() != self.timeline_canvas:
                self.media_stack.setCurrentWidget(self.timeline_canvas)

            if self.is_playing:
                self.play_timer.stop()
                self.render_engine.set_playing(False)
                self.btn_play.setIcon(qta.icon('mdi6.play', color='#e66b2c'))
                if not self.is_timeline_preview:
                    self._stop_all_timeline_audio()
            else:
                if not self.is_timeline_preview and self.playhead >= self.duration and self.duration > 0:
                    self.playhead_seek_requested.emit(0)
                
                self.playback_start_time = time.time()
                self.playback_start_playhead = self.playhead
                
                self.play_timer.start(33) 
                self.render_engine.set_playing(True)
                self.btn_play.setIcon(qta.icon('mdi6.pause', color='#e66b2c'))
                if not self.is_timeline_preview:
                    self._sync_timeline_audio(int(self.playhead))
                
            self.is_playing = not self.is_playing
            
            if hasattr(global_signals, 'playback_state_changed'):
                global_signals.playback_state_changed.emit(self.is_playing)

    def step_forward(self):
        if self.is_preview_mode and not self.is_timeline_preview:
            self.player.setPosition(min(self.preview_duration, self.player.position() + 1000))
        else:
            self.playhead_seek_requested.emit(min(self.duration, self.playhead + 16))

    def step_backward(self):
        if self.is_preview_mode and not self.is_timeline_preview:
            self.player.setPosition(max(0, self.player.position() - 1000))
        else:
            self.playhead_seek_requested.emit(max(0, self.playhead - 16))

    def _on_scrubber_moved(self, val):
        if self.is_preview_mode:
            if self.preview_duration > 0:
                new_pos = int((val / 1000.0) * self.preview_duration)
                if not self.is_timeline_preview:
                    self.player.setPosition(new_pos)
        else:
            if self.duration > 0:
                new_playhead = (val / 1000.0) * self.duration
                self.playhead_seek_requested.emit(int(new_playhead))
                self.render_engine.request_frame(int(new_playhead))

    def update_duration(self, duration_logical):
        self.duration = duration_logical
        if not self.is_preview_mode:
            self._update_timecode_label()
        
    def update_playhead(self, playhead_logical):
        if self.is_preview_mode:
            self.is_preview_mode = False
            self.is_timeline_preview = False
            if hasattr(self.render_engine, 'set_preview_preset'):
                self.render_engine.set_preview_preset(None)
            self.player.stop()
            self.media_stack.setCurrentWidget(self.timeline_canvas)
            if self.is_playing:
                self.toggle_play()
            if hasattr(self, '_original_playhead'):
                delattr(self, '_original_playhead')
            
        self.playhead = playhead_logical
        self.timeline_canvas.set_time(self.playhead)
        self._update_timecode_label()
        
        if hasattr(global_signals, 'playhead_moved'):
            global_signals.playhead_moved.emit(self.playhead)
            if hasattr(self, 'playback_start_playhead'):
                expected_pos = self.playback_start_playhead + ((time.time() - self.playback_start_time) * 100.0)
                if abs(self.playhead - expected_pos) > 10: 
                    self.playback_start_time = time.time()
                    self.playback_start_playhead = self.playhead
        
        # FIX: Always update the visual preview safely when scrolling or paused
        if not self.is_timeline_preview:
            self.render_engine.request_frame(self.playhead)
            
            if not self.is_playing:
                self._sync_timeline_audio(int(self.playhead))
                self._stop_all_timeline_audio()
            
            if self.duration > 0:
                perc = int((self.playhead / self.duration) * 1000)
                perc = max(0, min(1000, perc))
                self.scrubber.blockSignals(True)
                self.scrubber.setValue(perc)
                self.scrubber.blockSignals(False)

    def _update_timecode_label(self, preview=False):
        def format_time(val, is_ms=False):
            if val < 0: val = 0
            
            if is_ms:
                total_seconds = int(val // 1000)
                frames = int(((val % 1000) / 1000.0) * 30)
            else:
                total_seconds = int(val // 100)
                frames = int((val % 100) / 100 * 30)
                
            hours = total_seconds // 3600
            mins = (total_seconds % 3600) // 60
            secs = total_seconds % 60
            
            return f"{hours:02d}:{mins:02d}:{secs:02d}:{frames:02d}"
            
        if preview:
            p_str = format_time(self.preview_position, is_ms=True)
            d_str = format_time(self.preview_duration, is_ms=True)
        else:
            p_str = format_time(self.playhead, is_ms=False)
            d_str = format_time(self.duration, is_ms=False)
            
        self.lbl_timecode.setText(f"{p_str} / {d_str}")

    def _cleanup(self):
        self.is_playing = False
        self.play_timer.stop()
        
        if hasattr(self, 'render_engine'):
            self.render_engine.stop()
            self.render_engine.wait(300) 
            
        if hasattr(self, 'player') and self.player:
            self.player.stop()
            self.player.setVideoOutput(None)
            self.player.setAudioOutput(None)
            self.player.deleteLater()
            
        for clip_id, data in self.audio_players.items():
            data['player'].stop()
            data['player'].deleteLater()
            data['output'].deleteLater()
        self.audio_players.clear()