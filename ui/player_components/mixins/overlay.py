import os
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QPen, QColor

class OverlayMixin:
    """
    Mixin for TimelinePreviewCanvas that handles the drawing of interactive
    on-screen UI elements, such as selection wireframes and transform handles.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._selected_clip_id = ""
        self._show_handles = False

    def paint_overlays(self, painter):
        """
        Renders interactive handles using QPainter on top of the OpenGL surface.
        Logic includes dashed wireframes, corner resize handles, and a rotation handle.
        """
        if self._show_handles and self._selected_clip_id:
            clip = self._get_selected_clip_data()
            if clip and clip.clip_type in ("video", "image", "caption"):
                bounds = self._get_clip_screen_bounds(clip)
                if bounds:
                    cx, cy = bounds["cx"], bounds["cy"]
                    hw, hh = bounds["hw"], bounds["hh"]
                    rotation = bounds["rotation"]
                    
                    painter.save()
                    # Apply clip transformation for drawing local handles
                    painter.translate(cx, cy)
                    painter.rotate(rotation)
                    
                    # 1. Draw Selection Wireframe
                    painter.setPen(QPen(QColor("#e66b2c"), 2, Qt.DashLine))
                    painter.setBrush(Qt.NoBrush)
                    painter.drawRect(QRectF(-hw, -hh, hw * 2, hh * 2))
                    
                    # 2. Draw Corner Resize Handles
                    handle_size = 8
                    corners = [
                        QPointF(-hw, -hh), QPointF(hw, -hh),
                        QPointF(-hw, hh), QPointF(hw, hh)
                    ]
                    painter.setPen(QPen(QColor("#ffffff"), 1))
                    painter.setBrush(QColor("#e66b2c"))
                    for corner in corners:
                        painter.drawRect(QRectF(
                            corner.x() - handle_size/2, corner.y() - handle_size/2,
                            handle_size, handle_size
                        ))
                    
                    # 3. Draw Rotation Handle (Top Center)
                    top_center = QPointF(0, -hh - 25)
                    painter.setPen(QPen(QColor("#ffffff"), 1))
                    painter.setBrush(QColor("#4299e1"))
                    painter.drawEllipse(top_center, 6, 6)
                    
                    # Connector line to rotation handle
                    painter.setPen(QPen(QColor("#4299e1"), 1))
                    painter.drawLine(0, 0, 0, int(top_center.y() + 6))
                    
                    painter.restore()

    def _get_clip_screen_bounds(self, clip):
        """
        Calculates the on-screen (widget) coordinates of a clip's bounding box.
        Handles animated properties (Position, Scale, Rotation) using frame-accurate timing.
        """
        if not clip or self.frame_width <= 0:
            return None
        
        props = clip.applied_effects if isinstance(clip.applied_effects, dict) else {}
        
        base_x = getattr(clip, "Position_X", props.get("Position_X", 0))
        base_y = getattr(clip, "Position_Y", props.get("Position_Y", 0))
        base_zoom = props.get("Scale", 100) / 100.0
        base_rot = props.get("Rotation", 0)
        
        # USE FRAME-ACCURATE TIMING: Sync handles to the frame currently visible on the GPU.
        sync_time = self.last_frame_time
        
        if hasattr(clip, 'get_animated_value'):
            rel_time = max(0.0, sync_time - (clip.start_time / 10.0))
            pos_x = clip.get_animated_value("Position_X", rel_time, base_x)
            pos_y = clip.get_animated_value("Position_Y", rel_time, base_y)
            zoom = clip.get_animated_value("Scale", rel_time, base_zoom * 100) / 100.0
            rotation = clip.get_animated_value("Rotation", rel_time, base_rot)
        else:
            pos_x, pos_y, zoom, rotation = base_x, base_y, base_zoom, base_rot
            
        scale_pct = zoom
        self._update_canvas_mapping()
        
        # Mapping from project space to widget space
        center_x = (self._proj_w / 2) + pos_x
        center_y = (self._proj_h / 2) + pos_y
        cw, ch = self._proj_w, self._proj_h
        
        # Calculate media-specific aspect ratio adjustment
        if clip.clip_type in ["video", "image"] and getattr(clip, "file_path", None) and os.path.exists(clip.file_path):
            if "media_w" not in props or "media_h" not in props:
                from core.media_manager import media_manager
                meta = media_manager.process_file(clip.file_path)
                if meta:
                    props["media_w"] = meta.get("width", 0)
                    props["media_h"] = meta.get("height", 0)
            
            if props.get("media_w", 0) > 0 and props.get("media_h", 0) > 0:
                mw, mh = props["media_w"], props["media_h"]
                ratio = min(self._proj_w / mw, self._proj_h / mh)
                cw = mw * ratio
                ch = mh * ratio
                
        elif clip.clip_type == "caption":
            font_size = max(1, int(props.get("Font Size", 80)))
            text = props.get("text", "") or getattr(clip, "file_path", "") or "New Caption"
            cw = len(text) * font_size * 0.6
            ch = font_size * 1.5
            
        # Apply crop modifiers
        crop_w = props.get("crop_w", 100) / 100.0
        crop_h = props.get("crop_h", 100) / 100.0
        
        cw = max(1.0, cw * crop_w)
        ch = max(1.0, ch * crop_h)

        half_w = (cw / 2) * scale_pct
        half_h = (ch / 2) * scale_pct
        
        render_scale = self._canvas_scale
        cx = self._canvas_offset_x + center_x * render_scale
        cy = self._canvas_offset_y + center_y * render_scale
        hw = half_w * render_scale
        hh = half_h * render_scale
        
        return {"cx": cx, "cy": cy, "hw": hw, "hh": hh, "rotation": rotation, "original_scale": scale_pct}

