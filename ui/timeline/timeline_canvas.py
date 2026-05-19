# ui/timeline/timeline_canvas.py

import random
import copy
import json
import os
import hashlib
import uuid

from PySide6.QtCore import Qt, QRect, QPoint, Signal, QTimer, QThreadPool, QCoreApplication
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QPainterPath, QCursor, QPixmap, QPolygon
from PySide6.QtWidgets import QWidget

from core.signal_hub import global_signals
from core.models import ProjectData, TrackData, ClipData
from core.logger import LoggerManager

try:
    from core.models import Easing
except ImportError:
    Easing = None

from core.project_manager import project_manager
from core.app_config import app_config
from core.media_manager import media_manager
from .timeline_workers import PersistentThumbnailWorker

# Import the new components and mixins
from ui.timeline.canvas.keyframe_popup import KeyframePopup
from ui.timeline.canvas.mixins.base import BaseMixin
from ui.timeline.canvas.mixins.rendering import RenderingMixin
from ui.timeline.canvas.mixins.interaction import InteractionMixin
from ui.timeline.canvas.mixins.operations import OperationsMixin
from ui.timeline.canvas.mixins.data_sync import DataSyncMixin
from ui.timeline.canvas.mixins.drag_drop import DragDropMixin
from ui.timeline.canvas.mixins.assets import AssetsMixin

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

# Initialize HIVE Logger
logger = LoggerManager().logger

class TracksCanvas(BaseMixin, RenderingMixin, InteractionMixin, 
                   OperationsMixin, DataSyncMixin, DragDropMixin, AssetsMixin, QWidget):
    """
    Custom painted widget that draws the actual timeline tracks, ruler, and playhead.
    
    Architecture:
    This class uses a Mixin-based design to separate responsibilities while sharing a unified state.
    - BaseMixin: Shared state and undo/redo logic.
    - RenderingMixin: QPainter logic and asset management.
    - InteractionMixin: Input handling (mouse/wheel).
    - OperationsMixin: Clip editing (split/trim).
    - DataSyncMixin: Backend project synchronization.
    - DragDropMixin: External file/asset ingestion.
    - AssetsMixin: Resource cleanup.
    """
    
    item_clicked = Signal(str, str, dict)
    scroll_requested = Signal(int)
    v_scroll_requested = Signal(int)
    zoom_requested = Signal(int)
    tracks_changed = Signal()
    v1_duration_changed = Signal(float)
    playhead_changed = Signal(float, bool)
    state_changed = Signal() 

    def __init__(self, parent=None):
        super().__init__(parent)
        logger.info("TimelineCanvas: Initializing modular architecture...")
        
        self.setAcceptDrops(True)
        
        # Initialize state from BaseMixin
        self._init_base_state()
        
        # UI & Interaction State from original __init__
        self.setMouseTracking(True)
        
        # Threading setup (kept in main class for central management)
        self.thread_pool = QThreadPool.globalInstance()
        self.thread_pool.setMaxThreadCount(min(4, self.thread_pool.maxThreadCount()))
        
        app = QCoreApplication.instance()
        if app:
            app.aboutToQuit.connect(self._cleanup_threads)
        
        # Signals initialization
        global_signals.waveform_ready.connect(self._on_waveform_ready)
        if hasattr(global_signals, 'clip_transform_changed'):
            global_signals.clip_transform_changed.connect(self._on_external_transform)

        # Timer connection (moved from mixin for safety)
        self.auto_scroll_timer.timeout.connect(self._do_auto_scroll)

        # Initial Layout/Logic pass
        self._cleanup_empty_tracks()
        self._apply_magnetic_v1()
        self.update_max_width()
        self._recalc_height() 
        
        logger.info(f"TimelineCanvas: Ready. CV2_AVAILABLE={CV2_AVAILABLE}")
        
    def _cleanup_threads(self):
        """Clears pending thumbnail loads and waits for threads to finish."""
        logger.info("TimelineCanvas: Cleaning up background threads...")
        self.thread_pool.clear()
        self.thread_pool.waitForDone(1000)
