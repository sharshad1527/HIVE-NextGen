from PySide6.QtCore import QTimer
from core.render_engine import RenderEngine
from core.logger import hive_logger

class RenderingMixin:
    """
    Manages the connection to the RenderEngine, including frame ingestion
    and project resolution/aspect-ratio scaling.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._preview_aspect = (16, 9)

        # Initialize the high-performance RenderEngine
        self.render_engine = RenderEngine()
        self.render_engine.frame_ready.connect(self._on_timeline_frame_received)
        self.render_engine.frame_ready_raw.connect(self._on_timeline_frame_received_raw)
        self.render_engine.start()
        hive_logger.info("RenderingMixin: RenderEngine started.")

    def _force_refresh_render(self):
        """Forces the RenderEngine to generate a new frame for the current playhead."""
        if not self.is_playing:
            self.render_engine.request_frame(int(self.playhead))

    def _on_property_changed_rerender(self, clip_id, prop_name, value):
        """Slot for when a clip property changes, requiring a re-render of the current frame."""
        self._force_refresh_render()

    def _on_timeline_frame_received(self, frame):
        """Slot for when the RenderEngine produces a new QImage frame (legacy path)."""
        self.timeline_canvas.set_frame(frame)

    def _on_timeline_frame_received_raw(self, frame_data):
        """
        Pass sync tuple (logical_time, frame, effect_data) to viewport for GPU upload.
        This is the modern, high-performance path.
        """
        self.timeline_canvas.update_frame(frame_data)

    def _on_aspect_changed(self, aspect_text):
        """Slot for manual aspect ratio overrides from the UI."""
        if aspect_text in self.ASPECT_PRESETS:
            hive_logger.debug(f"RenderingMixin: Aspect ratio changed to {aspect_text}.")
            self._preview_aspect = self.ASPECT_PRESETS[aspect_text]
            self._update_canvas_size()
            self._force_refresh_render()

    def _update_canvas_size(self):
        """Adjusts the viewport widget size to maintain the desired aspect ratio within the panel."""
        available_w = self._canvas_area.width()
        available_h = self._canvas_area.height()
        if available_w <= 0 or available_h <= 0:
            return
        
        aspect_w, aspect_h = self._preview_aspect
        aspect_ratio = aspect_w / aspect_h
        
        if available_w / available_h > aspect_ratio:
            canvas_h = available_h
            canvas_w = int(canvas_h * aspect_ratio)
        else:
            canvas_w = available_w
            canvas_h = int(canvas_w / aspect_ratio)
        
        self.video_container.setFixedSize(max(1, canvas_w), max(1, canvas_h))

    def resizeEvent(self, event):
        """Overridden to trigger aspect-ratio recalculation on widget resize."""
        super().resizeEvent(event)
        QTimer.singleShot(0, self._update_canvas_size)

    def _on_res_changed(self, res_text):
        """Slot for changing the preview render scale (Quality: Full, 1/2, 1/4, 1/8)."""
        hive_logger.info(f"RenderingMixin: Render resolution set to {res_text}.")
        if res_text == "Full":
            self.render_engine.set_render_scale(1.0)
            self.render_engine.set_render_fps(30.0)
        elif res_text == "1/2":
            self.render_engine.set_render_scale(0.5)
            self.render_engine.set_render_fps(30.0)
        elif res_text == "1/4":
            self.render_engine.set_render_scale(0.25)
            self.render_engine.set_render_fps(30.0)
        elif res_text == "1/8":
            self.render_engine.set_render_scale(0.125)
            self.render_engine.set_render_fps(24.0)
            
        self.resolution_changed.emit(res_text)
        
        if self.is_preview_mode and not self.is_timeline_preview:
            self._apply_preview_source()

