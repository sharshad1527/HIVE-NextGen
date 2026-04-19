# ui/timeline/timeline_canvas.py
import random
import copy
import json
import os
import hashlib
import uuid
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QRect, QPoint, Signal, QTimer, QThreadPool, QCoreApplication
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QPainterPath, QCursor, QPixmap

from core.signal_hub import global_signals
from core.models import ProjectData, TrackData, ClipData
from core.project_manager import project_manager
from core.app_config import app_config
from core.media_manager import media_manager
from .timeline_workers import FrameFetchWorker

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False


class TracksCanvas(QWidget):
    """Custom painted widget that draws the actual timeline tracks, ruler, and playhead"""
    
    item_clicked = Signal(str, str, dict)
    scroll_requested = Signal(int)
    v_scroll_requested = Signal(int)
    zoom_requested = Signal(int)
    tracks_changed = Signal()
    v1_duration_changed = Signal(float)
    playhead_changed = Signal(float)
    state_changed = Signal() # Emits whenever an edit is made to trigger Auto-Save tracking

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        
        self._initialized = False  # Guard: prevents sync_to_project before project is loaded
        self.zoom_factor = 1.0
        self.max_logical_width = 0
        self.logical_playhead = 0.0 
        self.v_scroll_y = 0 
        
        # Tool States
        self.active_tool = "pointer"
        self.magnet_enabled = True
        self.v1_gravity_enabled = True
        self.snap_line_x = None
        self.blade_line_x = None
        
        self.track_defs = [] 
        self.track_states = {}
        
        self._drop_target_rect = None
        self._drop_target_type = None
        self._drop_target_item = None
        self._drop_target_edge = None
        
        self.items = []
        self.audio_waveforms = [random.randint(10, 40) for _ in range(300)] # Fallback
        
        self.pixmap_cache = {} 
        self.pending_thumbs = set()
        
        # App Teardown Protection
        self.thread_pool = QThreadPool.globalInstance()
        self.thread_pool.setMaxThreadCount(min(4, self.thread_pool.maxThreadCount()))
        app = QCoreApplication.instance()
        if app:
            app.aboutToQuit.connect(self._cleanup_threads)
        
        self._click_physical_pos = None
        self._click_logical_x = 0
        self._potential_action = None
        self._potential_item = None
        self._potential_edge = None
        self._drag_started = False
        
        self.selected_ids = set()
        self.selected_item_type = ""
        self.marquee_start = None
        self.marquee_current = None
        self.marquee_initial_selection = set()
        self.drag_start_positions = {}
        
        self.hovered_id = ""
        self.dragging_item = "" 
        self.resizing_item = ""
        self.resize_edge = "" 
        self.drag_offset_x = 0  
        self.drag_offset_y = 0  
        self.original_track = "" 
        self.original_x = 0      
        
        self.history = []
        self.history_idx = -1
        
        self.auto_scroll_timer = QTimer(self)
        self.auto_scroll_timer.timeout.connect(self._do_auto_scroll)
        self.scroll_dx = 0
        
        self.setMouseTracking(True)
        self._cleanup_empty_tracks()
        self._apply_magnetic_v1()
        self.update_max_width()
        # NOTE: Do NOT call save_state() here — it would call sync_to_project()
        # and overwrite the loaded project's tracks with empty items before
        # load_from_project has a chance to populate self.items.

        global_signals.waveform_ready.connect(self._on_waveform_ready)
        if hasattr(global_signals, 'clip_transform_changed'):
            global_signals.clip_transform_changed.connect(self._on_external_transform)

    def _cleanup_threads(self):
        """Clears pending thumbnail loads to prevent crashes on exit."""
        self.thread_pool.clear()

    def get_project_cache_dir(self):
        """Returns a local /cache folder inside the current project to store thumbnails."""
        if hasattr(project_manager, 'current_project') and project_manager.current_project:
            try:
                proj_name = project_manager.current_project.name
                proj_dir = os.path.join(str(app_config.default_project_path), proj_name)
                cache_dir = os.path.join(proj_dir, "cache")
                os.makedirs(cache_dir, exist_ok=True)
                return cache_dir
            except Exception:
                pass
        # Fallback
        return str(app_config.thumbnail_cache_path)

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
                # DO NOT CALL save_state() here, since dragged timeline events will save state on release
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
        
        # Quantize to 3 seconds (3000ms) for huge performance gains
        time_ms_quantized = round(time_ms / 3000.0) * 3000
        cache_key = f"{file_hash}_{target_height}_{time_ms_quantized}"

        # 1. RAM Cache (Instant Delivery)
        if cache_key in self.pixmap_cache:
            px = self.pixmap_cache[cache_key]
            return px if not px.isNull() else None

        # 2. Disk Cache (Fast Delivery - avoids re-decoding across reboots)
        disk_cache_path = os.path.join(self.get_project_cache_dir(), f"{cache_key}.jpg")
        if os.path.exists(disk_cache_path):
            px = self._get_pixmap(disk_cache_path, target_height)
            if px:
                self.pixmap_cache[cache_key] = px
                return px

        # 3. Generation via OpenCV (Heavy - Pushed to Background Thread)
        if cache_key not in self.pending_thumbs:
            if len(self.pending_thumbs) < 30:  # Limit queue depth to prevent extreme lag on fast scrubbing
                self.pending_thumbs.add(cache_key)
                worker = FrameFetchWorker(file_path, time_ms_quantized, target_height, cache_key, disk_cache_path)
                worker.signals.loaded.connect(self._on_dynamic_thumb_loaded)
                self.thread_pool.start(worker)

        # Immediate Fallback to the main generic thumbnail while loading to prevent blinking
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
        return self.pixmap_cache[cache_key]

    def get_formatted_duration(self):
        """Calculates total sequence duration and returns an HH:MM:SS:FF string for Hub syncing."""
        duration_logical = self.get_v1_duration()
        total_seconds = int(duration_logical // 100)
        frames = int((duration_logical % 100) / 100 * 30)
        
        hours = total_seconds // 3600
        mins = (total_seconds % 3600) // 60
        secs = total_seconds % 60
        
        return f"{hours:02d}:{mins:02d}:{secs:02d}:{frames:02d}"

    def load_from_project(self, project: ProjectData):
        """Translates backend ProjectData into UI timeline clips."""
        self.items.clear()
        
        if project and project.tracks:
            for track in project.tracks:
                for clip in track.clips:
                    ui_x = clip.start_time / 10.0
                    ui_w = (clip.end_time - clip.start_time) / 10.0
                    
                    item = {
                        "id": clip.clip_id,
                        "track": track.track_id, 
                        "type": clip.clip_type,
                        "text": os.path.basename(clip.file_path) if clip.file_path else "Media",
                        "file_path": clip.file_path,
                        "x": ui_x,
                        "w": ui_w,
                        "max_w": clip.applied_effects.get("max_w", float('inf')) if isinstance(clip.applied_effects, dict) else float('inf'),
                        "source_in": clip.applied_effects.get("source_in", 0) if isinstance(clip.applied_effects, dict) else 0
                    }
                    
                    if isinstance(clip.applied_effects, dict):
                        for key, val in clip.applied_effects.items():
                            item[key] = val
                            
                    self.items.append(item)
                    if item["type"] in ["audio", "video"] and item["file_path"]:
                        media_manager.request_waveform(item["file_path"])
                    
        self._initialized = True  # Now safe to sync_to_project
        self._cleanup_empty_tracks()
        self._apply_magnetic_v1()
        self.update_max_width()
        self.save_state()
        self.update()

    def sync_to_project(self):
        """Packs current visual timeline blocks back into the backend Brain."""
        if not project_manager.current_project:
            return
        if not self._initialized:
            return  # Guard: skip syncing empty items before project is loaded
            
        new_tracks = []
        track_map = {}
        
        for item in self.items:
            t_id = item["track"]
            if t_id not in track_map:
                track_map[t_id] = []
            track_map[t_id].append(item)
            
        for t_def in self.track_defs:
            t_id = t_def["id"]
            group = t_def["group"]
            clips = []
            
            for item in track_map.get(t_id, []):
                # Clean out UI-only objects (like inf floats/waveforms) that crash MsgPack saving
                metadata = {}
                skip_keys = {"id", "track", "type", "text", "file_path", "x", "w", "visual_y", "waveform"}
                for k, v in item.items():
                    if k in skip_keys:
                        continue
                    # Filter out float('inf') which crashes msgpack
                    if isinstance(v, float) and (v == float('inf') or v == float('-inf') or v != v):
                        continue
                    metadata[k] = v
                
                actual_file_path = item.get("file_path", item.get("text", ""))
                
                # For captions, preserve the text in applied_effects
                if item.get("type") == "caption":
                    if "text" not in metadata:
                        metadata["text"] = item.get("text", "New Caption")
                
                clips.append(ClipData(
                    clip_id=item["id"],
                    clip_type=item["type"],
                    file_path=actual_file_path, 
                    start_time=int(item["x"] * 10), 
                    end_time=int((item["x"] + item["w"]) * 10),
                    applied_effects=metadata
                ))
                
            new_tracks.append(TrackData(
                track_name=t_def["label"],
                track_type=group,
                track_id=t_id,
                clips=clips,
                is_hidden=self.track_states.get(t_id, {}).get("hidden", False)
            ))
            
        project_manager.current_project.tracks = new_tracks

    def _emit_selection_state(self):
        if not self.selected_ids:
            self.item_clicked.emit("", "", {})
            global_signals.clip_deselected.emit()
        elif len(self.selected_ids) > 1:
            self.item_clicked.emit("multiple", "", {})
            global_signals.clip_deselected.emit()
        else:
            item_id = list(self.selected_ids)[0]
            item = next((i for i in self.items if i["id"] == item_id), None)
            if item:
                # BUG 3 FIX: When user clicked a sub-element (transition/effect badge),
                # emit the sub-type so the Properties Panel shows the correct page.
                emit_type = self.selected_item_type
                if emit_type not in ["transition_in", "transition_out", "clip_effect"]:
                    emit_type = item["type"]
                self.item_clicked.emit(emit_type, item["id"], copy.deepcopy(item))
                global_signals.clip_selected.emit(emit_type, item["id"])
            else:
                self.item_clicked.emit("", "", {})
                global_signals.clip_deselected.emit()

    def update_item_property(self, item_id, prop_name, new_value, save_state=True):
        if prop_name == "apply_transition_to_all":
            track_id = new_value.get("track")
            trans_name = new_value.get("transition")
            trans_dur = int(app_config.get_setting("default_transition_duration", 1.0) * 30)
            for item in self.items:
                if item["track"] == track_id and item["type"] in ["video", "image"]:
                    item["transition_in"] = trans_name
                    item["transition_in_duration"] = trans_dur
                    item["transition_out"] = trans_name
                    item["transition_out_duration"] = trans_dur
            self.update()
            if save_state:
                self.save_state()
            return
            
        for item in self.items:
            if item["id"] == item_id:
                item[prop_name] = new_value
                self.update()
                if save_state:
                    self.save_state()
                break
        
        # Force the preview player to re-render with the updated property
        global_signals.clip_transform_changed.emit(item_id, prop_name, new_value)

    # --- DRAG AND DROP ---
    def _get_track_group(self, track_id):
        if not track_id: return None
        for t in self.track_defs:
            if t["id"] == track_id: return t["group"]
        return None

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("application/x-have-item"):
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        pos = event.position().toPoint()
        z = self.zoom_factor
        logical_x = pos.x() / z
        
        if not event.mimeData().hasFormat("application/x-have-item"):
            event.ignore()
            return
            
        data = json.loads(event.mimeData().data("application/x-have-item").data().decode('utf-8'))
        drop_type = data.get("type")
        subtype = data.get("subtype")
        
        self._drop_target_rect = None
        self._drop_target_type = None
        self._drop_target_item = None
        
        hovered_clip = None
        clip_rect = None
        target_track = self._get_track_at_y(pos.y())
        target_track_group = self._get_track_group(target_track)

        for item in reversed(self.items):
            if self.is_track_hidden(item["track"]): continue
            ty, th = self.get_track_y(item["track"])
            if ty <= pos.y() <= ty + th:
                ix = item["x"] * z
                iw = item["w"] * z
                if ix <= pos.x() <= ix + iw:
                    hovered_clip = item
                    clip_rect = QRect(int(ix), ty, int(iw), th)
                    break

        if drop_type == "transition":
            if hovered_clip and hovered_clip["type"] in ["video", "image"]:
                ix = hovered_clip["x"] * z
                iw = hovered_clip["w"] * z
                dist_left = abs(pos.x() - ix)
                dist_right = abs(pos.x() - (ix + iw))
                
                if dist_left < 20:
                    adj = next((i for i in self.items if i["track"] == hovered_clip["track"] and abs((i["x"] + i["w"]) - hovered_clip["x"]) < 5), None)
                    if adj:
                        self._drop_target_rect = QRect(int(ix) - 10, self.get_track_y(hovered_clip["track"])[0], 20, self.get_track_y(hovered_clip["track"])[1])
                        self._drop_target_type = "transition"
                        self._drop_target_item = hovered_clip["id"]
                        self._drop_target_edge = "left"
                        event.acceptProposedAction()
                        self.update()
                        return
                elif dist_right < 20:
                    adj = next((i for i in self.items if i["track"] == hovered_clip["track"] and abs(i["x"] - (hovered_clip["x"] + hovered_clip["w"])) < 5), None)
                    if adj:
                        self._drop_target_rect = QRect(int(ix + iw) - 10, self.get_track_y(hovered_clip["track"])[0], 20, self.get_track_y(hovered_clip["track"])[1])
                        self._drop_target_type = "transition"
                        self._drop_target_item = hovered_clip["id"]
                        self._drop_target_edge = "right"
                        event.acceptProposedAction()
                        self.update()
                        return
            event.ignore()
            self.update()
            return
            
        elif drop_type == "effect":
            if hovered_clip and hovered_clip["type"] in ["video", "image"]:
                self._drop_target_rect = clip_rect
                self._drop_target_type = "clip"
                self._drop_target_item = hovered_clip["id"]
                event.acceptProposedAction()
            elif target_track_group == "effect":
                ty, th = self.get_track_y(target_track)
                w = 300
                
                # Check if we are near the edge to insert between tracks
                if pos.y() < ty + 10:
                    self._drop_target_rect = QRect(0, ty - 2, 9999, 4)
                    self._drop_target_type = "track_insert"
                    self._drop_target_insert_index = next((i for i, t in enumerate(self.track_defs) if t["id"] == target_track), 0)
                elif pos.y() > ty + th - 10:
                    self._drop_target_rect = QRect(0, ty + th - 2, 9999, 4)
                    self._drop_target_type = "track_insert"
                    self._drop_target_insert_index = next((i for i, t in enumerate(self.track_defs) if t["id"] == target_track), 0) + 1
                else:
                    self._drop_target_rect = QRect(int(logical_x * z), ty, w, th)
                    self._drop_target_type = "track"
                    
                event.acceptProposedAction()
            elif not target_track_group:
                ty = 32 + sum(t["height"] for t in self.track_defs)
                th = 48
                w = 300
                # If hovering below all tracks, we can create one at the very bottom
                self._drop_target_rect = QRect(int(logical_x * z), ty, w, th)
                self._drop_target_type = "track_new"
                event.acceptProposedAction()
            else:
                event.ignore()
            self.update()
            return
            
        else:
            expected_group = "video" if subtype in ["video", "image"] else ("audio" if subtype == "audio" else "caption")
            
            if target_track_group == expected_group:
                ty, th = self.get_track_y(target_track)
                w = 150 if drop_type == "caption" else 300
                
                # Interleaved track insertion logic
                if pos.y() < ty + 10:
                    self._drop_target_rect = QRect(0, ty - 2, 9999, 4)
                    self._drop_target_type = "track_insert"
                    self._drop_target_insert_index = next((i for i, t in enumerate(self.track_defs) if t["id"] == target_track), 0)
                elif pos.y() > ty + th - 10:
                    self._drop_target_rect = QRect(0, ty + th - 2, 9999, 4)
                    self._drop_target_type = "track_insert"
                    self._drop_target_insert_index = next((i for i, t in enumerate(self.track_defs) if t["id"] == target_track), 0) + 1
                else:
                    self._drop_target_rect = QRect(int(logical_x * z), ty, w, th)
                    self._drop_target_type = "track"
                event.acceptProposedAction()
            elif not target_track_group:
                ty = 32 + sum(t["height"] for t in self.track_defs)
                th = 48 if expected_group == "caption" else 80 if expected_group == "video" else 64
                w = 150 if drop_type == "caption" else 300
                self._drop_target_rect = QRect(int(logical_x * z), ty, w, th)
                self._drop_target_type = "track_new"
                event.acceptProposedAction()
            else:
                # If hovering over a different group (e.g Effect over Video), allow inserting between!
                ty, th = self.get_track_y(target_track) if target_track else (0, 0)
                if target_track:
                    if pos.y() < ty + (th / 2):
                        self._drop_target_rect = QRect(0, ty - 2, 9999, 4)
                        self._drop_target_insert_index = next((i for i, t in enumerate(self.track_defs) if t["id"] == target_track), 0)
                    else:
                        self._drop_target_rect = QRect(0, ty + th - 2, 9999, 4)
                        self._drop_target_insert_index = next((i for i, t in enumerate(self.track_defs) if t["id"] == target_track), 0) + 1
                    self._drop_target_type = "track_insert"
                    event.acceptProposedAction()
                else:
                    event.ignore()
            
            self.update()

    def dragLeaveEvent(self, event):
        self._drop_target_rect = None
        self._drop_target_type = None
        self._drop_target_edge = None
        self.update()

    def dropEvent(self, event):
        if not self._drop_target_type:
            event.ignore()
            return
            
        data_raw = json.loads(event.mimeData().data("application/x-have-item").data().decode('utf-8'))
        pos = event.position().toPoint()
        z = self.zoom_factor
        logical_x = pos.x() / z
        
        batch = data_raw.pop("batch") if "batch" in data_raw else [data_raw]
        base_x = logical_x
        
        for data in batch:
            drop_type = data.get("type")
            title = data.get("title")
            subtype = data.get("subtype")
            file_path = data.get("file_path", "") 
            
            if drop_type == "transition" and self._drop_target_type == "transition":
                item = next((i for i in self.items if i["id"] == self._drop_target_item), None)
                if item:
                    trans_dur_frames = int(app_config.get_setting("default_transition_duration", 1.0) * 30)
    
                    if getattr(self, "_drop_target_edge", "left") == "left":
                        item["transition_in"] = title
                        item["transition_in_duration"] = trans_dur_frames
                    else:
                        item["transition_out"] = title
                        item["transition_out_duration"] = trans_dur_frames
                    self.save_state()
                    self._emit_selection_state()
                    
            elif drop_type == "effect" and self._drop_target_type == "clip":
                item = next((i for i in self.items if i["id"] == self._drop_target_item), None)
                if item:
                    # applied_effects is historically a string OR a list. Ensure it's a list.
                    current_effects = item.get("applied_effects", [])
                    if isinstance(current_effects, str):
                        current_effects = [current_effects]
                    elif not isinstance(current_effects, list):
                        current_effects = []
                        
                    if title not in current_effects:
                        current_effects.append(title)
                        
                    item["applied_effects"] = current_effects
                    item["primary_effect"] = title
                    
                    # Ensure preset defaults (like effect_amount) are injected!
                    preset_props = data.get("preset_properties", {})
                    if preset_props:
                        from core.preset_loader import get_default_properties
                        defaults = get_default_properties({"properties": preset_props})
                        for k, v in defaults.items():
                            item[k] = v
                    
                    self.save_state()
                    self._emit_selection_state()
                    
            elif drop_type in ["media", "caption", "effect"] and self._drop_target_type in ["track", "track_new", "track_insert"]:
                expected_group = "video" if subtype in ["video", "image"] else ("audio" if subtype == "audio" else ("caption" if drop_type == "caption" else "effect"))
                
                # Define the shared batch target track outside so multiple items map to the SAME new track
                target_track = getattr(self, '_batch_target_track', None)
                if not target_track:
                    if self._drop_target_type == "track_insert":
                        target_track = f"{expected_group}_{random.randint(10000, 99999)}"
                        idx = getattr(self, "_drop_target_insert_index", len(self.track_defs))
                        self.track_defs.insert(idx, {"id": target_track, "group": expected_group, "label": "New", "icon": "", "height": 48})
                    elif self._drop_target_type == "track":
                        target_track = self._get_track_at_y(pos.y())
                    
                    if not target_track or self._get_track_group(target_track) != expected_group:
                        target_track = None
                        for t in self.track_defs:
                            if t["group"] == expected_group:
                                target_track = t["id"]
                                break
                        if not target_track: target_track = f"{expected_group}_1"
                    
                    self._batch_target_track = target_track

                display_text = os.path.basename(file_path) if file_path else (title if title else "New Item")
    
                item_w = 1000
                max_w = float('inf')
                
                if data.get("duration"):
                    item_w = int(float(data.get("duration")) * 100)
                    if subtype in ["video", "audio"]: max_w = item_w
                elif drop_type == "caption":
                    item_w = 400
                elif drop_type == "effect":
                    item_w = 1500
                elif subtype == "image":
                    item_w = int(app_config.get_setting("default_image_duration", 5.0) * 100)
                elif subtype in ["video", "audio"] and file_path:
                    duration_sec = 0
                    # 1. Try native wave module for flawless .wav parsing
                    if file_path.lower().endswith('.wav'):
                        try:
                            import wave
                            with wave.open(file_path, 'rb') as w_file:
                                duration_sec = w_file.getnframes() / float(w_file.getframerate())
                        except Exception:
                            pass
                    
                    # 2. Try OpenCV FFmpeg backend for .mp3, .m4a, and .mp4 videos
                    if duration_sec <= 0 and CV2_AVAILABLE:
                        try:
                            cap = cv2.VideoCapture(file_path)
                            fps = cap.get(cv2.CAP_PROP_FPS)
                            frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
                            if fps > 0:
                                duration_sec = frames / fps
                            cap.release()
                        except Exception:
                            pass
                            
                    if duration_sec > 0:
                        item_w = int(duration_sec * 100)
                        max_w = item_w
    
                new_item = {
                    "id": f"{drop_type}_{random.randint(10000, 99999)}",
                    "track": target_track,
                    "type": subtype if drop_type == "media" else drop_type,
                    "text": "New Caption" if drop_type == "caption" else display_text,
                    "file_path": file_path, 
                    "x": base_x,
                    "w": item_w,
                    "max_w": max_w,
                    "source_in": 0
                }
                
                if drop_type == "effect":
                    new_item["primary_effect"] = title
                    new_item["applied_effects"] = [title]
                
                # Merge preset properties from JSON-based presets (effects, captions, transitions)
                preset_props = data.get("preset_properties", {})
                if preset_props:
                    from core.preset_loader import get_default_properties
                    defaults = get_default_properties({"properties": preset_props})
                    for k, v in defaults.items():
                        new_item[k] = v
                    # Store the preset name for reference
                    new_item["preset_name"] = title
                
                if target_track != "video_1" or not self.v1_gravity_enabled:
                    track_items = [i for i in self.items if i["track"] == target_track]
                    while True:
                        overlap = False
                        for i in track_items:
                            if new_item["x"] < i["x"] + i["w"] and new_item["x"] + new_item["w"] > i["x"]:
                                overlap = True
                                new_item["x"] = i["x"] + i["w"] 
                        if not overlap:
                            break
    
                self.items.append(new_item)
                if new_item["type"] in ["audio", "video"] and new_item["file_path"]:
                    media_manager.request_waveform(new_item["file_path"])
                    
                # Increment base_x for the next item in the batch
                base_x += item_w

        self._cleanup_empty_tracks()
        self._apply_magnetic_v1()
        self.update_max_width()
        self.save_state()
            
        self._drop_target_rect = None
        self._drop_target_type = None
        self._drop_target_edge = None
        self._batch_target_track = None
        self.update()
        event.acceptProposedAction()

    # --- END DRAG AND DROP ---

    def set_v_scroll(self, val):
        self.v_scroll_y = val
        self.update()

    def wheelEvent(self, event):
        modifiers = event.modifiers()
        delta = event.angleDelta().y()
        
        if modifiers == Qt.ControlModifier:
            self.zoom_requested.emit(delta)
        elif modifiers == Qt.ShiftModifier:
            self.v_scroll_requested.emit(-delta)
        else:
            self.scroll_requested.emit(-delta)
            
        event.accept()

    def save_state(self):
        """Pushes current visual layout to undo history, and signals the UI that a change happened."""
        self.history = self.history[:self.history_idx + 1]
        self.history.append(copy.deepcopy(self.items))
        self.history_idx += 1
        
        # CRITICAL FIX: Force the UI to push its layout to the Engine's Backend Brain immediately!
        # This guarantees the RenderEngine sees dropped images and the AudioEngine tracks dragged clips.
        self.sync_to_project()
        
        self.state_changed.emit()
        
    def add_item_directly(self, data_raw):
        """Handles the + button clicking from Workspace to shoot items into correct tracks immediately."""
        batch = data_raw.pop("batch") if "batch" in data_raw else [data_raw]
        base_x = self.logical_playhead
        
        for data in batch:
            drop_type = data.get("type")
            subtype = data.get("subtype")
            title = data.get("title")
            file_path = data.get("file_path", "")
    
            if not drop_type:
                continue
    
            expected_group = "video" if subtype in ["video", "image"] else ("audio" if subtype == "audio" else ("caption" if drop_type == "caption" else "effect"))
    
            target_track = None
            for t in self.track_defs:
                if t["group"] == expected_group:
                    target_track = t["id"]
                    break
            if not target_track:
                target_track = f"{expected_group}_1"
    
            display_text = os.path.basename(file_path) if file_path else (title if title else "New Item")
            
            item_w = 1000
            max_w = float('inf')
            
            if data.get("duration"):
                item_w = int(float(data.get("duration")) * 100)
                if subtype in ["video", "audio"]: max_w = item_w
            elif drop_type == "caption":
                item_w = 400
            elif drop_type == "effect":
                item_w = 1500
            elif subtype == "image":
                item_w = int(app_config.get_setting("default_image_duration", 5.0) * 100)
            elif subtype in ["video", "audio"] and file_path:
                duration_sec = 0
                if file_path.lower().endswith('.wav'):
                    try:
                        import wave
                        with wave.open(file_path, 'rb') as w_file:
                            duration_sec = w_file.getnframes() / float(w_file.getframerate())
                    except Exception:
                        pass
                
                if duration_sec <= 0 and CV2_AVAILABLE:
                    try:
                        cap = cv2.VideoCapture(file_path)
                        fps = cap.get(cv2.CAP_PROP_FPS)
                        frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
                        if fps > 0:
                            duration_sec = frames / fps
                        cap.release()
                    except Exception:
                        pass
                        
                if duration_sec > 0:
                    item_w = int(duration_sec * 100)
                    max_w = item_w

            new_item = {
                "id": f"{drop_type}_{random.randint(10000, 99999)}",
                "track": target_track,
                "type": subtype if drop_type == "media" else drop_type,
                "text": "New Caption" if drop_type == "caption" else display_text,
                "file_path": file_path,
                "x": base_x,
                "w": item_w,
                "max_w": max_w,
                "source_in": 0
            }

            if target_track != "video_1" or not self.v1_gravity_enabled:
                track_items = [i for i in self.items if i["track"] == target_track]
                while True:
                    overlap = False
                    for i in track_items:
                        if new_item["x"] < i["x"] + i["w"] and new_item["x"] + new_item["w"] > i["x"]:
                            overlap = True
                            new_item["x"] = i["x"] + i["w"]
                    if not overlap:
                        break
        
            self.items.append(new_item)
            if new_item["type"] in ["audio", "video"] and new_item["file_path"]:
                media_manager.request_waveform(new_item["file_path"])
                
            base_x += item_w
            
        # Run cleanup outside the batch loop
        self._cleanup_empty_tracks()
        self._apply_magnetic_v1()
        self.update_max_width()
        self.save_state()
        self.sync_to_project()
        self.update()

    def undo(self):
        if self.history_idx > 0:
            self.history_idx -= 1
            self.items = copy.deepcopy(self.history[self.history_idx])
            current_ids = {i["id"] for i in self.items}
            self.selected_ids = {sid for sid in self.selected_ids if sid in current_ids}
            self._emit_selection_state()
            self._apply_magnetic_v1()
            self.update_max_width()
            self.state_changed.emit()
            self.update()

    def redo(self):
        if self.history_idx < len(self.history) - 1:
            self.history_idx += 1
            self.items = copy.deepcopy(self.history[self.history_idx])
            current_ids = {i["id"] for i in self.items}
            self.selected_ids = {sid for sid in self.selected_ids if sid in current_ids}
            self._emit_selection_state()
            self._apply_magnetic_v1()
            self.update_max_width()
            self.state_changed.emit()
            self.update()
            
    def freeze_frame_at_playhead(self):
        """Extracts the video frame exactly at the playhead, splits the track, and inserts a 3s image clip."""
        if not CV2_AVAILABLE:
            print("Cannot Freeze Frame: OpenCV is not installed.")
            return

        changed = False
        for s_id in list(self.selected_ids):
            item = next((i for i in self.items if i["id"] == s_id), None)
            if item and item["type"] == "video" and not self.is_track_locked(item["track"]):
                if item["x"] < self.logical_playhead < item["x"] + item["w"]:
                    
                    local_ms = (self.logical_playhead - item["x"] + item.get("source_in", 0)) * 10
                    file_path = item.get("file_path")
                    
                    if not file_path or not os.path.exists(file_path):
                        continue
                        
                    cap = cv2.VideoCapture(file_path)
                    cap.set(cv2.CAP_PROP_POS_MSEC, local_ms)
                    ret, frame = cap.read()
                    cap.release()
                    
                    if ret:
                        cache_dir = self.get_project_cache_dir()
                        os.makedirs(cache_dir, exist_ok=True)
                        frame_path = os.path.join(cache_dir, f"freeze_{uuid.uuid4().hex[:8]}.jpg")
                        cv2.imwrite(frame_path, frame)
                        
                        cut_x = self.logical_playhead
                        insert_duration = 300 # 300 units = 3 seconds (10ms per unit)
                        
                        for other in self.items:
                            if other["track"] == item["track"] and other["x"] >= cut_x and other["id"] != item["id"]:
                                other["x"] += insert_duration
                        
                        new_item_right = copy.deepcopy(item)
                        new_item_right["id"] = f"{item['id']}_right_{random.randint(1000, 9999)}"
                        
                        old_w = item["w"]
                        diff = cut_x - item["x"]
                        
                        item["w"] = diff
                        
                        new_item_right["x"] = cut_x + insert_duration
                        new_item_right["w"] = old_w - diff
                        new_item_right["source_in"] = item.get("source_in", 0) + diff
                        
                        if item.get("max_w", float('inf')) != float('inf'):
                            new_item_right["max_w"] = item["max_w"]
                        
                        freeze_item = {
                            "id": f"image_{random.randint(10000, 99999)}",
                            "track": item["track"],
                            "type": "image",
                            "text": "Freeze Frame",
                            "file_path": frame_path,
                            "x": cut_x,
                            "w": insert_duration,
                            "max_w": float('inf'),
                            "source_in": 0
                        }
                        
                        self.items.append(freeze_item)
                        self.items.append(new_item_right)
                        changed = True
                        
        if changed:
            self.save_state()
            self._apply_magnetic_v1()
            self.update_max_width()
            self.update()

    def split_at_playhead(self):
        changed = False
        for s_id in list(self.selected_ids):
            item = next((i for i in self.items if i["id"] == s_id), None)
            if item and item["type"] != "word" and not self.is_track_locked(item["track"]):
                if item["x"] + 2 < self.logical_playhead < item["x"] + item["w"] - 2:
                    new_item = copy.deepcopy(item)
                    new_item["id"] = f"{item['id']}_split_{random.randint(1000, 9999)}"
                    
                    old_w = item["w"]
                    diff = self.logical_playhead - item["x"]
                    item["w"] = diff
                    
                    new_item["x"] = self.logical_playhead
                    new_item["w"] = old_w - diff
                    new_item["source_in"] = item.get("source_in", 0) + diff
                    
                    if item.get("max_w", float('inf')) != float('inf'):
                        new_item["max_w"] = item["max_w"]
                        
                    self.items.append(new_item)
                    changed = True
        if changed:
            self.save_state()
            self._apply_magnetic_v1()
            self.update_max_width()
            self.update()

    def trim_left(self):
        changed = False
        for s_id in list(self.selected_ids):
            item = next((i for i in self.items if i["id"] == s_id), None)
            if item and item["type"] != "word" and not self.is_track_locked(item["track"]):
                if item["x"] < self.logical_playhead < item["x"] + item["w"]:
                    diff = self.logical_playhead - item["x"]
                    item["x"] = self.logical_playhead
                    item["w"] -= diff
                    item["source_in"] = item.get("source_in", 0) + diff
                    changed = True
        if changed:
            self.save_state()
            self._apply_magnetic_v1()
            self.update_max_width()
            self.update()

    def trim_right(self):
        changed = False
        for s_id in list(self.selected_ids):
            item = next((i for i in self.items if i["id"] == s_id), None)
            if item and item["type"] != "word" and not self.is_track_locked(item["track"]):
                if item["x"] < self.logical_playhead < item["x"] + item["w"]:
                    item["w"] = self.logical_playhead - item["x"]
                    changed = True
        if changed:
            self.save_state()
            self._apply_magnetic_v1()
            self.update_max_width()
            self.update()

    def toggle_item_property(self, prop_name):
        changed = False
        for s_id in list(self.selected_ids):
            item = next((i for i in self.items if i["id"] == s_id), None)
            if item and item["type"] in ["video", "image"]:
                item[prop_name] = not item.get(prop_name, False)
                changed = True
        if changed:
            self.save_state()
            self._emit_selection_state()
            self.update()

    def get_v1_duration(self):
        v1_items = [i for i in self.items if i["track"] == "video_1"]
        if not v1_items:
            return 0
        return max([i["x"] + i["w"] for i in v1_items])

    def toggle_track_state(self, track_id, state_type):
        if track_id in self.track_states:
            self.track_states[track_id][state_type] = not self.track_states[track_id][state_type]
            if state_type == "hidden" and self.track_states[track_id]["hidden"]:
                to_deselect = [i["id"] for i in self.items if i["track"] == track_id]
                self.selected_ids.difference_update(to_deselect)
                if not self.selected_ids:
                    self.selected_item_type = ""
                    self._emit_selection_state()
            self.update()

    def is_track_locked(self, track_id):
        return self.track_states.get(track_id, {}).get("locked", False)
        
    def is_track_hidden(self, track_id):
        return self.track_states.get(track_id, {}).get("hidden", False)

    def _apply_magnetic_v1(self):
        if self.is_track_locked("video_1"):
            v1_items = [i for i in self.items if i["track"] == "video_1"]
            duration = max([i["x"] + i["w"] for i in v1_items], default=0)
            self.v1_duration_changed.emit(float(duration))
            return

        v1_items = sorted([i for i in self.items if i["track"] == "video_1"], key=lambda k: k["x"])
        
        if self.v1_gravity_enabled:
            curr_x = 0
            for item in v1_items:
                item["x"] = curr_x
                curr_x += item["w"]
                
        duration = 0
        if v1_items:
            duration = max([i["x"] + i["w"] for i in v1_items])
        self.v1_duration_changed.emit(float(duration))

    def set_playhead(self, logical_x):
        self.logical_playhead = float(logical_x)
        self.playhead_changed.emit(self.logical_playhead)
        self.update()

    def _would_v1_be_empty(self, excluding_ids=None):
        """Check if V1 would become empty if the given clip IDs were removed/moved."""
        excluding = excluding_ids or set()
        return not any(i for i in self.items if i["track"] == "video_1" and i["id"] not in excluding)

    def delete_selected_item(self):
        if not self.selected_ids:
            return

        changed = False
        to_delete = set()
        
        for i in self.items:
            if i["id"] in self.selected_ids or i.get("parent_id") in self.selected_ids:
                if not self.is_track_locked(i["track"]):
                    # Intelligently pop sub-properties if the user had them selected
                    if self.selected_item_type == "transition_in":
                        i.pop("transition_in", None)
                        i.pop("transition", None) # Fallback legacy key
                        i.pop("transition_in_duration", None)
                        changed = True
                    elif self.selected_item_type == "transition_out":
                        i.pop("transition_out", None)
                        i.pop("transition_out_duration", None)
                        changed = True
                    elif self.selected_item_type == "clip_effect":
                        i.pop("applied_effects", None)
                        changed = True
                    else:
                        to_delete.add(i["id"])

        if to_delete:
            # BUG 2 FIX: Never let V1 become empty — block deletion if it would empty V1
            v1_remaining = [i for i in self.items if i["track"] == "video_1" and i["id"] not in to_delete]
            if not v1_remaining:
                # Check if ANY items are V1 items being deleted
                v1_deleting = [i for i in self.items if i["track"] == "video_1" and i["id"] in to_delete]
                if v1_deleting:
                    print("V1 Protection: Cannot delete — at least one clip must remain on V1.")
                    return
            
            self.items = [i for i in self.items if i["id"] not in to_delete]
            self.selected_ids.difference_update(to_delete)
            if not self.selected_ids:
                self.selected_item_type = ""
            changed = True
            
        if changed:
            self.save_state()
            self._cleanup_empty_tracks()
            self._apply_magnetic_v1()
            self.update_max_width()
            self._emit_selection_state()
            self.update()

    def _get_snap_target(self, left_x, right_x, current_item_id):
        targets = [0, self.logical_playhead]
        for item in self.items:
            if item["id"] not in self.selected_ids and item["type"] != "word" and not self.is_track_hidden(item["track"]):
                targets.extend([item["x"], item["x"] + item["w"]])
                
        threshold = 15 / self.zoom_factor 
        best_diff = float('inf')
        snap_x = None
        shift_x = 0
        
        for t in targets:
            if abs(left_x - t) < threshold and abs(left_x - t) < abs(best_diff):
                best_diff = left_x - t
                snap_x = t
                shift_x = -best_diff
            if abs(right_x - t) < threshold and abs(right_x - t) < abs(best_diff):
                best_diff = right_x - t
                snap_x = t
                shift_x = -best_diff
                
        return snap_x, shift_x

    def update_max_width(self):
        max_end = 0
        for item in self.items:
            max_end = max(max_end, item["x"] + item["w"])
        
        buffer = max(1000, int(max_end * 0.2)) 
        self.max_logical_width = max_end + buffer
        self.setMinimumWidth(max(int(self.max_logical_width * self.zoom_factor), 100))
        self.update()

    def move_track_up(self, track_id):
        idx = next((i for i, t in enumerate(self.track_defs) if t["id"] == track_id), -1)
        if idx > 0 and track_id not in ["video_1", "audio_1", "word_1"]:
            prev_t = self.track_defs[idx-1]["id"]
            if prev_t not in ["video_1", "audio_1", "word_1"]:
                self.track_defs[idx], self.track_defs[idx-1] = self.track_defs[idx-1], self.track_defs[idx]
                self._cleanup_empty_tracks()
                self.update()

    def move_track_down(self, track_id):
        idx = next((i for i, t in enumerate(self.track_defs) if t["id"] == track_id), -1)
        if idx != -1 and idx < len(self.track_defs) - 1 and track_id not in ["video_1", "audio_1", "word_1"]:
            next_t = self.track_defs[idx+1]["id"]
            if next_t not in ["video_1", "audio_1", "word_1"]:
                self.track_defs[idx], self.track_defs[idx+1] = self.track_defs[idx+1], self.track_defs[idx]
                self._cleanup_empty_tracks()
                self.update()

    def _create_def(self, group, num, tid):
        label_prefix = group.capitalize()
        if group == "video": label_prefix = "V"
        elif group == "effect": label_prefix = "Fx"
        elif group == "audio": label_prefix = "A"
        elif group == "caption": label_prefix = "C"
        
        label = f"{label_prefix}{num}"
        if num == 1:
            if group == "video": label = "V1 - Main"
            elif group == "audio": label = "A1 - Audio"
            elif group == "caption": label = "C1"
            elif group == "effect": label = "Fx1"
            
        icon = "mdi6.auto-fix"
        if group == "caption": icon = "mdi6.comment-text-outline"
        elif group == "video": icon = "mdi6.movie-open-outline"
        elif group == "audio": icon = "mdi6.volume-high"
        elif group == "word": icon = "mdi6.format-text"
        
        height = 80 if group == "video" else (64 if group == "audio" else 48)
        return {"id": tid, "group": group, "label": label, "icon": icon, "height": height}

    def _cleanup_empty_tracks(self):
        active_track_ids = set()
        for item in self.items:
            active_track_ids.add(item["track"])
            
        for base in ["video_1", "audio_1", "caption_1", "effect_1", "word_1"]:
            active_track_ids.add(base)
            
        top_zone = []
        audio_zone = []
        
        for t in self.track_defs:
            tid = t["id"]
            if tid in active_track_ids:
                if tid in ["video_1", "audio_1", "word_1"]: continue
                group = tid.split("_")[0]
                if group in ["video", "caption", "effect"]:
                    top_zone.append(tid)
                elif group == "audio":
                    audio_zone.append(tid)
                    
        for tid in active_track_ids:
            if tid not in top_zone and tid not in audio_zone and tid not in ["video_1", "audio_1", "word_1"]:
                group = tid.split("_")[0]
                if group in ["video", "caption", "effect"]:
                    top_zone.append(tid)
                elif group == "audio":
                    audio_zone.append(tid)

        max_group_counts = {"video": 1, "audio": 1, "caption": 0, "effect": 0, "word": 0}
        
        # Determine the maximum used numerical ID for each track group to assign new tracks properly
        all_zones = top_zone + audio_zone
        for old_id in all_zones:
            group = old_id.split("_")[0]
            try:
                num = int(old_id.split("_")[1])
            except:
                num = 0
            if num < 10000:
                max_group_counts[group] = max(max_group_counts.get(group, 0), num)

        new_defs = []
        track_mapping = {}

        # 1. Map ID assignments from bottom to top so that newly generated tracks get assigned V3, V4 incrementally
        for old_id in reversed(top_zone):
            group = old_id.split("_")[0]
            try:
                num = int(old_id.split("_")[1])
            except:
                num = 0

            if num >= 10000:
                # Brand new track!
                max_group_counts[group] += 1
                new_num = max_group_counts[group]
                new_id = f"{group}_{new_num}"
                track_mapping[old_id] = new_id
            else:
                # Existing track! Keep its identifier permanently.
                track_mapping[old_id] = old_id

        # 2. Append actual visual defs in top-to-bottom UI display order
        for old_id in top_zone:
            new_id = track_mapping[old_id]
            group = new_id.split("_")[0]
            new_num = int(new_id.split("_")[1])
            new_defs.append(self._create_def(group, new_num, new_id))
            
        # Mid Separator
        track_mapping["video_1"] = "video_1"
        new_defs.append(self._create_def("video", 1, "video_1"))
        track_mapping["audio_1"] = "audio_1"
        new_defs.append(self._create_def("audio", 1, "audio_1"))
        
        # Audio Extra
        for old_id in audio_zone:
            group = "audio"
            try:
                num = int(old_id.split("_")[1])
            except:
                num = 0
                
            if num >= 10000:
                # Brand new track!
                max_group_counts["audio"] += 1
                new_num = max_group_counts["audio"]
                new_id = f"audio_{new_num}"
                track_mapping[old_id] = new_id
            else:
                track_mapping[old_id] = old_id
                new_num = num
                new_id = old_id
                
            new_defs.append(self._create_def("audio", new_num, new_id))
            
        # Word Base
        track_mapping["word_1"] = "word_1"
        new_defs.append(self._create_def("word", 1, "word_1"))

        for item in self.items:
            if item["track"] in track_mapping:
                item["track"] = track_mapping[item["track"]]
                
        new_states = {}
        for old_id, new_id in track_mapping.items():
            new_states[new_id] = self.track_states.get(old_id, {"locked": False, "hidden": False})
            
        for t in new_defs:
            if t["id"] not in new_states:
                new_states[t["id"]] = {"locked": False, "hidden": False}

        self.track_states = new_states
        self.track_defs = new_defs
        self._recalc_height()
        self.tracks_changed.emit()

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

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            z = self.zoom_factor
            physical_x = event.position().x()
            logical_x = physical_x / z
            y = event.position().y()
            
            # BUG 1 FIX: Support Ctrl+click multi-select alongside Shift+click
            shift_held = bool(event.modifiers() & Qt.ShiftModifier)
            ctrl_held = bool(event.modifiers() & Qt.ControlModifier)
            multi_select = shift_held or ctrl_held
            
            self._click_physical_pos = event.position().toPoint()
            self._click_logical_x = logical_x
            self._potential_action = None
            self._potential_item = None
            self._potential_edge = None
            self._drag_started = False

            if self.v_scroll_y <= y <= self.v_scroll_y + 32:
                self.selected_ids.clear()
                self.set_playhead(max(0, logical_x))
                self._potential_action = "drag"
                self._potential_item = "playhead"
                self._emit_selection_state()
                self.update()
                return
            
            if self.active_tool == "pointer" and not multi_select:
                pass 

            for item in reversed(self.items):
                if self.is_track_hidden(item["track"]):
                    continue
                    
                if item["type"] == "word" and "parent_id" in item:
                    parent = next((p for p in self.items if p["id"] == item["parent_id"]), None)
                    if parent:
                        word_center = item["x"] + item["w"] / 2
                        if not (parent["x"] <= word_center <= parent["x"] + parent["w"]):
                            continue

                ty, th = self.get_track_y(item["track"])
                if ty <= y <= ty + th:
                    ix = item["x"] * z
                    iw = item["w"] * z
                    
                    if ix - 15 <= physical_x <= ix + iw + 15:
                        is_locked = self.is_track_locked(item["track"])
                        
                        draw_y = item.get("visual_y", ty)
                        rect = QRect(int(item["x"] * z), int(draw_y) + 4, int(item["w"] * z), th - 8)
                        
                        sub_item_clicked = None
                        
                        # Priority selection - Because it renders on top, we intercept FX clicks first!
                        if item.get("applied_effects"):
                            fx_rect = QRect(rect.right() - 22, rect.top() + 4, 18, 16)
                            if fx_rect.contains(physical_x, y):
                                sub_item_clicked = "clip_effect"
                                
                        if not sub_item_clicked and item.get("transition_out"):
                            frames = item.get("transition_out_duration", 30)
                            t_w_physical = int((frames / 30.0) * 100 * z)
                            t_out_rect = QRect(rect.right() - int(t_w_physical/2), rect.top(), t_w_physical, rect.height())
                            if t_out_rect.contains(physical_x, y):
                                sub_item_clicked = "transition_out"
                                
                        if not sub_item_clicked and (item.get("transition_in") or item.get("transition")):
                            frames = item.get("transition_in_duration", 30)
                            t_w_physical = int((frames / 30.0) * 100 * z)
                            t_in_rect = QRect(rect.left() - int(t_w_physical/2), rect.top(), t_w_physical, rect.height())
                            if t_in_rect.contains(physical_x, y):
                                sub_item_clicked = "transition_in"

                        if sub_item_clicked:
                            self.selected_ids = {item["id"]}
                            self.selected_item_type = sub_item_clicked
                            self._emit_selection_state()
                            self.update()
                            return
                        
                        if ix <= physical_x <= ix + iw:
                            if self.active_tool == "blade":
                                if item["type"] != "word" and not is_locked:
                                    cut_x = logical_x
                                    if cut_x > item["x"] + 2 and cut_x < item["x"] + item["w"] - 2:
                                        new_item = copy.deepcopy(item)
                                        new_item["id"] = f"{item['id']}_cut_{random.randint(1000, 9999)}"
                                        
                                        old_w = item["w"]
                                        diff = cut_x - item["x"]
                                        item["w"] = diff
                                        new_item["x"] = cut_x
                                        new_item["w"] = old_w - diff
                                        new_item["source_in"] = item.get("source_in", 0) + diff
                                        
                                        if item.get("max_w", float('inf')) != float('inf'):
                                            new_item["max_w"] = item["max_w"]
                                            
                                        self.items.append(new_item)
                                        self.save_state()
                                        self._apply_magnetic_v1()
                                        self.update_max_width()
                                        self.update()
                                return

                            if multi_select:
                                if item["id"] in self.selected_ids:
                                    self.selected_ids.remove(item["id"])
                                else:
                                    self.selected_ids.add(item["id"])
                            else:
                                if item["id"] not in self.selected_ids:
                                    self.selected_ids = {item["id"]}

                            self.selected_item_type = item["type"]
                            self.drag_start_positions = {i["id"]: i["x"] for i in self.items}

                            if item["type"] == "word":
                                self.set_playhead(item["x"])
                                self._emit_selection_state()
                                return
                            
                            if is_locked:
                                self._potential_action = None
                            elif len(self.selected_ids) <= 1 and physical_x - ix <= 5:
                                self._potential_action = "resize"
                                self._potential_item = item["id"]
                                self._potential_edge = "left"
                            elif len(self.selected_ids) <= 1 and (ix + iw) - physical_x <= 5:
                                self._potential_action = "resize"
                                self._potential_item = item["id"]
                                self._potential_edge = "right"
                            else:
                                self._potential_action = "drag"
                                self._potential_item = item["id"]
                                
                            self._emit_selection_state()
                            self.update()
                            return

            if self.active_tool == "pointer":
                if multi_select:
                    self.marquee_start = event.position().toPoint()
                    self.marquee_current = self.marquee_start
                    self.marquee_initial_selection = set(self.selected_ids)
                else:
                    self.selected_ids.clear()
                    self.set_playhead(max(0, logical_x))
                    self._potential_action = "drag"
                    self._potential_item = "playhead"
                    self._emit_selection_state()

    def mouseMoveEvent(self, event):
        z = self.zoom_factor
        physical_x = event.position().x()
        logical_x = physical_x / z
        y = event.position().y()
        
        if self.marquee_start is not None:
            self.marquee_current = event.position().toPoint()
            sel_rect = QRect(self.marquee_start, self.marquee_current).normalized()
            new_selection = set(self.marquee_initial_selection)
            
            for item in self.items:
                if self.is_track_hidden(item["track"]):
                    continue
                ty, th = self.get_track_y(item["track"])
                item_rect = QRect(int(item["x"] * z), ty, int(item["w"] * z), th)
                if sel_rect.intersects(item_rect):
                    new_selection.add(item["id"])
                    
            self.selected_ids = new_selection
            self.selected_item_type = "multiple" if len(self.selected_ids) > 1 else (self.items[0]["type"] if self.selected_ids else "")
            self._emit_selection_state()
            self.update()
            return
        
        if event.buttons() == Qt.NoButton:
            if self.v_scroll_y <= y <= self.v_scroll_y + 32:
                self.setCursor(Qt.ArrowCursor)
                if self.hovered_id != "":
                    self.hovered_id = ""
                    self.update()
                if self.active_tool == "blade":
                    self.blade_line_x = None
                    self.update()
                return

            if self.active_tool == "blade":
                self.setCursor(Qt.CrossCursor)
                self.blade_line_x = None
                new_hovered = ""
                for item in reversed(self.items):
                    if self.is_track_hidden(item["track"]): continue
                    if item["type"] == "word" and "parent_id" in item:
                        parent = next((p for p in self.items if p["id"] == item["parent_id"]), None)
                        if parent:
                            word_center = item["x"] + item["w"] / 2
                            if not (parent["x"] <= word_center <= parent["x"] + parent["w"]):
                                continue
                                
                    ty, th = self.get_track_y(item["track"])
                    if ty <= y <= ty + th:
                        ix = item["x"] * z
                        iw = item["w"] * z
                        if ix <= physical_x <= ix + iw:
                            if item["type"] != "word" and not self.is_track_locked(item["track"]):
                                self.blade_line_x = logical_x
                            new_hovered = item["id"]
                            break
                            
                if self.hovered_id != new_hovered:
                    self.hovered_id = new_hovered
                self.update()
                return

            new_hovered = ""
            cursor_set = False
            for item in reversed(self.items):
                if self.is_track_hidden(item["track"]): continue
                
                if item["type"] == "word" and "parent_id" in item:
                    parent = next((p for p in self.items if p["id"] == item["parent_id"]), None)
                    if parent:
                        word_center = item["x"] + item["w"] / 2
                        if not (parent["x"] <= word_center <= parent["x"] + parent["w"]):
                            continue

                ty, th = self.get_track_y(item["track"])
                if ty <= y <= ty + th:
                    ix = item["x"] * z
                    iw = item["w"] * z
                    
                    if ix - 10 <= physical_x <= ix + iw + 10:
                        new_hovered = item["id"]
                        if self.is_track_locked(item["track"]):
                            self.setCursor(Qt.ArrowCursor if self.active_tool == "blade" else Qt.PointingHandCursor)
                            cursor_set = True
                        else:
                            if item["type"] != "word" and (ix <= physical_x <= ix + 5 or (ix + iw - 5) <= physical_x <= ix + iw):
                                self.setCursor(Qt.SizeHorCursor)
                                cursor_set = True
                            else:
                                self.setCursor(Qt.PointingHandCursor)
                                cursor_set = True
                        break
            
            if not cursor_set:
                self.setCursor(Qt.ArrowCursor)

            if self.hovered_id != new_hovered:
                self.hovered_id = new_hovered
                self.update()
                
        elif event.buttons() == Qt.LeftButton and self.active_tool == "pointer":
            if not self._drag_started and self._click_physical_pos:
                diff_x = abs(physical_x - self._click_physical_pos.x())
                diff_y = abs(y - self._click_physical_pos.y())
                
                if diff_x > 5 or diff_y > 5:
                    self._drag_started = True
                    
                    if self._potential_action == "drag":
                        self.dragging_item = self._potential_item
                        if self.dragging_item != "playhead":
                            item = next((i for i in self.items if i["id"] == self.dragging_item), None)
                            if item:
                                self.drag_offset_x = self._click_logical_x - item["x"]
                                self.drag_offset_y = self._click_physical_pos.y() - self.get_track_y(item["track"])[0]
                                self.original_track = item["track"]
                                self.original_x = item["x"]
                                item["visual_y"] = self.get_track_y(item["track"])[0]
                                
                    elif self._potential_action == "resize":
                        self.resizing_item = self._potential_item
                        self.resize_edge = self._potential_edge
            
            if self._drag_started:
                viewport_rect = self.visibleRegion().boundingRect()
                scroll_margin = 50
                if physical_x < viewport_rect.left() + scroll_margin:
                    self.scroll_dx = -15
                    self.auto_scroll_timer.start(16)
                elif physical_x > viewport_rect.right() - scroll_margin:
                    self.scroll_dx = 15
                    self.auto_scroll_timer.start(16)
                else:
                    self.auto_scroll_timer.stop()
                    
                self._process_mouse_move(logical_x)

    def _process_mouse_move(self, logical_x):
        logical_x = max(0, logical_x)
        self.snap_line_x = None 
        
        if self.dragging_item == "playhead":
            self.set_playhead(logical_x)
            return

        item = next((i for i in self.items if i["id"] == (self.dragging_item or self.resizing_item)), None)
        if not item: return

        if self.dragging_item:
            primary_item = next((i for i in self.items if i["id"] == self.dragging_item), None)
            if not primary_item: return
            
            old_x = self.drag_start_positions[primary_item["id"]]
            new_x = max(0, logical_x - self.drag_offset_x)
            
            if self.magnet_enabled and (primary_item["track"] != "video_1" or not self.v1_gravity_enabled):
                snap_x, shift_x = self._get_snap_target(new_x, new_x + primary_item["w"], primary_item["id"])
                if snap_x is not None:
                    new_x += shift_x
                    self.snap_line_x = snap_x
            
            actual_dx = new_x - old_x
            
            for s_id in self.selected_ids:
                it = next((i for i in self.items if i["id"] == s_id), None)
                if it:
                    if self.is_track_locked(it["track"]): 
                        continue
                    if it["type"] == "word" and it.get("parent_id") in self.selected_ids:
                        continue
                    it["x"] = max(0, self.drag_start_positions[s_id] + actual_dx)
                    
                    if it["type"] == "audio":
                        for w in self.items:
                            if w.get("parent_id") == it["id"] and w["id"] not in self.selected_ids:
                                w["x"] = max(0, self.drag_start_positions.get(w["id"], w["x"] - actual_dx) + actual_dx)

            if len(self.selected_ids) == 1:
                local_pos = self.mapFromGlobal(QCursor.pos())
                my_y = local_pos.y()
                primary_item["visual_y"] = my_y - self.drag_offset_y
                
                hovered_track = None
                current_y = 32
                for t in self.track_defs:
                    if current_y <= my_y <= current_y + t["height"]:
                        hovered_track = t
                        break
                    current_y += t["height"]
                
                if hovered_track and not self.is_track_locked(hovered_track["id"]):
                    if primary_item["type"] in ["video", "image"] and hovered_track["group"] == "video":
                        primary_item["track"] = hovered_track["id"]
                    elif primary_item["type"] == "audio" and hovered_track["group"] == "audio":
                        primary_item["track"] = hovered_track["id"]
                    elif primary_item["type"] == "effect" and hovered_track["group"] == "effect":
                        primary_item["track"] = hovered_track["id"]
                    elif primary_item["type"] == "caption" and hovered_track["group"] == "caption":
                        primary_item["track"] = hovered_track["id"]
                    
            self.update_max_width()
            
        elif self.resizing_item:
            old_w = item["w"]
            old_x = item["x"]
            if self.resize_edge == "right":
                new_w = logical_x - item["x"]
                if self.magnet_enabled:
                    snap_x, shift_x = self._get_snap_target(-1000, item["x"] + new_w, item["id"])
                    if snap_x is not None:
                        new_w += shift_x
                        self.snap_line_x = snap_x
                        
                item["w"] = max(10, min(new_w, item.get("max_w", float('inf'))))
            elif self.resize_edge == "left":
                max_left_x = item["x"] + item["w"] - 10
                new_x = min(logical_x, max_left_x)
                if self.magnet_enabled:
                    snap_x, shift_x = self._get_snap_target(new_x, -1000, item["id"])
                    if snap_x is not None:
                        new_x += shift_x
                        self.snap_line_x = snap_x
                
                if item.get("max_w", float('inf')) != float('inf'):
                    min_x = (item["x"] + item["w"]) - item["max_w"]
                    new_x = max(new_x, min_x)
                right_edge = item["x"] + item["w"]
                diff = new_x - item["x"]
                item["x"] = new_x
                item["w"] = right_edge - new_x
                item["source_in"] = max(0, item.get("source_in", 0) + diff)
                
            if item["track"] != "video_1" or not self.v1_gravity_enabled:
                for other in self.items:
                    if other != item and other["track"] == item["track"]:
                        if item["x"] < other["x"] + other["w"] and item["x"] + item["w"] > other["x"]:
                            item["x"] = old_x
                            item["w"] = old_w
                            # Reset source_in rollback since collision denied resize
                            if self.resize_edge == "left":
                                item["source_in"] = max(0, item.get("source_in", 0) - diff)
                            break
                        
            self.update_max_width()
                
        self.update()

    def _do_auto_scroll(self):
        self.scroll_requested.emit(self.scroll_dx)
        local_pos = self.mapFromGlobal(QCursor.pos())
        logical_x = local_pos.x() / self.zoom_factor
        self._process_mouse_move(logical_x)

    def mouseReleaseEvent(self, event):
        if self.marquee_start is not None:
            self.marquee_start = None
            self.marquee_current = None
            self.update()
            return

        if event.button() == Qt.LeftButton:
            self.auto_scroll_timer.stop()
            self.snap_line_x = None
            
            changed_during_drag = False
            
            if self._drag_started and self.dragging_item:
                if self.dragging_item != "playhead":
                    changed_during_drag = True
                    
                    if len(self.selected_ids) == 1:
                        item = next((i for i in self.items if i["id"] == self.dragging_item), None)
                        if item:
                            center_y = item.get("visual_y", self.get_track_y(item["track"])[0]) + self.get_track_y(item["track"])[1] / 2
                            group = "video" if item["type"] in ["video", "image"] else item["type"]
                            group_tracks = [t for t in self.track_defs if t["group"] == group]
                            
                            # Remember original track before reassignment for V1 protection
                            track_before_drag = self.original_track
                            
                            if group_tracks:
                                matched = False
                                for t in group_tracks:
                                    ty, th = self.get_track_y(t["id"])
                                    if ty <= center_y <= ty + th:
                                        if not self.is_track_locked(t["id"]):
                                            item["track"] = t["id"]
                                        matched = True
                                        break
                                
                                if not matched:
                                    first_t_y = self.get_track_y(group_tracks[0]["id"])[0]
                                    last_t_y, last_th = self.get_track_y(group_tracks[-1]["id"])
                                    max_num = max(int(t["id"].split('_')[1]) for t in group_tracks)
                                    
                                    if center_y < first_t_y and group in ["video", "effect", "caption"]:
                                        item["track"] = f"{group}_{max_num + 1}"
                                    elif center_y > last_t_y + last_th and group == "audio":
                                        item["track"] = f"{group}_{max_num + 1}"

                            # BUG 2 FIX: If clip was on V1 and is now moving away, check V1 protection
                            if track_before_drag == "video_1" and item["track"] != "video_1":
                                v1_remaining = [i for i in self.items if i["track"] == "video_1" and i["id"] != item["id"]]
                                if not v1_remaining:
                                    print("V1 Protection: Cannot move last clip from V1.")
                                    item["track"] = "video_1"
                                    item["x"] = self.original_x

                            if item["track"] != "video_1" or not self.v1_gravity_enabled:
                                while True:
                                    overlapping = False
                                    for other in self.items:
                                        if other != item and other["track"] == item["track"]:
                                            if item["x"] < other["x"] + other["w"] and item["x"] + item["w"] > other["x"]:
                                                overlapping = True
                                                item["x"] = other["x"] + other["w"] 
                                                break
                                    if not overlapping:
                                        break
                        
                            if "visual_y" in item:
                                del item["visual_y"]
            elif self._drag_started and self.resizing_item:
                changed_during_drag = True
                        
            self._drag_started = False
            self.dragging_item = ""
            self.resizing_item = ""
            
            if changed_during_drag:
                self.save_state()
            
            self._cleanup_empty_tracks()
            self._apply_magnetic_v1() 
            self.update_max_width()
            self._emit_selection_state()
            self.update()

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

        word_groups = {}
        for item in self.items:
            if self.is_track_hidden(item["track"]): continue
            
            if item["type"] == "word" and "parent_id" in item:
                parent = next((p for p in self.items if p["id"] == item["parent_id"]), None)
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
            parent = next((p for p in self.items if p["id"] == pid), None)
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

        # -------------------------------------------------------------
        # PASS 1: Base Graphics (Rectangles, Thumbnails, Waveforms)
        # -------------------------------------------------------------
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
                parent = next((p for p in self.items if p["id"] == item.get("parent_id")), None)
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
                
            elif item["type"] == "effect":
                painter.fillPath(path, QColor(138, 43, 226, 80))
                painter.setPen(QColor("#e0b0ff"))
                painter.setFont(QFont("Arial", 8, QFont.Bold))
                painter.drawText(rect, Qt.AlignCenter, item["text"])

            elif item["type"] in ["video", "image"]:
                bg_color = QColor("#1a1a1a") if item["type"]=="video" else QColor("#1f1a30")
                if not is_selected and not is_hovered: bg_color.setAlpha(180)
                
                painter.fillPath(path, bg_color)
                painter.drawPath(path)
                
                # Split rect for thumb and waveform to prevent overlay
                has_wave = item["type"] == "video" and item.get("waveform")
                thumb_h = int((th - 8) * 0.65) if has_wave else int(th - 8)
                thumb_rect = QRect(rect.left(), rect.top(), rect.width(), thumb_h)
                
                # DYNAMIC THUMBNAIL RENDERING BLOCK
                if thumb_h > 0:
                    if item["type"] == "image":
                        # For static images, seamlessly tile the one thumbnail
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
                        # For video, extract actual timestamps based on timeline length scaling
                        painter.save()
                        painter.setClipRect(thumb_rect)
                        
                        thumb_w_physical = int(thumb_h * 1.777) # 16:9 approx fallback size
                        if thumb_w_physical < 10: thumb_w_physical = 100
                        
                        item_phys_x = thumb_rect.left()
                        start_i = max(0, (visible_left - item_phys_x) // thumb_w_physical)
                        end_i = min(thumb_rect.width() // thumb_w_physical + 1, (visible_right - item_phys_x) // thumb_w_physical + 2)
                        
                        source_in = item.get("source_in", 0)
                        
                        for i in range(start_i, end_i):
                            logical_offset = (i * thumb_w_physical) / z
                            # FIX: 100 units = 1000ms. So 1 unit = 10ms offset.
                            time_ms = (source_in + logical_offset) * 10
                            
                            px = self._get_dynamic_thumbnail(item, time_ms, thumb_h)
                            if px:
                                painter.drawPixmap(item_phys_x + i * thumb_w_physical, thumb_rect.top(), px)
                        
                        overlay_color = QColor(0, 0, 0, 140) if not is_selected and not is_hovered else QColor(0, 0, 0, 90)
                        painter.fillRect(thumb_rect, overlay_color)
                        painter.restore()
                
                # DRAW WAVEFORM OVERLAY FOR VIDEO
                if has_wave:
                    wave_data = item.get("waveform", [])
                    if wave_data:
                        painter.save()
                        
                        wave_bg_h = rect.height() - thumb_h
                        wave_bg_rect = QRect(rect.left(), thumb_rect.bottom(), rect.width(), wave_bg_h)
                        
                        painter.setClipRect(wave_bg_rect)
                        painter.fillRect(wave_bg_rect, QColor(0, 0, 0, 150))
                        
                        wave_color = QColor(230, 107, 44, 220) if is_selected else QColor(0, 150, 150, 180) # Orange selected, Aqua unselected
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
                                
                            h = (val / 100.0) * max_wave_h
                            safe_h = max(2, min(h, max_wave_h))
                            painter.drawLine(hx, int(base_y - safe_h/2), hx, int(base_y + safe_h/2))
                            
                        painter.restore()

            elif item["type"] == "audio":
                if is_selected:
                    painter.fillPath(path, QColor(230, 107, 44, 25))
                    painter.setPen(QPen(QColor("#e66b2c"), 1))
                    wave_color = QColor("#e66b2c")
                elif is_hovered:
                    painter.fillPath(path, QColor(255, 255, 255, 12))
                    painter.setPen(QPen(QColor("#404040"), 1))
                    wave_color = QColor("#cccccc")
                else:
                    painter.fillPath(path, Qt.transparent)
                    painter.setPen(QPen(QColor("#1f1f1f"), 1))
                    wave_color = QColor("#666666")

                painter.drawPath(path)
                
                # DRAW TEXT top-left
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
                
                samples_per_logical = 50.0 / 100.0 # Standard UI scalar
                
                source_in = item.get("source_in", 0)
                
                if wave_data:
                    for i in range(start_i, end_i):
                        logical_w_pos = item["x"] + (i * logical_step)
                        logical_offset = logical_w_pos - item["x"]
                        
                        hx = int(logical_w_pos * z)
                        
                        # Add source_in shift for accurate audio waveform sync if trimmed
                        sample_idx = int((source_in + logical_offset) * samples_per_logical)
                        
                        val = wave_data[sample_idx] if 0 <= sample_idx < len(wave_data) else 0
                            
                        h = (val / 100.0) * max_wave_h
                        safe_h = max(2, min(h, max_wave_h))
                        painter.drawLine(hx, int(base_y - safe_h/2), hx, int(base_y + safe_h/2))
                else:
                    # Fallback dummy wave while loading safely to prevent visual pops
                    for i in range(start_i, end_i):
                        logical_w_pos = item["x"] + (i * logical_step)
                        hx = int(logical_w_pos * z)
                        wave_idx = int(logical_w_pos) % len(self.audio_waveforms)
                        h = self.audio_waveforms[wave_idx] 
                        safe_h = min(h, max_wave_h) 
                        painter.drawLine(hx, int(base_y - safe_h/2), hx, int(base_y + safe_h/2))

        # -------------------------------------------------------------
        # PASS 2: Overlay Elements (Transitions, Text, FX Badges)
        # Guarantees FX Button and Names are readable on top of everything!
        # -------------------------------------------------------------
        for item in self.items:
            if self.is_track_hidden(item["track"]): continue
            if item["type"] not in ["video", "image"]: continue
            
            item_start = item["x"] * z
            item_end = (item["x"] + item["w"]) * z
            if item_end < visible_left - 50 or item_start > visible_right + 50:
                continue

            ty, th = self.get_track_y(item["track"])
            if th == 0: continue 
            draw_y = item.get("visual_y", ty)
            rect = QRect(int(item["x"] * z), int(draw_y) + 4, int(item["w"] * z), th - 8)
            is_selected = item["id"] in self.selected_ids

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

            # Draw Readability Text
            painter.setPen(QColor("#d1d1d1"))
            prefix = ""
            if item.get("freeze"): prefix += "[F] "
            if item.get("reverse"): prefix += "[Rev] "
            if item.get("mirror"): prefix += "[M] "
            if item.get("rotate"): prefix += "[Rot] "
            
            # Show Crop preset tag dynamically!
            crop_type = item.get("crop_preset", "Original")
            if crop_type != "Original": prefix += f"[{crop_type}] "
            elif item.get("crop"): prefix += "[C] "
            
            painter.setFont(QFont("Arial", 8, QFont.Bold))
            painter.drawText(rect.adjusted(5, 5, -5, -5), Qt.AlignLeft | Qt.AlignTop, prefix + item["text"])

            # Render the FX box LAST so it remains clickable on top of transitions
            if item.get("applied_effects"):
                fx_rect = QRect(rect.right() - 22, rect.top() + 4, 18, 16)
                fill_color = QColor(155, 89, 182, 220) if is_selected and self.selected_item_type == "clip_effect" else QColor(155, 89, 182, 180)
                painter.fillRect(fx_rect, fill_color) 
                painter.setPen(QPen(QColor("#e0b0ff"), 1 if is_selected and self.selected_item_type == "clip_effect" else 0))
                painter.drawRect(fx_rect)
                painter.setPen(QColor("#ffffff"))
                painter.setFont(QFont("Arial", 7, QFont.Bold))
                painter.drawText(fx_rect, Qt.AlignCenter, "FX")

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
            painter.setPen(QPen(QColor("#4299e1"), 2, Qt.DashLine))
            painter.drawLine(snap_px, 0, snap_px, self.height())

        if self.active_tool == "blade" and self.blade_line_x is not None:
            blade_px = int(self.blade_line_x * z)
            painter.setPen(QPen(QColor("#e81123"), 1, Qt.DashLine))
            painter.drawLine(blade_px, 0, blade_px, self.height())
            painter.setBrush(QColor("#e81123"))
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