# ui/player.py
import qtawesome as qta
import os
import time
from PySide6.QtWidgets import (QFrame, QVBoxLayout, QHBoxLayout, QPushButton, 
                               QLabel, QSlider, QWidget, QStackedWidget, QComboBox, QApplication)
from PySide6.QtCore import Qt, Signal, QTimer, QUrl
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtGui import QPainter

from core.signal_hub import global_signals
from core.project_manager import project_manager
from core.audio_mixer import audio_mixer
from core.logger import hive_logger

from ui.viewport import HiveViewport
from ui.player_components.mixins.playback import PlaybackMixin
from ui.player_components.mixins.rendering import RenderingMixin
from ui.player_components.mixins.player_sync import PlayerSyncMixin
from ui.player_components.mixins.overlay import OverlayMixin
from ui.player_components.mixins.interaction import InteractionMixin


class TimelinePreviewCanvas(InteractionMixin, OverlayMixin, HiveViewport):
    """
    High-performance custom drawing surface for RenderEngine frames.
    Combines OpenGL hardware acceleration with QPainter overlays for
    interactive clip manipulation (drag/scale/rotate).
    """
    
    transform_changed = Signal(str, str, object)  # clip_id, prop_name, value
    
    def __init__(self, parent=None):
        # Initialize mixins and OpenGL viewport
        super().__init__(parent=parent)
        
        self.current_time = 0.0  # Synced to playhead in logical units
        self.setStyleSheet("border-radius: 8px;")
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        
    def set_time(self, time_logical):
        """Updates internal time for frame-accurate coordinate mapping."""
        self.current_time = time_logical
        
    def set_frame(self, qimage):
        """Legacy support for direct QImage ingestion."""
        # Note: Optimized path uses update_frame() with raw buffers
        pass
    
    def paintGL(self):
        """
        The primary render loop.
        1. Renders the video frame via hardware-accelerated OpenGL.
        2. Renders interactive selection handles via QPainter.
        """
        painter = QPainter(self)
        painter.beginNativePainting()
        # Call HiveViewport.paintGL()
        super().paintGL()
        painter.endNativePainting()
        
        # Draw interactive handles from OverlayMixin
        self.paint_overlays(painter)
        
        painter.end()

    def set_selected_clip(self, clip_id):
        """Updates the current selection and triggers a redraw of handles."""
        self._selected_clip_id = clip_id
        self._show_handles = bool(clip_id)
        self.update()


