import random
import copy
import os
from PySide6.QtCore import Qt, QTimer
from core.signal_hub import global_signals
from core.project_manager import project_manager
from core.app_config import app_config
from core.models import TrackData, ClipData

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

class BaseMixin:
    """Provides base state and core state-management helper methods for the timeline canvas."""
    
    def _init_base_state(self):
        self._initialized = False  
        self.zoom_factor = 1.0
        self.max_logical_width = 0
        self.logical_playhead = 0.0 
        self.v_scroll_y = 0 
        
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
        self.audio_waveforms = [random.randint(10, 40) for _ in range(300)] 
        
        self.pixmap_cache = {} 
        self.pending_thumbs = set()
        
        self._click_physical_pos = None
        self._click_logical_x = 0
        self._potential_action = None
        self._potential_item = None
        self._potential_edge = None
        self._drag_started = False
        
        self.dragging_kf = None
        self.dragging_kf_prop = None
        self.dragging_kf_item = None
        self.dragging_kf_backend = None
        
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
        self.copied_attributes = None
        
        self.auto_scroll_timer = QTimer(self)
        self.scroll_dx = 0

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
        return str(app_config.thumbnail_cache_path)

    def _get_backend_clip(self, clip_id):
        if not project_manager.current_project: return None
        for track in project_manager.current_project.tracks:
            for clip in track.clips:
                if clip.clip_id == clip_id: return clip
        return None

    def clear_all(self):
        """Wipes the timeline completely for a new project."""
        self.items = []
        self.selected_ids = set()
        self.logical_playhead = 0.0
        self.max_logical_width = 0
        self._initialized = False
        self.update()
        self.v1_duration_changed.emit(0.0)
        print("Timeline: Canvas cleared.")

    def sync_to_project(self):
        """Packs current visual timeline blocks back into the backend Brain."""
        if not project_manager.current_project:
            return
        if not self._initialized:
            return 
            
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
                metadata = {}
                skip_keys = {"id", "track", "type", "text", "file_path", "x", "w", "visual_y", "waveform"}
                for k, v in item.items():
                    if k in skip_keys:
                        continue
                    if isinstance(v, float) and (v == float('inf') or v == float('-inf') or v != v):
                        continue
                    metadata[k] = v
                
                actual_file_path = item.get("file_path", item.get("text", ""))
                
                if item.get("type") == "caption":
                    if "text" not in metadata:
                        metadata["text"] = item.get("text", "New Caption")
                
                old_clip = self._get_backend_clip(item["id"])
                if old_clip:
                    old_clip.clip_type = item["type"]
                    old_clip.file_path = actual_file_path
                    old_clip.start_time = int(item["x"] * 10)
                    old_clip.end_time = int((item["x"] + item["w"]) * 10)
                    old_clip.applied_effects = metadata
                    clips.append(old_clip)
                else:
                    clips.append(ClipData(
                        clip_id=item["id"],
                        clip_type=item["type"],
                        file_path=actual_file_path, 
                        start_time=int(item["x"] * 10), 
                        end_time=int((item["x"] + item["w"]) * 10),
                        applied_effects=metadata,
                        animations={}
                    ))
                
            new_tracks.append(TrackData(
                track_name=t_def["label"],
                track_type=group,
                track_id=t_id,
                clips=clips,
                is_hidden=self.track_states.get(t_id, {}).get("hidden", False)
            ))
            
        project_manager.current_project.tracks = new_tracks
        if hasattr(global_signals, 'timeline_updated'):
            global_signals.timeline_updated.emit()

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
                emit_type = self.selected_item_type
                if emit_type not in ["transition_in", "transition_out", "clip_effect"]:
                    emit_type = item["type"]
                self.item_clicked.emit(emit_type, item["id"], copy.deepcopy(item))
                global_signals.clip_selected.emit(emit_type, item["id"])
            else:
                self.item_clicked.emit("", "", {})
                global_signals.clip_deselected.emit()

    def save_state(self):
        """Pushes current visual layout to undo history, and signals the UI that a change happened."""
        self.history = self.history[:self.history_idx + 1]
        state = {
            "items": copy.deepcopy(self.items),
            "track_defs": copy.deepcopy(self.track_defs),
            "track_states": copy.deepcopy(self.track_states)
        }
        self.history.append(state)
        self.history_idx += 1
        
        self.sync_to_project()
        self.state_changed.emit()

    def undo(self):
        if self.history_idx > 0:
            self.history_idx -= 1
            state = self.history[self.history_idx]
            self.items = copy.deepcopy(state.get("items", []))
            self.track_defs = copy.deepcopy(state.get("track_defs", []))
            self.track_states = copy.deepcopy(state.get("track_states", {}))
            
            current_ids = {i["id"] for i in self.items}
            self.selected_ids = {sid for sid in self.selected_ids if sid in current_ids}
            self._emit_selection_state()
            self._apply_magnetic_v1()
            self.update_max_width()
            self.tracks_changed.emit()
            self.state_changed.emit()
            self.sync_to_project()
            self.update()

    def redo(self):
        if self.history_idx < len(self.history) - 1:
            self.history_idx += 1
            state = self.history[self.history_idx]
            self.items = copy.deepcopy(state.get("items", []))
            self.track_defs = copy.deepcopy(state.get("track_defs", []))
            self.track_states = copy.deepcopy(state.get("track_states", {}))
            
            current_ids = {i["id"] for i in self.items}
            self.selected_ids = {sid for sid in self.selected_ids if sid in current_ids}
            self._emit_selection_state()
            self._apply_magnetic_v1()
            self.update_max_width()
            self.tracks_changed.emit()
            self.state_changed.emit()
            self.sync_to_project()
            self.update()

    def update_max_width(self):
        max_end = 0
        for item in self.items:
            max_end = max(max_end, item["x"] + item["w"])

        buffer = max(1000, int(max_end * 0.2))
        self.max_logical_width = max_end + buffer
        self.setMinimumWidth(max(int(self.max_logical_width * self.zoom_factor), 100))
        self.update()

    def get_formatted_duration(self):
        """Returns the total project duration in HH:MM:SS format."""
        max_end = 0
        for item in self.items:
            max_end = max(max_end, item["x"] + item["w"])

        total_seconds = int(max_end / 100.0)
        hours = total_seconds // 3600
        mins = (total_seconds % 3600) // 60
        secs = total_seconds % 60
        return f"{hours:02d}:{mins:02d}:{secs:02d}"

