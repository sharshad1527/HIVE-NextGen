# core/render_engine.py

import os
import time
import random
import copy
import threading
import queue
from PySide6.QtCore import QThread, Signal, Qt, QObject, QMutex, QMutexLocker, QRectF
from PySide6.QtGui import QImage, QPainter, QColor, QFont, QPen, QBrush, QRadialGradient
from core.logger import hive_logger
from core.project_manager import project_manager
from core.app_config import app_config
from core.models import ClipData
from core.video_decoder import VideoDecoder
from core.signal_hub import global_signals

try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False


class RenderEngine(QThread):
    frame_ready = Signal(QImage)
    frame_ready_raw = Signal(object) # Emits (logical_time, np.ndarray)

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
        hive_logger.info("RenderEngine initialized.")

    def request_frame(self, logical_time):
        with QMutexLocker(self.mutex):
            self.playhead_logical = logical_time
            if not self.is_playing: self._force_render = True

    def set_playing(self, playing):
        with QMutexLocker(self.mutex):
            self.is_playing = playing
            hive_logger.info(f"Playback {'started' if playing else 'stopped'}.")
            
    def set_render_fps(self, fps):
        with QMutexLocker(self.mutex): self._target_fps = float(fps)
            
    def set_render_scale(self, scale):
        with QMutexLocker(self.mutex):
            self._render_scale = scale
            for reader in self.video_readers.values():
                reader["decoder"].set_scale(scale)
                reader["lkgf"] = None
            if not self.is_playing: self._force_render = True
                
    def set_preview_preset(self, preset_data, target_clip_id=None):
        with QMutexLocker(self.mutex):
            self.preview_preset = preset_data
            self.preview_target_clip_id = target_clip_id
            self.preview_start_ms = self.playhead_logical * 10
            self._force_render = True

    def _clear_readers(self):
        for reader_data in self.video_readers.values(): reader_data["decoder"].stop()
        self.video_readers.clear()

    def stop(self):
        self._run_flag = False
        self._clear_readers()
        self.wait()

    def run(self):
        while self._run_flag:
            start_time = time.time()
            with QMutexLocker(self.mutex):
                playing, current_logical, force = self.is_playing, self.playhead_logical, self._force_render
                self._force_render = False

            if playing or force:
                result = self._composite_frame(current_logical)
                if result:
                    canvas, active_file_paths, pending = result
                    
                    # 1. Emit legacy QImage (for UI/Thumbnails if needed)
                    self.frame_ready.emit(canvas)
                    
                    # 2. Emit raw Numpy RGBA for OpenGL Viewport
                    rgba_canvas = canvas.convertToFormat(QImage.Format_RGBA8888)
                    ptr = rgba_canvas.bits()
                    arr = np.frombuffer(ptr, np.uint8).reshape((rgba_canvas.height(), rgba_canvas.width(), 4))
                    raw_frame = arr.copy()
                    
                    # Emit tuple (logical_time, frame) for frame-accurate handle sync
                    self.frame_ready_raw.emit((current_logical, raw_frame))
                    
                    if playing:
                        if not hasattr(self, '_frame_count'): self._frame_count = 0
                        self._frame_count += 1
                        if self._frame_count % 30 == 0:
                            hive_logger.debug(f"RenderEngine: Active (Playhead: {current_logical})")
                    
                    # Scrub-to-Preview: If decoder is still seeking during scrub, force next render
                    if not playing and pending:
                        with QMutexLocker(self.mutex):
                            self._force_render = True
                            
                    stale = [k for k in list(self.video_readers.keys()) if k not in active_file_paths]
                    for k in stale:
                        self.video_readers[k]["decoder"].stop()
                        del self.video_readers[k]

            elapsed = time.time() - start_time
            sleep_time = max(0, (1.0 / self._target_fps) - elapsed)
            time.sleep(sleep_time if playing else 0.016)


    def _get_effective_clip(self, clip):
        if not getattr(self, "preview_preset", None): return clip
        ptype = self.preview_preset.get("type")
        if ptype not in ["effect", "transition", "caption"]: return clip
        target_id = getattr(self, "preview_target_clip_id", None)
        if target_id and clip.clip_id != target_id: return clip
        
        c = copy.copy(clip)
        c.applied_effects = copy.deepcopy(clip.applied_effects) if isinstance(clip.applied_effects, dict) else {}
        if ptype == "effect":
            pname = self.preview_preset.get("title")
            c.applied_effects.update({"applied_effects": [pname], "primary_effect": pname})
            from core.preset_loader import get_default_properties
            defaults = get_default_properties({"properties": self.preview_preset.get("preset_properties", {})})
            c.applied_effects.update(defaults)
        return c

    def _draw_media(self, painter, clip, current_ms, proj_w, proj_h):
        file_path = clip.file_path
        if clip.clip_type == "video" and app_config.get_setting("auto_proxies", True):
            if clip.proxy_path and os.path.exists(clip.proxy_path): file_path = clip.proxy_path
        if not os.path.exists(file_path): return False, None

        qimg = None
        pending_seek = False
        if clip.clip_type == "video":
            # SHARED RESOURCE OPTIMIZATION: Use file_path as key instead of clip_id.
            # This ensures that multiple clips referencing the same file share a single 
            # VideoDecoder and its 1GB FrameCache, drastically reducing memory usage.
            reader_key = file_path 
            if reader_key not in self.video_readers:
                decoder = VideoDecoder(file_path)
                decoder.set_scale(self._render_scale)
                decoder.start() 
                self.video_readers[reader_key] = {"decoder": decoder, "last_ms": -1.0, "lkgf": None}
            
            reader_data = self.video_readers[reader_key]
            decoder = reader_data["decoder"]
            speed = max(0.1, (clip.applied_effects or {}).get("Speed", 100) / 100.0)
            local_ms = ((current_ms - clip.start_time) * speed) + getattr(clip, 'trim_in', 0)
            
            diff = abs(local_ms - reader_data["last_ms"])
            frame_array = None
            
            seek_threshold = 1000 if self.is_playing else 100
            
            # If we are seeking or far away from current frame
            if not self.is_playing or diff > seek_threshold:
                target_pos = local_ms / 10.0
                # Seek Storm Fix: Allow 50ms (500ms) drift during playback to let decoder breathe
                seek_drift = 50.0 if self.is_playing else 0.1
                
                if abs(target_pos - reader_data.get("last_seek_pos", -1)) > seek_drift:
                    decoder.seek_to(target_pos)
                    reader_data["last_seek_pos"] = target_pos
                
                try:
                    # Balanced wait: 33ms (one frame at 30fps)
                    logical_pos, f = decoder.frame_queue.get(timeout=0.033)
                    frame_ms = logical_pos * 10.0
                    if abs(frame_ms - local_ms) < 500: # Generous window for seeks
                        frame_array, reader_data["last_ms"] = f, frame_ms
                except queue.Empty:
                    if not self.is_playing:
                        pending_seek = True
            else:
                # Normal playback: Drain queue to catch up
                while not decoder.frame_queue.empty():
                    try:
                        logical_pos, f = decoder.frame_queue.get_nowait()
                        frame_ms = logical_pos * 10.0
                        if frame_ms >= local_ms - 33: # Approx 1 frame window at 30fps
                            frame_array, reader_data["last_ms"] = f, frame_ms
                            break
                    except queue.Empty:
                        break

            if frame_array is not None: reader_data["lkgf"] = frame_array
            else: frame_array = reader_data["lkgf"]

            if frame_array is not None:
                # Phase 3 Prep: VideoDecoder now outputs RGBA. 
                # We convert to BGRA for legacy OpenCV effects, then back to RGBA for display.
                bgra = cv2.cvtColor(frame_array, cv2.COLOR_RGBA2BGRA)
                processed = self._apply_cv_effects(bgra, clip, current_ms, has_alpha=True)
                
                rgba = cv2.cvtColor(processed, cv2.COLOR_BGRA2RGBA)
                qimg = QImage(rgba.data, rgba.shape[1], rgba.shape[0], rgba.shape[2]*rgba.shape[1], QImage.Format_RGBA8888).copy()
                
        elif clip.clip_type == "image":
            img = cv2.imread(file_path, cv2.IMREAD_UNCHANGED)
            if img is not None:
                if len(img.shape) == 3 and img.shape[2] == 4:
                    img = self._apply_cv_effects(img, clip, current_ms, True)
                    qimg = QImage(cv2.cvtColor(img, cv2.COLOR_BGRA2RGBA).data, img.shape[1], img.shape[0], 4*img.shape[1], QImage.Format_RGBA8888).copy()
                else:
                    if len(img.shape) == 2: img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
                    img = self._apply_cv_effects(img, clip, current_ms)
                    qimg = QImage(cv2.cvtColor(img, cv2.COLOR_BGR2RGB).data, img.shape[1], img.shape[0], 3*img.shape[1], QImage.Format_RGB888).copy()

        if qimg and not qimg.isNull():
            props = clip.applied_effects or {}
            if hasattr(clip, 'get_animated_value'):
                rel_t = max(0.0, (current_ms - clip.start_time) / 10.0)
                sc, px, py, rot, op = [clip.get_animated_value(k, rel_t, props.get(k, d)) for k,d in [("Scale",100),("Position_X",0),("Position_Y",0),("Rotation",0),("Opacity",100)]]
            else: sc, px, py, rot, op = props.get("Scale",100), props.get("Position_X",0), props.get("Position_Y",0), props.get("Rotation",0), props.get("Opacity",100)
            
            painter.save()
            painter.setOpacity(op/100.0)
            painter.translate((proj_w / 2) + px, (proj_h / 2) + py)
            if rot != 0: painter.rotate(rot)
            iw, ih = qimg.width(), qimg.height()
            cw, ch = iw * (props.get("crop_w", 100)/100), ih * (props.get("crop_h", 100)/100)
            source_rect = QRectF(iw * (props.get("crop_x", 0)/100), ih * (props.get("crop_y", 0)/100), cw, ch)
            ratio = min(proj_w / cw, proj_h / ch)
            dw, dh = cw * ratio * (sc/100.0), ch * ratio * (sc/100.0)
            if props.get("Corner_Radius", 0) > 0:
                from PySide6.QtGui import QPainterPath
                path = QPainterPath()
                path.addRoundedRect(QRectF(-dw/2, -dh/2, dw, dh), props["Corner_Radius"], props["Corner_Radius"])
                painter.setClipPath(path)
            painter.drawImage(QRectF(-dw/2, -dh/2, dw, dh), qimg, source_rect)
            painter.restore()
            
        return pending_seek, file_path

    def _composite_frame(self, logical_time):
        if not CV2_AVAILABLE: return self._create_error_frame("OpenCV Missing"), set(), False
        project = project_manager.current_project
        if not project: return None
        proj_w, proj_h = project.resolution
        rw, rh = int(proj_w * self._render_scale), int(proj_h * self._render_scale)
        canvas = QImage(rw, rh, QImage.Format_ARGB32); canvas.fill(Qt.black)
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.Antialiasing, self._render_scale >= 1.0)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, self._render_scale >= 1.0)
        painter.scale(self._render_scale, self._render_scale)
        current_ms, active_file_paths, total_pending = int(logical_time * 10), set(), False
        for track in reversed(project.tracks):
            if track.is_hidden: continue
            for original in track.clips:
                clip = self._get_effective_clip(original)
                if clip.start_time <= current_ms < clip.end_time:
                    if clip.clip_type in ["video", "image"]: 
                        pending, active_path = self._draw_media(painter, clip, current_ms, proj_w, proj_h)
                        if pending: total_pending = True
                        if active_path and clip.clip_type == "video": active_file_paths.add(active_path)
                    elif clip.clip_type == "caption": self._draw_caption(painter, clip, current_ms, proj_w, proj_h)
        painter.end()
        return canvas, active_file_paths, total_pending

    def _apply_cv_effects(self, frame, clip, current_ms=0, has_alpha=False):
        if not isinstance(clip.applied_effects, dict): return frame
        rel_t = max(0.0, (current_ms - clip.start_time) / 10.0)
        fxs = clip.applied_effects.get("applied_effects", [])
        if not fxs: return frame
        amt = (clip.get_animated_value("effect_amount", rel_t, 100) if hasattr(clip, 'get_animated_value') else 100) / 100.0
        for fx in (fxs if isinstance(fxs, list) else [fxs]):
            fxl = fx.lower()
            if "blur" in fxl: frame = self._fx_blur(frame, amt, clip.applied_effects, clip, rel_t)
            elif "glow" in fxl: frame = self._fx_glow(frame, amt, clip.applied_effects, clip, rel_t)
            elif "vignette" in fxl: frame = self._fx_vignette(frame, amt, clip.applied_effects, clip, rel_t)
            elif "color" in fxl: frame = self._fx_color_grade(frame, amt, clip.applied_effects, clip, rel_t)
            elif "vhs" in fxl: frame = self._fx_vhs(frame, amt, clip.applied_effects, clip, rel_t)
            elif "glitch" in fxl: frame = self._fx_glitch(frame, amt, clip.applied_effects, clip, rel_t)
        return frame

    def _fx_blur(self, f, a, p, c, t):
        r = int((c.get_animated_value("radius", t, 15) if hasattr(c, 'get_animated_value') else 15) * a)
        if r < 1: return f
        return cv2.GaussianBlur(f, (r|1, r|1), 0)

    def _fx_glow(self, f, a, p, c, t):
        r = int((c.get_animated_value("radius", t, 30) if hasattr(c, 'get_animated_value') else 30) * a)
        if r < 1: return f
        w = f[:,:,:3] if f.shape[2]>=3 else f
        res = cv2.addWeighted(w, 1.0, cv2.GaussianBlur(w, (r|1, r|1), 0), a*0.5, 0)
        if f.shape[2]==4: f[:,:,:3]=res; return f
        return res

    def _fx_vignette(self, f, a, p, c, t):
        h, w = f.shape[:2]
        rp = (c.get_animated_value("radius", t, 70) if hasattr(c, 'get_animated_value') else 70)/100.0
        Y, X = np.ogrid[:h, :w]
        mask = np.clip(1.0 - np.sqrt((X-w/2)**2 + (Y-h/2)**2) / (np.sqrt((w/2)**2 + (h/2)**2) * max(0.1, rp)), 0, 1)
        return (f.astype(np.float32) * np.dstack([1.0 - (1.0 - mask) * a]*f.shape[2])).astype(np.uint8)

    def _fx_color_grade(self, f, a, p, c, t):
        br, co, sa = [ (c.get_animated_value(k, t, d) if hasattr(c, 'get_animated_value') else d) * a for k,d in [("brightness",0),("contrast",10),("saturation",15)]]
        w = f[:,:,:3].astype(np.float32); w += br
        fct = (259*(co+255))/(255*(259-co)); w = fct*(w-128)+128
        if abs(sa) > 0.1:
            hsv = cv2.cvtColor(np.clip(w,0,255).astype(np.uint8), cv2.COLOR_BGR2HSV).astype(np.float32)
            hsv[:,:,1] = np.clip(hsv[:,:,1]*(1+sa/100),0,255)
            w = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR).astype(np.float32)
        res = np.clip(w,0,255).astype(np.uint8)
        if f.shape[2]==4: f[:,:,:3]=res; return f
        return res

    def _fx_vhs(self, f, a, p, c, t):
        h, w = f.shape[:2]; res = (f[:,:,:3] if f.shape[2]>=3 else f).copy()
        sh = int((c.get_animated_value("chromatic_shift", t, 5) if hasattr(c, 'get_animated_value') else 5)*a)
        if sh > 0: res[:,sh:,2] = f[:,:-sh,2]; res[:,:-sh,0] = f[:,sh:,0]
        n = (c.get_animated_value("noise", t, 30) if hasattr(c, 'get_animated_value') else 30)/100*a
        if n > 0: res = np.clip(res.astype(np.int16)+(np.random.randint(-25,25,res.shape)*n).astype(np.int16),0,255).astype(np.uint8)
        if f.shape[2]==4: f[:,:,:3]=res; return f
        return res

    def _fx_glitch(self, f, a, p, c, t):
        h, w = f.shape[:2]; res = f.copy()
        sa = int((c.get_animated_value("shift_amount", t, 20) if hasattr(c, 'get_animated_value') else 20)*a)
        bs = max(2, int(c.get_animated_value("block_size", t, 10) if hasattr(c, 'get_animated_value') else 10))
        if sa < 1: return f
        for _ in range(max(1, int(h/bs*a*0.3))):
            y, s = random.randint(0, max(0, h-bs)), random.randint(-sa, sa)
            if s > 0: res[y:y+bs, s:] = f[y:y+bs, :w-s]
            elif s < 0: res[y:y+bs, :w+s] = f[y:y+bs, -s:]
        return res

    def _draw_caption(self, painter, clip, current_ms, proj_w, proj_h):
        p = clip.applied_effects or {}
        text = p.get("text", "") or clip.file_path or "New Caption"
        if p.get("preset_name") == "Typewriter": text = text[:int(len(text)*(max(0,min(1,(current_ms-clip.start_time)/(clip.end_time-clip.start_time)))))]
        t = max(0.0, (current_ms-clip.start_time)/10.0)
        def gv(k, d): return clip.get_animated_value(k, t, p.get(k, d)) if hasattr(clip, 'get_animated_value') else p.get(k, d)
        painter.save()
        painter.setOpacity(gv("Opacity", 100)/100.0)
        painter.translate(proj_w/2+gv("Position_X", 0), proj_h/2+gv("Position_Y", 0))
        rot, sc = gv("Rotation", 0), gv("Scale", 100)/100.0
        if rot != 0: painter.rotate(rot)
        if sc != 1.0: painter.scale(sc, sc)
        font = QFont(p.get("Font Family", "Arial"), max(1, int(gv("Font Size", 80))), QFont.Bold)
        painter.setFont(font); fm = painter.fontMetrics()
        lines = self._wrap_text(text, int(p.get("max_chars_per_line", 0)), bool(p.get("word_wrap", True)), int(p.get("max_lines", 0)))
        th = len(lines)*fm.height()
        for i, line in enumerate(lines):
            painter.setPen(QColor(p.get("Text Color", "#FFFFFF")))
            painter.drawText(QRectF(-500, -th/2+i*fm.height(), 1000, fm.height()), Qt.AlignCenter, line)
        painter.restore()

    def _wrap_text(self, text, m, w, l):
        if m <= 0 or not text: return [text] if text else [""]
        res = []
        for p in text.split('\n'):
            if not p.strip(): res.append(""); continue
            if len(p) <= m: res.append(p); continue
            if w:
                curr = ""
                for word in p.split(' '):
                    test = f"{curr} {word}".strip() if curr else word
                    if len(test) <= m: curr = test
                    else:
                        if curr: res.append(curr)
                        while len(word) > m: res.append(word[:m]); word = word[m:]
                        curr = word
                if curr: res.append(curr)
            else:
                for i in range(0, len(p), m): res.append(p[i:i + m])
        return res[:l] if l > 0 and len(res) > l else res

    def _create_error_frame(self, message):
        img = QImage(1280, 720, QImage.Format_ARGB32); img.fill(Qt.black)
        p = QPainter(img); p.setPen(Qt.white); p.setFont(QFont("Arial", 24, QFont.Bold))
        p.drawText(img.rect(), Qt.AlignCenter, message); p.end()
        return img
