# ui/player.py

import qtawesome as qta
import os
import time
import hashlib
import math
from PySide6.QtWidgets import (QFrame, QVBoxLayout, QHBoxLayout, QPushButton, 
                               QLabel, QSlider, QWidget, QStackedWidget, QComboBox, QApplication)
from PySide6.QtCore import Qt, Signal, QTimer, QUrl, QRect
from PySide6.QtGui import QPixmap, QPainter
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget

from core.signal_hub import global_signals
from core.project_manager import project_manager
from core.render_engine import RenderEngine
from core.app_config import app_config


class TimelinePreviewCanvas(QWidget):
    """Custom drawing surface for the RenderEngine frames"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_frame = None
        self.setStyleSheet("background-color: #000000; border-radius: 8px;")
        
    def set_frame(self, qimage):
        self.current_frame = qimage
        self.update() 
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.black)
        
        if self.current_frame and not self.current_frame.isNull():
            # Optimization: Mathematical scaling avoids creating massive QImage clones in RAM 30 times a second
            cw, ch = self.width(), self.height()
            fw, fh = self.current_frame.width(), self.current_frame.height()
            
            if fw > 0 and fh > 0:
                ratio = min(cw / fw, ch / fh)
                nw, nh = int(fw * ratio), int(fh * ratio)
                x, y = (cw - nw) // 2, (ch - nh) // 2
                
                painter.setRenderHint(QPainter.SmoothPixmapTransform, False) # Fast render for playback
                painter.drawImage(QRect(x, y, nw, nh), self.current_frame)


class PlayerPanel(QFrame):
    
    playhead_seek_requested = Signal(int)
    resolution_changed = Signal(str) 

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Panel")
        
        self.duration = 0
        self.playhead = 0
        self.is_playing = False
        
        self.is_preview_mode = False
        self.preview_duration = 0
        self.preview_position = 0

        # Multi-Track Audio Engine Data
        self.audio_players = {}

        self.play_timer = QTimer(self)
        self.play_timer.setTimerType(Qt.PreciseTimer) # Optimization: Forces OS high-precision timing for buttery smooth framerates
        self.play_timer.timeout.connect(self._on_play_step)

        self.render_engine = RenderEngine()
        self.render_engine.frame_ready.connect(self._on_timeline_frame_received)
        self.render_engine.start()

        self.setStyleSheet("""
            QFrame#Panel {
                background-color: rgba(14, 14, 16, 0.90); 
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 12px;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)

        self.video_container = QFrame()
        self.video_container.setStyleSheet("""
            QFrame {
                background-color: #000000;
                border-radius: 8px;
                border: 1px solid #262626;
            }
        """)
        video_layout = QVBoxLayout(self.video_container)
        video_layout.setContentsMargins(0, 0, 0, 0)
        
        self.media_stack = QStackedWidget()
        video_layout.addWidget(self.media_stack)
        
        self.placeholder_lbl = QLabel("No Media Selected")
        self.placeholder_lbl.setAlignment(Qt.AlignCenter)
        self.placeholder_lbl.setStyleSheet("color: #555555; font-size: 16px; font-weight: bold; background: transparent;")
        
        self.video_widget = QVideoWidget()
        self.timeline_canvas = TimelinePreviewCanvas()
        
        self.media_stack.addWidget(self.placeholder_lbl)
        self.media_stack.addWidget(self.video_widget)
        self.media_stack.addWidget(self.timeline_canvas) 
        
        self.media_stack.setCurrentWidget(self.timeline_canvas)
        
        layout.addWidget(self.video_container, stretch=1)

        controls_container = QWidget()
        controls_layout = QVBoxLayout(controls_container)
        controls_layout.setContentsMargins(0, 15, 0, 0)
        controls_layout.setSpacing(10)

        self.scrubber = QSlider(Qt.Horizontal)
        self.scrubber.setRange(0, 1000)
        self.scrubber.setStyleSheet("""
            QSlider::groove:horizontal { border-radius: 2px; height: 4px; margin: 0px; background-color: #262626; }
            QSlider::handle:horizontal { background-color: #ffffff; border: none; height: 12px; width: 12px; margin: -4px 0; border-radius: 6px; }
            QSlider::handle:horizontal:hover { transform: scale(1.2); }
            QSlider::sub-page:horizontal { background-color: #e66b2c; border-radius: 2px; }
        """)
        self.scrubber.valueChanged.connect(self._on_scrubber_moved)
        controls_layout.addWidget(self.scrubber)

        bottom_row = QHBoxLayout()

        left_layout = QHBoxLayout()
        self.combo_res = QComboBox()
        self.combo_res.addItems(["Full", "1/2", "1/4", "1/8"])
        self.combo_res.setStyleSheet("""
            QComboBox {
                background-color: transparent; border: 1px solid rgba(255,255,255,0.1);
                border-radius: 4px; color: #808080; padding: 2px 8px; font-size: 10px;
                font-weight: bold;
            }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background-color: #1a1a1a; color: #d1d1d1; selection-background-color: #e66b2c;
            }
        """)
        self.combo_res.setCursor(Qt.PointingHandCursor)
        self.combo_res.setToolTip("Timeline Tick Resolution (For heavy projects)")
        self.combo_res.currentTextChanged.connect(self._on_res_changed)
        
        left_layout.addWidget(self.combo_res)
        left_layout.addStretch(1)

        center_layout = QHBoxLayout()
        self.btn_skip_back = QPushButton(qta.icon('mdi6.skip-previous-outline', color='#e66b2c'), "")
        self.btn_play = QPushButton(qta.icon('mdi6.play', color='#e66b2c'), "")
        self.btn_skip_fwd = QPushButton(qta.icon('mdi6.skip-next-outline', color='#e66b2c'), "")
        
        for btn in [self.btn_skip_back, self.btn_play, self.btn_skip_fwd]:
            btn.setStyleSheet("background: transparent; border: none; padding: 0 10px;")
            btn.setCursor(Qt.PointingHandCursor)
            center_layout.addWidget(btn)

        self.btn_play.clicked.connect(self.toggle_play)
        self.btn_skip_fwd.clicked.connect(self.step_forward)
        self.btn_skip_back.clicked.connect(self.step_backward)

        right_layout = QHBoxLayout()
        right_layout.addStretch(1)
        self.lbl_timecode = QLabel("00:00:00:00 / 00:00:00:00")
        self.lbl_timecode.setStyleSheet("color: #d1d1d1; font-family: monospace; font-size: 12px; font-weight: bold;")
        right_layout.addWidget(self.lbl_timecode)

        bottom_row.addLayout(left_layout, 1)   
        bottom_row.addLayout(center_layout, 0) 
        bottom_row.addLayout(right_layout, 1)  

        controls_layout.addLayout(bottom_row)
        layout.addWidget(controls_container)
        
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        self.player.setVideoOutput(self.video_widget)
        
        self.player.positionChanged.connect(self._on_player_position_changed)
        self.player.durationChanged.connect(self._on_player_duration_changed)
        self.player.playbackStateChanged.connect(self._on_player_state_changed)
        
        if QApplication.instance():
            QApplication.instance().aboutToQuit.connect(self._cleanup)

    def _on_timeline_frame_received(self, frame):
        self.timeline_canvas.set_frame(frame)

    def _on_res_changed(self, res_text):
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
        
        if self.is_preview_mode:
            self._apply_preview_source()

    def load_preview(self, media_data):
        self.current_preview_data = media_data
        self.is_preview_mode = True 
        self.preview_duration = 0
        self.preview_position = 0
        self._first_load_done = False
        
        if self.is_playing:
            self.toggle_play()
        self.player.stop()

        self._apply_preview_source()

    def _apply_preview_source(self):
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
        if self.is_preview_mode:
            self.preview_position = position
            self._update_timecode_label(preview=True)
            if self.preview_duration > 0:
                perc = int((self.preview_position / self.preview_duration) * 1000)
                self.scrubber.blockSignals(True)
                self.scrubber.setValue(max(0, min(1000, perc)))
                self.scrubber.blockSignals(False)

    def _on_player_duration_changed(self, duration):
        if self.is_preview_mode and duration > 0:
            self.preview_duration = duration
            self._update_timecode_label(preview=True)

    def _on_player_state_changed(self, state):
        if self.is_preview_mode:
            if state == QMediaPlayer.PlaybackState.PlayingState:
                self.btn_play.setIcon(qta.icon('mdi6.pause', color='#e66b2c'))
            else:
                self.btn_play.setIcon(qta.icon('mdi6.play', color='#e66b2c'))

    # ================== AUDIO MIXING ENGINE ==================
    def _sync_timeline_audio(self, current_ms):
        """Dynamically spins up QMediaPlayers to playback intersecting audio for the entire timeline."""
        project = project_manager.current_project
        if not project: return
        
        active_clip_ids = set()
        
        for track in project.tracks:
            if track.is_muted or track.is_hidden: continue
            for clip in track.clips:
                if clip.clip_type in ["video", "audio"] and clip.file_path:
                    # Is this clip currently intersecting the playhead?
                    if clip.start_time <= current_ms < clip.end_time:
                        active_clip_ids.add(clip.clip_id)
                        
                        trim_in_ms = getattr(clip, 'trim_in', 0)
                        if isinstance(clip.applied_effects, dict):
                            fx_source_in = clip.applied_effects.get("source_in", 0) * 10
                            trim_in_ms = max(trim_in_ms, fx_source_in)
                            
                        local_ms = (current_ms - clip.start_time) + trim_in_ms
                        
                        # Initialize a player if it doesn't exist
                        if clip.clip_id not in self.audio_players:
                            player = QMediaPlayer()
                            audio_output = QAudioOutput()
                            
                            vol_db = clip.applied_effects.get("Volume", 0) if isinstance(clip.applied_effects, dict) else 0
                            linear_vol = max(0.0, min(1.0, math.pow(10, vol_db / 20.0)))
                            audio_output.setVolume(linear_vol)
                            
                            player.setAudioOutput(audio_output)
                            player.setSource(QUrl.fromLocalFile(clip.file_path))
                            player.setPosition(local_ms)
                            
                            if self.is_playing:
                                player.play()
                                
                            self.audio_players[clip.clip_id] = {'player': player, 'output': audio_output}
                        else:
                            # Sync existing player
                            player = self.audio_players[clip.clip_id]['player']
                            if self.is_playing and player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
                                player.play()
                            elif not self.is_playing and player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                                player.pause()
                                
                            # Hard seek if it falls out of sync
                            if abs(player.position() - local_ms) > 150:
                                player.setPosition(local_ms)
                                
        # Cleanup inactive players that have passed out of bounds
        stale_ids = set(self.audio_players.keys()) - active_clip_ids
        for clip_id in stale_ids:
            self.audio_players[clip_id]['player'].stop()
            self.audio_players[clip_id]['player'].deleteLater()
            self.audio_players[clip_id]['output'].deleteLater()
            del self.audio_players[clip_id]

    def _stop_all_timeline_audio(self):
        """Silences the audio engine safely when paused."""
        for clip_id, data in self.audio_players.items():
            data['player'].pause()

    def _on_play_step(self):
        if not hasattr(self, 'playback_start_time'):
            self.playback_start_time = time.time()
            self.playback_start_playhead = self.playhead
            
        elapsed = time.time() - self.playback_start_time
        
        new_pos = self.playback_start_playhead + (elapsed * 100.0)
        
        if new_pos >= self.duration and self.duration > 0:
            new_pos = self.duration
            self.toggle_play() 
            
        # Optimization: Request frame immediately bypassing UI signal delays
        self.render_engine.request_frame(int(new_pos))
        self.playhead_seek_requested.emit(int(new_pos))
        self._sync_timeline_audio(int(new_pos))

    def toggle_play(self):
        if self.is_preview_mode:
            if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                self.player.pause()
            else:
                self.player.play()
        else:
            if self.media_stack.currentWidget() != self.timeline_canvas:
                self.media_stack.setCurrentWidget(self.timeline_canvas)

            if self.is_playing:
                self.play_timer.stop()
                self.render_engine.set_playing(False)
                self.btn_play.setIcon(qta.icon('mdi6.play', color='#e66b2c'))
                self._stop_all_timeline_audio()
            else:
                if self.playhead >= self.duration and self.duration > 0:
                    self.playhead_seek_requested.emit(0)
                
                self.playback_start_time = time.time()
                self.playback_start_playhead = self.playhead
                
                self.play_timer.start(33) 
                self.render_engine.set_playing(True)
                self.btn_play.setIcon(qta.icon('mdi6.pause', color='#e66b2c'))
                self._sync_timeline_audio(int(self.playhead))
                
            self.is_playing = not self.is_playing

    def step_forward(self):
        if self.is_preview_mode:
            self.player.setPosition(min(self.preview_duration, self.player.position() + 1000))
        else:
            self.playhead_seek_requested.emit(min(self.duration, self.playhead + 16))

    def step_backward(self):
        if self.is_preview_mode:
            self.player.setPosition(max(0, self.player.position() - 1000))
        else:
            self.playhead_seek_requested.emit(max(0, self.playhead - 16))

    def _on_scrubber_moved(self, val):
        if self.is_preview_mode:
            if self.preview_duration > 0:
                new_pos = int((val / 1000.0) * self.preview_duration)
                self.player.setPosition(new_pos)
        else:
            if self.duration > 0:
                new_playhead = (val / 1000.0) * self.duration
                self.playhead_seek_requested.emit(int(new_playhead))
                self.render_engine.request_frame(int(new_playhead))

    def update_duration(self, duration_logical):
        self.duration = duration_logical
        if not self.is_preview_mode:
            self._update_timecode_label()
        
    def update_playhead(self, playhead_logical):
        if self.is_preview_mode:
            self.is_preview_mode = False
            self.player.stop()
            self.media_stack.setCurrentWidget(self.timeline_canvas)
            self.btn_play.setIcon(qta.icon('mdi6.play', color='#e66b2c'))
            
        self.playhead = playhead_logical
        self._update_timecode_label()
        
        if self.is_playing:
            if hasattr(self, 'playback_start_playhead'):
                expected_pos = self.playback_start_playhead + ((time.time() - self.playback_start_time) * 100.0)
                if abs(self.playhead - expected_pos) > 10: 
                    self.playback_start_time = time.time()
                    self.playback_start_playhead = self.playhead
        
        self.render_engine.request_frame(self.playhead)
        
        if not self.is_playing:
            self._sync_timeline_audio(int(self.playhead))
            self._stop_all_timeline_audio()
        
        if self.duration > 0:
            perc = int((self.playhead / self.duration) * 1000)
            perc = max(0, min(1000, perc))
            self.scrubber.blockSignals(True)
            self.scrubber.setValue(perc)
            self.scrubber.blockSignals(False)

    def _update_timecode_label(self, preview=False):
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

    def _cleanup(self):
        self.is_playing = False
        self.play_timer.stop()
        
        if hasattr(self, 'render_engine'):
            self.render_engine.stop()
            self.render_engine.wait(300) 
            
        if hasattr(self, 'player') and self.player:
            self.player.stop()
            self.player.setVideoOutput(None)
            self.player.setAudioOutput(None)
            self.player.deleteLater()
            
        for clip_id, data in self.audio_players.items():
            data['player'].stop()
            data['player'].deleteLater()
            data['output'].deleteLater()
        self.audio_players.clear()