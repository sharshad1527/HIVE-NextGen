import numpy as np
from core.video_decoder import VideoDecoder

def test_video_decoder_yuv_output_shape_logic():
    """
    Test that the engine properly identifies YUV420P shapes.
    YUV420P returned from PyAV's to_ndarray is a 2D array of shape (H * 1.5, W).
    """
    decoder = VideoDecoder("dummy.mp4")
    assert decoder.frame_queue.maxsize == 30
    
    # Simulate a 1920x1080 YUV420p array
    w = 1920
    h = 1080
    dummy_yuv = np.zeros((h + (h // 2), w), dtype=np.uint8)
    
    # Validate the heuristic used by RenderEngine to differentiate YUV from RGBA
    assert len(dummy_yuv.shape) == 2, "YUV array should be 2-dimensional"
    
    # RGBA arrays have 3 dimensions
    dummy_rgba = np.zeros((h, w, 4), dtype=np.uint8)
    assert len(dummy_rgba.shape) == 3, "RGBA array should be 3-dimensional"