class Player(PlaybackMixin, RenderingMixin, PlayerSyncMixin, QFrame):
    """
    The primary Player component for the HIVE Editor.
    Architected as a 'Rigging' class that coordinates specialized Mixins
    for playback control, OpenGL rendering, and project synchronization.
    """
    
    playhead_seek_requested = Signal(int)
    resolution_changed = Signal(str) 

    ASPECT_PRESETS = {
        "16:9": (16, 9),
        "9:16": (9, 16),
        "4:3": (4, 3),
        "1:1": (1, 1),
        "21:9": (21, 9),
        "4:5": (4, 5),
    }

    def __init__(self, parent=None):
        # Cooperative multiple inheritance initialization
        super().__init__(parent=parent)
        self.setObjectName("Panel")
        
        hive_logger.info("Player: Initializing Panel components...")
        self.audio_mixer = audio_mixer
        
        # Build UI layout
        self._setup_ui()
        
        # Initialize hardware abstractions
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        self.player.setVideoOutput(self.video_widget)
        
        # Connect signals across mixins and UI
        self._setup_connections()

        # Perform initial state sync if a project is already active
        if project_manager.current_project:
            self._sync_mixer_to_timeline()
            # Force first frame rendering after a short delay for decoder stabilization
            QTimer.singleShot(1000, lambda: self.update_playhead(0))

        # Ensure clean shutdown
        if QApplication.instance():
            QApplication.instance().aboutToQuit.connect(self._cleanup)

    def _setup_ui(self):
        """Constructs the visual hierarchy and styling of the Player Panel."""
        self.setStyleSheet("""
            QFrame#Panel {
                background-color: rgba(14, 14, 16, 0.90); 
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 12px;
            }
        """)
        
        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(15, 15, 15, 15)

        # 1. Canvas / Viewport Area
        self._canvas_area = QWidget()
        self._canvas_area.setStyleSheet("background: transparent;")
        self._canvas_area_layout = QVBoxLayout(self._canvas_area)
        self._canvas_area_layout.setContentsMargins(0, 0, 0, 0)
        self._canvas_area_layout.setAlignment(Qt.AlignCenter)

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
        
        self._canvas_area_layout.addWidget(self.video_container)
        self._main_layout.addWidget(self._canvas_area, stretch=1)

        # 2. Playback Controls Area
        controls_container = QWidget()
        controls_layout = QVBoxLayout(controls_container)
        controls_layout.setContentsMargins(0, 15, 0, 0)
        controls_layout.setSpacing(10)

        # Scrubber Slider
        self.scrubber = QSlider(Qt.Horizontal)
        self.scrubber.setRange(0, 1000)
        self.scrubber.setStyleSheet("""
            QSlider::groove:horizontal { border-radius: 2px; height: 4px; margin: 0px; background-color: #262626; }
            QSlider::handle:horizontal { background-color: #ffffff; border: none; height: 12px; width: 12px; margin: -4px 0; border-radius: 6px; }
            QSlider::handle:horizontal:hover { transform: scale(1.2); }
            QSlider::sub-page:horizontal { background-color: #e66b2c; border-radius: 2px; }
        """)
        controls_layout.addWidget(self.scrubber)

        bottom_row = QHBoxLayout()

        # Left: Aspect & Resolution Dropdowns
        left_layout = QHBoxLayout()
        left_layout.setSpacing(6)
        
        combo_style = """
            QComboBox {
                background-color: transparent; border: 1px solid rgba(255,255,255,0.1);
                border-radius: 4px; color: #808080; padding: 2px 8px; font-size: 10px;
                font-weight: bold;
            }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background-color: #1a1a1a; color: #d1d1d1; selection-background-color: #e66b2c;
            }
        """
        
        self.combo_aspect = QComboBox()
        self.combo_aspect.addItems(list(self.ASPECT_PRESETS.keys()))
        self.combo_aspect.setStyleSheet(combo_style)
        self.combo_aspect.setCursor(Qt.PointingHandCursor)
        self.combo_aspect.setToolTip("Player Preview Aspect Ratio")
        
        self.combo_res = QComboBox()
        self.combo_res.addItems(["Full", "1/2", "1/4", "1/8"])
        self.combo_res.setStyleSheet(combo_style)
        self.combo_res.setCursor(Qt.PointingHandCursor)
        self.combo_res.setToolTip("Render Quality (For heavy projects)")
        
        left_layout.addWidget(self.combo_aspect)
        left_layout.addWidget(self.combo_res)
        left_layout.addStretch(1)

        # Center: Playback Buttons
        center_layout = QHBoxLayout()
        self.btn_skip_back = QPushButton(qta.icon('mdi6.skip-previous-outline', color='#e66b2c'), "")
        self.btn_play = QPushButton(qta.icon('mdi6.play', color='#e66b2c'), "")
        self.btn_skip_fwd = QPushButton(qta.icon('mdi6.skip-next-outline', color='#e66b2c'), "")
        
        for btn in [self.btn_skip_back, self.btn_play, self.btn_skip_fwd]:
            btn.setStyleSheet("background: transparent; border: none; padding: 0 10px;")
            btn.setCursor(Qt.PointingHandCursor)
            center_layout.addWidget(btn)

        # Right: Timecode Display
        right_layout = QHBoxLayout()
        right_layout.addStretch(1)
        self.lbl_timecode = QLabel("00:00:00:00 / 00:00:00:00")
        self.lbl_timecode.setStyleSheet("color: #d1d1d1; font-family: monospace; font-size: 12px; font-weight: bold;")
        right_layout.addWidget(self.lbl_timecode)

        bottom_row.addLayout(left_layout, 1)   
        bottom_row.addLayout(center_layout, 0) 
        bottom_row.addLayout(right_layout, 1)  

        controls_layout.addLayout(bottom_row)
        self._main_layout.addWidget(controls_container)

    def _setup_connections(self):
        """Wiring for UI interactions and global project signals."""
        self.timeline_canvas.frameSwapped.connect(self._on_play_step)
        self.timeline_canvas.transform_changed.connect(self._on_canvas_transform)
        
        self.scrubber.valueChanged.connect(self._on_scrubber_moved)
        self.combo_aspect.currentTextChanged.connect(self._on_aspect_changed)
        self.combo_res.currentTextChanged.connect(self._on_res_changed)
        
        self.btn_play.clicked.connect(self.toggle_play)
        self.btn_skip_fwd.clicked.connect(self.step_forward)
        self.btn_skip_back.clicked.connect(self.step_backward)
        
        self.player.positionChanged.connect(self._on_player_position_changed)
        self.player.durationChanged.connect(self._on_player_duration_changed)
        self.player.playbackStateChanged.connect(self._on_player_state_changed)
        
        global_signals.project_loaded.connect(self.reset_player)
        global_signals.clip_selected.connect(self._on_clip_selected_for_preview)
        global_signals.clip_deselected.connect(self._on_clip_deselected_for_preview)
        global_signals.project_resolution_changed.connect(self._on_project_resolution_changed)
        global_signals.timeline_updated.connect(self._sync_mixer_to_timeline)

        if hasattr(global_signals, 'clip_transform_changed'):
            global_signals.clip_transform_changed.connect(self._on_property_changed_rerender)
        if hasattr(global_signals, 'force_refresh'):
            global_signals.force_refresh.connect(self._force_refresh_render)

    def _cleanup(self):
        """Ensures all hardware resources and worker threads are released on application close."""
        hive_logger.info("Player: Cleaning up resources.")
        self.is_playing = False
        
        if hasattr(self, 'timeline_canvas'):
            self.timeline_canvas.cleanupGL()
            
        if hasattr(self, 'render_engine'):
            self.render_engine.stop()
            self.render_engine.wait(300) 
            
        if hasattr(self, 'player') and self.player:
            self.player.stop()
            self.player.setVideoOutput(None)
            self.player.setAudioOutput(None)
            self.player.deleteLater()
            
        if hasattr(self, 'audio_mixer'):
            self.audio_mixer.close()


# Alias for backward compatibility
PlayerPanel = Player
