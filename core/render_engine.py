# core/render_engine.py

import os
import time
import random
import copy
from PySide6.QtCore import QThread, Signal, Qt, QObject, QMutex, QMutexLocker, QRectF
from PySide6.QtGui import QImage, QPainter, QColor, QFont, QPen, QBrush, QRadialGradient
from core.project_manager import project_manager
from core.app_config import app_config
from core.models import ClipData

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
        self.preview_preset = None

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
                
    def set_preview_preset(self, preset_data):
        """Injects a preset to be previewed directly on the canvas without altering the project."""
        with QMutexLocker(self.mutex):
            self.preview_preset = preset_data
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

    def _get_effective_clip(self, original_clip):
        """Temporarily injects preview preset properties into the active clip for rendering cleanly."""
        if not getattr(self, "preview_preset", None):
            return original_clip
            
        ptype = self.preview_preset.get("type")
        if ptype not in ["effect", "transition", "caption"]:
            return original_clip
            
        clip = copy.copy(original_clip)
        # Clear existing applied effects and transitions to cleanly preview what the user is hovering/clicking!
        clip.applied_effects = {}
        clip.transition_in = None
        clip.transition_out = None
        
        pname = self.preview_preset.get("title")
        props = self.preview_preset.get("preset_properties", {})
        
        from core.preset_loader import get_default_properties
        defaults = get_default_properties({"properties": props})
        
        if ptype == "effect" and clip.clip_type in ["video", "image"]:
            clip.applied_effects["applied_effects"] = [pname]
            clip.applied_effects["primary_effect"] = pname
            for k, v in defaults.items(): 
                clip.applied_effects[k] = v
            
        elif ptype == "transition" and clip.clip_type in ["video", "image"]:
            clip.applied_effects["transition_out"] = pname
            clip.applied_effects["transition_out_duration"] = 30
            clip.transition_out = pname
            clip.transition_out_duration = 30
            
        return clip

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

        # Render directly from bottom to top (visual index N to 0)
        reversed_tracks = list(reversed(project.tracks))

        active_clip_ids = set()

        for track in reversed_tracks:
            if track.is_hidden: continue
            
            for original_clip in track.clips:
                clip = self._get_effective_clip(original_clip)
                if clip.start_time <= current_ms < clip.end_time:
                    
                    if clip.clip_type in ["video", "image"]:
                        active_clip_ids.add(clip.clip_id)
                        self._draw_media(painter, clip, current_ms, proj_w, proj_h)
                        
                    elif clip.clip_type == "effect":
                        # Do not draw other generic effects if we are currently globally previewing one
                        if getattr(self, "preview_preset", None) and self.preview_preset.get("type") in ["effect", "caption", "transition"]:
                            continue
                            
                        active_clip_ids.add(clip.clip_id)
                        painter.end()
                        canvas = self._apply_track_effect(canvas, clip, render_w, render_h)
                        painter = QPainter(canvas)
                        if self._render_scale < 1.0:
                            painter.setRenderHint(QPainter.Antialiasing, False)
                            painter.setRenderHint(QPainter.SmoothPixmapTransform, False)
                        else:
                            painter.setRenderHint(QPainter.Antialiasing)
                            painter.setRenderHint(QPainter.SmoothPixmapTransform)
                        painter.scale(self._render_scale, self._render_scale)
                        
                    elif clip.clip_type == "caption":
                        # Do not draw other generic captions if we are currently previewing one
                        if getattr(self, "preview_preset", None) and self.preview_preset.get("type") in ["effect", "caption", "transition"]:
                            continue
                            
                        active_clip_ids.add(clip.clip_id)
                        self._draw_caption(painter, clip, proj_w, proj_h)
                        
        # Global Preview Pass for Captions
        if getattr(self, "preview_preset", None) and self.preview_preset.get("type") == "caption":
            props = self.preview_preset.get("preset_properties", {})
            from core.preset_loader import get_default_properties
            defaults = get_default_properties({"properties": props})
            defaults["text"] = "Preview Caption"
            
            fake_clip = ClipData(file_path="", start_time=0, end_time=999999, clip_type="caption", applied_effects=defaults)
            self._draw_caption(painter, fake_clip, proj_w, proj_h)
                        
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
            
            # Transition Playback Support (Cross Dissolve Alpha)
            trans_in = props.get("transition_in")
            if trans_in:
                dur_frames = props.get("transition_in_duration", 30)
                dur_ms = dur_frames * (1000.0 / 30.0)
                elapsed_ms = current_ms - clip.start_time
                if 0 <= elapsed_ms < dur_ms:
                    opacity *= max(0.0, min(1.0, elapsed_ms / dur_ms))
                    
            trans_out = props.get("transition_out")
            if trans_out:
                dur_frames = props.get("transition_out_duration", 30)
                dur_ms = dur_frames * (1000.0 / 30.0)
                remaining_ms = clip.end_time - current_ms
                if 0 <= remaining_ms < dur_ms:
                    opacity *= max(0.0, min(1.0, remaining_ms / dur_ms))

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

    @staticmethod
    def _wrap_text(text, max_chars, word_wrap, max_lines):
        """Break text into lines based on layout settings."""
        if max_chars <= 0 or not text:
            lines = [text] if text else [""]
            return lines[:max_lines] if max_lines > 0 else lines
        
        result_lines = []
        paragraphs = text.split('\n')
        
        for paragraph in paragraphs:
            if not paragraph.strip():
                result_lines.append("")
                continue
                
            if len(paragraph) <= max_chars:
                result_lines.append(paragraph)
                continue
            
            if word_wrap:
                # Word-boundary wrapping
                words = paragraph.split(' ')
                current_line = ""
                for word in words:
                    test = f"{current_line} {word}".strip() if current_line else word
                    if len(test) <= max_chars:
                        current_line = test
                    else:
                        if current_line:
                            result_lines.append(current_line)
                        # Handle single words longer than max_chars
                        while len(word) > max_chars:
                            result_lines.append(word[:max_chars])
                            word = word[max_chars:]
                        current_line = word
                if current_line:
                    result_lines.append(current_line)
            else:
                # Hard character break
                for i in range(0, len(paragraph), max_chars):
                    result_lines.append(paragraph[i:i + max_chars])
        
        if max_lines > 0 and len(result_lines) > max_lines:
            result_lines = result_lines[:max_lines]
            # Add ellipsis to last line if truncated
            if result_lines:
                last = result_lines[-1]
                if len(last) > 3:
                    result_lines[-1] = last[:-3] + "..."
        
        return result_lines if result_lines else [""]

    def _draw_caption(self, painter, clip, proj_w, proj_h):
        props = clip.applied_effects if isinstance(clip.applied_effects, dict) else {}
        
        # Text source: applied_effects["text"] (from property panel) > file_path (initial text from timeline item)
        text = props.get("text", "") or clip.file_path or "New Caption"
        if not text.strip(): 
            text = "New Caption"
        
        font_family = props.get("Font Family", "Arial")
        font_size = max(1, int(props.get("Font Size", 80)))
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
        
        # Text layout properties
        max_chars = int(props.get("max_chars_per_line", 0))  # 0 = no limit
        max_lines = int(props.get("max_lines", 0))           # 0 = no limit
        word_wrap = bool(props.get("word_wrap", True))
        text_align = props.get("text_align", "Center")
        
        # Font weight mapping
        weight_map = {
            "Regular": QFont.Normal, "Bold": QFont.Bold,
            "Light": QFont.Light, "Black": QFont.Black,
            "Thin": QFont.Thin, "Medium": QFont.Medium,
            "DemiBold": QFont.DemiBold, "ExtraBold": QFont.ExtraBold,
        }
        font_weight_name = props.get("font_weight", "Bold")
        font_weight = weight_map.get(font_weight_name, QFont.Bold)
        
        painter.save()
        painter.setOpacity(opacity)
        
        center_x = proj_w / 2 + pos_x
        center_y = proj_h / 2 + pos_y
        painter.translate(center_x, center_y)
        
        if rotation != 0:
            painter.rotate(rotation)
        if scale_pct != 1.0:
            painter.scale(scale_pct, scale_pct)
        
        font = QFont(font_family, font_size, font_weight)
        painter.setFont(font)
        fm = painter.fontMetrics()
        
        # Apply text layout wrapping
        lines = self._wrap_text(text, max_chars, word_wrap, max_lines)
        
        # Calculate total bounds
        line_height = fm.height()
        line_spacing = int(line_height * 0.15)
        total_h = len(lines) * line_height + max(0, len(lines) - 1) * line_spacing
        max_line_w = max(fm.horizontalAdvance(line) for line in lines) if lines else 0
        
        # Alignment flag
        align_map = {"Left": Qt.AlignLeft, "Center": Qt.AlignHCenter, "Right": Qt.AlignRight}
        h_align = align_map.get(text_align, Qt.AlignHCenter)
        
        # Background box
        if bg_color_hex and bg_color_hex != "transparent" and bg_opacity > 0:
            bg_padding = int(props.get("bg_padding", 16))
            bg_radius = int(props.get("bg_radius", 8))
            bg_color = QColor(bg_color_hex)
            bg_color.setAlphaF(bg_opacity)
            painter.setBrush(QBrush(bg_color))
            painter.setPen(Qt.NoPen)
            bg_rect = QRectF(
                -max_line_w / 2 - bg_padding,
                -total_h / 2 - bg_padding,
                max_line_w + bg_padding * 2,
                total_h + bg_padding * 2
            )
            painter.drawRoundedRect(bg_rect, bg_radius, bg_radius)
        
        # Draw each line
        y_start = -total_h / 2
        
        for i, line in enumerate(lines):
            line_y = y_start + i * (line_height + line_spacing)
            line_rect = QRectF(-max_line_w / 2, line_y, max_line_w, line_height)
            
            # Text outline / shadow
            if outline_width > 0:
                painter.setPen(QPen(QColor(outline_color), outline_width))
                for dx, dy in [(-1, -1), (-1, 1), (1, -1), (1, 1), (0, -1), (0, 1), (-1, 0), (1, 0)]:
                    offset_rect = QRectF(
                        line_rect.x() + dx * outline_width, 
                        line_rect.y() + dy * outline_width,
                        line_rect.width(), line_rect.height()
                    )
                    painter.drawText(offset_rect, h_align | Qt.AlignVCenter, line)
            
            # Main text
            painter.setPen(QColor(color_hex))
            painter.drawText(line_rect, h_align | Qt.AlignVCenter, line)
        
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