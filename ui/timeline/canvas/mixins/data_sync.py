import os
from core.signal_hub import global_signals
from core.models import ProjectData, TrackData, ClipData
from core.project_manager import project_manager
from core.media_manager import media_manager

class DataSyncMixin:
    def load_from_project(self, project_data: ProjectData):
        """Translates backend ProjectData into UI timeline clips."""
        self.items.clear()
        
        if project_data and project_data.tracks:
            for track in project_data.tracks:
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
                    
        self._initialized = True 
        self._cleanup_empty_tracks()
        self._apply_magnetic_v1()
        self.update_max_width()
        self.save_state()
        self.update()

    def _get_track_group(self, track_id):
        if not track_id: return None
        for t in self.track_defs:
            if t["id"] == track_id: return t["group"]
        return None

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

    def set_playhead(self, logical_x, user_initiated=False):
        self.logical_playhead = float(logical_x)
        self.playhead_changed.emit(self.logical_playhead, user_initiated)
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
