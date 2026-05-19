import random
import copy
import os
import uuid
try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

from core.signal_hub import global_signals
from core.app_config import app_config
from core.media_manager import media_manager

class OperationsMixin:
    def update_item_property(self, item_id, prop_name, new_value, save_state=True):
        if prop_name == "apply_transition_to_all":
            track_id = new_value.get("track")
            if track_id != "video_1": return
            trans_name = new_value.get("transition")
            trans_dur = int(app_config.get_setting("default_transition_duration", 1.0) * 30)
            for item in self.items:
                if item["track"] == track_id and item["type"] in ["video", "image"] and not self.is_track_locked(item["track"]):
                    item["transition_in"] = trans_name
                    item["transition_in_duration"] = trans_dur
                    item["transition_out"] = trans_name
                    item["transition_out_duration"] = trans_dur
            self.update()
            if save_state:
                self.save_state()
            return

        if prop_name == "transition_in_duration_sec":
            frames = max(1, int(float(new_value) * 30))
            for item in self.items:
                if item["id"] == item_id and not self.is_track_locked(item["track"]):
                    item["transition_in_duration_sec"] = new_value
                    item["transition_in_duration"] = frames
                    self.update()
                    break
            self.save_state()
            global_signals.clip_transform_changed.emit(item_id, "transition_in_duration", frames)
            return

        if prop_name == "transition_out_duration_sec":
            frames = max(1, int(float(new_value) * 30))
            for item in self.items:
                if item["id"] == item_id and not self.is_track_locked(item["track"]):
                    item["transition_out_duration_sec"] = new_value
                    item["transition_out_duration"] = frames
                    self.update()
                    break
            self.save_state()
            global_signals.clip_transform_changed.emit(item_id, "transition_out_duration", frames)
            return
            
        for item in self.items:
            if item["id"] == item_id:
                if self.is_track_locked(item["track"]): return
                if prop_name == "Speed":
                    actual_speed = max(0.1, float(new_value))
                    item["w"] = item.get("max_w", item["w"]) / (actual_speed / 100.0)
                    self._apply_magnetic_v1()
                    self.update_max_width()
                item[prop_name] = new_value
                self.update()
                break
        
        if save_state:
            self.save_state()
        else:
            self.sync_to_project()
        
        global_signals.clip_transform_changed.emit(item_id, prop_name, new_value)

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
            
            if data.get("duration") and float(data["duration"]) > 0:
                duration_sec = float(data["duration"])
                item_w = int(duration_sec * 100)
                if subtype in ["video", "audio"]:
                    max_w = item_w
            elif drop_type == "caption":
                item_w = 400
            elif drop_type == "effect":
                item_w = 1500
            elif subtype == "image":
                item_w = int(app_config.get_setting("default_image_duration", 5.0) * 100)
            elif subtype in ["video", "audio"]:
                item_w = 1000  

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
            
        self._cleanup_empty_tracks()
        self._apply_magnetic_v1()
        self.update_max_width()
        self.save_state()
        self.sync_to_project()
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
                        insert_duration = 300 
                        
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

    def toggle_item_property(self, prop_name, **kwargs):
        changed = False
        for s_id in list(self.selected_ids):
            item = next((i for i in self.items if i["id"] == s_id), None)
            if item and item["type"] in ["video", "image"] and not self.is_track_locked(item["track"]):
                if prop_name == "rotate":
                    item["Rotation"] = (item.get("Rotation", 0) + 90) % 360
                    self._on_external_transform(s_id, "Rotation", item["Rotation"])
                else:
                    item[prop_name] = not item.get(prop_name, False)
                    for k, v in kwargs.items():
                        if k == "mute_audio" and v:
                            item["Volume"] = -100
                        else:
                            item[k] = v
                changed = True
        if changed:
            self.save_state()
            self.sync_to_project()
            self._emit_selection_state()
            self.update()

    def get_v1_duration(self):
        v1_items = [i for i in self.items if i["track"] == "video_1"]
        if not v1_items:
            return 0
        return max([i["x"] + i["w"] for i in v1_items])

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

    def delete_selected_item(self):
        if not self.selected_ids:
            return

        changed = False
        to_delete = set()
        
        for i in self.items:
            if i["id"] in self.selected_ids or i.get("parent_id") in self.selected_ids:
                if not self.is_track_locked(i["track"]):
                    if self.selected_item_type == "transition_in":
                        i.pop("transition_in", None)
                        i.pop("transition", None) 
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
            v1_remaining = [i for i in self.items if i["track"] == "video_1" and i["id"] not in to_delete]
            if not v1_remaining:
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

        for old_id in reversed(top_zone):
            group = old_id.split("_")[0]
            try:
                num = int(old_id.split("_")[1])
            except:
                num = 0

            if num >= 10000:
                max_group_counts[group] += 1
                new_num = max_group_counts[group]
                new_id = f"{group}_{new_num}"
                track_mapping[old_id] = new_id
            else:
                track_mapping[old_id] = old_id

        for old_id in top_zone:
            new_id = track_mapping[old_id]
            group = new_id.split("_")[0]
            new_num = int(new_id.split("_")[1])
            new_defs.append(self._create_def(group, new_num, new_id))
            
        track_mapping["video_1"] = "video_1"
        new_defs.append(self._create_def("video", 1, "video_1"))
        track_mapping["audio_1"] = "audio_1"
        new_defs.append(self._create_def("audio", 1, "audio_1"))
        
        for old_id in audio_zone:
            group = "audio"
            try:
                num = int(old_id.split("_")[1])
            except:
                num = 0
                
            if num >= 10000:
                max_group_counts["audio"] += 1
                new_num = max_group_counts["audio"]
                new_id = f"audio_{new_num}"
                track_mapping[old_id] = new_id
            else:
                track_mapping[old_id] = old_id
                new_num = num
                new_id = old_id
                
            new_defs.append(self._create_def("audio", new_num, new_id))
            
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
