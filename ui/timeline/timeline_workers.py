# ui/timeline/timeline_workers.py
import os
import queue
import threading
from PySide6.QtCore import QObject, Signal, QThread
from PySide6.QtGui import QImage

try:
    import av
    AV_AVAILABLE = True
except ImportError:
    AV_AVAILABLE = False


class ThumbSignals(QObject):
    """Signals for background thumbnail extraction."""
    loaded = Signal(str, QImage)


class PersistentThumbnailWorker(QThread):
    """Background worker that flawlessly seeks to a specific time in a video and extracts a frame using PyAV."""
    
    _instance = None
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
            cls._instance.start()
        return cls._instance

    def __init__(self):
        super().__init__()
        self.request_queue = queue.Queue()
        self.containers = {}
        self.running = True
        self.signals = ThumbSignals()

    def request_thumbnail(self, file_path, time_ms, height, cache_key, disk_path):
        self.request_queue.put((file_path, time_ms, height, cache_key, disk_path))

    def run(self):
        while self.running:
            try:
                req = self.request_queue.get(timeout=0.1)
                if not req:
                    continue
                file_path, time_ms, height, cache_key, disk_path = req
                
                qimg = QImage()
                if os.path.exists(disk_path):
                    qimg.load(disk_path)
                elif AV_AVAILABLE:
                    try:
                        if file_path not in self.containers:
                            self.containers[file_path] = av.open(file_path)
                        container = self.containers[file_path]
                        stream = container.streams.video[0]
                        
                        target_pts = int((time_ms / 1000.0) / stream.time_base)
                        container.seek(target_pts, stream=stream, any_frame=False)
                        
                        for frame in container.decode(stream):
                            # Allow getting nearest frame
                            if frame.pts >= target_pts or frame.key_frame:
                                img = frame.to_image()
                                w, h = img.size
                                new_w = int(w * (height / h)) if h > 0 else int(height * 1.777)
                                img = img.resize((new_w, height))
                                img.save(disk_path)
                                qimg.load(disk_path)
                                break
                    except Exception as e:
                        print(f"PyAV dynamic thumbnail error: {e}")
                
                try:
                    self.signals.loaded.emit(cache_key, qimg)
                except RuntimeError:
                    pass
            except queue.Empty:
                pass
            except Exception as e:
                pass

    def stop(self):
        self.running = False
        for c in self.containers.values():
            try:
                c.close()
            except:
                pass
        self.containers.clear()
