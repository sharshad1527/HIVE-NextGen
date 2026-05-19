import random
import copy
import os
from PySide6.QtCore import Qt, QRect, QPoint, Signal, QTimer
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QMenu

from core.signal_hub import global_signals
from ui.timeline.canvas.keyframe_popup import KeyframePopup

class InteractionMixin:
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

    def _get_item_and_kf_at(self, pos):
        z = self.zoom_factor
        physical_x = pos.x()
        y = pos.y()
        diamond_hit_radius = 8
        
        for item in reversed(self.items):
            if self.is_track_hidden(item["track"]): continue
            ty, th = self.get_track_y(item["track"])
            if ty <= y <= ty + th:
                ix = item["x"] * z
                iw = item["w"] * z
                
                if ix <= physical_x <= ix + iw:
                    backend_clip = self._get_backend_clip(item["id"])
                    if backend_clip and hasattr(backend_clip, 'animations'):
                        hit_kfs = []
                        for prop, anim_track in backend_clip.animations.items():
                            if not getattr(anim_track, 'enabled', True): continue
                            for kf in getattr(anim_track, 'keyframes', []):
                                kf_abs_time = item["x"] + kf.time
                                kf_x = int(kf_abs_time * z)
                                kf_y = item.get("visual_y", ty) + th / 2
                                if abs(physical_x - kf_x) < diamond_hit_radius and abs(y - kf_y) < diamond_hit_radius:
                                    hit_kfs.append((prop, kf))
                        if hit_kfs:
                            return item, backend_clip, hit_kfs
                    
                    return item, backend_clip, []
        return None, None, []

    def contextMenuEvent(self, event):
        item, backend_clip, hit_kfs = self._get_item_and_kf_at(event.pos())
        if not item: return
        
        if item["id"] not in self.selected_ids:
            self.selected_ids = {item["id"]}
            self.selected_item_type = item["type"]
            self._emit_selection_state()
            self.update()
        
        if hit_kfs:
            self.kf_popup = KeyframePopup(item, backend_clip, hit_kfs, self, self)
            global_pos = self.mapToGlobal(event.pos())
            # Offset a bit above the cursor
            self.kf_popup.move(global_pos.x() - 100, global_pos.y() - 150)
            self.kf_popup.show()
        else:
            menu = QMenu(self)
            
            cut_act = menu.addAction("Cut")
            copy_act = menu.addAction("Copy")
            paste_act = menu.addAction("Paste")
            dup_act = menu.addAction("Duplicate")
            menu.addSeparator()
            split_act = menu.addAction("Split at Playhead")
            menu.addSeparator()
            
            paste_attr_act = menu.addAction("Paste Attributes")
            if not getattr(self, 'copied_attributes', None):
                paste_attr_act.setEnabled(False)
                
            del_act = menu.addAction("Delete")
            
            action = menu.exec(event.globalPos())
            
            if action == copy_act:
                if backend_clip:
                    self.copied_attributes = copy.deepcopy(backend_clip)
            elif action == paste_attr_act and getattr(self, 'copied_attributes', None):
                if backend_clip and hasattr(backend_clip, 'copy_attributes_from'):
                    backend_clip.copy_attributes_from(self.copied_attributes)
                    for k, v in backend_clip.applied_effects.items():
                        item[k] = v
                self.save_state()
                self._emit_selection_state()
                if hasattr(global_signals, 'clip_updated'): global_signals.clip_updated.emit(backend_clip)
                if hasattr(global_signals, 'force_refresh'): global_signals.force_refresh.emit()
                self.update()
            elif action == split_act:
                self.split_at_playhead()
            elif action == del_act:
                self.delete_selected_item()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            z = self.zoom_factor
            physical_x = event.position().x()
            logical_x = physical_x / z
            y = event.position().y()
            
            item, backend_clip, hit_kfs = self._get_item_and_kf_at(event.position().toPoint())
            if hit_kfs:
                self.dragging_kf_item = item
                self.dragging_kf_backend = backend_clip
                self.dragging_kf_prop, self.dragging_kf = hit_kfs[0]
                self._drag_started = True
                self.setCursor(Qt.ClosedHandCursor)
                
                exact_kf_abs_time = item["x"] + self.dragging_kf.time
                self.set_playhead(exact_kf_abs_time)
                
                # Auto-select the item when a keyframe is clicked
                if item["id"] not in self.selected_ids:
                    self.selected_ids = {item["id"]}
                    self.selected_item_type = item["type"]
                    self._emit_selection_state()
                    self.update()
                return
            
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
                self.set_playhead(max(0, logical_x), user_initiated=True)
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
        
        if getattr(self, "dragging_kf", None):
            item = self.dragging_kf_item
            new_rel_time = logical_x - item["x"]
            new_rel_time = max(0, min(new_rel_time, item["w"]))
            self.dragging_kf.time = new_rel_time
            
            if hasattr(global_signals, 'clip_updated'):
                global_signals.clip_updated.emit(self.dragging_kf_backend)
            if hasattr(global_signals, 'force_refresh'):
                global_signals.force_refresh.emit()
            self.update()
            return
        
        if self.dragging_item == "playhead":
            self.set_playhead(logical_x, user_initiated=True)
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
                        
                speed_pct = float(item.get("Speed", 100)) / 100.0
                actual_max_w = item.get("max_w", float('inf'))
                if actual_max_w != float('inf'):
                    actual_max_w = actual_max_w / speed_pct
                item["w"] = max(10, min(new_w, actual_max_w))
            elif self.resize_edge == "left":
                max_left_x = item["x"] + item["w"] - 10
                new_x = min(logical_x, max_left_x)
                if self.magnet_enabled:
                    snap_x, shift_x = self._get_snap_target(new_x, -1000, item["id"])
                    if snap_x is not None:
                        new_x += shift_x
                        self.snap_line_x = snap_x
                
                speed_pct = float(item.get("Speed", 100)) / 100.0
                actual_max_w = item.get("max_w", float('inf'))
                if actual_max_w != float('inf'):
                    actual_max_w = actual_max_w / speed_pct
                    min_x = (item["x"] + item["w"]) - actual_max_w
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
            
            if getattr(self, "dragging_kf", None):
                if self.dragging_kf_backend and self.dragging_kf_prop:
                    track = self.dragging_kf_backend.animations.get(self.dragging_kf_prop)
                    if track:
                        track.keyframes.sort(key=lambda x: x.time)
                
                self.dragging_kf = None
                self.dragging_kf_prop = None
                self.dragging_kf_item = None
                self.dragging_kf_backend = None
                self._drag_started = False
                self.setCursor(Qt.ArrowCursor)
                self.save_state()
                return
            
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
