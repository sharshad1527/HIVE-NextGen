import json
import random
import os
from PySide6.QtCore import Qt, QRect
from core.app_config import app_config
from core.media_manager import media_manager

class DragDropMixin:
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
            if hovered_clip and hovered_clip["type"] in ["video", "image"] and hovered_clip["track"] == "video_1":
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
                    dur_sec = float(app_config.get_setting("default_transition_duration", 1.0))
                    trans_dur_frames = max(1, int(dur_sec * 30))

                    if getattr(self, "_drop_target_edge", "left") == "left":
                        item["transition_in"] = title
                        item["transition_in_duration"] = trans_dur_frames
                        item["transition_in_duration_sec"] = dur_sec
                    else:
                        item["transition_out"] = title
                        item["transition_out_duration"] = trans_dur_frames
                        item["transition_out_duration_sec"] = dur_sec
                    self.save_state()
                    self._emit_selection_state()
                    
            elif drop_type == "effect" and self._drop_target_type == "clip":
                item = next((i for i in self.items if i["id"] == self._drop_target_item), None)
                if item:
                    current_effects = item.get("applied_effects", [])
                    if isinstance(current_effects, str):
                        current_effects = [current_effects]
                    elif not isinstance(current_effects, list):
                        current_effects = []
                        
                    if title not in current_effects:
                        current_effects.append(title)
                        
                    item["applied_effects"] = current_effects
                    item["primary_effect"] = title
                    
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
                
                if drop_type == "effect":
                    new_item["primary_effect"] = title
                    new_item["applied_effects"] = [title]
                
                preset_props = data.get("preset_properties", {})
                if preset_props:
                    from core.preset_loader import get_default_properties
                    defaults = get_default_properties({"properties": preset_props})
                    for k, v in defaults.items():
                        new_item[k] = v
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
