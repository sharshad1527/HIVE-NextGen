import time
import hashlib
import os
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QPixmap
from PySide6.QtMultimedia import QMediaPlayer
import qtawesome as qta

from core.signal_hub import global_signals
from core.project_manager import project_manager
from core.audio_mixer import audio_mixer
from core.app_config import app_config

from core.logger import hive_logger

class PlaybackMixin:
    """
    Handles all temporal logic for the Player, including playback state,
    scrubbing, timecode formatting, and media previewing.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Temporal state
        self.duration = 0
        self.playhead = 0
        self.is_playing = False
        
        # Preview state
        self.is_preview_mode = False
        self.is_timeline_preview = False
        self.preview_duration = 0
        self.preview_position = 0
        self.preview_loops = 0
        self.playback_start_time = 0
        self.playback_start_playhead = 0
        self.current_preview_data = None
        self._first_load_done = False

    def toggle_play(self):
        """Switches between Play and Pause states, syncing with the Audio Mixer."""
        if self.is_preview_mode and not self.is_timeline_preview:
            if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                self.player.pause()
            else:
                self.player.play()
        else:
            if self.media_stack.currentWidget() != self.timeline_canvas:
                self.media_stack.setCurrentWidget(self.timeline_canvas)

            if self.is_playing:
                hive_logger.debug("PlaybackMixin: Pausing playback.")
                self.render_engine.set_playing(False)
                self.btn_play.setIcon(qta.icon('mdi6.play', color='#e66b2c'))
                if not self.is_timeline_preview:
                    self.audio_mixer.pause() 
                
                if hasattr(global_signals, 'auto_scroll_requested'):
                    global_signals.auto_scroll_requested.emit()
            else:
                hive_logger.debug(f"PlaybackMixin: Starting playback from {self.playhead}.")
                if not self.is_timeline_preview and self.playhead >= self.duration and self.duration > 0:
                    self.playhead_seek_requested.emit(0)
                
                self.playback_start_time = time.time()
                self.playback_start_playhead = self.playhead
                
                self.timeline_canvas.update() 
                self.render_engine.set_playing(True)
                self.btn_play.setIcon(qta.icon('mdi6.pause', color='#e66b2c'))
                if not self.is_timeline_preview:
                    self.audio_mixer.play()
                
            self.is_playing = not self.is_playing
            
            if hasattr(global_signals, 'playback_state_changed'):
                global_signals.playback_state_changed.emit(self.is_playing)

    def _on_play_step(self):
        """Internal callback for each frame tick, pulling the current time from the Audio Mixer."""
        # Poll the Master Clock (Audio Mixer)
        playhead_ms = self.audio_mixer.get_current_time_ms()
        new_pos = playhead_ms / 10.0
        
        self.timeline_canvas.set_time(self.playhead)
        
        if self.is_timeline_preview:
            if not hasattr(self, 'playback_start_time'):
                self.playback_start_time = time.time()
            elapsed = time.time() - self.playback_start_time
            duration_sec = getattr(self, 'preview_duration', 5000) / 1000.0
            if elapsed > duration_sec:
                self.playback_start_time = time.time()
                self.playhead = self.playback_start_playhead
            else:
                self.playhead = self.playback_start_playhead + (elapsed * 100.0)
                self._update_timecode_label(preview=False)
                self.render_engine.request_frame(int(self.playhead))
            return
        
        if new_pos >= self.duration and self.duration > 0:
            new_pos = self.duration
            if self.is_playing:
                self.toggle_play() 
            
        self.playhead = new_pos
        self.render_engine.request_frame(int(new_pos))
        self.playhead_seek_requested.emit(int(new_pos))        
        if hasattr(global_signals, 'playhead_moved'):
            global_signals.playhead_moved.emit(self.playhead)

    def step_forward(self):
        """Advances the playhead by one frame (approx 33ms at 30fps)."""
        if self.is_preview_mode and not self.is_timeline_preview:
            self.player.setPosition(min(self.preview_duration, self.player.position() + 1000))
        else:
            self.playhead_seek_requested.emit(min(self.duration, self.playhead + 16))

    def step_backward(self):
        """Retreats the playhead by one frame."""
        if self.is_preview_mode and not self.is_timeline_preview:
            self.player.setPosition(max(0, self.player.position() - 1000))
        else:
            self.playhead_seek_requested.emit(max(0, self.playhead - 16))

    def update_duration(self, duration_logical):
        """Updates the total project duration in logical units."""
        self.duration = duration_logical
        if not self.is_preview_mode:
            self._update_timecode_label()

    def update_playhead(self, playhead_logical, user_initiated=False):
        """
        External entry point for moving the playhead.
        Called by the timeline when the user scrubs or a command is issued.
        """
        if user_initiated and self.is_playing:
            self.toggle_play()

        if self.is_preview_mode:
            hive_logger.debug("PlaybackMixin: Exiting preview mode due to manual seek.")
            self.is_preview_mode = False
            self.is_timeline_preview = False
            if hasattr(self.render_engine, 'set_preview_preset'):
                self.render_engine.set_preview_preset(None)
            self.player.stop()
            self.media_stack.setCurrentWidget(self.timeline_canvas)
            if self.is_playing:
                self.toggle_play()
            if hasattr(self, '_original_playhead'):
                delattr(self, '_original_playhead')
            
        self.playhead = playhead_logical
        self.timeline_canvas.set_time(self.playhead)
        self._update_timecode_label()
        
        if hasattr(global_signals, 'playhead_moved'):
            global_signals.playhead_moved.emit(self.playhead)
            if hasattr(self, 'playback_start_playhead'):
                expected_pos = self.playback_start_playhead + ((time.time() - self.playback_start_time) * 100.0)
                if abs(self.playhead - expected_pos) > 10: 
                    self.playback_start_time = time.time()
                    self.playback_start_playhead = self.playhead
        
        if not self.is_timeline_preview:
            self.render_engine.request_frame(self.playhead)
            
            if not self.is_playing:
                playhead_ms = int(self.playhead * 10)
                self.audio_mixer.seek(playhead_ms)

            if self.duration > 0:
                perc = int((self.playhead / self.duration) * 1000)
                perc = max(0, min(1000, perc))
                self.scrubber.blockSignals(True)
                self.scrubber.setValue(perc)
                self.scrubber.blockSignals(False)

    def _update_timecode_label(self, preview=False):
        """Formats and displays the current playhead and duration as SMPTE timecode."""
        def format_time(val, is_ms=False):
            if val < 0: val = 0
            
            if is_ms:
                total_seconds = int(val // 1000)
                frames = int(((val % 1000) / 1000.0) * 30)
            else:
                total_seconds = int(val // 100)
                frames = int((val % 100) / 100 * 30)
                
            hours = total_seconds // 3600
            mins = (total_seconds % 3600) // 60
            secs = total_seconds % 60
            
            return f"{hours:02d}:{mins:02d}:{secs:02d}:{frames:02d}"
            
        if preview:
            p_str = format_time(self.preview_position, is_ms=True)
            d_str = format_time(self.preview_duration, is_ms=True)
        else:
            p_str = format_time(self.playhead, is_ms=False)
            d_str = format_time(self.duration, is_ms=False)
            
        self.lbl_timecode.setText(f"{p_str} / {d_str}")

    def load_preview(self, media_data):
        """Loads a temporary media item or effect for previewing in the player."""
        self.current_preview_data = media_data
        if not media_data:
            hive_logger.debug("PlaybackMixin: Clearing preview.")
            if hasattr(self.render_engine, 'set_preview_preset'):
                self.render_engine.set_preview_preset(None)
            self.is_preview_mode = False
            self.is_timeline_preview = False
            if self.is_playing:
                self.toggle_play()
            return

        preset_type = media_data.get("type")
        hive_logger.info(f"PlaybackMixin: Loading preview for {preset_type}.")
        
        if preset_type in ["effect", "caption", "transition"]:
            if not self.is_preview_mode or not hasattr(self, '_original_playhead'):
                self._original_playhead = self.playhead
                
            self.is_preview_mode = True
            self.is_timeline_preview = True
            self.preview_duration = 5000 
            self.preview_position = 0
            self.preview_loops = 0
            
            if preset_type == "transition" and hasattr(self, "timeline_canvas") and getattr(self, "timeline_canvas", None):
                clip = None
                project = project_manager.current_project
                if project:
                    for t in project.tracks:
                        if t.track_id == "video_1":
                            for c in t.clips:
                                if c.start_time <= self._original_playhead * 10 < c.end_time:
                                    clip = c
                                    break
                if clip:
                    target_ms = max(clip.start_time, clip.end_time - 3000)
                    self.playhead = target_ms / 10.0
                    self.preview_duration = 4000
                else:
                    self.playhead = self._original_playhead
            else:
                self.playhead = self._original_playhead
            
            self.playback_start_time = time.time()
            self.playback_start_playhead = self.playhead
            
            if hasattr(self.render_engine, 'set_preview_preset'):
                self.render_engine.set_preview_preset(media_data, target_clip_id=clip.clip_id if 'clip' in locals() and clip else None)
                
            self.player.stop()
            self.media_stack.setCurrentWidget(self.timeline_canvas)
            
            if not self.is_playing:
                self.timeline_canvas.update()
                self.render_engine.set_playing(True)
                self.btn_play.setIcon(qta.icon('mdi6.pause', color='#e66b2c'))
                self.is_playing = True
            return
            
        if hasattr(self.render_engine, 'set_preview_preset'):
            self.render_engine.set_preview_preset(None)
            
        self.is_preview_mode = True 
        self.is_timeline_preview = False
        self.preview_duration = 0
        self.preview_position = 0
        self._first_load_done = False
        
        if self.is_playing:
            self.toggle_play()
        self.player.stop()

        self._apply_preview_source()

    def _apply_preview_source(self):
        """Internal: Logic for switching between video, audio, or image preview sources."""
        if not hasattr(self, 'current_preview_data') or not self.current_preview_data:
            return
            
        media_data = self.current_preview_data
        title = media_data.get("title", "")
        file_path = media_data.get("file_path", "")
        proxy_path = media_data.get("proxy_path", "")
        media_type = media_data.get("subtype", media_data.get("type", ""))

        current_res = self.combo_res.currentText()
        active_path = file_path
        
        if media_type == "video" and current_res != "Full":
            if not proxy_path or not os.path.exists(proxy_path):
                file_hash = hashlib.md5(file_path.encode()).hexdigest()
                inferred_proxy = os.path.join(str(app_config.proxy_cache_path), f"{file_hash}_proxy.mp4")
                if os.path.exists(inferred_proxy):
                    proxy_path = inferred_proxy
                    
            if proxy_path and os.path.exists(proxy_path):
                active_path = proxy_path

        if active_path and os.path.exists(active_path):
            if media_type == "video":
                self.media_stack.setCurrentWidget(self.video_widget)
                
                was_playing = self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
                current_pos = self.player.position()
                
                current_source = self.player.source().toLocalFile()
                if current_source != active_path:
                    self.player.setSource(QUrl.fromLocalFile(active_path))
                    if current_pos > 0:
                        self.player.setPosition(current_pos)
                        
                if was_playing or not self._first_load_done:
                    self.player.play()
                    
                self._first_load_done = True
                
            elif media_type == "audio":
                self.media_stack.setCurrentWidget(self.placeholder_lbl)
                self.placeholder_lbl.setText(f"Playing Audio:\n{title}")
                self.player.setSource(QUrl.fromLocalFile(active_path))
                self.player.play()
            elif media_type == "image":
                self.media_stack.setCurrentWidget(self.placeholder_lbl)
                pixmap = QPixmap(active_path)
                scaled = pixmap.scaled(self.video_container.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.placeholder_lbl.setPixmap(scaled)
                self._update_timecode_label(preview=True)
            else:
                self.media_stack.setCurrentWidget(self.placeholder_lbl)
                self.placeholder_lbl.setText(f"Preview:\n{title}")
                self._update_timecode_label(preview=True)
        else:
            self.media_stack.setCurrentWidget(self.placeholder_lbl)
            self.placeholder_lbl.clear()
            self.placeholder_lbl.setText(f"Preview Mode:\n{title}")
            self._update_timecode_label(preview=True)

    def _on_player_position_changed(self, position):
        """Syncs the slider with the QMediaPlayer position."""
        if self.is_preview_mode and not self.is_timeline_preview:
            self.preview_position = position
            self._update_timecode_label(preview=True)
            if self.preview_duration > 0:
                perc = int((self.preview_position / self.preview_duration) * 1000)
                self.scrubber.blockSignals(True)
                self.scrubber.setValue(max(0, min(1000, perc)))
                self.scrubber.blockSignals(False)

    def _on_player_duration_changed(self, duration):
        """Callback when the media duration is first detected."""
        if self.is_preview_mode and not self.is_timeline_preview and duration > 0:
            self.preview_duration = duration
            self._update_timecode_label(preview=True)

    def _on_player_state_changed(self, state):
        """Syncs UI buttons with the QMediaPlayer state."""
        if self.is_preview_mode and not self.is_timeline_preview:
            if state == QMediaPlayer.PlaybackState.PlayingState:
                self.btn_play.setIcon(qta.icon('mdi6.pause', color='#e66b2c'))
            else:
                self.btn_play.setIcon(qta.icon('mdi6.play', color='#e66b2c'))

    def _on_scrubber_moved(self, val):
        """Callback when the user manually drags the scrubber slider."""
        if self.is_preview_mode:
            if self.preview_duration > 0:
                new_pos = int((val / 1000.0) * self.preview_duration)
                if not self.is_timeline_preview:
                    self.player.setPosition(new_pos)
        else:
            if self.duration > 0:
                new_playhead = (val / 1000.0) * self.duration
                self.playhead_seek_requested.emit(int(new_playhead))
                self.render_engine.request_frame(int(new_playhead))

