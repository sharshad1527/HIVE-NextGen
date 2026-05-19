from PySide6.QtWidgets import QApplication
from ui.player import Player, TimelinePreviewCanvas
import sys
import pytest

def test_player_inheritance_and_api():
    """
    Verify that the refactored Player class has all expected mixin methods and state.
    """
    app = QApplication.instance() or QApplication(sys.argv)
    player = Player()
    
    # Check PlaybackMixin methods
    assert hasattr(player, 'toggle_play')
    assert hasattr(player, 'update_playhead')
    
    # Check RenderingMixin methods
    assert hasattr(player, '_on_timeline_frame_received')
    assert hasattr(player, 'render_engine')
    
    # Check PlayerSyncMixin methods
    assert hasattr(player, 'reset_player')
    
    # Check state initialization
    assert player.is_playing == False
    assert player.playhead == 0
    assert player.duration == 0

def test_canvas_inheritance_and_api():
    """
    Verify that the refactored TimelinePreviewCanvas has all expected mixin methods and state.
    """
    app = QApplication.instance() or QApplication(sys.argv)
    canvas = TimelinePreviewCanvas()
    
    # Check InteractionMixin methods
    assert hasattr(canvas, 'mousePressEvent')
    assert hasattr(canvas, '_update_canvas_mapping')
    
    # Check OverlayMixin methods
    assert hasattr(canvas, 'paint_overlays')
    assert hasattr(canvas, '_get_clip_screen_bounds')
    
    # Check state initialization
    assert canvas._dragging == False
    assert canvas._show_handles == False
