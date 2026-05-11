import os
import sys
import time
import numpy as np
import cv2

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtGui import QImage, QPainter
from PySide6.QtCore import QCoreApplication

# Ensure Qt App exists
app = QCoreApplication.instance()
if not app:
    app = QCoreApplication(sys.argv)

def create_dummy_video(filename="dummy_test.mp4", width=1920, height=1080, fps=30, frames=30):
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(filename, fourcc, fps, (width, height))
    for i in range(frames):
        # Create a frame with some color and text
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        frame[:] = (i * 8 % 255, 100, 200) # BGR
        cv2.putText(frame, f"Frame {i}", (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        out.write(frame)
    out.release()
    print(f"Created {filename}")

def test_qimage_composition(width=1920, height=1080, iterations=30):
    print(f"\n--- Profiling QImage CPU Composition ({width}x{height}) ---")
    start_time = time.time()
    for i in range(iterations):
        # This simulates RenderEngine._composite_frame
        canvas = QImage(width, height, QImage.Format_RGBA8888)
        canvas.fill(0) # Transparent background
        painter = QPainter(canvas)
        
        # Simulate drawing 2 video layers
        layer1 = QImage(width, height, QImage.Format_RGBA8888)
        layer1.fill(0xFF00FF00) # Green
        painter.drawImage(0, 0, layer1)
        
        layer2 = QImage(width // 2, height // 2, QImage.Format_RGBA8888)
        layer2.fill(0xFFFF0000) # Red
        painter.drawImage(width // 4, height // 4, layer2)
        
        painter.end()
    
    elapsed = time.time() - start_time
    fps = iterations / elapsed
    print(f"Composited {iterations} frames in {elapsed:.4f} seconds ({fps:.2f} FPS)")
    return fps

def test_numpy_conversion(width=1920, height=1080, iterations=30):
    print(f"\n--- Profiling QImage to Numpy Conversion ({width}x{height}) ---")
    canvas = QImage(width, height, QImage.Format_RGBA8888)
    canvas.fill(0xFF00FF00)
    
    start_time = time.time()
    for i in range(iterations):
        ptr = canvas.bits()
        size = canvas.sizeInBytes()
        arr = np.frombuffer(ptr, np.uint8, count=size).reshape((height, width, 4))
        raw_frame = arr.copy()
        
    elapsed = time.time() - start_time
    fps = iterations / elapsed
    print(f"Converted {iterations} frames in {elapsed:.4f} seconds ({fps:.2f} FPS)")
    return fps

def test_video_decoder(filename="dummy_test.mp4"):
    from core.video_decoder import VideoDecoder
    print(f"\n--- Profiling VideoDecoder (CPU YUV->RGBA) ---")
    decoder = VideoDecoder(filename)
    decoder.start()
    
    start_time = time.time()
    frames_decoded = 0
    # Wait for decode
    time.sleep(0.5)
    
    for i in range(30):
        t0 = time.time()
        decoder.seek_to(i * 10.0) # Logical pos
        try:
            logical, frame = decoder.frame_queue.get(timeout=1.0)
            frames_decoded += 1
        except:
            pass
            
    decoder.stop()
    decoder.wait()
    
    elapsed = time.time() - start_time - 0.5
    fps = frames_decoded / elapsed if elapsed > 0 else 0
    print(f"Decoded {frames_decoded} frames in {elapsed:.4f} seconds ({fps:.2f} FPS)")
    return fps

if __name__ == "__main__":
    create_dummy_video()
    
    comp_fps = test_qimage_composition()
    conv_fps = test_numpy_conversion()
    dec_fps = test_video_decoder()
    
    print("\n--- Summary ---")
    if comp_fps < 60:
        print("❌ BUG/BOTTLENECK: QImage CPU Composition is too slow for 60FPS playback.")
    if conv_fps < 120:
        print("❌ BUG/BOTTLENECK: QImage to Numpy copying adds significant overhead on the main thread.")
    if dec_fps < 60:
        print("❌ BUG/BOTTLENECK: VideoDecoder CPU decoding is too slow or stalling.")

    try:
        os.remove("dummy_test.mp4")
    except:
        pass
