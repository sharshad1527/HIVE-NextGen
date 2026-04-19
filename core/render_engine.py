# core/render_engine.py

import os
import time
import random
from PySide6.QtCore import QThread, Signal, Qt, QObject, QMutex, QMutexLocker, QRectF
from PySide6.QtGui import QImage, QPainter, QColor, QFont, QPen, QBrush, QRadialGradient
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
    Supports effects: blur, glow, vignette, color grade, VHS, and glitch.
    """
    frame_ready = Signal(QImage)

    def __init__(self):
        super().__init__()
        self.is_playing = False
        self.playhead_logical = 0.0
        self.mutex = QMutex()
        self.video_readers = {}
        self._target_fps = 30.0
        self._render_scale = 1.0
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
        with QMutexLocker(self.mutex):
            self._target_fps = float(fps)
            
    def set_render_scale(self, scale):
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
                    
                    stale_readers = [k for k in list(self.video_readers.keys()) if k not in active_clip_ids]
                    for k in stale_readers:
                        self.video_readers[k].release()
                        del self.video_readers[k]

            elapsed = time.time() - start_time
            sleep_time = max(0, (1.0 / self._target_fps) - elapsed)
            time.sleep(sleep_time if playing else 0.016)

    @staticmethod
    def _get_track_num(track_id):
        try:
            return int(track_id.split('_')[-1])
        except:
            return 0

    def _composite_frame(self, logical_time):
        if not CV2_AVAILABLE:
            return self._create_error_frame("OpenCV (cv2) is not installed.\nPlease install opencv-python."), set()

        project = project_manager.current_project
        if not project:
            return None

        proj_w, proj_h = project.resolution
        
        render_w = max(1, int(proj_w * self._render_scale))
        render_h = max(1, int(proj_h * self._render_scale))
        
        canvas = QImage(render_w, render_h, QImage.Format_ARGB32)
        canvas.fill(Qt.black)
        
        painter = QPainter(canvas)
        
        if self._render_scale < 1.0:
            painter.setRenderHint(QPainter.Antialiasing, False)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, False)
        else:
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setRenderHint(QPainter.SmoothPixmapTransform)

        painter.scale(self._render_scale, self._render_scale)

        current_ms = int(logical_time * 10)

        visible_clips = []
        for track in project.tracks:
            if track.is_hidden: continue
            for clip in track.clips:
                if clip.start_time <= current_ms < clip.end_time:
                    visible_clips.append((track, clip))

        # Separate clips by category for layered compositing
        video_clips = []  # (track, clip) for video/image on video tracks
        effect_clips = []  # (track, clip) for standalone effects on effect tracks
        caption_clips = []  # (track, clip) for captions
        
        for track, clip in visible_clips:
            if clip.clip_type in ["video", "image"] and clip.file_path:
                video_clips.append((track, clip))
            elif clip.clip_type == "effect" and track.track_type == "effect":
                effect_clips.append((track, clip))
            elif clip.clip_type == "caption":
                caption_clips.append((track, clip))

        # Local alias for readability
        get_track_num = self._get_track_num

        # Sort video clips by track number (V1 first = bottom layer)
        video_clips.sort(key=lambda x: self._get_track_num(x[0].track_id))
        # Sort effect clips by track number
        effect_clips.sort(key=lambda x: self._get_track_num(x[0].track_id))
        # Sort captions by track number
        caption_clips.sort(key=lambda x: self._get_track_num(x[0].track_id))

        active_clip_ids = set()

        # BUG 4 FIX: Layered compositing — effects only affect video layers BELOW them.
        # Track layout (top to bottom in UI): Caption > V2 > Effect1 > V1 > Audio
        # Compositing order: Draw V1 first (bottom), apply Effect1, then draw V2, then captions
        
        # Build effect lookup: effect track number -> effect clip
        effect_by_track = {}
        for track, clip in effect_clips:
            active_clip_ids.add(clip.clip_id)
            tn = get_track_num(track.track_id)
            effect_by_track[tn] = (track, clip)

        # Get the sorted list of video track numbers
        video_track_nums = sorted(set(get_track_num(t.track_id) for t, c in video_clips))
        
        # Draw video clips from bottom (V1) to top (V2, V3, etc.)
        for v_num in video_track_nums:
            # Draw all video clips on this track
            for track, clip in video_clips:
                if get_track_num(track.track_id) == v_num:
                    active_clip_ids.add(clip.clip_id)
                    self._draw_media(painter, clip, current_ms, proj_w, proj_h)
            
            # After drawing this video layer, apply any effect tracks that sit 
            # right below it (effect tracks between this V-track and the next V-track)
            # Effect numbering corresponds to the video track they affect
            for e_num in sorted(effect_by_track.keys()):
                e_track, e_clip = effect_by_track[e_num]
                # Apply effect to the entire canvas so far
                if e_num <= v_num:
                    painter.end()
                    canvas = self._apply_track_effect(canvas, e_clip, render_w, render_h)
                    painter = QPainter(canvas)
                    if self._render_scale < 1.0:
                        painter.setRenderHint(QPainter.Antialiasing, False)
                        painter.setRenderHint(QPainter.SmoothPixmapTransform, False)
                    else:
                        painter.setRenderHint(QPainter.Antialiasing)
                        painter.setRenderHint(QPainter.SmoothPixmapTransform)
                    painter.scale(self._render_scale, self._render_scale)
                    del effect_by_track[e_num]  # Apply each effect only once
        
        # Apply any remaining effects that weren't matched to a video track
        for e_num in sorted(effect_by_track.keys()):
            e_track, e_clip = effect_by_track[e_num]
            painter.end()
            canvas = self._apply_track_effect(canvas, e_clip, render_w, render_h)
            painter = QPainter(canvas)
            if self._render_scale < 1.0:
                painter.setRenderHint(QPainter.Antialiasing, False)
                painter.setRenderHint(QPainter.SmoothPixmapTransform, False)
            else:
                painter.setRenderHint(QPainter.Antialiasing)
                painter.setRenderHint(QPainter.SmoothPixmapTransform)
            painter.scale(self._render_scale, self._render_scale)

        # Draw captions on top of everything
        for track, clip in caption_clips:
            active_clip_ids.add(clip.clip_id)
            self._draw_caption(painter, clip, proj_w, proj_h)
                
        painter.end()
        return canvas, active_clip_ids

    def _apply_track_effect(self, canvas, effect_clip, render_w, render_h):
        """Applies a standalone effect-track clip to the entire QImage canvas via OpenCV."""
        if not CV2_AVAILABLE:
            return canvas
        
        # Convert QImage to numpy array
        canvas = canvas.convertToFormat(QImage.Format_ARGB32)
        ptr = canvas.bits()
        arr = np.frombuffer(ptr, dtype=np.uint8).reshape((render_h, render_w, 4)).copy()
        # ARGB -> BGRA for OpenCV
        bgr = cv2.cvtColor(arr, cv2.COLOR_BGRA2BGR)
        
        # Apply effects using existing _apply_cv_effects pipeline
        bgr = self._apply_cv_effects(bgr, effect_clip)
        
        # Convert back to QImage
        bgr = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        h, w, ch = bgr.shape
        result = QImage(bgr.data, w, h, ch * w, QImage.Format_RGB888).copy()
        return result

    def _draw_media(self, painter, clip, current_ms, proj_w, proj_h):
        file_path = clip.file_path
        
        if clip.clip_type == "video" and app_config.get_setting("auto_proxies", True):
            if clip.proxy_path and os.path.exists(clip.proxy_path):
                file_path = clip.proxy_path

        if not os.path.exists(file_path):
            return

        qimg = None
        
        if clip.clip_type == "video":
            reader_key = clip.clip_id 
            if reader_key not in self.video_readers:
                self.video_readers[reader_key] = cv2.VideoCapture(file_path)
            
            cap = self.video_readers[reader_key]
            
            trim_in_ms = getattr(clip, 'trim_in', 0)
            if isinstance(clip.applied_effects, dict):
                fx_source_in = clip.applied_effects.get("source_in", 0) * 10
                trim_in_ms = max(trim_in_ms, fx_source_in)
                
            local_ms = (current_ms - clip.start_time) + trim_in_ms
            current_pos_ms = cap.get(cv2.CAP_PROP_POS_MSEC)
            
            diff = local_ms - current_pos_ms
            
            if diff < -70 or diff > 200:
                cap.set(cv2.CAP_PROP_POS_MSEC, local_ms)
                ret, frame = cap.read()
            else:
                ret, frame = cap.read()
                while ret and (local_ms - cap.get(cv2.CAP_PROP_POS_MSEC)) > 50:
                    ret, frame = cap.read()
                
            if not ret:
                fps = cap.get(cv2.CAP_PROP_FPS)
                if fps > 0:
                    total_ms = (cap.get(cv2.CAP_PROP_FRAME_COUNT) / fps) * 1000
                    cap.set(cv2.CAP_PROP_POS_MSEC, max(0, total_ms - 100))
                    ret, frame = cap.read()

            if ret:
                # Apply pixel-level effects before converting to QImage
                frame = self._apply_cv_effects(frame, clip)
                
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = frame.shape
                bytes_per_line = ch * w
                qimg = QImage(frame.data, w, h, bytes_per_line, QImage.Format_RGB888).copy()
                
        elif clip.clip_type == "image":
            img = cv2.imread(file_path, cv2.IMREAD_UNCHANGED)
            if img is not None:
                # Apply pixel-level effects
                if len(img.shape) == 3 and img.shape[2] == 4:
                    img = self._apply_cv_effects(img, clip, has_alpha=True)
                    img = cv2.cvtColor(img, cv2.COLOR_BGRA2RGBA)
                    h, w, ch = img.shape
                    bytes_per_line = ch * w
                    qimg = QImage(img.data, w, h, bytes_per_line, QImage.Format_RGBA8888).copy()
                else:
                    if len(img.shape) == 2:
                        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
                    img = self._apply_cv_effects(img, clip)
                    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                    h, w, ch = img.shape
                    bytes_per_line = ch * w
                    qimg = QImage(img.data, w, h, bytes_per_line, QImage.Format_RGB888).copy()

        if qimg and not qimg.isNull():
            props = clip.applied_effects or {}
            
            scale_pct = props.get("Scale", 100) / 100.0
            pos_x = props.get("Position_X", 0)
            pos_y = props.get("Position_Y", 0)
            rotation = props.get("Rotation", 0)
            opacity = props.get("Opacity", 100) / 100.0

            crop_x = props.get("crop_x", 0) / 100.0
            crop_y = props.get("crop_y", 0) / 100.0
            crop_w = props.get("crop_w", 100) / 100.0
            crop_h = props.get("crop_h", 100) / 100.0

            img_w = qimg.width()
            img_h = qimg.height()

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
                
            ratio = min(proj_w / cw, proj_h / ch)
            draw_w = cw * ratio * scale_pct
            draw_h = ch * ratio * scale_pct

            # Corner radius support
            corner_radius = props.get("Corner_Radius", 0)
            if corner_radius > 0:
                from PySide6.QtGui import QPainterPath
                path = QPainterPath()
                path.addRoundedRect(QRectF(-draw_w / 2, -draw_h / 2, draw_w, draw_h), corner_radius, corner_radius)
                painter.setClipPath(path)

            painter.drawImage(QRectF(-draw_w / 2, -draw_h / 2, draw_w, draw_h), qimg, source_rect)
            painter.restore()

    def _apply_cv_effects(self, frame, clip, has_alpha=False):
        """Apply OpenCV-based visual effects to a frame based on clip's applied_effects."""
        if not isinstance(clip.applied_effects, dict):
            return frame
        
        effects_list = clip.applied_effects.get("applied_effects", [])
        if isinstance(effects_list, str):
            effects_list = [effects_list]
        elif not isinstance(effects_list, list):
            effects_list = []
        
        # Also check for primary_effect key
        primary = clip.applied_effects.get("primary_effect", "")
        if primary and primary not in effects_list:
            effects_list.append(primary)
        
        if not effects_list:
            return frame
        
        amount = clip.applied_effects.get("effect_amount", 100) / 100.0
        
        for effect_name in effects_list:
            effect_lower = effect_name.lower()
            
            if "blur" in effect_lower or "gaussian" in effect_lower:
                frame = self._fx_blur(frame, amount, clip.applied_effects)
            elif "glow" in effect_lower or "cinematic" in effect_lower:
                frame = self._fx_glow(frame, amount, clip.applied_effects)
            elif "vignette" in effect_lower:
                frame = self._fx_vignette(frame, amount, clip.applied_effects)
            elif "color" in effect_lower and "grade" in effect_lower:
                frame = self._fx_color_grade(frame, amount, clip.applied_effects)
            elif "vhs" in effect_lower:
                frame = self._fx_vhs(frame, amount, clip.applied_effects)
            elif "glitch" in effect_lower:
                frame = self._fx_glitch(frame, amount, clip.applied_effects)
        
        return frame
    
    def _fx_blur(self, frame, amount, props):
        """Gaussian blur effect."""
        radius = int(props.get("radius", 15) * amount)
        if radius < 1:
            return frame
        # Kernel must be odd
        k = max(1, radius) | 1
        return cv2.GaussianBlur(frame, (k, k), 0)
    
    def _fx_glow(self, frame, amount, props):
        """Cinematic glow/bloom effect — bright areas bleed outward."""
        radius = int(props.get("radius", 30) * amount)
        if radius < 1:
            return frame
        k = max(1, radius) | 1
        
        # Work on BGR channels only (ignore alpha if present)
        work = frame[:, :, :3] if frame.shape[2] >= 3 else frame
        
        blurred = cv2.GaussianBlur(work, (k, k), 0)
        # Additive blend for bloom
        result = cv2.addWeighted(work, 1.0, blurred, amount * 0.5, 0)
        
        if frame.shape[2] == 4:
            frame[:, :, :3] = result
            return frame
        return result
    
    def _fx_vignette(self, frame, amount, props):
        """Radial vignette darkening toward edges."""
        h, w = frame.shape[:2]
        radius_pct = props.get("radius", 70) / 100.0
        softness = props.get("softness", 50) / 100.0
        
        # Create radial gradient mask
        Y, X = np.ogrid[:h, :w]
        cx, cy = w / 2, h / 2
        dist = np.sqrt((X - cx) ** 2 + (Y - cy) ** 2)
        max_dist = np.sqrt(cx ** 2 + cy ** 2)
        
        # Normalize and apply radius
        norm_dist = dist / (max_dist * max(0.1, radius_pct))
        mask = np.clip(1.0 - norm_dist, 0, 1)
        
        # Apply softness
        sigma = max(1, int(softness * 100)) | 1
        mask = cv2.GaussianBlur(mask.astype(np.float32), (sigma, sigma), 0)
        
        # Blend with amount
        mask = 1.0 - (1.0 - mask) * amount
        
        mask_3d = np.dstack([mask] * frame.shape[2]) if len(frame.shape) == 3 else mask
        result = (frame.astype(np.float32) * mask_3d).astype(np.uint8)
        return result
    
    def _fx_color_grade(self, frame, amount, props):
        """Brightness, contrast, and saturation adjustments."""
        brightness = props.get("brightness", 0) * amount
        contrast = props.get("contrast", 10) * amount
        saturation = props.get("saturation", 15) * amount
        
        work = frame[:, :, :3] if frame.shape[2] >= 3 else frame
        result = work.astype(np.float32)
        
        # Brightness
        result += brightness
        
        # Contrast
        factor = (259 * (contrast + 255)) / (255 * (259 - contrast))
        result = factor * (result - 128) + 128
        
        # Saturation
        if abs(saturation) > 0.1:
            hsv = cv2.cvtColor(np.clip(result, 0, 255).astype(np.uint8), cv2.COLOR_BGR2HSV).astype(np.float32)
            hsv[:, :, 1] = np.clip(hsv[:, :, 1] * (1 + saturation / 100.0), 0, 255)
            result = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR).astype(np.float32)
        
        result = np.clip(result, 0, 255).astype(np.uint8)
        
        if frame.shape[2] == 4:
            frame[:, :, :3] = result
            return frame
        return result
    
    def _fx_vhs(self, frame, amount, props):
        """VHS retro effect with scanlines and chromatic aberration."""
        h, w = frame.shape[:2]
        work = frame[:, :, :3] if frame.shape[2] >= 3 else frame
        result = work.copy()
        
        # Chromatic aberration (shift R and B channels)
        shift = int(props.get("chromatic_shift", 5) * amount)
        if shift > 0:
            result[:, shift:, 2] = work[:, :-shift, 2]  # Blue channel shift right
            result[:, :-shift, 0] = work[:, shift:, 0]  # Red channel shift left
        
        # Scanlines
        scanline_opacity = props.get("scanline_opacity", 40) / 100.0 * amount
        if scanline_opacity > 0:
            for y in range(0, h, 2):
                result[y, :] = (result[y, :].astype(np.float32) * (1 - scanline_opacity * 0.5)).astype(np.uint8)
        
        # Noise
        noise_amount = props.get("noise", 30) / 100.0 * amount
        if noise_amount > 0:
            noise = np.random.randint(-25, 25, result.shape, dtype=np.int16)
            result = np.clip(result.astype(np.int16) + (noise * noise_amount).astype(np.int16), 0, 255).astype(np.uint8)
        
        if frame.shape[2] == 4:
            frame[:, :, :3] = result
            return frame
        return result
    
    def _fx_glitch(self, frame, amount, props):
        """Digital glitch effect — random horizontal block displacement."""
        h, w = frame.shape[:2]
        work = frame.copy()
        
        block_size = max(2, int(props.get("block_size", 10)))
        shift_amount = int(props.get("shift_amount", 20) * amount)
        
        if shift_amount < 1:
            return frame
        
        # Random block shifts
        num_blocks = max(1, int(h / block_size * amount * 0.3))
        for _ in range(num_blocks):
            y_start = random.randint(0, max(0, h - block_size))
            y_end = min(h, y_start + block_size)
            shift = random.randint(-shift_amount, shift_amount)
            
            if shift > 0:
                work[y_start:y_end, shift:] = frame[y_start:y_end, :w-shift]
            elif shift < 0:
                work[y_start:y_end, :w+shift] = frame[y_start:y_end, -shift:]
        
        return work

    def _draw_caption(self, painter, clip, proj_w, proj_h):
        props = clip.applied_effects if isinstance(clip.applied_effects, dict) else {}
        
        # Text source: applied_effects["text"] (from property panel) > file_path (initial text from timeline item)
        text = props.get("text", "") or clip.file_path or "New Caption"
        if not text.strip(): 
            text = "New Caption"
        
        font_family = props.get("Font Family", "Arial")
        font_size = max(1, int(props.get("Font Size", 80)))  # Clamp to minimum 1
        color_hex = props.get("Text Color", "#FFFFFF")
        pos_x = props.get("Position_X", 0)
        pos_y = props.get("Position_Y", 0)
        opacity = props.get("Opacity", 100) / 100.0
        rotation = props.get("Rotation", 0)
        scale_pct = props.get("Scale", 100) / 100.0
        outline_width = props.get("outline_width", 2)
        outline_color = props.get("outline_color", "#000000")
        bg_color_hex = props.get("Bg Color", "transparent")
        bg_opacity = props.get("bg_opacity", 0) / 100.0
        
        painter.save()
        painter.setOpacity(opacity)
        
        # Apply transform
        center_x = proj_w / 2 + pos_x
        center_y = proj_h / 2 + pos_y
        painter.translate(center_x, center_y)
        
        if rotation != 0:
            painter.rotate(rotation)
        if scale_pct != 1.0:
            painter.scale(scale_pct, scale_pct)
        
        font = QFont(font_family, font_size, QFont.Bold)
        painter.setFont(font)
        
        # Calculate text bounds for background
        fm = painter.fontMetrics()
        text_rect = fm.boundingRect(text)
        text_w = text_rect.width()
        text_h = text_rect.height()
        
        # Background box
        if bg_color_hex and bg_color_hex != "transparent" and bg_opacity > 0:
            bg_padding = int(props.get("bg_padding", 16))
            bg_radius = int(props.get("bg_radius", 8))
            bg_color = QColor(bg_color_hex)
            bg_color.setAlphaF(bg_opacity)
            painter.setBrush(QBrush(bg_color))
            painter.setPen(Qt.NoPen)
            bg_rect = QRectF(
                -text_w / 2 - bg_padding,
                -text_h / 2 - bg_padding,
                text_w + bg_padding * 2,
                text_h + bg_padding * 2
            )
            painter.drawRoundedRect(bg_rect, bg_radius, bg_radius)
        
        # Text outline / shadow
        if outline_width > 0:
            painter.setPen(QPen(QColor(outline_color), outline_width))
            for dx, dy in [(-1, -1), (-1, 1), (1, -1), (1, 1), (0, -1), (0, 1), (-1, 0), (1, 0)]:
                painter.drawText(
                    QRectF(-text_w / 2 + dx * outline_width, -text_h / 2 + dy * outline_width, text_w, text_h),
                    Qt.AlignCenter | Qt.TextWordWrap, text
                )
        
        # Main text
        painter.setPen(QColor(color_hex))
        painter.drawText(
            QRectF(-text_w / 2, -text_h / 2, text_w, text_h),
            Qt.AlignCenter | Qt.TextWordWrap, text
        )
        
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