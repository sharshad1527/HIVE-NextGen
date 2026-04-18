# ui/timeline/timeline_workers.py
import os
import subprocess
from PySide6.QtCore import QObject, Signal, QRunnable
from PySide6.QtGui import QImage

# Attempt to load OpenCV for dynamic thumbnail extraction fallback
try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False


class ThumbSignals(QObject):
    """Signals for background thumbnail extraction."""
    loaded = Signal(str, QImage)


class FrameFetchWorker(QRunnable):
    """Background worker that flawlessly seeks to a specific time in a video and extracts a frame."""
    def __init__(self, file_path, time_ms, height, cache_key, disk_path):
        super().__init__()
        self.file_path = file_path
        self.time_ms = time_ms
        self.height = height
        self.cache_key = cache_key
        self.disk_path = disk_path
        self.signals = ThumbSignals()

    def run(self):
        qimg = QImage()
        try:
            # 1. Ultra-Fast extraction using FFmpeg
            # We seek BEFORE providing the input (-i) for rapid keyframe seeking (vital for times > 50s)
            sec = self.time_ms / 1000.0
            cmd = [
                "ffmpeg", "-y", 
                "-hwaccel", "auto",  # Offloads decoding to the GPU if available
                "-ss", str(sec), 
                "-i", self.file_path, 
                "-threads", "1",     # Still limit threads to prevent locking up CPU
                "-frames:v", "1", 
                "-q:v", "10",        # Greatly reduced quality requirement for much faster extraction
                "-vf", f"scale=-2:{self.height}", 
                self.disk_path
            ]
            
            kwargs = {}
            if os.name == 'nt':
                # Prevents annoying CMD boxes from flashing on Windows
                kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
                
            # Run FFmpeg (silently, reduced timeout to 15s since GPU/lower quality should be faster)
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15, **kwargs)
            
            if os.path.exists(self.disk_path):
                qimg.load(self.disk_path)
            else:
                # 2. Fallback to OpenCV if FFmpeg fails or isn't available
                if CV2_AVAILABLE:
                    import cv2
                    cap = cv2.VideoCapture(self.file_path)
                    if cap.isOpened():
                        # Try POS_MSEC first, it's faster if the container supports it
                        cap.set(cv2.CAP_PROP_POS_MSEC, self.time_ms)
                        ret, frame = cap.read()
                        if not ret:
                            # Try POS_FRAMES as a final resort (Can be sluggish)
                            fps = cap.get(cv2.CAP_PROP_FPS)
                            if fps and fps > 0:
                                cap.set(cv2.CAP_PROP_POS_FRAMES, int((self.time_ms / 1000.0) * fps))
                                ret, frame = cap.read()
                        
                        if ret:
                            h, w = frame.shape[:2]
                            new_w = int(w * (self.height / h)) if h > 0 else int(self.height * 1.777)
                            if new_w > 0 and self.height > 0:
                                frame_resized = cv2.resize(frame, (new_w, self.height))
                                cv2.imwrite(self.disk_path, frame_resized)
                                qimg.load(self.disk_path)
                        cap.release()
                        
        except Exception as e:
            print(f"Dynamic thumbnail error: {e}")
        finally:
            # Safely emit the signal. If the app is closing, ignore the RuntimeError.
            try:
                self.signals.loaded.emit(self.cache_key, qimg)
            except RuntimeError:
                pass