from collections import OrderedDict
import threading
import numpy as np
from core.logger import hive_logger

class FrameCache:
    """
    A thread-safe, Multi-Scale LRU (Least Recently Used) cache for video frames.
    
    This cache stores BGR Numpy arrays keyed by (PTS, Scale). It enforces memory limits
    based on the actual byte-size (nbytes) of the arrays rather than item count,
    ensuring stability in high-resolution projects.
    """
    
    def __init__(self, max_memory_bytes):
        self.max_memory_bytes = max_memory_bytes
        self.current_memory_bytes = 0
        
        # Internal storage: Key=(pts, scale), Value=numpy_array
        self.cache = OrderedDict()
        self.lock = threading.Lock()
        hive_logger.info(f"FrameCache: Initialized with {max_memory_bytes / (1024*1024):.2f} MB limit.")

    def update_limit(self, new_limit_bytes):
        """Dynamically updates the memory budget and evicts frames if necessary."""
        with self.lock:
            self.max_memory_bytes = new_limit_bytes
            self._enforce_memory_limit()
            hive_logger.debug(f"FrameCache: Limit updated to {new_limit_bytes / (1024*1024):.2f} MB.")

    def get(self, pts, scale=1.0):
        """Retrieves a frame from the cache. Updates LRU order on hit."""
        with self.lock:
            key = (pts, scale)
            if key in self.cache:
                self.cache.move_to_end(key)
                return self.cache[key]
            return None

    def put(self, pts, frame_array, scale=1.0):
        """Adds a new frame to the cache and triggers memory enforcement."""
        if not isinstance(frame_array, np.ndarray): return
        
        with self.lock:
            key = (pts, scale)
            if key in self.cache:
                old_frame = self.cache.pop(key)
                self.current_memory_bytes -= old_frame.nbytes

            frame_size = frame_array.nbytes
            if frame_size > self.max_memory_bytes:
                hive_logger.warning(f"FrameCache: Single frame ({frame_size}b) exceeds cache limit.")
                return

            self.cache[key] = frame_array
            self.current_memory_bytes += frame_size
            self._enforce_memory_limit()

    def _enforce_memory_limit(self):
        """Internal helper to prune the oldest items until under budget."""
        while self.current_memory_bytes > self.max_memory_bytes and self.cache:
            evicted_key, evicted_array = self.cache.popitem(last=False)
            self.current_memory_bytes -= evicted_array.nbytes
            # Noisy debug logs removed for production stability

    def clear(self):
        """Flushes all stored frames and resets memory counters."""
        with self.lock:
            self.cache.clear()
            self.current_memory_bytes = 0
            hive_logger.info("FrameCache: Flushed.")