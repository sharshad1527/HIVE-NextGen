import os
import hashlib
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QRect, QPoint, QSize
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QPainterPath, QPixmap, QPolygon
from core.app_config import app_config
from ui.timeline.timeline_workers import PersistentThumbnailWorker

class RenderingMixin:
    """Handles all painting and visual asset management for the timeline canvas."""

    def _on_waveform_ready(self, file_path, waveform):
        """Ingests processed audio arrays mapped by backend."""
        for item in self.items:
            if item.get("file_path") == file_path:
                item["waveform"] = waveform
        self.update()

    def _on_external_transform(self, clip_id, prop_name, value):
        """Called when the preview player moves/rotates a clip so timeline keeps local state synchronized."""
        for item in self.items:
            if item["id"] == clip_id:
                item[prop_name] = value
                break

    def _on_dynamic_thumb_loaded(self, cache_key, qimg):
        """Callback when background thread finishes decoding a video frame."""
        if not qimg.isNull():
            self.pixmap_cache[cache_key] = QPixmap.fromImage(qimg)
        
        self.pending_thumbs.discard(cache_key)
        self.update()

    def _get_dynamic_thumbnail(self, item, time_ms, target_height):
        """Fetches an exact video frame, prioritizing Memory -> Disk -> OpenCV Threads."""
        file_path = item.get("file_path")
        if not file_path or not os.path.exists(file_path):
            return None

        file_hash = hashlib.md5(file_path.encode()).hexdigest()
        
        time_ms_quantized = round(time_ms / 3000.0) * 3000
        cache_key = f"{file_hash}_{target_height}_{time_ms_quantized}"

        if cache_key in self.pixmap_cache:
            px = self.pixmap_cache[cache_key]
            return px if not px.isNull() else None

        disk_cache_path = os.path.join(self.get_project_cache_dir(), f"{cache_key}.jpg")
        if os.path.exists(disk_cache_path):
            px = self._get_pixmap(disk_cache_path, target_height)
            if px:
                self.pixmap_cache[cache_key] = px
                return px

        if cache_key not in self.pending_thumbs:
            if len(self.pending_thumbs) < 30: 
                self.pending_thumbs.add(cache_key)
                worker = PersistentThumbnailWorker.get_instance()
                try:
                    worker.signals.loaded.connect(self._on_dynamic_thumb_loaded, Qt.UniqueConnection)
                except Exception:
                    pass
                worker.request_thumbnail(file_path, time_ms_quantized, target_height, cache_key, disk_cache_path)

        fallback_path = os.path.join(self.get_project_cache_dir(), f"{file_hash}.jpg")
        if not os.path.exists(fallback_path):
            fallback_path = os.path.join(str(app_config.thumbnail_cache_path), f"{file_hash}.jpg")
        return self._get_pixmap(fallback_path, target_height)

    def _get_pixmap(self, path, height):
        """Loads generic image thumbnails cleanly."""
        if not path or not os.path.exists(path):
            return None
        cache_key = f"{path}_{height}"
        if cache_key not in self.pixmap_cache:
            px = QPixmap(path)
            if px.isNull():
                return None
            scaled = px.scaledToHeight(height, Qt.SmoothTransformation)
            self.pixmap_cache[cache_key] = scaled
        return self.pixmap_cache.get(cache_key)

    def _recalc_height(self):
        total_h = 32 + sum(t["height"] for t in self.track_defs)
        self.setFixedHeight(total_h)

    def set_zoom(self, zoom):
        self.zoom_factor = zoom
        self.setMinimumWidth(max(int(self.max_logical_width * self.zoom_factor), 100))
        self.update()

    def get_track_y(self, track_id):
        current_y = 32 
        for t in self.track_defs:
            if t["id"] == track_id:
                return current_y, t["height"]
            current_y += t["height"]
        return 0, 0

    def _get_track_at_y(self, y):
        current_y = 32
        for t in self.track_defs:
            if current_y <= y <= current_y + t["height"]: return t["id"]
            current_y += t["height"]
        return None

    def draw_keyframes(self, painter: QPainter, item: dict, clip_rect: QRect, z: float):
        if item["id"] not in self.selected_ids:
            return

        backend_clip = self._get_backend_clip(item["id"])
        if not backend_clip or not hasattr(backend_clip, 'animations'): return
        
        painter.save()
        diamond_size = 7
        painter.setBrush(QColor("#e66b2c"))
        painter.setPen(QPen(QColor("white"), 1))
        
        for prop_name, anim_track in backend_clip.animations.items():
            if not getattr(anim_track, 'enabled', True): continue
            for kf in getattr(anim_track, 'keyframes', []):
                kf_abs_time = item["x"] + kf.time
                kf_x = int(kf_abs_time * z)
                kf_y = clip_rect.center().y()
                
                poly = [
                    QPoint(kf_x, kf_y - diamond_size),
                    QPoint(kf_x + diamond_size, kf_y),
                    QPoint(kf_x, kf_y + diamond_size),
                    QPoint(kf_x - diamond_size, kf_y)
                ]
                painter.drawPolygon(QPolygon(poly))
        painter.restore()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        z = self.zoom_factor

        clip_rect = event.rect()
        visible_left = clip_rect.left()
        visible_right = clip_rect.right()

        painter.fillRect(clip_rect, QColor("#111111"))

        if self._drop_target_rect:
            if self._drop_target_type == "clip":
                painter.fillRect(self._drop_target_rect, QColor(138, 43, 226, 60))
                painter.setPen(QPen(QColor(138, 43, 226, 255), 2))
                painter.drawRect(self._drop_target_rect)
            elif self._drop_target_type == "transition":
                painter.fillRect(self._drop_target_rect, QColor(66, 153, 225, 100)) 
                painter.setPen(QPen(QColor(66, 153, 225, 255), 2))
                painter.drawRect(self._drop_target_rect)
            elif self._drop_target_type in ["track", "track_new"]:
                painter.fillRect(self._drop_target_rect, QColor(255, 255, 255, 20))
                painter.setPen(QPen(QColor(230, 107, 44, 150), 2, Qt.DashLine))
                painter.drawRect(self._drop_target_rect)
            elif self._drop_target_type == "track_insert":
                painter.fillRect(self._drop_target_rect, QColor(230, 107, 44, 255))
                painter.setPen(QPen(QColor(255, 255, 255, 200), 2))
                y_center = self._drop_target_rect.top() + 2
                painter.drawLine(0, y_center, self.width(), y_center)

        painter.setPen(QPen(QColor("#1f1f1f"), 1))
        current_y = 32
        painter.drawLine(visible_left, current_y, visible_right, current_y)
        for t in self.track_defs:
            ty, th = self.get_track_y(t["id"])
            current_y += th
            painter.drawLine(visible_left, current_y, visible_right, current_y)
            if self.is_track_locked(t["id"]):
                painter.fillRect(visible_left, ty, clip_rect.width(), th, QColor(0, 0, 0, 90))

        items_by_id = {item["id"]: item for item in self.items}
        
        word_groups = {}
        for item in self.items:
            if self.is_track_hidden(item["track"]): continue
            
            if item["type"] == "word" and "parent_id" in item:
                parent = items_by_id.get(item["parent_id"])
                if parent:
                    p_start = parent["x"] * z
                    p_end = (parent["x"] + parent["w"]) * z
                    if p_end < visible_left - 50 or p_start > visible_right + 50:
                        continue

                key = (item["track"], item["parent_id"])
                if key not in word_groups:
                    word_groups[key] = {"words": [], "hovered": False}
                word_groups[key]["words"].append(item)
                if self.hovered_id == item["id"] or item["id"] in self.selected_ids:
                    word_groups[key]["hovered"] = True

        for (track_id, pid), data in word_groups.items():
            parent = items_by_id.get(pid)
            if parent:
                ty, th = self.get_track_y(track_id)
                if th > 0:
                    rect_y = ty + (th - 36) / 2
                    c_rect = QRect(int(parent["x"] * z), int(rect_y), int(parent["w"] * z), 36)
                    c_path = QPainterPath()
                    c_path.addRoundedRect(c_rect, 4, 4)
                    
                    border_color = QColor(230, 107, 44, 128) if data["hovered"] else QColor("#333333")
                    painter.fillPath(c_path, QColor("#1a1a1a"))
                    painter.setPen(QPen(border_color, 1))
                    painter.drawPath(c_path)

        for item in self.items:
            if self.is_track_hidden(item["track"]): continue
            
            item_start = item["x"] * z
            item_end = (item["x"] + item["w"]) * z
            if item_end < visible_left - 50 or item_start > visible_right + 50:
                continue

            ty, th = self.get_track_y(item["track"])
            if th == 0: continue 
            draw_y = item.get("visual_y", ty)
            
            is_selected = item["id"] in self.selected_ids
            is_hovered = (self.hovered_id == item["id"])
            
            if item["type"] == "word":
                parent = items_by_id.get(item.get("parent_id"))
                if parent:
                    word_center = item["x"] + item["w"] / 2
                    if not (parent["x"] <= word_center <= parent["x"] + parent["w"]):
                        continue
                
                word_h = 24
                word_y = draw_y + (th - word_h) / 2
                word_rect = QRect(int(item["x"] * z) + 2, int(word_y), int(item["w"] * z) - 4, word_h)
                word_path = QPainterPath()

                if is_selected:
                    word_rect = word_rect.adjusted(-2, -2, 2, 2)
                    word_path.addRoundedRect(word_rect, 4, 4)
                    painter.fillPath(word_path, QColor("#e66b2c"))
                    painter.setPen(QColor("#ffffff"))
                    painter.setFont(QFont("Arial", 8, QFont.Bold))
                elif is_hovered:
                    word_path.addRoundedRect(word_rect, 4, 4)
                    painter.fillPath(word_path, QColor("#2a2a2a"))
                    painter.setPen(QColor("#e0e0e0"))
                    painter.setFont(QFont("Arial", 8))
                else:
                    word_path.addRoundedRect(word_rect, 4, 4)
                    painter.fillPath(word_path, Qt.transparent)
                    painter.setPen(QColor("#a0a0a0"))
                    painter.setFont(QFont("Arial", 8))
                    
                painter.drawText(word_rect, Qt.AlignCenter, f"[{item['text']}]")
                continue

            rect = QRect(int(item["x"] * z), int(draw_y) + 4, int(item["w"] * z), th - 8)
            path = QPainterPath()
            path.addRoundedRect(rect, 4, 4)

            if is_selected and item["type"] in ["video", "image", "effect", "caption"] and self.selected_item_type not in ["transition_in", "transition_out", "clip_effect"]:
                painter.setPen(QPen(QColor(230, 107, 44, 180), 2))
                painter.drawPath(path)

            if item["type"] == "caption":
                bg_color = QColor(230, 107, 44, 80) if is_selected else QColor(230, 107, 44, 40)
                painter.fillPath(path, bg_color)
                painter.setPen(QColor("#ffffff"))
                painter.setFont(QFont("Arial", 8, QFont.Bold))
                painter.drawText(rect, Qt.AlignCenter, item["text"])
                self.draw_keyframes(painter, item, rect, z)
                
            elif item["type"] == "effect":
                painter.fillPath(path, QColor(138, 43, 226, 80))
                painter.setPen(QColor("#e0b0ff"))
                painter.setFont(QFont("Arial", 8, QFont.Bold))
                painter.drawText(rect, Qt.AlignCenter, item["text"])
                self.draw_keyframes(painter, item, rect, z)

            elif item["type"] in ["video", "image"]:
                bg_color = QColor("#1a1a1a") if item["type"]=="video" else QColor("#1f1a30")
                if not is_selected and not is_hovered: bg_color.setAlpha(180)
                
                painter.fillPath(path, bg_color)
                painter.drawPath(path)
                
                has_wave = item["type"] == "video" and item.get("waveform")
                thumb_h = int((th - 8) * 0.65) if has_wave else int(th - 8)
                thumb_rect = QRect(rect.left(), rect.top(), rect.width(), thumb_h)
                
                if thumb_h > 0:
                    if item["type"] == "image":
                        thumb_path = item.get("file_path")
                        px = self._get_pixmap(thumb_path, thumb_h)
                        if px:
                            painter.save()
                            painter.setClipRect(thumb_rect)
                            
                            px_w = px.width()
                            item_phys_x = thumb_rect.left()
                            start_i = max(0, (visible_left - item_phys_x) // px_w)
                            end_i = min(thumb_rect.width() // px_w + 1, (visible_right - item_phys_x) // px_w + 2)
                            
                            for i in range(start_i, end_i):
                                painter.drawPixmap(item_phys_x + i * px_w, thumb_rect.top(), px)
                            
                            overlay_color = QColor(0, 0, 0, 140) if not is_selected and not is_hovered else QColor(0, 0, 0, 90)
                            painter.fillRect(thumb_rect, overlay_color)
                            painter.restore()
                            
                    elif item["type"] == "video":
                        painter.save()
                        painter.setClipRect(thumb_rect)
                        
                        thumb_w_physical = int(thumb_h * 1.777) 
                        if thumb_w_physical < 10: thumb_w_physical = 100
                        
                        item_phys_x = thumb_rect.left()
                        start_i = max(0, (visible_left - item_phys_x) // thumb_w_physical)
                        end_i = min(thumb_rect.width() // thumb_w_physical + 1, (visible_right - item_phys_x) // thumb_w_physical + 2)
                        
                        source_in = item.get("source_in", 0)
                        
                        for i in range(start_i, end_i):
                            logical_offset = (i * thumb_w_physical) / z
                            time_ms = (source_in + logical_offset) * 10
                            
                            px = self._get_dynamic_thumbnail(item, time_ms, thumb_h)
                            if px:
                                painter.drawPixmap(item_phys_x + i * thumb_w_physical, thumb_rect.top(), px)
                        
                        overlay_color = QColor(0, 0, 0, 140) if not is_selected and not is_hovered else QColor(0, 0, 0, 90)
                        painter.fillRect(thumb_rect, overlay_color)
                        painter.restore()
                
                if has_wave:
                    wave_data = item.get("waveform", [])
                    if wave_data:
                        painter.save()
                        
                        wave_bg_h = rect.height() - thumb_h
                        wave_bg_rect = QRect(rect.left(), thumb_rect.bottom(), rect.width(), wave_bg_h)
                        
                        painter.setClipRect(wave_bg_rect)
                        painter.fillRect(wave_bg_rect, QColor(0, 0, 0, 150))
                        
                        wave_color = QColor(160, 160, 160, 220) if is_selected else QColor(0, 150, 150, 180) 
                        bar_width = 2 if z > 0.5 else 1
                        wave_pen = QPen(wave_color, bar_width)
                        wave_pen.setCapStyle(Qt.RoundCap)
                        painter.setPen(wave_pen)
                        
                        max_wave_h = wave_bg_h - 4
                        base_y = wave_bg_rect.bottom() - max_wave_h/2 - 2
                        
                        physical_step = max(3, bar_width * 2) 
                        logical_step = physical_step / z
                        
                        start_logical = max(0, (visible_left - 10) / z - item["x"])
                        end_logical = min(item["w"], (visible_right + 10) / z - item["x"])
                        
                        start_i = int(start_logical / logical_step)
                        end_i = int(end_logical / logical_step) + 1
                        
                        samples_per_logical = 50.0 / 100.0
                        source_in = item.get("source_in", 0)
                        
                        for i in range(start_i, end_i):
                            logical_w_pos = item["x"] + (i * logical_step)
                            logical_offset = logical_w_pos - item["x"]
                            hx = int(logical_w_pos * z)
                            
                            sample_idx = int((source_in + logical_offset) * samples_per_logical)
                            val = wave_data[sample_idx] if 0 <= sample_idx < len(wave_data) else 0
                            volume_pct = float(item.get("Volume", 100)) / 100.0
                            val *= volume_pct
                                
                            h = (val / 100.0) * max_wave_h
                            safe_h = max(2, min(h, max_wave_h))
                            painter.drawLine(hx, int(base_y - safe_h/2), hx, int(base_y + safe_h/2))
                            
                        painter.restore()

            elif item["type"] == "audio":
                if is_selected:
                    painter.fillPath(path, QColor(50, 50, 50, 180))
                    painter.setPen(QPen(QColor("#666666"), 1))
                    wave_color = QColor("#777777")
                elif is_hovered:
                    painter.fillPath(path, QColor(35, 35, 35, 180))
                    painter.setPen(QPen(QColor("#555555"), 1))
                    wave_color = QColor("#666666")
                else:
                    painter.fillPath(path, QColor(20, 20, 20, 180))
                    painter.setPen(QPen(QColor("#333333"), 1))
                    wave_color = QColor("#555555")

                painter.drawPath(path)
                
                painter.setPen(QColor("#d1d1d1"))
                painter.setFont(QFont("Arial", 8, QFont.Bold))
                painter.drawText(rect.adjusted(5, 5, -5, -5), Qt.AlignLeft | Qt.AlignTop, item["text"])
                
                wave_data = item.get("waveform", [])
                
                bar_width = 2 if z > 0.5 else 1
                wave_pen = QPen(wave_color, bar_width) 
                wave_pen.setCapStyle(Qt.RoundCap)               
                painter.setPen(wave_pen)
                
                base_y = draw_y + th/2
                max_wave_h = th - 16 
                
                physical_step = max(3, bar_width * 2) 
                logical_step = physical_step / z
                
                start_logical = max(0, (visible_left - 10) / z - item["x"])
                end_logical = min(item["w"], (visible_right + 10) / z - item["x"])
                
                start_i = int(start_logical / logical_step)
                end_i = int(end_logical / logical_step) + 1
                
                samples_per_logical = 50.0 / 100.0 
                
                source_in = item.get("source_in", 0)
                
                if wave_data:
                    for i in range(start_i, end_i):
                        logical_w_pos = item["x"] + (i * logical_step)
                        logical_offset = logical_w_pos - item["x"]
                        
                        hx = int(logical_w_pos * z)
                        
                        sample_idx = int((source_in + logical_offset) * samples_per_logical)
                        
                        val = wave_data[sample_idx] if 0 <= sample_idx < len(wave_data) else 0
                        volume_pct = float(item.get("Volume", 100)) / 100.0
                        val *= volume_pct
                            
                        h = (val / 100.0) * max_wave_h
                        safe_h = max(2, min(h, max_wave_h))
                        painter.drawLine(hx, int(base_y - safe_h/2), hx, int(base_y + safe_h/2))
                else:
                    volume_pct = float(item.get("Volume", 100)) / 100.0
                    for i in range(start_i, end_i):
                        logical_w_pos = item["x"] + (i * logical_step)
                        hx = int(logical_w_pos * z)
                        wave_idx = int(logical_w_pos) % len(self.audio_waveforms)
                        h = self.audio_waveforms[wave_idx] * volume_pct 
                        safe_h = min(h, max_wave_h) 
                        painter.drawLine(hx, int(base_y - safe_h/2), hx, int(base_y + safe_h/2))

            if item["type"] in ["video", "image"]:
                if item.get("transition_in") or item.get("transition"):
                    frames = item.get("transition_in_duration", 30)
                    t_w_physical = int((frames / 30.0) * 100 * z)
                    t_rect = QRect(rect.left() - int(t_w_physical/2), rect.top(), t_w_physical, rect.height())
                    
                    fill_color = QColor(66, 153, 225, 200) if is_selected and self.selected_item_type == "transition_in" else QColor(66, 153, 225, 150)
                    painter.fillRect(t_rect, fill_color) 
                    painter.setPen(QPen(QColor(66, 153, 225, 255), 2 if is_selected and self.selected_item_type == "transition_in" else 1))
                    painter.drawRect(t_rect)
                    painter.setPen(QColor("#ffffff"))
                    painter.setFont(QFont("Arial", 8, QFont.Bold))
                    painter.drawText(t_rect, Qt.AlignCenter, "T")
                    
                if item.get("transition_out"):
                    frames = item.get("transition_out_duration", 30)
                    t_w_physical = int((frames / 30.0) * 100 * z)
                    t_rect = QRect(rect.right() - int(t_w_physical/2), rect.top(), t_w_physical, rect.height())
                    
                    fill_color = QColor(66, 153, 225, 200) if is_selected and self.selected_item_type == "transition_out" else QColor(66, 153, 225, 150)
                    painter.fillRect(t_rect, fill_color) 
                    painter.setPen(QPen(QColor(66, 153, 225, 255), 2 if is_selected and self.selected_item_type == "transition_out" else 1))
                    painter.drawRect(t_rect)
                    painter.setPen(QColor("#ffffff"))
                    painter.setFont(QFont("Arial", 8, QFont.Bold))
                    painter.drawText(t_rect, Qt.AlignCenter, "T")

                painter.setPen(QColor("#d1d1d1"))
                prefix = ""
                if item.get("freeze"): prefix += "[F] "
                if item.get("reverse"): prefix += "[Rev] "
                if item.get("mirror"): prefix += "[M] "
                if item.get("rotate"): prefix += "[Rot] "
                
                crop_type = item.get("crop_preset", "Original")
                if crop_type != "Original": prefix += f"[{crop_type}] "
                elif item.get("crop"): prefix += "[C] "
                
                painter.setFont(QFont("Arial", 8, QFont.Bold))
                painter.drawText(rect.adjusted(5, 5, -5, -5), Qt.AlignLeft | Qt.AlignTop, prefix + item["text"])

                if item.get("applied_effects"):
                    fx_rect = QRect(rect.right() - 22, rect.top() + 4, 18, 16)
                    fill_color = QColor(155, 89, 182, 220) if is_selected and self.selected_item_type == "clip_effect" else QColor(155, 89, 182, 180)
                    painter.fillRect(fx_rect, fill_color) 
                    painter.setPen(QPen(QColor("#e0b0ff"), 1 if is_selected and self.selected_item_type == "clip_effect" else 0))
                    painter.drawRect(fx_rect)
                    painter.setPen(QColor("#ffffff"))
                    painter.setFont(QFont("Arial", 7, QFont.Bold))
                    painter.drawText(fx_rect, Qt.AlignCenter, "FX")
                    
            self.draw_keyframes(painter, item, rect, z)

        if self.marquee_start and self.marquee_current:
            rect = QRect(self.marquee_start, self.marquee_current).normalized()
            painter.fillRect(rect, QColor(230, 107, 44, 40))
            painter.setPen(QPen(QColor(230, 107, 44, 200), 1))
            painter.drawRect(rect)

        ruler_y = self.v_scroll_y
        
        painter.fillRect(visible_left, ruler_y, clip_rect.width(), 32, QColor("#131313"))
        painter.setPen(QPen(QColor("#1f1f1f"), 1))
        painter.drawLine(visible_left, ruler_y + 32, visible_right, ruler_y + 32)
        
        logical_width_to_draw = int(self.width() / z)
        pixels_per_second = 100 * z
        
        if pixels_per_second >= 300: 
            start_frame = max(0, int((visible_left / z) / 100.0 * 30) - 10)
            end_frame = int((visible_right / z) / 100.0 * 30) + 10
            
            for f in range(start_frame, end_frame):
                logical_x = (f / 30.0) * 100.0
                x = int(logical_x * z)
                
                if f % 30 == 0:
                    painter.setPen(QPen(QColor("#555555"), 1))
                    painter.drawLine(x, ruler_y + 16, x, ruler_y + 32)
                    secs = (f // 30) % 60
                    mins = (f // 30) // 60
                    painter.setFont(QFont("monospace", 8, QFont.Bold))
                    painter.drawText(x + 4, ruler_y + 26, f"00:{mins:02d}:{secs:02d}:00")
                elif f % 5 == 0:
                    painter.setPen(QPen(QColor("#404040"), 1))
                    painter.drawLine(x, ruler_y + 22, x, ruler_y + 32)
                    painter.setFont(QFont("monospace", 7))
                    painter.setPen(QColor("#777777"))
                    painter.drawText(x + 2, ruler_y + 31, f"{f%30:02d}f")
                else:
                    painter.setPen(QPen(QColor("#2a2a2a"), 1))
                    painter.drawLine(x, ruler_y + 26, x, ruler_y + 32)

        else: 
            min_pixels_for_text = 60
            if pixels_per_second >= min_pixels_for_text:
                major_step, medium_step, minor_step = 100, 50, 10
            elif pixels_per_second * 2 >= min_pixels_for_text:
                major_step, medium_step, minor_step = 200, 100, 50
            elif pixels_per_second * 5 >= min_pixels_for_text:
                major_step, medium_step, minor_step = 500, 100, 0
            elif pixels_per_second * 10 >= min_pixels_for_text:
                major_step, medium_step, minor_step = 1000, 500, 0
            elif pixels_per_second * 30 >= min_pixels_for_text:
                major_step, medium_step, minor_step = 3000, 1000, 0
            elif pixels_per_second * 60 >= min_pixels_for_text: 
                major_step, medium_step, minor_step = 6000, 3000, 0
            elif pixels_per_second * 300 >= min_pixels_for_text: 
                major_step, medium_step, minor_step = 30000, 15000, 0
            else: 
                major_step, medium_step, minor_step = 60000, 30000, 0

            smallest_step = minor_step if minor_step > 0 else (medium_step if medium_step > 0 else major_step)
            if smallest_step * z < 4:
                smallest_step = medium_step if medium_step > 0 and medium_step * z >= 4 else major_step

            start_logical_x = max(0, int(visible_left / z) - major_step)
            start_logical_x -= (start_logical_x % smallest_step)
            end_logical_x = min(logical_width_to_draw, int(visible_right / z) + major_step)

            painter.setFont(QFont("monospace", 8))
            for logical_x in range(start_logical_x, end_logical_x + smallest_step, smallest_step):
                x = int(logical_x * z)
                if logical_x % major_step == 0:
                    painter.setPen(QPen(QColor("#555555"), 1))
                    painter.drawLine(x, ruler_y + 16, x, ruler_y + 32)
                    
                    total_seconds = logical_x // 100
                    hours = total_seconds // 3600
                    mins = (total_seconds % 3600) // 60
                    secs = total_seconds % 60
                    
                    painter.drawText(x + 4, ruler_y + 26, f"{hours:02d}:{mins:02d}:{secs:02d}")
                elif medium_step > 0 and logical_x % medium_step == 0:
                    painter.setPen(QPen(QColor("#404040"), 1))
                    painter.drawLine(x, ruler_y + 22, x, ruler_y + 32)
                elif minor_step > 0 and logical_x % minor_step == 0:
                    painter.setPen(QPen(QColor("#2a2a2a"), 1))
                    painter.drawLine(x, ruler_y + 26, x, ruler_y + 32)

        if self.snap_line_x is not None:
            snap_px = int(self.snap_line_x * z)
            painter.setPen(QPen(QColor("#e66b2c"), 2, Qt.DashLine))
            painter.drawLine(snap_px, 0, snap_px, self.height())

        if self.active_tool == "blade" and self.blade_line_x is not None:
            blade_px = int(self.blade_line_x * z)
            painter.setPen(QPen(QColor("#ff3b30"), 1, Qt.DashLine))
            painter.drawLine(blade_px, 0, blade_px, self.height())
            painter.setBrush(QColor("#ff3b30"))
            painter.setPen(Qt.NoPen)
            painter.drawPolygon([
                QPoint(blade_px - 5, ruler_y),
                QPoint(blade_px + 5, ruler_y),
                QPoint(blade_px, ruler_y + 6)
            ])

        playhead_physical_x = int(self.logical_playhead * z)
        
        painter.setPen(QPen(QColor(230, 107, 44, 80), 4))
        painter.drawLine(playhead_physical_x, ruler_y, playhead_physical_x, self.height())
        
        painter.setPen(QPen(QColor("#e66b2c"), 1))
        painter.drawLine(playhead_physical_x, ruler_y, playhead_physical_x, self.height())
        
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#e66b2c"))
        
        path = QPainterPath()
        path.moveTo(playhead_physical_x - 7, ruler_y)
        path.lineTo(playhead_physical_x + 7, ruler_y)
        path.lineTo(playhead_physical_x + 7, ruler_y + 10)
        path.lineTo(playhead_physical_x, ruler_y + 18)
        path.lineTo(playhead_physical_x - 7, ruler_y + 10)
        path.closeSubpath()
        painter.drawPath(path)
        
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(QPoint(playhead_physical_x - 1, ruler_y + 5), 3, 3)
