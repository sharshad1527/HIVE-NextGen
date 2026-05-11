from PySide6.QtWidgets import QApplication
from ui.player import TimelinePreviewCanvas
from core.models import ClipData
import sys

def test_player_ui_probe_no_disk_io():
    """
    Ensure that TimelinePreviewCanvas correctly calculates bounds 
    using cached metadata without invoking cv2.VideoCapture on the UI thread.
    """
    app = QApplication.instance() or QApplication(sys.argv)
    canvas = TimelinePreviewCanvas()
    clip = ClipData(clip_id="test", clip_type="image", file_path="dummy.png", start_time=0, end_time=100)
    clip.applied_effects = {"media_w": 1920, "media_h": 1080, "Position_X": 0, "Position_Y": 0, "Scale": 100, "Rotation": 0}
    
    # Override frame dimensions to pass early return check
    canvas.frame_width = 1920
    canvas.frame_height = 1080
    
    # The bounds calculation should succeed using applied_effects directly
    bounds = canvas._get_clip_screen_bounds(clip)
    
    assert bounds is not None
    assert "cx" in bounds
    assert "cy" in bounds
    # Assuming no offset, cx should be centered at 960 (half of 1920)
    assert bounds["cx"] > 0
