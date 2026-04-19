# core/render_engine.py

import os
import time
from PySide6.QtCore import QThread, Signal, Qt, QObject, QMutex, QMutexLocker, QRectF
from PySide6.QtGui import QImage, QPainter, QColor, QFont
from core.project_manager import project_manager
from core.app_config import app_config

try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False


class RenderEngine(QThread):
    """
    Background thread that composites video frames, images, and text 
    for the timeline preview using OpenCV and QPainter.
    """
    frame_ready = Signal(QImage)

    def __init__(self):
        super().__init__()
        self.is_playing = False
        self.playhead_logical = 0.0
        self.mutex = QMutex()
        self.video_readers = {}  # Cache of {file_path: cv2.VideoCapture} to prevent constant reopening
        self._target_fps = 30.0
        self._render_scale = 1.0 # Optimization: Allows compositing at a lower internal resolution
        self._run_flag = True
        self._force_render = False

    def request_frame(self, logical_time):
        """Called by the UI when the playhead moves (scrubbing or stepping)."""
        with QMutexLocker(self.mutex):
            self.playhead_logical = logical_time
            if not self.is_playing:
                self._force_render = True

    def set_playing(self, playing):
        with QMutexLocker(self.mutex):
            self.is_playing = playing
            
    def set_render_fps(self, fps):
        """Safely throttles the Engine processing speed down for Low-End PCs"""
        with QMutexLocker(self.mutex):
            self._target_fps = float(fps)
            
    def set_render_scale(self, scale):
        """Reduces the total pixel count the engine has to composite for massive speed boosts."""
        with QMutexLocker(self.mutex):
            self._render_scale = scale
            if not self.is_playing:
                self._force_render = True

    def _clear_readers(self):
        for cap in self.video_readers.values():
            cap.release()
        self.video_readers.clear()

    def stop(self):
        self._run_flag = False
        self._clear_readers()
        self.wait()

    def run(self):
        while self._run_flag:
            start_time = time.time()
            
            with QMutexLocker(self.mutex):
                playing = self.is_playing
                current_logical = self.playhead_logical
                force = self._force_render
                self._force_render = False

            if playing or force:
                result = self._composite_frame(current_logical)
                if result:
                    frame, active_clip_ids = result
                    self.frame_ready.emit(frame)
                    
                    # Garbage Collect unused OpenCV readers to free RAM and prevent Read-Head fighting
                    stale_readers = [k for k in list(self.video_readers.keys()) if k not in active_clip_ids]
                    for k in stale_readers:
                        self.video_readers[k].release()
                        del self.video_readers[k]

            # Cap frame rate accurately
            elapsed = time.time() - start_time
            sleep_time = max(0, (1.0 / self._target_fps) - elapsed)
            time.sleep(sleep_time if playing else 0.016)

    def _composite_frame(self, logical_time):
        if not CV2_AVAILABLE:
            return self._create_error_frame("OpenCV (cv2) is not installed.\nPlease install opencv-python."), set()

        project = project_manager.current_project
        if not project:
            return None

        # 1. Initialize blank canvas at Scaled Project Resolution
        proj_w, proj_h = project.resolution
        
        # Optimization: Shrink the actual drawing canvas
        render_w = max(1, int(proj_w * self._render_scale))
        render_h = max(1, int(proj_h * self._render_scale))
        
        canvas = QImage(render_w, render_h, QImage.Format_ARGB32)
        canvas.fill(Qt.black)
        
        painter = QPainter(canvas)
        
        # Optimization: Disable smooth transformations when scaled down to save CPU
        if self._render_scale < 1.0:
            painter.setRenderHint(QPainter.Antialiasing, False)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, False)
        else:
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setRenderHint(QPainter.SmoothPixmapTransform)

        # Scale the painter so our logical math remains in 1080p/4k coordinates
        painter.scale(self._render_scale, self._render_scale)

        current_ms = int(logical_time * 10)

        # 2. Gather visible clips at this exact millisecond
        visible_clips = []
        for track in project.tracks:
            if track.is_hidden: continue
            for clip in track.clips:
                if clip.start_time <= current_ms < clip.end_time:
                    visible_clips.append((track, clip))

        def get_track_weight(track_type):
            if track_type == "video": return 1
            if track_type == "image": return 2
            if track_type == "effect": return 3
            if track_type == "caption": return 4
            return 0
            
        def get_track_num(track_id):
            try:
                return int(track_id.split('_')[-1])
            except:
                return 0
            
        # FIX: Properly sort by track number (V1 -> V2 -> V3) so top layers actually render on top!
        visible_clips.sort(key=lambda x: (get_track_weight(x[0].track_type), get_track_num(x[0].track_id)))

        active_clip_ids = set()

        # 3. Draw each layer
        for track, clip in visible_clips:
            active_clip_ids.add(clip.clip_id)
            if clip.clip_type in ["video", "image"] and clip.file_path:
                self._draw_media(painter, clip, current_ms, proj_w, proj_h)
            elif clip.clip_type == "caption":
                self._draw_caption(painter, clip, proj_w, proj_h)
                
        painter.end()
        return canvas, active_clip_ids

    def _draw_media(self, painter, clip, current_ms, proj_w, proj_h):
        file_path = clip.file_path
        
        if clip.clip_type == "video" and app_config.get_setting("auto_proxies", True):
            if clip.proxy_path and os.path.exists(clip.proxy_path):
                file_path = clip.proxy_path

        if not os.path.exists(file_path):
            return

        qimg = None
        
        if clip.clip_type == "video":
            # FIX: Use clip_id as the key so multiple clips of the same file don't fight over the read head!
            reader_key = clip.clip_id 
            if reader_key not in self.video_readers:
                self.video_readers[reader_key] = cv2.VideoCapture(file_path)
            
            cap = self.video_readers[reader_key]
            
            # Extract proper trim offset from applied_effects (UI sets source_in via logic units, 1 unit = 10ms)
            trim_in_ms = getattr(clip, 'trim_in', 0)
            if isinstance(clip.applied_effects, dict):
                fx_source_in = clip.applied_effects.get("source_in", 0) * 10
                trim_in_ms = max(trim_in_ms, fx_source_in)
                
            local_ms = (current_ms - clip.start_time) + trim_in_ms
            current_pos_ms = cap.get(cv2.CAP_PROP_POS_MSEC)
            
            # Seek if out of sync (backward seeking, or big jumps forward)
            if local_ms < current_pos_ms or (local_ms - current_pos_ms) > 100:
                cap.set(cv2.CAP_PROP_POS_MSEC, local_ms)
                
            ret, frame = cap.read()
            
            if not ret:
                # Retry: OpenCV sometimes drops the first frame right after a seek
                cap.set(cv2.CAP_PROP_POS_MSEC, local_ms)
                ret, frame = cap.read()
                
            if not ret:
                # Final Fallback: If local_ms is completely beyond the EOF, grab the very last frame so it doesn't blank out
                fps = cap.get(cv2.CAP_PROP_FPS)
                if fps > 0:
                    total_ms = (cap.get(cv2.CAP_PROP_FRAME_COUNT) / fps) * 1000
                    cap.set(cv2.CAP_PROP_POS_MSEC, max(0, total_ms - 100))
                    ret, frame = cap.read()

            if ret:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = frame.shape
                bytes_per_line = ch * w
                qimg = QImage(frame.data, w, h, bytes_per_line, QImage.Format_RGB888).copy()
                
        elif clip.clip_type == "image":
            qimg = QImage(file_path)

        if qimg and not qimg.isNull():
            props = clip.applied_effects or {}
            
            scale_pct = props.get("Scale", 100) / 100.0
            pos_x = props.get("Position_X", 0)
            pos_y = props.get("Position_Y", 0)
            rotation = props.get("Rotation", 0)
            opacity = props.get("Opacity", 100) / 100.0

            # Direct mapping from Crop UI bounds (The UI already calculates proper aspect ratios)
            crop_x = props.get("crop_x", 0) / 100.0
            crop_y = props.get("crop_y", 0) / 100.0
            crop_w = props.get("crop_w", 100) / 100.0
            crop_h = props.get("crop_h", 100) / 100.0

            img_w = qimg.width()
            img_h = qimg.height()

            # Identify the exact region of the image we want to keep
            cw = max(1.0, img_w * crop_w)
            ch = max(1.0, img_h * crop_h)
            cx = img_w * crop_x
            cy = img_h * crop_y

            source_rect = QRectF(cx, cy, cw, ch)

            painter.save()
            painter.setOpacity(opacity)
            
            center_x = (proj_w / 2) + pos_x
            center_y = (proj_h / 2) + pos_y
            painter.translate(center_x, center_y)
            
            if rotation != 0:
                painter.rotate(rotation)
                
            # Map the cropped section to fill the project screen, then apply user scale
            ratio = min(proj_w / cw, proj_h / ch)
            draw_w = cw * ratio * scale_pct
            draw_h = ch * ratio * scale_pct

            painter.drawImage(QRectF(-draw_w / 2, -draw_h / 2, draw_w, draw_h), qimg, source_rect)
            painter.restore()

    def _draw_caption(self, painter, clip, proj_w, proj_h):
        text = clip.applied_effects.get("text", clip.file_path) 
        if not text: return
        
        font_family = clip.applied_effects.get("Font Family", "Arial")
        font_size = int(clip.applied_effects.get("Font Size", 80))
        color_hex = clip.applied_effects.get("Text Color", "#FFFFFF")
        pos_x = clip.applied_effects.get("Position_X", 0)
        pos_y = clip.applied_effects.get("Position_Y", 0)
        
        painter.save()
        painter.setFont(QFont(font_family, font_size, QFont.Bold))
        painter.setPen(QColor(color_hex))
        
        painter.setPen(QColor(0, 0, 0, 180))
        painter.drawText(pos_x + 4, pos_y + 4, proj_w, proj_h, Qt.AlignCenter | Qt.TextWordWrap, text)
        
        painter.setPen(QColor(color_hex))
        painter.drawText(pos_x, pos_y, proj_w, proj_h, Qt.AlignCenter | Qt.TextWordWrap, text)
        painter.restore()

    def _create_error_frame(self, message):
        img = QImage(1280, 720, QImage.Format_ARGB32)
        img.fill(Qt.black)
        painter = QPainter(img)
        painter.setPen(Qt.white)
        painter.setFont(QFont("Arial", 24, QFont.Bold))
        painter.drawText(img.rect(), Qt.AlignCenter, message)
        painter.end()
        return img