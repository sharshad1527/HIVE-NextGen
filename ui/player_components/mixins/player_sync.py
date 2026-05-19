import qtawesome as qta
from PySide6.QtCore import QTimer

from core.signal_hub import global_signals
from core.project_manager import project_manager
from core.logger import hive_logger

class PlayerSyncMixin:
    """
    Mixin containing project-level synchronization and global signal responses for the Player.
    Ensures the Player's internal state matches the current project resolution, tracks, and selection.
    """

    def _sync_mixer_to_timeline(self):
        """Called anytime a clip is dragged, trimmed, cut, or deleted to update the Audio Mixer's timeline."""
        if project_manager.current_project:
            hive_logger.debug("PlayerSyncMixin: Syncing Audio Mixer to timeline.")
            self.audio_mixer.sync_from_project(project_manager.current_project)

    def reset_player(self):
        """Clears all state and prepares the Player for a new project load."""
        hive_logger.info("PlayerSyncMixin: Resetting player for new project.")
        self.is_playing = False
        self.playhead = 0.0
        self.duration = 0.0
        self.is_preview_mode = False
        self.is_timeline_preview = False
        
        # Reset hardware components
        self.player.stop()
        self.audio_mixer.clear_tracks()
        if hasattr(self.render_engine, 'clear_cache'):
            self.render_engine.clear_cache() 
        
        # Reset UI elements
        self._update_timecode_label()
        self.scrubber.setValue(0)
        self.btn_play.setIcon(qta.icon('mdi6.play', color='#e66b2c'))
        
        # AGGRESSIVE PRIMING: Ensure decoders are woken up and frame 0 is rendered.
        # Multiple requests handle potential async initialization delays.
        for delay in [200, 600, 1200]:
            QTimer.singleShot(delay, lambda: self.render_engine.request_frame(0))
        
        hive_logger.info("PlayerSyncMixin: Project loaded. Renderer primed.")

    def _on_clip_updated(self, clip_data):
        """Callback when a clip's underlying data is modified."""
        # This currently triggers an audio mixer rebuild to ensure sync
        self._sync_mixer_to_timeline()

    def _on_project_resolution_changed(self, resolution):
        """Automatically updates the player aspect ratio when the project resolution changes."""
        w, h = resolution
        hive_logger.info(f"PlayerSyncMixin: Project resolution changed to {w}x{h}.")
        best_match = "16:9" 
        target_ratio = w / h if h > 0 else 1.78
        min_diff = float('inf')
        for label, (aw, ah) in self.ASPECT_PRESETS.items():
            diff = abs((aw / ah) - target_ratio)
            if diff < min_diff:
                min_diff = diff
                best_match = label
        
        self.combo_aspect.blockSignals(True)
        self.combo_aspect.setCurrentText(best_match)
        self.combo_aspect.blockSignals(False)
        self._preview_aspect = self.ASPECT_PRESETS[best_match]
        self._update_canvas_size()
        self._force_refresh_render()

    def _on_clip_selected_for_preview(self, item_type, clip_id):
        """Informs the canvas which clip is currently selected for overlay handle drawing."""
        self.timeline_canvas.set_selected_clip(clip_id)
    
    def _on_clip_deselected_for_preview(self):
        """Clears selection handles on the canvas."""
        self.timeline_canvas.set_selected_clip("")

    def _on_canvas_transform(self, clip_id, prop_name, value):
        """Propagates interactive canvas transforms (drag/scale/rotate) to the global signal hub."""
        global_signals.clip_transform_changed.emit(clip_id, prop_name, value)

