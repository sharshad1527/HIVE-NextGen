import pytest
from PySide6.QtWidgets import QApplication
from ui.timeline.timeline_canvas import TracksCanvas
import os

@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app

def test_trackscanvas_restructuring_interface(qapp):
    """Verifies that the restructured TracksCanvas maintains its public interface."""
    canvas = TracksCanvas()
    
    # Core state
    assert hasattr(canvas, 'zoom_factor')
    assert hasattr(canvas, 'items')
    assert hasattr(canvas, 'track_defs')
    
    # Rendering methods
    assert hasattr(canvas, 'paintEvent')
    assert hasattr(canvas, 'draw_keyframes')
    
    # Interaction methods
    assert hasattr(canvas, 'mousePressEvent')
    assert hasattr(canvas, 'mouseMoveEvent')
    assert hasattr(canvas, 'mouseReleaseEvent')
    assert hasattr(canvas, 'wheelEvent')
    
    # Operation methods
    assert hasattr(canvas, 'split_at_playhead')
    assert hasattr(canvas, 'delete_selected_item')
    assert hasattr(canvas, 'undo')
    assert hasattr(canvas, 'redo')
    
    # DataSync methods
    assert hasattr(canvas, 'load_from_project')
    assert hasattr(canvas, 'sync_to_project')
    
    # DragDrop methods
    assert hasattr(canvas, 'dragEnterEvent')
    assert hasattr(canvas, 'dropEvent')

def test_trackscanvas_state_initialization(qapp):
    """Verifies that the _init_base_state correctly sets up the canvas."""
    canvas = TracksCanvas()
    assert canvas.zoom_factor == 1.0
    assert canvas.active_tool == "pointer"
    assert isinstance(canvas.items, list)
    assert isinstance(canvas.selected_ids, set)

if __name__ == "__main__":
    pytest.main([__file__])
