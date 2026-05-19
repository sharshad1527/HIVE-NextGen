import math
from PySide6.QtCore import Qt, QPointF, QRectF
from core.signal_hub import global_signals
from core.project_manager import project_manager
from core.logger import hive_logger

class InteractionMixin:
    """
    Mixin for TimelinePreviewCanvas that handles all mouse-driven interactions,
    such as selecting, dragging, resizing, and rotating clips directly on the canvas.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Interactive state variables
        self._dragging = False
        self._rotating = False
        self._resizing = False
        self._drag_start = QPointF()
        self._drag_start_pos = (0, 0)
        self._drag_start_rotation = 0
        self._drag_start_scale = 1.0
        self._drag_start_dist = 0.0
        
        # Project coordinate mapping
        self._canvas_scale = 1.0
        self._canvas_offset_x = 0
        self._canvas_offset_y = 0  
        self._proj_w = 1920
        self._proj_h = 1080

    def _update_canvas_mapping(self):
        """
        Calculates the letterboxing/pillarboxing offsets and scale factor 
        between the widget size and the project frame size.
        """
        if self.frame_width > 0 and self.frame_height > 0:
            cw, ch = self.width(), self.height()
            fw, fh = self.frame_width, self.frame_height
            self._canvas_scale = min(cw / fw, ch / fh)
            nw = fw * self._canvas_scale
            nh = fh * self._canvas_scale
            self._canvas_offset_x = (cw - nw) / 2
            self._canvas_offset_y = (ch - nh) / 2

    def _canvas_to_project(self, canvas_point):
        """Maps a point from widget (pixel) space to project (resolution) space."""
        self._update_canvas_mapping()
        if self._canvas_scale == 0:
            return QPointF(0, 0)
        
        project = project_manager.current_project
        if project:
            self._proj_w, self._proj_h = project.resolution
        
        frame_x = (canvas_point.x() - self._canvas_offset_x) / self._canvas_scale
        frame_y = (canvas_point.y() - self._canvas_offset_y) / self._canvas_scale
        
        return QPointF(frame_x, frame_y)

    def _get_selected_clip_data(self):
        """Helper to fetch the ClipData object for the currently selected clip ID."""
        if not self._selected_clip_id or not project_manager.current_project:
            return None
        for track in project_manager.current_project.tracks:
            for clip in track.clips:
                if clip.clip_id == self._selected_clip_id:
                    return clip
        return None

    def _mouse_to_local(self, pos, cx, cy, rotation):
        """Converts a global mouse position to local coordinates relative to a transformed clip."""
        from PySide6.QtGui import QTransform
        t = QTransform()
        t.translate(cx, cy)
        t.rotate(rotation)
        t_inv, invertible = t.inverted()
        if not invertible: return pos
        return t_inv.map(pos)
    
    def _get_visible_clips(self):
        """Returns a list of clips currently visible at the current playhead, sorted by track Z-order."""
        visible = []
        if not project_manager.current_project:
            return visible
        
        # Iterate in reverse track order (top tracks drawn last, clicked first)
        for track in reversed(project_manager.current_project.tracks):
            if getattr(track, 'hidden', False):
                continue
            for clip in reversed(track.clips):
                start = clip.start_time / 10.0
                duration = (clip.end_time - clip.start_time) / 10.0
                end = start + duration
                if start <= self.current_time < end:
                    visible.append(clip)
        return visible

    def mousePressEvent(self, event):
        """Initiates canvas interactions (select, drag, resize, rotate)."""
        if event.button() == Qt.LeftButton:
            pos = event.position()
            handled = False
            
            # 1. First, check if the click hits a handle on the already selected clip
            if self._show_handles and self._selected_clip_id:
                clip = self._get_selected_clip_data()
                if clip:
                    bounds = self._get_clip_screen_bounds(clip)
                    if bounds:
                        local_pos = self._mouse_to_local(pos, bounds["cx"], bounds["cy"], bounds["rotation"])
                        hw, hh = bounds["hw"], bounds["hh"]
                        props = clip.applied_effects if isinstance(clip.applied_effects, dict) else {}
                        
                        self._resizing = False
                        self._dragging = False
                        self._rotating = False
                        
                        # Get current state for relative delta calculation
                        base_x = getattr(clip, "Position_X", props.get("Position_X", 0))
                        base_y = getattr(clip, "Position_Y", props.get("Position_Y", 0))
                        base_rot = props.get("Rotation", 0)
                        
                        sync_time = self.last_frame_time
                        if hasattr(clip, 'get_animated_value'):
                            rel_time = max(0.0, sync_time - (clip.start_time / 10.0))
                            curr_x = clip.get_animated_value("Position_X", rel_time, base_x)
                            curr_y = clip.get_animated_value("Position_Y", rel_time, base_y)
                            curr_rot = clip.get_animated_value("Rotation", rel_time, base_rot)
                        else:
                            curr_x, curr_y, curr_rot = base_x, base_y, base_rot
                        
                        # Rotation Handle Check
                        rot_handle = QPointF(0, -hh - 25)
                        if (local_pos - rot_handle).manhattanLength() < 20:
                            hive_logger.debug(f"InteractionMixin: Starting rotation for {clip.clip_id}.")
                            self._rotating = True
                            self._drag_start = pos
                            self._drag_start_rotation = curr_rot
                            self.setCursor(Qt.ClosedHandCursor)
                            handled = True
                        else:
                            # Resize Handles Check
                            handle_size = 12
                            corners = [
                                QPointF(-hw, -hh), QPointF(hw, -hh),
                                QPointF(-hw, hh), QPointF(hw, hh)
                            ]
                            for corner in corners:
                                if (local_pos - corner).manhattanLength() < handle_size * 2:
                                    hive_logger.debug(f"InteractionMixin: Starting resize for {clip.clip_id}.")
                                    self._resizing = True
                                    self._drag_start = pos
                                    self._drag_start_scale = bounds["original_scale"]
                                    self._drag_start_dist = math.sqrt((pos.x() - bounds["cx"])**2 + (pos.y() - bounds["cy"])**2)
                                    handled = True
                                    break
                            
                            # Body Drag Check
                            if not handled:
                                rect = QRectF(-hw, -hh, hw * 2, hh * 2)
                                if rect.contains(local_pos):
                                    hive_logger.debug(f"InteractionMixin: Starting drag for {clip.clip_id}.")
                                    self._dragging = True
                                    self._drag_start = pos
                                    self._drag_start_pos = (curr_x, curr_y)
                                    self.setCursor(Qt.ClosedHandCursor)
                                    handled = True

            # 2. If nothing on the selected clip was hit, try to select a different clip
            if not handled:
                clicked_clip = None
                for clip in self._get_visible_clips():
                    bounds = self._get_clip_screen_bounds(clip)
                    if bounds:
                        local_pos = self._mouse_to_local(pos, bounds["cx"], bounds["cy"], bounds["rotation"])
                        hw, hh = bounds["hw"], bounds["hh"]
                        rect = QRectF(-hw, -hh, hw * 2, hh * 2)
                        if rect.contains(local_pos):
                            clicked_clip = clip
                            break
                            
                if clicked_clip:
                    hive_logger.info(f"InteractionMixin: Selecting clip {clicked_clip.clip_id}.")
                    self._selected_clip_id = clicked_clip.clip_id
                    self._show_handles = True
                    self.update()
                    if hasattr(global_signals, 'clip_selected'):
                        global_signals.clip_selected.emit(clicked_clip.clip_type, clicked_clip.clip_id)
                    
                    # Auto-start dragging the new selection
                    bounds = self._get_clip_screen_bounds(clicked_clip)
                    if bounds:
                        props = clicked_clip.applied_effects if isinstance(clicked_clip.applied_effects, dict) else {}
                        base_x = getattr(clicked_clip, "Position_X", props.get("Position_X", 0))
                        base_y = getattr(clicked_clip, "Position_Y", props.get("Position_Y", 0))
                        
                        sync_time = self.last_frame_time
                        if hasattr(clicked_clip, 'get_animated_value'):
                            rel_time = max(0.0, sync_time - (clicked_clip.start_time / 10.0))
                            curr_x = clicked_clip.get_animated_value("Position_X", rel_time, base_x)
                            curr_y = clicked_clip.get_animated_value("Position_Y", rel_time, base_y)
                        else:
                            curr_x, curr_y = base_x, base_y
                            
                        self._dragging = True
                        self._drag_start = pos
                        self._drag_start_pos = (curr_x, curr_y)
                        self.setCursor(Qt.ClosedHandCursor)
                    return
                else:
                    # Clicked empty space: Clear selection
                    if self._selected_clip_id:
                        hive_logger.debug("InteractionMixin: Clearing selection.")
                        self._selected_clip_id = ""
                        self._show_handles = False
                        self.update()
                        if hasattr(global_signals, 'clip_deselected'):
                            global_signals.clip_deselected.emit()

            if handled:
                return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Processes active dragging, rotating, or resizing deltas."""
        if self._dragging and self._selected_clip_id:
            delta = event.position() - self._drag_start
            
            self._update_canvas_mapping()
            if self._canvas_scale > 0:
                proj_dx = delta.x() / self._canvas_scale
                proj_dy = delta.y() / self._canvas_scale
                
                new_x = int(self._drag_start_pos[0] + proj_dx)
                new_y = int(self._drag_start_pos[1] + proj_dy)
                
                clip = self._get_selected_clip_data()
                if clip:
                    rel_time = max(0.0, self.last_frame_time - (clip.start_time / 10.0))
                    if hasattr(clip, 'is_keyframing_enabled'):
                        if clip.is_keyframing_enabled("Position_X"): clip.set_keyframe("Position_X", rel_time, new_x)
                        if clip.is_keyframing_enabled("Position_Y"): clip.set_keyframe("Position_Y", rel_time, new_y)
                    
                    setattr(clip, "Position_X", new_x)
                    setattr(clip, "Position_Y", new_y)
                    
                    if isinstance(clip.applied_effects, dict):
                        clip.applied_effects["Position_X"] = new_x
                        clip.applied_effects["Position_Y"] = new_y
                    
                    self.transform_changed.emit(self._selected_clip_id, "Position_X", new_x)
                    self.transform_changed.emit(self._selected_clip_id, "Position_Y", new_y)
                    
                    if hasattr(global_signals, 'force_refresh'):
                        global_signals.force_refresh.emit()
                    self.update()
            return
        
        elif self._rotating and self._selected_clip_id:
            clip = self._get_selected_clip_data()
            if clip:
                bounds = self._get_clip_screen_bounds(clip)
                if bounds:
                    dx = event.position().x() - bounds["cx"]
                    dy = event.position().y() - bounds["cy"]
                    angle = math.degrees(math.atan2(dx, -dy))
                    
                    dx0 = self._drag_start.x() - bounds["cx"]
                    dy0 = self._drag_start.y() - bounds["cy"]
                    start_angle = math.degrees(math.atan2(dx0, -dy0))
                    
                    delta_angle = angle - start_angle
                    new_rotation = int(max(-360, min(360, self._drag_start_rotation + delta_angle)))
                    
                    rel_time = max(0.0, self.last_frame_time - (clip.start_time / 10.0))
                    if hasattr(clip, 'is_keyframing_enabled') and clip.is_keyframing_enabled("Rotation"):
                        clip.set_keyframe("Rotation", rel_time, new_rotation)
                    
                    setattr(clip, "Rotation", new_rotation)
                    if isinstance(clip.applied_effects, dict):
                        clip.applied_effects["Rotation"] = new_rotation
                        
                    self.transform_changed.emit(self._selected_clip_id, "Rotation", new_rotation)
                    if hasattr(global_signals, 'force_refresh'):
                        global_signals.force_refresh.emit()
                    self.update()
            return

        elif getattr(self, "_resizing", False) and self._selected_clip_id:
            clip = self._get_selected_clip_data()
            if clip:
                bounds = self._get_clip_screen_bounds(clip)
                if bounds and self._drag_start_dist > 0:
                    pos = event.position()
                    current_dist = math.sqrt((pos.x() - bounds["cx"])**2 + (pos.y() - bounds["cy"])**2)
                    
                    ratio = current_dist / self._drag_start_dist
                    new_scale = max(0.1, min(5.0, self._drag_start_scale * ratio))
                    
                    rel_time = max(0.0, self.last_frame_time - (clip.start_time / 10.0))
                    if hasattr(clip, 'is_keyframing_enabled') and clip.is_keyframing_enabled("Scale"):
                        clip.set_keyframe("Scale", rel_time, new_scale * 100)
                        
                    setattr(clip, "Scale", new_scale * 100)
                    if isinstance(clip.applied_effects, dict):
                        clip.applied_effects["Scale"] = int(new_scale * 100)
                        
                    self.transform_changed.emit(self._selected_clip_id, "Scale", new_scale * 100)
                    if hasattr(global_signals, 'force_refresh'):
                        global_signals.force_refresh.emit()
                    self.update()
            return
        
        # Hover state cursor updates
        if self._show_handles and self._selected_clip_id:
            clip = self._get_selected_clip_data()
            if clip:
                bounds = self._get_clip_screen_bounds(clip)
                if bounds:
                    pos = event.position()
                    local_pos = self._mouse_to_local(pos, bounds["cx"], bounds["cy"], bounds["rotation"])
                    hw, hh = bounds["hw"], bounds["hh"]
                    
                    rot_handle = QPointF(0, -hh - 25)
                    if (local_pos - rot_handle).manhattanLength() < 20:
                        self.setCursor(Qt.CrossCursor)
                        return
                        
                    handle_size = 12
                    corners = [
                        QPointF(-hw, -hh), QPointF(hw, -hh),
                        QPointF(-hw, hh), QPointF(hw, hh)
                    ]
                    for corner in corners:
                        if (local_pos - corner).manhattanLength() < handle_size * 2:
                            self.setCursor(Qt.SizeFDiagCursor)
                            return
                            
                    rect = QRectF(-hw, -hh, hw * 2, hh * 2)
                    if rect.contains(local_pos):
                        self.setCursor(Qt.OpenHandCursor)
                        return
        
        self.setCursor(Qt.ArrowCursor)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """Finalizes the interaction and emits persistent property change signals."""
        if self._dragging or self._rotating or getattr(self, "_resizing", False):
            self._dragging = False
            self._rotating = False
            self._resizing = False
            self.setCursor(Qt.ArrowCursor)
            
            clip = self._get_selected_clip_data()
            if clip:
                # Emit final transform signals for timeline/properties sync
                global_signals.clip_transform_changed.emit(
                    self._selected_clip_id, "Position_X", getattr(clip, "Position_X", 0)
                )
                global_signals.clip_transform_changed.emit(
                    self._selected_clip_id, "Scale", getattr(clip, "Scale", 100.0)
                )
            return
        
        super().mouseReleaseEvent(event)
