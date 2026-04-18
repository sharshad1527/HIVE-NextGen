# ui/player.py
import qtawesome as qta
import os
from PySide6.QtWidgets import (QFrame, QVBoxLayout, QHBoxLayout, QPushButton, 
                               QLabel, QSlider, QWidget, QStackedWidget, QComboBox, QApplication)
from PySide6.QtCore import Qt, Signal, QTimer, QUrl
from PySide6.QtGui import QPixmap
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget

from core.signal_hub import global_signals
from core.project_manager import project_manager

class PlayerPanel(QFrame):
    
    playhead_seek_requested = Signal(int)
    resolution_changed = Signal(str) # Universal signal to adjust playback rendering resolution

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Panel")
        
        self.duration = 0
        self.playhead = 0
        self.is_playing = False
        
        # State indicators for Media Preview
        self.is_preview_mode = False
        self.preview_duration = 0
        self.preview_position = 0

        self.play_timer = QTimer(self)
        self.play_timer.setInterval(33) # Default to Full Resolution (~30fps)
        self.play_timer.timeout.connect(self._on_play_step)

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
        
        # Use QStackedWidget to seamlessly switch between Video playback and Image/Text placeholders
        self.media_stack = QStackedWidget()
        video_layout.addWidget(self.media_stack)
        
        self.placeholder_lbl = QLabel("No Media Selected")
        self.placeholder_lbl.setAlignment(Qt.AlignCenter)
        self.placeholder_lbl.setStyleSheet("color: #555555; font-size: 16px; font-weight: bold; background: transparent;")
        
        self.video_widget = QVideoWidget()
        
        self.media_stack.addWidget(self.placeholder_lbl)
        self.media_stack.addWidget(self.video_widget)
        self.media_stack.setCurrentWidget(self.placeholder_lbl)
        
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

        # Bottom Row - Using a 3-part layout to perfectly center the buttons
        bottom_row = QHBoxLayout()

        # 1. Left Layout (Resolution Control)
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

        # 2. Center Layout (Playback Controls)
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

        # 3. Right Layout (Timecode)
        right_layout = QHBoxLayout()
        right_layout.addStretch(1)
        self.lbl_timecode = QLabel("00:00:00:00 / 00:00:00:00")
        self.lbl_timecode.setStyleSheet("color: #d1d1d1; font-family: monospace; font-size: 12px; font-weight: bold;")
        right_layout.addWidget(self.lbl_timecode)

        # Combine perfectly
        bottom_row.addLayout(left_layout, 1)   # Push from left
        bottom_row.addLayout(center_layout, 0) # Exact center
        bottom_row.addLayout(right_layout, 1)  # Push from right

        controls_layout.addLayout(bottom_row)
        layout.addWidget(controls_container)
        
        # --- Real Multimedia Player Backend Setup ---
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        self.player.setVideoOutput(self.video_widget)
        
        self.player.positionChanged.connect(self._on_player_position_changed)
        self.player.durationChanged.connect(self._on_player_duration_changed)
        self.player.playbackStateChanged.connect(self._on_player_state_changed)
        
        # --- Clean up resources when app closes to prevent ghost audio ---
        if QApplication.instance():
            QApplication.instance().aboutToQuit.connect(self._cleanup)

    def _on_res_changed(self, res_text):
        """Reduces UI update frequency based on resolution choice to save CPU usage"""
        if res_text == "Full":
            self.play_timer.setInterval(33)   # ~30 fps update
        elif res_text == "1/2":
            self.play_timer.setInterval(66)   # ~15 fps update (Less CPU)
        elif res_text == "1/4":
            self.play_timer.setInterval(133)  # ~7.5 fps update (Low End)
        elif res_text == "1/8":
            self.play_timer.setInterval(266)  # ~3.75 fps update (Potato PC)
            
        self.resolution_changed.emit(res_text)
        
        # FIX: Trigger real-time dynamic swap between 4k and Proxy!
        if self.is_preview_mode:
            self._apply_preview_source()

    def load_preview(self, media_data):
        """Called when Workspace Panel items are clicked. Prepares for playback."""
        self.current_preview_data = media_data
        self.is_preview_mode = True 
        self.preview_duration = 0
        self.preview_position = 0
        self._first_load_done = False
        
        # Ensure dummy timeline timer is paused when checking out media files
        if self.is_playing:
            self.toggle_play()
        self.player.stop()

        self._apply_preview_source()

    def _apply_preview_source(self):
        """Checks the Resolution dropdown to play either the Original or the Proxy file."""
        if not hasattr(self, 'current_preview_data') or not self.current_preview_data:
            return
            
        media_data = self.current_preview_data
        title = media_data.get("title", "")
        file_path = media_data.get("file_path", "")
        proxy_path = media_data.get("proxy_path", "")
        media_type = media_data.get("subtype", media_data.get("type", ""))

        current_res = self.combo_res.currentText()
        active_path = file_path
        
        # PROXY SWITCHING LOGIC: Switch to the 360p lightweight proxy if user changed the dropdown
        if media_type == "video" and current_res != "Full" and proxy_path and os.path.exists(proxy_path):
            active_path = proxy_path
            print(f"PLAYER: Dynamically swapped to 360p PROXY for smooth playback.")

        if active_path and os.path.exists(active_path):
            if media_type == "video":
                self.media_stack.setCurrentWidget(self.video_widget)
                
                # Remember state to seamlessly swap resolution without interrupting the user
                was_playing = self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
                current_pos = self.player.position()
                
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
        # Media duration can occasionally return -1 during loading streams
        if self.is_preview_mode and duration > 0:
            self.preview_duration = duration
            self._update_timecode_label(preview=True)

    def _on_player_state_changed(self, state):
        if self.is_preview_mode:
            if state == QMediaPlayer.PlaybackState.PlayingState:
                self.btn_play.setIcon(qta.icon('mdi6.pause', color='#e66b2c'))
            else:
                self.btn_play.setIcon(qta.icon('mdi6.play', color='#e66b2c'))

    def _on_play_step(self):
        # Dynamically scale the playhead advance based on the performance interval
        interval_ms = self.play_timer.interval()
        if interval_ms <= 0: interval_ms = 33
            
        step_units = interval_ms / 10.0 # 10 logical units = 100ms
        
        new_pos = self.playhead + step_units 
        if new_pos >= self.duration and self.duration > 0:
            new_pos = self.duration
            self.toggle_play() 
            
        self.playhead_seek_requested.emit(int(new_pos))

    def toggle_play(self):
        if self.is_preview_mode:
            if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                self.player.pause()
            else:
                self.player.play()
        else:
            if self.is_playing:
                self.play_timer.stop()
                self.btn_play.setIcon(qta.icon('mdi6.play', color='#e66b2c'))
            else:
                if self.playhead >= self.duration and self.duration > 0:
                    self.playhead_seek_requested.emit(0)
                self.play_timer.start() 
                self.btn_play.setIcon(qta.icon('mdi6.pause', color='#e66b2c'))
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

    def update_duration(self, duration_logical):
        self.duration = duration_logical
        if not self.is_preview_mode:
            self._update_timecode_label()
        
    def update_playhead(self, playhead_logical):
        # Override preview mode securely if the timeline is interacted with
        if self.is_preview_mode:
            self.is_preview_mode = False
            self.player.stop()
            self.media_stack.setCurrentWidget(self.placeholder_lbl)
            self.placeholder_lbl.clear()
            self.placeholder_lbl.setText("Timeline Viewer")
            self.btn_play.setIcon(qta.icon('mdi6.play', color='#e66b2c'))
            
        self.playhead = playhead_logical
        self._update_timecode_label()
        
        if self.duration > 0:
            perc = int((self.playhead / self.duration) * 1000)
            perc = max(0, min(1000, perc))
            self.scrubber.blockSignals(True)
            self.scrubber.setValue(perc)
            self.scrubber.blockSignals(False)

    def _update_timecode_label(self, preview=False):
        # Helper to format accurately into HH:MM:SS:FF formats
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
        """Ensures the media stops playing and resources are freed when the app closes."""
        self.is_playing = False
        self.play_timer.stop()
        if hasattr(self, 'player') and self.player:
            self.player.stop()
            self.player.setSource(QUrl())